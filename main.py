import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import aiosqlite
import json
import time
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv
import traceback
from collections import defaultdict
from atomic_file_system import (
    AtomicFileHandler,
    SafeConfig,
    SafeDatabaseManager,
    SafeLogRotator,
    global_file_handler,
    global_log_rotator
)
from rich.console import Console 
from rich.panel import Panel



load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", 0))


class MetricsCollector:
    def __init__(self):
        self.command_count = defaultdict(int)
        self.error_count = 0
        self.start_time = time.time()
        self.messages_seen = 0
        self.commands_processed = 0
    
    def record_command(self, command_name: str):
        self.command_count[command_name] += 1
        self.commands_processed += 1
    
    def record_error(self):
        self.error_count += 1
    
    def record_message(self):
        self.messages_seen += 1
    
    def get_uptime(self) -> float:
        return time.time() - self.start_time
    
    def get_stats(self) -> dict:
        return {
            "uptime": self.get_uptime(),
            "commands_processed": self.commands_processed,
            "messages_seen": self.messages_seen,
            "error_count": self.error_count,
            "top_commands": dict(sorted(self.command_count.items(), key=lambda x: x[1], reverse=True)[:10])
        }


BOT_OWNER_ONLY_COMMANDS = ["reload", "load", "unload", "sync", "atomictest"]


def is_bot_owner():
    async def predicate(ctx):
        if ctx.author.id != BOT_OWNER_ID:
            raise commands.CheckFailure("This command is restricted to the bot owner only.")
        return True
    return commands.check(predicate)


def is_bot_owner_or_guild_owner():
    async def predicate(ctx):
        if ctx.author.id == BOT_OWNER_ID:
            return True
        if ctx.guild and ctx.guild.owner_id == ctx.author.id:
            return True
        raise commands.CheckFailure("This command requires bot owner or guild owner permissions.")
    return commands.check(predicate)


def has_command_permission():
    async def predicate(ctx):
        if ctx.author.id == BOT_OWNER_ID:
            return True
        
        command_name = ctx.command.qualified_name
        
        if command_name in BOT_OWNER_ONLY_COMMANDS:
            raise commands.CheckFailure(f"The command '{command_name}' is restricted to the bot owner.")
        
        required_roles = ctx.bot.config.get(f"command_permissions.{command_name}", [])
        
        if not required_roles:
            return True
        
        if not ctx.guild:
            raise commands.CheckFailure("This command cannot be used in DMs.")
        
        member_role_ids = [role.id for role in ctx.author.roles]
        if not any(role_id in member_role_ids for role_id in required_roles):
            raise commands.CheckFailure(f"You need one of the required roles to use '{command_name}'.")
        
        return True
    
    return commands.check(predicate)


async def check_app_command_permissions(interaction: discord.Interaction, command_name: str) -> bool:
    if interaction.user.id == BOT_OWNER_ID:
        return True
    
    if command_name in BOT_OWNER_ONLY_COMMANDS:
        await interaction.response.send_message(
            f"❌ The command `/{command_name}` is restricted to the bot owner only.",
            ephemeral=True
        )
        return False
    
    bot = interaction.client
    required_roles = bot.config.get(f"command_permissions.{command_name}", [])
    
    if not required_roles:
        return True
    
    if not interaction.guild:
        await interaction.response.send_message(
            "❌ This command cannot be used in DMs.",
            ephemeral=True
        )
        return False
    
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        await interaction.response.send_message(
            "❌ Unable to verify your permissions.",
            ephemeral=True
        )
        return False
    
    member_role_ids = [role.id for role in member.roles]
    if not any(role_id in member_role_ids for role_id in required_roles):
        role_mentions = ", ".join([f"<@&{rid}>" for rid in required_roles[:3]])
        await interaction.response.send_message(
            f"❌ You need one of these roles to use this command: {role_mentions}",
            ephemeral=True
        )
        return False
    
    return True


async def command_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    commands_list = [cmd.name for cmd in interaction.client.commands]
    return [
        app_commands.Choice(name=cmd, value=cmd)
        for cmd in commands_list
        if current.lower() in cmd.lower()
    ][:25]


