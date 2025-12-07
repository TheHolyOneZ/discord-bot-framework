"""
================================================================================
SLASH COMMAND LIMITER - ADVANCED DISCORD BOT PROTECTION
================================================================================

PRIMARY PURPOSE:
    Prevents bot crashes by enforcing Discord's 100 slash command limit.
    Allows loading more cogs than Discord's limit by converting excess commands.

WHAT IT DOES:
    ✓ Monitors slash command count in real-time
    ✓ Blocks slash commands when approaching limit (95/100)
    ✓ Strips slash functionality from hybrid commands (keeps prefix)
    ✓ Never modifies your source code files
    ✓ Comprehensive logging to botlogs/debug_slashlimiter.log

COMMAND CONVERSION (BETA):
    When the limit is reached, this cog attempts to convert app commands to 
    prefix commands. This is an EXPERIMENTAL feature with the following caveats:
    
    ⚠️  CONVERSION SUCCESS RATE: ~30-50%
    ⚠️  Some converted commands WILL throw errors
    ⚠️  Commands expecting Interaction objects cannot be converted properly
    ⚠️  Complex commands with modals/buttons/selects will fail
    ⚠️  Autocomplete features will not work
    
    The conversion is a "best effort" fallback to prevent total cog failure.
    Think of it as: "Some functionality > No functionality"

WHY CONVERSIONS FAIL:
    - Slash commands use discord.Interaction, prefix uses discord.ext.commands.Context
    - These are fundamentally incompatible objects
    - Parameters work differently (decorators vs function args)
    - Some features only exist in slash commands
    
RECOMMENDATION:
    If you hit the limit frequently, redesign your bot to use fewer slash commands
    or switch to primarily prefix commands. This limiter is a safety net, not a 
    permanent solution.

CHECK STATUS:
    Use the /slashlimit command to see current usage and converted commands.
    Check botlogs/debug_slashlimiter.log for detailed conversion attempts.



================================================================================


SLASH COMMAND LIMITER - ADVANCED DISCORD BOT PROTECTION
(Updated / fixed for discord.py 2.6.3)


PS Sorry, I uploaded the wrong files and uploaded a broken version on GitHub. This one should work properly. My bad!

================================================================================
"""

from discord.ext import commands
from discord import app_commands
import discord
import logging
import inspect
import functools
import traceback
from pathlib import Path
from datetime import datetime


DEBUG_MODE = True


logger = logging.getLogger("slash_limiter")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)


def apply_logging_rules():
    """
    If DEBUG_MODE is False, silence noisy discord stream handlers that some libs add.
    This function will no-op when DEBUG_MODE is True.
    """
    global DEBUG_MODE

    if DEBUG_MODE:
        return


    logging.getLogger().handlers.clear()
    logging.disable(logging.CRITICAL)

    discord_logger = logging.getLogger("discord")

    for handler in discord_logger.handlers[:]:
        if isinstance(handler, logging.StreamHandler):
            discord_logger.removeHandler(handler)

    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

    discord_logger.addHandler(NullHandler())


apply_logging_rules()


