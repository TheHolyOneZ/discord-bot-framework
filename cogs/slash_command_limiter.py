"""
Slash Command Limiter Cog
Prevents bot crashes from Discord's 100 global slash command limit
Automatically converts hybrid commands to prefix-only if limit is reached
"""

from discord.ext import commands
import discord
from discord import app_commands
from typing import List, Dict, Set
import logging

logger = logging.getLogger('discord')


class SlashCommandLimiter(commands.Cog):
    
    

    DISCORD_SLASH_LIMIT = 100

    WARNING_THRESHOLD = 90

    SAFE_LIMIT = 95
    
    def __init__(self, bot):
        self.bot = bot
        self.slash_disabled_extensions: Set[str] = set()
        self.prefix_only_commands: Set[str] = set()
        self.warning_sent = False
        

        bot.is_slash_disabled = self.is_slash_disabled
        bot.get_prefix_only_commands = self.get_prefix_only_commands
        
        logger.info("Slash Command Limiter: System initialized")
    
    @commands.Cog.listener()
    async def on_ready(self):
        
        await self.check_slash_command_limit()
        

        if hasattr(self.bot, 'register_hook'):
            self.bot.register_hook("extension_loaded", self.on_extension_loaded_hook, priority=15)
            logger.info("Slash Command Limiter: Registered with event hooks")
    
    async def check_slash_command_limit(self) -> Dict[str, any]:
        """
        Check current slash command count and warn if approaching limit
        
        Returns:
            Dict with status information
        """
        try:

            slash_commands = self.bot.tree.get_commands()
            current_count = len(slash_commands)
            
            status = {
                "current": current_count,
                "limit": self.DISCORD_SLASH_LIMIT,
                "remaining": self.DISCORD_SLASH_LIMIT - current_count,
                "percentage": (current_count / self.DISCORD_SLASH_LIMIT) * 100,
                "status": "safe"
            }
            

            if current_count >= self.SAFE_LIMIT:
                status["status"] = "critical"
                logger.error(f"⚠️ CRITICAL: Slash commands at {current_count}/{self.DISCORD_SLASH_LIMIT}! Very close to limit!")
            elif current_count >= self.WARNING_THRESHOLD:
                status["status"] = "warning"
                if not self.warning_sent:
                    logger.warning(f"⚠️ WARNING: Slash commands at {current_count}/{self.DISCORD_SLASH_LIMIT} ({status['percentage']:.1f}%)")
                    self.warning_sent = True
            else:
                status["status"] = "safe"
                logger.info(f"✅ Slash commands: {current_count}/{self.DISCORD_SLASH_LIMIT} ({status['percentage']:.1f}%)")
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to check slash command limit: {e}")
            return {"error": str(e)}
    
    async def disable_slash_for_extension(self, extension_name: str) -> bool:
        """
        Disable slash commands for an extension and fall back to prefix-only
        
        Args:
            extension_name: Full extension name (e.g., 'extensions.myext')
        
        Returns:
            bool: True if successfully disabled
        """
        try:
            simple_name = extension_name.replace("extensions.", "").replace("cogs.", "")
            

            self.slash_disabled_extensions.add(simple_name)
            

            for cmd in self.bot.commands:
                if hasattr(cmd, 'cog') and cmd.cog:
                    cog_module = cmd.cog.__module__
                    if cog_module.startswith(extension_name):

                        self.prefix_only_commands.add(cmd.name)
                        logger.info(f"Converted to prefix-only: {cmd.name} (from {simple_name})")
            
            logger.warning(f"Extension '{simple_name}' running in PREFIX-ONLY mode due to slash command limit")
            return True
            
        except Exception as e:
            logger.error(f"Failed to disable slash for {extension_name}: {e}")
            return False
    
    def is_slash_disabled(self, extension_name: str) -> bool:
        """
        Check if an extension has slash commands disabled
        
        Args:
            extension_name: Extension name (simple or full)
        
        Returns:
            bool: True if slash is disabled for this extension
        """
        simple_name = extension_name.replace("extensions.", "").replace("cogs.", "")
        return simple_name in self.slash_disabled_extensions
    
    def get_prefix_only_commands(self) -> Set[str]:
        
        return self.prefix_only_commands.copy()
    
    async def on_extension_loaded_hook(self, bot, extension_name: str, **kwargs):
        
        

        if extension_name.startswith("cogs."):
            return
        

        status = await self.check_slash_command_limit()
        

        if status.get("status") == "critical":
            logger.warning(f"Slash command limit critical! Disabling slash for {extension_name}")
            await self.disable_slash_for_extension(extension_name)
    
    @commands.hybrid_command(name="slashlimit", help="Check slash command usage and limits")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def slash_limit_command(self, ctx):
        
        
        status = await self.check_slash_command_limit()
        

        color_map = {
            "safe": 0x00ff00,      
            "warning": 0xffff00,   
            "critical": 0xff0000   
        }
        color = color_map.get(status.get("status", "safe"), 0x5865f2)
        
        embed = discord.Embed(
            title="📊 Slash Command Usage",
            description="**Discord imposes a hard limit of 100 global slash commands**",
            color=color,
            timestamp=discord.utils.utcnow()
        )
        

        percentage = status.get("percentage", 0)
        progress_bar = self._create_progress_bar(percentage)
        
        embed.add_field(
            name="📈 Current Usage",
            value=f"```{status.get('current', 0)}/{self.DISCORD_SLASH_LIMIT} commands ({percentage:.1f}%)\n{progress_bar}```",
            inline=False
        )
        
        embed.add_field(
            name="🔢 Remaining",
            value=f"```{status.get('remaining', 0)} slots available```",
            inline=True
        )
        

        status_text = {
            "safe": "✅ Safe - Plenty of room",
            "warning": "⚠️ Warning - Getting full",
            "critical": "🚨 Critical - At limit!"
        }
        embed.add_field(
            name="🚦 Status",
            value=f"```{status_text.get(status.get('status', 'safe'), 'Unknown')}```",
            inline=True
        )
        

        if self.slash_disabled_extensions:
            disabled_list = "\n".join([f"• {ext}" for ext in sorted(self.slash_disabled_extensions)])
            embed.add_field(
                name="⚙️ Prefix-Only Extensions",
                value=f"```{disabled_list}```",
                inline=False
            )
        

        if self.prefix_only_commands:
            cmds_list = ", ".join(sorted(list(self.prefix_only_commands)[:10]))
            if len(self.prefix_only_commands) > 10:
                cmds_list += f"... (+{len(self.prefix_only_commands) - 10} more)"
            embed.add_field(
                name="📝 Prefix-Only Commands",
                value=f"```{cmds_list}```",
                inline=False
            )
        

        embed.add_field(
            name="ℹ️ Information",
            value=(
                "```When limit is reached:\n"
                "• New extensions run prefix-only\n"
                "• Existing slash commands still work\n"
                "• Help menu shows prefix/slash status```"
            ),
            inline=False
        )
        
        embed.set_footer(text="Framework Protection System")
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    def _create_progress_bar(self, percentage: float, length: int = 20) -> str:
        
        filled = int((percentage / 100) * length)
        empty = length - filled
        
        if percentage >= 95:
            bar_char = "🔴"
        elif percentage >= 90:
            bar_char = "🟡"
        else:
            bar_char = "🟢"
        
        return f"[{'█' * filled}{'░' * empty}] {bar_char}"
    
    def cog_unload(self):
        
        if hasattr(self.bot, 'is_slash_disabled'):
            delattr(self.bot, 'is_slash_disabled')
        if hasattr(self.bot, 'get_prefix_only_commands'):
            delattr(self.bot, 'get_prefix_only_commands')
        
        logger.info("Slash Command Limiter: Cog unloaded")


async def setup(bot):
    
    await bot.add_cog(SlashCommandLimiter(bot))
    logger.info("Slash Command Limiter cog loaded successfully")