class BotFrameWork(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config: Optional[SafeConfig] = None
        self.db: Optional[SafeDatabaseManager] = None
        self.metrics = MetricsCollector()
        self.extension_load_times: Dict[str, float] = {}
        self.last_extension_check = time.time()
        self._shutdown_event = asyncio.Event()
        self._slash_synced = False
        self.bot_owner_id = BOT_OWNER_ID



    async def setup_hook(self):
        self.config = SafeConfig(file_handler=global_file_handler)
        await self.config.initialize()
        
        db_path = self.config.get("database.path", "./data/bot.db")
        self.db = SafeDatabaseManager(db_path, file_handler=global_file_handler)
        await self.db.connect()
        
        if self.config.get("extensions.auto_load", True):
            await self.load_all_extensions()
        
        self.status_update_task.start()
        
        if self.config.get("auto_reload", False):
            self.extension_reloader.start()
        
        self.log_rotation_task.start()
    
    async def load_all_extensions(self):
        loaded = 0
        failed = 0
        blacklist = self.config.get("extensions.blacklist", [])
        
        extensions_path = Path("./extensions")
        if not extensions_path.exists():
            extensions_path.mkdir(parents=True)
            logger.warning("Created extensions directory")
            return
        

        for filepath in list(extensions_path.glob("*.py")):
            ext_name = filepath.stem
            original_filepath = filepath 


            if " " in ext_name:
                new_ext_name = ext_name.replace(" ", "_")
                new_filepath = extensions_path / f"{new_ext_name}.py"
                

                if new_filepath.exists():
                    logger.warning(f"Conflicting extensions found: '{original_filepath.name}' and '{new_filepath.name}'. Skipping the one with space.")
                    continue
                
                try:
                    original_filepath.rename(new_filepath)
                    logger.warning(f"Renamed illegal extension '{original_filepath.name}' to '{new_filepath.name}' during startup.")
                    filepath = new_filepath 
                    ext_name = new_ext_name 
                except Exception as e:
                    logger.error(f"Failed to rename {original_filepath.name} during startup: {e}")
                    failed += 1
                    continue

            
            if ext_name in blacklist:
                logger.info(f"Skipped blacklisted: {filepath.name}")
                continue
            
            try:

                start_time = time.time()
                await self.load_extension(f"extensions.{ext_name}")
                load_time = time.time() - start_time
                self.extension_load_times[ext_name] = load_time
                logger.info(f"Extension loaded: {ext_name}.py ({load_time:.3f}s)")
                loaded += 1
            except Exception as e:
                logger.error(f"Failed loading {ext_name}.py: {e}")
                logger.debug(traceback.format_exc())
                failed += 1
        
        logger.info(f"Extensions: {loaded} loaded, {failed} failed")
    
    @tasks.loop(seconds=30)
    async def extension_reloader(self):
        extensions_path = Path("./extensions")
        if not extensions_path.exists():
            return
        
        for filepath in extensions_path.glob("*.py"):
            ext_name = f"extensions.{filepath.stem}"
            file_mtime = filepath.stat().st_mtime
            
            if file_mtime > self.last_extension_check and ext_name in self.extensions:
                try:
                    await self.reload_extension(ext_name)
                    logger.info(f"Hot-reloaded: {filepath.name}")

                    self.extension_load_times[filepath.stem] = time.time() - self.last_extension_check
                except Exception as e:
                    logger.error(f"Failed to reload {filepath.name}: {e}")
        
        self.last_extension_check = time.time()
    
    @extension_reloader.before_loop
    async def before_extension_reloader(self):
        await self.wait_until_ready()
    
    @tasks.loop(hours=1)
    async def log_rotation_task(self):
        permanent_log = Path("./botlogs/permanent.log")
        if await global_log_rotator.should_rotate(permanent_log):
            await global_log_rotator.rotate_log(permanent_log)
            logger.info("Rotated permanent log file")
        
        await global_log_rotator.cleanup_old_logs(days=30)
    
    @log_rotation_task.before_loop
    async def before_log_rotation(self):
        await self.wait_until_ready()
    

    @tasks.loop(minutes=5)
    async def status_update_task(self):
        status_config = self.config.get("status", {})
        status_text = status_config.get("text", "{guilds} servers")
        status_type = status_config.get("type", "watching")
        
        text = status_text.format(
            guilds=len(self.guilds),
            users=len(self.users),
            commands=len(self.commands)
        )
        
        activity_map = {
            "playing": discord.ActivityType.playing,
            "watching": discord.ActivityType.watching,
            "listening": discord.ActivityType.listening,
            "competing": discord.ActivityType.competing
        }
        
        activity_type = activity_map.get(status_type.lower(), discord.ActivityType.watching)
        activity = discord.Activity(type=activity_type, name=text)
        await self.change_presence(activity=activity)
    


    @status_update_task.before_loop
    async def before_status_update(self):
        await self.wait_until_ready()
    
    async def get_prefix(self, message: discord.Message):
        if not message.guild:
            return self.config.get("prefix", "!")
        
        custom_prefix = await self.db.get_guild_prefix(message.guild.id)
        return custom_prefix if custom_prefix else self.config.get("prefix", "!")
    
    async def sync_commands(self, force: bool = False):
        if self._slash_synced and not force:
            logger.info("Commands already synced, skipping")
            return 0
        
        try:
            logger.info("Starting command sync process...")
            
            synced = await self.tree.sync()
            self._slash_synced = True
            logger.info(f"Successfully synced {len(synced)} slash commands globally")
            
            for cmd in synced:
                logger.debug(f"  - Synced: /{cmd.name}")
            
            return len(synced)
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', 60)
                logger.warning(f"Rate limited during sync, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                return await self.sync_commands(force=True)
            else:
                logger.error(f"HTTP error during sync: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
            logger.debug(traceback.format_exc())
            raise
    
    async def close(self):
        logger.info("Shutting down bot...")
        
        self.status_update_task.cancel()
        if hasattr(self, 'extension_reloader'):
            self.extension_reloader.cancel()
        if hasattr(self, 'log_rotation_task'):
            self.log_rotation_task.cancel()
        
        if self.db:
            await self.db.backup()
            await self.db.close()
        
        await super().close()
        logger.info("Bot shutdown complete")


def setup_logging():
    os.makedirs("./botlogs", exist_ok=True)
    
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '[{asctime}] [{levelname:<8}] {name}: {message}',
        style='{',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    permanent_handler = RotatingFileHandler(
        filename='./botlogs/permanent.log',
        encoding='utf-8',
        maxBytes=10485760,
        backupCount=5
    )
    permanent_handler.setFormatter(formatter)
    
    current_handler = logging.FileHandler(
        filename='./botlogs/current_run.log',
        encoding='utf-8',
        mode='w'
    )
    current_handler.setFormatter(formatter)
    
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    
    logger.addHandler(permanent_handler)
    logger.addHandler(current_handler)
    logger.addHandler(console)
    
    return logger


logger = setup_logging()

intents = discord.Intents.all()
bot = BotFrameWork(
    command_prefix=lambda b, m: b.get_prefix(m),
    intents=intents,
    help_command=None,
    case_insensitive=True,
    strip_after_prefix=True
)


@bot.event
async def on_ready():
    console = Console()
    

    uptime_str = str(timedelta(seconds=int(bot.metrics.get_uptime()))).split('.')[0]
    
    stats_info = (
        f"**User:** [bold blue]{bot.user}[/bold blue] (ID: {bot.user.id})\n"
        f"**Owner:** [bold yellow]{BOT_OWNER_ID}[/bold yellow]\n"
        f"**Status:** [bold green]Online[/bold green]\n"
        f"**Latency:** [bold magenta]{bot.latency*1000:.2f}ms[/bold magenta]\n"
        f"**Uptime:** {uptime_str}\n"
        f"**Servers:** [bold]{len(bot.guilds)}[/bold] | **Users:** [bold]{len(bot.users)}[/bold]\n"
        f"**Commands:** [bold]{len(bot.tree.get_commands())}[/bold] (Slash)"
    )
    
    panel = Panel(
        stats_info,
        title="[bold white on blue] 🤖 Bot Framework Started [/bold white on blue]",
        subtitle=f"[dim]Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
        border_style="cyan",
        width=80
    )
    
    console.print(panel)
    
    logger.info(f"Bot is online as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Bot Owner ID: {BOT_OWNER_ID}")
    logger.info(f"Connected to {len(bot.guilds)} servers")
    logger.info(f"Serving {len(bot.users)} users")
    logger.info(f"Registered commands: {len(bot.tree.get_commands())}")
    logger.info(f"Latency: {bot.latency*1000:.2f}ms")
    
    try:
        synced_count = await bot.sync_commands()
        logger.info(f"Initial sync complete: {synced_count} commands")
    except Exception as e:
        logger.error(f"Failed initial sync: {e}")
        logger.debug(traceback.format_exc())

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    
    
    if message.guild and bot.user.mentioned_in(message) and len(message.mentions) == 1:
        
        mention_no_nick = f"<@{bot.user.id}>"
        mention_with_nick = f"<@!{bot.user.id}>"
        
        content_after_mention = message.content.strip()
        
        if content_after_mention.startswith(mention_with_nick):
            content_after_mention = content_after_mention.replace(mention_with_nick, "", 1).strip()
        
        elif content_after_mention.startswith(mention_no_nick):
            content_after_mention = content_after_mention.replace(mention_no_nick, "", 1).strip()
        
        if not content_after_mention:
            
            prefix = await bot.get_prefix(message)
            if isinstance(prefix, list):
                prefix = prefix[0]
            
            
            embed = discord.Embed(
                title="🤖 Discord Bot Framework",
                description="**Hello! I'm a bot built on an advanced, extensible framework.**\n",
                color=0x5865f2,
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(
                name="🔗 Quick Info",
                value=f"```Prefix: {prefix}\nSlash: / (Always available)```",
                inline=False
            )
            
            embed.add_field(
                name="💡 More Information & Help",
                value=(
                    f"To see the list of all commands, use **`{prefix}help`** or **`/help`**.\n"
                    f"For framework information and features, use **`{prefix}discordbotframework`** or **`/discordbotframework`**."
                ),
                inline=False
            )

            embed.add_field(
                name="👤 Original Creator",
                value="**TheHolyOneZ**\n[GitHub Repository](https://github.com/TheHolyOneZ/discord-bot-framework)",
                inline=False
            )
            
            embed.set_footer(text=f"Serving {len(bot.guilds)} servers | Latency: {bot.latency*1000:.2f}ms")
            embed.set_thumbnail(url=bot.user.display_avatar.url)

            await message.channel.send(embed=embed)
            
            return 
    
    
    bot.metrics.record_message()
    await bot.process_commands(message)


@bot.event
async def on_command(ctx: commands.Context):
    bot.metrics.record_command(ctx.command.name)
    await bot.db.increment_command_usage(ctx.command.name)
    logger.info(f"Command: {ctx.command.name} | User: {ctx.author} | Guild: {ctx.guild}")


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    bot.metrics.record_error()
    
    if isinstance(error, commands.CommandNotFound):
        return
    
    embed = discord.Embed(color=0xff0000, timestamp=discord.utils.utcnow())
    delete_after = 10
    
    if isinstance(error, commands.CheckFailure):
        embed.title = "❌ Permission Denied"
        embed.description = "```You don't have permission to use this command```"
    
    elif isinstance(error, commands.MissingPermissions):
        embed.title = "❌ Missing Permissions"
        embed.description = f"```You lack permissions: {', '.join(error.missing_permissions)}```"
    
    elif isinstance(error, commands.BotMissingPermissions):
        embed.title = "❌ Bot Missing Permissions"
        embed.description = f"```I lack permissions: {', '.join(error.missing_permissions)}```"
    
    elif isinstance(error, commands.CommandOnCooldown):
        embed.title = "⏱️ Command on Cooldown"
        embed.description = f"```Cooldown: {error.retry_after:.1f}s remaining```"
    
    elif isinstance(error, commands.MissingRequiredArgument):
        embed.title = "❌ Missing Argument"
        embed.description = f"```Missing argument: {error.param.name}```"
    
    elif isinstance(error, commands.BadArgument):
        embed.title = "❌ Invalid Argument"
        embed.description = f"```Invalid argument provided```"
    
    else:
        logger.error(f"Unhandled error in {ctx.command}: {error}")
        logger.debug(traceback.format_exc())
        embed.title = "❌ Command Error"
        embed.description = f"```py\n{str(error)[:200]}```"
        delete_after = 15
    
    embed.set_footer(text=f"Command: {ctx.command.name}")
    msg = await ctx.send(embed=embed)
    await asyncio.sleep(delete_after)
    try:
        await msg.delete()
    except:
        pass


@bot.event
async def on_guild_join(guild: discord.Guild):
    logger.info(f"Joined guild: {guild.name} (ID: {guild.id}) | Members: {guild.member_count}")


@bot.event
async def on_guild_remove(guild: discord.Guild):
    logger.info(f"Left guild: {guild.name} (ID: {guild.id})")


@bot.hybrid_command(name="help", help="Display the help menu")
@has_command_permission()
async def help_command(ctx):
    if ctx.interaction:
        if not await check_app_command_permissions(ctx.interaction, "help"):
            return
    categories = {}
    
    main_commands = [cmd for cmd in bot.commands if cmd.cog is None and not cmd.hidden]
    if main_commands:
        categories["Main"] = main_commands
    
    for cog_name, cog in bot.cogs.items():
        cmds = [cmd for cmd in cog.get_commands() if not cmd.hidden]
        if cmds:
            categories[cog_name] = cmds
    
    prefix = await bot.get_prefix(ctx.message)
    if isinstance(prefix, list):
        prefix = prefix[0]
    
    embed = discord.Embed(
        title="📚 Help Menu",
        description="**Select a category from the dropdown menu**\n\n"
                    f"```Available Categories: {len(categories)}\nCurrent Prefix: {prefix}```",
        color=0x2b2d31,
        timestamp=discord.utils.utcnow()
    )
    
    embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    if not categories:
        embed.description = "❌ No commands available"
        await ctx.send(embed=embed)
        return
    
    view = HelpView(categories, ctx.author, prefix)
    await ctx.send(embed=embed, view=view)
    logger.info(f"Help menu requested by {ctx.author} in {ctx.guild}")
    
    try:
        await ctx.message.delete()
    except:
        pass


@bot.hybrid_command(name="stats", help="Display bot statistics and metrics")
@commands.cooldown(1, 10, commands.BucketType.user)
@has_command_permission()
async def stats_command(ctx):
    if ctx.interaction:
        if not await check_app_command_permissions(ctx.interaction, "stats"):
            return
    stats = bot.metrics.get_stats()
    
    uptime_seconds = int(stats['uptime'])
    uptime_str = str(timedelta(seconds=uptime_seconds))
    
    embed = discord.Embed(
        title="📊 Bot Statistics",
        color=0x00ff00,
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(name="⏱️ Uptime", value=f"```{uptime_str}```", inline=True)
    embed.add_field(name="🌐 Guilds", value=f"```{len(bot.guilds)}```", inline=True)
    embed.add_field(name="👥 Users", value=f"```{len(bot.users)}```", inline=True)
    embed.add_field(name="📝 Commands Processed", value=f"```{stats['commands_processed']}```", inline=True)
    embed.add_field(name="💬 Messages Seen", value=f"```{stats['messages_seen']}```", inline=True)
    embed.add_field(name="🔧 Extensions Loaded", value=f"```{len(bot.extensions)}```", inline=True)
    embed.add_field(name="📡 Latency", value=f"```{bot.latency*1000:.2f}ms```", inline=True)
    embed.add_field(name="❌ Errors", value=f"```{stats['error_count']}```", inline=True)
    embed.add_field(name="📋 Slash Commands", value=f"```{len(bot.tree.get_commands())}```", inline=True)
    
    if stats['top_commands']:
        top_cmds = '\n'.join([f"{cmd}: {count}" for cmd, count in list(stats['top_commands'].items())[:5]])
        embed.add_field(name="🔥 Top Commands", value=f"```{top_cmds}```", inline=False)
    
    embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)
    
    try:
        await ctx.message.delete()
    except:
        pass


@bot.hybrid_command(name="atomictest", help="Test atomic file operations")
@is_bot_owner()
async def atomictest_command(ctx):
    if ctx.interaction:
        if not await check_app_command_permissions(ctx.interaction, "atomictest"):
            return
    embed = discord.Embed(
        title="🧪 Atomic File Operations Test",
        description="Running tests...",
        color=0xffff00,
        timestamp=discord.utils.utcnow()
    )
    msg = await ctx.send(embed=embed)
    
    results = []
    test_file = "./data/atomic_test.json"
    
    try:
        test_data = {"test": "data", "timestamp": datetime.now().isoformat(), "count": 42}
        
        start = time.time()
        success = await global_file_handler.atomic_write_json(test_file, test_data)
        write_time = (time.time() - start) * 1000
        results.append(f"✅ Write: {write_time:.2f}ms" if success else "❌ Write failed")
        
        start = time.time()
        read_data = await global_file_handler.atomic_read_json(test_file, use_cache=False)
        read_time = (time.time() - start) * 1000
        results.append(f"✅ Read (no cache): {read_time:.2f}ms" if read_data else "❌ Read failed")
        
        start = time.time()
        cached_data = await global_file_handler.atomic_read_json(test_file, use_cache=True)
        cached_time = (time.time() - start) * 1000
        results.append(f"✅ Read (cached): {cached_time:.2f}ms" if cached_data else "❌ Cache failed")
        
        if read_data == test_data:
            results.append("✅ Data integrity verified")
        else:
            results.append("❌ Data corruption detected")
        
        tasks = []
        for i in range(10):
            test_concurrent = {"concurrent": i, "timestamp": datetime.now().isoformat()}
            tasks.append(global_file_handler.atomic_write_json(f"./data/test_{i}.json", test_concurrent))
        
        start = time.time()
        await asyncio.gather(*tasks)
        concurrent_time = (time.time() - start) * 1000
        results.append(f"✅ 10 concurrent writes: {concurrent_time:.2f}ms")
        
        for i in range(10):
            try:
                os.remove(f"./data/test_{i}.json")
            except:
                pass
        
        embed.title = "✅ Atomic File Operations Test Complete"
        embed.description = "```\n" + "\n".join(results) + "```"
        embed.color = 0x00ff00
        embed.add_field(
            name="Cache Info",
            value=f"```Cache entries: {len(global_file_handler._cache)}\nCache TTL: {global_file_handler._cache_ttl}s```",
            inline=False
        )
        
    except Exception as e:
        embed.title = "❌ Test Failed"
        embed.description = f"```py\n{str(e)[:200]}```"
        embed.color = 0xff0000
        logger.error(f"Atomic test error: {e}")
        logger.debug(traceback.format_exc())
    
    await msg.edit(embed=embed)
    
    try:
        await ctx.message.delete()
    except:
        pass


@bot.hybrid_command(name="sync", help="Force sync slash commands (Bot Owner Only)")
@is_bot_owner()
async def sync_command(ctx):
    if ctx.interaction:
        if not await check_app_command_permissions(ctx.interaction, "sync"):
            return
    embed = discord.Embed(
        title="🔄 Syncing Commands...",
        description="```Please wait...```",
        color=0xffff00,
        timestamp=discord.utils.utcnow()
    )
    msg = await ctx.send(embed=embed)
    
    try:
        logger.info(f"Manual sync initiated by {ctx.author}")
        count = await bot.sync_commands(force=True)
        
        embed.title = "✅ Sync Complete"
        embed.description = f"```Successfully synced {count} commands```"
        embed.color = 0x00ff00
        
        commands_list = [cmd.name for cmd in bot.tree.get_commands()]
        if commands_list:
            embed.add_field(
                name="Synced Commands",
                value=f"```{', '.join(commands_list)}```",
                inline=False
            )
        
        await msg.edit(embed=embed)
        logger.info(f"Commands manually synced: {count} commands")
    except Exception as e:
        embed.title = "❌ Sync Failed"
        embed.description = f"```{str(e)[:200]}```"
        embed.color = 0xff0000
        await msg.edit(embed=embed)
        logger.error(f"Manual sync failed: {e}")
        logger.debug(traceback.format_exc())
    
    try:
        await ctx.message.delete()
    except:
        pass

@bot.hybrid_command(name="reload", help="Reload a specific extension (Bot Owner Only)")
@is_bot_owner()
async def reload_command(ctx, *, extension: str):
    if ctx.interaction:
        if not await check_app_command_permissions(ctx.interaction, "reload"):
            return

    extension_name_with_space = extension.strip()
    extension_name_with_underscore = extension_name_with_space.replace(" ", "_")
    
    extensions_path = Path("./extensions")
    path_with_space = extensions_path / f"{extension_name_with_space}.py"
    path_with_underscore = extensions_path / f"{extension_name_with_underscore}.py"
    
    final_ext_to_load = None
    rename_message = None

    if path_with_space.exists():
        try:
            path_with_space.rename(path_with_underscore)
            final_ext_to_load = extension_name_with_underscore

            rename_message = (
                f"Found '{path_with_space.name}', renamed it to '{path_with_underscore.name}'. "
                f"Use `!reload {extension_name_with_underscore}` or `!unload {extension_name_with_underscore}` for future operations."
            )
            logger.info(f"Renamed extension: {path_with_space.name} -> {path_with_underscore.name}")
        except Exception as e:
            embed = discord.Embed(
                title="❌ File Rename Failed",
                description=f"```Found {path_with_space.name}, but failed to rename it:\n{e}```",
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
            await ctx.send(embed=embed)
            logger.error(f"Failed to rename {path_with_space.name}: {e}")
            return

    elif path_with_underscore.exists():
        final_ext_to_load = extension_name_with_underscore
    
    if not final_ext_to_load:
        embed = discord.Embed(
            title="❌ Extension Not Found",
            description=f"```Could not find '{path_with_space.name}' or '{path_with_underscore.name}'```",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass
        return
    
    try:
        start_time = time.time() 
        await bot.reload_extension(f"extensions.{final_ext_to_load}")
        load_time = time.time() - start_time 
        bot.extension_load_times[final_ext_to_load] = load_time 

        embed = discord.Embed(
            title="✅ Extension Reloaded",
            description=f"```Successfully reloaded: {final_ext_to_load} ({load_time:.3f}s)```", 
            color=0x00ff00,
            timestamp=discord.utils.utcnow()
        )
        if rename_message:
            embed.add_field(name="ℹ️ Note", value=f"```{rename_message}```", inline=False)
        
        await ctx.send(embed=embed)
        logger.info(f"Extension reloaded by {ctx.author}: {final_ext_to_load}")
        
        try:
            await ctx.message.delete()
        except:
            pass
    except Exception as e:
        embed = discord.Embed(
            title="❌ Reload Failed",
            description=f"```An error occurred while reloading {final_ext_to_load}:\n{str(e)[:200]}```",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        msg = await ctx.send(embed=embed)
        logger.error(f"Failed to reload {final_ext_to_load}: {e}")
        await asyncio.sleep(10)
        try:
            await msg.delete()
        except:
            pass
@bot.hybrid_command(name="load", help="Load a specific extension (Bot Owner Only)")
@is_bot_owner()
async def load_command(ctx, *, extension: str):
    if ctx.interaction:
        if not await check_app_command_permissions(ctx.interaction, "load"):
            return

    extension_name_with_space = extension.strip()
    extension_name_with_underscore = extension_name_with_space.replace(" ", "_")
    
    extensions_path = Path("./extensions")
    path_with_space = extensions_path / f"{extension_name_with_space}.py"
    path_with_underscore = extensions_path / f"{extension_name_with_underscore}.py"
    
    final_ext_to_load = None
    rename_message = None

    if path_with_space.exists():
        try:
            path_with_space.rename(path_with_underscore)
            final_ext_to_load = extension_name_with_underscore

            rename_message = (
                f"Found '{path_with_space.name}', renamed it to '{path_with_underscore.name}'. "
                f"Use `!reload {extension_name_with_underscore}` or `!unload {extension_name_with_underscore}` for future operations."
            )
            logger.info(f"Renamed extension: {path_with_space.name} -> {path_with_underscore.name}")
        except Exception as e:
            embed = discord.Embed(
                title="❌ File Rename Failed",
                description=f"```Found {path_with_space.name}, but failed to rename it:\n{e}```",
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
            await ctx.send(embed=embed)
            logger.error(f"Failed to rename {path_with_space.name}: {e}")
            return

    elif path_with_underscore.exists():
        final_ext_to_load = extension_name_with_underscore
    
    if not final_ext_to_load:
        embed = discord.Embed(
            title="❌ Extension Not Found",
            description=f"```Could not find '{path_with_space.name}' or '{path_with_underscore.name}'```",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass
        return
    
    try:
        start_time = time.time()
        await bot.load_extension(f"extensions.{final_ext_to_load}")
        load_time = time.time() - start_time
        bot.extension_load_times[final_ext_to_load] = load_time
        
        embed = discord.Embed(
            title="✅ Extension Loaded",
            description=f"```Successfully loaded: {final_ext_to_load} ({load_time:.3f}s)```",
            color=0x00ff00,
            timestamp=discord.utils.utcnow()
        )
        if rename_message:
            embed.add_field(name="ℹ️ Note", value=f"```{rename_message}```", inline=False)
            
        await ctx.send(embed=embed)
        logger.info(f"Extension loaded by {ctx.author}: {final_ext_to_load}")
        
        try:
            await ctx.message.delete()
        except:
            pass
    except Exception as e:
        error_str = str(e)
        

        if "already loaded" in error_str or isinstance(e, commands.ExtensionAlreadyLoaded):
            embed = discord.Embed(
                title="❌ Extension Already Loaded",
                description=f"```Extension '{final_ext_to_load}' is already loaded. Use !reload {final_ext_to_load} if you wish to update it.```",
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
        else:
            embed = discord.Embed(
                title="❌ Load Failed",
                description=f"```An error occurred while loading {final_ext_to_load}:\n{error_str[:200]}```",
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
        
        msg = await ctx.send(embed=embed)
        logger.error(f"Failed to load {final_ext_to_load}: {e}")
        await asyncio.sleep(10)
        try:
            await msg.delete()
        except:
            pass


@bot.hybrid_command(name="unload", help="Unload a specific extension (Bot Owner Only)")
@is_bot_owner()
async def unload_command(ctx, *, extension: str):
    if ctx.interaction:
        if not await check_app_command_permissions(ctx.interaction, "unload"):
            return
    
    ext_name_underscore = f"extensions.{extension.strip().replace(' ', '_')}"
    ext_name_no_space = f"extensions.{extension.strip().replace(' ', '')}"
    
    final_ext_name = None
    
    if ext_name_underscore in bot.extensions:
        final_ext_name = ext_name_underscore
    elif ext_name_no_space in bot.extensions:
        final_ext_name = ext_name_no_space

    if not final_ext_name:
        embed = discord.Embed(
            title="❌ Extension Not Loaded",
            description=f"```Extension '{extension}' is not currently loaded```",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass
        return
    
    try:
        await bot.unload_extension(final_ext_name)
        simple_name = final_ext_name.replace("extensions.", "")
        

        if simple_name in bot.extension_load_times:
            del bot.extension_load_times[simple_name]
            
        embed = discord.Embed(
            title="✅ Extension Unloaded",
            description=f"```Successfully unloaded: {simple_name}```",
            color=0x00ff00,
            timestamp=discord.utils.utcnow()
        )
        await ctx.send(embed=embed)
        logger.info(f"Extension unloaded by {ctx.author}: {simple_name}")
        
        try:
            await ctx.message.delete()
        except:
            pass
    except Exception as e:
        embed = discord.Embed(
            title="❌ Unload Failed",
            description=f"```{str(e)[:200]}```",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        msg = await ctx.send(embed=embed)
        logger.error(f"Failed to unload {final_ext_name}: {e}")
        await asyncio.sleep(10)
        try:
            await msg.delete()
        except:
            pass

@bot.hybrid_command(name="extensions", help="List all loaded extensions")
@commands.cooldown(1, 10, commands.BucketType.user)
@has_command_permission()
async def extensions_command(ctx):
    if ctx.interaction:
        if not await check_app_command_permissions(ctx.interaction, "extensions"):
            return
    if not bot.extensions:
        embed = discord.Embed(
            title="❌ No Extensions",
            description="```No extensions loaded```",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title="🔌 Loaded Extensions",
        color=0x5865f2,
        timestamp=discord.utils.utcnow()
    )
    
    ext_list = []
    for ext_name in sorted(bot.extensions.keys()):
        simple_name = ext_name.replace("extensions.", "")
        load_time = bot.extension_load_times.get(simple_name, 0)
        ext_list.append(f"• {simple_name} ({load_time:.3f}s)")
    
    embed.description = "```" + "\n".join(ext_list) + "```"
    embed.set_footer(text=f"Total: {len(bot.extensions)} extensions")
    await ctx.send(embed=embed)
    
    try:
        await ctx.message.delete()
    except:
        pass


@bot.hybrid_command(name="setprefix", help="Set a custom prefix for this server")
@commands.has_permissions(administrator=True)
@commands.guild_only()
@has_command_permission()
async def setprefix_command(ctx, prefix: str):
    if ctx.interaction:
        if not await check_app_command_permissions(ctx.interaction, "setprefix"):
            return
    if len(prefix) > 5:
        embed = discord.Embed(
            title="❌ Invalid Prefix",
            description="```Prefix must be 5 characters or less```",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass
        return
    
    await bot.db.set_guild_prefix(ctx.guild.id, prefix)
    embed = discord.Embed(
        title="✅ Prefix Changed",
        description=f"```Prefix changed to: {prefix}```",
        color=0x00ff00,
        timestamp=discord.utils.utcnow()
    )
    await ctx.send(embed=embed)
    logger.info(f"Prefix changed in {ctx.guild.name} to: {prefix}")
    
    try:
        await ctx.message.delete()
    except:
        pass


@bot.hybrid_command(name="config", help="Configure command role permissions (Guild Owner or Bot Owner)")
@is_bot_owner_or_guild_owner()
@commands.guild_only()
@app_commands.describe(
    command_name="The command to configure",
    role="The role to grant access"
)
@app_commands.autocomplete(command_name=command_autocomplete)
async def config_command(ctx, command_name: str = None, role: discord.Role = None):
    if ctx.interaction:
        user_id = ctx.interaction.user.id
        prefix = "/"
    else:
        user_id = ctx.author.id
        prefix = await bot.get_prefix(ctx.message)
        if isinstance(prefix, list):
            prefix = prefix[0]
    
    is_owner = user_id == BOT_OWNER_ID
    
    if not command_name:
        embed = discord.Embed(
            title="⚙️ Command Configuration",
            description=f"**Usage:**\n```{prefix}config <command_name> <@role>```\n\n"
                       f"**Example:**\n```{prefix}config help @Moderator```\n\n"
                       f"**Remove restrictions:**\n```{prefix}config <command_name> none```",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        configurable_cmds = []
        restricted_cmds = []
        
        for cmd in sorted([cmd.name for cmd in bot.commands]):
            if cmd in BOT_OWNER_ONLY_COMMANDS:
                restricted_cmds.append(cmd)
            else:
                configurable_cmds.append(cmd)
        
        if configurable_cmds:
            embed.add_field(
                name="✅ Configurable Commands",
                value=f"```{', '.join(configurable_cmds)}```",
                inline=False
            )
        
        if restricted_cmds and is_owner:
            embed.add_field(
                name="🔒 Bot Owner Only",
                value=f"```{', '.join(restricted_cmds)}```",
                inline=False
            )
        elif restricted_cmds and not is_owner:
            embed.add_field(
                name="🔒 Bot Owner Only (Not Configurable)",
                value=f"```{', '.join(restricted_cmds)}```",
                inline=False
            )
        
        current_perms = bot.config.get("command_permissions", {})
        if current_perms:
            perm_list = []
            for cmd, role_ids in current_perms.items():
                roles_str = ", ".join([f"<@&{rid}>" for rid in role_ids])
                perm_list.append(f"• {cmd}: {roles_str}")
            
            if perm_list:
                embed.add_field(
                    name="📋 Current Permissions",
                    value="\n".join(perm_list[:10]),
                    inline=False
                )
        
        embed.set_footer(
            text=f"You are: {'Bot Owner' if is_owner else 'Guild Owner'}",
            icon_url=ctx.author.display_avatar.url
        )
        
        await ctx.send(embed=embed)
        try:
            await ctx.message.delete()
        except:
            pass
        return
    
    if command_name not in [cmd.name for cmd in bot.commands]:
        embed = discord.Embed(
            title="❌ Command Not Found",
            description=f"```Command '{command_name}' does not exist```",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass
        return
    
    if command_name in BOT_OWNER_ONLY_COMMANDS and not is_owner:
        embed = discord.Embed(
            title="🔒 Restricted Command",
            description=f"```Command '{command_name}' is restricted to the bot owner and cannot be configured by guild owners```",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass
        return
    
    if role is None and command_name.lower() != "none":
        embed = discord.Embed(
            title="❌ Missing Role",
            description=f"```Please specify a role or use 'none' to remove restrictions```",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass
        return
    
    current_perms = bot.config.get("command_permissions", {})
    
    if command_name.lower() == "none" or role is None:
        if command_name in BOT_OWNER_ONLY_COMMANDS and not is_owner:
            embed = discord.Embed(
                title="🔒 Access Denied",
                description=f"```You cannot modify permissions for bot owner commands```",
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
            msg = await ctx.send(embed=embed)
            await asyncio.sleep(5)
            try:
                await msg.delete()
            except:
                pass
            return
        
        if command_name in current_perms:
            del current_perms[command_name]
            await bot.config.set("command_permissions", current_perms)
            embed = discord.Embed(
                title="✅ Permissions Removed",
                description=f"```Removed role restrictions from: {command_name}```",
                color=0x00ff00,
                timestamp=discord.utils.utcnow()
            )
        else:
            embed = discord.Embed(
                title="ℹ️ No Restrictions",
                description=f"```Command '{command_name}' has no role restrictions```",
                color=0x5865f2,
                timestamp=discord.utils.utcnow()
            )
    else:
        if command_name in BOT_OWNER_ONLY_COMMANDS and not is_owner:
            embed = discord.Embed(
                title="🔒 Access Denied",
                description=f"```You cannot add permissions to bot owner commands```",
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
            msg = await ctx.send(embed=embed)
            await asyncio.sleep(5)
            try:
                await msg.delete()
            except:
                pass
            return
        
        if command_name not in current_perms:
            current_perms[command_name] = []
        
        if role.id in current_perms[command_name]:
            embed = discord.Embed(
                title="ℹ️ Already Configured",
                description=f"```Role {role.name} already has access to {command_name}```",
                color=0x5865f2,
                timestamp=discord.utils.utcnow()
            )
        else:
            current_perms[command_name].append(role.id)
            await bot.config.set("command_permissions", current_perms)
            embed = discord.Embed(
                title="✅ Permission Added",
                description=f"```Command: {command_name}\nRole: {role.name}```",
                color=0x00ff00,
                timestamp=discord.utils.utcnow()
            )
            logger.info(f"Permission added by {ctx.author}: {command_name} -> {role.name}")
    
    await ctx.send(embed=embed)
    try:
        await ctx.message.delete()
    except:
        pass


@bot.hybrid_command(name="discordbotframework", aliases=["framework", "botinfo"], help="Display bot framework information")
@commands.cooldown(1, 10, commands.BucketType.user)
@has_command_permission()
async def framework_command(ctx):
    if ctx.interaction:
        if not await check_app_command_permissions(ctx.interaction, "discordbotframework"):
            return
    embed = discord.Embed(
        title="🤖 Discord Bot Framework",
        description="**Advanced Discord Bot Framework with Dynamic Features**",
        color=0x5865f2,
        timestamp=discord.utils.utcnow()
    )
    
    features = [
        "• Dynamic Extension Loading System",
        "• Hot-Reload Capability",
        "• Atomic File Operations & Caching",
        "• Role-Based Command Permissions",
        "• Advanced Help Menu with Categories",
        "• Interactive Dropdown Menus & Pagination",
        "• Database Management (SQLite + WAL)",
        "• Metrics & Statistics Tracking",
        "• Command Usage Analytics",
        "• Automatic Error Handling",
        "• Safe Rotating Log System",
        "• Custom Prefix Per Guild",
        "• Hybrid Commands (Prefix & Slash)",
        "• Auto-Delete Success Messages",
        "• Whitespace-Tolerant Extension Names",
        "• Configuration System (JSON)",
        "• Improved Slash Command Sync",
        "• Bot Owner & Guild Owner Permissions"
    ]
    
    embed.add_field(
        name="✨ Framework Features",
        value="```" + "\n".join(features) + "```",
        inline=False
    )
    
    commands_list = [
        "!help - Interactive help menu",
        "!stats - Bot statistics",
        "!extensions - List loaded extensions",
        "!config - Configure permissions",
        "!setprefix - Set custom prefix"
    ]
    
    owner_commands = [
        "!reload <ext> - Reload extension (Owner)",
        "!load <ext> - Load extension (Owner)",
        "!unload <ext> - Unload extension (Owner)",
        "!sync - Force sync slash commands (Owner)",
        "!atomictest - Test file operations (Owner)"
    ]
    
    embed.add_field(
        name="📝 User Commands",
        value="```" + "\n".join(commands_list) + "```",
        inline=False
    )
    
    embed.add_field(
        name="🔒 Owner Commands",
        value="```" + "\n".join(owner_commands) + "```",
        inline=False
    )
    
    stats = bot.metrics.get_stats()
    uptime_str = str(timedelta(seconds=int(stats['uptime'])))
    
    embed.add_field(
        name="📊 Current Stats",
        value=f"```Uptime: {uptime_str}\nGuilds: {len(bot.guilds)}\nExtensions: {len(bot.extensions)}\nLatency: {bot.latency*1000:.2f}ms```",
        inline=False
    )
    
    embed.add_field(
        name="🔗 Repository",
        value="[GitHub Repository](https://github.com/TheHolyOneZ/discord-bot-framework)",
        inline=False
    )
    
    embed.set_footer(text=f"Created by TheHolyOneZ | Requested by {ctx.author}")
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await ctx.send(embed=embed)
    try:
        await ctx.message.delete()
    except:
        pass


class HelpView(discord.ui.View):
    def __init__(self, categories, author, prefix):
        super().__init__(timeout=180)
        self.categories = categories
        self.author = author
        self.prefix = prefix
        self.add_item(CategorySelect(categories, prefix))
        self.add_item(CreditsButton())
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message(
                "❌ Only the requester can use this menu!", 
                ephemeral=True
            )
            return False
        return True


class CategorySelect(discord.ui.Select):
    def __init__(self, categories, prefix):
        options = [
            discord.SelectOption(
                label=cog_name,
                description=f"{len(cmds)} commands available",
                emoji="📁"
            )
            for cog_name, cmds in categories.items()
        ]
        super().__init__(
            placeholder="📂 Select a category...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.categories = categories
        self.prefix = prefix
    
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        cmds = self.categories[selected]
        
        page = 0
        per_page = 5
        total_pages = (len(cmds) - 1) // per_page + 1
        
        embed = self.create_page_embed(selected, cmds, page, per_page, total_pages)
        
        view = CategoryView(selected, cmds, page, per_page, total_pages, interaction.user, self.prefix)
        await interaction.response.edit_message(embed=embed, view=view)
        logger.info(f"{interaction.user} selected category '{selected}'")
    
    def create_page_embed(self, category, cmds, page, per_page, total_pages):
        start = page * per_page
        end = start + per_page
        
        embed = discord.Embed(
            title=f"📂 {category}",
            description=f"```Total Commands: {len(cmds)} | Page {page + 1}/{total_pages}```\n",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        for cmd in cmds[start:end]:
            cmd_help = cmd.help or "No description available"
            embed.add_field(
                name=f"▸ {self.prefix}{cmd.name}",
                value=f"```{cmd_help}```",
                inline=False
            )
        
        embed.set_footer(text=f"Category: {category}")
        
        return embed


class CategoryView(discord.ui.View):
    def __init__(self, category, cmds, page, per_page, total_pages, author, prefix):
        super().__init__(timeout=180)
        self.category = category
        self.cmds = cmds
        self.page = page
        self.per_page = per_page
        self.total_pages = total_pages
        self.author = author
        self.prefix = prefix
        
        if total_pages > 1:
            self.add_item(PrevButton(prefix))
            self.add_item(NextButton(prefix))
        
        self.add_item(BackButton(prefix))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message(
                "❌ Only the requester can use this menu!", 
                ephemeral=True
            )
            return False
        return True


class PrevButton(discord.ui.Button):
    def __init__(self, prefix):
        super().__init__(style=discord.ButtonStyle.gray, label="◀ Previous", row=1)
        self.prefix = prefix
    
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if view.page > 0:
            view.page -= 1
        
        embed = self.create_page_embed(view.category, view.cmds, view.page, view.per_page, view.total_pages)
        await interaction.response.edit_message(embed=embed, view=view)
    
    def create_page_embed(self, category, cmds, page, per_page, total_pages):
        start = page * per_page
        end = start + per_page
        
        embed = discord.Embed(
            title=f"📂 {category}",
            description=f"```Total Commands: {len(cmds)} | Page {page + 1}/{total_pages}```\n",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        for cmd in cmds[start:end]:
            cmd_help = cmd.help or "No description available"
            embed.add_field(
                name=f"▸ {self.prefix}{cmd.name}",
                value=f"```{cmd_help}```",
                inline=False
            )
        
        embed.set_footer(text=f"Category: {category}")
        
        return embed


class NextButton(discord.ui.Button):
    def __init__(self, prefix):
        super().__init__(style=discord.ButtonStyle.gray, label="Next ▶", row=1)
        self.prefix = prefix
    
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if view.page < view.total_pages - 1:
            view.page += 1
        
        embed = self.create_page_embed(view.category, view.cmds, view.page, view.per_page, view.total_pages)
        await interaction.response.edit_message(embed=embed, view=view)
    
    def create_page_embed(self, category, cmds, page, per_page, total_pages):
        start = page * per_page
        end = start + per_page
        
        embed = discord.Embed(
            title=f"📂 {category}",
            description=f"```Total Commands: {len(cmds)} | Page {page + 1}/{total_pages}```\n",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        for cmd in cmds[start:end]:
            cmd_help = cmd.help or "No description available"
            embed.add_field(
                name=f"▸ {self.prefix}{cmd.name}",
                value=f"```{cmd_help}```",
                inline=False
            )
        
        embed.set_footer(text=f"Category: {category}")
        
        return embed


class BackButton(discord.ui.Button):
    def __init__(self, prefix):
        super().__init__(style=discord.ButtonStyle.blurple, label="🏠 Back to Main", row=1)
        self.prefix = prefix
    
    async def callback(self, interaction: discord.Interaction):
        categories = {}
        
        main_commands = [cmd for cmd in interaction.client.commands if cmd.cog is None and not cmd.hidden]
        if main_commands:
            categories["Main"] = main_commands
        
        for cog_name, cog in interaction.client.cogs.items():
            cmds = [cmd for cmd in cog.get_commands() if not cmd.hidden]
            if cmds:
                categories[cog_name] = cmds
        
        if not categories:
            embed = discord.Embed(
                title="❌ Error",
                description="```No categories available```",
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return
        
        embed = discord.Embed(
            title="📚 Help Menu",
            description="**Select a category from the dropdown menu**\n\n"
                        f"```Available Categories: {len(categories)}\nCurrent Prefix: {self.prefix}```",
            color=0x2b2d31,
            timestamp=discord.utils.utcnow()
        )
        
        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.set_thumbnail(url=interaction.client.user.display_avatar.url)
        
        view = HelpView(categories, interaction.user, self.prefix)
        await interaction.response.edit_message(embed=embed, view=view)


class CreditsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, label="ℹ️ Credits", row=1)
    
    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="✨ Credits & System Info",
            description="**This **MAIN** bot system was crafted with care**",
            color=0xffd700,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="👤 Created By",
            value="```TheHolyOneZ```\n\nRepository\nhttps://github.com/TheHolyOneZ/discord-bot-framework",
            inline=False
        )
        
        embed.add_field(
            name="🔧 System Features",
            value=(
                "```• Dynamic Extension Loading System\n"
                "• Hot-Reload Capability\n"
                "• Atomic File Operations\n"
                "• Role-Based Command Permissions\n"
                "• Advanced Help Menu Structure\n"
                "• Interactive Dropdown Menus\n"
                "• Automatic Category Organization\n"
                "• Extension Info & Dynamic Loading\n"
                "• Pagination Support\n"
                "• Hybrid Commands (Prefix & Slash)\n"
                "• Advanced Logging System\n"
                "• Database Management (SQLite)\n"
                "• Metrics & Statistics Tracking\n"
                "• Command Usage Analytics\n"
                "• Configuration System (JSON)\n"
                "• Custom Prefix Per Guild\n"
                "• Auto-Delete Messages\n"
                "• Whitespace-Tolerant Extensions\n"
                "• Advanced Error Handling\n"
                "• File Caching System\n"
                "• Bot/Guild Owner Permissions```"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📜 License",
            value="```MIT License - Free to modify```",
            inline=False
        )
        
        embed.set_footer(text="Made with 💜 by TheHolyOneZ")
        embed.set_thumbnail(url=interaction.client.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


def signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, initiating shutdown...")
    asyncio.create_task(bot.close())
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


if __name__ == "__main__":
    if not TOKEN:
        logger.critical("DISCORD_TOKEN not found in .env!")
        exit(1)
    
    if not BOT_OWNER_ID:
        logger.critical("BOT_OWNER_ID not found in .env!")
        exit(1)
    
    try:
        bot.run(TOKEN, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Bot failed to start: {e}")
        logger.debug(traceback.format_exc())