class SlashLimiter(commands.Cog):
    DISCORD_SLASH_LIMIT = 100
    WARNING_THRESHOLD = 90
    SAFE_LIMIT = 95

    def __init__(self, bot):
        self.bot = bot
        cfg = getattr(bot, "config", {}) or {}
        slcfg = cfg.get("slash_limiter", {}) if isinstance(cfg, dict) else {}


        self.DISCORD_SLASH_LIMIT = int(slcfg.get("max_limit", self.DISCORD_SLASH_LIMIT))
        self.WARNING_THRESHOLD = int(slcfg.get("warning_threshold", self.WARNING_THRESHOLD))
        self.SAFE_LIMIT = int(slcfg.get("safe_limit", self.SAFE_LIMIT))
        self.DEBUG_MODE = bool(slcfg.get("debug_mode", DEBUG_MODE))


        self._original_tree_add = None
        self._original_cog_inject = None
        self._patched = False
        self._converted_commands = {}
        self._blocked_commands = {}
        self._registered_hooks = False
        self._warning_sent = False
        self._injection_depth = 0


        self._setup_debug_logging()


        bot.is_slash_disabled = self.is_slash_disabled
        bot.get_converted_commands = self.get_converted_commands

        self._log_debug("=" * 80)
        self._log_debug(f"SLASH LIMITER INITIALIZATION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._log_debug("=" * 80)
        self._log_debug("Configuration:")
        self._log_debug(f"  - Discord Slash Limit: {self.DISCORD_SLASH_LIMIT}")
        self._log_debug(f"  - Warning Threshold: {self.WARNING_THRESHOLD}")
        self._log_debug(f"  - Safe Limit: {self.SAFE_LIMIT}")
        self._log_debug(f"  - Debug Mode: {self.DEBUG_MODE}")

        logger.info(f"[LIMITER] Initializing (warn={self.WARNING_THRESHOLD}, limit={self.SAFE_LIMIT})")
        self._patch_immediately()
        logger.info("[LIMITER] Ready and active")
        self._log_debug("Initialization complete\n")

    def _setup_debug_logging(self):
        try:
            log_dir = Path("botlogs")
            log_dir.mkdir(exist_ok=True)
            self.debug_log_path = log_dir / "debug_slashlimiter.log"
            self.debug_logger = logging.getLogger("slash_limiter_debug")
            self.debug_logger.setLevel(logging.DEBUG)

            self.debug_logger.handlers.clear()
            handler = logging.FileHandler(self.debug_log_path, mode="a", encoding="utf-8")
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            handler.setFormatter(formatter)
            self.debug_logger.addHandler(handler)
            self.debug_logger.propagate = False
        except Exception as e:

            logger.error(f"[LIMITER] Failed to setup debug logging: {e}")
            self.debug_logger = None

    def _log_debug(self, message: str):
        if getattr(self, "debug_logger", None):
            try:
                self.debug_logger.debug(message)
            except Exception:
                pass

    def _patch_immediately(self):
        if self._patched:
            self._log_debug("PATCH ATTEMPT: Already patched, skipping")
            logger.warning("[LIMITER] Already patched, skipping")
            return

        tree = getattr(self.bot, "tree", None)
        if tree is None:
            self._log_debug("PATCH FAILED: No command tree found")
            logger.error("[LIMITER] No command tree found, cannot patch")
            return

        self._log_debug("\n" + "=" * 80)
        self._log_debug("PATCHING PROCESS STARTED")
        self._log_debug("=" * 80)
        logger.info("[LIMITER] Starting patch process")


        self._original_tree_add = tree.add_command

        self._original_cog_inject = getattr(commands.Cog, "_inject", None)

        limiter_self = self  


        def wrapped_tree_add(command, guild=None, guilds=None, override=False):
            try:

                try:
                    current = len(tree.get_commands())
                except Exception:
                    current = len(tree.get_commands()) if hasattr(tree, "get_commands") else 0
            except Exception as e:
                limiter_self._log_debug(f"ERROR counting commands during tree.add_command: {e}")
                if limiter_self.DEBUG_MODE:
                    logger.debug(f"[LIMITER] Error counting commands: {e}")
                current = 0

            cmd_name = getattr(command, "name", None) or getattr(command, "qualified_name", "<unknown>")


            if current >= limiter_self.SAFE_LIMIT:
                limiter_self._blocked_commands[cmd_name] = {
                    "reason": "Exceeded safe limit",
                    "current_count": current,
                    "timestamp": datetime.now().isoformat()
                }
                limiter_self._log_debug(f"\nBLOCKED SLASH COMMAND:")
                limiter_self._log_debug(f"  Command Name: {cmd_name}")
                limiter_self._log_debug(f"  Current Count: {current}/{limiter_self.SAFE_LIMIT}")
                limiter_self._log_debug(f"  Reason: Safe limit exceeded")
                limiter_self._log_debug(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.warning(f"[LIMITER] BLOCKED slash '{cmd_name}' (at {current}/{limiter_self.SAFE_LIMIT})")
                if current >= limiter_self.WARNING_THRESHOLD and not limiter_self._warning_sent:
                    logger.warning(f"[LIMITER] Slash commands at {current}/{limiter_self.DISCORD_SLASH_LIMIT}")
                    limiter_self._warning_sent = True
                return None


            if current >= limiter_self.WARNING_THRESHOLD and not limiter_self._warning_sent:
                limiter_self._log_debug(f"\nWARNING: Approaching limit at {current}/{limiter_self.DISCORD_SLASH_LIMIT}")
                logger.warning(f"[LIMITER] WARNING: Approaching limit {current}/{limiter_self.DISCORD_SLASH_LIMIT}")
                limiter_self._warning_sent = True

            if limiter_self.DEBUG_MODE:
                limiter_self._log_debug(f"ALLOWING slash command '{cmd_name}' ({current + 1}/{limiter_self.SAFE_LIMIT})")
                logger.debug(f"[LIMITER] Allowing slash '{cmd_name}' ({current + 1}/{limiter_self.SAFE_LIMIT})")

            try:

                return limiter_self._original_tree_add(command, guild=guild, guilds=guilds, override=override)
            except TypeError:

                try:
                    return limiter_self._original_tree_add(command, guild=guild, override=override)
                except Exception as e:
                    limiter_self._log_debug(f"ERROR adding command '{cmd_name}': {e}")
                    logger.error(f"[LIMITER] Error adding command '{cmd_name}': {e}")
                    raise
            except Exception as e:
                limiter_self._log_debug(f"ERROR adding command '{cmd_name}': {e}")
                logger.error(f"[LIMITER] Error adding command '{cmd_name}': {e}")
                raise


        async def wrapped_cog_inject(cog_self, bot, *, override=False, guild=None, guilds=None):
            """
            Injection wrapper compatible with:
            - discord.py 2.6.3
            - frameworks that pass guild/guilds into _inject()
            """
            limiter_self._injection_depth += 1
            depth = limiter_self._injection_depth
            cog_name = getattr(cog_self, "qualified_name", cog_self.__class__.__name__)

            limiter_self._log_debug(f"\n{'  ' * (depth - 1)}COG INJECTION DEPTH {depth}: {cog_name}")
            if limiter_self.DEBUG_MODE:
                logger.debug(f"[LIMITER:{depth}] Injecting cog '{cog_name}'")


            if cog_self.__class__.__name__ == "SlashLimiter":
                try:

                    return await limiter_self._original_cog_inject(
                        cog_self, bot, override=override, guild=guild, guilds=guilds
                    )
                except TypeError:

                    return await limiter_self._original_cog_inject(
                        cog_self, bot, override=override
                    )
                finally:
                    limiter_self._injection_depth -= 1

            try:

                try:
                    current = len(bot.tree.get_commands())
                except Exception:
                    current = 0

                limiter_self._log_debug(
                    f"{'  ' * (depth - 1)}  Current slash count: {current}/{limiter_self.SAFE_LIMIT}"
                )


                if current >= limiter_self.SAFE_LIMIT:
                    limiter_self._log_debug(
                        f"{'  ' * (depth - 1)}  LIMIT REACHED - Converting to prefix commands"
                    )
                    logger.warning(f"[LIMITER:{depth}] Cog '{cog_name}' loading at limit - converting to prefix")


                    for app_cmd in getattr(cog_self, "__cog_app_commands__", []):
                        try:
                            limiter_self._convert_to_prefix_sync(bot, app_cmd, cog_name, depth)
                        except Exception as e:
                            limiter_self._log_debug(
                                f"{'  ' * (depth - 1)}  ERROR converting {getattr(app_cmd,'name','?')}: {e}"
                            )


                    for hybrid in getattr(cog_self, "__cog_commands__", []):
                        if getattr(hybrid, "app_command", None) is not None:
                            hybrid.app_command = None
                            limiter_self._converted_commands[f"{cog_name}:{hybrid.name}"] = {
                                "type": "hybrid_stripped",
                                "original_name": hybrid.name,
                                "cog": cog_name,
                                "timestamp": datetime.now().isoformat(),
                            }


                try:

                    result = await limiter_self._original_cog_inject(
                        cog_self, bot, override=override, guild=guild, guilds=guilds
                    )
                except TypeError:

                    result = await limiter_self._original_cog_inject(
                        cog_self, bot, override=override
                    )

                limiter_self._injection_depth -= 1
                return result

            except Exception as e:
                limiter_self._injection_depth -= 1
                limiter_self._log_debug(f"ERROR in wrapped_cog_inject: {e}\n{traceback.format_exc()}")
                raise



        tree.add_command = wrapped_tree_add
        if self._original_cog_inject:
            commands.Cog._inject = wrapped_cog_inject
        self._patched = True
        self._log_debug("Patching complete: tree.add_command and Cog._inject wrapped")
        self._log_debug("=" * 80 + "\n")
        logger.info("[LIMITER] Successfully patched tree.add_command + Cog._inject")

    def _convert_to_prefix_sync(self, bot, app_cmd, cog_name, depth):
        """
        Convert an app command or group into a prefix Command added to the bot.
        This is a best-effort conversion; many interactive features won't work.
        """

        if isinstance(app_cmd, app_commands.Group):
            self._log_debug(f"{'  ' * depth}  GROUP CONVERSION: {app_cmd.name} ({len(app_cmd.commands)} subcommands)")
            if self.DEBUG_MODE:
                logger.debug(f"[LIMITER] Converting group '{app_cmd.name}' with {len(app_cmd.commands)} subcommands")
            for subcmd in app_cmd.commands:
                self._convert_to_prefix_sync(bot, subcmd, cog_name, depth + 1)
            return

        if not isinstance(app_cmd, app_commands.Command):
            self._log_debug(f"{'  ' * depth}  SKIPPED: Non-command object {type(app_cmd)}")
            if self.DEBUG_MODE:
                logger.debug(f"[LIMITER] Skipping non-command object: {type(app_cmd)}")
            return

        callback = getattr(app_cmd, "callback", None)
        if callback is None:
            self._log_debug(f"{'  ' * depth}  SKIPPED: No callback found")
            if self.DEBUG_MODE:
                logger.warning(f"[LIMITER] App command has no callback, skipping")
            return

        name = getattr(app_cmd, "name", None) or callback.__name__
        desc = getattr(app_cmd, "description", "") or ""
        cmd_name = name.replace(" ", "_").replace("-", "_")
        original_name = cmd_name
        if bot.get_command(cmd_name):
            cmd_name = f"{cmd_name}_alt"
            self._log_debug(f"{'  ' * depth}  NAME COLLISION: Using '{cmd_name}' instead of '{original_name}'")
            if self.DEBUG_MODE:
                logger.debug(f"[LIMITER] Command name collision, using '{cmd_name}' instead of '{original_name}'")

        @functools.wraps(callback)
        async def prefix_wrapper(ctx, *args, **kwargs):
            try:

                sig = inspect.signature(callback)
                params = list(sig.parameters.values())

                if len(params) > 0 and params[0].name in ("interaction", "inter", "ctx"):
                    return await callback(ctx, *args, **kwargs)

                return await callback(ctx)
            except TypeError as e:

                self._log_debug(f"{'  ' * depth}  CONVERSION ERROR: {cmd_name} - TypeError: {e}")
                try:
                    await ctx.send(
                        "⚠️ **Command Conversion Error**\n"
                        f"This command (`{cmd_name}`) was auto-converted from slash to prefix due to Discord's limit.\n"
                        "However, it cannot function properly as a prefix command.\n"
                        f"Error: `{str(e)[:100]}`"
                    )
                except Exception:
                    pass
            except Exception as e:
                self._log_debug(f"{'  ' * depth}  CONVERSION ERROR: {cmd_name} - {type(e).__name__}: {e}")
                if self.DEBUG_MODE:
                    logger.exception(f"[LIMITER] Error in converted command {cmd_name}")
                try:
                    await ctx.send(f"⚠️ Error executing converted command: {e}")
                except Exception:
                    pass

        new_cmd = commands.Command(prefix_wrapper, name=cmd_name, help=desc)
        try:
            bot.add_command(new_cmd)
            conversion_info = {
                "type": "app_to_prefix",
                "original_name": name,
                "converted_name": cmd_name,
                "description": desc,
                "cog": cog_name,
                "had_collision": cmd_name != original_name,
                "timestamp": datetime.now().isoformat()
            }
            self._converted_commands[f"{cog_name}:{cmd_name}"] = conversion_info
            self._log_debug(f"{'  ' * depth}  CONVERTED TO PREFIX:")
            self._log_debug(f"{'  ' * depth}    Original: /{name}")
            self._log_debug(f"{'  ' * depth}    New: {cmd_name} (prefix command)")
            self._log_debug(f"{'  ' * depth}    Cog: {cog_name}")
            if desc:
                self._log_debug(f"{'  ' * depth}    Description: {desc}")
            logger.info(f"[LIMITER] Converted slash '{name}' -> prefix '{cmd_name}'")
        except Exception as e:
            self._log_debug(f"{'  ' * depth}  ERROR adding prefix command '{cmd_name}': {e}")
            if self.DEBUG_MODE:
                logger.error(f"[LIMITER] Failed adding prefix command '{cmd_name}': {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self._log_debug("\n" + "=" * 80)
            self._log_debug(f"BOT READY EVENT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log_debug("=" * 80)
            logger.info("[LIMITER] Bot ready, checking status")
            await self.check_slash_command_limit()


            if hasattr(self.bot, "register_hook") and not self._registered_hooks:
                try:
                    self.bot.register_hook("extension_loaded", self._on_extension_loaded_hook, priority=15)
                    self.bot.register_hook("extension_load_failed", self._on_extension_load_failed_hook, priority=15)
                    self._registered_hooks = True
                    self._log_debug("Registered with event hooks system")
                    logger.info("[LIMITER] Registered with event hooks")
                except Exception as e:
                    self._log_debug(f"No event hooks system available: {e}")
                    logger.debug(f"[LIMITER] No event hooks system available: {e}")

            self._log_summary()
        except Exception as e:
            self._log_debug(f"ERROR during on_ready: {e}\n{traceback.format_exc()}")
            logger.exception("[LIMITER] Error during on_ready")

    def _log_summary(self):
        self._log_debug("\n" + "=" * 80)
        self._log_debug("CONVERSION SUMMARY")
        self._log_debug("=" * 80)
        if self._converted_commands:
            self._log_debug(f"\nTotal Converted Commands: {len(self._converted_commands)}")
            app_to_prefix = [k for k, v in self._converted_commands.items() if v.get("type") == "app_to_prefix"]
            hybrid_stripped = [k for k, v in self._converted_commands.items() if v.get("type") == "hybrid_stripped"]
            if app_to_prefix:
                self._log_debug(f"\nApp Commands -> Prefix ({len(app_to_prefix)}):")
                for key in sorted(app_to_prefix):
                    info = self._converted_commands[key]
                    self._log_debug(f"  - /{info['original_name']} -> {info['converted_name']} [{info['cog']}]")
            if hybrid_stripped:
                self._log_debug(f"\nHybrid Commands Stripped ({len(hybrid_stripped)}):")
                for key in sorted(hybrid_stripped):
                    info = self._converted_commands[key]
                    self._log_debug(f"  - {info['original_name']} (prefix only) [{info['cog']}]")
        else:
            self._log_debug("\nNo commands were converted (all loaded within safe limit)")

        if self._blocked_commands:
            self._log_debug(f"\nTotal Blocked Commands: {len(self._blocked_commands)}")
            self._log_debug("\nBlocked Slash Commands:")
            for cmd_name in sorted(self._blocked_commands.keys()):
                info = self._blocked_commands[cmd_name]
                self._log_debug(f"  - /{cmd_name} (blocked at {info['current_count']}/{self.SAFE_LIMIT})")
        else:
            self._log_debug("\nNo commands were blocked")
        self._log_debug("\n" + "=" * 80 + "\n")

    async def check_slash_command_limit(self):
        try:
            current = len(self.bot.tree.get_commands())
            remaining = max(self.DISCORD_SLASH_LIMIT - current, 0)
            percentage = (current / self.DISCORD_SLASH_LIMIT) * 100 if self.DISCORD_SLASH_LIMIT else 0.0
            status = {"current": current, "limit": self.DISCORD_SLASH_LIMIT, "remaining": remaining, "percentage": percentage, "status": "safe"}

            self._log_debug("SLASH COMMAND LIMIT CHECK:")
            self._log_debug(f"  Current: {current}/{self.DISCORD_SLASH_LIMIT}")
            self._log_debug(f"  Percentage: {percentage:.1f}%")
            self._log_debug(f"  Remaining: {remaining}")

            if current >= self.SAFE_LIMIT:
                status["status"] = "critical"
                self._log_debug("  Status: CRITICAL")
                logger.error(f"[LIMITER] CRITICAL: Slash commands at {current}/{self.DISCORD_SLASH_LIMIT}")
            elif current >= self.WARNING_THRESHOLD:
                status["status"] = "warning"
                self._log_debug("  Status: WARNING")
                if not self._warning_sent:
                    logger.warning(f"[LIMITER] WARNING: Slash commands at {current}/{self.DISCORD_SLASH_LIMIT} ({percentage:.1f}%)")
                    self._warning_sent = True
            else:
                status["status"] = "safe"
                self._log_debug("  Status: SAFE")
                logger.info(f"[LIMITER] Slash commands: {current}/{self.DISCORD_SLASH_LIMIT} ({percentage:.1f}%)")

            self._log_debug(f"  Blocked: {len(self._blocked_commands)}, Converted: {len(self._converted_commands)}\n")
            logger.info(f"[LIMITER] Blocked: {len(self._blocked_commands)}, Converted: {len(self._converted_commands)}")
            return status
        except Exception as e:
            self._log_debug(f"ERROR checking slash command limit: {e}\n{traceback.format_exc()}")
            logger.exception("[LIMITER] Failed to check slash command limit")
            return {"error": "failed"}

    def is_slash_disabled(self, name):
        return name in self._blocked_commands

    def get_converted_commands(self):
        return dict(self._converted_commands)

    async def _on_extension_loaded_hook(self, bot, extension_name, **kwargs):
        try:
            self._log_debug(f"\nEXTENSION LOADED: {extension_name}")
            if self.DEBUG_MODE:
                logger.debug(f"[LIMITER] Extension loaded: {extension_name}")
            status = await self.check_slash_command_limit()
            if status.get("status") == "critical":
                self._log_debug("  WARNING: Loaded at critical limit")
                logger.warning(f"[LIMITER] Extension {extension_name} loaded at critical limit")
        except Exception as e:
            self._log_debug(f"ERROR in extension_loaded hook: {e}")
            logger.exception("[LIMITER] Error in extension_loaded hook")

    async def _on_extension_load_failed_hook(self, bot, extension_name, error=None, **kwargs):
        try:
            if error is None:
                return
            err_str = str(error)
            self._log_debug(f"\nEXTENSION LOAD FAILED: {extension_name}")
            self._log_debug(f"  Error: {err_str}")
            if "CommandLimitReached" in err_str:
                self._log_debug("  Type: CommandLimitReached (limiter should have prevented this)")
                logger.error(f"[LIMITER] Extension {extension_name} failed: CommandLimitReached (limiter should have prevented this!)")
            elif "can't be used in 'await' expression" in err_str:
                self._log_debug("  Type: Malformed setup() - not a limiter issue")
                logger.debug(f"[LIMITER] Extension {extension_name} has malformed setup() - not a limiter issue")
        except Exception as e:
            self._log_debug(f"ERROR in extension_load_failed hook: {e}")
            logger.exception("[LIMITER] Error in extension_load_failed hook")

    @commands.hybrid_command(name="slashlimit", help="Check slash command usage and limits")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def slash_limit_command(self, ctx):
        status = await self.check_slash_command_limit()
        color_map = {"safe": 0x00FF00, "warning": 0xFFFF00, "critical": 0xFF0000}
        color = color_map.get(status.get("status", "safe"), 0x5865F2)
        embed = discord.Embed(
            title="Slash Command Usage",
            description="Discord imposes a hard limit of 100 global slash commands",
            color=color,
            timestamp=discord.utils.utcnow()
        )
        percentage = status.get("percentage", 0)
        progress_bar = self._create_progress_bar(percentage)
        embed.add_field(
            name="Current Usage",
            value=f"```{status.get('current', 0)}/{self.DISCORD_SLASH_LIMIT} commands ({percentage:.1f}%)\n{progress_bar}```",
            inline=False
        )
        embed.add_field(name="Remaining", value=f"```{status.get('remaining', 0)} slots available```", inline=True)
        status_text = {"safe": "Safe - Plenty of room", "warning": "Warning - Getting full", "critical": "Critical - At limit"}
        embed.add_field(name="Status", value=f"```{status_text.get(status.get('status', 'safe'), 'Unknown')}```", inline=True)
        if self._blocked_commands:
            blocked_list = "\n".join([f"{cmd}" for cmd in sorted(self._blocked_commands.keys())[:20]])
            if len(self._blocked_commands) > 20:
                blocked_list += f"\n... (+{len(self._blocked_commands) - 20} more)"
            embed.add_field(name="Blocked Slash Commands", value=f"```{blocked_list}```", inline=False)
        if self._converted_commands:
            conv_list = []
            for key in sorted(list(self._converted_commands.keys())[:15]):
                info = self._converted_commands[key]
                if info.get("type") == "app_to_prefix":
                    conv_list.append(f"/{info['original_name']} -> {info['converted_name']}")
                else:
                    conv_list.append(f"{info['original_name']} (hybrid stripped)")
            conv_str = "\n".join(conv_list)
            if len(self._converted_commands) > 15:
                conv_str += f"\n... (+{len(self._converted_commands) - 15} more)"
            embed.add_field(name="Converted Commands", value=f"```{conv_str}```", inline=False)
        embed.add_field(
            name="How It Works",
            value="```Intercepts cog loading before slash registration\nConverts slash commands to prefix (BETA - may fail)\nStrips slash from hybrids, keeps prefix\nNever modifies cog source code```",
            inline=False
        )
        embed.add_field(
            name="⚠️ Conversion Status",
            value="```Converted commands are EXPERIMENTAL\n~30-50% success rate\nSome will throw errors when used\nCheck debug log for details```",
            inline=False
        )
        embed.add_field(name="Debug Log", value=f"```Check: botlogs/debug_slashlimiter.log```", inline=False)
        embed.set_footer(text="Slash Limiter")
        await ctx.send(embed=embed)

    def _create_progress_bar(self, percentage, length=20):
        try:
            filled = int((percentage / 100) * length)
            empty = max(length - filled, 0)
            return f"[{'█' * filled}{'░' * empty}]"
        except Exception:
            return "[" + "░" * length + "]"

    def cog_unload(self):
        try:
            self._log_debug("\n" + "=" * 80)
            self._log_debug(f"COG UNLOAD - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self._log_debug("=" * 80)
            logger.info("[LIMITER] Unloading cog")


            if hasattr(self.bot, "is_slash_disabled"):
                try:
                    delattr(self.bot, "is_slash_disabled")
                except Exception:
                    pass
            if hasattr(self.bot, "get_converted_commands"):
                try:
                    delattr(self.bot, "get_converted_commands")
                except Exception:
                    pass


            if self._original_tree_add and self._patched:
                try:
                    self.bot.tree.add_command = self._original_tree_add
                    self._log_debug("Restored original tree.add_command")
                    logger.info("[LIMITER] Restored original tree.add_command")
                except Exception as e:
                    self._log_debug(f"Failed restoring tree.add_command: {e}")
                    logger.error(f"[LIMITER] Failed restoring tree.add_command: {e}")


            if self._original_cog_inject and self._patched:
                try:
                    commands.Cog._inject = self._original_cog_inject
                    self._log_debug("Restored original Cog._inject")
                    logger.info("[LIMITER] Restored original Cog._inject")
                except Exception as e:
                    self._log_debug(f"Failed restoring Cog._inject: {e}")
                    logger.error(f"[LIMITER] Failed restoring Cog._inject: {e}")

            self._log_debug("Cog unload complete")
            self._log_debug("=" * 80 + "\n")
        except Exception as e:
            self._log_debug(f"ERROR during cog_unload: {e}\n{traceback.format_exc()}")
            logger.exception("[LIMITER] Error during cog_unload")

        logger.info("[LIMITER] Cog unloaded")


print("[LIMITER] Active — logs written to botlogs/debug_slashlimiter.log")


async def setup(bot):
    """
    Standard async setup entrypoint for discord.py cogs.
    """
    await bot.add_cog(SlashLimiter(bot))
    logger.info("[LIMITER] Loaded successfully")
