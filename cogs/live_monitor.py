"""Zoryx Discord Bot Framework - Live Monitor Dashboard

Credits tab and visual design (c) 2025 TheHolyOneZ (GitHub: @TheHolyOneZ).
This dedicated Credits section (including layout, wording, and crown artwork)
IS NOT covered by the MIT license of the rest of the framework and MUST remain
clearly visible at all times in any use or modification of this dashboard.



Tutorial on how you can use this cog can be found on YouTube! I will post a video later in the next 1-3 days on how to set it up properly.
Btw, this cog got created over two weeks of work, so there may be comments in the code like error fixes, notes, etc. If you decide to play with this cog, know the license above + read the license on the git or the LICENSE file in the main directory! You can ignore the comments; they won't harm but may make the code even longer.
"""

from discord.ext import commands, tasks
import discord
from discord import app_commands
import aiohttp
import asyncio
import secrets
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
import psutil
import time
import inspect
import shutil
import platform
logger = logging.getLogger('discord')


class LiveMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_file = Path("./data/live_monitor_config.json")
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        
        self.local_assets_dir = Path("./assets")
        self.local_assets_dir.mkdir(parents=True, exist_ok=True)
        
        self.config = self._load_config()
        self.is_enabled = False
        self.last_send_success = None
        self.send_failures = 0
        
        self._process = None
        self._start_time = datetime.now()
        self._command_usage = {}
        self._event_log = []
        self._max_event_log = 1000
        self._hook_execution_log = []
        self._max_hook_execution_log = 1000
        self._fileops_response = None


        self._fileops_lock = asyncio.Lock()

        logger.info("Live Monitor: Advanced system initialized")
    
    @commands.Cog.listener()
    async def on_command(self, ctx):
        cmd_name = ctx.command.qualified_name if ctx.command else "unknown"
        if cmd_name not in self._command_usage:
            self._command_usage[cmd_name] = {
                "count": 0,
                "last_used": None,
                "errors": 0,
                "avg_time": 0,
                "total_time": 0
            }
        
        self._command_usage[cmd_name]["count"] += 1
        self._command_usage[cmd_name]["last_used"] = datetime.now().isoformat()
        
        self._log_event("command_executed", {
            "command": cmd_name,
            "user": str(ctx.author),
            "guild": ctx.guild.name if ctx.guild else "DM",
            "channel": ctx.channel.name if hasattr(ctx.channel, 'name') else "DM"
        })
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        cmd_name = ctx.command.qualified_name if ctx.command else "unknown"
        if cmd_name in self._command_usage:
            self._command_usage[cmd_name]["errors"] += 1
        
        self._log_event("command_error", {
            "command": cmd_name,
            "error": str(error),
            "user": str(ctx.author),
            "guild": ctx.guild.name if ctx.guild else "DM"
        })
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        self._log_event("guild_join", {
            "guild": guild.name,
            "guild_id": guild.id,
            "member_count": guild.member_count
        })
    
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        self._log_event("guild_remove", {
            "guild": guild.name,
            "guild_id": guild.id
        })
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        
        if len(self._event_log) == 0 or self._event_log[-1].get("type") != "message_activity":
            self._log_event("message_activity", {
                "count": 1,
                "last_author": str(message.author),
                "last_guild": message.guild.name if message.guild else "DM"
            })
        else:
            last_event = self._event_log[-1]
            last_event["details"]["count"] = last_event["details"].get("count", 0) + 1
            last_event["details"]["last_author"] = str(message.author)
            last_event["details"]["last_guild"] = message.guild.name if message.guild else "DM"
            last_event["timestamp"] = datetime.now().isoformat()
    
    def _load_config(self) -> Dict[str, Any]:
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                pass

        return {
            "enabled": False,
            "secret_token": None,
            "website_url": None,
            "update_interval": 5,

            "setup_token": None,
        }

    def _get_default_prefix(self) -> str:
        """Best-effort fetch of the global/default prefix from config.json.
        Falls back to '!' if anything goes wrong.
        """
        try:
            config_path = Path("./config.json")
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                prefix = cfg.get("prefix")
                if isinstance(prefix, str) and prefix:
                    return prefix
        except Exception as e:
            logger.error(f"Live Monitor: Failed to read default prefix from config.json: {e}")
        return "!"
    
    def _save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logger.error(f"Live Monitor: Failed to save config: {e}")
    
    def _log_event(self, event_type: str, details: Dict[str, Any]):
        self._event_log.append({
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "details": details
        })
        if len(self._event_log) > self._max_event_log:
            self._event_log = self._event_log[-self._max_event_log:]
    
    def _log_hook_execution(self, hook_id: str, success: bool, execution_time: float, error: str = None):
        self._hook_execution_log.append({
            "timestamp": datetime.now().isoformat(),
            "hook_id": hook_id,
            "success": success,
            "execution_time_ms": round(execution_time, 2),
            "error": error
        })
        if len(self._hook_execution_log) > self._max_hook_execution_log:
            self._hook_execution_log = self._hook_execution_log[-self._max_hook_execution_log:]
    
    async def _get_db_command_stats(self) -> List[tuple]:
        if hasattr(self.bot, 'db') and self.bot.db:
            try:
                return await self.bot.db.get_command_stats()
            except Exception as e:
                logger.error(f"Failed to get DB command stats: {e}")
        return []
    
    def _get_command_type(self, cmd) -> str:
        from discord.ext.commands import HybridCommand
        
        if isinstance(cmd, HybridCommand):
            slash_limiter_cog = self.bot.get_cog("SlashLimiter")
            if slash_limiter_cog and cmd.name in slash_limiter_cog._converted_commands:
                return "prefix_only_converted"
            return "hybrid"
        
        if hasattr(cmd, 'app_command') and cmd.app_command is not None:
            return "hybrid"
        
        return "prefix_only"
    
    async def _get_all_commands(self) -> List[Dict[str, Any]]:
        commands_list = []
        db_stats = await self._get_db_command_stats()
        db_stats_dict = {cmd: count for cmd, count in db_stats}
        
        for cmd in self.bot.commands:
            cmd_type = self._get_command_type(cmd)
            
            usage_count = 0
            if hasattr(self.bot, 'metrics') and hasattr(self.bot.metrics, 'command_count'):
                usage_count = self.bot.metrics.command_count.get(cmd.qualified_name, 0)
            
            db_count = db_stats_dict.get(cmd.qualified_name, 0)
            usage_count = max(usage_count, db_count)
            
            usage = self._command_usage.get(cmd.qualified_name, {
                "count": usage_count,
                "last_used": None,
                "errors": 0,
                "avg_time": 0
            })
            
            commands_list.append({
                "name": cmd.qualified_name,
                "type": cmd_type,
                "cog": cmd.cog.qualified_name if cmd.cog else None,
                "enabled": cmd.enabled,
                "hidden": cmd.hidden,
                "description": cmd.short_doc or cmd.help or "No description",
                "usage_count": max(usage["count"], usage_count),
                "last_used": usage["last_used"],
                "error_count": usage["errors"],
                "aliases": list(cmd.aliases) if hasattr(cmd, 'aliases') else [],
                "params": [p for p in cmd.clean_params.keys()] if hasattr(cmd, 'clean_params') else []
            })
        
        if hasattr(self.bot, 'tree'):
            for cmd in self.bot.tree.walk_commands():
                usage = self._command_usage.get(cmd.qualified_name, {
                    "count": 0,
                    "last_used": None,
                    "errors": 0,
                    "avg_time": 0
                })
                
                commands_list.append({
                    "name": cmd.qualified_name,
                    "type": "slash",
                    "cog": None,
                    "enabled": True,
                    "hidden": False,
                    "description": cmd.description or "No description",
                    "usage_count": usage["count"],
                    "last_used": usage["last_used"],
                    "error_count": usage["errors"],
                    "aliases": [],
                    "params": []
                })
        
        return commands_list
    
    def _get_file_system_info(self) -> Dict[str, Any]:
        data_dir = Path("./data")
        cogs_dir = Path("./cogs")
        extensions_dir = Path("./extensions")
        botlogs_dir = Path("./botlogs")

        def get_dir_info(path: Path) -> Dict[str, Any]:
            if not path.exists():
                return {"exists": False, "file_count": 0, "total_size": 0}

            try:
                files = list(path.rglob("*"))
                file_count = sum(1 for item in files if item.is_file())
                total_size = sum(item.stat().st_size for item in files if item.is_file())
            except Exception as e:
                logger.error(f"Error scanning {path}: {e}")
                file_count = 0
                total_size = 0

            return {
                "exists": True,
                "file_count": file_count,
                "total_size": total_size
            }

        return {
            "data": get_dir_info(data_dir),
            "cogs": get_dir_info(cogs_dir),
            "extensions": get_dir_info(extensions_dir),
            "botlogs": get_dir_info(botlogs_dir)
        }

    def _get_dashboard_assets(self) -> List[Path]:
        """Return a list of local asset files to ship with the Live Monitor dashboard.

        These are optional; if they don't exist the dashboard still works, just
        without branding. Expected filenames in ./assets/ are:
          - zoryx-framework.png
          - zoryx-framework.ico
          - banner.png
        """
        assets: List[Path] = []
        try:
            if not self.local_assets_dir.exists():
                return assets
            for name in ("zoryx-framework.png", "zoryx-framework.ico", "banner.png"):
                p = self.local_assets_dir / name
                if p.exists() and p.is_file():
                    assets.append(p)
        except Exception as e:
            logger.error(f"Live Monitor: Failed to enumerate dashboard assets: {e}")
        return assets

    def _copy_dashboard_assets(self, output_dir: Path) -> None:
        """Copy local dashboard assets into the generated website folder.

        This prepares an /assets directory next to index.html so users can
        simply upload everything as-is to their web hosting.
        """
        try:
            files = self._get_dashboard_assets()
            if not files:
                return

            target_dir = output_dir / "assets"
            target_dir.mkdir(parents=True, exist_ok=True)

            for src in files:
                dest = target_dir / src.name
                try:
                    shutil.copy2(src, dest)
                except Exception as e:
                    logger.error(f"Live Monitor: Failed to copy asset {src} -> {dest}: {e}")
        except Exception as e:
            logger.error(f"Live Monitor: Failed to prepare dashboard assets: {e}")

    async def _sync_assets_to_server_once(self) -> None:
        """Best-effort sync of branding assets to the remote dashboard server.

        This sends a one-off JSON package with base64-encoded files to
        receive.php?package=assets, which will write them into /assets on the
        web host so the dashboard can use them immediately.
        """
        if not self.config.get("website_url") or not self.config.get("secret_token"):
            return

        files = self._get_dashboard_assets()
        if not files:
            return

        base_url = str(self.config["website_url"]).rstrip("/")
        token = self.config["secret_token"]
        url = f"{base_url}/receive.php?token={token}&package=assets"

        payload = []
        for src in files:
            try:
                data = src.read_bytes()
            except Exception as e:
                logger.error(f"Live Monitor: Failed to read asset {src}: {e}")
                continue
            import base64
            payload.append({
                "filename": src.name,
                "content": base64.b64encode(data).decode("ascii"),
            })

        if not payload:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Live Monitor: Asset sync failed with HTTP {resp.status}")
                    else:
                        logger.info("Live Monitor: Dashboard assets synced to remote server")
        except Exception as e:
            logger.error(f"Live Monitor: Error syncing dashboard assets to server: {e}")
    
    @commands.Cog.listener()
    async def on_command(self, ctx):
        cmd_name = ctx.command.qualified_name if ctx.command else "unknown"
        if cmd_name not in self._command_usage:
            self._command_usage[cmd_name] = {
                "count": 0,
                "last_used": None,
                "errors": 0,
                "avg_time": 0,
                "total_time": 0
            }
        self._command_usage[cmd_name]["count"] += 1
        self._command_usage[cmd_name]["last_used"] = datetime.now().isoformat()
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        cmd_name = ctx.command.qualified_name if ctx.command else "unknown"
        if cmd_name in self._command_usage:
            self._command_usage[cmd_name]["errors"] += 1
        
        self._log_event("command_error", {
            "command": cmd_name,
            "error": str(error)[:200],
            "user": str(ctx.author)
        })
    
    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        cmd_name = command.qualified_name if hasattr(command, 'qualified_name') else str(command)
        if cmd_name not in self._command_usage:
            self._command_usage[cmd_name] = {
                "count": 0,
                "last_used": None,
                "errors": 0,
                "avg_time": 0,
                "total_time": 0
            }
        self._command_usage[cmd_name]["count"] += 1
        self._command_usage[cmd_name]["last_used"] = datetime.now().isoformat()
    
    async def cog_load(self):
        if self.config.get("enabled") and self.config.get("website_url"):
            self.is_enabled = True
            self.send_status_loop.start()
            logger.info("Live Monitor: Auto-started from saved config")
    
    def cog_unload(self):
        if self.send_status_loop.is_running():
            self.send_status_loop.cancel()
        

        plugin_registry_path = Path("./data/plugin_registry.json")
        if plugin_registry_path.exists():
            try:
                plugin_registry_path.unlink()
                logger.info("Live Monitor: Deleted plugin_registry.json for clean restart")
            except Exception as e:
                logger.warning(f"Live Monitor: Could not delete plugin_registry.json: {e}")
        
        logger.info("Live Monitor: Cog unloaded")
    
    async def _get_process(self):
        if self._process is None:
            loop = asyncio.get_event_loop()
            self._process = await loop.run_in_executor(None, psutil.Process)
        return self._process
    
    async def _collect_monitor_data(self) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        process = await self._get_process()
        

        guild_summaries = []
        try:
            for g in self.bot.guilds:
                text_channels = []
                for ch in getattr(g, 'text_channels', []):
                    try:
                        is_nsfw = False
                        if hasattr(ch, 'is_nsfw') and callable(ch.is_nsfw):
                            is_nsfw = ch.is_nsfw()
                        else:
                            is_nsfw = getattr(ch, 'nsfw', False)
                        text_channels.append({
                            "id": str(ch.id),
                            "name": ch.name,
                            "nsfw": bool(is_nsfw),
                        })
                    except Exception:
                        continue
                guild_summaries.append({
                    "id": str(g.id),
                    "name": g.name,
                    "member_count": getattr(g, 'member_count', 0) or 0,
                    "owner_id": str(getattr(g, 'owner_id', '')),
                    "owner": str(getattr(getattr(g, 'owner', None), 'name', '')),
                    "joined_at": getattr(getattr(g, 'me', None), 'joined_at', None).isoformat() if getattr(getattr(g, 'me', None), 'joined_at', None) else None,
                    "text_channels": text_channels,
                })
        except Exception as e:
            logger.error(f"Live Monitor: Failed to build guild summaries: {e}")
        
        chat_history = getattr(self, "_last_chat_history", None)


        
        def _get_system_info():
            memory_info = process.memory_info()
            cpu_times = process.cpu_times()
            
            cpu_value = process.cpu_percent(interval=None)
            if cpu_value == 0:
                time.sleep(0.1)
                cpu_value = process.cpu_percent(interval=None)
            
            return {
                "cpu_percent": round(cpu_value, 1),
                "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
                "memory_percent": process.memory_percent(),
                "threads": process.num_threads(),
                "open_files": len(process.open_files()),
                "connections": len(process.connections()),
                "cpu_user_time": cpu_times.user,
                "cpu_system_time": cpu_times.system,
                "platform": platform.system()
            }
        
        try:
            system_info = await loop.run_in_executor(None, _get_system_info)
        except:
            system_info = {"cpu_percent": 0, "memory_mb": 0, "threads": 0, "open_files": 0, "connections": 0}
        
        uptime = (datetime.now() - self._start_time).total_seconds()
        
        user_extensions_count = len([e for e in self.bot.extensions.keys() if e.startswith("extensions.")])
        framework_cogs_count = len([e for e in self.bot.extensions.keys() if e.startswith("cogs.")])
        
        bot_info = {
            "user": str(self.bot.user) if self.bot.user else "Unknown",
            "id": str(self.bot.user.id) if self.bot.user else "0",
            "guilds": len(self.bot.guilds),
            "users": sum(g.member_count for g in self.bot.guilds if g.member_count),
            "latency": round(self.bot.latency * 1000, 2),
            "uptime_seconds": int(uptime),
            "uptime_formatted": str(timedelta(seconds=int(uptime))),
            "cogs_loaded": len(self.bot.cogs),
            "extensions_loaded": len(self.bot.extensions),
            "user_extensions": user_extensions_count,
            "framework_cogs": framework_cogs_count,
            "guilds_detail": guild_summaries,
        }
        
        core_data = {
            "timestamp": datetime.now().isoformat(),
            "bot": bot_info,
            "system": system_info,
            "health": {},
        }
        if chat_history is not None:
            core_data["chat_history"] = chat_history
        
        event_hooks_data = {}
        if hasattr(self.bot, 'list_hooks'):
            try:
                event_hooks_cog = self.bot.get_cog("EventHooks")
                if event_hooks_cog:
                    hooks_list = []
                    
                    for event_name, callbacks in event_hooks_cog.hooks.items():
                        for hook_info in callbacks:
                            hook_id = hook_info["hook_id"]
                            
                            exec_history = [h for h in self._hook_execution_log if h["hook_id"] == hook_id][-5:]
                            
                            hooks_list.append({
                                "hook_id": hook_id,
                                "event": event_name,
                                "callback": hook_info["callback"].__name__,
                                "priority": hook_info["priority"],
                                "execution_count": hook_info["execution_count"],
                                "failure_count": hook_info["failure_count"],
                                "avg_time_ms": round(hook_info["total_execution_time"] / hook_info["execution_count"], 2) if hook_info["execution_count"] > 0 else 0,
                                "last_execution": hook_info.get("last_execution", "Never"),
                                "disabled": hook_id in event_hooks_cog.disabled_hooks,
                                "circuit_open": event_hooks_cog.circuit_breaker.is_open(hook_id),
                                "execution_history": exec_history
                            })
                    
                    event_hooks_data = {
                        "total": len(hooks_list),
                        "disabled": len(event_hooks_cog.disabled_hooks),
                        "circuit_open": len([h for h in event_hooks_cog.circuit_breaker.disabled_until.keys()]),
                        "queue_size": event_hooks_cog._hook_queue.qsize(),
                        "metrics": event_hooks_cog.metrics,
                        "hooks": hooks_list
                    }
            except Exception as e:
                logger.error(f"Live Monitor: Failed to collect event hooks data: {e}")
        
        slash_limiter_data = {}
        slash_limiter_cog = self.bot.get_cog("SlashLimiter")
        if slash_limiter_cog:
            try:
                status = await slash_limiter_cog.check_slash_command_limit()
                slash_limiter_data = {
                    "current": status.get("current", 0),
                    "limit": slash_limiter_cog.DISCORD_SLASH_LIMIT,
                    "remaining": status.get("remaining", 0),
                    "percentage": status.get("percentage", 0),
                    "status": status.get("status", "unknown"),
                    "blocked": len(slash_limiter_cog._blocked_commands),
                    "converted": len(slash_limiter_cog._converted_commands),
                    "blocked_list": [
                        {
                            "name": name,
                            "timestamp": info.get("timestamp", "Unknown")
                        }
                        for name, info in list(slash_limiter_cog._blocked_commands.items())[:10]
                    ],
                    "converted_list": [
                        {
                            "original": info["original_name"],
                            "converted": info["converted_name"],
                            "cog": info.get("cog", "Unknown")
                        }
                        for info in list(slash_limiter_cog._converted_commands.values())[:10]
                    ]
                }
            except Exception as e:
                logger.error(f"Live Monitor: Failed to collect slash limiter data: {e}")
        
        atomic_fs_data = {}
        if hasattr(self.bot.config, 'file_handler'):
            try:
                stats = self.bot.config.file_handler.get_cache_stats()
                atomic_fs_data = {
                    "cache_size": stats["cache_size"],
                    "max_cache_size": stats["max_cache_size"],
                    "hit_rate": stats["hit_rate"],
                    "active_locks": stats["active_locks"],
                    "total_reads": stats["total_reads"],
                    "total_writes": stats["total_writes"],
                    "write_failures": stats["write_failures"],
                    "read_failures": stats["read_failures"],
                }

                if hasattr(self.bot.config.file_handler, "get_lock_details"):
                    lock_info = self.bot.config.file_handler.get_lock_details()
                    atomic_fs_data["lock_summary"] = {
                        "total": lock_info.get("total_locks", 0),
                        "active": lock_info.get("active_locks", 0),
                    }
                    atomic_fs_data["locks"] = lock_info.get("locks", [])
            except Exception as e:
                logger.error(f"Live Monitor: Failed to collect atomic FS data: {e}")


        core_settings = {}
        framework_info = {}
        try:
            if hasattr(self.bot, "config") and self.bot.config is not None:
                core_settings = {
                    "auto_reload": bool(self.bot.config.get("auto_reload", False)),
                    "extensions_auto_load": bool(self.bot.config.get("extensions.auto_load", True)),
                }
                fw_section = self.bot.config.get("framework", {}) or {}
                framework_info = {
                    "version": fw_section.get("version"),
                    "recommended_python": fw_section.get("recommended_python"),
                    "python_runtime": fw_section.get("python_runtime"),
                    "docs_url": "https://zygnalbot.com/bot-framework/",
                    "github_url": "https://github.com/TheHolyOneZ/discord-bot-framework",
                    "support_url": "https://zygnalbot.com/support.html",
                }
        except Exception as e:
            logger.error(f"Live Monitor: Failed to collect core settings/framework info: {e}")
        
        plugins_data = {}
        plugin_registry_cog = self.bot.get_cog("PluginRegistry")
        plugins_list = []
        

        loaded_plugin_names = set()
        if plugin_registry_cog:
            try:
                all_plugins = plugin_registry_cog.get_all_plugins()
                
                for name, metadata in all_plugins.items():
                    loaded_plugin_names.add(name)
                    deps_ok, dep_messages = plugin_registry_cog.check_dependencies(name)
                    has_conflicts, conflict_messages = plugin_registry_cog.detect_conflicts(name)
                    has_cycle, cycle_path = plugin_registry_cog._detect_circular_dependencies(name)
                    
                    plugin_commands = list(metadata.commands)[:20]
                    
                    if metadata.cogs:
                        for cog_name in metadata.cogs:
                            cog = self.bot.get_cog(cog_name)
                            if cog and hasattr(cog, 'get_app_commands'):
                                try:
                                    for app_cmd in cog.get_app_commands():
                                        cmd_name = app_cmd.qualified_name if hasattr(app_cmd, 'qualified_name') else app_cmd.name
                                        if cmd_name not in plugin_commands and len(plugin_commands) < 20:
                                            plugin_commands.append(cmd_name)
                                except:
                                    pass
                    
                    plugins_list.append({
                        "name": name,
                        "version": metadata.version,
                        "author": metadata.author,
                        "description": metadata.description,
                        "commands": plugin_commands,
                        "commands_count": len(plugin_commands),
                        "cogs": list(metadata.cogs),
                        "cogs_count": len(metadata.cogs),
                        "dependencies": metadata.dependencies,
                        "conflicts_with": list(metadata.conflicts_with),
                        "provides_hooks": metadata.provides_hooks,
                        "listens_to_hooks": metadata.listens_to_hooks,
                        "loaded_at": metadata.loaded_at,
                        "load_time": metadata.load_time,
                        "file_path": str(metadata.file_path) if metadata.file_path else None,
                        "deps_ok": deps_ok,
                        "has_conflicts": has_conflicts,
                        "has_cycle": has_cycle,
                        "scan_errors": metadata.scan_errors,
                        "dep_messages": dep_messages if not deps_ok else [],
                        "conflict_messages": conflict_messages if has_conflicts else [],
                        "loaded": f"extensions.{name}" in self.bot.extensions
                    })
            except Exception as e:
                logger.error(f"Live Monitor: Failed to collect plugins data: {e}")
        

        extensions_path = Path("./extensions")
        if extensions_path.exists():
            for filepath in extensions_path.glob("*.py"):
                ext_name = filepath.stem
                

                if ext_name in loaded_plugin_names:
                    continue
                

                full_name = f"extensions.{ext_name}"
                is_loaded = full_name in self.bot.extensions
                load_time = self.bot.extension_load_times.get(ext_name, 0) if hasattr(self.bot, 'extension_load_times') else 0
                
                plugins_list.append({
                    "name": ext_name,
                    "version": "unknown",
                    "author": "unknown",
                    "description": "Extension file exists but not loaded or failed to load",
                    "commands": [],
                    "commands_count": 0,
                    "cogs": [],
                    "cogs_count": 0,
                    "dependencies": {},
                    "conflicts_with": [],
                    "provides_hooks": [],
                    "listens_to_hooks": [],
                    "loaded_at": None,
                    "load_time": load_time,
                    "file_path": str(filepath),
                    "deps_ok": True,  # Unknown, assume OK
                    "has_conflicts": False,  # Unknown, assume no conflicts
                    "has_cycle": False,  # Unknown, assume no cycle
                    "scan_errors": [],
                    "dep_messages": [],
                    "conflict_messages": [],
                    "loaded": is_loaded
                })
        

        plugins_data = {
            "total": len(plugins_list),
            "plugins": plugins_list,
            "enforce_dependencies": bool(getattr(plugin_registry_cog, "enforce_dependencies", False)) if plugin_registry_cog else False,
            "enforce_conflicts": bool(getattr(plugin_registry_cog, "enforce_conflicts", False)) if plugin_registry_cog else False,
        }
        
        available_extensions = []
        extensions_path = Path("./extensions")
        if extensions_path.exists():
            for filepath in extensions_path.glob("*.py"):
                ext_name = filepath.stem
                full_name = f"extensions.{ext_name}"
                is_loaded = full_name in self.bot.extensions
                
                load_time = self.bot.extension_load_times.get(ext_name, 0) if hasattr(self.bot, 'extension_load_times') else 0
                
                available_extensions.append({
                    "name": ext_name,
                    "full_name": full_name,
                    "file_path": str(filepath),
                    "loaded": is_loaded,
                    "load_time": load_time
                })
        
        diagnostics_cog = self.bot.get_cog("FrameworkDiagnostics")
        health_data = {}
        if diagnostics_cog:
            try:
                error_rate = diagnostics_cog._calculate_error_rate()
                health_data = {
                    "error_rate": error_rate,
                    "status": "critical" if error_rate >= 10 else "degraded" if error_rate >= 5 else "healthy",
                    "event_loop_lag_ms": round(diagnostics_cog.health_metrics.get("event_loop_lag_ms", 0), 2),
                    "consecutive_write_failures": diagnostics_cog.health_metrics.get("consecutive_write_failures", 0)
                }
            except Exception as e:
                logger.error(f"Live Monitor: Failed to collect health data: {e}")
        
        commands_list = await self._get_all_commands()

        commands_data = {
            "total": len(commands_list),
            "commands": commands_list
        }
        

        file_system_data = self._get_file_system_info()


        fileops_data = self._fileops_response or {}
        self._fileops_response = None  # Reset after sending

        recent_events = self._event_log[-30:]
        
        return {
            "timestamp": datetime.now().isoformat(),
            "bot": bot_info,
            "system": system_info,
            "event_hooks": event_hooks_data,
            "slash_limiter": slash_limiter_data,
            "atomic_fs": atomic_fs_data,
            "core_settings": core_settings,
            "framework": framework_info,
            "plugins": plugins_data,
            "available_extensions": available_extensions,
            "health": health_data,
            "commands": commands_data,
            "file_system": {**file_system_data, "fileops": fileops_data},
            "events": recent_events,
            "chat_history": chat_history,
        }
    
    @tasks.loop(seconds=2)
    async def send_status_loop(self):
        if not self.is_enabled or not self.config.get("website_url") or not self.config.get("secret_token"):
            return
        
        try:
            await self._check_for_commands()
            
            data = await self._collect_monitor_data()
            
            packages = {
                "core": {
                    "timestamp": data["timestamp"],
                    "bot": data["bot"],
                    "system": data["system"],
                    "health": data.get("health", {}),
                    "chat_history": data.get("chat_history"),
                },
                "commands": data.get("commands", {}),
                "plugins": data.get("plugins", {}),
                "hooks": data.get("event_hooks", {}),
                "extensions": {"available_extensions": data.get("available_extensions", [])},
                "system_details": {
                    "slash_limiter": data.get("slash_limiter", {}),
                    "atomic_fs": data.get("atomic_fs", {}),
                    "core_settings": data.get("core_settings", {}),
                    "framework": data.get("framework", {}),
                },
                "events": {"events": data.get("events", [])},
                "filesystem": data.get("file_system", {})
            }
            
            base_url = self.config['website_url']
            token = self.config['secret_token']
            
            async with aiohttp.ClientSession() as session:
                for package_name, package_data in packages.items():
                    url = f"{base_url}/receive.php?token={token}&package={package_name}"
                    try:
                        async with session.post(url, json=package_data, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status != 200:
                                logger.warning(f"Live Monitor: Package '{package_name}' send failed with status {resp.status}")
                    except asyncio.CancelledError:

                        logger.info("Live Monitor: send_status_loop HTTP send cancelled")
                        raise
                    except Exception as e:
                        logger.error(f"Live Monitor: Error sending package '{package_name}': {e}")
            
            self.last_send_success = datetime.now()
            self.send_failures = 0
        
        except asyncio.CancelledError:
            logger.info("Live Monitor: send_status_loop cancelled")
            raise
        except Exception as e:
            self.send_failures += 1
            logger.error(f"Live Monitor: Send error: {e}")
    
    @send_status_loop.before_loop
    async def before_send_status_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(2)
    
    async def _check_for_commands(self):
        if not self.config.get("website_url") or not self.config.get("secret_token"):
            return
        
        try:
            url = f"{self.config['website_url']}/get_commands.php?token={self.config['secret_token']}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        commands = await resp.json()

                        if commands:
                            logger.info(f"Live Monitor: Received {len(commands)} command(s) from server")



                        for cmd in commands:
                            cmd_type = cmd.get("command", "unknown")
                            logger.info(f"Live Monitor: Executing command '{cmd_type}' with params: {cmd.get('params', {})}")

                            asyncio.create_task(self._execute_command(cmd))
        
        except asyncio.CancelledError:
            logger.info("Live Monitor: _check_for_commands cancelled")
            raise
        except Exception as e:
            logger.error(f"Live Monitor: Command check error: {e}")
    
    async def _execute_command(self, command: Dict[str, Any]):
        cmd_type = command.get("command")
        params = command.get("params", {})



        if isinstance(params, list):

            if params and isinstance(params[0], dict):
                params = params[0]
            else:
                params = {}
        elif not isinstance(params, dict):
            params = {}
        

        fileops_commands = [
            "list_dir", "read_file", "write_file", "rename_file", "create_dir", "delete_path",
            "fetch_marketplace_extensions", "download_marketplace_extension", "load_downloaded_extension",
            "backup_bot_directory"
        ]
        if cmd_type in fileops_commands:
            self._fileops_response = None
        
        try:
            if cmd_type == "enable_hook":
                hook_id = params.get("hook_id")
                if hasattr(self.bot, 'enable_hook'):
                    self.bot.enable_hook(hook_id)
                    self._log_event("hook_enabled", {"hook_id": hook_id})
            
            elif cmd_type == "disable_hook":
                hook_id = params.get("hook_id")
                if hasattr(self.bot, 'disable_hook'):
                    self.bot.disable_hook(hook_id)
                    self._log_event("hook_disabled", {"hook_id": hook_id})
            
            elif cmd_type == "reset_circuit":
                hook_id = params.get("hook_id")
                event_hooks_cog = self.bot.get_cog("EventHooks")
                if event_hooks_cog:
                    event_hooks_cog.circuit_breaker.reset(hook_id)
                    self._log_event("circuit_reset", {"hook_id": hook_id})
            
            elif cmd_type == "reload_extension":
                ext_name = params.get("extension")
                try:
                    await self.bot.reload_extension(ext_name)
                    logger.info(f"Live Monitor: [OK] Extension reloaded successfully: {ext_name}")
                    self._log_event("extension_reloaded", {"extension": ext_name, "success": True})
                    

                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Live Monitor: [ERROR] Failed to reload extension {ext_name}: {e}")
                    self._log_event("extension_reload_failed", {"extension": ext_name, "error": str(e)})
            
            elif cmd_type == "load_extension":
                ext_name = params.get("extension")
                try:
                    start_time = time.time()
                    await self.bot.load_extension(ext_name)
                    load_time = time.time() - start_time
                    

                    simple_name = ext_name.replace("extensions.", "").replace("cogs.", "")
                    if not hasattr(self.bot, 'extension_load_times'):
                        self.bot.extension_load_times = {}
                    self.bot.extension_load_times[simple_name] = load_time
                    
                    logger.info(f"Live Monitor: [OK] Extension loaded successfully: {ext_name} ({load_time:.3f}s)")
                    self._log_event("extension_loaded", {"extension": ext_name, "success": True, "load_time": load_time})
                    

                    await asyncio.sleep(0.5)
                    

                    plugin_registry_cog = self.bot.get_cog("PluginRegistry")
                    if plugin_registry_cog:
                        if simple_name not in plugin_registry_cog.registry:
                            logger.info(f"Live Monitor: Manually triggering PluginRegistry scan for {simple_name}")
                            try:
                                await plugin_registry_cog.register_plugin(simple_name, auto_scan=True)
                                logger.info(f"Live Monitor: [OK] PluginRegistry scan complete for {simple_name}")
                            except Exception as scan_err:
                                logger.error(f"Live Monitor: [ERROR] PluginRegistry scan failed for {simple_name}: {scan_err}")
                        else:

                            plugin_registry_cog.registry[simple_name].load_time = load_time
                except Exception as e:
                    logger.error(f"Live Monitor: [ERROR] Failed to load extension {ext_name}: {e}")
                    self._log_event("extension_load_failed", {"extension": ext_name, "error": str(e)})
            
            elif cmd_type == "unload_extension":
                ext_name = params.get("extension")
                try:
                    await self.bot.unload_extension(ext_name)
                    logger.info(f"Live Monitor: [OK] Extension unloaded successfully: {ext_name}")
                    self._log_event("extension_unloaded", {"extension": ext_name, "success": True})
                except Exception as e:
                    logger.error(f"Live Monitor: [ERROR] Failed to unload extension {ext_name}: {e}")
                    self._log_event("extension_unload_failed", {"extension": ext_name, "error": str(e)})
            
            elif cmd_type == "plugin_registry_set_enforcement":
                mode = params.get("mode")
                enabled = params.get("enabled")
                plugin_registry_cog = self.bot.get_cog("PluginRegistry")
                if plugin_registry_cog and isinstance(enabled, bool) and mode in {"deps", "conflicts"}:
                    if mode == "deps":
                        setattr(plugin_registry_cog, "enforce_dependencies", enabled)
                        self._log_event("plugin_enforcement_updated", {"mode": "dependencies", "enabled": enabled})
                    else:
                        setattr(plugin_registry_cog, "enforce_conflicts", enabled)
                        self._log_event("plugin_enforcement_updated", {"mode": "conflicts", "enabled": enabled})

            elif cmd_type == "slash_limiter_set_debug":
                enabled = bool(params.get("enabled"))
                slash_limiter_cog = self.bot.get_cog("SlashLimiter")
                if slash_limiter_cog and hasattr(slash_limiter_cog, "DEBUG_MODE"):
                    slash_limiter_cog.DEBUG_MODE = enabled
                    self._log_event("slash_limiter_debug_updated", {"enabled": enabled})
            
            elif cmd_type == "set_auto_reload":
                enabled = bool(params.get("enabled"))
                try:
                    if hasattr(self.bot, "config") and self.bot.config is not None:
                        await self.bot.config.set("auto_reload", enabled)
                except Exception as e:
                    logger.error(f"Live Monitor: Failed to update auto_reload in config: {e}")
                try:
                    if hasattr(self.bot, "extension_reloader"):
                        task = self.bot.extension_reloader
                        if enabled and not task.is_running():
                            task.start()
                        elif not enabled and task.is_running():
                            task.cancel()
                except Exception as e:
                    logger.error(f"Live Monitor: Failed to start/stop extension_reloader: {e}")
                self._log_event("auto_reload_updated", {"enabled": enabled})

            elif cmd_type == "set_extensions_auto_load":
                enabled = bool(params.get("enabled"))
                try:
                    if hasattr(self.bot, "config") and self.bot.config is not None:
                        await self.bot.config.set("extensions.auto_load", enabled)
                        self._log_event("extensions_auto_load_updated", {"enabled": enabled})
                except Exception as e:
                    logger.error(f"Live Monitor: Failed to update extensions.auto_load in config: {e}")
            
            elif cmd_type == "clear_cache":
                if hasattr(self.bot.config, 'file_handler'):
                    self.bot.config.file_handler.clear_all_cache()
                    self._log_event("cache_cleared", {})

            elif cmd_type == "generate_framework_diagnostics":
                diagnostics_cog = self.bot.get_cog("FrameworkDiagnostics")
                if diagnostics_cog and hasattr(diagnostics_cog, "generate_diagnostics"):
                    try:
                        diag = await diagnostics_cog.generate_diagnostics()
                        self._log_event("framework_diagnostics_generated", {"success": bool(diag)})
                    except Exception as e:
                        logger.error(f"Live Monitor: Failed to generate framework diagnostics via dashboard: {e}")
                        self._log_event("framework_diagnostics_failed", {"error": str(e)})

            elif cmd_type == "leave_guild":
                guild_id = params.get("guild_id")
                if guild_id is None:
                    return
                try:
                    gid_int = int(guild_id)
                except (TypeError, ValueError):
                    logger.error(f"Live Monitor: leave_guild called with invalid guild_id={guild_id!r}")
                    return
                guild = self.bot.get_guild(gid_int)
                if guild is None:
                    logger.error(f"Live Monitor: leave_guild - guild not found: {gid_int}")
                    return
                try:
                    await guild.leave()
                    self._log_event(
                        "guild_left",
                        {
                            "guild_id": str(guild.id),
                            "guild": guild.name,
                            "owner_id": str(getattr(guild, "owner_id", "")),
                        },
                    )
                except Exception as e:
                    logger.error(f"Live Monitor: Failed to leave guild {gid_int}: {e}")
                    self._log_event(
                        "guild_leave_failed",
                        {"guild_id": str(gid_int), "error": str(e)},
                    )

            elif cmd_type == "backup_bot_directory":



                try:
                    base = Path(".").resolve()
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_root = Path("./data/Dashboardbackups")
                    backup_root.mkdir(parents=True, exist_ok=True)
                    archive_base = backup_root / f"bot_backup_{ts}"

                    logger.info(f"Live Monitor: Starting backup: {archive_base}.zip")



                    archive_path_str = await asyncio.to_thread(
                        shutil.make_archive,
                        str(archive_base),
                        "zip",
                        base,
                    )
                    archive_path = Path(archive_path_str)


                    def _get_file_stats(path):
                        if path.exists():
                            size = path.stat().st_size
                            return size, size / (1024 * 1024)
                        return 0, 0

                    size_bytes, size_mb = await asyncio.to_thread(_get_file_stats, archive_path)

                    self._log_event(
                        "bot_backup_created",
                        {
                            "path": str(archive_path),
                            "directory": str(backup_root.resolve()),
                            "size_bytes": size_bytes,
                            "size_mb": f"{size_mb:.2f}"
                        },
                    )
                    logger.info(f"Live Monitor: Backup completed successfully: {archive_path.name} ({size_mb:.2f} MB)")

                    self._fileops_response = {
                        "success": True,
                        "message": f"Backup created: {archive_path.name} ({size_mb:.2f} MB)",
                        "path": str(archive_path)
                    }
                except Exception as e:
                    logger.error(f"Live Monitor: backup_bot_directory failed: {e}")
                    self._log_event("bot_backup_failed", {"error": str(e)})
                    self._fileops_response = {
                        "success": False,
                        "error": str(e)
                    }

            elif cmd_type == "shutdown_bot":
                delay = int(params.get("delay", 0))
                self._log_event("bot_shutdown_requested", {"delay_seconds": delay})

                async def _delayed_shutdown():
                    try:
                        if delay > 0:
                            await asyncio.sleep(delay)
                        await self.bot.close()
                    except Exception as e:
                        logger.error(f"Live Monitor: Shutdown command failed: {e}")
                        self._log_event("bot_shutdown_failed", {"error": str(e)})

                asyncio.create_task(_delayed_shutdown())

            elif cmd_type == "af_invalidate_cache_entry":
                path = params.get("path")
                if path and hasattr(self.bot.config, 'file_handler'):
                    self.bot.config.file_handler.invalidate_cache(path)
                    self._log_event("atomic_fs_cache_invalidated", {"path": path})

            elif cmd_type == "af_force_release_lock":
                path = params.get("path")
                if path and hasattr(self.bot.config, 'file_handler') and hasattr(self.bot.config.file_handler, 'force_release_lock'):
                    released = self.bot.config.file_handler.force_release_lock(path)
                    self._log_event(
                        "atomic_fs_lock_released" if released else "atomic_fs_lock_release_failed",
                        {"path": path}
                    )

            elif cmd_type == "fetch_marketplace_extensions":
                try:
                    api_url = "https://zygnalbot.com/extension/api/extensions.php?action=list"
                    logger.info(f"Live Monitor: Fetching marketplace extensions from {api_url}")
                    
                    timeout = aiohttp.ClientTimeout(total=30)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.get(api_url) as response:
                            logger.info(f"Live Monitor: Marketplace API returned status {response.status}")
                            
                            if response.status == 200:
                                data = await response.json()
                                if data.get('success'):
                                    extensions = data.get('extensions', [])
                                    logger.info(f"Live Monitor: Successfully fetched {len(extensions)} extensions")
                                    self._fileops_response = {
                                        "success": True,
                                        "command_type": "fetch_marketplace_extensions",
                                        "extensions": extensions
                                    }

                                    try:
                                        base_url = self.config['website_url']
                                        token = self.config['secret_token']
                                        url = f"{base_url}/receive.php?token={token}&package=fileops"
                                        async with aiohttp.ClientSession() as session:
                                            async with session.post(url, json=self._fileops_response, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                                if resp.status == 200:
                                                    logger.info(f"Live Monitor: [OK] Marketplace extensions sent to dashboard ({len(extensions)} extensions)")
                                                else:
                                                    logger.warning(f"Live Monitor: [ERROR] Marketplace send failed with status {resp.status}")
                                    except Exception as send_err:
                                        logger.error(f"Live Monitor: [ERROR] Failed to send marketplace response: {send_err}")
                                else:
                                    error_msg = "API returned success: false"
                                    logger.error(f"Live Monitor: {error_msg}")
                                    self._fileops_response = {"success": False, "error": error_msg}
                            elif response.status == 429:
                                error_msg = "Rate limit exceeded. Please try again in a moment."
                                logger.warning(f"Live Monitor: {error_msg}")
                                self._fileops_response = {"success": False, "error": error_msg}
                            else:
                                error_msg = f"API request failed with status {response.status}"
                                logger.error(f"Live Monitor: {error_msg}")
                                self._fileops_response = {"success": False, "error": error_msg}
                except asyncio.TimeoutError:
                    error_msg = "Request timed out after 30 seconds"
                    logger.error(f"Live Monitor: Marketplace fetch - {error_msg}")
                    self._fileops_response = {"success": False, "error": error_msg}
                except Exception as e:
                    error_msg = f"Marketplace fetch failed: {str(e)}"
                    logger.error(f"Live Monitor: {error_msg}")
                    self._fileops_response = {"success": False, "error": str(e)}
                finally:

                    if self._fileops_response and (self._fileops_response.get('success') is False or self._fileops_response.get('error')):
                        try:
                            base_url = self.config['website_url']
                            token = self.config['secret_token']
                            url = f"{base_url}/receive.php?token={token}&package=fileops"
                            async with aiohttp.ClientSession() as session:
                                async with session.post(url, json=self._fileops_response, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                    if resp.status == 200:
                                        logger.info(f"Live Monitor: [OK] Error response sent to dashboard")
                        except Exception as send_err:
                            logger.error(f"Live Monitor: [ERROR] Failed to send error response: {send_err}")
            
            elif cmd_type == "download_marketplace_extension":

                try:
                    base_url = self.config['website_url']
                    token = self.config['secret_token']
                    url = f"{base_url}/receive.php?token={token}&package=fileops"
                    async with aiohttp.ClientSession() as session:

                        await session.post(url, json={}, timeout=aiohttp.ClientTimeout(total=10))
                except:
                    pass
                
                try:
                    extension_data = params.get("extension")
                    if not extension_data:
                        self._fileops_response = {"success": False, "error": "No extension data provided"}
                    else:
                        zygnal_id_file = Path("./data/marketplace/ZygnalID.txt")
                        zygnal_id_file.parent.mkdir(parents=True, exist_ok=True)
                        
                        if zygnal_id_file.exists():
                            with open(zygnal_id_file, 'r') as f:
                                zygnal_id = f.read().strip()
                        else:
                            import secrets
                            alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
                            zygnal_id = ''.join(secrets.choice(alphabet) for _ in range(16))
                            zygnal_id_file.parent.mkdir(parents=True, exist_ok=True)
                            with open(zygnal_id_file, 'w') as f:
                                f.write(zygnal_id)
                        
                        if extension_data.get('customUrl'):
                            base_url = extension_data['customUrl']
                            if base_url.startswith('http') and zygnal_id:
                                sep = '&' if ('?' in base_url) else '?'
                                download_url = f"{base_url}{sep}zygnalid={zygnal_id}"
                            else:
                                download_url = base_url
                        else:
                            extension_id = extension_data['id']
                            download_url = f"https://zygnalbot.com/extension/download.php?id={extension_id}&zygnalid={zygnal_id}"
                        

                        response_text = None
                        error = None
                        max_retries = 3
                        
                        for attempt in range(max_retries):
                            try:
                                timeout = aiohttp.ClientTimeout(total=60)
                                async with aiohttp.ClientSession(timeout=timeout) as session:
                                    async with session.get(download_url) as response:
                                        if response.status == 200:
                                            response_text = await response.text()
                                            break
                                        elif response.status == 403:
                                            error = "403"
                                            break
                                        elif response.status == 429:
                                            retry_after = int(response.headers.get('Retry-After', 60))
                                            if attempt < max_retries - 1:
                                                logger.warning(f"Rate limited, retrying after {retry_after}s (attempt {attempt + 1}/{max_retries})")
                                                await asyncio.sleep(retry_after)
                                                continue
                                            error = "Rate limited (max retries reached)"
                                            break
                                        else:
                                            error = f"HTTP {response.status}"
                                            break
                            except asyncio.TimeoutError:
                                if attempt < max_retries - 1:
                                    logger.warning(f"Timeout, retrying (attempt {attempt + 1}/{max_retries})")
                                    await asyncio.sleep(2 ** attempt)
                                    continue
                                error = "Timeout (max retries reached)"
                                break
                            except Exception as e:
                                if attempt < max_retries - 1:
                                    logger.warning(f"Error: {e}, retrying (attempt {attempt + 1}/{max_retries})")
                                    await asyncio.sleep(2 ** attempt)
                                    continue
                                error = f"Error: {e}"
                                break
                        

                        if error and ("403" in str(error) or "Forbidden" in str(error)):
                            error_message = (
                                "**ZygnalID Not Activated**\n\n"
                                "Your ZygnalID is probably NOT activated or got deactivated.\n\n"
                                "**How to activate:**\n"
                                "1. Join the ZygnalBot Discord server: `gg/sgZnXca5ts`\n"
                                "2. Create a ticket with the category **Zygnal Activation**\n"
                                "3. Read the embed that got sent into the ticket\n"
                                "4. Provide the information requested\n"
                                "5. Wait for a supporter or TheHolyOneZ to activate it\n\n"
                                f"Use `/marketplace myid` to view your ZygnalID"
                            )
                            logger.error("Download failed - 403 Forbidden (ZygnalID not activated)")
                            self._fileops_response = {"success": False, "error": error_message, "error_type": "zygnal_id_not_activated"}

                            try:
                                base_url = self.config['website_url']
                                token = self.config['secret_token']
                                url = f"{base_url}/receive.php?token={token}&package=fileops"
                                async with aiohttp.ClientSession() as session:
                                    async with session.post(url, json=self._fileops_response, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                        if resp.status == 200:
                                            logger.info(f"Live Monitor: [OK] 403 error sent to dashboard")
                            except Exception as send_err:
                                logger.error(f"Live Monitor: [ERROR] Failed to send 403 error: {send_err}")
                        elif error:
                            self._fileops_response = {"success": False, "error": error}
                        elif response_text:
                            if ("invalid" in response_text.lower() and "zygnalid" in response_text.lower()) or "not activated" in response_text.lower():
                                error_message = (
                                    "Your ZygnalID is **invalid or not activated**.\n\n"
                                    "**To activate your ID, follow these steps:**\n"
                                    "1. Go to the official ZygnalBot Discord server: `gg/sgZnXca5ts`\n"
                                    "2. Verify yourself on the server.\n"
                                    "3. Open a ticket for **Zygnal ID Activation**.\n"
                                    "4. Read the embed sent in the ticket and provide the necessary information to start the activation process.\n\n"
                                    f"Your ZygnalID: {zygnal_id}"
                                )
                                logger.error("Download failed due to ZygnalID issue")
                                self._fileops_response = {"success": False, "error": error_message, "error_type": "zygnal_id_not_activated"}

                                try:
                                    base_url = self.config['website_url']
                                    token = self.config['secret_token']
                                    url = f"{base_url}/receive.php?token={token}&package=fileops"
                                    async with aiohttp.ClientSession() as session:
                                        async with session.post(url, json=self._fileops_response, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                            if resp.status == 200:
                                                logger.info(f"Live Monitor: [OK] ZygnalID error sent to dashboard")
                                except Exception as send_err:
                                    logger.error(f"Live Monitor: [ERROR] Failed to send ZygnalID error: {send_err}")
                            else:
                                extensions_folder = Path("./extensions")
                                extensions_folder.mkdir(parents=True, exist_ok=True)
                                
                                import re
                                filename = f"{extension_data['title'].replace(' ', '_').lower()}.{extension_data['fileType']}"
                                filename = re.sub(r'[^\w\-_\.]', '', filename)
                                filepath = extensions_folder / filename
                                
                                with open(filepath, 'w', encoding='utf-8') as f:
                                    f.write(response_text)
                                
                                logger.info(f"Successfully downloaded extension to {filepath}")
                                

                                filepath_str = str(filepath)
                                if platform.system() == "Windows":

                                    filepath_formatted = filepath_str
                                else:

                                    filepath_formatted = filepath_str.replace('\\', '/')
                                
                                self._fileops_response = {
                                    "success": True,
                                    "command_type": "download_marketplace_extension",
                                    "message": f"Downloaded to {filepath}",
                                    "filepath": filepath_formatted,
                                    "filename": filename
                                }
                        else:
                            self._fileops_response = {"success": False, "error": "Max retries exceeded"}
                        

                        if self._fileops_response:
                            try:
                                base_url = self.config['website_url']
                                token = self.config['secret_token']
                                url = f"{base_url}/receive.php?token={token}&package=fileops"
                                async with aiohttp.ClientSession() as session:
                                    async with session.post(url, json=self._fileops_response, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                        if resp.status == 200:
                                            logger.info(f"Live Monitor: [OK] Download response sent to dashboard")
                                        else:
                                            logger.warning(f"Live Monitor: [ERROR] Download response send failed with status {resp.status}")
                            except Exception as send_err:
                                logger.error(f"Live Monitor: [ERROR] Failed to send download response: {send_err}")
                except Exception as e:
                    logger.error(f"Marketplace download failed: {e}")
                    self._fileops_response = {"success": False, "error": str(e)}

                    try:
                        base_url = self.config['website_url']
                        token = self.config['secret_token']
                        url = f"{base_url}/receive.php?token={token}&package=fileops"
                        async with aiohttp.ClientSession() as session:
                            async with session.post(url, json=self._fileops_response, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                pass
                    except:
                        pass
            
            elif cmd_type == "load_downloaded_extension":
                try:
                    filepath = params.get("filepath")
                    if not filepath:
                        self._fileops_response = {"success": False, "error": "No filepath provided"}
                    else:
                        file_path = Path(filepath)
                        if not file_path.exists():
                            self._fileops_response = {"success": False, "error": f"File not found: {filepath}"}
                        else:
                            extension_name = file_path.stem
                            await self.bot.load_extension(f"extensions.{extension_name}")
                            
                            self._fileops_response = {
                                "success": True,
                                "message": f"Loaded extension: {extension_name}",
                                "extension_name": extension_name
                            }
                        

                        if self._fileops_response:
                            try:
                                base_url = self.config['website_url']
                                token = self.config['secret_token']
                                url = f"{base_url}/receive.php?token={token}&package=fileops"
                                async with aiohttp.ClientSession() as session:
                                    async with session.post(url, json=self._fileops_response, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                        if resp.status == 200:
                                            logger.info(f"Live Monitor: [OK] Load response sent to dashboard")
                                        else:
                                            logger.warning(f"Live Monitor: [ERROR] Load response send failed with status {resp.status}")
                            except Exception as send_err:
                                logger.error(f"Live Monitor: [ERROR] Failed to send load response: {send_err}")
                except Exception as e:
                    logger.error(f"Load downloaded extension failed: {e}")
                    self._fileops_response = {"success": False, "error": str(e)}

                    try:
                        base_url = self.config['website_url']
                        token = self.config['secret_token']
                        url = f"{base_url}/receive.php?token={token}&package=fileops"
                        async with aiohttp.ClientSession() as session:
                            async with session.post(url, json=self._fileops_response, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                pass
                    except:
                        pass

            elif cmd_type == "list_dir":
                path = params.get("path")
                allowed_paths = ["./", "./botlogs", "./data", "./cogs", "./extensions"]
                if not path or not any(path.startswith(p) for p in allowed_paths):
                    return
                try:

                    def _list_directory(dir_path):
                        p = Path(dir_path)
                        if not p.is_dir():
                            return None
                        files = []
                        for item in sorted(p.iterdir()):
                            if item.is_file():
                                files.append({
                                    "name": item.name,
                                    "type": "file",
                                    "size": item.stat().st_size,
                                    "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat()
                                })
                            elif item.is_dir():
                                files.append({"name": item.name, "type": "dir"})
                        return files


                    files = await asyncio.to_thread(_list_directory, path)

                    if files is not None:
                        response_data = {
                            "type": "list_dir",
                            "path": path,
                            "files": files,
                            "request_id": params.get("request_id")
                        }
                        logger.info(f"Live Monitor: Preparing fileops response for list_dir: {path} ({len(files)} items)")

                        async with self._fileops_lock:
                            try:
                                base_url = self.config['website_url']
                                token = self.config['secret_token']
                                url = f"{base_url}/receive.php?token={token}&package=fileops"
                                async with aiohttp.ClientSession() as session:
                                    async with session.post(url, json=response_data, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                        if resp.status == 200:
                                            logger.info(f"Live Monitor: [OK] Fileops sent successfully (list_dir: {path})")
                                        else:
                                            logger.warning(f"Live Monitor: [ERROR] Fileops send failed with status {resp.status}")
                            except Exception as e:
                                logger.error(f"Live Monitor: [ERROR] Failed to send fileops response: {e}")
                except Exception as e:
                    logger.error(f"Live Monitor: List dir error: {e}")

            elif cmd_type == "read_file":
                path = params.get("path")
                allowed_paths = ["./", "./botlogs", "./data", "./cogs", "./extensions"]
                if not path or not any(path.startswith(p) for p in allowed_paths):
                    return
                try:

                    def _read_file(file_path, max_size):
                        p = Path(file_path)
                        if not p.is_file():
                            return None, "not a file"

                        file_size = p.stat().st_size

                        if file_size > max_size:
                            return None, f"File too large ({file_size} bytes). Maximum size is {max_size} bytes."

                        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        return content, None


                    max_size = 10 * 1024 * 1024  # 10MB limit
                    content, error = await asyncio.to_thread(_read_file, path, max_size)

                    if error:
                        logger.error(f"Live Monitor: read_file failed - {error}: {path}")
                        if error == "not a file":
                            return

                        response_data = {
                            "type": "read_file",
                            "path": path,
                            "content": f"ERROR: {error}",
                            "error": True,
                            "request_id": params.get("request_id")
                        }
                    else:
                        response_data = {
                            "type": "read_file",
                            "path": path,
                            "content": content,
                            "request_id": params.get("request_id")
                        }
                        logger.info(f"Live Monitor: Preparing fileops response for read_file: {path} ({len(content)} bytes)")


                    async with self._fileops_lock:
                        try:
                            base_url = self.config['website_url']
                            token = self.config['secret_token']
                            url = f"{base_url}/receive.php?token={token}&package=fileops"
                            async with aiohttp.ClientSession() as session:
                                async with session.post(url, json=response_data, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                    if resp.status == 200:
                                        logger.info(f"Live Monitor: [OK] Fileops sent successfully (read_file: {path})")
                                    else:
                                        logger.warning(f"Live Monitor: [ERROR] Fileops send failed with status {resp.status}")
                        except Exception as e:
                            logger.error(f"Live Monitor: [ERROR] Failed to send fileops response: {e}")
                except Exception as e:
                    logger.error(f"Live Monitor: Read file error: {e}")

                    async with self._fileops_lock:
                        try:
                            response_data = {
                                "type": "read_file",
                                "path": path,
                                "content": f"ERROR: Failed to read file - {str(e)}",
                                "error": True,
                                "request_id": params.get("request_id")
                            }
                            base_url = self.config['website_url']
                            token = self.config['secret_token']
                            url = f"{base_url}/receive.php?token={token}&package=fileops"
                            async with aiohttp.ClientSession() as session:
                                async with session.post(url, json=response_data, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                    logger.info(f"Live Monitor: Sent error response for read_file: {path}")
                        except:
                            pass

            elif cmd_type == "write_file":
                path = params.get("path")
                content = params.get("content", "")
                allowed_paths = ["./", "./botlogs", "./data", "./cogs", "./extensions"]
                if not path or not any(path.startswith(p) for p in allowed_paths):
                    return
                try:

                    def _write_file(file_path, file_content):
                        p = Path(file_path)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        with open(p, 'w', encoding='utf-8') as f:
                            f.write(file_content)


                    await asyncio.to_thread(_write_file, path, content)
                    self._log_event("file_written", {"path": path})
                except Exception as e:
                    logger.error(f"Live Monitor: Write file error: {e}")

            elif cmd_type == "rename_file":
                old_path = params.get("old_path")
                new_path = params.get("new_path")
                allowed_paths = ["./", "./botlogs", "./data", "./cogs", "./extensions"]
                if not old_path or not new_path:
                    return
                if not any(old_path.startswith(p) for p in allowed_paths):
                    return
                if not any(new_path.startswith(p) for p in allowed_paths):
                    return
                try:

                    def _rename_file(old_file_path, new_file_path):
                        old_p = Path(old_file_path)
                        new_p = Path(new_file_path)
                        new_p.parent.mkdir(parents=True, exist_ok=True)
                        old_p.rename(new_p)


                    await asyncio.to_thread(_rename_file, old_path, new_path)
                    self._log_event("file_renamed", {"old_path": old_path, "new_path": new_path})
                except Exception as e:
                    logger.error(f"Live Monitor: Rename file error: {e}")

            elif cmd_type == "create_dir":
                path = params.get("path")
                allowed_paths = ["./", "./botlogs", "./data", "./cogs", "./extensions"]
                if not path or not any(path.startswith(p) for p in allowed_paths):
                    return
                try:

                    def _create_dir(dir_path):
                        p = Path(dir_path)
                        p.mkdir(parents=True, exist_ok=True)


                    await asyncio.to_thread(_create_dir, path)
                    self._log_event("dir_created", {"path": path})
                except Exception as e:
                    logger.error(f"Live Monitor: Create dir error: {e}")

            elif cmd_type == "delete_path":
                path = params.get("path")
                allowed_paths = ["./", "./botlogs", "./data", "./cogs", "./extensions"]
                if not path or not any(path.startswith(p) for p in allowed_paths):
                    return
                try:

                    def _delete_path(target_path):
                        p = Path(target_path)
                        if p.is_dir():
                            shutil.rmtree(p)
                        elif p.is_file():
                            p.unlink()


                    await asyncio.to_thread(_delete_path, path)
                    self._log_event("path_deleted", {"path": path})
                except Exception as e:
                    logger.error(f"Live Monitor: Delete path error: {e}")

            elif cmd_type == "send_chat_message":
                guild_id = params.get("guild_id")
                channel_id = params.get("channel_id")
                content = (params.get("content") or "").strip()
                if not channel_id or not content:
                    return
                try:
                    channel_id_int = int(channel_id)
                except (TypeError, ValueError):
                    logger.error(f"Live Monitor: Invalid channel_id for send_chat_message: {channel_id}")
                    return
                try:
                    channel = self.bot.get_channel(channel_id_int)
                    if channel is None and guild_id:
                        try:
                            g = self.bot.get_guild(int(guild_id))
                            if g:
                                channel = g.get_channel(channel_id_int)
                        except Exception:
                            pass
                    if channel is None:
                        logger.error(f"Live Monitor: send_chat_message - channel not found: {channel_id}")
                        return
                    await channel.send(content)
                    self._log_event("chat_message_sent", {
                        "guild_id": str(getattr(getattr(channel, 'guild', None), 'id', guild_id)),
                        "guild": getattr(getattr(channel, 'guild', None), 'name', 'Unknown'),
                        "channel_id": str(channel_id_int),
                        "channel": getattr(channel, 'name', 'Unknown'),
                        "content_preview": content[:120]
                    })
                except Exception as e:
                    logger.error(f"Live Monitor: send_chat_message error: {e}")

            elif cmd_type == "request_chat_history":
                guild_id = params.get("guild_id")
                channel_id = params.get("channel_id")
                try:
                    channel_id_int = int(channel_id)
                except (TypeError, ValueError):
                    logger.error(f"Live Monitor: Invalid channel_id for request_chat_history: {channel_id}")
                    return
                try:
                    channel = self.bot.get_channel(channel_id_int)
                    if channel is None and guild_id:
                        try:
                            g = self.bot.get_guild(int(guild_id))
                            if g:
                                channel = g.get_channel(channel_id_int)
                        except Exception:
                            pass
                    if channel is None:
                        logger.error(f"Live Monitor: request_chat_history - channel not found: {channel_id}")
                        return

                    messages = []
                    try:
                        async for msg in channel.history(limit=50, oldest_first=True):
                            try:
                                messages.append({
                                    "id": str(msg.id),
                                    "author": str(msg.author),
                                    "timestamp": msg.created_at.isoformat(),
                                    "content": msg.content,
                                })
                            except Exception:
                                continue
                    except Exception as e:
                        logger.error(f"Live Monitor: Error fetching chat history: {e}")
                        messages = []

                    self._last_chat_history = {
                        "guild_id": str(getattr(getattr(channel, 'guild', None), 'id', guild_id)),
                        "guild_name": getattr(getattr(channel, 'guild', None), 'name', 'Unknown'),
                        "channel_id": str(channel.id),
                        "channel_name": getattr(channel, 'name', 'Unknown'),
                        "messages": messages,
                    }

                    logger.info(
                        f"Live Monitor: Prepared chat history for guild={self._last_chat_history['guild_id']} "
                        f"channel={self._last_chat_history['channel_id']} messages={len(messages)}"
                    )

                    self._log_event("chat_history_requested", {
                        "guild_id": self._last_chat_history["guild_id"],
                        "channel_id": self._last_chat_history["channel_id"],
                        "message_count": len(messages),
                    })
                except Exception as e:
                    logger.error(f"Live Monitor: request_chat_history error: {e}")
        
        except asyncio.CancelledError:
            logger.info("Live Monitor: _execute_command cancelled")
            raise
        except Exception as e:
            logger.error(f"Live Monitor: Command execution error: {e}")
            self._log_event("command_error", {"command": cmd_type, "error": str(e)})
    
    @app_commands.command(name="livemonitor", description="Configure the live monitoring system")
    @app_commands.describe(
        action="Action to perform",
        url="Website URL for the dashboard",
        interval="Update interval in seconds (5-60)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Quick Start (Setup + Files)", value="quickstart"),
        app_commands.Choice(name="Status", value="status"),
        app_commands.Choice(name="Enable", value="enable"),
        app_commands.Choice(name="Disable", value="disable"),
        app_commands.Choice(name="Get Files", value="files")
    ])
    @app_commands.check(lambda interaction: interaction.client.is_owner(interaction.user))
    async def livemonitor_slash(
        self,
        interaction: discord.Interaction,
        action: str,
        url: Optional[str] = None,
        interval: Optional[int] = None
    ):
        await self._livemonitor_logic(interaction, action, url, interval)

    
    @commands.command(name="livemonitor")
    @commands.is_owner()
    async def livemonitor_prefix(self, ctx, action: str = "status", url: Optional[str] = None, interval: Optional[int] = None):
        await self._livemonitor_logic(ctx, action, url, interval)
    
    async def _livemonitor_logic(self, ctx, action: str, url: Optional[str], interval: Optional[int]):
        if action == "status":
            embed = discord.Embed(
                title="Live Monitor Status",
                color=0x00ff00 if self.is_enabled else 0xff0000,
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="Status",
                value="✅ Enabled" if self.is_enabled else "⏸️ Disabled",
                inline=True
            )
            
            if self.config.get("website_url"):
                embed.add_field(
                    name="Dashboard URL",
                    value=self.config["website_url"],
                    inline=False
                )
            
            if self.config.get("secret_token"):
                embed.add_field(
                    name="Setup Complete",
                    value="✅ Token configured",
                    inline=True
                )
            else:
                embed.add_field(
                    name="Setup Required",
                    value="⚠️ Run quickstart to set up",
                    inline=True
                )
            
            if self.last_send_success:
                embed.add_field(
                    name="Last Success",
                    value=self.last_send_success.strftime("%Y-%m-%d %H:%M:%S"),
                    inline=True
                )
            
            embed.add_field(
                name="Send Failures",
                value=str(self.send_failures),
                inline=True
            )
            
            embed.add_field(
                name="Update Interval",
                value=f"{self.config.get('update_interval', 5)}s",
                inline=True
            )
            
            if not self.config.get("secret_token"):
                embed.add_field(
                    name="Next Steps",
                    value="Run `/livemonitor quickstart <your_website_url>` to get started",
                    inline=False
                )
            
            await (ctx.send(embed=embed) if hasattr(ctx, 'send') else ctx.response.send_message(embed=embed))
        
        elif action == "quickstart":
            if not url:
                embed = discord.Embed(
                    title="Quick Start - Live Monitor",
                    color=0xff0000,
                    description="Please provide a URL for your dashboard"
                )
                embed.add_field(
                    name="Usage",
                    value="`/livemonitor quickstart <your_website_url>`",
                    inline=False
                )
                embed.add_field(
                    name="Example",
                    value="`/livemonitor quickstart https://mybot.com/monitor`",
                    inline=False
                )
                await (ctx.send(embed=embed) if hasattr(ctx, 'send') else ctx.response.send_message(embed=embed))
                return
            
            await (ctx.defer() if hasattr(ctx, 'defer') else ctx.response.defer())
            
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'https://' + url
            

            token = secrets.token_urlsafe(32)

            setup_token = secrets.token_urlsafe(32)
            
            self.config["website_url"] = url.rstrip('/')
            self.config["secret_token"] = token
            self.config["setup_token"] = setup_token
            self.config["update_interval"] = interval or 5
            self.config["enabled"] = False
            self._save_config()
            
            embed = discord.Embed(
                title="📦 Generating Files...",
                color=0x3b82f6,
                description="Creating your dashboard files"
            )
            
            msg = await (ctx.send(embed=embed) if hasattr(ctx, 'send') else ctx.followup.send(embed=embed))
            
            output_dir = Path("./live_monitor_website")
            output_dir.mkdir(exist_ok=True)
            

            (output_dir / "index.php").write_text(
                self._generate_index_php(token, self._get_default_prefix(), setup_token),
                encoding='utf-8'
            )


            (output_dir / "lm_bootstrap.php").write_text(
                self._generate_lm_bootstrap_php(token, setup_token), encoding='utf-8'
            )
            (output_dir / "lm_db.php").write_text(self._generate_lm_db_php(), encoding='utf-8')
            (output_dir / "lm_auth.php").write_text(self._generate_lm_auth_php(), encoding='utf-8')
            (output_dir / "setup.php").write_text(self._generate_setup_php(), encoding='utf-8')
            (output_dir / "login.php").write_text(self._generate_login_php(), encoding='utf-8')
            (output_dir / "oauth_callback.php").write_text(self._generate_oauth_callback_php(), encoding='utf-8')
            (output_dir / "logout.php").write_text(self._generate_logout_php(), encoding='utf-8')
            (output_dir / "owner_audit.php").write_text(self._generate_owner_audit_php(), encoding='utf-8')
            (output_dir / "owner_roles.php").write_text(self._generate_owner_roles_php(), encoding='utf-8')
            (output_dir / "owner_db.php").write_text(self._generate_owner_db_php(), encoding='utf-8')
            (output_dir / "backup_dashboard.php").write_text(self._generate_backup_dashboard_php(), encoding='utf-8')


            (output_dir / "receive.php").write_text(self._generate_receive_php(token), encoding='utf-8')
            (output_dir / "get_commands.php").write_text(self._generate_get_commands_php(token), encoding='utf-8')
            (output_dir / "send_command.php").write_text(self._generate_send_command_php(token), encoding='utf-8')



            self._copy_dashboard_assets(output_dir)
            

            archive_path = shutil.make_archive(str(output_dir), "zip", root_dir=output_dir)


            try:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_root = Path("./data/Dashboardbackups")
                backup_root.mkdir(parents=True, exist_ok=True)
                dash_backup = backup_root / f"web_dashboard_{ts}.zip"
                shutil.copy2(archive_path, dash_backup)
            except Exception as e:
                logger.error(f"Live Monitor: failed to copy dashboard zip to ./data/Dashboardbackups: {e}")


            files = [
                discord.File(archive_path, filename="live_monitor_website.zip"),
            ]
            
            embed = discord.Embed(
                title="✅ Live Monitor - Setup Complete!",
                color=0x00ff00,
                description="Your dashboard files are ready. Follow the steps below:"
            )
            
            embed.add_field(
                name="📁 Step 1: Upload Files",
                value=(
                    "Download `live_monitor_website.zip`, extract it, and upload **everything inside** "
                    "(all PHP files plus the `assets` folder) into the folder on your webhost where you "
                    "want the dashboard to live, for example:\n`" + url + "`"
                ),
                inline=False
            )
            
            embed.add_field(
                name="🔑 Step 2: Security Token",
                value=f"Your secret token (already in files):\n```{token}```",
                inline=False
            )
            
            embed.add_field(
                name="🚀 Step 3: Enable Monitoring",
                value="Run: `/livemonitor enable`",
                inline=False
            )

            embed.add_field(
                name="🌐 Step 4: Claim & Secure Dashboard",
                value=(
                    "Claim URL (one-time setup):\n"
                    f"`{url.rstrip('/')}/setup.php?setup_token={setup_token}`\n\n"
                    "Open this link in your browser, follow the on-screen guide to configure "
                    "Discord OAuth, then log in with your Discord account to lock the dashboard."
                ),
                inline=False
            )
            
            embed.add_field(
                name="📋 What’s Inside the Zip",
                value=(
                    "• `index.php` - Dashboard interface (Discord login protected)\\n"\
                    "• Bridge endpoints: `receive.php`, `get_commands.php`, `send_command.php`\\n"\
                    "• Security helpers: `setup.php`, `login.php`, `logout.php`, `oauth_callback.php`, `lm_db.php`, `lm_auth.php`, `lm_bootstrap.php`, `owner_audit.php`, `owner_roles.php`, `owner_db.php`, `backup_dashboard.php`\\n"\
                    "• Branding assets in `/assets` (icons, banner) so images load without extra setup.\\n"\
                ),
                inline=False
            )
            
            embed.set_footer(text="All files contain your security token. Keep them private!")
            
            if hasattr(ctx, 'send'):
                await msg.delete()
                await ctx.send(embed=embed, files=files)
            else:
                await msg.edit(embed=embed)
                await ctx.followup.send(files=files)
        
        elif action == "enable":
            if not self.config.get("website_url") or not self.config.get("secret_token"):
                embed = discord.Embed(
                    title="⚠️ Setup Required",
                    color=0xff0000,
                    description="Please run quick start first"
                )
                embed.add_field(
                    name="Command",
                    value="`/livemonitor quickstart <your_website_url>`",
                    inline=False
                )
                await (ctx.send(embed=embed) if hasattr(ctx, 'send') else ctx.response.send_message(embed=embed))
                return
            
            self.is_enabled = True
            self.config["enabled"] = True
            self._save_config()
            
            if not self.send_status_loop.is_running():
                self.send_status_loop.start()




            try:
                await self._sync_assets_to_server_once()
            except Exception as e:
                logger.error(f"Live Monitor: Asset sync on enable failed: {e}")
            
            embed = discord.Embed(
                title="✅ Live Monitor Enabled",
                color=0x00ff00,
                description="Bot is now sending data to your dashboard"
            )
            embed.add_field(
                name="Dashboard URL",
                value=f"{self.config['website_url']}/index.php",
                inline=False
            )
            embed.add_field(
                name="Update Interval",
                value=f"Every {self.config.get('update_interval', 5)} seconds",
                inline=False
            )
            
            await (ctx.send(embed=embed) if hasattr(ctx, 'send') else ctx.response.send_message(embed=embed))
        
        elif action == "disable":
            self.is_enabled = False
            self.config["enabled"] = False
            self._save_config()
            
            if self.send_status_loop.is_running():
                self.send_status_loop.cancel()
            
            embed = discord.Embed(
                title="⏸️ Live Monitor Disabled",
                color=0xff0000,
                description="Bot has stopped sending data"
            )
            
            await (ctx.send(embed=embed) if hasattr(ctx, 'send') else ctx.response.send_message(embed=embed))
        
        elif action == "files":
            if not self.config.get("secret_token"):
                embed = discord.Embed(
                    title="⚠️ Setup Required",
                    color=0xff0000,
                    description="Please run quick start first"
                )
                embed.add_field(
                    name="Command",
                    value="`/livemonitor quickstart <your_website_url>`",
                    inline=False
                )
                await (ctx.send(embed=embed) if hasattr(ctx, 'send') else ctx.response.send_message(embed=embed))
                return
            
            await (ctx.defer() if hasattr(ctx, 'defer') else ctx.response.defer())
            
            output_dir = Path("./live_monitor_website")
            output_dir.mkdir(exist_ok=True)
            
            token = self.config["secret_token"]
            setup_token = self.config.get("setup_token") or secrets.token_urlsafe(32)
            self.config["setup_token"] = setup_token
            self._save_config()


            (output_dir / "index.php").write_text(
                self._generate_index_php(token, self._get_default_prefix(), setup_token),
                encoding='utf-8'
            )
            (output_dir / "lm_bootstrap.php").write_text(
                self._generate_lm_bootstrap_php(token, setup_token), encoding='utf-8'
            )
            (output_dir / "lm_db.php").write_text(self._generate_lm_db_php(), encoding='utf-8')
            (output_dir / "lm_auth.php").write_text(self._generate_lm_auth_php(), encoding='utf-8')
            (output_dir / "setup.php").write_text(self._generate_setup_php(), encoding='utf-8')
            (output_dir / "login.php").write_text(self._generate_login_php(), encoding='utf-8')
            (output_dir / "oauth_callback.php").write_text(self._generate_oauth_callback_php(), encoding='utf-8')
            (output_dir / "logout.php").write_text(self._generate_logout_php(), encoding='utf-8')
            (output_dir / "owner_audit.php").write_text(self._generate_owner_audit_php(), encoding='utf-8')
            (output_dir / "owner_roles.php").write_text(self._generate_owner_roles_php(), encoding='utf-8')
            (output_dir / "owner_db.php").write_text(self._generate_owner_db_php(), encoding='utf-8')
            (output_dir / "backup_dashboard.php").write_text(self._generate_backup_dashboard_php(), encoding='utf-8')


            (output_dir / "receive.php").write_text(self._generate_receive_php(token), encoding='utf-8')
            (output_dir / "get_commands.php").write_text(self._generate_get_commands_php(token), encoding='utf-8')
            (output_dir / "send_command.php").write_text(self._generate_send_command_php(token), encoding='utf-8')



            self._copy_dashboard_assets(output_dir)
            
            archive_path = shutil.make_archive(str(output_dir), "zip", root_dir=output_dir)



            try:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_root = Path("./data/Dashboardbackups")
                backup_root.mkdir(parents=True, exist_ok=True)
                dash_backup = backup_root / f"web_dashboard_{ts}.zip"
                shutil.copy2(archive_path, dash_backup)
            except Exception as e:
                logger.error(f"Live Monitor: failed to copy dashboard files zip to ./data/Dashboardbackups: {e}")

            files = [
                discord.File(archive_path, filename="live_monitor_website.zip"),
            ]
            
            embed = discord.Embed(
                title="📁 Dashboard Files",
                color=0x3b82f6,
                description="Updated dashboard files packaged as a single zip archive."
            )
            
            embed.add_field(
                name="Upload Location",
                value=f"`{self.config['website_url']}`",
                inline=False
            )
            
            embed.add_field(
                name="Contents",
                value=(
                    "The `live_monitor_website.zip` contains all PHP files and the `assets` folder. "
                    "Extract it locally and upload everything inside to the path above."
                ),
                inline=False
            )
            
            if hasattr(ctx, 'send'):
                await ctx.send(embed=embed, files=files)
            else:
                await ctx.followup.send(embed=embed, files=files)
    
    def _generate_index_html(self, token: str) -> str:
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Live Monitor Dashboard</title>
    <link rel="icon" type="image/png" href="assets/zoryx-framework.png">
    <link rel="icon" type="image/x-icon" href="assets/zoryx-framework.ico">
    <link rel="shortcut icon" href="assets/zoryx-framework.ico">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #3b82f6;
            --secondary: #8b5cf6;
            --accent-cyan: #22d3ee;
            --accent-pink: #ec4899;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --bg-dark: #0a0e27;
            --bg-darker: #050814;
            --bg-card: rgba(26, 31, 58, 0.8);
            --bg-card-hover: rgba(51, 65, 85, 0.9);
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --border: rgba(59, 130, 246, 0.2);
            --glow: rgba(59, 130, 246, 0.4);
        }

        body.dragging {
            user-select: none;
            cursor: col-resize !important;
        }

        body.dragging * {
            cursor: col-resize !important;
        }

        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb {
            background: transparent;
            border-radius: 10px;
        }
        *:hover::-webkit-scrollbar-thumb { background: var(--gh-border); }

        .explorer-unit {
            width: 100%;
            max-width: 100%;
            height: 600px;
            display: flex;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 10px;
            overflow: hidden;
            position: relative;
        }
        #file-browser-content,
        #tab-files {
            width: 100%;
        }
        .file-pane {
            width: 100%;
            display: flex;
            flex-direction: column;
            background: #0d1117;
            transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
            min-width: 300px;
            z-index: 2;
        }

        .explorer-unit.editor-open .file-pane {
            flex-shrink: 0;
            border-right: 1px solid #30363d;
        }

        .dir-header {
            padding: 8px 16px;
            background: rgba(22, 27, 34, 0.6);
            border-bottom: 1px solid rgba(48, 54, 61, 0.8);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .breadcrumb {
            font-size: 11px;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(13, 17, 23, 0.8);
            border: 1px solid rgba(48, 54, 61, 0.8);
            border-radius: 6px;
            padding: 4px 10px;
        }
        
        .breadcrumb-icon {
            font-size: 14px;
            margin-right: 2px;
        }

        .breadcrumb .crumb {
            color: #58a6ff;
            cursor: pointer;
            transition: all 0.2s;
            padding: 1px 3px;
            border-radius: 3px;
        }

        .breadcrumb .crumb:hover {
            background: rgba(88, 166, 255, 0.1);
            text-decoration: none;
        }

        .breadcrumb span {
            color: #6e7681;
            font-weight: 400;
            font-size: 11px;
        }

        .view-controls {
            display: flex;
            border: 1px solid #30363d;
            border-radius: 6px;
            overflow: hidden;
        }

        .file-toolbar {
            position: relative;
            display: flex;
            align-items: center;
        }

        .file-toolbar-toggle {
            background: transparent;
            border: none;
            color: #8b949e;
            font-size: 18px;
            line-height: 1;
            padding: 4px 6px;
            cursor: pointer;
            border-radius: 4px;
        }

        .file-toolbar-toggle:hover {
            background: rgba(110, 118, 129, 0.2);
        }

        .file-toolbar-menu {
            position: absolute;
            right: 0;
            top: 32px;
            background: #161b22;
            border-radius: 8px;
            border: 1px solid #30363d;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
            padding: 4px 0;
            display: none;
            min-width: 180px;
            z-index: 30;
            flex-direction: column;
        }

        .file-toolbar-menu.open {
            display: flex;
        }

        .file-toolbar-menu .v-btn {
            width: 100%;
            border: none;
            border-radius: 0;
            text-align: left;
            justify-content: flex-start;
        }

        .view-btn {
            background: #21262d;
            border: none;
            color: #8b949e;
            padding: 6px 16px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            border-right: 1px solid #30363d;
            transition: all 0.2s ease;
        }
        
        .view-btn:last-child {
            border-right: none;
        }
        
        .view-btn:hover {
            background: #30363d;
            color: #c9d1d9;
        }
        
        .view-btn.active {
            background: #1e40af;
            color: #ffffff;
        }

        .v-btn {
            background: #21262d;
            border: none;
            color: #c9d1d9;
            padding: 4px 12px;
            font-size: 12px;
            cursor: pointer;
            border-right: 1px solid #30363d;
        }
        .v-btn:last-child { border-right: none; }
        .v-btn.active { background: #30363d; }

        .scroll-area { flex: 1; overflow-y: auto; padding: 0; }

        .file-grid { display: grid; }
        .file-grid.list-mode { grid-template-columns: 1fr; }
        .file-grid.grid-mode { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); padding: 16px; gap: 8px; }

        .list {
            max-height: 420px;
            overflow-y: auto;
        }

        .file-grid.loading {
            pointer-events: none;
            opacity: 0.6;
            position: relative;
        }

        .file-grid.loading::after {
            content: 'Loading...';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: var(--gh-dark);
            padding: 8px 16px;
            border-radius: 6px;
            border: 1px solid var(--gh-border);
            font-size: 14px;
            z-index: 10;
        }

        .file-row {
            padding: 8px 16px;
            border-bottom: 1px solid #21262d;
            display: flex;
            align-items: center;
            gap: 12px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.1s;
        }

        .grid-mode .file-row {
            flex-direction: column;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 16px;
            text-align: center;
        }

        .file-row:hover { background: #161b22; }
        .file-row.active { background: rgba(56, 139, 253, 0.1); }
        .file-row.folder { color: #58a6ff; font-weight: 500; }
        .file-name { color: #c9d1d9; }
        .file-meta { color: #8b949e; font-size: 12px; margin-left: auto; }
        .grid-mode .file-meta { margin-left: 0; }

        .resizer {
            width: 4px;
            cursor: col-resize;
            background: transparent;
            z-index: 10;
            display: none;
            transition: background 0.2s;
            user-select: none;
            flex-shrink: 0;
        }
        .explorer-unit.editor-open .resizer { display: block; }
        .resizer:hover { background: #58a6ff; }

        .editor-pane {
            display: none;
            flex-direction: column;
            background: rgba(22, 27, 34, 0.7);
            backdrop-filter: blur(25px);
            width: 0;
            overflow: hidden;
        }

        .explorer-unit.editor-open .editor-pane {
            display: flex !important;
            flex: 1 !important;
        }

        .editor-header {
            padding: 12px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #30363d;
            background: rgba(255,255,255,0.02);
        }

        .action-group { display: flex; gap: 8px; }

        .btn {
            height: 32px;
            padding: 0 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            border: 1px solid #30363d;
            background: #21262d;
            color: #c9d1d9;
            transition: all 0.2s ease;
        }

        .btn-save { background: #238636; border-color: rgba(255,255,255,0.1); color: white; }
        .btn:hover { border-color: #8b949e; }
        .btn:active {
            transform: scale(0.95);
        }

        textarea {
            flex: 1;
            background: transparent;
            border: none;
            color: #d1d5db;
            padding: 24px;
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
            font-size: 14px;
            line-height: 1.6;
            outline: none;
            resize: none;
            white-space: pre;
            overflow-wrap: normal;
            overflow-x: auto;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, var(--bg-dark) 0%, var(--bg-darker) 100%);
            color: var(--text-primary);
            line-height: 1.6;
            min-height: 100vh;
            overflow-x: hidden;
        }

        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: 
                radial-gradient(circle at 20% 50%, rgba(59, 130, 246, 0.1) 0%, transparent 50%),
                radial-gradient(circle at 80% 80%, rgba(139, 92, 246, 0.1) 0%, transparent 50%);
            pointer-events: none;
            z-index: 0;
        }

        .container {
            max-width: 1800px;
            margin: 0 auto;
            padding: 20px;
            position: relative;
            z-index: 1;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: stretch;
            margin-bottom: 24px;
            padding: 18px 20px;
            background:
                linear-gradient(135deg, rgba(15, 23, 42, 0.96), rgba(15, 23, 42, 0.92)),
                url('assets/banner.png') center/cover no-repeat;
            backdrop-filter: blur(20px);
            border-radius: 16px;
            border: 1px solid var(--border);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            gap: 16px;
        }

        .header h1 {
            font-size: 32px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--primary), var(--accent-cyan), var(--secondary));
            background-size: 200% auto;

            background-clip: text;
            -webkit-background-clip: text;

            color: transparent;
            -webkit-text-fill-color: transparent;

            animation: shimmer 3s linear infinite;
            margin: 0;
        }

        .header-left {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .header-title-row {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .brand-logo {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            flex-shrink: 0;
            box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.5);
            background: rgba(15, 23, 42, 0.9);
            object-fit: contain;
        }

        .header-subtitle {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.16em;
            color: var(--text-secondary);
        }

        .header-subtitle a {
            color: inherit;
        }

        .header-subtitle a:hover {
            color: #e5f3ff;
        }

        .header-meta {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
        }

        .header-status-group {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }

        .lm-user-pill {
            min-width: 0;
            display: flex;
            align-items: center;
            padding: 6px 10px;
            border-radius: 12px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            background:
                radial-gradient(circle at 0 0, rgba(56,189,248,0.22), transparent 60%),
                radial-gradient(circle at 100% 100%, rgba(59,130,246,0.16), transparent 55%),
                rgba(15,23,42,0.96);
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
            font-size: 11px;
            color: var(--text-secondary);
        }

        .lm-user-pill-inner {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .lm-user-pill-text {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .lm-user-logout-button {
            margin-left: 10px;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            background: rgba(15,23,42,0.95);
            color: var(--text-secondary);
            font-size: 11px;
            padding: 4px 10px;
            cursor: pointer;
            white-space: nowrap;
        }

        .lm-user-logout-button:hover {
            color: var(--text-primary);
            border-color: var(--primary);
        }

        .lm-user-pill-avatar {
            width: 20px;
            height: 20px;
            border-radius: 999px;
            overflow: hidden;
            flex-shrink: 0;
            background: #020617;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            color: #e5e7eb;
        }

        .lm-user-pill-avatar img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .lm-user-pill-name {
            font-weight: 600;
            color: var(--text-primary);
        }

        .lm-user-pill-role {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .header-info-button {
            border-radius: 999px;
            border: 1px solid var(--border);
            background: rgba(15, 23, 42, 0.9);
            color: var(--text-secondary);
            font-size: 11px;
            padding: 4px 10px;
            cursor: pointer;
        }

        .header-info-button:hover {
            color: var(--text-primary);
            border-color: var(--primary);
        }

        .header-stats {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }

        .header-stat {
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 10px 15px;
            background: rgba(59, 130, 246, 0.1);
            border-radius: 8px;
            border: 1px solid rgba(59, 130, 246, 0.2);
            min-width: 80px;
        }

        .header-stat .label {
            font-size: 11px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 4px;
        }

        .header-stat span:last-child {
            font-size: 18px;
            font-weight: 700;
            color: var(--text-primary);
        }

        @keyframes shimmer {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }

        .status-badge {
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }

        .status-healthy {
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(5, 150, 105, 0.3));
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.4);
        }

        .status-degraded {
            background: linear-gradient(135deg, rgba(245, 158, 11, 0.2), rgba(217, 119, 6, 0.3));
            color: var(--warning);
            border: 1px solid rgba(245, 158, 11, 0.4);
        }

        .guilds-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 12px;
        }

        .guild-card {
            border-radius: 14px;
            border: 1px solid rgba(30, 64, 175, 0.7);
            background:
                radial-gradient(circle at 0 0, rgba(56,189,248,0.18), transparent 55%),
                radial-gradient(circle at 100% 100%, rgba(59,130,246,0.16), transparent 55%),
                rgba(15,23,42,0.98);
            padding: 12px 14px;
            box-shadow: 0 14px 36px rgba(15,23,42,0.85);
        }

        .guild-card-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 8px;
        }

        .guild-card-name {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .guild-card-members {
            font-size: 12px;
            color: var(--text-secondary);
        }

        .guild-card-meta {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 6px 12px;
            font-size: 11px;
            margin-bottom: 10px;
        }

        .guild-card-meta-row {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .guild-meta-label {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-secondary);
            font-size: 10px;
        }

        .guild-meta-value {
            color: var(--text-primary);
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }

        .guild-meta-value.mono {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
            font-size: 10px;
        }

        .guild-card-actions {
            display: flex;
            justify-content: flex-end;
        }

        .db-table-card {
            border-radius: 12px;
            border: 1px solid var(--border);
            background: rgba(15,23,42,0.96);
            padding: 10px 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 8px;
        }

        .db-table-main {
            min-width: 0;
        }

        .db-table-name {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .db-table-meta {
            font-size: 11px;
            color: var(--text-secondary);
        }

        .db-rows-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }

        .db-rows-table th,
        .db-rows-table td {
            padding: 6px 8px;
            border-bottom: 1px solid rgba(30,41,59,0.9);
            text-align: left;
        }

.db-rows-table th {
            border-bottom-color: var(--border);
            font-weight: 600;
            color: var(--text-secondary);
            font-size: 11px;
        }

        .invite-card {
            width: 100%;
            max-width: 100%;
            min-height: 520px;
            border-radius: 20px;
            border: 2px solid rgba(59, 130, 246, 0.6);
            background:
                radial-gradient(circle at 10% 10%, rgba(37, 99, 235, 0.35), transparent 60%),
                radial-gradient(circle at 90% 90%, rgba(139, 92, 246, 0.30), transparent 60%),
                radial-gradient(circle at 50% 50%, rgba(59, 130, 246, 0.08), transparent 80%),
                linear-gradient(135deg, rgba(13, 17, 23, 0.98) 0%, rgba(17, 24, 39, 0.98) 100%);
            box-shadow: 
                0 0 80px rgba(59, 130, 246, 0.2),
                0 25px 60px rgba(15, 23, 42, 0.9),
                inset 0 1px 1px rgba(255, 255, 255, 0.1);
            position: relative;
            overflow: hidden;
        }

        .invite-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: linear-gradient(90deg, 
                transparent 0%, 
                rgba(59, 130, 246, 0.8) 20%, 
                rgba(139, 92, 246, 0.8) 80%, 
                transparent 100%);
        }

        .invite-card-header {
            border-bottom: 1px solid rgba(59, 130, 246, 0.3);
            background: linear-gradient(135deg, rgba(37, 99, 235, 0.05) 0%, rgba(139, 92, 246, 0.05) 100%);
            padding: 24px 28px;
        }

        .invite-card-body {
            padding: 28px;
        }

        .invite-output {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
            background: rgba(0, 0, 0, 0.3) !important;
            border: 1px solid rgba(59, 130, 246, 0.4) !important;
            color: #60a5fa !important;
        }

        .marketplace-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 16px;
            margin-top: 16px;
        }

        .marketplace-extension-card {
            background: linear-gradient(135deg, rgba(13, 17, 23, 0.98) 0%, rgba(17, 24, 39, 0.98) 100%);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 12px;
            padding: 18px;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .marketplace-extension-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent, rgba(59, 130, 246, 0.6), transparent);
        }

        .marketplace-extension-card:hover {
            border-color: rgba(59, 130, 246, 0.6);
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(59, 130, 246, 0.2);
        }

        .marketplace-ext-header {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 12px;
        }

        .marketplace-ext-icon {
            width: 48px;
            height: 48px;
            border-radius: 8px;
            object-fit: cover;
            border: 1px solid rgba(59, 130, 246, 0.3);
        }

        .marketplace-ext-info {
            flex: 1;
        }

        .marketplace-ext-title {
            font-size: 15px;
            font-weight: 600;
            color: #60a5fa;
            margin-bottom: 4px;
        }

        .marketplace-ext-version {
            font-size: 11px;
            color: var(--text-secondary);
        }

        .marketplace-ext-status {
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
        }

        .marketplace-status-working {
            background: rgba(34, 197, 94, 0.2);
            color: #22c55e;
            border: 1px solid rgba(34, 197, 94, 0.3);
        }

        .marketplace-status-beta {
            background: rgba(245, 158, 11, 0.2);
            color: #f59e0b;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }

        .marketplace-status-broken {
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .marketplace-ext-description {
            font-size: 12px;
            color: var(--text-secondary);
            margin: 12px 0;
            line-height: 1.5;
        }

        .marketplace-ext-banner {
            width: 100%;
            height: 120px;
            border-radius: 8px;
            object-fit: cover;
            margin-bottom: 12px;
            border: 1px solid rgba(59, 130, 246, 0.2);
        }

        .marketplace-ext-footer {
            display: flex;
            gap: 8px;
            margin-top: 12px;
        }

        .marketplace-ext-footer button {
            flex: 1;
        }

        .status-critical {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(220, 38, 38, 0.3));
            color: var(--danger);
            border: 1px solid rgba(239, 68, 68, 0.4);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .system-hero {
            display: grid;
            grid-template-columns: minmax(0, 2.2fr) minmax(0, 1.8fr);
            gap: 16px;
            margin-bottom: 24px;
        }

        .system-hero-main {
            padding: 12px 18px;
            border-radius: 16px;
            border: 1px solid var(--border);
            background:
                radial-gradient(circle at 0% 0%, rgba(59, 130, 246, 0.35), transparent 60%),
                radial-gradient(circle at 100% 100%, rgba(139, 92, 246, 0.25), transparent 60%),
                rgba(15, 23, 42, 0.9);
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
        }

        .system-hero-metric {
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-width: 0;
        }

        .system-hero-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-secondary);
            margin-bottom: 4px;
        }

        .system-hero-value {
            font-size: 22px;
            font-weight: 700;
            color: var(--text-primary);
            display: flex;
            align-items: baseline;
            gap: 4px;
        }

        .system-hero-unit {
            font-size: 14px;
            color: var(--text-secondary);
            font-weight: 500;
        }

        .system-hero-secondary {
            padding: 14px 16px;
            border-radius: 16px;
            border: 1px solid var(--border);
            background: rgba(15, 23, 42, 0.9);
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
        }

        .system-hero-pill {
            padding: 8px 10px;
            border-radius: 10px;
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(148, 163, 184, 0.4);
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .system-hero-pill-label {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-secondary);
        }

        .system-hero-pill-value {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
        }

        @media (max-width: 900px) {
            .system-hero {
                grid-template-columns: minmax(0, 1fr);
            }
        }

        .hero-info-panel {
            display: none;
            margin-bottom: 20px;
            padding: 10px 16px;
            border-radius: 12px;
            border: 1px solid var(--border);
            background: rgba(15, 23, 42, 0.9);
        }

        .hero-info-panel.visible {
            display: flex;
            flex-wrap: wrap;
            gap: 14px 24px;
        }

        .hero-info-row {
            display: flex;
            gap: 8px;
            font-size: 13px;
        }

        .hero-info-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-secondary);
        }

        .hero-info-value {
            font-weight: 600;
            color: var(--text-primary);
        }

        .stat {
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
            background: rgba(13, 17, 23, 0.6);
            border-radius: 8px;
            border: 1px solid rgba(59, 130, 246, 0.2);
            transition: all 0.2s ease;
        }

        .stat:hover {
            border-color: rgba(59, 130, 246, 0.4);
            background: rgba(13, 17, 23, 0.8);
        }

        .stat-card {
            background: var(--bg-card);
            backdrop-filter: blur(20px);
            padding: 24px;
            border-radius: 16px;
            border: 1px solid var(--border);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--primary), var(--accent-cyan));
            opacity: 0;
            transition: opacity 0.3s ease;
        }

        .stat-card:hover {
            transform: translateY(-4px);
            border-color: var(--primary);
            box-shadow: 0 12px 32px rgba(59, 130, 246, 0.2);
        }

        .stat-card:hover::before {
            opacity: 1;
        }

        .stat-label {
            font-size: 11px;
            color: #8b949e;
            font-weight: 500;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            text-align: center;
        }

        .stat-value {
            font-size: 32px;
            font-weight: 700;
            color: #60a5fa;
            line-height: 1;
        }

        .stat-unit {
            font-size: 18px;
            color: var(--text-secondary);
            font-weight: 400;
            margin-left: 4px;
        }

        .section {
            background: var(--bg-card);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            border: 1px solid var(--border);
            padding: 28px;
            margin-bottom: 24px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }

        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 18px;
            border-bottom: 1px solid var(--border);
        }

        .section-title {
            font-size: 22px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--primary), var(--accent-cyan));

            background-clip: text;
            -webkit-background-clip: text;

            color: transparent;
            -webkit-text-fill-color: transparent;
        }

        .tab-container {
            display: flex;
            gap: 10px;
            margin-bottom: 24px;
            border-bottom: 2px solid var(--border);
            padding-bottom: 4px;
            flex-wrap: wrap;
        }

        .tab {
            padding: 12px 28px;
            background: transparent;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            font-weight: 600;
            font-size: 14px;
            transition: all 0.3s ease;
            border-bottom: 3px solid transparent;
            position: relative;
        }

        .tab:hover {
            color: var(--text-primary);
            background: rgba(59, 130, 246, 0.1);
            border-radius: 8px 8px 0 0;
        }

        .tab.active {
            color: var(--primary);
            border-bottom-color: var(--primary);
            background: rgba(59, 130, 246, 0.15);
            border-radius: 8px 8px 0 0;
            box-shadow: 0 2px 12px rgba(59, 130, 246, 0.3);
        }

        /* Special highlight styling for the Credits tab */
        .tab.tab-credits {
            border-radius: 999px 999px 0 0;
            overflow: visible;
        }

        .tab.tab-credits::before {
            content: '';
            position: absolute;
            inset: -2px;
            border-radius: inherit;
            background: conic-gradient(from 180deg, #facc15, #fb923c, #f97316, #facc15);
            opacity: 0.35;
            filter: blur(6px);
            z-index: -1;
            pointer-events: none;
            transition: opacity 0.35s ease;
        }

        .tab.tab-credits.active::before {
            opacity: 0.7;
        }

        .tab-content {
            display: none;
            animation: fadeIn 0.4s ease;
        }

        .tab-content.active {
            display: block;
            width: 100%;
            min-width: 0;
        }
        .section {
            width: 100%;
        }
        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .card {
            background: rgba(30, 41, 59, 0.5);
            backdrop-filter: blur(10px);
            padding: 18px;
            border-radius: 12px;
            border: 1px solid var(--border);
            margin-bottom: 14px;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease, border-color 0.2s ease;
        }

        /* Layout helpers for two-column sections (Plugins & Extensions, etc.) */
        .two-column-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
            gap: 20px;
        }

        .column-card {
            background: rgba(15, 23, 42, 0.85);
            border-radius: 16px;
            border: 1px solid var(--border);
            padding: 20px;
            backdrop-filter: blur(18px);
        }

        .column-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }

        .column-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .column-subtitle {
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 2px;
        }

        /* Live Monitor main layout + grouped sidebar + drawer + palette */
        .lm-main-layout {
            margin-top: 12px;
            display: grid;
            grid-template-columns: 230px minmax(0, 1fr);
            gap: 18px;
            align-items: flex-start;
        }

        .lm-main-content {
            min-width: 0;
        }

        .lm-sidebar {
            border-radius: 16px;
            border: 1px solid rgba(31, 41, 55, 0.9);
            background: rgba(15, 23, 42, 0.98);
            padding: 10px 12px;
        }

        .lm-sidebar-group-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.16em;
            color: var(--text-secondary);
            margin: 8px 0 4px;
        }

        .lm-sidebar-item {
            width: 100%;
            border-radius: 9px;
            border: none;
            background: transparent;
            color: var(--text-secondary);
            padding: 7px 10px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            cursor: pointer;
            transition: background 0.18s ease, color 0.18s ease, transform 0.15s ease;
        }

        .lm-sidebar-item:hover {
            background: rgba(30, 64, 175, 0.4);
            color: var(--text-primary);
            transform: translateX(2px);
        }

        .lm-sidebar-item.lm-active {
            background: radial-gradient(circle at 0 0, rgba(37, 99, 235, 0.9), rgba(15, 23, 42, 1));
            color: #e5f3ff;
            box-shadow: 0 16px 36px rgba(15, 23, 42, 0.95);
        }

        .lm-nav-top-row {
            display: flex;
            justify-content: flex-end;
            gap: 8px;
            margin: 8px 0 4px;
        }

        .nav-palette-trigger,
        .lm-drawer-trigger {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 10px;
            border-radius: 8px;
            border: 1px solid rgba(31, 41, 55, 0.9);
            background: rgba(15, 23, 42, 0.98);
            font-size: 12px;
            cursor: pointer;
            color: var(--text-primary);
        }

        .nav-palette-trigger:hover,
        .lm-drawer-trigger:hover {
            border-color: rgba(59, 130, 246, 0.9);
            box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.5);
        }

        .nav-palette-trigger kbd {
            font-size: 10px;
            padding: 1px 4px;
            border-radius: 4px;
            background: rgba(17, 24, 39, 0.9);
            border: 1px solid rgba(55, 65, 81, 0.9);
            color: var(--text-secondary);
        }

        .lm-drawer-icon {
            font-size: 14px;
        }

        /* Command palette overlay (D10 style) */
        .lm-nav-palette-overlay {
            position: fixed;
            inset: 0;
            background: rgba(15, 23, 42, 0.78);
            backdrop-filter: blur(10px);
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.18s ease;
            z-index: 80;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .lm-nav-palette-overlay.lm-open {
            opacity: 1;
            pointer-events: auto;
        }

        .lm-nav-palette-dialog {
            width: min(640px, 100% - 40px);
            max-height: 70vh;
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            background: radial-gradient(circle at 0 0, rgba(30, 64, 175, 0.8), rgba(15, 23, 42, 0.98));
            box-shadow: 0 30px 80px rgba(0, 0, 0, 0.9);
            padding: 12px 14px 16px;
        }

        .lm-nav-palette-title {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 4px;
        }

        .lm-nav-palette-sub {
            font-size: 11px;
            color: var(--text-secondary);
            margin-bottom: 10px;
        }

        .lm-nav-palette-list {
            border-radius: 10px;
            border: 1px solid rgba(31, 41, 55, 0.9);
            background: rgba(15, 23, 42, 0.98);
            max-height: 42vh;
            overflow-y: auto;
        }

        .lm-nav-palette-item {
            width: 100%;
            border: none;
            background: transparent;
            color: var(--text-secondary);
            text-align: left;
            padding: 8px 10px;
            display: flex;
            justify-content: space-between;
            gap: 10px;
            font-size: 13px;
            cursor: pointer;
            transition: background 0.15s ease, color 0.15s ease;
        }

        .lm-nav-palette-item .lm-badge {
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 999px;
            border: 1px solid rgba(55, 65, 81, 0.9);
            color: var(--text-secondary);
        }

        .lm-nav-palette-item:hover {
            background: rgba(31, 41, 55, 0.95);
            color: var(--text-primary);
        }

        .lm-nav-palette-item.lm-active {
            background: radial-gradient(circle at 0 0, rgba(37, 99, 235, 0.9), rgba(15, 23, 42, 1));
            color: #e5f3ff;
        }

        /* Drawer nav (D8 style) */
        .lm-drawer-backdrop {
            position: fixed;
            inset: 0;
            background: rgba(15, 23, 42, 0.8);
            backdrop-filter: blur(6px);
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
            z-index: 60;
        }

        .lm-drawer {
            position: fixed;
            top: 0;
            left: 0;
            bottom: 0;
            width: 260px;
            transform: translateX(-100%);
            transition: transform 0.25s ease;
            z-index: 61;
            padding: 14px 12px;
            border-radius: 0 18px 18px 0;
            border-right: 1px solid rgba(148, 163, 184, 0.5);
            background: radial-gradient(circle at 0 0, rgba(30, 64, 175, 0.75), rgba(15, 23, 42, 0.98));
        }

        .lm-drawer-title {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 4px;
        }

        .lm-drawer-sub {
            font-size: 11px;
            color: var(--text-secondary);
            margin-bottom: 10px;
        }

        .lm-drawer-group-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.16em;
            color: var(--text-secondary);
            margin: 8px 0 4px;
        }

        .lm-drawer-item {
            width: 100%;
            border-radius: 9px;
            border: none;
            background: transparent;
            color: var(--text-secondary);
            padding: 7px 9px;
            font-size: 13px;
            text-align: left;
            cursor: pointer;
            transition: background 0.18s ease, color 0.18s ease;
        }

        .lm-drawer-item:hover {
            background: rgba(15, 23, 42, 0.97);
            color: var(--text-primary);
        }

        .lm-drawer-item.lm-active {
            background: radial-gradient(circle at 0 0, rgba(37, 99, 235, 0.95), rgba(15, 23, 42, 1));
            color: #e5f3ff;
        }

        body.lm-drawer-open .lm-drawer-backdrop {
            opacity: 1;
            pointer-events: auto;
        }

        body.lm-drawer-open .lm-drawer {
            transform: translateX(0);
        }

        /* Responsive: hide sidebar on small screens, hide drawer controls on desktop */
        @media (max-width: 900px) {
            .lm-main-layout {
                grid-template-columns: minmax(0, 1fr);
            }
            .lm-sidebar {
                display: none;
            }
        }

        @media (min-width: 901px) {
            .lm-drawer-trigger,
            #lm-drawer-backdrop,
            #lm-drawer-nav {
                display: none;
            }
        }

        /* Hide old horizontal tab bar visually, keep for compatibility */
        .tab-container {
            display: none;
        }

        .column-filters {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 12px;
        }

        .input-text {
            flex: 1 1 160px;
            min-width: 0;
            padding: 8px 10px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: rgba(15, 23, 42, 0.8);
            color: var(--text-primary);
            font-size: 13px;
        }

        .input-text::placeholder {
            color: var(--text-secondary);
        }

        .select {
            flex: 0 0 auto;
            padding: 8px 10px;
            border-radius: 8px;
            border: 1px solid var(--border);
            background: rgba(15, 23, 42, 0.8);
            color: var(--text-primary);
            font-size: 13px;
        }

        /* System tab layout */
        .system-grid {
            display: grid;
            grid-template-columns: minmax(0, 2fr) minmax(0, 2.2fr);
            gap: 20px;
            align-items: flex-start;
        }

        .system-main {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 20px;
        }

        .system-locks {
            min-height: 0;
        }

        @media (max-width: 1100px) {
            .system-grid {
                grid-template-columns: minmax(0, 1fr);
            }
        }

        /* Atomic File System lock table layout */
        .af-locks-header,
        .af-lock-row {
            display: grid;
            grid-template-columns: minmax(0, 4fr) minmax(0, 1.2fr) minmax(0, 1.5fr) minmax(0, 1.8fr) minmax(0, 2.4fr);
            gap: 8px;
            align-items: center;
        }

        .af-locks-header {
            font-size: 11px;
            text-transform: uppercase;
            color: var(--text-secondary);
            letter-spacing: 0.06em;
            border-bottom: 1px solid var(--border);
            padding-bottom: 6px;
            margin-bottom: 6px;
        }

        .af-lock-row {
            padding: 6px 0;
            border-bottom: 1px solid rgba(148, 163, 184, 0.25);
            font-size: 12px;
        }

        .af-lock-row:last-child {
            border-bottom: none;
        }

        .af-lock-path {
            font-family: monospace;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .af-lock-status-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 11px;
            border: 1px solid var(--border);
        }

        .af-lock-status-locked {
            background: rgba(239, 68, 68, 0.16);
            border-color: rgba(239, 68, 68, 0.4);
            color: var(--danger);
        }

        .af-lock-status-idle {
            background: rgba(34, 197, 94, 0.12);
            border-color: rgba(34, 197, 94, 0.35);
            color: var(--success);
        }

        .af-lock-actions {
            display: flex;
            gap: 6px;
            justify-content: flex-end;
            flex-wrap: wrap;
        }

        .af-lock-note {
            margin-top: 6px;
            font-size: 11px;
            color: var(--text-secondary);
        }

        .button-compact {
            padding: 6px 10px;
            font-size: 11px;
            box-shadow: none;
        }

        .file-drop-active {
            outline: 2px dashed rgba(59, 130, 246, 0.7);
            outline-offset: 4px;
        }
        
        .breadcrumb-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            margin-right: 6px;
        }
        
        .breadcrumb-icon svg {
            width: 16px;
            height: 16px;
            vertical-align: middle;
        }
        
        #file-context-menu {
            position: absolute;
            z-index: 2000;
            background: #020617;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 4px 0;
            min-width: 180px;
            box-shadow: 0 18px 45px rgba(15, 23, 42, 0.9);
            display: none;
        }

        #tab-files {
            position: relative;
        }

        .file-context-item {
            padding: 7px 14px;
            font-size: 13px;
            color: var(--text-primary);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 6px;
        }

        .file-context-item:hover {
            background: rgba(59, 130, 246, 0.18);
        }

        .file-context-item.danger {
            color: var(--danger);
        }

        .file-context-item.danger:hover {
            background: rgba(239, 68, 68, 0.16);
        }

        .card:hover {
            background: var(--bg-card-hover);
            border-color: var(--primary);
            transform: translateY(-2px);
            box-shadow: 0 8px 32px rgba(139, 92, 246, 0.2);
        }

        /* Dashboard overview cards: unify value text + clickable health card */
        #overview-stats .overview-stat-value {
            font-size: 14px;
            color: var(--text-secondary);
            margin-top: 4px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .stat-card-clickable {
            cursor: pointer;
            transition: background 0.18s ease, box-shadow 0.18s ease, transform 0.1s ease;
        }

        .stat-card-clickable:hover {
            background: rgba(148, 163, 184, 0.06);
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.65);
            transform: translateY(-1px);
        }

        /* SVG-based status chips used in header badge + Bot Health card */
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 4px 10px;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.45);
            background: radial-gradient(circle at 0 0, rgba(37, 99, 235, 0.4), rgba(15, 23, 42, 0.9));
            font-size: 12px;
        }

        .status-badge-caption {
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-weight: 600;
            color: var(--text-secondary);
        }

        .status-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .status-chip-icon {
            width: 14px;
            height: 14px;
            flex-shrink: 0;
        }

        .status-chip-label {
            font-size: 13px;
            font-weight: 600;
        }

        .status-chip-healthy .status-chip-label {
            color: #22c55e;
        }

        .status-chip-degraded .status-chip-label {
            color: #f59e0b;
        }

        .status-chip-critical .status-chip-label {
            color: #ef4444;
        }

        /* Simple JSON viewer for diagnostics modal */
        .code-block-json {
            background: rgba(15, 23, 42, 0.95);
            border-radius: 10px;
            border: 1px solid var(--border);
            padding: 12px 14px;
            font-family: 'JetBrains Mono', 'Courier New', monospace;
            font-size: 12px;
            max-height: 420px;
            overflow: auto;
            white-space: pre;
            line-height: 1.4;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }

        .card-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .card-subtitle {
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 6px;
        }

        .card-body {
            display: none;
            padding-top: 14px;
            border-top: 1px solid var(--border);
            margin-top: 14px;
        }

        .card.expanded .card-body {
            display: block;
        }

        .button {
            padding: 10px 20px;
            border-radius: 8px;
            border: none;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }

        .button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
        }

        .button:disabled,
        .button[disabled] {
            opacity: 0.5;
            cursor: not-allowed;
            pointer-events: none;
        }

        .button-primary {
            background: linear-gradient(135deg, var(--primary), var(--accent-cyan));
            color: white;
        }

        .button-primary:hover {
            box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
        }

        .button-danger {
            background: linear-gradient(135deg, var(--danger), #dc2626);
            color: white;
        }

        .button-danger:hover {
            box-shadow: 0 6px 20px rgba(239, 68, 68, 0.4);
        }

        .button-secondary {
            background: rgba(59, 130, 246, 0.15);
            color: var(--primary);
            border: 1px solid var(--primary);
        }

        .button-secondary:hover {
            background: rgba(59, 130, 246, 0.25);
        }

        .button-success {
            background: linear-gradient(135deg, var(--success), #059669);
            color: white;
        }

        .button-success:hover {
            box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4);
        }

        .badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .badge-success {
            background: rgba(16, 185, 129, 0.2);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .badge-warning {
            background: rgba(245, 158, 11, 0.2);
            color: var(--warning);
            border: 1px solid rgba(245, 158, 11, 0.3);
        }

        .badge-danger {
            background: rgba(239, 68, 68, 0.2);
            color: var(--danger);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .badge-info {
            background: rgba(59, 130, 246, 0.2);
            color: var(--primary);
            border: 1px solid rgba(59, 130, 246, 0.3);
        }

        .badge-secondary {
            background: rgba(139, 92, 246, 0.2);
            color: var(--secondary);
            border: 1px solid rgba(139, 92, 246, 0.3);
        }

        .progress-bar {
            width: 100%;
            height: 10px;
            background: rgba(59, 130, 246, 0.1);
            border-radius: 6px;
            overflow: hidden;
            margin-top: 10px;
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2);
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--primary), var(--accent-cyan));
            border-radius: 6px;
            transition: width 0.5s ease;
            box-shadow: 0 0 12px var(--glow);
        }

        .property {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(51, 65, 85, 0.5);
        }

        .property:last-child {
            border-bottom: none;
        }

        .property-label {
            color: var(--text-secondary);
            font-weight: 500;
        }

        .property-value {
            color: var(--text-primary);
            font-weight: 600;
        }

        .empty-state {
            text-align: center;
            padding: 50px;
            color: var(--text-secondary);
        }

        .loading {
            text-align: center;
            padding: 50px;
            color: var(--text-secondary);
        }

        .footer {
            text-align: center;
            padding: 24px;
            color: var(--text-secondary);
            font-size: 13px;
            margin-top: 30px;
        }

        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(8px);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }

        .modal.active {
            display: flex;
        }

        .modal-content {
            background: var(--bg-card);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            border: 1px solid var(--border);
            padding: 28px;
            max-width: 700px;
            width: 90%;
            max-height: 85vh;
            overflow-y: auto;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 18px;
            border-bottom: 1px solid var(--border);
        }

        .modal-title {
            font-size: 22px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--primary), var(--accent-cyan));

            background-clip: text;
            -webkit-background-clip: text;

            color: transparent;
            -webkit-text-fill-color: transparent;
        }

        .close-button {
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 28px;
            cursor: pointer;
            transition: all 0.3s ease;
            width: 36px;
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 8px;
        }

        .close-button:hover {
            color: var(--text-primary);
            background: rgba(239, 68, 68, 0.2);
        }

        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }

        ::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb {
            background: rgba(139, 92, 246, 0.5);
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: rgba(139, 92, 246, 0.7);
        }

        button:focus,
        input:focus,
        select:focus,
        textarea:focus {
            outline: 2px solid rgba(139, 92, 246, 0.6);
            outline-offset: 2px;
        }

        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
            }

            .lm-main-layout {
                grid-template-columns: minmax(0, 1fr);
            }

            .stats-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .two-column-grid,
            .system-grid {
                grid-template-columns: minmax(0, 1fr);
            }

            .explorer-unit {
                flex-direction: column;
                height: auto;
            }

            .explorer-unit .file-pane,
            .explorer-unit .editor-pane {
                min-height: 220px;
            }
        }

        /* Global link styling so dashboard links look polished */
        a {
            color: var(--accent-cyan);
            text-decoration: none;
            position: relative;
            font-weight: 500;
            transition: color 0.25s ease, text-shadow 0.25s ease;
        }

        a::after {
            content: '';
            position: absolute;
            left: 0;
            bottom: -2px;
            width: 100%;
            height: 2px;
            border-radius: 999px;
            background: linear-gradient(90deg, var(--primary), var(--accent-cyan));
            transform: scaleX(0);
            transform-origin: left;
            opacity: 0.7;
            transition: transform 0.25s ease;
        }

        a:hover {
            color: #e5f3ff;
            text-shadow: 0 0 8px rgba(34, 211, 238, 0.7);
        }

        a:hover::after {
            transform: scaleX(1);
        }

        .button-group {
            display: flex;
            gap: 8px;
            margin-top: 12px;
            flex-wrap: wrap;
        }

        .quick-actions-grid {
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
        }

        .quick-actions-column {
            flex: 1 1 240px;
            min-width: 0;
        }

        .quick-actions-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-secondary);
            margin-bottom: 4px;
        }

        .quick-actions-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .toggle-pill {
            position: relative;
            width: 40px;
            height: 20px;
            border-radius: 999px;
            border: 1px solid var(--border);
            background: rgba(15, 23, 42, 0.9);
            padding: 2px;
            display: inline-flex;
            align-items: center;
            cursor: pointer;
            transition: background 0.2s ease, border-color 0.2s ease;
        }

        .toggle-pill-knob {
            width: 16px;
            height: 16px;
            border-radius: 999px;
            background: #e5e7eb;
            transform: translateX(0);
            transition: transform 0.2s ease, background 0.2s ease;
        }

        .toggle-pill.on {
            background: rgba(16, 185, 129, 0.25);
            border-color: rgba(16, 185, 129, 0.7);
        }

        .toggle-pill.on .toggle-pill-knob {
            transform: translateX(18px);
            background: #bbf7d0;
        }

        .execution-history {
            max-height: 300px;
            overflow-y: auto;
            margin-top: 12px;
        }

        .history-item {
            background: rgba(15, 23, 42, 0.5);
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 8px;
            border-left: 3px solid var(--border);
        }

        .history-item.success {
            border-left-color: var(--success);
        }

        .history-item.failure {
            border-left-color: var(--danger);
        }

        .file-browser {
            background: rgba(15, 23, 42, 0.8);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid var(--border);
        }

        .file-browser-header {
            display: flex;
            flex-direction: column;
            gap: 15px;
            margin-bottom: 20px;
        }

        .file-browser-actions {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }

        .breadcrumb {
            font-family: 'Inter', monospace;
            font-size: 14px;
            color: var(--text-primary);
            background: rgba(59, 130, 246, 0.1);
            padding: 8px 12px;
            border-radius: 6px;
            border: 1px solid rgba(59, 130, 246, 0.2);
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }

        .breadcrumb-item {
            cursor: pointer;
            color: var(--primary);
            transition: color 0.2s ease;
        }

        .breadcrumb-item:hover {
            color: var(--accent-cyan);
        }

        .breadcrumb-separator {
            color: var(--text-secondary);
        }

        .path-actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .file-tree {
            font-family: 'Inter', monospace;
            font-size: 14px;
        }

        .file-item {
            display: flex;
            align-items: center;
            padding: 8px 12px;
            cursor: pointer;
            border-radius: 6px;
            transition: all 0.2s ease;
            margin-bottom: 2px;
        }

        .file-item:hover {
            background: rgba(59, 130, 246, 0.1);
        }

        .file-item.expanded {
            background: rgba(59, 130, 246, 0.15);
        }

        .file-icon {
            margin-right: 8px;
            font-size: 16px;
        }

        .file-name {
            flex: 1;
            color: var(--text-primary);
        }

        .file-size {
            color: var(--text-secondary);
            font-size: 12px;
        }

        .file-children {
            margin-left: 20px;
            border-left: 2px solid var(--border);
            padding-left: 10px;
            margin-top: 5px;
        }

        .terminal-modal .modal-content {
            max-width: 90vw;
            width: 90vw;
            max-height: 90vh;
        }

        .terminal-window {
            background: #1e1e1e;
            border-radius: 8px;
            padding: 20px;
            font-family: 'Courier New', monospace;
            color: #f8f8f2;
            position: relative;
            max-width: 95vw;
            max-height: 90vh;
        }

        .terminal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #333;
        }

        .terminal-title {
            font-weight: 600;
            color: #61dafb;
            font-size: 14px;
        }

        .terminal-controls {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .terminal-content {
            background: #1e1e1e;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 15px;
            max-height: 60vh;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 13px;
            line-height: 1.4;
            position: relative;
        }

        .terminal-content.with-lines {
            padding-left: 60px;
        }

        .line-numbers {
            position: absolute;
            left: 10px;
            top: 15px;
            color: #666;
            font-size: 12px;
            user-select: none;
            pointer-events: none;
        }

        .terminal-edit {
            background: #1e1e1e;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 15px;
            max-height: 60vh;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            color: #f8f8f2;
            resize: vertical;
            min-height: 200px;
            line-height: 1.4;
            white-space: pre;
            word-wrap: normal;
            overflow-wrap: normal;
        }

        .terminal-edit:focus {
            outline: none;
            border-color: var(--primary);
        }

        .code-editor {
            position: relative;
            background: #1e1e1e;
            border: 1px solid #333;
            border-radius: 4px;
            max-height: 60vh;
            overflow: hidden;
        }

        .code-editor .line-numbers {
            width: 50px;
            text-align: right;
            padding-right: 10px;
            border-right: 1px solid #333;
            background: #252526;
        }

        .code-editor textarea {
            margin-left: 60px;
            width: calc(100% - 60px);
            background: transparent;
            border: none;
            color: #f8f8f2;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.4;
            resize: none;
            outline: none;
            padding: 15px 15px 15px 0;
            min-height: 200px;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
    <div class="header-left">
                <div class="header-title-row">
                    <img src="assets/zoryx-framework.png" alt="Zoryx Framework" class="brand-logo">
                    <h1>Live Monitor Dashboard</h1>
                </div>
                <div class="header-subtitle">
                    <a href="https://github.com/TheHolyOneZ/discord-bot-framework" target="_blank" rel="noopener noreferrer">
                        Zoryx Discord Bot Framework
                    </a>
                </div>
                <div class="header-meta">
                    <div class="header-status-group">
                        <div id="status-badge" class="status-badge">Loading...</div>
                        <button id="hero-info-button" class="header-info-button" onclick="toggleHeroInfo()">Details</button>
                    </div>
                    <div id="lm-user-pill" class="lm-user-pill"></div>
                </div>
            </div>
            <div class="system-hero-main">
                <div class="system-hero-metric">
                    <div class="system-hero-label">CPU</div>
                    <div class="system-hero-value"><span id="cpu-value">0</span><span class="system-hero-unit">%</span></div>
                </div>
                <div class="system-hero-metric">
                    <div class="system-hero-label">Memory</div>
                    <div class="system-hero-value" id="memory-value">0 MB</div>
                </div>
                <div class="system-hero-metric">
                    <div class="system-hero-label">Latency</div>
                    <div class="system-hero-value"><span id="latency-value">0</span><span class="system-hero-unit">ms</span></div>
                </div>
            </div>
        </div>

        <div id="hero-info-panel" class="hero-info-panel">
            <div class="hero-info-row">
                <span class="hero-info-label">Guilds</span>
                <span class="hero-info-value" id="guilds-value">0</span>
            </div>
            <div class="hero-info-row">
                <span class="hero-info-label">Users</span>
                <span class="hero-info-value" id="users-value">0</span>
            </div>
            <div class="hero-info-row">
                <span class="hero-info-label">Uptime</span>
                <span class="hero-info-value" id="uptime-value">0s</span>
            </div>
        </div>

        <div id="loading" class="loading">
            <p>Loading data from bot...</p>
        </div>

        <div id="content" style="display: none;">

            <div class="lm-nav-top-row">
                <button class="nav-palette-trigger" id="lm-nav-palette-trigger">
                    <span>Open Navigation</span>
                    <kbd>Ctrl</kbd><kbd>K</kbd>
                </button>
                <button class="lm-drawer-trigger" id="lm-drawer-trigger">
                    <span class="lm-drawer-icon">☰</span>
                    <span>Navigation</span>
                </button>
            </div>

                <div class="lm-main-layout">
                <aside class="lm-sidebar" id="lm-sidebar-nav">
                    <div class="lm-sidebar-group-label">Core</div>
                    <button class="lm-sidebar-item" data-tab="dashboard">Dashboard</button>
                    <button class="lm-sidebar-item" data-tab="commands">Commands</button>
                    <button class="lm-sidebar-item" data-tab="plugins">Plugins &amp; Extensions</button>
                    <button class="lm-sidebar-item" data-tab="hooks">Event Hooks</button>
                    <button class="lm-sidebar-item" data-tab="filesystem">File System</button>
                    <button class="lm-sidebar-item" data-tab="system">System</button>

                    <div class="lm-sidebar-group-label">Tools</div>
                    <button class="lm-sidebar-item" data-tab="files">File Browser</button>
                    <button class="lm-sidebar-item" data-tab="chat">Chat Console</button>
                    <button class="lm-sidebar-item" data-tab="guilds">Guilds / Servers</button>
                    <button class="lm-sidebar-item" data-tab="events">Events</button>
                    <button class="lm-sidebar-item" data-tab="invite">Bot Invite Helper</button>
                    <button class="lm-sidebar-item" data-tab="marketplace">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:8px;display:inline-block;vertical-align:middle;">
                            <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
                        </svg>
                        Extension Marketplace <span style="font-size:10px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);padding:2px 6px;border-radius:4px;margin-left:6px;">BETA</span></button>

                    <div class="lm-sidebar-group-label">Admin</div>
                    <button class="lm-sidebar-item" data-tab="roles">Roles &amp; Access</button>
                    <button class="lm-sidebar-item" data-tab="security">Security &amp; Logs</button>
                    <button class="lm-sidebar-item" data-tab="database">Database</button>

                    <div class="lm-sidebar-group-label">Meta</div>
                    <button class="lm-sidebar-item" data-tab="credits">Credits 👑</button>
                </aside>

                <div class="lm-main-content">
                    <div class="section">
                        <div class="tab-container">
                    <button class="tab active" onclick="switchTab('dashboard')">Dashboard</button>
                    <button class="tab" onclick="switchTab('commands')">Commands</button>
                    <button class="tab" onclick="switchTab('plugins')">Plugins & Extensions</button>
                    <button class="tab" onclick="switchTab('hooks')">Event Hooks</button>
                    <button class="tab" onclick="switchTab('filesystem')">File System</button>
                    <button class="tab" onclick="switchTab('files')">File Browser</button>
                    <button class="tab" onclick="switchTab('chat')">Chat Console (EXPERIMENTAL)</button>
                    <button class="tab" onclick="switchTab('guilds')">Guilds / Servers</button>
                    <button class="tab" onclick="switchTab('events')">Events</button>
                    <button class="tab" onclick="switchTab('system')">System</button>
                    <button class="tab" onclick="switchTab('invite')">Bot Invite Helper</button>
                    <button class="tab" onclick="switchTab('database')">Database</button>
                    <button class="tab" onclick="switchTab('roles')">Roles &amp; Access</button>
                    <button class="tab" onclick="switchTab('security')">Security &amp; Logs</button>
                    <button class="tab tab-credits" onclick="switchTab('credits')">
                        <span style="display:inline-flex;align-items:center;gap:8px;">
                            <span style="width:18px;height:18px;display:inline-flex;align-items:center;justify-content:center;">
                                <svg viewBox="0 0 24 24" aria-hidden="true">
                                    <defs>
                                        <linearGradient id="credfits-crown-gradient" x1="0" y1="0" x2="1" y2="1">
                                            <stop offset="0%" stop-color="#facc15">
                                                <animate attributeName="stop-color" values="#facc15;#fb923c;#facc15" dur="4s" repeatCount="indefinite" />
                                            </stop>
                                            <stop offset="100%" stop-color="#fb923c">
                                                <animate attributeName="stop-color" values="#fb923c;#f97316;#fb923c" dur="4s" repeatCount="indefinite" />
                                            </stop>
                                        </linearGradient>
                                    </defs>
                                    <path fill="url(#credfits-crown-gradient)" d="M4 18h16l-1.5-9-4 3-2.5-6-2.5 6-4-3L4 18z" />
                                    <circle cx="6" cy="7" r="1.4" fill="#facc15">
                                        <animate attributeName="r" values="1.4;1.7;1.4" dur="2.6s" repeatCount="indefinite" />
                                    </circle>
                                    <circle cx="12" cy="5" r="1.4" fill="#facc15">
                                        <animate attributeName="r" values="1.4;1.9;1.4" dur="2.2s" repeatCount="indefinite" />
                                    </circle>
                                    <circle cx="18" cy="7" r="1.4" fill="#facc15">
                                        <animate attributeName="r" values="1.4;1.7;1.4" dur="2.9s" repeatCount="indefinite" />
                                    </circle>
                                </svg>
                            </span>
                            <span>Credits</span>
                        </span>
                    </button>
                </div>

                <div id="tab-dashboard" class="tab-content active">
                    <div class="section-header">
                        <div class="section-title">Dashboard Overview</div>
                        <button class="button button-secondary" id="tour-trigger">Quick Tour</button>
                    </div>

                    <div id="alerts-bar"></div>

                    <div class="stats-grid" id="overview-stats">
                        <div class="stat-card stat-card-clickable" onclick="openDiagnosticsModal()">
                            <div class="stat-label">Bot Health</div>
                            <div class="overview-stat-value" id="overview-health-text">Checking...</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Uptime &amp; Reach</div>
                            <div class="overview-stat-value" id="overview-uptime-guilds">--</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Activity Snapshot</div>
                            <div class="overview-stat-value" id="overview-activity">--</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Framework</div>
                            <div class="overview-stat-value" id="overview-framework">Version: --</div>
                        </div>
                    </div>

                    <div class="two-column-grid">
                        <div class="column-card">
                            <div class="column-header">
                                <div>
                                    <div class="column-title">Alerts</div>
                                    <div class="column-subtitle">Key things you should know right now</div>
                                </div>
                            </div>
                            <div id="overview-alert-list" class="list" style="padding:12px;"></div>
                        </div>
                        <div class="column-card">
                            <div class="column-header">
                                <div>
                                    <div class="column-title">Quick Actions</div>
                                    <div class="column-subtitle">Common operations for operators</div>
                                </div>
                            </div>
                            <div class="quick-actions-grid">
                                <div class="quick-actions-column">
                                    <div class="quick-actions-label">Lifecycle</div>
                                    <div class="quick-actions-row">
                                        <button class="button button-danger" onclick="confirmShutdownBot()">Shutdown Bot</button>
                                    </div>
                                    <div style="font-size:11px;color:var(--text-secondary);margin-top:6px;">
                                        Shutdown will cleanly close the bot process. Restart it again using your hosting panel or process manager.
                                    </div>
                                </div>
                                <div class="quick-actions-column">
                                    <div class="quick-actions-label">Diagnostics &amp; Files</div>
                                    <div class="quick-actions-row">
                                        <button class="button button-secondary" onclick="sendCommand('clear_cache', {})">Clear Cache</button>
                                        <button class="button button-secondary" onclick="switchTab('filesystem')">View File System</button>
                                        <button class="button button-secondary" onclick="openMainConfig()">Open config.json</button>
                                        <button class="button button-secondary" onclick="openLiveMonitorConfig()">Open live_monitor_config.json</button>
                                        <button class="button button-secondary" onclick="window.location='backup_dashboard.php'">Download dashboard backup</button>
                                        <button class="button button-secondary" onclick="requestBotBackup()">Backup bot directory</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div id="tab-commands" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">Commands Overview</div>
                            <button class="header-info-button" onclick="openSectionHelp('commands')">?</button>
                        </div>
                        <button class="button button-secondary" onclick="refreshCommands()">Refresh</button>
                    </div>
                    
                    <div class="card" style="margin-bottom: 20px;">
                        <div class="card-header">
                            <div class="card-title">System Metrics</div>
                        </div>
                        <div class="stats-grid">
                            <div class="stat">
                                <span class="stat-label">Total Commands</span>
                                <span class="stat-value" id="cmd-total">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Slash Commands</span>
                                <span class="stat-value" id="cmd-slash">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Prefix Commands</span>
                                <span class="stat-value" id="cmd-prefix">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Hybrid Commands</span>
                                <span class="stat-value" id="cmd-hybrid">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Total Cogs</span>
                                <span class="stat-value" id="cmd-cogs">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Total Usage</span>
                                <span class="stat-value" id="cmd-usage">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Total Errors</span>
                                <span class="stat-value" id="cmd-errors">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Success Rate</span>
                                <span class="stat-value" id="cmd-success">100%</span>
                            </div>
                        </div>
                    </div>

                    <div class="explorer-unit">
                        <div class="file-pane" style="width: 100%; max-width: 100%;">
                            <div class="dir-header">
                                <div class="breadcrumb">
                                    <span class="crumb">Registered Commands</span>
                                </div>
                                <div class="view-controls">
                                    <button class="view-btn active" data-view="all">All</button>
                                    <button class="view-btn" data-view="slash">Slash</button>
                                    <button class="view-btn" data-view="prefix">Prefix</button>
                                    <button class="view-btn" data-view="hybrid">Hybrid</button>
                                </div>
                            </div>
                            
                            <div class="dir-header" style="border-top: none;">
                                <input
                                    id="cmd-search"
                                    class="input-text"
                                    type="text"
                                    placeholder="Search by name, description, or cog..."
                                    style="flex: 1; margin-right: 12px;"
                                />
                                <select id="cmd-sort" class="select">
                                    <option value="name">Sort by Name</option>
                                    <option value="usage">Sort by Usage</option>
                                    <option value="errors">Sort by Errors</option>
                                    <option value="cog">Sort by Cog</option>
                                </select>
                            </div>

                            <div class="list" id="commands-list" style="padding: 12px;"></div>
                        </div>
                    </div>
                </div>

                <div id="tab-plugins" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">Plugins &amp; Extensions</div>
                            <button class="header-info-button" onclick="openSectionHelp('plugins')">?</button>
                        </div>
                        <button class="button button-secondary" onclick="refreshPlugins()">Refresh</button>
                    </div>

                    <div class="card" id="plugins-stats-card" style="margin-bottom: 20px;">
                        <div class="card-header" style="justify-content: space-between; align-items: center;">
                            <div>
                                <div class="card-title">System Overview</div>
                                <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
                                    Summary of plugin and extension health. Toggle this on when you need a quick snapshot.
                                </div>
                            </div>
                            <div style="display:flex;align-items:center;gap:8px;">
                                <span style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.08em;">Show Stats</span>
                                <button type="button" class="toggle-pill" id="plugins-stats-toggle" aria-pressed="false" aria-label="Toggle plugin stats overview">
                                    <span class="toggle-pill-knob"></span>
                                </button>
                            </div>
                        </div>
                        <div class="stats-grid" id="plugins-stats-body">
                            <div class="stat">
                                <span class="stat-label">Total Plugins</span>
                                <span class="stat-value" id="total-plugins">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Loaded</span>
                                <span class="stat-value" id="loaded-plugins">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Healthy</span>
                                <span class="stat-value" id="healthy-plugins">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">With Issues</span>
                                <span class="stat-value" id="issues-plugins">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Total Commands</span>
                                <span class="stat-value" id="total-commands">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Total Cogs</span>
                                <span class="stat-value" id="total-cogs">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Available Extensions</span>
                                <span class="stat-value" id="total-extensions">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Avg Load Time</span>
                                <span class="stat-value" id="avg-load-time">0ms</span>
                            </div>
                        </div>
                    </div>

                    <div class="card" id="plugins-promo-card" style="margin-bottom: 20px; cursor: default;">
                        <div class="card-header">
                            <div>
                                <div class="card-title">Discover More Extensions</div>
                                <div class="card-subtitle">Browse the official ZygnalBot Extension Portal for additional extensions and plugins.</div>
                            </div>
                            <div style="display:flex;gap:10px;flex-wrap:wrap;">
                                <a href="https://zygnalbot.com/extension/" target="_blank" rel="noreferrer noopener" class="button button-primary" style="text-decoration:none;display:inline-flex;align-items:center;gap:6px;">
                                    <span>Open Extension Portal</span>
                                </a>
                                <button class="button button-secondary" onclick="switchTab('marketplace')" style="display:inline-flex;align-items:center;gap:6px;">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline-block;vertical-align:middle;">
                                        <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
                                    </svg>
                                    <span>Try Beta Marketplace</span>
                                </button>
                            </div>
                        </div>
                    </div>

                    <div class="explorer-unit">
                        <div class="file-pane" style="width: 100%; max-width: 100%;">
                            <div class="dir-header">
                                <div class="breadcrumb">
                                    <span class="crumb">Plugins & Extensions</span>
                                </div>
                                <div class="view-controls">
                                    <button class="view-btn active" data-view="plugins">Plugins & Extensions</button>
                                </div>
                            </div>
                            
                            <div class="dir-header" style="border-top: none;">
                                <input
                                    id="plugin-search"
                                    class="input-text"
                                    type="text"
                                    placeholder="Search by name, description, or command..."
                                    style="flex: 1; margin-right: 12px;"
                                />
                                <select id="plugin-filter" class="select">
                                    <option value="all">All</option>
                                    <option value="loaded">Loaded Only</option>
                                    <option value="not_loaded">Not Loaded Only</option>
                                    <option value="healthy">Healthy Only</option>
                                    <option value="issues">With Issues</option>
                                </select>
                            </div>

                            <div class="list" id="plugins-extensions-list" style="padding: 12px;"></div>
                        </div>
                    </div>
                </div>

                <div id="tab-hooks" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">Event Hooks System</div>
                            <button class="header-info-button" onclick="openSectionHelp('hooks')">?</button>
                        </div>
                        <button class="button button-secondary" onclick="refreshHooks()">Refresh</button>
                    </div>
                    
                    <div class="card" style="margin-bottom: 20px;">
                        <div class="card-header">
                            <div class="card-title">System Metrics</div>
                        </div>
                        <div class="stats-grid">
                            <div class="stat">
                                <span class="stat-label">Total Emissions</span>
                                <span class="stat-value" id="hooks-emissions">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Total Executions</span>
                                <span class="stat-value" id="hooks-executions">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Total Failures</span>
                                <span class="stat-value" id="hooks-failures">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Queue Size</span>
                                <span class="stat-value" id="hooks-queue-size">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Queue Full Count</span>
                                <span class="stat-value" id="hooks-queue-full">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Worker Restarts</span>
                                <span class="stat-value" id="hooks-worker-restarts">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Disabled Hooks</span>
                                <span class="stat-value" id="hooks-disabled">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Circuit Open</span>
                                <span class="stat-value" id="hooks-circuit-open">0</span>
                            </div>
                        </div>
                    </div>

                    <div class="explorer-unit">
                        <div class="file-pane" style="width: 100%; max-width: 100%;">
                            <div class="dir-header">
                                <div class="breadcrumb">
                                    <span class="crumb">Registered Event Hooks</span>
                                </div>
                                <div class="view-controls">
                                    <button class="view-btn active" data-view="all">All Hooks</button>
                                    <button class="view-btn" data-view="active">Active</button>
                                    <button class="view-btn" data-view="disabled">Disabled</button>
                                    <button class="view-btn" data-view="issues">With Issues</button>
                                </div>
                            </div>
                            
                            <div class="dir-header" style="border-top: none;">
                                <input
                                    id="hooks-search"
                                    class="input-text"
                                    type="text"
                                    placeholder="Search by event name or callback..."
                                    style="flex: 1; margin-right: 12px;"
                                />
                                <select id="hooks-sort" class="select">
                                    <option value="priority">Sort by Priority</option>
                                    <option value="executions">Sort by Executions</option>
                                    <option value="failures">Sort by Failures</option>
                                    <option value="time">Sort by Avg Time</option>
                                </select>
                            </div>

                            <div class="list" id="hooks-list" style="padding: 12px;"></div>
                        </div>
                    </div>
                </div>

                <div id="tab-filesystem" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">File System Overview</div>
                            <button class="header-info-button" onclick="openSectionHelp('filesystem')">?</button>
                        </div>
                        <button class="button button-secondary" onclick="refreshFileSystem()">Refresh</button>
                    </div>
                    
                    <div class="card" style="margin-bottom: 20px;">
                        <div class="card-header">
                            <div class="card-title">System Metrics</div>
                        </div>
                        <div class="stats-grid">
                            <div class="stat">
                                <span class="stat-label">Total Files</span>
                                <span class="stat-value" id="fs-total-files">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Total Size</span>
                                <span class="stat-value" id="fs-total-size">0 MB</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Data Dir Files</span>
                                <span class="stat-value" id="fs-data-files">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Cogs Dir Files</span>
                                <span class="stat-value" id="fs-cogs-files">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Extensions Files</span>
                                <span class="stat-value" id="fs-ext-files">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Botlogs Files</span>
                                <span class="stat-value" id="fs-logs-files">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Cache Hits</span>
                                <span class="stat-value" id="fs-cache-hits">0</span>
                            </div>
                            <div class="stat">
                                <span class="stat-label">Cache Misses</span>
                                <span class="stat-value" id="fs-cache-misses">0</span>
                            </div>
                        </div>
                    </div>

                    <div class="explorer-unit">
                        <div class="file-pane" style="width: 100%; max-width: 100%;">
                            <div class="dir-header">
                                <div class="breadcrumb">
                                    <span class="crumb">Directory Statistics</span>
                                </div>
                            </div>

                            <div class="list" id="filesystem-content" style="padding: 12px;"></div>
                        </div>
                    </div>
                </div>

                <div id="tab-files" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">File Browser</div>
                            <button class="header-info-button" onclick="openSectionHelp('files')">?</button>
                        </div>
                    </div>
                    <div id="file-browser-content">
                        <div class="explorer-unit">
                            <div class="file-pane" id="pane">
                                <div class="dir-header">
                                    <div class="breadcrumb" id="breadcrumb"></div>
                                    <div class="file-toolbar">
                                        <button class="file-toolbar-toggle" id="file-toolbar-toggle" aria-label="File actions" aria-haspopup="true" aria-expanded="false">⋮</button>
                                        <div class="file-toolbar-menu" id="file-toolbar-menu">
                                            <button class="v-btn" onclick="refreshFileBrowser()">Refresh</button>
                                            <button class="v-btn" onclick="createNewFile()">New File</button>
                                            <button class="v-btn" onclick="createNewFolder()">New Folder</button>
                                            <hr style="border:none;border-top:1px solid #30363d;margin:4px 0;" />
                                            <button class="v-btn active" onclick="setView('list', this)">List view</button>
                                            <button class="v-btn" onclick="setView('grid', this)">Grid view</button>
                                        </div>
                                    </div>
                                </div>
                                <div class="scroll-area"><div class="file-grid list-mode" id="list"></div></div>
                            </div>
                            <div class="resizer" id="resize"></div>
                            <div class="editor-pane">
                                <div class="editor-header">
                                    <span id="fileName" style="font-size:11px; font-weight:600">file.ts</span>
                                    <div class="action-group">
                                        <button class="btn" onclick="jumpEditorScroll()">Jump to Bottom</button>
                                        <button class="btn" onclick="closeEditor()">Close</button>
                                        <button class="btn" onclick="promptRenameCurrentFile()">Rename</button>
                                        <button class="btn btn-save" onclick="save()">Save</button>
                                    </div>
                                </div>
                                <textarea id="fileContent"></textarea>
                            </div>
                        </div>
                    </div>
                    <div id="file-context-menu">
                        <div class="file-context-item" onclick="contextRename()">Rename</div>
                        <div class="file-context-item" onclick="contextMove()">Move</div>
                        <div class="file-context-item danger" onclick="contextDelete()">Delete</div>
                    </div>
                </div>

                <div id="tab-chat" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">Chat Console (EXPERIMENTAL)</div>
                            <button class="header-info-button" onclick="openSectionHelp('chat')">?</button>
                        </div>
                    </div>
                    <div class="two-column-grid" id="chat-console">
                        <div class="column-card">
                            <div class="column-header">
                                <div>
                                    <div class="column-title">Servers</div>
                                    <div class="column-subtitle">Select a server to see its text channels</div>
                                </div>
                            </div>
                            <div id="chat-guilds" class="list" style="padding: 12px;"></div>
                        </div>
                        <div class="column-card">
                            <div class="column-header">
                                <div>
                                    <div class="column-title">Channel & Conversation</div>
                                    <div class="column-subtitle" id="chat-channel-subtitle">No channel selected</div>
                                </div>
                            </div>
                            <div class="list" style="padding: 12px; max-height: 260px; overflow-y: auto;" id="chat-channels"></div>
                            <div style="margin-top: 16px;">
                                <div id="chat-message-log" style="height: 200px; overflow-y: auto; border: 1px solid var(--border); border-radius: 8px; padding: 10px; background: rgba(15,23,42,0.9);"></div>
                                <div style="margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap;">
                                    <input id="chat-message-input" class="input-text" type="text" placeholder="Type a message to send as the bot..." style="flex: 1; min-width: 180px;" />
                                    <button class="button button-primary" onclick="sendChatMessage()">Send</button>
                                    <button class="button" onclick="requestChatHistory()">Request chat data (BETA)</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div id="tab-guilds" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">Guilds / Servers</div>
                            <button class="header-info-button" onclick="openSectionHelp('guilds')">?</button>
                        </div>
                    </div>
                    <div class="card" style="cursor: default;">
                        <div class="card-header">
                            <div class="card-title">Current Servers</div>
                            <div class="card-subtitle">Overview of guilds the bot is currently in.</div>
                        </div>
                        <div class="card-body" style="display:block;">
                            <div id="guilds-list" class="guilds-grid">
                                <div class="loading">Loading...</div>
                            </div>
                        </div>
                    </div>
                </div>

                <div id="tab-events" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">Recent Events</div>
                            <button class="header-info-button" onclick="openSectionHelp('events')">?</button>
                        </div>
                        <div id="events-count">0 Events</div>
                    </div>
                    <div id="events-list"></div>
                </div>

                <div id="tab-system" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">System Details</div>
                            <button class="header-info-button" onclick="openSectionHelp('system')">?</button>
                        </div>
                    </div>
                    <div id="system-details"></div>
                </div>

                <div id="tab-invite" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">Bot Invite Helper</div>
                            <button class="header-info-button" onclick="openSectionHelp('invite')">?</button>
                        </div>
                    </div>
                    <div class="card invite-card">
                        <div class="card-header invite-card-header" style="align-items:flex-start;">
                            <div>
                                <div class="card-title">Generate a Discord bot invite link</div>
                                <div class="card-subtitle">
                                    Quickly build a correct OAuth2 invite URL for your bot. For advanced settings (redirects, more scopes, whitelists, etc.) use the official Discord Developer Portal for your application.
                                </div>
                            </div>
                            <a href="https://discord.com/developers/applications" target="_blank" rel="noreferrer noopener" class="button button-secondary button-compact" style="text-decoration:none;">
                                Open Developer Portal
                            </a>
                        </div>
                        <div class="card-body invite-card-body" style="display:block;">
                            <div class="property-group" style="margin-bottom:24px;display:grid;gap:20px;">
                                <div class="property" style="display:flex;flex-direction:column;gap:10px;">
                                    <span class="property-label" style="font-size:14px;font-weight:600;color:#60a5fa;">Application / Client ID</span>
                                    <input id="invite-app-id" class="input-text" type="text" placeholder="Enter your bot application's client ID (numeric)" style="width:100%;font-size:14px;padding:14px 18px;border-radius:10px;background:rgba(0,0,0,0.3);border:1px solid rgba(59,130,246,0.3);transition:all 0.2s ease;" />
                                </div>
                                <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
                                    <div class="property" style="display:flex;flex-direction:column;gap:10px;">
                                        <span class="property-label" style="font-size:14px;font-weight:600;color:#60a5fa;">OAuth2 Scopes</span>
                                        <div style="display:flex;flex-direction:column;gap:10px;padding:16px;background:rgba(0,0,0,0.2);border-radius:10px;border:1px solid rgba(59,130,246,0.2);">
                                            <label style="display:flex;align-items:center;gap:10px;font-size:14px;cursor:pointer;padding:8px;border-radius:6px;transition:background 0.2s ease;" onmouseover="this.style.background='rgba(59,130,246,0.1)'" onmouseout="this.style.background='transparent'">
                                                <input id="invite-scope-bot" type="checkbox" checked style="width:18px;height:18px;cursor:pointer;" /> <span style="font-weight:500;">bot</span>
                                            </label>
                                            <label style="display:flex;align-items:center;gap:10px;font-size:14px;cursor:pointer;padding:8px;border-radius:6px;transition:background 0.2s ease;" onmouseover="this.style.background='rgba(59,130,246,0.1)'" onmouseout="this.style.background='transparent'">
                                                <input id="invite-scope-commands" type="checkbox" checked style="width:18px;height:18px;cursor:pointer;" /> <span style="font-weight:500;">applications.commands</span>
                                            </label>
                                        </div>
                                        <div style="font-size:12px;color:var(--text-secondary);padding:0 4px;">
                                            Most bot setups should have both enabled
                                        </div>
                                    </div>
                                    <div class="property" style="display:flex;flex-direction:column;gap:10px;">
                                        <span class="property-label" style="font-size:14px;font-weight:600;color:#60a5fa;">Permissions Bitmask</span>
                                        <input id="invite-permissions" class="input-text" type="text" placeholder="e.g. 0 (no perms), 8 (admin)" style="width:100%;font-size:14px;padding:14px 18px;border-radius:10px;background:rgba(0,0,0,0.3);border:1px solid rgba(59,130,246,0.3);transition:all 0.2s ease;" />
                                        <div style="font-size:12px;color:var(--text-secondary);padding:0 4px;">
                                            Optional. Leave empty for full selector
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div style="padding:20px;background:linear-gradient(135deg,rgba(37,99,235,0.08),rgba(139,92,246,0.08));border-radius:12px;border:1px solid rgba(59,130,246,0.3);margin-bottom:20px;">
                                <div style="font-size:14px;font-weight:600;color:#60a5fa;margin-bottom:12px;">Generated Invite URL</div>
                                <input id="invite-output-url" class="input-text invite-output" type="text" readonly placeholder="Click 'Generate invite link' to build a URL" style="width:100%;font-size:13px;padding:14px 18px;border-radius:10px;margin-bottom:12px;" />
                                <div style="display:flex;gap:10px;flex-wrap:wrap;">
                                    <button class="button button-primary" onclick="generateInviteLink()" style="padding:12px 24px;font-size:14px;font-weight:600;border-radius:10px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);border:none;box-shadow:0 4px 12px rgba(59,130,246,0.4);">Generate invite link</button>
                                    <button class="button button-secondary" onclick="openInviteLink()" style="padding:12px 24px;font-size:14px;font-weight:500;border-radius:10px;">Open in new tab</button>
                                    <button class="button button-secondary" onclick="copyInviteLink()" style="padding:12px 24px;font-size:14px;font-weight:500;border-radius:10px;">Copy to clipboard</button>
                                </div>
                            </div>
                            <div style="font-size:12px;color:var(--text-secondary);padding:12px 16px;background:rgba(59,130,246,0.05);border-radius:8px;border-left:3px solid rgba(59,130,246,0.5);">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right:6px;display:inline-block;vertical-align:middle;">
                                    <path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z"/>
                                </svg> Tip: You can reuse the same Application ID and settings for multiple servers. Share the generated link only with people you trust.
                            </div>
                        </div>
                    </div>
                </div>

                <div id="tab-marketplace" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">Extension/Plugin Marketplace</div>
                            <span style="font-size:11px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);padding:4px 10px;border-radius:6px;font-weight:600;">BETA</span>
                            <button class="header-info-button" onclick="openSectionHelp('marketplace')">?</button>
                        </div>
                    </div>
                    
                    <div style="margin-bottom:16px;padding:12px 16px;background:rgba(59,130,246,0.08);border-radius:10px;border-left:3px solid rgba(59,130,246,0.6);font-size:12px;">
                        <strong>📜 License Notice:</strong> Downloaded extensions may ONLY be used within ZygnalBot ecosystem. Do NOT remove or alter names: ZygnalBot, TheHolyOneZ, TheZ. Violations result in permanent ban.<br/>
                        <strong>📁 Downloads:</strong> Extensions are saved directly to <code>./extensions/</code> folder.
                    </div>
                    
                    <div style="display:flex;gap:12px;margin-bottom:20px;">
                        <button class="button button-primary" onclick="fetchMarketplaceExtensions()" ${typeof LM_PERMS !== 'undefined' && !LM_PERMS.control_marketplace ? 'disabled title="You don\'t have permission to refresh marketplace"' : ''}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;display:inline-block;vertical-align:middle;">
                                <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
                            </svg>
                            Refresh Marketplace
                        </button>
                        <input type="text" id="marketplace-search" class="input-text" placeholder="Search extensions..." style="flex:1;max-width:400px;padding:10px 16px;" onkeyup="filterMarketplaceExtensions()" />
                        <select id="marketplace-filter" class="input-text" style="padding:10px 16px;" onchange="filterMarketplaceExtensions()">
                            <option value="all">All Status</option>
                            <option value="working">Working</option>
                            <option value="beta">Beta</option>
                            <option value="broken">Broken</option>
                        </select>
                    </div>
                    
                    <div id="marketplace-content">
                        <div class="loading">Click "Refresh Marketplace" to load extensions...</div>
                    </div>
                </div>

                <div id="tab-roles" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">Roles &amp; Access</div>
                            <button class="header-info-button" onclick="openSectionHelp('roles')">?</button>
                        </div>
                    </div>
                    <div id="roles-content">
                        <div class="loading">Loading roles...</div>
                    </div>
                </div>

                <div id="tab-security" class="tab-content">
        <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">Security &amp; Logs</div>
                            <button class="header-info-button" onclick="openSectionHelp('security')">?</button>
                        </div>
                        <button class="button button-secondary button-compact" onclick="window.location='owner_audit.php?export=csv'">Export Logs</button>
                    </div>
                    <div style="border-radius:12px;overflow:hidden;border:1px solid var(--border);height:520px;">
                        <iframe src="owner_audit.php" style="width:100%;height:100%;border:0;background:transparent;"></iframe>
                    </div>
                </div>

                <div id="tab-database" class="tab-content">
                    <div class="section-header">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div class="section-title">Database viewer</div>
                            <button class="header-info-button" onclick="openSectionHelp('database')">?</button>
                        </div>
                    </div>
                    <div class="two-column-grid">
                        <div class="column-card">
                            <div class="column-header">
                                <div>
                                    <div class="column-title">Tables</div>
                                    <div class="column-subtitle">dashboard.sqlite (local dashboard database)</div>
                                </div>
                            </div>
                            <div id="db-tables" class="list" style="padding:12px;"></div>
                        </div>
                        <div class="column-card">
                            <div class="column-header">
                                <div>
                                    <div class="column-title" id="db-selected-title">No table selected</div>
                                    <div class="column-subtitle" id="db-selected-subtitle"></div>
                                </div>
                            </div>
                            <div id="db-rows" class="list" style="padding:12px;max-height:420px;overflow:auto;"></div>
                        </div>
                    </div>
                </div>

                <div id="tab-credits" class="tab-content">
                    <div style="
                        position: sticky;
                        top: 0;
                        z-index: 5;
                        margin-bottom: 18px;
                        padding: 10px 16px;
                        border-radius: 999px;
                        border: 1px solid rgba(250, 204, 21, 0.7);
                        background:
                            radial-gradient(circle at 0 0, rgba(250, 204, 21, 0.22), transparent 60%),
                            radial-gradient(circle at 100% 100%, rgba(251, 113, 133, 0.18), transparent 55%),
                            rgba(15, 23, 42, 0.98);
                        box-shadow: 0 0 25px rgba(250, 204, 21, 0.35);
                        display: flex;
                        align-items: center;
                        gap: 10px;
                        font-size: 12px;
                        color: var(--text-primary);
                    ">
                        <span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;">
                            <svg viewBox="0 0 24 24" aria-hidden="true">
                                <defs>
                                    <linearGradient id="credfits-banner-gradient" x1="0" y1="0" x2="1" y2="1">
                                        <stop offset="0%" stop-color="#facc15">
                                            <animate attributeName="stop-color" values="#facc15;#fde047;#facc15" dur="5s" repeatCount="indefinite" />
                                        </stop>
                                        <stop offset="100%" stop-color="#fb923c">
                                            <animate attributeName="stop-color" values="#fb923c;#f97316;#fb923c" dur="5s" repeatCount="indefinite" />
                                        </stop>
                                    </linearGradient>
                                </defs>
                                <path fill="url(#credfits-banner-gradient)" d="M4 18h16l-1.5-9-4 3-2.5-6-2.5 6-4-3L4 18z" />
                            </svg>
                        </span>
                        <span>
                            <strong>Credits &amp; Design Copyright &copy; 2025 TheHolyOneZ.</strong>
                            This dedicated Credits tab (layout, wording, SVG crown artwork) is <strong>NOT</strong> part of the framework's MIT license and MUST remain clearly visible at all times in any use or modification of this dashboard.
                        </span>
                    </div>

                    <div class="section-header">
                        <div class="section-title">👑 Credits</div>
                        <div class="badge badge-secondary" style="font-size: 11px;">Zoryx Discord Bot Framework</div>
                    </div>

                    <div class="card" style="cursor: default; overflow: hidden; position: relative;">
                        <div style="position:absolute;inset:-1px;border-radius:18px;padding:1px;background:
                            radial-gradient(circle at 0 0, rgba(250,204,21,0.55), transparent 60%),
                            radial-gradient(circle at 100% 100%, rgba(251,113,133,0.45), transparent 55%);
                            opacity:0.9;"></div>
                        <div style="position:absolute;inset:0;border-radius:18px;background:
                            radial-gradient(circle at 10% 0%, rgba(59,130,246,0.4), transparent 60%),
                            radial-gradient(circle at 100% 100%, rgba(139,92,246,0.35), transparent 55%),
                            rgba(15,23,42,0.96);
                            filter:blur(0px);"></div>
                        <div style="position:relative;border-radius:16px;padding:20px 22px;display:grid;grid-template-columns:minmax(0,2.1fr) minmax(0,1.9fr);gap:20px;">
                            <div>
                                <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
                                    <div style="width:40px;height:40px;display:inline-flex;align-items:center;justify-content:center;">
                                        <svg viewBox="0 0 24 24" aria-hidden="true">
                                            <defs>
                                                <linearGradient id="credfits-hero-gradient" x1="0" y1="0" x2="1" y2="1">
                                                    <stop offset="0%" stop-color="#facc15">
                                                        <animate attributeName="stop-color" values="#facc15;#fde047;#facc15" dur="6s" repeatCount="indefinite" />
                                                    </stop>
                                                    <stop offset="100%" stop-color="#fb7185">
                                                        <animate attributeName="stop-color" values="#fb7185;#f97316;#fb7185" dur="6s" repeatCount="indefinite" />
                                                    </stop>
                                                </linearGradient>
                                            </defs>
                                            <g>
                                                <path fill="url(#credfits-hero-gradient)" d="M4 18h16l-1.5-9-4 3-2.5-6-2.5 6-4-3L4 18z" />
                                                <circle cx="6" cy="7" r="1.6" fill="#facc15">
                                                    <animate attributeName="r" values="1.6;2.0;1.6" dur="3.2s" repeatCount="indefinite" />
                                                </circle>
                                                <circle cx="12" cy="5" r="1.8" fill="#facc15">
                                                    <animate attributeName="r" values="1.8;2.4;1.8" dur="2.7s" repeatCount="indefinite" />
                                                </circle>
                                                <circle cx="18" cy="7" r="1.6" fill="#facc15">
                                                    <animate attributeName="r" values="1.6;2.0;1.6" dur="3.5s" repeatCount="indefinite" />
                                                </circle>
                                            </g>
                                        </svg>
                                    </div>
                                    <div>
                                        <div style="font-size:15px;font-weight:700;color:var(--text-primary);">Creator &amp; Framework</div>
                                        <div style="font-size:12px;color:var(--text-secondary);">Zoryx is one piece of the wider ZygnalBot ecosystem.</div>
                                    </div>
                                </div>

                                <div class="property">
                                    <span class="property-label">Creator</span>
                                    <span class="property-value">TheHolyOneZ</span>
                                </div>
                                <div class="property">
                                    <span class="property-label">Framework</span>
                                    <span class="property-value">Zoryx Discord Bot Framework</span>
                                </div>
                                <div class="property">
                                    <span class="property-label">Ecosystem</span>
                                    <span class="property-value">Part of the ZygnalBot ecosystem</span>
                                </div>
                                <div class="property">
                                    <span class="property-label">Overview</span>
                                    <span class="property-value"><a href="https://zygnalbot.com/bot-framework/" target="_blank" rel="noreferrer noopener">zygnalbot.com/bot-framework</a></span>
                                </div>
                                <div class="property">
                                    <span class="property-label">Repository</span>
                                    <span class="property-value"><a href="https://github.com/TheHolyOneZ/discord-bot-framework" target="_blank" rel="noreferrer noopener">github.com/TheHolyOneZ/discord-bot-framework</a></span>
                                </div>
                            </div>

                            <div>
                                <div style="font-size:13px;color:var(--text-secondary);margin-bottom:10px;">
                                    This dashboard, live monitoring system, and framework tooling are built to give you serious power over your bot while staying beautiful and readable in real-world production use.
                                </div>
                                <ul style="margin-left:18px;font-size:13px;color:var(--text-secondary);list-style:disc;margin-bottom:10px;">
                                    <li>Deep control over plugins, extensions, and hooks</li>
                                    <li>Safe atomic file operations &amp; per-guild data handling</li>
                                    <li>Clean monitoring UX for long-running self-hosted bots</li>
                                    <li>Self-host friendly design with full data ownership</li>
                                </ul>
                                <div style="font-size:13px;color:var(--text-secondary);margin-bottom:10px;">
                                    If this framework powers your bot, a star on the repo or a small bit of support goes a long way.
                                </div>
                                <div class="property" style="border-bottom:none;">
                                    <span class="property-label">Support</span>
                                    <span class="property-value"><a href="https://zygnalbot.com/support.html" target="_blank" rel="noreferrer noopener">zygnalbot.com/support.html</a></span>
                                </div>
                            </div>
                        </div>
                    </div>
                    </div>
                </div>
            </div>
        </div>

        <div id="lm-nav-palette-overlay" class="lm-nav-palette-overlay">
            <div class="lm-nav-palette-dialog">
                <div class="lm-nav-palette-title">Navigation</div>
                <div class="lm-nav-palette-sub">Jump to a dashboard section</div>
                <div class="lm-nav-palette-list">
                    <button class="lm-nav-palette-item" data-tab="dashboard">
                        <span>Dashboard</span><span class="lm-badge">Core</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="commands">
                        <span>Commands</span><span class="lm-badge">Core</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="plugins">
                        <span>Plugins &amp; Extensions</span><span class="lm-badge">Core</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="hooks">
                        <span>Event Hooks</span><span class="lm-badge">Core</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="filesystem">
                        <span>File System</span><span class="lm-badge">Core</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="files">
                        <span>File Browser</span><span class="lm-badge">Tools</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="chat">
                        <span>Chat Console</span><span class="lm-badge">Tools</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="guilds">
                        <span>Guilds / Servers</span><span class="lm-badge">Tools</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="events">
                        <span>Events</span><span class="lm-badge">Tools</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="invite">
                        <div class="lm-nav-palette-icon">🔗</div>
                        <div class="lm-nav-palette-label">Bot Invite</div>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="marketplace">
                        <div class="lm-nav-palette-icon">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
                            </svg>
                        </div>
                        <div class="lm-nav-palette-label">Marketplace <span style="font-size:9px;">BETA</span></div>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="invite" style="display:none;">
                        <span>Bot Invite Helper</span><span class="lm-badge">Tools</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="system">
                        <span>System</span><span class="lm-badge">Core</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="roles">
                        <span>Roles &amp; Access</span><span class="lm-badge">Admin</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="security">
                        <span>Security &amp; Logs</span><span class="lm-badge">Admin</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="database">
                        <span>Database</span><span class="lm-badge">Admin</span>
                    </button>
                    <button class="lm-nav-palette-item" data-tab="credits">
                        <span>Credits</span><span class="lm-badge">👑 Meta</span>
                    </button>
                </div>
            </div>
        </div>

        <div id="lm-drawer-backdrop" class="lm-drawer-backdrop"></div>
        <nav id="lm-drawer-nav" class="lm-drawer" aria-label="Live Monitor Navigation">
            <div class="lm-drawer-title">Navigation</div>
            <div class="lm-drawer-sub">Live Monitor Sections</div>

            <div class="lm-drawer-group-label">Core</div>
            <button class="lm-drawer-item" data-tab="dashboard">Dashboard</button>
            <button class="lm-drawer-item" data-tab="commands">Commands</button>
            <button class="lm-drawer-item" data-tab="plugins">Plugins &amp; Extensions</button>
            <button class="lm-drawer-item" data-tab="hooks">Event Hooks</button>
            <button class="lm-drawer-item" data-tab="filesystem">File System</button>
            <button class="lm-drawer-item" data-tab="system">System</button>

            <div class="lm-drawer-group-label">Tools</div>
            <button class="lm-drawer-item" data-tab="files">File Browser</button>
            <button class="lm-drawer-item" data-tab="chat">Chat Console</button>
            <button class="lm-drawer-item" data-tab="guilds">Guilds / Servers</button>
            <button class="lm-drawer-item" data-tab="events">Events</button>
            <button class="lm-drawer-item" data-tab="invite">Bot Invite Helper</button>
            <button class="lm-drawer-item" data-tab="marketplace">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:8px;display:inline-block;vertical-align:middle;">
                    <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
                </svg>
                Marketplace (BETA)
            </button>

            <div class="lm-drawer-group-label">Admin</div>
            <button class="lm-drawer-item" data-tab="roles">Roles &amp; Access</button>
            <button class="lm-drawer-item" data-tab="security">Security &amp; Logs</button>
            <button class="lm-drawer-item" data-tab="database">Database</button>

            <div class="lm-drawer-group-label">Meta</div>
            <button class="lm-drawer-item" data-tab="credits">Credits 👑</button>
        </nav>

        <div class="footer">
            <p>Last Updated: <span id="last-update">Never</span></p>
            <p style="margin-top: 4px; font-size: 12px; opacity: 0.85;">
                <a href="https://github.com/TheHolyOneZ/discord-bot-framework" target="_blank" rel="noopener noreferrer">
                    Zoryx Discord Bot Framework · Live Monitor
                </a>
            </p>
        </div>
    </div>

        <div id="lm-tour-overlay" class="lm-nav-palette-overlay" style="display:none;">
            <div class="lm-nav-palette-dialog" style="max-width:720px;">
                <div class="lm-nav-palette-title">Welcome to the Live Monitor Dashboard</div>
                <div class="lm-nav-palette-sub">Quick tour for first-time users</div>
                <div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;">
                    &bull; <strong>Dashboard</strong> &mdash; real-time health, alerts, and quick actions (including backups).<br>
                    &bull; <strong>Commands</strong> &mdash; detailed usage, errors, and performance per command.<br>
                    &bull; <strong>Plugins &amp; Extensions</strong> &mdash; plugin health, load times, and conflicts.<br>
                    &bull; <strong>File System &amp; File Browser</strong> &mdash; browse logs and config files safely.<br>
                    &bull; <strong>Guilds &amp; Servers</strong> &mdash; see where your bot is and leave servers when needed.<br>
                    &bull; <strong>Database</strong> &mdash; explore the Live Monitor SQLite database (if your role allows it).<br>
                    &bull; <strong>Roles &amp; Security</strong> &mdash; manage who can access which features and review audit logs.
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;">
                    <div style="font-size:12px;color:var(--text-secondary);">You can re-open this tour anytime from the Dashboard's Quick Tour button.</div>
                    <button class="button button-primary button-compact" onclick="completeTour()">Got it</button>
                </div>
            </div>
        </div>

        <div id="modal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <div class="modal-title" id="modal-title"></div>
                <button class="close-button" onclick="closeModal()">&times;</button>
            </div>
            <div id="modal-body"></div>
        </div>
    </div>

    <script>
<?php
    $u = lm_current_user();
    $roleName = $u['role'] ?? 'VISITOR';
    $tier = lm_resolve_role_tier($roleName);
    $perms = lm_role_permissions($roleName, $tier);
    $info = [
        'display_name' => $u['display_name'] ?? '',
        'discord_user_id' => $u['discord_user_id'] ?? '',
        'avatar_url' => $u['avatar_url'] ?? '',
        'role' => $roleName,
    ];
    echo 'const LM_CURRENT_USER = ' . json_encode($info, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . ';';
    echo 'const LM_PERMS = ' . json_encode($perms, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . ';';
?>
        const TOKEN = '{{TOKEN}}';
        const DEFAULT_PREFIX = '{{PREFIX}}';
        let currentData = null;
        let platformOS = null;

        function switchTab(tabName) {
            if (!tabName) return;

            // Activate tab contents
            document.querySelectorAll('.tab-content').forEach(panel => {
                panel.classList.toggle('active', panel.id === 'tab-' + tabName);
            });

            // Legacy horizontal tabs (kept for compatibility, may be hidden)
            document.querySelectorAll('.tab').forEach(btn => {
                const onclick = btn.getAttribute('onclick') || '';
                const isMatch = onclick.includes("'" + tabName + "'") || onclick.includes('"' + tabName + '"');
                btn.classList.toggle('active', isMatch);
            });

            // Sidebar (S4-style)
            document.querySelectorAll('#lm-sidebar-nav .lm-sidebar-item').forEach(btn => {
                btn.classList.toggle('lm-active', btn.dataset.tab === tabName);
            });

            // Drawer (D8-style)
            document.querySelectorAll('#lm-drawer-nav .lm-drawer-item').forEach(btn => {
                btn.classList.toggle('lm-active', btn.dataset.tab === tabName);
            });
        }

        // Sidebar navigation click handlers
        (function () {
            const sidebar = document.getElementById('lm-sidebar-nav');
            if (!sidebar) return;
            sidebar.querySelectorAll('.lm-sidebar-item').forEach(btn => {
                btn.addEventListener('click', () => {
                    switchTab(btn.dataset.tab);
                });
            });
        })();

        // Drawer handling (D8 style)
        (function () {
            const trigger = document.getElementById('lm-drawer-trigger');
            const backdrop = document.getElementById('lm-drawer-backdrop');
            const drawer = document.getElementById('lm-drawer-nav');
            if (!trigger || !backdrop || !drawer) return;

            function setOpen(open) {
                document.body.classList.toggle('lm-drawer-open', open);
            }

            trigger.addEventListener('click', () => {
                setOpen(!document.body.classList.contains('lm-drawer-open'));
            });

            backdrop.addEventListener('click', () => setOpen(false));

            drawer.querySelectorAll('.lm-drawer-item').forEach(btn => {
                btn.addEventListener('click', () => {
                    switchTab(btn.dataset.tab);
                    setOpen(false);
                });
            });
        })();

        // Command palette handling (D10 style)
        (function () {
            const trigger = document.getElementById('lm-nav-palette-trigger');
            const overlay = document.getElementById('lm-nav-palette-overlay');
            if (!trigger || !overlay) return;

            function openPalette() {
                overlay.classList.add('lm-open');
            }

            function closePalette() {
                overlay.classList.remove('lm-open');
            }

            trigger.addEventListener('click', openPalette);

            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    closePalette();
                }
            });

            window.addEventListener('keydown', (e) => {
                if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
                    e.preventDefault();
                    openPalette();
                }
                if (e.key === 'Escape') {
                    closePalette();
                }
            });

            overlay.querySelectorAll('.lm-nav-palette-item').forEach(btn => {
                btn.addEventListener('click', () => {
                    switchTab(btn.dataset.tab);
                    closePalette();
                });
            });
        })();

        function isTabAllowedByPerms(tabName) {
            if (!tabName || typeof LM_PERMS === 'undefined') {
                return true;
            }
            const map = {
                dashboard: 'view_dashboard',
                commands: 'view_commands',
                plugins: 'view_plugins',
                hooks: 'view_hooks',
                filesystem: 'view_filesystem',
                files: 'view_files',
                chat: 'view_chat',
                events: 'view_events',
                system: 'view_system',
                invite: 'view_system',
                roles: 'view_security',
                security: 'view_security',
                guilds: 'view_guilds',
                database: 'view_database',
                credits: null,
            };
            const key = map[tabName];
            if (!key) return true;
            return !!LM_PERMS[key];
        }

        function applyPermissionsToUI() {
            if (typeof LM_PERMS === 'undefined') {
                return;
            }

            const tabPermMap = {
                dashboard: 'view_dashboard',
                commands: 'view_commands',
                plugins: 'view_plugins',
                hooks: 'view_hooks',
                filesystem: 'view_filesystem',
                files: 'view_files',
                chat: 'view_chat',
                events: 'view_events',
                system: 'view_system',
                invite: 'view_system',
                roles: 'view_security',
                security: 'view_security',
                guilds: 'view_guilds',
                database: 'view_database',
                credits: null,
            };

            Object.keys(tabPermMap).forEach(tab => {
                const permKey = tabPermMap[tab];
                const allowed = permKey ? !!LM_PERMS[permKey] : true;

                ['.lm-sidebar-item', '.lm-drawer-item', '.lm-nav-palette-item'].forEach(selector => {
                    document.querySelectorAll(`${selector}[data-tab="${tab}"]`).forEach(el => {
                        el.style.display = allowed ? '' : 'none';
                    });
                });

                const tabContent = document.getElementById('tab-' + tab);
                if (tabContent) {
                    tabContent.style.display = allowed ? '' : 'none';
                }
            });

            // Gate high-impact core actions
            if (!LM_PERMS.control_core) {
                document.querySelectorAll('button[onclick*="confirmShutdownBot"]').forEach(btn => {
                    btn.disabled = true;
                    btn.style.opacity = '0.5';
                    btn.style.cursor = 'not-allowed';
                    btn.title = 'This action is not allowed for your role.';
                });
            }

            // Gate dashboard & bot backup actions
            if (!LM_PERMS.control_backup) {
                document.querySelectorAll('button[onclick*="backup_bot_directory"], button[onclick*="backup_dashboard.php"]').forEach(btn => {
                    btn.disabled = true;
                    btn.style.opacity = '0.5';
                    btn.style.cursor = 'not-allowed';
                    btn.title = 'Creating backups is not allowed for your role.';
                });
            }

            // Gate chat console actions
            if (!LM_PERMS.control_chat) {
                ['sendChatMessage', 'requestChatHistory'].forEach(fnName => {
                    document.querySelectorAll(`button[onclick*="${fnName}"]`).forEach(btn => {
                        btn.disabled = true;
                        btn.style.opacity = '0.5';
                        btn.style.cursor = 'not-allowed';
                        btn.title = 'This chat action is not allowed for your role.';
                    });
                });
            }

            // Gate file operations (but still allow viewing when view_files is true)
            if (!LM_PERMS.control_files) {
                const markers = ['createNewFile', 'createNewFolder', 'save(', 'promptRenameCurrentFile', 'contextRename', 'contextMove', 'contextDelete'];
                markers.forEach(marker => {
                    document.querySelectorAll(`#tab-files button[onclick*="${marker}"], #file-context-menu .file-context-item[onclick*="${marker}"]`).forEach(el => {
                        el.style.opacity = '0.5';
                        el.style.cursor = 'not-allowed';
                        el.onclick = (e) => {
                            e.preventDefault();
                            showNotification('This file operation is not allowed for your role.', 'error');
                        };
                    });
                });
            }
        }

        // Apply permissions and ensure we start on the Dashboard view
        applyPermissionsToUI();
        switchTab('dashboard');

        function toggleCard(cardId) {
            const card = document.getElementById(cardId);
            card.classList.toggle('expanded');
        }

        function openModal(title, content) {
            document.getElementById('modal-title').textContent = title;
            document.getElementById('modal-body').innerHTML = content;
            document.getElementById('modal').classList.add('active');
        }
        
        function showModal(title, content) {
            openModal(title, content);
        }

        function closeModal() {
            document.getElementById('modal').classList.remove('active');
        }

        function confirmShutdownBot() {
            const ok = confirm('Shutdown the bot now? This will close the bot and it will NOT restart automatically.');
            if (!ok) return;
            sendCommand('shutdown_bot', {});
        }

        function requestBotBackup() {
            sendCommand('backup_bot_directory', {});
            showNotification('Bot backup requested. The archive will be saved on the bot host under ./data/Dashboardbackups as bot_backup_YYYYMMDD_HHMMSS.zip.', 'info');
        }

        function buildInviteUrl() {
            const appIdInput = document.getElementById('invite-app-id');
            const scopeBot = document.getElementById('invite-scope-bot');
            const scopeCmd = document.getElementById('invite-scope-commands');
            const permsInput = document.getElementById('invite-permissions');
            if (!appIdInput || !scopeBot || !scopeCmd || !permsInput) {
                showNotification('Invite helper inputs are missing from the page.', 'error');
                return null;
            }
            const appId = appIdInput.value.trim();
            if (!appId) {
                showNotification('Please enter your bot Application / Client ID.', 'error');
                return null;
            }
            if (!/^\\d{5,}$/.test(appId)) {
                showNotification('The Application ID should be a numeric Discord snowflake.', 'error');
                return null;
            }
            const scopes = [];
            if (scopeBot.checked) scopes.push('bot');
            if (scopeCmd.checked) scopes.push('applications.commands');
            if (!scopes.length) {
                showNotification('Select at least one scope (typically "bot" and/or "applications.commands").', 'error');
                return null;
            }
            const permsRaw = permsInput.value.trim();
            const params = new URLSearchParams();
            params.set('client_id', appId);
            params.set('scope', scopes.join(' '));
            if (permsRaw) {
                if (!/^\\d+$/.test(permsRaw)) {
                    showNotification('Permissions bitmask must be a numeric value (or leave it empty).', 'error');
                    return null;
                }
                params.set('permissions', permsRaw);
            }
            // Let Discord handle the rest of the OAuth2 flow; this is only for building the URL.
            const baseUrl = 'https://discord.com/api/oauth2/authorize';
            return baseUrl + '?' + params.toString();
        }

        function generateInviteLink() {
            const url = buildInviteUrl();
            if (!url) return;
            const out = document.getElementById('invite-output-url');
            if (out) {
                out.value = url;
                out.scrollLeft = 0;
            }
            showNotification('Invite link generated. You can copy it or open it in a new tab.', 'success');
        }

        function openInviteLink() {
            const out = document.getElementById('invite-output-url');
            let url = out && out.value.trim();
            if (!url) {
                url = buildInviteUrl();
            }
            if (!url) return;
            window.open(url, '_blank', 'noopener');
        }

        async function copyInviteLink() {
            const out = document.getElementById('invite-output-url');
            if (!out || !out.value.trim()) {
                showNotification('Nothing to copy yet. Generate an invite link first.', 'error');
                return;
            }
            const url = out.value.trim();
            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(url);
                } else {
                    out.select();
                    document.execCommand('copy');
                }
                showNotification('Invite link copied to clipboard.', 'success');
            } catch (e) {
                console.error('Clipboard error:', e);
                showNotification('Failed to copy invite link. You can copy it manually from the input field.', 'error');
            }
        }

        let marketplaceExtensions = [];

        async function fetchMarketplaceExtensions() {
            const content = document.getElementById('marketplace-content');
            content.innerHTML = '<div class="loading">Loading extensions...</div>';
            
            // Use 60 attempts (30 seconds) to match API timeout
            sendCommandWithResponse('fetch_marketplace_extensions', {}, (data) => {
                if (data && data.success && data.extensions) {
                    marketplaceExtensions = data.extensions;
                    renderMarketplaceExtensions(marketplaceExtensions);
                    showNotification(`Loaded ${marketplaceExtensions.length} extensions`, 'success');
                } else {
                    content.innerHTML = '<div class="empty-state"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" style="margin-right:8px;display:inline-block;vertical-align:middle;"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg> ' + (data.error || 'Failed to load extensions') + '</div>';
                    showNotification(data.error || 'Failed to load extensions', 'error');
                }
            }, 60);
        }

        function renderMarketplaceExtensions(extensions) {
            const content = document.getElementById('marketplace-content');
            
            if (!extensions || extensions.length === 0) {
                content.innerHTML = '<div class="empty-state">No extensions found</div>';
                return;
            }
            
            let html = '<div class="marketplace-grid">';
            
            extensions.forEach(ext => {
                const statusClass = `marketplace-status-${ext.status.toLowerCase()}`;
                const statusIcon = ext.status === 'working' 
                    ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle;"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>'
                    : ext.status === 'beta'
                    ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle;"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>'
                    : '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle;"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>';
                
                html += `
                    <div class="marketplace-extension-card" data-status="${ext.status.toLowerCase()}" data-title="${ext.title.toLowerCase()}" data-description="${ext.description.toLowerCase()}">
                        ${ext.banner ? `<img src="${ext.banner}" class="marketplace-ext-banner" onerror="this.style.display='none'" />` : ''}
                        <div class="marketplace-ext-header">
                            ${ext.icon ? `<img src="${ext.icon}" class="marketplace-ext-icon" onerror="this.src='https://via.placeholder.com/48?text=${ext.title[0]}'" />` : `<div class="marketplace-ext-icon" style="display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#3b82f6,#8b5cf6);font-size:20px;font-weight:bold;">${ext.title[0]}</div>`}
                            <div class="marketplace-ext-info">
                                <div class="marketplace-ext-title">${ext.title}</div>
                                <div class="marketplace-ext-version">v${ext.version}</div>
                            </div>
                            <div class="marketplace-ext-status ${statusClass}">
                                ${statusIcon} ${ext.status}
                            </div>
                        </div>
                        <div class="marketplace-ext-description">${ext.description}</div>
                        <div style="font-size:11px;color:var(--text-secondary);margin-bottom:8px;">
                            Type: ${ext.fileType.toUpperCase()} • ID: ${ext.id}
                        </div>
                        <div class="marketplace-ext-footer">
                            <button class="button button-primary button-compact" onclick="downloadExtension(${ext.id})" ${typeof LM_PERMS !== 'undefined' && !LM_PERMS.control_marketplace ? 'disabled title="You do not have permission to download extensions"' : ''}>
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;display:inline-block;vertical-align:middle;">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
                                </svg>
                                Download
                            </button>
                            <button class="button button-secondary button-compact" onclick="showExtensionDetails(${ext.id})">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px;display:inline-block;vertical-align:middle;">
                                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
                                </svg>
                                Details
                            </button>
                        </div>
                    </div>
                `;
            });
            
            html += '</div>';
            content.innerHTML = html;
        }

        function filterMarketplaceExtensions() {
            const searchTerm = document.getElementById('marketplace-search').value.toLowerCase();
            const statusFilter = document.getElementById('marketplace-filter').value;
            
            const filtered = marketplaceExtensions.filter(ext => {
                const matchesSearch = !searchTerm || 
                    ext.title.toLowerCase().includes(searchTerm) || 
                    ext.description.toLowerCase().includes(searchTerm) ||
                    ext.details.toLowerCase().includes(searchTerm);
                
                const matchesStatus = statusFilter === 'all' || ext.status.toLowerCase() === statusFilter;
                
                return matchesSearch && matchesStatus;
            });
            
            renderMarketplaceExtensions(filtered);
        }

        async function downloadExtension(extensionId) {
            const extension = marketplaceExtensions.find(e => e.id === extensionId);
            if (!extension) {
                showNotification('Extension not found', 'error');
                return;
            }
            
            const shouldLoad = confirm(`Download ${extension.title}?\\n\\nWould you like to automatically load it after download?`);
            console.log('[MARKETPLACE] Auto-load after download:', shouldLoad);
            
            showNotification(`Downloading ${extension.title}...`, 'info');
            
            sendCommandWithResponse('download_marketplace_extension', { extension }, (response) => {
                console.log('[MARKETPLACE] Download response:', response);
                
                if (response && response.success) {
                    showNotification(`Downloaded ${extension.title} to ./extensions/`, 'success');
                    
                    if (shouldLoad && response.filepath) {
                        console.log('[MARKETPLACE] Auto-loading extension:', response.filepath);
                        setTimeout(() => {
                            loadDownloadedExtension(response.filepath, extension.title);
                        }, 1500);
                    } else if (shouldLoad && !response.filepath) {
                        console.warn('[MARKETPLACE] Cannot auto-load: filepath not provided in response');
                        showNotification('Downloaded successfully, but auto-load failed. Please load manually from Plugins & Extensions tab.', 'warning');
                    }
                } else {
                    const errorMsg = response.error || 'Download failed';
                    
                    if (response.error_type === 'zygnal_id_not_activated') {
                        let formattedMsg = errorMsg
                            .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')
                            .replace(/`(.+?)`/g, '<code style="background:rgba(0,0,0,0.3);padding:2px 6px;border-radius:4px;">$1</code>')
                            .replace(/\\n\\n/g, '<br/><br/>')
                            .replace(/\\n/g, '<br/>');
                        
                        openModal('Download Failed - Activation Required', 
                            `<div style="font-size:14px;line-height:1.8;color:#e6edf3;">${formattedMsg}</div>`);
                    } else {
                        showNotification(errorMsg, 'error');
                    }
                }
            }, 120);
        }

        function loadDownloadedExtension(filepath, extensionName) {
            // Use platform-appropriate path separator
            const separator = (platformOS === 'Windows') ? '\\\\' : '/';
            const filename = filepath.split(separator).pop() || filepath.split(/[\\\\/]/).pop();
            const extensionNameFromFile = filename.replace(/\\.(py|pyw)$/, '');
            const extensionPath = `extensions.${extensionNameFromFile}`;
            
            console.log('[MARKETPLACE] Platform:', platformOS, 'Separator:', separator);
            console.log('[MARKETPLACE] Loading extension:', extensionPath, 'from filepath:', filepath);
            showNotification(`Loading ${extensionName}...`, 'info');
            sendCommand('load_extension', { extension: extensionPath });
        }

        function renderMarkdown(text) {
            if (!text) return '';
            return text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/\\n/g, '<br/>');
        }

        function showExtensionDetails(extensionId) {
            const ext = marketplaceExtensions.find(e => e.id === extensionId);
            if (!ext) return;
            
            const statusIcon = ext.status === 'working' 
                    ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle;"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>'
                    : ext.status === 'beta'
                    ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle;"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>'
                    : '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block;vertical-align:middle;"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>';
            
            const renderedDetails = renderMarkdown(ext.details || ext.description);
            
            const html = `
                <div style="max-height:500px;overflow-y:auto;">
                    ${ext.banner ? `<img src="${ext.banner}" style="width:100%;border-radius:8px;margin-bottom:12px;" />` : ''}
                    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
                        ${ext.icon ? `<img src="${ext.icon}" style="width:64px;height:64px;border-radius:8px;" />` : ''}
                        <div>
                            <h3 style="margin:0;color:#60a5fa;">${ext.title}</h3>
                            <p style="margin:4px 0;color:var(--text-secondary);font-size:13px;">Version ${ext.version} • ${statusIcon} ${ext.status}</p>
                        </div>
                    </div>
                    <p style="font-size:13px;line-height:1.6;margin-bottom:12px;">${ext.description}</p>
                    <div style="background:rgba(59,130,246,0.08);padding:14px;border-radius:8px;margin-bottom:12px;">
                        <div style="font-size:12px;line-height:1.7;color:var(--text-primary);">${renderedDetails}</div>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;">
                        <div><strong>Type:</strong> ${ext.fileType.toUpperCase()}</div>
                        <div><strong>ID:</strong> ${ext.id}</div>
                    </div>
                </div>
            `;
            
            openModal(ext.title, html);
        }

        function interpretHttpError(status, payload, context) {
            // context: 'command', 'file', 'roles', 'database', etc.
            if (status === 403) {
                const base = context === 'roles'
                    ? 'You do not have permission to manage Roles & Access on this dashboard.'
                    : context === 'file'
                        ? 'You do not have permission to perform this file operation.'
                        : context === 'database'
                            ? 'You do not have permission to view the dashboard database.'
                            : 'You do not have permission to perform this action.';
                let extra = '';
                if (payload && typeof payload === 'object') {
                    if (payload.error) {
                        extra = ' Details: ' + payload.error;
                    } else if (payload.reason) {
                        extra = ' Details: ' + payload.reason;
                    } else if (payload.message) {
                        extra = ' Details: ' + payload.message;
                    }
                }
                return base + extra;
            }
            if (status === 401) {
                return 'Your session expired or you are not logged in. Please reload the page and log in again.';
            }
            if (status >= 500) {
                return 'The dashboard backend returned an internal error (' + status + '). Check your hosting logs.';
            }
            return 'Request failed with HTTP ' + status + '. Please check the browser console for details.';
        }

        function sendCommand(command, params) {
            if (isCommandPending) {
                showNotification('Please wait, a command is already being processed...', 'info');
                return;
            }

            isCommandPending = true;
            showNotification('Sending command...', 'info');

            fetch('./send_command.php?token=' + TOKEN, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ command: command, params: params })
            })
            .then(async r => {
                let payload = null;
                try {
                    payload = await r.json();
                } catch (_) {
                    // ignore JSON parse errors
                }
                if (!r.ok) {
                    const msg = interpretHttpError(r.status, payload, 'command');
                    throw new Error(msg);
                }
                return payload || {};
            })
            .then(data => {
                isCommandPending = false;
                showNotification('Command sent successfully', 'success');
                setTimeout(loadData, 1000);
            })
            .catch(err => {
                isCommandPending = false;
                console.error('Command error:', err);
                showNotification(err.message || 'Error while sending command.', 'error');
            });
        }

        function sendCommandWithResponse(command, params, callback, maxAttempts = 30) {
            if (isCommandPending) {
                showNotification('Please wait, a command is already being processed...', 'info');
                return;
            }

            isCommandPending = true;
            const expectedCommandType = command; // Match command type to sent command

            fetch('./send_command.php?token=' + TOKEN, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ command: command, params: params })
            })
            .then(async r => {
                let payload = null;
                try {
                    payload = await r.json();
                } catch (_) {
                    // ignore JSON parse errors
                }
                if (!r.ok) {
                    const msg = interpretHttpError(r.status, payload, 'command');
                    throw new Error(msg);
                }
                return payload || {};
            })
            .then(data => {
                // Poll for fileops response
                let attempts = 0;
                const pollInterval = setInterval(() => {
                    attempts++;
                    fetch('monitor_data_fileops.json?t=' + Date.now())
                        .then(r => {
                            // 404 is expected when bot hasn't written response yet
                            if (!r.ok && r.status !== 404) {
                                throw new Error(`HTTP ${r.status}`);
                            }
                            return r.status === 404 ? null : r.json();
                        })
                        .then(fileops => {
                            if (fileops && (fileops.success !== undefined || fileops.error !== undefined)) {
                                // Check if this response is for our command
                                if (fileops.command_type && fileops.command_type !== expectedCommandType) {
                                    console.log(`[FILEOPS] Ignoring response for ${fileops.command_type}, waiting for ${expectedCommandType}`);
                                    return; // Continue polling
                                }
                                
                                clearInterval(pollInterval);
                                isCommandPending = false;
                                callback(fileops);
                            } else if (attempts >= maxAttempts) {
                                clearInterval(pollInterval);
                                isCommandPending = false;
                                showNotification('Command timeout - no response received after ' + (maxAttempts/2) + ' seconds', 'error');
                                callback({ success: false, error: 'Timeout waiting for bot response' });
                            }
                        })
                        .catch(err => {
                            // Only fail on max attempts to allow transient errors
                            if (attempts >= maxAttempts) {
                                clearInterval(pollInterval);
                                isCommandPending = false;
                                showNotification('Error polling for response: ' + err.message, 'error');
                                callback({ success: false, error: err.message });
                            }
                        });
                }, 500);
            })
            .catch(err => {
                isCommandPending = false;
                console.error('Command error:', err);
                showNotification(err.message || 'Error while sending command.', 'error');
                callback({ success: false, error: err.message });
            });
        }

        function refreshPlugins() {
            alert('Refreshing plugins and extensions data...');
            loadData();
        }
        
        function viewPluginStatus(plugin) {
            let statusContent = '';
            
            if (plugin.deps_ok && !plugin.has_conflicts && !plugin.has_cycle && plugin.scan_errors.length === 0) {
                statusContent = `
                    <div style="padding: 20px; text-align: center;">
                        <div style="font-size: 48px; margin-bottom: 16px;">✅</div>
                        <h3 style="color: var(--success); margin-bottom: 12px;">Plugin is Healthy!</h3>
                        <p style="color: var(--text-secondary);">No issues detected with ${plugin.name}</p>
                        <div style="margin-top: 20px; padding: 16px; background: rgba(16, 185, 129, 0.1); border-radius: 8px; border: 1px solid rgba(16, 185, 129, 0.3);">
                            <div class="property">
                                <span class="property-label">Dependencies</span>
                                <span class="property-value" style="color: var(--success);">✓ All satisfied</span>
                            </div>
                            <div class="property">
                                <span class="property-label">Conflicts</span>
                                <span class="property-value" style="color: var(--success);">✓ None detected</span>
                            </div>
                            <div class="property">
                                <span class="property-label">Circular Dependencies</span>
                                <span class="property-value" style="color: var(--success);">✓ None detected</span>
                            </div>
                            <div class="property">
                                <span class="property-label">Scan Errors</span>
                                <span class="property-value" style="color: var(--success);">✓ No errors</span>
                            </div>
                        </div>
                    </div>
                `;
            } else {
                const issues = [];
                
                if (!plugin.deps_ok && plugin.dep_messages && plugin.dep_messages.length > 0) {
                    issues.push({
                        title: '❌ Dependency Issues',
                        items: plugin.dep_messages,
                        color: 'var(--danger)'
                    });
                }
                
                if (plugin.has_conflicts && plugin.conflict_messages && plugin.conflict_messages.length > 0) {
                    issues.push({
                        title: '⚠️ Conflicts Detected',
                        items: plugin.conflict_messages,
                        color: 'var(--warning)'
                    });
                }
                
                if (plugin.has_cycle) {
                    issues.push({
                        title: 'Circular Dependency',
                        items: ['This plugin has a circular dependency that could cause loading issues'],
                        color: 'var(--danger)'
                    });
                }
                
                if (plugin.scan_errors && plugin.scan_errors.length > 0) {
                    issues.push({
                        title: '⚠️ Scan Errors',
                        items: plugin.scan_errors,
                        color: 'var(--warning)'
                    });
                }
                
                statusContent = `
                    <div style="padding: 20px;">
                        <div style="text-align: center; margin-bottom: 24px;">
                            <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
                            <h3 style="color: var(--danger); margin-bottom: 8px;">Plugin Has Issues</h3>
                            <p style="color: var(--text-secondary);">${issues.length} issue${issues.length > 1 ? 's' : ''} detected with ${plugin.name}</p>
                        </div>
                        ${issues.map(issue => `
                            <div style="margin-bottom: 20px; padding: 16px; background: rgba(239, 68, 68, 0.1); border-radius: 8px; border: 1px solid rgba(239, 68, 68, 0.3);">
                                <h4 style="color: ${issue.color}; margin-bottom: 12px;">${issue.title}</h4>
                                <ul style="list-style: none; padding: 0; margin: 0;">
                                    ${issue.items.map(item => `
                                        <li style="padding: 8px 0; border-bottom: 1px solid var(--border); color: var(--text-secondary); font-size: 14px;">
                                            ${item}
                                        </li>
                                    `).join('')}
                                </ul>
                            </div>
                        `).join('')}
                        <div style="margin-top: 20px; padding: 12px; background: rgba(59, 130, 246, 0.1); border-radius: 8px; border: 1px solid rgba(59, 130, 246, 0.3);">
                            <p style="color: var(--text-secondary); font-size: 13px; margin: 0;">
                                💡 <strong>Tip:</strong> Fix these issues to ensure the plugin works correctly
                            </p>
                        </div>
                    </div>
                `;
            }
            
            showModal('Plugin Status: ' + plugin.name, statusContent);
        }

        function viewPluginDetails(plugin) {
            const content = `
                <div style="padding: 20px;">
                    <div class="property-group" style="margin-bottom: 24px;">
                        <h4 style="color: #58a6ff; margin-bottom: 12px; font-size: 16px; font-weight: 600;">General Information</h4>
                        <div class="property">
                            <span class="property-label">Name</span>
                            <span class="property-value">${plugin.name}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Version</span>
                            <span class="property-value">${plugin.version}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Author</span>
                            <span class="property-value">${plugin.author}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Description</span>
                            <span class="property-value">${plugin.description || 'No description'}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Loaded At</span>
                            <span class="property-value" style="font-size: 11px; font-family: monospace;">${plugin.loaded_at}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Load Time</span>
                            <span class="property-value">${Math.round((plugin.load_time || 0) * 1000)}ms</span>
                        </div>
                        ${plugin.file_path ? `
                        <div class="property">
                            <span class="property-label">File Path</span>
                            <span class="property-value" style="font-size: 11px; font-family: monospace;">${plugin.file_path}</span>
                        </div>
                        ` : ''}
                    </div>
                    
                    <div class="property-group" style="margin-bottom: 24px;">
                        <h4 style="color: #58a6ff; margin-bottom: 12px; font-size: 16px; font-weight: 600;">Features</h4>
                        <div class="property">
                            <span class="property-label">Commands</span>
                            <span class="property-value">${plugin.commands_count || 0}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Cogs</span>
                            <span class="property-value">${(plugin.cogs || []).length}</span>
                        </div>
                        ${(plugin.provides_hooks || []).length > 0 ? `
                        <div class="property">
                            <span class="property-label">Provides Hooks</span>
                            <span class="property-value">${(plugin.provides_hooks || []).join(', ')}</span>
                        </div>
                        ` : ''}
                        ${(plugin.listens_to_hooks || []).length > 0 ? `
                        <div class="property">
                            <span class="property-label">Listens to Hooks</span>
                            <span class="property-value">${(plugin.listens_to_hooks || []).join(', ')}</span>
                        </div>
                        ` : ''}
                    </div>
                    
                    ${(plugin.commands || []).length > 0 ? `
                    <div class="property-group" style="margin-bottom: 24px;">
                        <h4 style="color: #58a6ff; margin-bottom: 12px; font-size: 16px; font-weight: 600;">Commands (${plugin.commands.length})</h4>
                        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                            ${(plugin.commands || []).map(cmd => 
                                `<span class="badge" style="background: #1e3a8a; font-size: 12px;">${cmd}</span>`
                            ).join('')}
                        </div>
                    </div>
                    ` : ''}
                    
                    ${(plugin.cogs || []).length > 0 ? `
                    <div class="property-group" style="margin-bottom: 24px;">
                        <h4 style="color: #58a6ff; margin-bottom: 12px; font-size: 16px; font-weight: 600;">Cogs (${plugin.cogs.length})</h4>
                        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                            ${(plugin.cogs || []).map(cog => 
                                `<span class="badge badge-secondary" style="font-size: 12px;">${cog}</span>`
                            ).join('')}
                        </div>
                    </div>
                    ` : ''}
                    
                    ${Object.keys(plugin.dependencies || {}).length > 0 ? `
                    <div class="property-group" style="margin-bottom: 24px;">
                        <h4 style="color: #58a6ff; margin-bottom: 12px; font-size: 16px; font-weight: 600;">Dependencies</h4>
                        ${Object.entries(plugin.dependencies || {}).map(([name, version]) => `
                            <div class="property">
                                <span class="property-label">${name}</span>
                                <span class="property-value">${version}</span>
                            </div>
                        `).join('')}
                    </div>
                    ` : ''}
                    
                    ${(plugin.conflicts_with || []).length > 0 ? `
                    <div class="property-group" style="margin-bottom: 24px;">
                        <h4 style="color: #ef4444; margin-bottom: 12px; font-size: 16px; font-weight: 600;">Conflicts With</h4>
                        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                            ${(plugin.conflicts_with || []).map(conflict => 
                                `<span class="badge badge-warning" style="font-size: 12px;">${conflict}</span>`
                            ).join('')}
                        </div>
                    </div>
                    ` : ''}
                </div>
            `;
            
            showModal('Plugin Details: ' + plugin.name, content);
        }

        function viewHookDetails(hook) {
            let content = `
                <div class="property">
                    <span class="property-label">Hook ID</span>
                    <span class="property-value" style="font-size: 11px; font-family: monospace;">${hook.hook_id}</span>
                </div>
                <div class="property">
                    <span class="property-label">Event</span>
                    <span class="property-value">${hook.event}</span>
                </div>
                <div class="property">
                    <span class="property-label">Callback</span>
                    <span class="property-value">${hook.callback}</span>
                </div>
                <div class="property">
                    <span class="property-label">Priority</span>
                    <span class="property-value">${hook.priority}</span>
                </div>
                <div class="property">
                    <span class="property-label">Executions</span>
                    <span class="property-value">${hook.execution_count}</span>
                </div>
                <div class="property">
                    <span class="property-label">Failures</span>
                    <span class="property-value">${hook.failure_count}</span>
                </div>
                <div class="property">
                    <span class="property-label">Avg Time</span>
                    <span class="property-value">${hook.avg_time_ms}ms</span>
                </div>
                <div class="property">
                    <span class="property-label">Status</span>
                    <span class="property-value">
                        <span class="badge" style="background: ${hook.disabled ? '#6b7280' : hook.circuit_open ? '#f59e0b' : '#3b82f6'};">
                            ${hook.disabled ? 'Disabled' : hook.circuit_open ? 'Circuit Open' : 'Active'}
                        </span>
                    </span>
                </div>
            `;

            if (hook.execution_history && hook.execution_history.length > 0) {
                content += `
                    <h3 style="margin-top: 20px; margin-bottom: 12px; color: #58a6ff;">Execution History (Last ${hook.execution_history.length})</h3>
                    <div class="execution-history">
                `;
                
                hook.execution_history.slice().reverse().forEach(entry => {
                    const badge = entry.success ? 
                        '<span class="badge" style="background: #3b82f6;">Success</span>' : 
                        '<span class="badge" style="background: #ef4444;">Failure</span>';
                    
                    const errorText = entry.error ? `<div style="margin-top: 8px; color: #ef4444; font-size: 12px;">Error: ${entry.error}</div>` : '';
                    
                    content += `
                        <div class="history-item ${entry.success ? 'success' : 'failure'}">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                ${badge}
                                <span style="font-size: 11px; color: var(--text-secondary);">${formatTime(entry.timestamp)}</span>
                            </div>
                            <div style="font-size: 13px;">Execution Time: <strong>${entry.execution_time_ms}ms</strong></div>
                            ${errorText}
                        </div>
                    `;
                });
                
                content += '</div>';
            }

            content += `
                <div class="button-group">
                    <button class="button button-${hook.disabled ? 'success' : 'danger'}" onclick="sendCommand('${hook.disabled ? 'enable_hook' : 'disable_hook'}', {hook_id: '${hook.hook_id}'})">
                        ${hook.disabled ? 'Enable Hook' : 'Disable Hook'}
                    </button>
                    ${hook.circuit_open ? `
                        <button class="button button-secondary" onclick="sendCommand('reset_circuit', {hook_id: '${hook.hook_id}'})">
                            Reset Circuit
                        </button>
                    ` : ''}
                </div>
            `;

            openModal('Hook Details', content);
        }

        window.refreshHooks = () => {
            showNotification('Refreshing Event Hooks...', 'info');
            loadData();
        };

        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        }

        function formatTime(isoString) {
            if (!isoString) return 'Never';
            const date = new Date(isoString);
            return date.toLocaleString();
        }

        let currentCommandView = 'all';
        let currentCommandSort = 'name';

        function renderCommands(commands) {
            const container = document.getElementById('commands-list');
            
            if (commands.length === 0) {
                container.innerHTML = '<div class="empty-state">No commands found</div>';
                return;
            }
            
            const slashCount = commands.filter(c => c.type === 'slash').length;
            const prefixCount = commands.filter(c => (c.type === 'prefix' || c.type === 'prefix_only')).length;
            const hybridCount = commands.filter(c => c.type === 'hybrid').length;
            const uniqueCogs = new Set(commands.map(c => c.cog).filter(Boolean)).size;
            const totalUsage = commands.reduce((sum, c) => sum + (c.usage_count || 0), 0);
            const totalErrors = commands.reduce((sum, c) => sum + (c.error_count || 0), 0);
            const successRate = totalUsage > 0 ? Math.round(((totalUsage - totalErrors) / totalUsage) * 100) : 100;
            
            document.getElementById('cmd-total').textContent = commands.length;
            document.getElementById('cmd-slash').textContent = slashCount;
            document.getElementById('cmd-prefix').textContent = prefixCount;
            document.getElementById('cmd-hybrid').textContent = hybridCount;
            document.getElementById('cmd-cogs').textContent = uniqueCogs;
            document.getElementById('cmd-usage').textContent = totalUsage;
            document.getElementById('cmd-errors').textContent = totalErrors;
            document.getElementById('cmd-success').textContent = successRate + '%';
            
            const viewButtons = document.querySelectorAll('#tab-commands .view-btn');
            viewButtons.forEach(btn => {
                btn.onclick = () => {
                    viewButtons.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    currentCommandView = btn.dataset.view;
                    renderCommandsList();
                };
            });
            
            const searchInput = document.getElementById('cmd-search');
            const sortSelect = document.getElementById('cmd-sort');
            
            searchInput.oninput = renderCommandsList;
            sortSelect.onchange = () => {
                currentCommandSort = sortSelect.value;
                renderCommandsList();
            };
            
            renderCommandsList();
            
            function renderCommandsList() {
                const searchTerm = searchInput.value.toLowerCase();
                
                let filteredCommands = commands.filter(cmd => {
                    const matchesSearch = !searchTerm || 
                        cmd.name.toLowerCase().includes(searchTerm) ||
                        (cmd.description || '').toLowerCase().includes(searchTerm) ||
                        (cmd.cog || '').toLowerCase().includes(searchTerm);
                    
                    const matchesFilter =
                        currentCommandView === 'all' ||
                        (currentCommandView === 'slash' && cmd.type === 'slash') ||
                        (currentCommandView === 'prefix' && (cmd.type === 'prefix' || cmd.type === 'prefix_only')) ||
                        (currentCommandView === 'hybrid' && cmd.type === 'hybrid');
                    
                    return matchesSearch && matchesFilter;
                });
                
                filteredCommands.sort((a, b) => {
                    switch (currentCommandSort) {
                        case 'name':
                            return a.name.localeCompare(b.name);
                        case 'usage':
                            return (b.usage_count || 0) - (a.usage_count || 0);
                        case 'errors':
                            return (b.error_count || 0) - (a.error_count || 0);
                        case 'cog':
                            return (a.cog || '').localeCompare(b.cog || '');
                        default:
                            return 0;
                    }
                });
                
                if (filteredCommands.length === 0) {
                    container.innerHTML = '<div class="empty-state">No commands found</div>';
                    return;
                }
                
                container.innerHTML = filteredCommands.map((cmd, idx) => {
                    const typeColors = {
                        'slash': '#3b82f6',
                        'hybrid': '#10b981',
                        'prefix': '#6b7280',
                        'prefix_only': '#6b7280'
                    };
                    const typeColor = typeColors[cmd.type] || '#6b7280';
                    
                    const hasErrors = (cmd.error_count || 0) > 0;
                    const cmdSuccessRate = (cmd.usage_count || 0) > 0 ? 
                        Math.round(((cmd.usage_count - (cmd.error_count || 0)) / cmd.usage_count) * 100) : 100;

                    const globalPrefix = (typeof DEFAULT_PREFIX !== 'undefined' && DEFAULT_PREFIX) ? DEFAULT_PREFIX : '!';
                    const baseName = cmd.name;
                    let invocationChips = '';

                    if (cmd.type === 'hybrid') {
                        const prefixCall = `${globalPrefix}${baseName}`;
                        const slashCall = `/${baseName}`;
                        invocationChips = `
                            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px;">
                                <span class="badge" style="background: #1e3a8a; font-size: 11px;">${prefixCall}</span>
                                <span class="badge" style="background: #3b82f6; font-size: 11px;">${slashCall}</span>
                            </div>
                        `;
                    } else if (cmd.type === 'slash') {
                        const slashCall = `/${baseName}`;
                        invocationChips = `
                            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px;">
                                <span class="badge" style="background: #3b82f6; font-size: 11px;">${slashCall}</span>
                            </div>
                        `;
                    } else {
                        const prefixCall = `${globalPrefix}${baseName}`;
                        invocationChips = `
                            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 6px;">
                                <span class="badge" style="background: #1e3a8a; font-size: 11px;">${prefixCall}</span>
                            </div>
                        `;
                    }
                    
                    return `
                        <div class="file-row" style="flex-direction: column; align-items: stretch; padding: 10px 12px; margin-bottom: 6px; border: 1px solid #30363d; border-radius: 6px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <div style="flex: 1;">
                                    <div style="font-size: 13px; font-weight: 600; color: #58a6ff; margin-bottom: 2px;">
                                        ${cmd.name}
                                    </div>
                                    ${invocationChips}
                                    <div style="font-size: 12px; color: #8b949e; margin-bottom: 6px;">
                                        ${cmd.description || 'No description'}
                                    </div>
                                    <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                                        <span class="badge" style="background: ${typeColor}; font-size: 10px;">${cmd.type.toUpperCase()}</span>
                                        ${cmd.cog ? `<span class="badge" style="background: #1e40af; font-size: 10px;">${cmd.cog}</span>` : ''}
                                        ${hasErrors ? '<span class="badge" style="background: #ef4444; font-size: 10px;">Has Errors</span>' : ''}
                                    </div>
                                </div>
                            </div>
                            
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 6px; margin-bottom: 8px; padding: 6px 8px; background: rgba(13, 17, 23, 0.5); border-radius: 6px; border: 1px solid rgba(59, 130, 246, 0.25);">
                                <div>
                                    <div style="font-size: 10px; color: #8b949e; text-transform: uppercase;">Usage</div>
                                    <div style="font-size: 14px; font-weight: 600; color: #60a5fa;">${cmd.usage_count || 0}</div>
                                </div>
                                <div>
                                    <div style="font-size: 10px; color: #8b949e; text-transform: uppercase;">Errors</div>
                                    <div style="font-size: 14px; font-weight: 600; color: ${hasErrors ? '#f87171' : '#60a5fa'};">${cmd.error_count || 0}</div>
                                </div>
                                <div>
                                    <div style="font-size: 10px; color: #8b949e; text-transform: uppercase;">Success</div>
                                    <div style="font-size: 14px; font-weight: 600; color: #60a5fa;">${cmdSuccessRate}%</div>
                                </div>
                                <div>
                                    <div style="font-size: 10px; color: #8b949e; text-transform: uppercase;">Last Used</div>
                                    <div style="font-size: 12px; font-weight: 600; color: #60a5fa;">${cmd.last_used ? formatTime(cmd.last_used) : 'Never'}</div>
                                </div>
                            </div>
                            
                            ${(cmd.params && cmd.params.length > 0) || (cmd.subcommands && cmd.subcommands.length > 0) ? `
                            <div style="margin-bottom: 8px;">
                                ${cmd.params && cmd.params.length > 0 ? `
                                <div style="margin-bottom: 6px;">
                                    <div style="font-size: 11px; color: #8b949e; margin-bottom: 4px;">Parameters (${cmd.params.length}):</div>
                                    <div style="display: flex; gap: 3px; flex-wrap: wrap;">
                                        ${cmd.params.map(param => {
                                            const required = param.required !== false;
                                            const paramName = typeof param === 'string' ? param : (param.name || param);
                                            const paramType = typeof param === 'object' ? param.type : '';
                                            const paramDesc = typeof param === 'object' ? param.description : '';
                                            return `<span class="badge" style="background: ${required ? '#1e40af' : '#374151'}; font-size: 10px;" title="${paramDesc || paramName}">
                                                ${paramName}${paramType ? `: ${paramType}` : ''}${required ? '' : ' (optional)'}
                                            </span>`;
                                        }).join('')}
                                    </div>
                                </div>
                                ` : ''}
                                
                                ${cmd.subcommands && cmd.subcommands.length > 0 ? `
                                <div>
                                    <div style="font-size: 11px; color: #8b949e; margin-bottom: 4px;">Subcommands (${cmd.subcommands.length}):</div>
                                    <div style="display: flex; gap: 3px; flex-wrap: wrap;">
                                        ${cmd.subcommands.slice(0, 10).map(sub => {
                                            const subName = typeof sub === 'string' ? sub : (sub.name || sub);
                                            const subDesc = typeof sub === 'object' ? sub.description : '';
                                            return `<span class="badge" style="background: #7c3aed; font-size: 10px;" title="${subDesc || subName}">${subName}</span>`;
                                        }).join('')}
                                        ${cmd.subcommands.length > 10 ? `<span class="badge" style="background: #6b7280; font-size: 10px;">+${cmd.subcommands.length - 10} more</span>` : ''}
                                    </div>
                                </div>
                                ` : ''}
                            </div>
                            ` : ''}
                            
                            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                                <button class="button button-primary" onclick="viewCommandDetails(${JSON.stringify(cmd).replace(/"/g, '&quot;')})" style="padding: 6px 10px; font-size: 11px; box-shadow: none;">
                                    View Details
                                </button>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

        window.refreshCommands = () => {
            showNotification('Refreshing Commands...', 'info');
            loadData();
        };

        function viewCommandDetails(cmd) {
            const globalPrefix = (typeof DEFAULT_PREFIX !== 'undefined' && DEFAULT_PREFIX) ? DEFAULT_PREFIX : '!';
            let invocationText = '';
            if (cmd.type === 'hybrid') {
                invocationText = `${globalPrefix}${cmd.name}  or  /${cmd.name}`;
            } else if (cmd.type === 'slash') {
                invocationText = `/${cmd.name}`;
            } else {
                invocationText = `${globalPrefix}${cmd.name}`;
            }

            let content = `
                <div style="padding: 20px;">
                    <div class="property-group" style="margin-bottom: 24px;">
                        <h4 style="color: #58a6ff; margin-bottom: 12px; font-size: 16px; font-weight: 600;">General Information</h4>
                        <div class="property">
                            <span class="property-label">Name</span>
                            <span class="property-value">${cmd.name}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Description</span>
                            <span class="property-value">${cmd.description || 'No description'}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Type</span>
                            <span class="property-value">${cmd.type.toUpperCase()}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Invocation</span>
                            <span class="property-value" style="font-family: monospace;">${invocationText}</span>
                        </div>
                        ${cmd.cog ? `
                        <div class="property">
                            <span class="property-label">Cog</span>
                            <span class="property-value">${cmd.cog}</span>
                        </div>
                        ` : ''}
                    </div>
                    
                    <div class="property-group" style="margin-bottom: 24px;">
                        <h4 style="color: #58a6ff; margin-bottom: 12px; font-size: 16px; font-weight: 600;">Usage Statistics</h4>
                        <div class="property">
                            <span class="property-label">Total Uses</span>
                            <span class="property-value">${cmd.usage_count || 0}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Errors</span>
                            <span class="property-value">${cmd.error_count || 0}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Success Rate</span>
                            <span class="property-value">${cmd.usage_count > 0 ? Math.round(((cmd.usage_count - (cmd.error_count || 0)) / cmd.usage_count) * 100) : 100}%</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Last Used</span>
                            <span class="property-value">${cmd.last_used ? formatTime(cmd.last_used) : 'Never'}</span>
                        </div>
                    </div>
                    
                    ${cmd.params && cmd.params.length > 0 ? `
                    <div class="property-group" style="margin-bottom: 24px;">
                        <h4 style="color: #58a6ff; margin-bottom: 12px; font-size: 16px; font-weight: 600;">Parameters (${cmd.params.length})</h4>
                        ${cmd.params.map(param => {
                            const paramName = typeof param === 'string' ? param : (param.name || param);
                            const paramType = typeof param === 'object' ? param.type : 'unknown';
                            const paramDesc = typeof param === 'object' ? param.description : '';
                            const required = typeof param === 'object' ? (param.required !== false) : true;
                            return `
                                <div class="property">
                                    <span class="property-label">${paramName}</span>
                                    <span class="property-value">
                                        <span class="badge" style="background: #1e40af;">${paramType}</span>
                                        ${required ? '<span class="badge" style="background: #ef4444; margin-left: 4px;">Required</span>' : '<span class="badge" style="background: #6b7280; margin-left: 4px;">Optional</span>'}
                                        ${paramDesc ? `<div style="font-size: 12px; color: #8b949e; margin-top: 4px;">${paramDesc}</div>` : ''}
                                    </span>
                                </div>
                            `;
                        }).join('')}
                    </div>
                    ` : ''}
                    
                    ${cmd.subcommands && cmd.subcommands.length > 0 ? `
                    <div class="property-group" style="margin-bottom: 24px;">
                        <h4 style="color: #58a6ff; margin-bottom: 12px; font-size: 16px; font-weight: 600;">Subcommands (${cmd.subcommands.length})</h4>
                        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                            ${cmd.subcommands.map(sub => {
                                const subName = typeof sub === 'string' ? sub : (sub.name || sub);
                                const subDesc = typeof sub === 'object' ? sub.description : '';
                                return `<span class="badge" style="background: #7c3aed; font-size: 12px;" title="${subDesc || subName}">${subName}</span>`;
                            }).join('')}
                        </div>
                    </div>
                    ` : ''}
                </div>
            `;
            
            openModal('Command Details', content);
        }

        
        let pluginStatsToggleInitialized = false;
        let pluginStatsVisible = false;

        function setPluginStatsVisibility(visible) {
            const body = document.getElementById('plugins-stats-body');
            const toggle = document.getElementById('plugins-stats-toggle');
            if (!body || !toggle) return;
            pluginStatsVisible = visible;
            body.style.display = visible ? 'grid' : 'none';
            toggle.classList.toggle('on', visible);
            toggle.setAttribute('aria-pressed', visible ? 'true' : 'false');
        }

        function initPluginStatsToggle() {
            if (pluginStatsToggleInitialized) return;
            const toggle = document.getElementById('plugins-stats-toggle');
            const body = document.getElementById('plugins-stats-body');
            if (!toggle || !body) return;
            setPluginStatsVisibility(false);
            toggle.addEventListener('click', () => {
                setPluginStatsVisibility(!pluginStatsVisible);
            });
            pluginStatsToggleInitialized = true;
        }

        function renderPlugins(pluginsData) {
            const plugins = pluginsData.plugins || [];
            const availableExtensions = currentData.available_extensions || [];
            
            updatePluginStats(plugins, availableExtensions);
            initPluginStatsToggle();

            // Enforcement controls (deps/conflicts) if available
            const enforcementContainerId = 'plugin-enforcement-controls';
            const overviewCardHeader = document.querySelector('#tab-plugins .card .card-header');
            if (overviewCardHeader && (pluginsData.enforce_dependencies !== undefined || pluginsData.enforce_conflicts !== undefined)) {
                let existing = document.getElementById(enforcementContainerId);
                const depsEnabled = !!pluginsData.enforce_dependencies;
                const conflictsEnabled = !!pluginsData.enforce_conflicts;

                const depsClass = depsEnabled ? 'button-success' : 'button-secondary';
                const confClass = conflictsEnabled ? 'button-success' : 'button-secondary';

                const html = `
                    <div id="${enforcementContainerId}" style="margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">
                        <span style="font-size: 12px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.08em;">Enforcement</span>
                        <button class="button ${depsClass} button-compact" onclick="togglePluginEnforcement('deps', ${depsEnabled ? 'false' : 'true'})">
                            Dependencies: ${depsEnabled ? 'On' : 'Off'}
                        </button>
                        <button class="button ${confClass} button-compact" onclick="togglePluginEnforcement('conflicts', ${conflictsEnabled ? 'false' : 'true'})">
                            Conflicts: ${conflictsEnabled ? 'On' : 'Off'}
                        </button>
                    </div>
                `;

                if (existing) {
                    existing.outerHTML = html;
                } else {
                    const wrapper = document.createElement('div');
                    wrapper.innerHTML = html;
                    overviewCardHeader.appendChild(wrapper.firstElementChild);
                }
            }
            
            
            const searchInput = document.getElementById('plugin-search');
            const filterSelect = document.getElementById('plugin-filter');
            
            searchInput.oninput = renderPluginsList;
            filterSelect.onchange = renderPluginsList;
            
            renderPluginsList();
            
            function updatePluginStats(plugins, extensions) {
                const totalPlugins = plugins.length;
                const loadedPlugins = plugins.filter(p => p.loaded).length;
                const healthyPlugins = plugins.filter(p => 
                    p.deps_ok && !p.has_conflicts && !p.has_cycle && (!p.scan_errors || p.scan_errors.length === 0)
                ).length;
                const issuesPlugins = totalPlugins - healthyPlugins;
                const totalCommands = plugins.reduce((sum, p) => sum + (p.commands_count || 0), 0);
                const totalCogs = plugins.reduce((sum, p) => sum + (p.cogs ? p.cogs.length : 0), 0);
                const avgLoadTime = totalPlugins > 0 
                    ? Math.round(plugins.reduce((sum, p) => sum + (p.load_time || 0), 0) / totalPlugins * 1000)
                    : 0;
                
                document.getElementById('total-plugins').textContent = totalPlugins;
                document.getElementById('loaded-plugins').textContent = loadedPlugins;
                document.getElementById('healthy-plugins').textContent = healthyPlugins;
                document.getElementById('issues-plugins').textContent = issuesPlugins;
                document.getElementById('total-commands').textContent = totalCommands;
                document.getElementById('total-cogs').textContent = totalCogs;
                document.getElementById('total-extensions').textContent = extensions.length;
                document.getElementById('avg-load-time').textContent = avgLoadTime + 'ms';
            }
            
            function renderPluginsList() {
                const container = document.getElementById('plugins-extensions-list');
                const searchTerm = searchInput.value.toLowerCase();
                const filter = filterSelect.value;
                
                // Merge plugins (from PluginRegistry) with availableExtensions (from disk)
                // This ensures we show ALL extension files, even if they failed to load
                let items = [...plugins];
                
                // Add any extensions that exist on disk but aren't in PluginRegistry
                availableExtensions.forEach(ext => {
                    if (!items.find(p => p.name === ext.name)) {
                        // This extension exists on disk but failed to load or hasn't been scanned
                        items.push({
                            name: ext.name,
                            full_name: ext.full_name,
                            file_path: ext.file_path,
                            loaded: ext.loaded,
                            load_time: ext.load_time,
                            // Missing PluginRegistry data - fill with defaults
                            version: 'unknown',
                            author: 'unknown',
                            description: 'Extension file exists but not registered in PluginRegistry (may have failed to load)',
                            commands: [],
                            commands_count: 0,
                            cogs: [],
                            dependencies: {},
                            conflicts_with: [],
                            provides_hooks: [],
                            listens_to_hooks: [],
                            loaded_at: null,
                            deps_ok: false,
                            has_conflicts: false,
                            has_cycle: false,
                            scan_errors: ['Not registered in PluginRegistry']
                        });
                    }
                });
                
                items = items.filter(item => {
                    const matchesSearch = !searchTerm || 
                        item.name.toLowerCase().includes(searchTerm) ||
                            (item.description || '').toLowerCase().includes(searchTerm) ||
                            (item.commands || []).some(cmd => cmd.toLowerCase().includes(searchTerm));
                        
                        const isHealthy = item.deps_ok && !item.has_conflicts && !item.has_cycle && (!item.scan_errors || item.scan_errors.length === 0);
                        
                        const matchesFilter = 
                            filter === 'all' ||
                            (filter === 'loaded' && item.loaded) ||
                            (filter === 'not_loaded' && !item.loaded) ||
                            (filter === 'healthy' && isHealthy) ||
                            (filter === 'issues' && !isHealthy);
                        
                        return matchesSearch && matchesFilter;
                });
                
                if (items.length === 0) {
                    container.innerHTML = `<div class=\"empty-state\">No plugins found</div>`;
                    return;
                }
                
                container.innerHTML = items.map((plugin, idx) => {
                        const isHealthy = plugin.deps_ok && !plugin.has_conflicts && !plugin.has_cycle && (!plugin.scan_errors || plugin.scan_errors.length === 0);
                        const statusText = isHealthy ? 'Healthy' : 'Issues';
                        const statusColor = isHealthy ? '#3b82f6' : '#ef4444';
                        const statusBg = isHealthy ? 'rgba(59, 130, 246, 0.1)' : 'rgba(239, 68, 68, 0.1)';
                        
                        return `
                            <div class="file-row" style="flex-direction: column; align-items: stretch; padding: 16px; margin-bottom: 8px; border: 1px solid #30363d; border-radius: 6px;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                    <div style="flex: 1;">
                                        <div style="font-size: 15px; font-weight: 600; color: #58a6ff; margin-bottom: 4px;">
                                            ${plugin.name}
                                        </div>
                                        <div style="font-size: 13px; color: #8b949e; margin-bottom: 8px;">
                                            ${plugin.description || 'No description'}
                                        </div>
                                        <div style=\"display: flex; gap: 8px; flex-wrap: wrap;\">
                                            <span class=\"badge\" style=\"background: ${plugin.loaded ? '#3b82f6' : '#6b7280'};\">${plugin.loaded ? 'Loaded' : 'Not Loaded'}</span>
                                            <span class=\"badge\" style=\"background: ${statusColor};${isHealthy ? '' : ' cursor:pointer;'}\" ${isHealthy ? '' : `onclick=\"viewPluginStatus(${JSON.stringify(plugin).replace(/"/g, '&quot;')})\"`}>
                                                ${statusText}
                                            </span>
                                            <span class=\"badge\" style=\"background: #1e40af;\">v${plugin.version}</span>
                                            ${plugin.author !== 'unknown' ? `<span class="badge badge-secondary">by ${plugin.author}</span>` : ''}
                                        </div>
                                    </div>
                                </div>
                                
                                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 12px; padding: 12px; background: rgba(13, 17, 23, 0.6); border-radius: 6px; border: 1px solid rgba(59, 130, 246, 0.2);">
                                    <div>
                                        <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Commands</div>
                                        <div style="font-size: 16px; font-weight: 600; color: #60a5fa;">${plugin.commands_count || 0}</div>
                                    </div>
                                    <div>
                                        <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Cogs</div>
                                        <div style="font-size: 16px; font-weight: 600; color: #60a5fa;">${(plugin.cogs || []).length}</div>
                                    </div>
                                    <div>
                                        <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Load Time</div>
                                        <div style="font-size: 16px; font-weight: 600; color: #60a5fa;">${Math.round((plugin.load_time || 0) * 1000)}ms</div>
                                    </div>
                                    <div>
                                        <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Dependencies</div>
                                        <div style="font-size: 16px; font-weight: 600; color: #60a5fa;">${Object.keys(plugin.dependencies || {}).length}</div>
                                    </div>
                                </div>
                                
                                ${(plugin.commands || []).length > 0 ? `
                                <div style="margin-bottom: 12px;">
                                    <div style="font-size: 12px; color: #8b949e; margin-bottom: 6px;">Commands:</div>
                                    <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                                        ${(plugin.commands || []).slice(0, 15).map(cmd => 
                                            `<span class="badge" style="background: #1e3a8a; font-size: 11px;">${cmd}</span>`
                                        ).join('')}
                                        ${(plugin.commands || []).length > 15 ? `<span class="badge badge-secondary" style="font-size: 11px;">+${(plugin.commands || []).length - 15} more</span>` : ''}
                                    </div>
                                </div>
                                ` : ''}
                                
                                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                                    <button class="button button-primary" onclick="viewPluginDetails(${JSON.stringify(plugin).replace(/"/g, '&quot;')})">
                                        Details
                                    </button>
                                    <button class="button button-secondary" onclick="sendCommand('reload_extension', {extension: 'extensions.${plugin.name}'})">
                                        Reload
                                    </button>
                                    ${plugin.loaded ? `
                                        <button class="button button-danger" onclick="sendCommand('unload_extension', {extension: 'extensions.${plugin.name}'})">
                                            Unload
                                        </button>
                                    ` : `
                                        <button class="button button-success" onclick="sendCommand('load_extension', {extension: 'extensions.${plugin.name}'})">
                                            Load
                                        </button>
                                    `}
                                    ${!isHealthy ? `
                                        <button class="button button-warning" onclick="viewPluginStatus(${JSON.stringify(plugin).replace(/"/g, '&quot;')})">
                                            View Issues
                                        </button>
                                    ` : ''}
                                </div>
                            </div>
                        `;
                    }).join('');
            }
        }

        let currentHookView = 'all';
        let currentHookSort = 'priority';

        function renderHooks(eventHooksData) {
            const hooks = eventHooksData.hooks || [];
            const metrics = eventHooksData.metrics || {};
            
            document.getElementById('hooks-emissions').textContent = metrics.total_emissions || 0;
            document.getElementById('hooks-executions').textContent = metrics.total_executions || 0;
            document.getElementById('hooks-failures').textContent = metrics.total_failures || 0;
            document.getElementById('hooks-queue-size').textContent = eventHooksData.queue_size || 0;
            document.getElementById('hooks-queue-full').textContent = metrics.queue_full_count || 0;
            document.getElementById('hooks-worker-restarts').textContent = metrics.worker_restarts || 0;
            document.getElementById('hooks-disabled').textContent = eventHooksData.disabled || 0;
            document.getElementById('hooks-circuit-open').textContent = eventHooksData.circuit_open || 0;
            
            const viewButtons = document.querySelectorAll('#tab-hooks .view-btn');
            viewButtons.forEach(btn => {
                btn.onclick = () => {
                    viewButtons.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    currentHookView = btn.dataset.view;
                    renderHooksList();
                };
            });
            
            const searchInput = document.getElementById('hooks-search');
            const sortSelect = document.getElementById('hooks-sort');
            
            searchInput.oninput = renderHooksList;
            sortSelect.onchange = () => {
                currentHookSort = sortSelect.value;
                renderHooksList();
            };
            
            renderHooksList();
            
            function renderHooksList() {
                const container = document.getElementById('hooks-list');
                const searchTerm = searchInput.value.toLowerCase();
                
                let filteredHooks = hooks.filter(hook => {
                    const matchesSearch = !searchTerm || 
                        hook.event.toLowerCase().includes(searchTerm) ||
                        hook.callback.toLowerCase().includes(searchTerm) ||
                        hook.hook_id.toLowerCase().includes(searchTerm);
                    
                    const isActive = !hook.disabled && !hook.circuit_open;
                    const hasIssues = hook.circuit_open || hook.failure_count > 0;
                    
                    const matchesFilter =
                        currentHookView === 'all' ||
                        (currentHookView === 'active' && isActive) ||
                        (currentHookView === 'disabled' && hook.disabled) ||
                        (currentHookView === 'issues' && hasIssues);
                    
                    return matchesSearch && matchesFilter;
                });
                
                filteredHooks.sort((a, b) => {
                    switch (currentHookSort) {
                        case 'priority':
                            return b.priority - a.priority;
                        case 'executions':
                            return b.execution_count - a.execution_count;
                        case 'failures':
                            return b.failure_count - a.failure_count;
                        case 'time':
                            return b.avg_time_ms - a.avg_time_ms;
                        default:
                            return 0;
                    }
                });
                
                if (filteredHooks.length === 0) {
                    container.innerHTML = '<div class="empty-state">No hooks found</div>';
                    return;
                }
                
                container.innerHTML = filteredHooks.map((hook, idx) => {
                    const isActive = !hook.disabled && !hook.circuit_open;
                    const statusColor = hook.disabled ? '#6b7280' : hook.circuit_open ? '#f59e0b' : '#3b82f6';
                    const statusText = hook.disabled ? 'Disabled' : hook.circuit_open ? 'Circuit Open' : 'Active';
                    const hasIssues = hook.circuit_open || hook.failure_count > 0;
                    
                    return `
                        <div class="file-row" style="flex-direction: column; align-items: stretch; padding: 16px; margin-bottom: 8px; border: 1px solid #30363d; border-radius: 6px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                <div style="flex: 1;">
                                    <div style="font-size: 15px; font-weight: 600; color: #58a6ff; margin-bottom: 4px;">
                                        ${hook.event} → ${hook.callback}
                                    </div>
                                    <div style="font-size: 12px; color: #8b949e; margin-bottom: 8px;">
                                        Hook ID: ${hook.hook_id}
                                    </div>
                                    <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                                        <span class="badge" style="background: ${statusColor};">${statusText}</span>
                                        <span class="badge" style="background: #1e40af;">Priority ${hook.priority}</span>
                                        ${hasIssues ? '<span class="badge" style="background: #ef4444;">Has Issues</span>' : ''}
                                    </div>
                                </div>
                            </div>
                            
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 12px; padding: 12px; background: rgba(13, 17, 23, 0.6); border-radius: 6px; border: 1px solid rgba(59, 130, 246, 0.2);">
                                <div>
                                    <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Executions</div>
                                    <div style="font-size: 16px; font-weight: 600; color: #60a5fa;">${hook.execution_count || 0}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Failures</div>
                                    <div style="font-size: 16px; font-weight: 600; color: ${hook.failure_count > 0 ? '#f87171' : '#60a5fa'};">${hook.failure_count || 0}</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Avg Time</div>
                                    <div style="font-size: 16px; font-weight: 600; color: #60a5fa;">${hook.avg_time_ms || 0}ms</div>
                                </div>
                                <div>
                                    <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Success Rate</div>
                                    <div style="font-size: 16px; font-weight: 600; color: #60a5fa;">${hook.execution_count > 0 ? Math.round(((hook.execution_count - hook.failure_count) / hook.execution_count) * 100) : 100}%</div>
                                </div>
                            </div>
                            
                            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                                <button class="button button-primary" onclick="viewHookDetails(${JSON.stringify(hook).replace(/"/g, '&quot;')})
                                    Details
                                </button>
                                <button class="button button-${hook.disabled ? 'success' : 'secondary'}" onclick="sendCommand('${hook.disabled ? 'enable_hook' : 'disable_hook'}', {hook_id: '${hook.hook_id}'})">
                                    ${hook.disabled ? 'Enable' : 'Disable'}
                                </button>
                                ${hook.circuit_open ? `
                                    <button class="button button-warning" onclick="sendCommand('reset_circuit', {hook_id: '${hook.hook_id}'})">
                                        Reset Circuit
                                    </button>
                                ` : ''}
                            </div>
                        </div>
                    `;
                }).join('');
            }
        }

        function renderFileSystem(fs) {
            const container = document.getElementById('filesystem-content');

            if (!fs || Object.keys(fs).length === 0) {
                container.innerHTML = '<div class="empty-state">File system monitoring disabled to reduce data size</div>';
                document.getElementById('fs-total-files').textContent = '0';
                document.getElementById('fs-total-size').textContent = '0 MB';
                document.getElementById('fs-data-files').textContent = '0';
                document.getElementById('fs-cogs-files').textContent = '0';
                document.getElementById('fs-ext-files').textContent = '0';
                document.getElementById('fs-logs-files').textContent = '0';
                document.getElementById('fs-cache-hits').textContent = '0';
                document.getElementById('fs-cache-misses').textContent = '0';
                return;
            }

            let totalFiles = 0;
            let totalSize = 0;
            
            if (fs.data && fs.data.exists) {
                totalFiles += fs.data.file_count || 0;
                totalSize += fs.data.total_size || 0;
            }
            if (fs.cogs && fs.cogs.exists) {
                totalFiles += fs.cogs.file_count || 0;
                totalSize += fs.cogs.total_size || 0;
            }
            if (fs.extensions && fs.extensions.exists) {
                totalFiles += fs.extensions.file_count || 0;
                totalSize += fs.extensions.total_size || 0;
            }
            if (fs.botlogs && fs.botlogs.exists) {
                totalFiles += fs.botlogs.file_count || 0;
                totalSize += fs.botlogs.total_size || 0;
            }
            
            document.getElementById('fs-total-files').textContent = totalFiles;
            document.getElementById('fs-total-size').textContent = formatBytes(totalSize);
            document.getElementById('fs-data-files').textContent = (fs.data && fs.data.exists) ? fs.data.file_count : 0;
            document.getElementById('fs-cogs-files').textContent = (fs.cogs && fs.cogs.exists) ? fs.cogs.file_count : 0;
            document.getElementById('fs-ext-files').textContent = (fs.extensions && fs.extensions.exists) ? fs.extensions.file_count : 0;
            document.getElementById('fs-logs-files').textContent = (fs.botlogs && fs.botlogs.exists) ? fs.botlogs.file_count : 0;
            
            if (fs.cache_metrics) {
                document.getElementById('fs-cache-hits').textContent = fs.cache_metrics.hits || 0;
                document.getElementById('fs-cache-misses').textContent = fs.cache_metrics.misses || 0;
            }

            const renderDirectory = (name, data, icon) => {
                if (!data || !data.exists) {
                    return `
                        <div class="file-row" style="flex-direction: column; align-items: stretch; padding: 16px; margin-bottom: 8px; border: 1px solid #30363d; border-radius: 6px; opacity: 0.5;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <div style="font-size: 15px; font-weight: 600; color: #8b949e; margin-bottom: 4px;">
                                        ${name}
                                    </div>
                                    <div style="font-size: 13px; color: #6b7280;">
                                        Directory not available
                                    </div>
                                </div>
                                <span class="badge" style="background: #6b7280;">Not Found</span>
                            </div>
                        </div>
                    `;
                }

                const sizeColor = data.total_size > 10485760 ? '#f59e0b' : '#60a5fa';
                
                return `
                    <div class="file-row" style="flex-direction: column; align-items: stretch; padding: 16px; margin-bottom: 8px; border: 1px solid #30363d; border-radius: 6px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <div style="flex: 1;">
                                <div style="font-size: 15px; font-weight: 600; color: #58a6ff; margin-bottom: 4px;">
                                    ${name}
                                </div>
                                <div style="font-size: 13px; color: #8b949e; margin-bottom: 8px;">
                                    ${data.path || 'Unknown path'}
                                </div>
                                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                                    <span class="badge" style="background: #10b981;">Exists</span>
                                    ${data.file_count > 0 ? '<span class="badge" style="background: #3b82f6;">Has Files</span>' : '<span class="badge" style="background: #6b7280;">Empty</span>'}
                                </div>
                            </div>
                        </div>
                        
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 12px; padding: 12px; background: rgba(13, 17, 23, 0.6); border-radius: 6px; border: 1px solid rgba(59, 130, 246, 0.2);">
                            <div>
                                <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Files</div>
                                <div style="font-size: 16px; font-weight: 600; color: #60a5fa;">${data.file_count || 0}</div>
                            </div>
                            <div>
                                <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Total Size</div>
                                <div style="font-size: 16px; font-weight: 600; color: ${sizeColor};">${formatBytes(data.total_size || 0)}</div>
                            </div>
                            <div>
                                <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Avg File Size</div>
                                <div style="font-size: 16px; font-weight: 600; color: #60a5fa;">${data.file_count > 0 ? formatBytes((data.total_size || 0) / data.file_count) : '0 B'}</div>
                            </div>
                            <div>
                                <div style="font-size: 11px; color: #8b949e; text-transform: uppercase;">Largest File</div>
                                <div style="font-size: 16px; font-weight: 600; color: #60a5fa;">${data.largest_file ? formatBytes(data.largest_file.size) : 'N/A'}</div>
                            </div>
                        </div>
                        
                        ${data.largest_file ? `
                        <div style="margin-bottom: 12px; padding: 8px 12px; background: rgba(59, 130, 246, 0.1); border-radius: 6px; border-left: 3px solid #3b82f6;">
                            <div style="font-size: 11px; color: #8b949e; margin-bottom: 4px;">LARGEST FILE</div>
                            <div style="font-size: 13px; color: #c9d1d9; font-family: monospace;">${data.largest_file.name}</div>
                        </div>
                        ` : ''}
                        
                        ${data.recent_files && data.recent_files.length > 0 ? `
                        <div style="margin-bottom: 12px;">
                            <div style="font-size: 12px; color: #8b949e; margin-bottom: 6px;">Recent Files (${Math.min(data.recent_files.length, 5)}):</div>
                            <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                                ${data.recent_files.slice(0, 5).map(f => 
                                    `<span class="badge" style="background: #1e3a8a; font-size: 11px;" title="${formatBytes(f.size)}">${f.name}</span>`
                                ).join('')}
                            </div>
                        </div>
                        ` : ''}
                    </div>
                `;
            };

            container.innerHTML = `
                ${fs.data ? renderDirectory('Data Directory', fs.data) : ''}
                ${fs.cogs ? renderDirectory('Cogs Directory', fs.cogs) : ''}
                ${fs.extensions ? renderDirectory('Extensions Directory', fs.extensions) : ''}
                ${fs.botlogs ? renderDirectory('Botlogs Directory', fs.botlogs) : ''}
            `;
        }

        window.refreshFileSystem = () => {
            showNotification('Refreshing File System...', 'info');
            loadData();
        };

        let currentFileTree = {};
        let currentPath = '';
        let fileBrowserInitialized = false;
        let requestIdCounter = 0;
        let contextMenuPath = null;
        let contextMenuName = null;
        let contextMenuIsDir = false;
        function generateRequestId() {
            return `req_${Date.now()}_${++requestIdCounter}`;
        }

        function sendFileCommand(command, params = {}) {
            const requestId = generateRequestId();
            params.request_id = requestId;
            
            fetch('./send_command.php?token=' + TOKEN, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command, params })
            })
            .then(async r => {
                let payload = null;
                try {
                    payload = await r.json();
                } catch (_) {}
                if (!r.ok) {
                    const msg = interpretHttpError(r.status, payload, 'file');
                    throw new Error(msg);
                }
                return payload || {};
            })
            .catch(e => {
                console.error('File command send error:', e);
                showNotification(e.message || 'File operation failed.', 'error');
            });
            
            return requestId;
        }

        function updateFileTree(fileops) {
            if (fileops.type === 'list_dir') {
                currentFileTree[fileops.path.replace('./', '')] = { files: fileops.files, loaded: true };
            }
        }

        function renderFileBrowser(fs, fileops) {
            if (fileBrowserInitialized) return; // Don't re-render

            // Initialize with botlogs, data, cogs, extensions if available
            if (Object.keys(currentFileTree).length === 0) {
            if (fs.botlogs && fs.botlogs.exists) {
                currentFileTree['botlogs'] = { files: [], loaded: false };
            }
            if (fs.data && fs.data.exists) {
                currentFileTree['data'] = { files: [], loaded: false };
            }
            if (fs.cogs && fs.cogs.exists) {
                currentFileTree['cogs'] = { files: [], loaded: false };
            }
            if (fs.extensions && fs.extensions.exists) {
                currentFileTree['extensions'] = { files: [], loaded: false };
            }
            }

            // If we have fileops data, update the tree
            if (fileops) {
                updateFileTree(fileops);
            }

            renderBreadcrumb();
            renderFiles();
            initExplorer();
            initFileToolbar();
            fileBrowserInitialized = true;

            // Enable drag & drop upload for text files into the current directory
            const dropZone = document.getElementById('file-browser-content');
            if (dropZone && !dropZone._dragInitialized) {
                dropZone.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    dropZone.classList.add('file-drop-active');
                });
                dropZone.addEventListener('dragleave', (e) => {
                    if (e.target === dropZone) {
                        dropZone.classList.remove('file-drop-active');
                    }
                });
                dropZone.addEventListener('drop', (e) => {
                    e.preventDefault();
                    dropZone.classList.remove('file-drop-active');
                    const files = Array.from(e.dataTransfer?.files || []);
                    if (!files.length) return;

                    files.forEach(file => {
                        if (file.size > 10 * 1024 * 1024) {
                            showNotification(`Skipping ${file.name} (too large)`, 'error');
                            return;
                        }
                        const reader = new FileReader();
                        reader.onload = (evt) => {
                            const relPath = currentPath ? currentPath + '/' + file.name : file.name;
                            const fullPath = relPath.startsWith('./') ? relPath : './' + relPath;
                            sendCommand('write_file', { path: fullPath, content: evt.target.result });
                        };
                        reader.readAsText(file);
                    });

                    showNotification('Upload requested. Files will appear shortly.', 'success');
                    setTimeout(reloadCurrentDirectory, 1500);
                });
                dropZone._dragInitialized = true;
            }
            
            setTimeout(() => {
                ['data', 'botlogs'].forEach(dir => {
                    if (currentFileTree[dir] && !currentFileTree[dir].loaded) {
                        const fullPath = './' + dir;
                        const rid = sendFileCommand('list_dir', { path: fullPath });
                        
                        let retries = 0;
                        const poll = () => {
                            retries++;
                            fetch('monitor_data_fileops.json?t=' + Date.now())
                                .then(r => r.ok ? r.text() : null)
                                .then(text => {
                                    if (text) {
                                        try {
                                            const data = JSON.parse(text);
                                            if (data && data.type === 'list_dir' && 
                                                data.path === fullPath && 
                                                data.request_id === rid) {
                                                currentFileTree[dir] = { files: data.files, loaded: true };
                                                console.log(`Pre-loaded directory: ${dir}`);
                                            } else if (retries < 10) {
                                                setTimeout(poll, 1000);
                                            }
                                        } catch (e) {
                                            if (retries < 10) setTimeout(poll, 1000);
                                        }
                                    } else if (retries < 10) {
                                        setTimeout(poll, 1000);
                                    }
                                })
                                .catch(() => {
                                    if (retries < 10) setTimeout(poll, 1000);
                                });
                        };
                        setTimeout(poll, 2000 + (dir === 'botlogs' ? 2000 : 0));
                    }
                });
            }, 1000);
        }

        function getFiles(path) {
            let current = currentFileTree;
            const parts = path.split('/').filter(p => p);
            for(let part of parts) {
                current = current[part];
                if(!current) return [];
            }

            if(Array.isArray(current)) return current;

            const folders = [];
            const files = [];
            for(let key in current) {
                if(typeof current[key] === 'object' && !Array.isArray(current[key]) && key !== 'files' && key !== 'loaded') {
                    folders.push({ name: key, type: 'folder' });
                } else if (key === 'files' && Array.isArray(current[key])) {
                    return current[key];
                }
            }
            return [...folders, ...files];
        }

        function renderBreadcrumb() {
            const breadcrumb = document.getElementById('breadcrumb');
            const path = currentPath.split('/').filter(p => p);

            let html = '<span class="breadcrumb-icon"><svg width="14" height="14" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg"><path d="M3 4.5A1.5 1.5 0 0 1 4.5 3h3.382a1.5 1.5 0 0 1 1.06.44L10.94 5H15.5A1.5 1.5 0 0 1 17 6.5v7A1.5 1.5 0 0 1 15.5 15h-11A1.5 1.5 0 0 1 3 13.5v-9Z" fill="#38bdf8"/></svg></span><span class="crumb" onclick="navigateTo(-1)">Root</span>';
            if (path.length > 0) {
                html += '<span>/</span>';
            }

            html += path.map((part, i) => {
                const isLast = i === path.length - 1;
                return `<span class="crumb" onclick="navigateTo(${i})">${part}</span>${!isLast ? '<span>/</span>' : ''}`;
            }).join('');

            breadcrumb.innerHTML = html;
        }

        function renderFiles() {
            const list = document.getElementById('list');
            let files = [];

            if (currentPath === '') {
                const rootDirs = ['botlogs', 'data', 'cogs', 'extensions'];
                files = rootDirs.filter(dir => currentFileTree[dir]).map(dir => ({ name: dir, type: 'folder' }));
            } else {
                files = getFiles(currentPath);
            }

            let fileIndex = 0;
            list.innerHTML = files.map((f, i) => {
                if(f.type === 'folder' || f.type === 'dir') {
                    return `
                        <div class="file-row folder" onclick="openFolder('${f.name}')" oncontextmenu="openFileContextMenu(event, '${f.name}', true)">
                            <div class="file-name">${f.name}</div>
                            <div class="file-meta">Folder</div>
                        </div>
                    `;
                }
                const currentFileIndex = fileIndex++;
                return `
                    <div class="file-row" id="f-${currentFileIndex}" onclick="openFile(${currentFileIndex})" oncontextmenu="openFileContextMenu(event, '${f.name}', false)">
                        <div class="file-name">${f.name}</div>
                        <div class="file-meta">${f.size || 'File'}</div>
                    </div>
                `;
            }).join('');
        }

        function openFileContextMenu(event, name, isDir) {
            event.preventDefault();
            const menu = document.getElementById('file-context-menu');
            if (!menu) return;

            contextMenuName = name;
            contextMenuIsDir = !!isDir;
            const base = currentPath ? currentPath + '/' : '';
            const rel = base + name;
            contextMenuPath = rel.startsWith('./') ? rel : './' + rel;

            // Position relative to the File Browser tab so it follows the mouse precisely
            const container = document.getElementById('tab-files') || document.body;
            const rect = container.getBoundingClientRect();

            let x = event.clientX - rect.left;
            let y = event.clientY - rect.top;

            const menuRect = menu.getBoundingClientRect();
            const menuWidth = menuRect.width || 200;
            const menuHeight = menuRect.height || 120;

            // Clamp within the container
            const maxX = Math.max(0, rect.width - menuWidth - 8);
            const maxY = Math.max(0, rect.height - menuHeight - 8);
            if (x < 8) x = 8; else if (x > maxX) x = maxX;
            if (y < 8) y = 8; else if (y > maxY) y = maxY;

            menu.style.display = 'block';
            menu.style.left = x + 'px';
            menu.style.top = y + 'px';
        }

        function closeFileContextMenu() {
            const menu = document.getElementById('file-context-menu');
            if (!menu) return;
            menu.style.display = 'none';
            contextMenuPath = null;
            contextMenuName = null;
            contextMenuIsDir = false;
        }

        function contextRename() {
            if (!contextMenuPath || !contextMenuName) return;
            const newName = prompt('New name', contextMenuName);
            if (!newName || newName === contextMenuName) {
                closeFileContextMenu();
                return;
            }
            let baseDir = currentPath || '';
            const newRel = baseDir ? baseDir + '/' + newName : newName;
            const oldPath = contextMenuPath;
            const newPath = newRel.startsWith('./') ? newRel : './' + newRel;
            sendCommand('rename_file', { old_path: oldPath, new_path: newPath });
            showNotification('Rename requested', 'info');
            closeFileContextMenu();
            setTimeout(reloadCurrentDirectory, 800);
        }

        function contextMove() {
            if (!contextMenuPath || !contextMenuName) return;
            const targetDir = prompt(
                'Move to which directory?\\n\\n' +
                '- Path is relative to the bot root (same as File Browser).\\n' +
                '- Examples: data, data/config, cogs, botlogs/debug, ./extensions.\\n\\n' +
                'Leave empty to move back to root.',
                currentPath
            );
            if (targetDir === null) {
                closeFileContextMenu();
                return;
            }
            let base = (targetDir || '').trim();
            if (base.startsWith('./')) base = base.slice(2);
            if (base.startsWith('/')) base = base.slice(1);
            if (base.endsWith('/')) base = base.slice(0, -1);
            const newRel = base ? base + '/' + contextMenuName : contextMenuName;
            const oldPath = contextMenuPath;
            const newPath = newRel.startsWith('./') ? newRel : './' + newRel;
            sendCommand('rename_file', { old_path: oldPath, new_path: newPath });
            showNotification('Move requested', 'info');
            closeFileContextMenu();
            setTimeout(reloadCurrentDirectory, 800);
        }

        function contextDelete() {
            if (!contextMenuPath || !contextMenuName) return;
            const confirmed = confirm('Delete ' + contextMenuName + (contextMenuIsDir ? ' and all its contents?' : '?'));
            if (!confirmed) {
                closeFileContextMenu();
                return;
            }
            sendCommand('delete_path', { path: contextMenuPath });
            showNotification('Delete requested', 'warning');
            closeFileContextMenu();
            setTimeout(reloadCurrentDirectory, 800);
        }

        document.addEventListener('click', (e) => {
            const menu = document.getElementById('file-context-menu');
            if (!menu) return;
            if (menu.style.display === 'block' && !menu.contains(e.target)) {
                closeFileContextMenu();
            }
        });

        window.navigateTo = (depth) => {
            if (depth === -1) {
                currentPath = '';
            } else {
                const pathParts = currentPath.split('/').filter(p => p);
                currentPath = pathParts.slice(0, depth + 1).join('/');
            }
            renderBreadcrumb();
            renderFiles();
        };

        window.openFolder = (folderName) => {
            currentPath = currentPath ? currentPath + '/' + folderName : folderName;
            if (!currentFileTree[currentPath] || !currentFileTree[currentPath].loaded) {
                loadDirectory(currentPath);
            } else {
                renderBreadcrumb();
                renderFiles();
            }
        };

        function reloadCurrentDirectory() {
            if (currentPath) {
                loadDirectory(currentPath);
            } else {
                renderBreadcrumb();
                renderFiles();
            }
        }

        function createNewFile() {
            const baseName = prompt('New file name (e.g. notes.txt or my_extension.py)');
            if (!baseName) return;
            const relPath = currentPath ? currentPath + '/' + baseName : baseName;
            const fullPath = relPath.startsWith('./') ? relPath : './' + relPath;
            sendCommand('write_file', { path: fullPath, content: '' });
            showNotification('File created', 'success');
            setTimeout(reloadCurrentDirectory, 800);
        }

        function createNewFolder() {
            const baseName = prompt('New folder name');
            if (!baseName) return;
            const relPath = currentPath ? currentPath + '/' + baseName : baseName;
            const fullPath = relPath.startsWith('./') ? relPath : './' + relPath;
            sendCommand('create_dir', { path: fullPath });
            showNotification('Folder creation requested', 'success');
            setTimeout(reloadCurrentDirectory, 800);
        }

        function initExplorer() {
            const fileBrowser = document.getElementById('file-browser-content');
            if (!fileBrowser) {
                console.error('[EDITOR] ERROR: file-browser-content container not found');
                return;
            }

            const resizer = fileBrowser.querySelector('#resize') || document.getElementById('resize');
            const pane = fileBrowser.querySelector('#pane') || document.getElementById('pane');
            const unit = fileBrowser.querySelector('.explorer-unit') || document.querySelector('#tab-files .explorer-unit');

            if (!resizer || !pane || !unit) {
                console.error('[EDITOR] ERROR: Missing explorer elements in File Browser tab');
                return;
            }

            resizer.addEventListener('mousedown', (e) => {
                e.preventDefault();
                document.body.classList.add('dragging');

                const startX = e.clientX;
                const startWidth = pane.offsetWidth || 320;

                function doDrag(e) {
                    e.preventDefault();
                    const delta = e.clientX - startX;
                    const proposed = startWidth + delta;
                    const minWidth = 220;  // let user go quite narrow
                    const maxWidth = Math.max(320, unit.offsetWidth - 320); // leave room for editor
                    const newWidth = Math.min(Math.max(proposed, minWidth), maxWidth);
                    pane.style.width = newWidth + 'px';
                }

                function stopDrag() {
                    document.body.classList.remove('dragging');
                    document.removeEventListener('mousemove', doDrag);
                    document.removeEventListener('mouseup', stopDrag);
                }

                document.addEventListener('mousemove', doDrag);
                document.addEventListener('mouseup', stopDrag);
            });
        }

        function initFileToolbar() {
            const toggle = document.getElementById('file-toolbar-toggle');
            const menu = document.getElementById('file-toolbar-menu');
            if (!toggle || !menu || toggle._initialized) return;
            toggle._initialized = true;

            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                const isOpen = menu.classList.contains('open');
                menu.classList.toggle('open', !isOpen);
                toggle.setAttribute('aria-expanded', String(!isOpen));
            });

            document.addEventListener('click', (e) => {
                if (!menu.classList.contains('open')) return;
                if (e.target === toggle || menu.contains(e.target)) return;
                menu.classList.remove('open');
                toggle.setAttribute('aria-expanded', 'false');
            });
        }

        window.setView = (mode, btn) => {
            const grid = document.getElementById('list');
            if (!grid) return;
            const group = btn && btn.parentElement;
            if (group) {
                group.querySelectorAll('button').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            }
            grid.className = `file-grid ${mode}-mode`;
            const menu = document.getElementById('file-toolbar-menu');
            const toggle = document.getElementById('file-toolbar-toggle');
            if (menu && toggle) {
                menu.classList.remove('open');
                toggle.setAttribute('aria-expanded', 'false');
            }
        };

        window.refreshFileBrowser = () => {
            showNotification('Refreshing file browser...', 'info');
            reloadCurrentDirectory();
        };

        window.openFile = (fid) => {
            console.log(`[EDITOR] openFile called with fid: ${fid}`);
            
            const files = getFiles(currentPath).filter(f => f.type === 'file');
            console.log(`[EDITOR] Found ${files.length} files`);
            
            const file = files[fid];
            
            if (!file) {
                console.error(`[EDITOR] ERROR: No file at index ${fid}. Total files: ${files.length}`);
                console.log('[EDITOR] Available files:', files);
                console.log('[EDITOR] Current path:', currentPath);
                showNotification('Error opening file', 'error');
                return;
            }

            console.log(`[EDITOR] Opening file: ${file.name}`);

            const fileBrowser = document.getElementById('file-browser-content');
            const unit = (fileBrowser && fileBrowser.querySelector('.explorer-unit')) || document.querySelector('#tab-files .explorer-unit');
            const name = document.getElementById('fileName');
            const text = document.getElementById('fileContent');
            const editorPane = (fileBrowser && fileBrowser.querySelector('.editor-pane')) || document.querySelector('#tab-files .editor-pane');
            const filePane = (fileBrowser && fileBrowser.querySelector('.file-pane')) || document.querySelector('#tab-files .file-pane');

            console.log('[EDITOR] Element check:', {
                unit: !!unit,
                name: !!name,
                text: !!text,
                editorPane: !!editorPane,
                filePane: !!filePane
            });

            if (!unit || !name || !text || !editorPane || !filePane) {
                console.error('[EDITOR] ERROR: Missing editor elements!');
                showNotification('Editor not initialized', 'error');
                return;
            }

            console.log('[EDITOR] All elements found, proceeding...');

            unit.querySelectorAll('.file-row').forEach(r => r.classList.remove('active'));
            const rows = unit.querySelectorAll('.file-row:not(.folder)');
            if(rows[fid]) rows[fid].classList.add('active');

            name.innerText = file.name;
            const placeholder = `// Loading ${file.name}...\\n\\n// Please wait while content loads...`;
            text.value = addLineNumbers(placeholder);
            
            console.log('[EDITOR] Adding editor-open class to:', unit);








            console.log('[EDITOR] Adding editor-open class to:', unit);
            unit.classList.add('editor-open');

            // WAIT for the unit to have actual width before proceeding
            function waitForWidth(attempt = 0) {
                if (unit.offsetWidth > 0) {
                    console.log('[EDITOR] ✅ Unit has width:', unit.offsetWidth);
                    
                    console.log('[EDITOR] FORCING file-pane width to 420px...');
                    if (!filePane.style.width) {
                        filePane.style.width = '420px';
                    }
                    filePane.style.flexShrink = '0';
                    
                    console.log('[EDITOR] FORCING editor-pane to be visible with inline styles...');
                    editorPane.style.display = 'flex';
                    editorPane.style.flex = '1';
                    
                    console.log('[EDITOR] ✅ Editor should be visible now!');
                } else if (attempt < 20) {
                    console.log('[EDITOR] ⏳ Waiting for width, attempt', attempt + 1);
                    setTimeout(() => waitForWidth(attempt + 1), 50);
                } else {
                    console.error('[EDITOR] ❌ Unit never got width after 1 second!');
                }
            }

            waitForWidth();
            
            setTimeout(() => {
                console.log('[EDITOR] Scrolling editor into view...');
                editorPane.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 100);

            const filePath = currentPath ? currentPath + '/' + file.name : file.name;
            console.log(`[EDITOR] Loading file from path: ${filePath}`);
            loadFile(filePath);
        };
        
        function addLineNumbers(content) {
            const lines = content.split('\\n');
            const maxDigits = String(lines.length).length;
            return lines.map((line, i) => {
                const lineNum = String(i + 1).padStart(maxDigits, ' ');
                return `${lineNum} | ${line}`;
            }).join('\\n');
        }
        
        function stripLineNumbers(content) {
            return content.split('\\n').map(line => {
                const pipeIndex = line.indexOf(' | ');
                return pipeIndex !== -1 ? line.substring(pipeIndex + 3) : line;
            }).join('\\n');
        }

        window.closeEditor = () => {
            const fileBrowser = document.getElementById('file-browser-content');
            const unit = (fileBrowser && fileBrowser.querySelector('.explorer-unit')) || document.querySelector('#tab-files .explorer-unit');
            const pane = document.getElementById('pane');
            const editorPane = (fileBrowser && fileBrowser.querySelector('.editor-pane')) || document.querySelector('#tab-files .editor-pane');
            const filePane = (fileBrowser && fileBrowser.querySelector('.file-pane')) || document.querySelector('#tab-files .file-pane');
            
            unit.classList.remove('editor-open');
            
            if (pane) pane.style.width = "";
            
            if (filePane) {
                filePane.style.width = '';
                filePane.style.flexShrink = '';
            }
            
            if (editorPane) {
                editorPane.style.display = '';
                editorPane.style.flex = '';
            }
            
            unit.querySelectorAll('.file-row').forEach(r => r.classList.remove('active'));
        };

        window.jumpEditorScroll = () => {
            const text = document.getElementById('fileContent');
            if (!text) return;

            const threshold = 16;
            const atBottom = text.scrollTop + text.clientHeight >= text.scrollHeight - threshold;

            if (atBottom) {
                text.scrollTop = 0;
            } else {
                text.scrollTop = text.scrollHeight;
            }
        };

        window.save = () => {
            const text = document.getElementById('fileContent');
            const fileName = document.getElementById('fileName').innerText;
            const path = currentPath ? currentPath + '/' + fileName : fileName;
            const fullPath = path.startsWith('./') ? path : './' + path;
            const contentWithoutLineNumbers = stripLineNumbers(text.value);
            sendCommand('write_file', { path: fullPath, content: contentWithoutLineNumbers });
            showNotification('File saved successfully', 'success');
            closeEditor();
        };

        function promptRenameCurrentFile() {
            const fileNameEl = document.getElementById('fileName');
            if (!fileNameEl) return;
            const currentName = fileNameEl.innerText;
            const currentRel = currentPath ? currentPath + '/' + currentName : currentName;
            const newName = prompt('New file name', currentName);
            if (!newName || newName === currentName) return;
            const newRel = currentPath ? currentPath + '/' + newName : newName;
            const oldPath = currentRel.startsWith('./') ? currentRel : './' + currentRel;
            const newPath = newRel.startsWith('./') ? newRel : './' + newRel;
            sendCommand('rename_file', { old_path: oldPath, new_path: newPath });
            showNotification('Rename requested', 'info');
            closeEditor();
            setTimeout(reloadCurrentDirectory, 800);
        }

        function goToPath(path) {
            currentPath = path;
            if (path === '') {
                // Show root directories
                renderFiles();
            } else {
                // Load and show the directory
                loadDirectory(path);
            }
            renderBreadcrumb();
        }

        function loadDirectory(path) {
            const list = document.getElementById('list');
            if (list) {
                list.innerHTML = '<div style="padding: 40px; text-align: center; color: #8b949e;"><div style="font-size: 18px; margin-bottom: 8px;">Loading directory...</div><div style="font-size: 13px;">Please wait</div></div>';
            }
            
            const fullPath = path.startsWith('./') ? path : './' + path;
            const requestId = sendFileCommand('list_dir', { path: fullPath });
            
            let retries = 0;
            const maxRetries = 15;
            const poll = () => {
                retries++;
                fetch('monitor_data_fileops.json?t=' + Date.now())
                    .then(r => r.ok ? r.text() : null)
                    .then(text => {
                        if (!text) {
                            if (retries < maxRetries) setTimeout(poll, 1000);
                            return;
                        }
                        try {
                            const data = JSON.parse(text);
                            if (data && data.type === 'list_dir' && 
                                data.path === fullPath && 
                                data.request_id === requestId) {
                                currentFileTree[path] = { files: data.files, loaded: true };
                                currentPath = path;
                                renderFiles();
                                renderBreadcrumb();
                                showNotification('Directory loaded successfully', 'success');
                            } else if (retries < maxRetries) {
                                setTimeout(poll, 1000);
                            }
                        } catch (e) {
                            if (retries < maxRetries) setTimeout(poll, 1000);
                        }
                    })
                    .catch(err => {
                        if (retries < maxRetries) setTimeout(poll, 1000);
                        else {
                            if (list) list.innerHTML = '<div style="padding: 40px; text-align: center; color: #ef4444;">Failed to load directory</div>';
                            showNotification('Failed to load directory', 'error');
                        }
                    });
            };
            setTimeout(poll, 500);
        }

        function loadFile(path) {
            console.log(`[LOADFILE] Starting to load: ${path}`);
            showNotification('Loading file...', 'info');
            const fullPath = path.startsWith('./') ? path : './' + path;
            console.log(`[LOADFILE] Full path: ${fullPath}`);
            const requestId = sendFileCommand('read_file', { path: fullPath });
            console.log(`[LOADFILE] Request ID: ${requestId}`);
            
            let retries = 0;
            const maxRetries = 15;
            const poll = () => {
                retries++;
                console.log(`[LOADFILE] Poll attempt ${retries}/${maxRetries}`);
                fetch('monitor_data_fileops.json?t=' + Date.now())
                    .then(r => {
                        console.log(`[LOADFILE] Fetch response:`, r.ok, r.status);
                        return r.ok ? r.text() : null;
                    })
                    .then(text => {
                        if (!text) {
                            console.log(`[LOADFILE] No text response, retrying...`);
                            if (retries < maxRetries) setTimeout(poll, 1000);
                            else console.error('[LOADFILE] Max retries reached, giving up');
                            return;
                        }
                        try {
                            const data = JSON.parse(text);
                            console.log(`[LOADFILE] Parsed data:`, {
                                type: data.type,
                                path: data.path,
                                requestId: data.request_id,
                                contentLength: data.content?.length || 0
                            });
                            
                            if (data && data.type === 'read_file' && 
                                data.path === fullPath && 
                                data.request_id === requestId) {
                                console.log(`[LOADFILE] SUCCESS! Loading content into editor...`);
                                const textArea = document.getElementById('fileContent');
                                textArea.value = addLineNumbers(data.content);
                                textArea.scrollTop = 0;
                                console.log(`[LOADFILE] Content loaded, ${data.content.length} bytes`);
                                showNotification('File loaded successfully', 'success');
                            } else {
                                console.log(`[LOADFILE] Data mismatch, waiting for correct response...`);
                                if (retries < maxRetries) setTimeout(poll, 1000);
                            }
                        } catch (e) {
                            console.error(`[LOADFILE] Parse error:`, e);
                            if (retries < maxRetries) setTimeout(poll, 1000);
                        }
                    })
                    .catch(err => {
                        console.error(`[LOADFILE] Fetch error:`, err);
                        if (retries < maxRetries) {
                            setTimeout(poll, 1000);
                        } else {
                            console.error('[LOADFILE] Max retries reached after errors');
                            showNotification('Failed to load file - check console', 'error');
                        }
                    });
            };
            setTimeout(poll, 500);
        }

        function showFileModal(path, content) {
            const fileBrowser = document.getElementById('file-browser-content');
            const unit = (fileBrowser && fileBrowser.querySelector('.explorer-unit')) || document.querySelector('#tab-files .explorer-unit');
            const name = document.getElementById('fileName');
            const text = document.getElementById('fileContent');

            const fileName = path.split('/').pop();

            name.innerText = fileName;
            text.value = content;
            if (unit) {
                unit.classList.add('editor-open');
            }
        }


        let selectedChatGuildId = null;
        let selectedChatChannelId = null;
        let chatMessageHistory = [];

        function appendChatLog(entry) {
            chatMessageHistory.push(entry);
            const log = document.getElementById('chat-message-log');
            if (!log) return;
            log.innerHTML = chatMessageHistory.map(e => `
                <div style="margin-bottom:6px; font-size:13px;">
                    <span style="color:#64748b;">[${new Date(e.timestamp).toLocaleTimeString()}]</span>
                    <span style="color:#38bdf8; font-weight:600;">${e.guild || ''} #${e.channel || ''}</span>:
                    <span style="color:#e5e7eb;">${e.content}</span>
                </div>
            `).join('');
            log.scrollTop = log.scrollHeight;
        }

        function renderChatConsole(botInfo) {
            const guilds = botInfo.guilds_detail || [];
            const guildContainer = document.getElementById('chat-guilds');
            const channelContainer = document.getElementById('chat-channels');
            const subtitle = document.getElementById('chat-channel-subtitle');
            if (!guildContainer || !channelContainer) return;

            if (!guilds.length) {
                guildContainer.innerHTML = '<div class="empty-state">Bot is not in any servers or guild data is unavailable.</div>';
                channelContainer.innerHTML = '<div class="empty-state">No channels to show.</div>';
                if (subtitle) subtitle.textContent = 'No channel selected';
                return;
            }

            guildContainer.innerHTML = guilds.map(g => `
                <div class="file-row" onclick="selectChatGuild('${g.id}')" data-guild-id="${g.id}">
                    <div class="file-name">${g.name}</div>
                    <div class="file-meta">${g.member_count || 0} members</div>
                </div>
            `).join('');

            if (!selectedChatGuildId && guilds.length) {
                selectedChatGuildId = guilds[0].id;
            }
            selectChatGuild(selectedChatGuildId, false);
        }

        function renderGuilds(guildsDetail) {
            const container = document.getElementById('guilds-list');
            if (!container) return;
            const rows = Array.isArray(guildsDetail) ? guildsDetail : [];
            if (!rows.length) {
                container.innerHTML = '<div class="empty-state">Bot is not in any servers or guild data is unavailable.</div>';
                return;
            }
            container.classList.add('guilds-grid');
            container.innerHTML = rows.map(g => {
                const members = g.member_count || 0;
                const ownerId = g.owner_id || '';
                const ownerName = g.owner || '';
                const ownerLabel = ownerName || ownerId || 'Unknown';
                const joined = g.joined_at ? new Date(g.joined_at).toLocaleString() : 'Unknown';
                let actionsHtml = '<span style="font-size:12px;color:var(--text-secondary);">No permission</span>';
                if (typeof LM_PERMS !== 'undefined' && LM_PERMS.control_guilds) {
                    const safeName = (g.name || '').replace(/"/g, '&quot;');
                    actionsHtml = `<button class="button button-danger button-compact" onclick="confirmLeaveGuild('${g.id}', '${safeName}')">Leave</button>`;
                }
                const safeNameDisplay = g.name || 'Unknown server';
                return `
                    <div class="guild-card">
                        <div class="guild-card-header">
                            <div class="guild-card-name">${safeNameDisplay}</div>
                            <div class="guild-card-members">${members.toLocaleString()} members</div>
                        </div>
                        <div class="guild-card-meta">
                            <div class="guild-card-meta-row">
                                <div class="guild-meta-label">Server ID</div>
                                <div class="guild-meta-value mono">${g.id || ''}</div>
                            </div>
                            <div class="guild-card-meta-row">
                                <div class="guild-meta-label">Owner</div>
                                <div class="guild-meta-value">${ownerLabel}</div>
                            </div>
                            <div class="guild-card-meta-row">
                                <div class="guild-meta-label">Joined</div>
                                <div class="guild-meta-value">${joined}</div>
                            </div>
                        </div>
                        <div class="guild-card-actions">
                            ${actionsHtml}
                        </div>
                    </div>
                `;
            }).join('');
        }

        window.confirmLeaveGuild = function (guildId, guildName) {
            if (typeof LM_PERMS !== 'undefined' && !LM_PERMS.control_guilds) {
                showNotification('You do not have permission to make the bot leave servers.', 'error');
                return;
            }
            const name = guildName || guildId;
            if (!confirm(`Make the bot leave the server "${name}"?`)) {
                return;
            }
            sendCommand('leave_guild', { guild_id: guildId });
        };

        window.selectChatGuild = (guildId, clearLog = true) => {
            selectedChatGuildId = guildId;
            const guilds = (currentData?.bot?.guilds_detail) || [];
            const g = guilds.find(x => x.id == guildId);
            const channelContainer = document.getElementById('chat-channels');
            const subtitle = document.getElementById('chat-channel-subtitle');
            if (!g || !channelContainer) return;

            document.querySelectorAll('#chat-guilds .file-row').forEach(row => {
                if (String(row.getAttribute('data-guild-id')) === String(guildId)) {
                    row.classList.add('active');
                } else {
                    row.classList.remove('active');
                }
            });

            const channels = g.text_channels || [];
            if (!channels.length) {
                channelContainer.innerHTML = '<div class="empty-state">No text channels in this server.</div>';
                if (subtitle) subtitle.textContent = `${g.name} — no text channels`;
                return;
            }

            channelContainer.innerHTML = channels.map(ch => `
                <div class="file-row" onclick="selectChatChannel('${g.id}', '${ch.id}')" data-channel-id="${ch.id}">
                    <div class="file-name">#${ch.name}</div>
                </div>
            `).join('');

            if (subtitle) subtitle.textContent = 'Select a channel to start chatting as the bot';
            if (clearLog) {
                chatMessageHistory = [];
                const log = document.getElementById('chat-message-log');
                if (log) log.innerHTML = '';
            }
        };

        window.selectChatChannel = (guildId, channelId) => {
            selectedChatGuildId = guildId;
            selectedChatChannelId = channelId;
            const guilds = (currentData?.bot?.guilds_detail) || [];
            const g = guilds.find(x => x.id == guildId);
            const ch = g ? (g.text_channels || []).find(c => c.id == channelId) : null;
            const subtitle = document.getElementById('chat-channel-subtitle');
            if (subtitle && ch && g) {
                subtitle.textContent = `${g.name} — #${ch.name}`;
            }
            document.querySelectorAll('#chat-channels .file-row').forEach(row => {
                if (String(row.getAttribute('data-channel-id')) === String(channelId)) {
                    row.classList.add('active');
                } else {
                    row.classList.remove('active');
                }
            });
        };

        window.sendChatMessage = () => {
            if (!selectedChatChannelId) {
                showNotification('Select a channel first.', 'error');
                return;
            }
            const input = document.getElementById('chat-message-input');
            if (!input) return;
            const content = input.value.trim();
            if (!content) return;

            sendCommand('send_chat_message', {
                guild_id: selectedChatGuildId,
                channel_id: selectedChatChannelId,
                content
            });

            const guilds = (currentData?.bot?.guilds_detail) || [];
            const g = guilds.find(x => x.id == selectedChatGuildId);
            const ch = g ? (g.text_channels || []).find(c => c.id == selectedChatChannelId) : null;
            appendChatLog({
                timestamp: new Date().toISOString(),
                guild: g ? g.name : '',
                channel: ch ? ch.name : '',
                content
            });

            input.value = '';
        };

        window.requestChatHistory = () => {
            if (!selectedChatChannelId) {
                showNotification('Select a channel first.', 'error');
                return;
            }
            sendCommand('request_chat_history', {
                guild_id: selectedChatGuildId,
                channel_id: selectedChatChannelId
            });
            showNotification('Requested chat data (BETA) for this channel.', 'info');
        };

        window.togglePluginEnforcement = (mode, enabled) => {
            const parsedEnabled = String(enabled) === 'true';
            sendCommand('plugin_registry_set_enforcement', { mode, enabled: parsedEnabled });
            showNotification(`Plugin enforcement updated: ${mode} = ${parsedEnabled ? 'On' : 'Off'}`, 'info');
            setTimeout(loadData, 1500);
        };

        window.toggleSlashLimiterDebug = () => {
            const current = currentData?.slash_limiter?.debug_mode ? true : false;
            const next = !current;
            sendCommand('slash_limiter_set_debug', { enabled: next });
            showNotification(`Slash limiter debug ${next ? 'enabled' : 'disabled'}`, 'info');
            setTimeout(loadData, 1500);
        };

        window.toggleAutoReload = () => {
            const current = currentData?.core_settings?.auto_reload ? true : false;
            const next = !current;
            sendCommand('set_auto_reload', { enabled: next });
            showNotification(`Auto reload ${next ? 'enabled' : 'disabled'}`, 'info');
            setTimeout(loadData, 1500);
        };

        window.toggleExtensionsAutoLoad = () => {
            const current = currentData?.core_settings?.extensions_auto_load ? true : false;
            const next = !current;
            sendCommand('set_extensions_auto_load', { enabled: next });
            showNotification(`Extensions auto-load on startup ${next ? 'enabled' : 'disabled'}`, 'info');
            setTimeout(loadData, 1500);
        };

        function renderEvents(events) {
            const container = document.getElementById('events-list');
            document.getElementById('events-count').textContent = events.length + ' Events';
            
            if (events.length === 0) {
                container.innerHTML = '<div class="empty-state">No events recorded</div>';
                return;
            }

            container.innerHTML = events.slice().reverse().slice(0, 50).map((event, index) => `
                <div class="card" style="cursor: default;">
                    <div class="card-header">
                        <div>
                            <div class="card-title">${event.type}</div>
                            <div class="card-subtitle">${formatTime(event.timestamp)}</div>
                        </div>
                        <span class="badge badge-info">${event.type}</span>
                    </div>
                    ${event.details && Object.keys(event.details).length > 0 ? `
                    <div class="card-body" style="display: block;">
                        ${Object.entries(event.details).map(([key, value]) => `
                            <div class="property">
                                <span class="property-label">${key}</span>
                                <span class="property-value" style="font-size: 12px; word-break: break-all;">${JSON.stringify(value).substring(0, 100)}</span>
                            </div>
                        `).join('')}
                    </div>
                    ` : ''}
                </div>
            `).join('');
        }

        function toggleHeroInfo() {
            const panel = document.getElementById('hero-info-panel');
            if (!panel) return;
            panel.classList.toggle('visible');
        }

        function renderSystemDetails(data) {
            const container = document.getElementById('system-details');
            
            // LEFT COLUMN: overview cards
            let left = `
                <div class="card" style="cursor: default;">
                    <div class="card-title">Bot Information</div>
                    <div class="card-body" style="display: block;">
                        <div class="property">
                            <span class="property-label">User</span>
                            <span class="property-value">${data.bot.user}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Cogs Loaded</span>
                            <span class="property-value">${data.bot.cogs_loaded}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Extensions</span>
                            <span class="property-value">${data.bot.extensions_loaded}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">User Extensions</span>
                            <span class="property-value">${data.bot.user_extensions}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Framework Cogs</span>
                            <span class="property-value">${data.bot.framework_cogs}</span>
                        </div>
                    </div>
                </div>

                <div class="card" style="cursor: default;">
                    <div class="card-title">System Resources</div>
                    <div class="card-body" style="display: block;">
                        <div class="property">
                            <span class="property-label">CPU User Time</span>
                            <span class="property-value">${Math.round(data.system.cpu_user_time || 0)}s</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Memory Percent</span>
                            <span class="property-value">${(data.system.memory_percent || 0).toFixed(2)}%</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Threads</span>
                            <span class="property-value">${data.system.threads}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Open Files</span>
                            <span class="property-value">${data.system.open_files}</span>
                        </div>
                        <div class="property">
                            <span class="property-label">Connections</span>
                            <span class="property-value">${data.system.connections}</span>
                        </div>
                    </div>
                </div>
            `;
            // Framework health
            if (data.health) {
                const errorRate = data.health.error_rate ?? 0;
                const statusLabel = data.health.status || 'unknown';
                const statusBadgeClass = statusLabel === 'healthy' ? 'badge-success' : (statusLabel === 'degraded' ? 'badge-warning' : 'badge-danger');

                left += `
                    <div class="card" style="cursor: default;">
                        <div class="card-title">Framework Health</div>
                        <div class="card-body" style="display: block;">
                            <div class="property">
                                <span class="property-label">Status</span>
                                <span class="property-value"><span class="badge ${statusBadgeClass}">${statusLabel}</span></span>
                            </div>
                            <div class="property">
                                <span class="property-label">Error Rate</span>
                                <span class="property-value">${errorRate.toFixed(2)}%</span>
                            </div>
                            <div class="property">
                                <span class="property-label">Event Loop Lag</span>
                                <span class="property-value">${(data.health.event_loop_lag_ms || 0).toFixed(2)} ms</span>
                            </div>
                            <div class="property">
                                <span class="property-label">Consecutive Write Failures</span>
                                <span class="property-value">${data.health.consecutive_write_failures || 0}</span>
                            </div>
                        </div>
                    </div>
                `;
            }

            // Slash limiter card
        if (data.slash_limiter) {
            left += `
                    <div class="card" style="cursor: default;">
                        <div class="card-title">Slash Command Limiter</div>
                        <div class="card-body" style="display: block;">
                            <div class="property">
                                <span class="property-label">Status</span>
                                <span class="badge badge-${data.slash_limiter.status === 'safe' ? 'success' : data.slash_limiter.status === 'warning' ? 'warning' : 'danger'}">${data.slash_limiter.status}</span>
                            </div>
                            <div class="property">
                                <span class="property-label">Current / Limit</span>
                                <span class="property-value">${data.slash_limiter.current} / ${data.slash_limiter.limit}</span>
                            </div>
                            <div style="margin-top: 8px;">
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: ${data.slash_limiter.percentage}%"></div>
                                </div>
                            </div>
                            <div class="property" style="margin-top: 8px;">
                                <span class="property-label">Blocked</span>
                                <span class="property-value">${data.slash_limiter.blocked}</span>
                            </div>
                            <div class="property">
                                <span class="property-label">Converted</span>
                                <span class="property-value">${data.slash_limiter.converted}</span>
                            </div>
                        </div>
                    </div>
                `;
            }

            // Event hooks metrics
            if (data.event_hooks && data.event_hooks.metrics) {
                left += `
                    <div class="card" style="cursor: default;">
                        <div class="card-title">Event Hooks Metrics</div>
                        <div class="card-body" style="display: block;">
                            <div class="property">
                                <span class="property-label">Total Emissions</span>
                                <span class="property-value">${data.event_hooks.metrics.total_emissions || 0}</span>
                            </div>
                            <div class="property">
                                <span class="property-label">Total Executions</span>
                                <span class="property-value">${data.event_hooks.metrics.total_executions || 0}</span>
                            </div>
                            <div class="property">
                                <span class="property-label">Total Failures</span>
                                <span class="property-value">${data.event_hooks.metrics.total_failures || 0}</span>
                            </div>
                            <div class="property">
                                <span class="property-label">Queue Size</span>
                                <span class="property-value">${data.event_hooks.queue_size || 0}</span>
                            </div>
                        </div>
                    </div>
                `;
            }

            // Core settings card (auto reload, auto load)
            if (data.core_settings && (Object.keys(data.core_settings).length > 0)) {
                left += `
                    <div class="card" style="cursor: default;">
                        <div class="card-title">Core Settings</div>
                        <div class="card-body" style="display: block;">
                            <div class="property">
                                <span class="property-label">Auto Reload Extensions</span>
                                <span class="property-value">
                                    <span class="badge ${data.core_settings.auto_reload ? 'badge-success' : 'badge-warning'}">${data.core_settings.auto_reload ? 'On' : 'Off'}</span>
                                </span>
                            </div>
                            <div class="property">
                                <span class="property-label">Auto Load Extensions (Startup)</span>
                                <span class="property-value">
                                    <span class="badge ${data.core_settings.extensions_auto_load ? 'badge-success' : 'badge-warning'}">${data.core_settings.extensions_auto_load ? 'On' : 'Off'}</span>
                                </span>
                            </div>
                            <div class="button-group">
                                <button class="button button-secondary button-compact" onclick="toggleAutoReload()">Toggle Auto Reload</button>
                                <button class="button button-secondary button-compact" onclick="toggleExtensionsAutoLoad()">Toggle Auto Load</button>
                            </div>
                        </div>
                    </div>
                `;
            }

            // RIGHT COLUMN: dedicated Atomic FS / Active Locks card
            let right = '';
            if (data.atomic_fs) {
                const locks = data.atomic_fs.locks || [];
                right = `
                    <div class="card" style="cursor: default;">
                        <div class="card-title">Active File Locks</div>
                        <div class="card-subtitle" style="margin-top: 4px; font-size: 12px; color: var(--text-secondary);">
                            Hit rate ${data.atomic_fs.hit_rate}% • Cache ${data.atomic_fs.cache_size}/${data.atomic_fs.max_cache_size} • Active locks ${data.atomic_fs.active_locks}
                        </div>
                        <div class="card-body" style="display: block; max-height: 520px; overflow-y: auto;">
                            <div class="af-locks-header">
                                <span>Path</span>
                                <span>Status</span>
                                <span>Last Op</span>
                                <span>Last Used</span>
                                <span style="text-align:right;">Actions</span>
                            </div>
                            ${locks.map(lock => `
                                <div class="af-lock-row">
                                    <div class="af-lock-path" title="${lock.path}">${lock.path}</div>
                                    <div>
                                        <span class="af-lock-status-chip ${lock.locked ? 'af-lock-status-locked' : 'af-lock-status-idle'}">
                                            ${lock.locked ? 'Locked' : 'Idle'}
                                        </span>
                                    </div>
                                    <div>${lock.last_operation || 'n/a'}</div>
                                    <div style="font-size: 11px; color: var(--text-secondary);">
                                        ${lock.last_used ? formatTime(lock.last_used) : 'n/a'}
                                    </div>
                                    <div class="af-lock-actions">
                                        <button class="button button-secondary button-compact af-invalidate-lock" data-path="${lock.path}">Invalidate</button>
                                        <button class="button button-danger button-compact af-release-lock" data-path="${lock.path}">Force</button>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            const html = `
                <div class="system-grid">
                    <div class="system-main">
                        ${left}
                    </div>
                    <div class="system-locks">
                        ${right || '<div class="empty-state">Atomic file system metrics are not available.</div>'}
                    </div>
                </div>
            `;

            container.innerHTML = html;

            // Attach Atomic FS lock controls after rendering
            const invalidateButtons = container.querySelectorAll('.af-invalidate-lock');
            invalidateButtons.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const path = btn.getAttribute('data-path');
                    if (path) {
                        sendCommand('af_invalidate_cache_entry', { path });
                    }
                });
            });

            const releaseButtons = container.querySelectorAll('.af-release-lock');
            releaseButtons.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const path = btn.getAttribute('data-path');
                    if (path) {
                        sendCommand('af_force_release_lock', { path });
                    }
                });
            });
        }

        let retryCount = 0;
        const maxRetries = 10;
        let retryTimeout = null;
        let expandedCards = new Set();
        let searchState = {
            commands: ''
        };
        let isCommandPending = false;
        
        function openSectionHelp(section) {
            const map = {
                dashboard: {
                    title: 'Dashboard Overview',
                    body: 'High-level health, alerts, and quick actions. Start here to see if anything needs attention.',
                },
                commands: {
                    title: 'Commands Overview',
                    body: 'Shows every registered command with usage, errors, and how to invoke it. Sort and filter to find hotspots.',
                },
                plugins: {
                    title: 'Plugins & Extensions',
                    body: 'Each plugin corresponds to an extension. This view surfaces dependency issues, conflicts, and load times so you can keep your stack healthy.',
                },
                hooks: {
                    title: 'Event Hooks System',
                    body: 'Advanced event pipeline. Use this to see which hooks are running, how often, and where failures happen.',
                },
                filesystem: {
                    title: 'File System Overview',
                    body: 'Aggregate stats for data, cogs, extensions, and botlogs. Helps you spot growth and disk-heavy areas.',
                },
                files: {
                    title: 'File Browser',
                    body: 'Safe, live view into your bot files. Browse logs, configs, and cogs. Writes go through the bot so atomic FS rules still apply.',
                },
                chat: {
                    title: 'Chat Console',
                    body: 'Experimental console to talk as the bot and inspect recent messages. Use for quick diagnostics, not for full moderation.',
                },
                events: {
                    title: 'Recent Events',
                    body: 'Stream of high-level framework events (joins, errors, hook actions). Good for “what just happened?” questions.',
                },
                system: {
                    title: 'System Details',
                    body: 'Low-level metrics like event-loop lag, atomic FS locks, and slash command limiter state.',
                },
                roles: {
                    title: 'Roles & Access',
                    body: 'Owner-only panel to see which Discord IDs can access the dashboard and what role (OWNER / HELPER / VISITOR) they have.',
                },
                security: {
                    title: 'Security & Logs',
                    body: 'Owner-only audit view that shows logins, configuration changes, and other sensitive events. Backed by a SQLite audit_log table.',
                },
                guilds: {
                    title: 'Guilds / Servers',
                    body: 'Lists the servers the bot is in. With the right role, you can make the bot leave a guild from here.',
                },
                database: {
                    title: 'Database viewer',
                    body: 'Read-only viewer for the local dashboard.sqlite database (config, roles, audits).',
                },
                invite: {
                    title: 'Bot Invite Helper',
                    body: 'Generate OAuth2 invite URLs for your bot. Configure application ID, scopes (bot, applications.commands), and permissions. For advanced settings, use the Discord Developer Portal.',
                },
                marketplace: {
                    title: 'Extension/Plugin Marketplace',
                    body: 'BETA feature - Browse and download extensions directly from the ZygnalBot marketplace. Downloaded extensions are saved directly to ./extensions/ folder and can be automatically loaded. Requires ZygnalID activation for downloads.',
                },
                invite: {
                    title: 'Bot Invite Helper',
                    body: 'Generate Discord OAuth2 invite links for your bot. Customize the client ID, scopes, and permissions to create the perfect invite URL for adding your bot to servers.',
                },
            };
            const info = map[section] || { title: 'Section Help', body: 'This section provides additional monitoring information.' };
            openModal(info.title, `<p style="font-size:13px;color:var(--text-secondary);">${info.body}</p>`);
        }

        function showNotification(message, type = 'info') {
            const notification = document.createElement('div');
            notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 16px 24px;
                background: ${type === 'success' ? 'var(--success)' : type === 'error' ? 'var(--danger)' : 'var(--primary)'};
                color: white;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                z-index: 10000;
                animation: slideIn 0.3s ease;
                font-weight: 600;
            `;
            notification.textContent = message;
            document.body.appendChild(notification);
            
            setTimeout(() => {
                notification.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => notification.remove(), 300);
            }, 3000);
        }
        
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(400px); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(400px); opacity: 0; }
            }
        `;
        document.head.appendChild(style);

        // === Roles & Access (owner-only UI over owner_roles.php) ===
        let rolesTabInitialized = false;

        function loadRolesTab() {
            if (rolesTabInitialized) return;
            const container = document.getElementById('roles-content');
            if (!container) return;

            container.innerHTML = '<div class="loading">Loading roles from server...</div>';

            fetch('owner_roles.php?format=json', { credentials: 'include' })
                .then(async r => {
                    let data = null;
                    try {
                        data = await r.json();
                    } catch (_) {}
                    if (!r.ok) {
                        const msg = interpretHttpError(r.status, data, 'roles');
                        showNotification(msg, 'error');
                        throw new Error(msg);
                    }
                    return data || {};
                })
                .then(data => {
                    renderRolesTab(container, data);
                    rolesTabInitialized = true;
                })
                .catch(err => {
                    console.error('Roles load error:', err);
                    container.innerHTML = '<div class="empty-state">Unable to load roles. Make sure you are logged in as the dashboard owner.</div>';
                });
        }

        function renderRolesTab(container, data) {
            const users = data.users || [];
            const roles = data.roles || [];
            const ownerId = data.owner_discord_id || null;

            const VIEW_PERM_DEFS = [
                { key: 'view_dashboard', label: 'Dashboard' },
                { key: 'view_commands', label: 'Commands' },
                { key: 'view_plugins', label: 'Plugins & Extensions' },
                { key: 'view_hooks', label: 'Event Hooks' },
                { key: 'view_filesystem', label: 'File System Overview' },
                { key: 'view_files', label: 'File Browser' },
                { key: 'view_chat', label: 'Chat Console' },
                { key: 'view_events', label: 'Events' },
                { key: 'view_system', label: 'System Details' },
                { key: 'view_security', label: 'Security & Logs' },
                { key: 'view_guilds', label: 'Guilds / Servers' },
                { key: 'view_database', label: 'Database viewer' },
                { key: 'view_marketplace', label: 'Extension Marketplace (BETA)' },
                { key: 'view_invite', label: 'Bot Invite Helper' },
            ];

            const CONTROL_PERM_DEFS = [
                { key: 'control_core', label: 'Core actions (shutdown, diagnostics, locks)' },
                { key: 'control_plugins', label: 'Manage plugins & extensions (load/unload/reload)' },
                { key: 'control_hooks', label: 'Manage hooks (enable/disable/reset circuits)' },
                { key: 'control_files', label: 'Modify files (create/edit/delete/rename)' },
                { key: 'control_chat', label: 'Send messages via Chat Console' },
                { key: 'control_guilds', label: 'Manage guilds (leave servers)' },
                { key: 'control_database', label: 'Database write access (advanced)' },
                { key: 'control_backup', label: 'Create backups (dashboard/bot)' },
                { key: 'control_invite', label: 'Generate bot invite links' },
                { key: 'control_marketplace', label: 'Download & install marketplace extensions' },
            ];

            const OTHER_PERM_DEFS = [
                { key: 'export_logs', label: 'Export audit logs from Security tab' },
            ];

            const rolesOptions = roles.map(r => r.name).filter(Boolean);

            const rolesHtml = users.map(u => {
                const isOwner = u.role === 'OWNER';
                const disableRoleChange = isOwner;
                const disableDelete = isOwner;
                const allRoleNames = Array.from(new Set([...rolesOptions, u.role].filter(Boolean)));
                const roleOptionsHtml = allRoleNames.map(name => `<option value="${name}" ${u.role === name ? 'selected' : ''}>${name}</option>`).join('');
                const roleSelect = `
                    <select data-user-id="${u.id}" class="select role-select" ${disableRoleChange ? 'disabled' : ''}>
                        ${roleOptionsHtml}
                    </select>`;
                return `
                    <tr>
                        <td>${u.id}</td>
                        <td>${u.discord_user_id}</td>
                        <td>${u.display_name}</td>
                        <td>${roleSelect}</td>
                        <td>
                            <button class="button button-secondary button-compact" data-action="save-role" data-user-id="${u.id}" ${disableRoleChange ? 'disabled' : ''}>Save</button>
                            <button class="button button-danger button-compact" data-action="delete-user" data-user-id="${u.id}" ${disableDelete ? 'disabled' : ''}>Remove</button>
                        </td>
                    </tr>`;
            }).join('');

            container.innerHTML = `
                <div class="two-column-grid" style="align-items:flex-start;">
                    <div class="column-card">
                        <div class="column-header">
                            <div>
                                <div class="column-title">Users & Access</div>
                                <div class="column-subtitle">Assign Discord IDs to roles that can log in.</div>
                            </div>
                        </div>
                        <div class="card" style="cursor: default; margin-bottom: 16px;">
                            <div class="card-header">
                                <div class="card-title">Add User</div>
                            </div>
                            <div class="card-body" style="display:block;">
                                <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;">
                                    <input id="roles-add-discord" class="input-text" type="text" placeholder="Discord User ID (e.g. 123456789012345678)" style="flex:1;min-width:200px;" />
                                    <input id="roles-add-name" class="input-text" type="text" placeholder="Display name (optional)" style="flex:1;min-width:160px;" />
                                    <select id="roles-add-role" class="select">
                                        ${rolesOptions.map(name => `<option value="${name}">${name}</option>`).join('')}
                                    </select>
                                    <button class="button button-primary button-compact" id="roles-add-submit">Add</button>
                                </div>
                                <p class="hint" style="margin-top:8px;">OWNER is assigned on first claim and cannot be added here.</p>
                            </div>
                        </div>
                        <div class="card" style="cursor: default;">
                            <div class="card-header">
                                <div class="card-title">Existing Users</div>
                            </div>
                            <div class="card-body" style="display:block;overflow-x:auto;">
                                <table style="width:100%;border-collapse:collapse;font-size:12px;">
                                    <thead>
                                        <tr>
                                            <th style="text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);">ID</th>
                                            <th style="text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);">Discord ID</th>
                                            <th style="text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);">Name</th>
                                            <th style="text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);">Role</th>
                                            <th style="text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${rolesHtml || '<tr><td colspan="5" style="padding:10px 8px;color:var(--text-secondary);">No users registered yet. Use the form above to add one.</td></tr>'}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    <div class="column-card">
                        <div class="column-header">
                            <div>
                                <div class="column-title">Role Profiles</div>
                                <div class="column-subtitle">Create custom roles and fine-tune what they can do.</div>
                            </div>
                        </div>
                        <div id="roles-profiles"></div>
                    </div>
                </div>
            `;

            const addBtn = document.getElementById('roles-add-submit');
            if (addBtn) {
                addBtn.addEventListener('click', () => {
                    const did = (document.getElementById('roles-add-discord') || {}).value?.trim();
                    const name = (document.getElementById('roles-add-name') || {}).value?.trim();
                    const roleSel = document.getElementById('roles-add-role');
                    const role = roleSel ? roleSel.value : 'VISITOR';
                    if (!did) {
                        showNotification('Please provide a Discord user ID.', 'error');
                        return;
                    }
                    rolesApiRequest({ action: 'add', discord_user_id: did, display_name: name || did, role });
                });
            }

            container.querySelectorAll('button[data-action="save-role"]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const userId = btn.getAttribute('data-user-id');
                    const sel = container.querySelector(`select.role-select[data-user-id="${userId}"]`);
                    if (!sel) return;
                    const role = sel.value;
                    rolesApiRequest({ action: 'update_role', user_id: parseInt(userId, 10), role });
                });
            });

            container.querySelectorAll('button[data-action="delete-user"]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const userId = btn.getAttribute('data-user-id');
                    if (!confirm('Remove this user from dashboard access?')) return;
                    rolesApiRequest({ action: 'delete', user_id: parseInt(userId, 10) });
                });
            });

            // ---- Role profiles UI ----
            const profilesContainer = document.getElementById('roles-profiles');
            if (!profilesContainer) return;

            const builtin = roles.filter(r => r.system);
            const custom = roles.filter(r => !r.system);

            let html = '';
            if (builtin.length) {
                html += `
                    <div class="card" style="cursor: default; margin-bottom: 12px;">
                        <div class="card-header">
                            <div class="card-title">Built-in Roles</div>
                        </div>
                        <div class="card-body" style="display:block;">
                            <ul style="font-size:13px;color:var(--text-secondary);padding-left:18px;">
                                ${builtin.map(r => `<li><strong>${r.name}</strong> — ${r.description || ''}</li>`).join('')}
                            </ul>
                            <p style="font-size:11px;color:var(--text-secondary);margin-top:6px;">These roles define the base behavior. Custom roles inherit from them.</p>
                        </div>
                    </div>
                `;
            }

            html += `
                <div class="card" style="cursor: default; margin-bottom: 12px;">
                    <div class="card-header">
                        <div class="card-title">Create Role</div>
                    </div>
                    <div class="card-body" style="display:block;">
                        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;">
                            <input id="role-new-name" class="input-text" type="text" placeholder="Role name (e.g. LOGS_ONLY)" style="flex:1;min-width:160px;" />
                            <select id="role-new-base" class="select">
                                <option value="VISITOR">VISITOR (view-only)</option>
                                <option value="HELPER">HELPER</option>
                                <option value="OWNER">OWNER (full)</option>
                            </select>
                            <button class="button button-primary button-compact" id="role-new-create">Create</button>
                        </div>
                        <p class="hint" style="margin-top:8px;">After creating a role, you can fine-tune its permissions below.</p>
                    </div>
                </div>
            `;

            custom.forEach(role => {
                const perms = role.permissions || {};
                const enabledActions = CONTROL_PERM_DEFS.filter(def => perms[def.key]).map(def => def.label);
                const enabledTabs = VIEW_PERM_DEFS.filter(def => perms[def.key]).map(def => def.label);
                const otherCaps = OTHER_PERM_DEFS.filter(def => perms[def.key]).map(def => def.label);
                const summaryParts = [];
                if (enabledTabs.length) summaryParts.push('Tabs: ' + enabledTabs.join(', '));
                if (enabledActions.length) summaryParts.push('Actions: ' + enabledActions.join(', '));
                if (otherCaps.length) summaryParts.push(otherCaps.join(', '));
                const summaryText = summaryParts.length
                    ? summaryParts.join(' • ')
                    : 'No capabilities enabled yet. This role currently cannot see or do anything.';

                html += `
                    <div class="card" data-role-id="${role.id}" style="cursor: default; margin-bottom: 10px;">
                        <div class="card-header" style="align-items:flex-start;justify-content:space-between;gap:8px;">
                            <div>
                                <div class="card-title">${role.name}
                                    <span class="badge badge-warning role-edited-badge" style="display:none;margin-left:6px;font-size:10px;">Edited</span>
                                </div>
                                <div class="card-subtitle" style="max-width:320px;">Base tier: ${role.base_role}</div>
                                <div class="card-subtitle" style="max-width:420px;margin-top:4px;font-size:11px;">${summaryText}</div>
                            </div>
                            <div style="display:flex;flex-direction:column;gap:6px;align-items:flex-end;">
                                <button class="button button-secondary button-compact" data-role-action="toggle" data-role-id="${role.id}">Edit</button>
                                <button class="button button-danger button-compact" data-role-action="delete" data-role-id="${role.id}">Delete</button>
                            </div>
                        </div>
                        <div class="card-body" style="display:none;">
                            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;align-items:center;">
                                <label style="font-size:12px;color:var(--text-secondary);">Base tier:</label>
                                <select class="select" data-role-field="base_role" data-role-id="${role.id}">
                                    <option value="VISITOR" ${role.base_role === 'VISITOR' ? 'selected' : ''}>VISITOR</option>
                                    <option value="HELPER" ${role.base_role === 'HELPER' ? 'selected' : ''}>HELPER</option>
                                    <option value="OWNER" ${role.base_role === 'OWNER' ? 'selected' : ''}>OWNER</option>
                                </select>
                            </div>
                            <div style="margin-bottom:10px;">
                                <textarea class="input-text" data-role-field="description" data-role-id="${role.id}" style="width:100%;min-height:40px;resize:vertical;" placeholder="Description...">${role.description || ''}</textarea>
                            </div>
                            <div style="margin-bottom:8px;">
                                <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">Basic actions this role can perform</div>
                                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:6px;">
                                    ${CONTROL_PERM_DEFS.map(def => `
                                        <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-secondary);">
                                            <input type="checkbox" data-role-perm="${def.key}" data-role-id="${role.id}" ${perms[def.key] ? 'checked' : ''} />
                                            <span>${def.label}</span>
                                        </label>
                                    `).join('')}
                                </div>
                            </div>
                            <div style="margin-bottom:8px;">
                                <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">Advanced: which tabs this role can see</div>
                                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:6px;">
                                    ${VIEW_PERM_DEFS.map(def => `
                                        <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-secondary);">
                                            <input type="checkbox" data-role-perm="${def.key}" data-role-id="${role.id}" ${perms[def.key] ? 'checked' : ''} />
                                            <span>${def.label}</span>
                                        </label>
                                    `).join('')}
                                </div>
                            </div>
                            <div>
                                <div style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">Other capabilities</div>
                                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:6px;">
                                    ${OTHER_PERM_DEFS.map(def => `
                                        <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-secondary);">
                                            <input type="checkbox" data-role-perm="${def.key}" data-role-id="${role.id}" ${perms[def.key] ? 'checked' : ''} />
                                            <span>${def.label}</span>
                                        </label>
                                    `).join('')}
                                </div>
                            </div>
                            <div style="margin-top:10px;display:flex;justify-content:flex-end;gap:8px;">
                                <button class="button button-secondary button-compact" data-role-action="save" data-role-id="${role.id}">Save Changes</button>
                            </div>
                        </div>
                    </div>
                `;
            });

            profilesContainer.innerHTML = html;

            function markRoleEdited(roleId) {
                const card = profilesContainer.querySelector(`.card[data-role-id="${roleId}"]`);
                if (!card) return;
                const badge = card.querySelector('.role-edited-badge');
                if (!badge) return;
                badge.style.display = 'inline-flex';
            }

            // Collapse/expand custom role details
            profilesContainer.querySelectorAll('[data-role-action="toggle"]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const id = parseInt(btn.getAttribute('data-role-id'), 10);
                    if (!id) return;
                    const card = profilesContainer.querySelector(`.card[data-role-id="${id}"]`);
                    if (!card) return;
                    const body = card.querySelector('.card-body');
                    if (!body) return;
                    const isOpen = body.style.display === 'block';
                    body.style.display = isOpen ? 'none' : 'block';
                    btn.textContent = isOpen ? 'Edit' : 'Close';
                });
            });

            // Mark roles as edited when fields change
            profilesContainer.querySelectorAll('[data-role-field="base_role"]').forEach(sel => {
                const id = parseInt(sel.getAttribute('data-role-id'), 10);
                sel.addEventListener('change', () => markRoleEdited(id));
            });
            profilesContainer.querySelectorAll('[data-role-field="description"]').forEach(area => {
                const id = parseInt(area.getAttribute('data-role-id'), 10);
                area.addEventListener('input', () => markRoleEdited(id));
            });
            profilesContainer.querySelectorAll('[data-role-perm]').forEach(cb => {
                const id = parseInt(cb.getAttribute('data-role-id'), 10);
                cb.addEventListener('change', () => markRoleEdited(id));
            });

            const createBtn = document.getElementById('role-new-create');
            if (createBtn) {
                createBtn.addEventListener('click', () => {
                    const nameEl = document.getElementById('role-new-name');
                    const baseEl = document.getElementById('role-new-base');
                    const name = nameEl.value.trim();
                    const base = baseEl.value;
                    if (!name) {
                        showNotification('Role name is required', 'error');
                        return;
                    }
                    rolesApiRequest({ action: 'role_create', name, base_role: base });
                });
            }

            profilesContainer.querySelectorAll('[data-role-action="delete"]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const id = parseInt(btn.getAttribute('data-role-id'), 10);
                    if (!id) return;
                    if (!confirm('Delete this role profile? It must not be assigned to any users.')) return;
                    rolesApiRequest({ action: 'role_delete', id });
                });
            });

            profilesContainer.querySelectorAll('[data-role-action="save"]').forEach(btn => {
                btn.addEventListener('click', () => {
                    const id = parseInt(btn.getAttribute('data-role-id'), 10);
                    if (!id) return;
                    const card = profilesContainer.querySelector(`.card[data-role-id="${id}"]`);
                    if (!card) return;
                    const baseSel = card.querySelector('[data-role-field="base_role"]');
                    const descEl = card.querySelector('[data-role-field="description"]');
                    const permEls = card.querySelectorAll('[data-role-perm]');
                    const base_role = baseSel ? baseSel.value : 'VISITOR';
                    const description = descEl ? descEl.value : '';
                    const perms = {};
                    permEls.forEach(el => {
                        const key = el.getAttribute('data-role-perm');
                        perms[key] = el.checked;
                    });
                    rolesApiRequest({ action: 'role_update', id, base_role, description, permissions: perms });
                });
            });
        }

        function rolesApiRequest(payload) {
            fetch('owner_roles.php', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(payload)
            })
                .then(async r => {
                    let data = null;
                    try {
                        data = await r.json();
                    } catch (_) {}
                    if (!r.ok) {
                        const msg = interpretHttpError(r.status, data, 'roles');
                        throw new Error(msg);
                    }
                    return data || {};
                })
                .then(data => {
                    if (!data.success) {
                        showNotification(data.error || 'Roles API error', 'error');
                        return;
                    }
                    showNotification(data.message || 'Updated roles', 'success');
                    rolesTabInitialized = false;
                    loadRolesTab();
                })
                .catch(err => {
                    console.error('Roles API error:', err);
                    showNotification(err.message || 'Failed to update roles.', 'error');
                });
        }

        function loadDatabaseTables() {
            const tablesEl = document.getElementById('db-tables');
            const rowsEl = document.getElementById('db-rows');
            const titleEl = document.getElementById('db-selected-title');
            const subtitleEl = document.getElementById('db-selected-subtitle');
            if (!tablesEl || !rowsEl) return;

            tablesEl.innerHTML = '<div class="loading">Loading tables...</div>';
            rowsEl.innerHTML = '';
            if (titleEl) titleEl.textContent = 'No table selected';
            if (subtitleEl) subtitleEl.textContent = '';

            fetch('owner_db.php?action=tables', { credentials: 'include' })
                .then(async r => {
                    let data = null;
                    try {
                        data = await r.json();
                    } catch (_) {}
                    if (!r.ok) {
                        const msg = interpretHttpError(r.status, data, 'database');
                        showNotification(msg, 'error');
                        throw new Error(msg);
                    }
                    return data || {};
                })
                .then(data => {
                    const tables = data.tables || [];
                    if (!tables.length) {
                        tablesEl.innerHTML = '<div class="empty-state">No tables found in dashboard database.</div>';
                        return;
                    }
                    tablesEl.innerHTML = tables.map(t => `
                        <div class="db-table-card">
                            <div class="db-table-main">
                                <div class="db-table-name">${t.name}</div>
                                <div class="db-table-meta">${typeof t.count === 'number' ? (t.count + ' rows') : ''}</div>
                            </div>
                            <button class="button button-secondary button-compact" onclick="loadDatabaseRows('${t.name}')">Open</button>
                        </div>
                    `).join('');
                })
                .catch(err => {
                    console.error('Database tables load error:', err);
                    tablesEl.innerHTML = '<div class="empty-state">Failed to load tables from database.</div>';
                });
        }

        window.loadDatabaseRows = function (tableName) {
            const rowsEl = document.getElementById('db-rows');
            const titleEl = document.getElementById('db-selected-title');
            const subtitleEl = document.getElementById('db-selected-subtitle');
            if (!rowsEl) return;

            rowsEl.innerHTML = '<div class="loading">Loading rows...</div>';
            if (titleEl) titleEl.textContent = `Table: ${tableName}`;
            if (subtitleEl) subtitleEl.textContent = 'Showing first 100 rows (read-only).';

            const params = new URLSearchParams({ action: 'rows', table: tableName, limit: '100' });
            fetch('owner_db.php?' + params.toString(), { credentials: 'include' })
                .then(async r => {
                    let data = null;
                    try {
                        data = await r.json();
                    } catch (_) {}
                    if (!r.ok) {
                        const msg = interpretHttpError(r.status, data, 'database');
                        showNotification(msg, 'error');
                        throw new Error(msg);
                    }
                    return data || {};
                })
                .then(data => {
                    const rows = data.rows || [];
                    if (!rows.length) {
                        rowsEl.innerHTML = '<div class="empty-state">No rows in this table.</div>';
                        return;
                    }
                    const cols = Object.keys(rows[0]);
                    let html = '<table class="db-rows-table">';
                    html += '<thead><tr>' + cols.map(c => `<th>${c}</th>`).join('') + '</tr></thead>';
                    html += '<tbody>';
                    rows.forEach(r => {
                        html += '<tr>' + cols.map(c => {
                            const v = r[c];
                            const text = (v === null || v === undefined) ? '' : String(v);
                            return `<td>${text}</td>`;
                        }).join('') + '</tr>';
                    });
                    html += '</tbody></table>';
                    rowsEl.innerHTML = html;
                })
                .catch(err => {
                    console.error('Database rows load error:', err);
                    rowsEl.innerHTML = '<div class="empty-state">Failed to load table rows.</div>';
                });
        };

        function renderCurrentUserPill() {
            try {
                if (typeof LM_CURRENT_USER === 'undefined') return;
                const u = LM_CURRENT_USER || {};
                if (!u.discord_user_id) return;
                const pill = document.getElementById('lm-user-pill');
                if (!pill) return;
                const initial = (u.display_name || 'U').charAt(0).toUpperCase();
                const avatarHtml = u.avatar_url
                    ? `<span class="lm-user-pill-avatar"><img src="${u.avatar_url}" alt="${u.display_name || ''}"></span>`
                    : `<span class="lm-user-pill-avatar">${initial}</span>`;
                pill.innerHTML = `
                    <div class="lm-user-pill-inner">
                        ${avatarHtml}
                        <div class="lm-user-pill-text">
                            <div class="lm-user-pill-name">${u.display_name || 'Unknown user'}</div>
                            <div class="lm-user-pill-role">${(u.role || '').toUpperCase()}</div>
                        </div>
                        <button class="lm-user-logout-button" onclick="window.location='logout.php'">Logout</button>
                    </div>
                `;
            } catch (e) {}
        }

        renderCurrentUserPill();

        function renderStatusChip(status) {
            const safeStatus = status || 'healthy';
            const label = safeStatus.charAt(0).toUpperCase() + safeStatus.slice(1);
            let color = '#22c55e';
            if (safeStatus === 'critical') {
                color = '#ef4444';
            } else if (safeStatus === 'degraded') {
                color = '#f59e0b';
            }
            return `
                <span class="status-chip status-chip-${safeStatus}">
                    <svg class="status-chip-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                        <circle cx="8" cy="8" r="6.75" fill="none" stroke="${color}" stroke-width="1.5" />
                        <path d="M4.5 8.2L7 10.7L11.5 5.5" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                    <span class="status-chip-label">${label}</span>
                </span>
            `;
        }

        function setStatusBadge(status) {
            const badge = document.getElementById('status-badge');
            if (!badge) return;
            const safeStatus = status || 'healthy';
            badge.className = 'status-badge status-' + safeStatus;
            badge.innerHTML = `
                <span class="status-badge-caption">Bot Status</span>
                ${renderStatusChip(safeStatus)}
            `;
        }

        function prettyPrintJson(raw) {
            if (!raw) return 'No diagnostics data available.';
            try {
                const parsed = JSON.parse(raw);
                return JSON.stringify(parsed, null, 2);
            } catch (e) {
                return raw;
            }
        }

        function openDiagnosticsModal() {
            const body = `
                <div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;">
                    Framework diagnostics from <code>data/framework_diagnostics.json</code>.
                </div>
                <pre id="diag-json-view" class="code-block-json">Regenerating diagnostics...</pre>
            `;
            openModal('Framework Diagnostics JSON', body);
            
            // Always regenerate on click to show current info
            console.log('[DIAGNOSTICS] Triggering fresh diagnostics generation...');
            sendCommand('generate_framework_diagnostics', {});
            
            // Wait for generation, then fetch
            setTimeout(() => {
                fetchDiagnosticsJson();
            }, 2000);
        }

        function fetchDiagnosticsJson() {
            const path = './data/framework_diagnostics.json';
            const view = document.getElementById('diag-json-view');
            if (!view) return;

            function attemptRead(allowGenerate) {
                const requestId = sendFileCommand('read_file', { path });
                let retries = 0;
                const maxRetries = 10;

                const poll = () => {
                    retries++;
                    fetch('monitor_data_fileops.json?t=' + Date.now())
                        .then(r => r.ok ? r.text() : null)
                        .then(text => {
                            if (!text) {
                                if (retries < maxRetries) {
                                    return setTimeout(poll, 900);
                                }
                                if (allowGenerate) {
                                    triggerDiagnosticsGeneration();
                                } else {
                                    view.textContent = 'Unable to load diagnostics data from the bot.';
                                }
                                return;
                            }
                            let data;
                            try {
                                data = JSON.parse(text);
                            } catch {
                                if (retries < maxRetries) {
                                    return setTimeout(poll, 900);
                                }
                                if (allowGenerate) {
                                    triggerDiagnosticsGeneration();
                                } else {
                                    view.textContent = 'Diagnostics response from bot could not be parsed.';
                                }
                                return;
                            }

                            if (data && data.type === 'read_file' && data.path === path && data.request_id === requestId) {
                                const raw = data.content || '';
                                view.textContent = prettyPrintJson(raw);
                            } else if (retries < maxRetries) {
                                setTimeout(poll, 900);
                            } else if (allowGenerate) {
                                triggerDiagnosticsGeneration();
                            } else {
                                view.textContent = 'Diagnostics data not available.';
                            }
                        })
                        .catch(() => {
                            if (retries < maxRetries) {
                                setTimeout(poll, 900);
                            } else if (allowGenerate) {
                                triggerDiagnosticsGeneration();
                            } else {
                                view.textContent = 'Network error while loading diagnostics.';
                            }
                        });
                };

                setTimeout(poll, 600);
            }

            function triggerDiagnosticsGeneration() {
                view.textContent = 'No existing diagnostics found. Generating a fresh report...';
                sendCommand('generate_framework_diagnostics', {});
                setTimeout(() => attemptRead(false), 2000);
            }

            attemptRead(true);
        }

        function updateOverview(data, previous) {
            const health = data.health || {};
            const system = data.system || {};
            const bot = data.bot || {};
            const framework = data.framework || {};

            const healthText = document.getElementById('overview-health-text');
            if (healthText) {
                const status = health.status || 'healthy';
                healthText.innerHTML = renderStatusChip(status);
            }

            const uptimeGuilds = document.getElementById('overview-uptime-guilds');
            if (uptimeGuilds) {
                uptimeGuilds.textContent = `Uptime: ${bot.uptime_formatted || '0s'} • ${bot.guilds || 0} guilds`;
            }

            const activityEl = document.getElementById('overview-activity');
            if (activityEl) {
                const msgs = previous && previous.metrics ? previous.metrics.messages_seen || 0 : 0;
                const nowMsgs = data.metrics ? data.metrics.messages_seen || 0 : msgs;
                const delta = nowMsgs - msgs;
                const trend = delta > 0 ? `↑ ${delta} msgs since last refresh` : 'No change since last refresh';
                activityEl.textContent = `CPU ${system.cpu_percent?.toFixed(1) || '0'}% • RAM ${(system.memory_percent || 0).toFixed(0)}% • ${trend}`;
            }

            const frameworkEl = document.getElementById('overview-framework');
            if (frameworkEl) {
                const v = framework.version || 'unknown';
                const py = framework.python_runtime || 'unknown';
                const rec = framework.recommended_python || '';
                const ok = rec && py === rec;
                frameworkEl.textContent = `Version ${v} • Python ${py}${rec ? (ok ? ' (recommended)' : ` (recommended ${rec})`) : ''}`;
            }

            const alertsContainer = document.getElementById('overview-alert-list');
            const bannerContainer = document.getElementById('alerts-bar');
            if (!alertsContainer || !bannerContainer) return;

            const alerts = [];
            const memPct = system.memory_percent || 0;
            if (memPct >= 85) {
                alerts.push({
                    type: 'warning',
                    text: `Memory at ${memPct.toFixed(0)}% - consider restarting or investigating memory usage.`,
                });
            } else if (memPct >= 70) {
                alerts.push({
                    type: 'info',
                    text: `Memory at ${memPct.toFixed(0)}% (high but acceptable).`,
                });
            }

            const errorRate = health.error_rate || 0;
            if (errorRate >= 10) {
                alerts.push({ type: 'warning', text: `Command errors increasing (error rate ${errorRate.toFixed(2)}%).` });
            }

            if (previous && previous.bot && typeof previous.bot.guilds === 'number') {
                const diff = (bot.guilds || 0) - (previous.bot.guilds || 0);
                if (diff > 0) {
                    alerts.push({ type: 'info', text: `Bot added to ${diff} new server(s) since the last refresh.` });
                }
            }

            if (alerts.length === 0) {
                alertsContainer.innerHTML = '<div class="empty-state">No active alerts. Your bot looks good.</div>';
                bannerContainer.innerHTML = '';
                return;
            }

            alertsContainer.innerHTML = alerts.map(a => `
                <div class="card" style="cursor: default;">
                    <div class="card-header">
                        <div class="card-title">${a.type === 'warning' ? '⚠️ Alert' : 'ℹ️ Info'}</div>
                    </div>
                    <div class="card-body" style="display:block;">
                        <div style="font-size:13px;color:var(--text-secondary);">${a.text}</div>
                    </div>
                </div>
            `).join('');

            const topAlert = alerts[0];
            const color = topAlert.type === 'warning' ? 'rgba(245,158,11,0.18)' : 'rgba(59,130,246,0.18)';
            bannerContainer.innerHTML = `
                <div style="margin-bottom:14px;padding:10px 14px;border-radius:10px;background:${color};border:1px solid rgba(148,163,184,0.4);font-size:13px;">
                    ${topAlert.text}
                </div>
            `;
        }

        function openMainConfig() {
            switchTab('files');
            quickOpenFile('./config.json', 'config.json');
        }

        function openLiveMonitorConfig() {
            switchTab('files');
            quickOpenFile('./data/live_monitor_config.json', 'live_monitor_config.json');
        }

        function quickOpenFile(path, displayName) {
            const fileBrowser = document.getElementById('file-browser-content');
            const unit = (fileBrowser && fileBrowser.querySelector('.explorer-unit')) || document.querySelector('#tab-files .explorer-unit');
            const name = document.getElementById('fileName');
            const text = document.getElementById('fileContent');
            if (!unit || !name || !text) return;

            name.innerText = displayName || path.split('/').pop();
            text.value = addLineNumbers('// Loading ' + name.innerText + '...');
            unit.classList.add('editor-open');
            const filePane = (fileBrowser && fileBrowser.querySelector('.file-pane')) || document.querySelector('#tab-files .file-pane');
            const editorPane = (fileBrowser && fileBrowser.querySelector('.editor-pane')) || document.querySelector('#tab-files .editor-pane');
            if (filePane) {
                if (!filePane.style.width) filePane.style.width = '420px';
                filePane.style.flexShrink = '0';
            }
            if (editorPane) {
                editorPane.style.display = 'flex';
                editorPane.style.flex = '1';
            }
            loadFile(path);
        }

        function maybeShowTour() {
            try {
                const seen = window.localStorage.getItem('lm_tour_seen');
                if (!seen) {
                    const overlay = document.getElementById('lm-tour-overlay');
                    if (overlay) {
                        overlay.style.display = 'flex';
                        overlay.classList.add('lm-open');
                    }
                }
            } catch (_) {}
        }

        function completeTour() {
            try { window.localStorage.setItem('lm_tour_seen', '1'); } catch (_) {}
            const overlay = document.getElementById('lm-tour-overlay');
            if (overlay) {
                overlay.classList.remove('lm-open');
                overlay.style.display = 'none';
            }
        }

        (function () {
            const tourTrigger = document.getElementById('tour-trigger');
            if (tourTrigger) {
                tourTrigger.addEventListener('click', () => {
                    const overlay = document.getElementById('lm-tour-overlay');
                    if (overlay) {
                        overlay.style.display = 'flex';
                        overlay.classList.add('lm-open');
                    }
                });
            }
        })();

        let isFirstLoad = true;
        async function loadData() {
            const searchInput = document.getElementById('cmd-search');
            if (searchInput) {
                searchState.commands = searchInput.value;
            }
            
            document.querySelectorAll('.card').forEach(card => {
                const body = card.querySelector('.card-body');
                if (body && body.style.display === 'block') {
                    expandedCards.add(card.id);
                }
            });
            
            try {
                if (isFirstLoad) {
                    document.getElementById('loading').innerHTML = 
                        '<p>Initializing dashboard...</p>' +
                        '<p style="color: var(--text-secondary); margin-top: 8px;">Waiting for bot to send data</p>';
                    await new Promise(resolve => setTimeout(resolve, 2500));
                    isFirstLoad = false;
                }
                
                const packages = ['core', 'commands', 'plugins', 'hooks', 'extensions', 'system_details', 'events', 'filesystem'];
                const loadPromises = packages.map((pkg, index) => 
                    new Promise(resolve => {
                        setTimeout(() => {
                            fetch(`monitor_data_${pkg}.json?t=` + Date.now())
                                .then(r => r.ok ? r.json() : null)
                                .catch(() => null)
                                .then(resolve);
                        }, index * 100);
                    })
                );

                const results = await Promise.all(loadPromises);

                const data = {
                    "timestamp": results[0]?.timestamp || new Date().toISOString(),
                    "bot": results[0]?.bot || {},
                    "system": results[0]?.system || {},
                    "health": results[0]?.health || {},
                    "chat_history": results[0]?.chat_history || null,
                    "commands": results[1] || {},
                    "plugins": results[2] || {},
                    "event_hooks": results[3] || {},
                    "available_extensions": results[4]?.available_extensions || [],
                    "slash_limiter": results[5]?.slash_limiter || {},
                    "atomic_fs": results[5]?.atomic_fs || {},
                    "core_settings": results[5]?.core_settings || {},
                    "framework": results[5]?.framework || {},
                    "events": results[6]?.events || [],
                    "file_system": results[7] || {}
                };
                
                if (!results[0]) {
                    if (retryCount < maxRetries) {
                        retryCount++;
                        const waitTime = Math.min(1000 * retryCount, 5000);
                        document.getElementById('loading').innerHTML = 
                            '<p>Waiting for bot to send data...</p>' +
                            '<p style="color: var(--text-secondary); margin-top: 8px;">Retry ' + retryCount + '/' + maxRetries + '</p>' +
                            '<p style="color: var(--text-secondary); font-size: 12px;">Make sure you ran: /livemonitor enable</p>';
                        
                        if (retryTimeout) clearTimeout(retryTimeout);
                        retryTimeout = setTimeout(loadData, waitTime);
                        return;
                    } else {
                        document.getElementById('loading').innerHTML = 
                            '<div style="color: var(--danger); padding: 20px;">' +
                            '<h3>⚠️ Unable to Load Data</h3>' +
                            '<p style="margin-top: 12px;">Possible issues:</p>' +
                            '<ul style="text-align: left; margin: 12px auto; max-width: 400px;">' +
                            '<li>Bot hasnt sent data yet (run /livemonitor enable)</li>' +
                            '<li>receive.php not working or not uploaded</li>' +
                            '<li>Monitor data files not being created</li>' +
                            '</ul>' +
                            '<button class="button button-primary" style="margin-top: 16px;" onclick="retryCount=0; loadData()">Try Again</button>' +
                            '</div>';
                        return;
                    }
                }
                
                retryCount = 0;
                const previousData = currentData;
                currentData = data;
                
                // Extract platform info
                if (data.system && data.system.platform) {
                    platformOS = data.system.platform;
                    console.log('[SYSTEM] Platform detected:', platformOS);
                }
                
                document.getElementById('loading').style.display = 'none';
                document.getElementById('content').style.display = 'block';

                const memPct = data.system.memory_percent || 0;
                const memBand = memPct >= 85 ? 'Critical' : memPct >= 70 ? 'High' : 'Normal';
                const memMb = (data.system.memory_mb || 0).toFixed(2);
                document.getElementById('cpu-value').textContent = (data.system.cpu_percent || 0).toFixed(1);
                document.getElementById('cpu-value').title = 'Process CPU usage as a percentage of one core.';
                document.getElementById('memory-value').textContent = `${memMb} MB`;
                document.getElementById('memory-value').title = `Resident memory usage for the bot process; ${memPct.toFixed(0)}% of total (${memBand}).`;
                const guildEl = document.getElementById('guilds-value');
                if (guildEl) guildEl.textContent = data.bot.guilds || 0;
                const userEl = document.getElementById('users-value');
                if (userEl) userEl.textContent = data.bot.users || 0;
                const uptimeEl = document.getElementById('uptime-value');
                if (uptimeEl) uptimeEl.textContent = data.bot.uptime_formatted || '0s';
                document.getElementById('latency-value').textContent = (data.bot.latency || 0).toFixed(2);
                
                const status = data.health && data.health.status ? data.health.status : 'healthy';
                setStatusBadge(status);
                
                if (data.commands && data.commands.commands) {
                    renderCommands(data.commands.commands);
                }
                
                if (data.plugins) {
                    renderPlugins(data.plugins);
                }
                
                if (data.event_hooks && data.event_hooks.hooks) {
                    renderHooks(data.event_hooks);
                }
                
        if (data.bot && data.bot.guilds_detail) {
                    renderChatConsole(data.bot);
                    renderGuilds(data.bot.guilds_detail);
                }

                updateOverview(data, previousData);

                if (data.chat_history && data.chat_history.messages) {
                    const hist = data.chat_history;
                    chatMessageHistory = [];
                    const guildName = hist.guild_name || '';
                    const channelName = hist.channel_name || '';
                    (hist.messages || []).forEach(m => {
                        appendChatLog({
                            timestamp: m.timestamp,
                            guild: guildName,
                            channel: channelName,
                            content: m.content
                        });
                    });
                }
                
                if (data.file_system) {
                    renderFileSystem(data.file_system);
                    if (data.file_system.fileops) {
                        updateFileTree(data.file_system.fileops);
                    }
                    if (!fileBrowserInitialized) {
                        renderFileBrowser(data.file_system, data.file_system.fileops);
                    }
                }
                
                if (data.events) {
                    renderEvents(data.events);
                }
                
                renderSystemDetails(data);
                
                setTimeout(() => {
                    if (searchState.commands && document.getElementById('cmd-search')) {
                        document.getElementById('cmd-search').value = searchState.commands;
                        const event = new Event('input');
                        document.getElementById('cmd-search').dispatchEvent(event);
                    }
                    
                    expandedCards.forEach(cardId => {
                        const card = document.getElementById(cardId);
                        if (card) {
                            const body = card.querySelector('.card-body');
                            if (body) body.style.display = 'block';
                        }
                    });
                }, 50);
                
                document.getElementById('last-update').textContent = new Date().toLocaleString();
            } catch (err) {
                console.error('Load error:', err);
                showNotification('⚠️ Data loading error. Retrying...', 'error');
            }
        }

        document.getElementById('modal').addEventListener('click', (e) => {
            if (e.target.id === 'modal') closeModal();
        });

        loadData();
        maybeShowTour();
        setInterval(loadData, 20000);

        // When switching tabs, lazily initialize heavy owner-only panels
        const originalSwitchTab = switchTab;
        window.switchTab = function (tabName) {
            if (!isTabAllowedByPerms(tabName)) {
                showNotification('You do not have permission to view this section.', 'error');
                return;
            }
            originalSwitchTab(tabName);
            if (tabName === 'roles') {
                loadRolesTab();
            } else if (tabName === 'database') {
                loadDatabaseTables();
            }
        };
    </script>
</body>
</html>'''.replace('{{TOKEN}}', token).replace('{{PREFIX}}', self._get_default_prefix())

    def _generate_index_php(self, token: str, default_prefix: str, setup_token: str) -> str:
        """Wrap the static dashboard HTML in a small PHP bootstrap.

        The underlying HTML/JS is still generated by `_generate_index_html`, but
        index.php adds a lightweight guard that ensures the dashboard is either
        in one-time setup mode or requires a logged-in Discord user.
        """
        base_html = self._generate_index_html(token)
        php_guard = """<?php
require_once __DIR__ . '/lm_db.php';
require_once __DIR__ . '/lm_auth.php';

lm_start_session_if_needed();
lm_ensure_schema();
lm_guard_index();
?>
"""
        return php_guard + base_html

    def _generate_lm_bootstrap_php(self, secret_token: str, setup_token: str) -> str:
        """Small bootstrap file that carries tokens into the PHP world.

        LM_SECRET_TOKEN is used for bootstrapping the initial DB config; the
        actual bot↔web communication still relies on SECRET_TOKEN inside the
        bridge scripts.
        """
        return f'''<?php
// Auto-generated by Zoryx Live Monitor. Do not edit manually unless you
// know what you're doing.

if (!defined('LM_SECRET_TOKEN')) {{
    define('LM_SECRET_TOKEN', '{secret_token}');
}}

if (!defined('LM_SETUP_TOKEN')) {{
    define('LM_SETUP_TOKEN', '{setup_token}');
}}
?>
'''

    def _generate_lm_db_php(self) -> str:
        """Database helper (SQLite by default, file-based, zero-config)."""
        return '''<?php
// Lightweight DB helper for the Live Monitor dashboard (SQLite by default).
require_once __DIR__ . '/lm_bootstrap.php';

function lm_db() {
    static $pdo = null;
    if ($pdo !== null) {
        return $pdo;
    }

    $dbDir = __DIR__ . '/data';
    if (!is_dir($dbDir)) {
        mkdir($dbDir, 0775, true);
    }

    $dsn = 'sqlite:' . $dbDir . '/dashboard.sqlite';

    $pdo = new PDO($dsn, null, null, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);

    return $pdo;
}

function lm_ensure_schema() {
    $pdo = lm_db();

    // Global config (single row)
    $pdo->exec("\r
        CREATE TABLE IF NOT EXISTS dashboard_config (\r
            id INTEGER PRIMARY KEY AUTOINCREMENT,\r
            owner_discord_id VARCHAR(32) NULL,\r
            setup_completed INTEGER NOT NULL DEFAULT 0,\r
            setup_token VARCHAR(64) NULL,\r
            discord_client_id VARCHAR(64) NULL,\r
            discord_client_secret VARCHAR(128) NULL,\r
            oauth_redirect_url VARCHAR(255) NULL,\r
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\r
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP\r
        );\r
    ");

    // Allowed dashboard users
    $pdo->exec("\r
        CREATE TABLE IF NOT EXISTS dashboard_users (\r
            id INTEGER PRIMARY KEY AUTOINCREMENT,\r
            discord_user_id VARCHAR(32) UNIQUE NOT NULL,\r
            display_name VARCHAR(128) NOT NULL,\r
            avatar_url VARCHAR(255) NULL,\r
            role VARCHAR(16) NOT NULL,\r
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\r
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP\r
        );\r
    ");

    // Audit logs
    $pdo->exec("\r
        CREATE TABLE IF NOT EXISTS audit_logs (\r
            id INTEGER PRIMARY KEY AUTOINCREMENT,\r
            timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\r
            actor_user_id INTEGER NULL,\r
            actor_discord_id VARCHAR(32) NULL,\r
            action VARCHAR(64) NOT NULL,\r
            target_type VARCHAR(64) NULL,\r
            target_id VARCHAR(128) NULL,\r
            ip_address VARCHAR(45) NULL,\r
            user_agent VARCHAR(255) NULL,\r
            meta_json TEXT NULL\r
        );\r
    ");

    $pdo->exec("CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs (timestamp);");
    $pdo->exec("CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs (actor_user_id);");
    $pdo->exec("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs (action);");

    // Optional custom roles table (role profiles / aliases)
    $pdo->exec("\r
        CREATE TABLE IF NOT EXISTS dashboard_roles (\r
            id INTEGER PRIMARY KEY AUTOINCREMENT,\r
            name VARCHAR(64) UNIQUE NOT NULL,\r
            base_role VARCHAR(16) NOT NULL,\r
            description VARCHAR(255) NULL,\r
            permissions_json TEXT NULL,\r
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,\r
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP\r
        );\r
    ");

    // Best-effort migration: add permissions_json if an older table exists without it
    try {
        $pdo->exec("ALTER TABLE dashboard_roles ADD COLUMN permissions_json TEXT NULL");
    } catch (Throwable $e) {
        // Ignore if column already exists
    }

    // Seed single config row if missing
    $stmt = $pdo->query("SELECT COUNT(*) AS c FROM dashboard_config");
    $row = $stmt->fetch();
    $count = isset($row['c']) ? (int)$row['c'] : 0;
    if ($count === 0) {
        $setupToken = defined('LM_SETUP_TOKEN') ? LM_SETUP_TOKEN : null;
        $insert = $pdo->prepare("\r
            INSERT INTO dashboard_config (owner_discord_id, setup_completed, setup_token)\r
            VALUES (NULL, 0, :token)\r
        ");
        $insert->execute([':token' => $setupToken]);
    }
}
?>
'''

    def _generate_lm_auth_php(self) -> str:
        """Authentication helpers: sessions, roles, audit logging, guards."""
        return '''<?php
require_once __DIR__ . '/lm_db.php';

function lm_start_session_if_needed(): void {
    if (session_status() !== PHP_SESSION_ACTIVE) {
        // Simple, safe default session configuration
        session_start([
            'cookie_httponly' => true,
            'cookie_secure' => (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off'),
            'cookie_samesite' => 'Lax',
        ]);
    }
}

function lm_get_config(): array {
    lm_ensure_schema();
    $pdo = lm_db();
    $stmt = $pdo->query('SELECT * FROM dashboard_config LIMIT 1');
    $row = $stmt->fetch();
    return $row ?: [];
}

function lm_save_config(array $config): void {
    $pdo = lm_db();
    $current = lm_get_config();
    if (!$current) {
        return;
    }

    $fields = [
        'owner_discord_id',
        'setup_completed',
        'setup_token',
        'discord_client_id',
        'discord_client_secret',
        'oauth_redirect_url',
    ];
    $sets = [];
    $params = [];
    foreach ($fields as $field) {
        if (array_key_exists($field, $config)) {
            $sets[] = "$field = :$field";
            $params[":$field"] = $config[$field];
        }
    }
    if (!$sets) {
        return;
    }
    $sql = 'UPDATE dashboard_config SET ' . implode(', ', $sets) . ' WHERE id = :id';
    $params[':id'] = $current['id'];
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
}

function lm_current_user(): ?array {
    lm_start_session_if_needed();
    if (empty($_SESSION['lm_user_id'])) {
        return null;
    }
    $pdo = lm_db();
    $stmt = $pdo->prepare('SELECT * FROM dashboard_users WHERE id = :id LIMIT 1');
    $stmt->execute([':id' => $_SESSION['lm_user_id']]);
    $user = $stmt->fetch();
    return $user ?: null;
}

function lm_is_logged_in(): bool {
    return lm_current_user() !== null;
}

function lm_log_audit(string $action, ?string $targetType = null, ?string $targetId = null, array $meta = []): void {
    try {
        lm_start_session_if_needed();
        lm_ensure_schema();
        $pdo = lm_db();
        $user = lm_current_user();

        $stmt = $pdo->prepare('INSERT INTO audit_logs (
            actor_user_id, actor_discord_id, action, target_type, target_id, ip_address, user_agent, meta_json
        ) VALUES (:uid, :did, :action, :tt, :tid, :ip, :ua, :meta)');

        $ip = $_SERVER['REMOTE_ADDR'] ?? null;
        $ua = $_SERVER['HTTP_USER_AGENT'] ?? null;

        $stmt->execute([
            ':uid' => $user['id'] ?? null,
            ':did' => $user['discord_user_id'] ?? null,
            ':action' => $action,
            ':tt' => $targetType,
            ':tid' => $targetId,
            ':ip' => $ip,
            ':ua' => $ua,
            ':meta' => $meta ? json_encode($meta, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) : null,
        ]);
    } catch (Throwable $e) {
        // Never break the dashboard because of logging issues.
    }
}

function lm_guard_index(): void {
    lm_start_session_if_needed();
    lm_ensure_schema();
    $config = lm_get_config();

    // Not yet claimed: redirect to setup wizard if we have a setup token
    if (empty($config['setup_completed'])) {
        $token = $config['setup_token'] ?? (defined('LM_SETUP_TOKEN') ? LM_SETUP_TOKEN : null);
        if (!$token) {
            http_response_code(503);
            echo '<h1>Dashboard setup required</h1><p>Please re-run /livemonitor quickstart to generate a new setup link.</p>';
            exit;
        }

        $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
        $host = $_SERVER['HTTP_HOST'] ?? 'localhost';
        $basePath = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? ''), '/');
        $setupUrl = sprintf('%s://%s%s/setup.php?setup_token=%s', $scheme, $host, $basePath, urlencode($token));
        header('Location: ' . $setupUrl);
        exit;
    }

    // Already claimed: require a logged-in dashboard user
    $user = lm_current_user();
    if (!$user) {
        header('Location: login.php');
        exit;
    }
}

function lm_require_owner(): void {
    $user = lm_current_user();
    if (!$user || ($user['role'] ?? '') !== 'OWNER') {
        http_response_code(403);
        echo '<h1>Forbidden</h1><p>Owner access is required to view this page.</p>';
        exit;
    }
}

/**
 * Resolve an arbitrary role name (including custom roles) to a base tier
 * of OWNER / HELPER / VISITOR for permission checks.
 */
function lm_resolve_role_tier(string $roleName): string {
    $upper = strtoupper($roleName);
    if (in_array($upper, ['OWNER', 'HELPER', 'VISITOR'], true)) {
        return $upper;
    }
    try {
        $pdo = lm_db();
        $stmt = $pdo->prepare('SELECT base_role FROM dashboard_roles WHERE UPPER(name) = UPPER(:name) LIMIT 1');
        $stmt->execute([':name' => $roleName]);
        $row = $stmt->fetch();
        if ($row && !empty($row['base_role'])) {
            $base = strtoupper($row['base_role']);
            if (in_array($base, ['OWNER', 'HELPER', 'VISITOR'], true)) {
                return $base;
            }
        }
    } catch (Throwable $e) {
        // Ignore DB or lookup errors; fall back to VISITOR tier.
    }
    return 'VISITOR';
}

function lm_default_permissions_for_tier(string $tier): array {
    switch ($tier) {
        case 'OWNER':
            return [
                'view_dashboard'  => true,
                'view_commands'   => true,
                'view_plugins'    => true,
                'view_hooks'      => true,
                'view_filesystem' => true,
                'view_files'      => true,
                'view_chat'       => true,
                'view_events'     => true,
                'view_system'     => true,
                'view_security'   => true,
                'view_guilds'     => true,
                'view_database'   => true,
                'view_marketplace'=> true,
                'view_invite'     => true,
                'control_core'    => true,
                'control_plugins' => true,
                'control_hooks'   => true,
                'control_files'   => true,
                'control_chat'    => true,
                'control_guilds'  => true,
                'control_database'=> true,
                'control_backup'  => true,
                'control_invite'  => true,
                'control_marketplace' => true,
                'export_logs'     => true,
            ];
        case 'HELPER':
            return [
                'view_dashboard'  => true,
                'view_commands'   => true,
                'view_plugins'    => true,
                'view_hooks'      => true,
                'view_filesystem' => true,
                'view_files'      => true,
                'view_chat'       => true,
                'view_events'     => true,
                'view_system'     => true,
                'view_security'   => false,
                'view_guilds'     => true,
                'view_database'   => true,
                'view_marketplace'=> true,
                'view_invite'     => true,
                'control_core'    => false,
                'control_plugins' => true,
                'control_hooks'   => true,
                'control_files'   => true,
                'control_chat'    => true,
                'control_guilds'  => false,
                'control_database'=> false,
                'control_backup'  => false,
                'control_invite'  => true,
                'control_marketplace' => true,
                'export_logs'     => false,
            ];
        case 'VISITOR':
        default:
            return [
                'view_dashboard'  => true,
                'view_commands'   => true,
                'view_plugins'    => true,
                'view_hooks'      => true,
                'view_filesystem' => true,
                'view_files'      => false,
                'view_chat'       => false,
                'view_events'     => true,
                'view_system'     => true,
                'view_security'   => false,
                'view_guilds'     => false,
                'view_database'   => false,
                'view_marketplace'=> false,
                'view_invite'     => true,
                'control_core'    => false,
                'control_plugins' => false,
                'control_hooks'   => false,
                'control_files'   => false,
                'control_chat'    => false,
                'control_guilds'  => false,
                'control_database'=> false,
                'control_backup'  => false,
                'control_invite'  => false,
                'control_marketplace' => false,
                'export_logs'     => false,
            ];
    }
}

/**
 * Compute the effective permissions for a role name + tier, merging
 * dashboard_roles.permissions_json (if any) over the tier defaults.
 */
function lm_role_permissions(string $roleName, string $tier): array {
    $perms = lm_default_permissions_for_tier($tier);
    try {
        $upper = strtoupper($roleName);
        if (in_array($upper, ['OWNER', 'HELPER', 'VISITOR'], true)) {
            return $perms;
        }
        $pdo = lm_db();
        $stmt = $pdo->prepare('SELECT permissions_json FROM dashboard_roles WHERE UPPER(name) = UPPER(:name) LIMIT 1');
        $stmt->execute([':name' => $roleName]);
        $row = $stmt->fetch();
        if ($row && !empty($row['permissions_json'])) {
            $decoded = json_decode($row['permissions_json'], true);
            if (is_array($decoded)) {
                foreach ($decoded as $k => $v) {
                    $perms[$k] = (bool)$v;
                }
            }
        }
    } catch (Throwable $e) {
        // Ignore
    }
    return $perms;
}

?>
'''

    def _generate_setup_php(self) -> str:
        """One-time setup wizard page (Discord OAuth config + claim link)."""
        return '''<?php
require_once __DIR__ . '/lm_auth.php';

lm_start_session_if_needed();
lm_ensure_schema();
$pdo = lm_db();
$config = lm_get_config();

if (!empty($config['setup_completed'])) {
    header('Location: index.php');
    exit;
}

$requiredToken = $config['setup_token'] ?? (defined('LM_SETUP_TOKEN') ? LM_SETUP_TOKEN : null);
$providedToken = $_GET['setup_token'] ?? '';
if (!$requiredToken || !$providedToken || !hash_equals($requiredToken, $providedToken)) {
    http_response_code(403);
    echo '<h1>Invalid setup link</h1><p>Please re-run /livemonitor quickstart to generate a fresh setup URL.</p>';
    exit;
}

$message = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $clientId = trim($_POST['discord_client_id'] ?? '');
    $clientSecret = trim($_POST['discord_client_secret'] ?? '');

    if ($clientId && $clientSecret) {
        $config['discord_client_id'] = $clientId;
        $config['discord_client_secret'] = $clientSecret;

        // Compute and persist the redirect URL for convenience
        $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
        $host = $_SERVER['HTTP_HOST'] ?? 'localhost';
        $basePath = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? ''), '/');
        $redirectUrl = sprintf('%s://%s%s/oauth_callback.php', $scheme, $host, $basePath);
        $config['oauth_redirect_url'] = $redirectUrl;

        lm_save_config($config);
        lm_log_audit('OAUTH_CONFIG_UPDATED', 'SETTING', 'discord_oauth', []);
        $message = 'Saved! You can now click "Connect with Discord" below to claim the dashboard.';
    } else {
        $message = 'Please fill both Client ID and Client Secret.';
    }

    $config = lm_get_config();
}

$scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
$host = $_SERVER['HTTP_HOST'] ?? 'localhost';
$basePath = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? ''), '/');
$redirectUrl = $config['oauth_redirect_url'] ?? sprintf('%s://%s%s/oauth_callback.php', $scheme, $host, $basePath);

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Live Monitor – Setup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #020617;
            color: #e5e7eb;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 16px;
        }
        .card {
            max-width: 720px;
            width: 100%;
            background: #020617;
            border-radius: 16px;
            padding: 24px 24px 20px;
            border: 1px solid rgba(148, 163, 184, 0.4);
            box-shadow: 0 24px 80px rgba(15, 23, 42, 0.9);
        }
        h1 {
            margin-top: 0;
            margin-bottom: 4px;
            font-size: 22px;
        }
        p {
            margin: 4px 0;
            color: #9ca3af;
            font-size: 14px;
        }
        label {
            display: block;
            margin-top: 12px;
            margin-bottom: 4px;
            font-size: 13px;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 8px 10px;
            border-radius: 8px;
            border: 1px solid rgba(148, 163, 184, 0.5);
            background: #020617;
            color: #e5e7eb;
            font-size: 13px;
        }
        input[type="text"]:focus, input[type="password"]:focus {
            outline: 2px solid #3b82f6;
            outline-offset: 1px;
        }
        .hint {
            font-size: 12px;
            color: #6b7280;
            margin-top: 2px;
        }
        .redirect-box {
            padding: 8px 10px;
            border-radius: 8px;
            border: 1px solid rgba(55, 65, 81, 0.9);
            background: #020617;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
            font-size: 12px;
            margin-top: 4px;
            word-break: break-all;
        }
        .actions {
            margin-top: 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }
        button {
            border-radius: 8px;
            border: none;
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }
        .btn-primary {
            background: #3b82f6;
            color: white;
        }
        .btn-secondary {
            background: #111827;
            color: #e5e7eb;
            border: 1px solid rgba(75, 85, 99, 0.8);
        }
        .message {
            margin-top: 10px;
            font-size: 13px;
            color: #f97316;
        }
        .steps {
            margin-top: 12px;
            padding-left: 18px;
            font-size: 13px;
            color: #9ca3af;
        }
        .steps li {
            margin-bottom: 4px;
        }
    </style>
</head>
<body>
<div class="card">
    <h1>Live Monitor – One-time Setup</h1>
    <p>This page is only for the bot owner. Configure Discord OAuth once, then claim the dashboard.</p>

    <h3 style="margin-top:16px;margin-bottom:4px;font-size:14px;">1. Configure Discord Application</h3>
    <ol class="steps">
        <li>Open the <strong>Discord Developer Portal</strong> and select your bot's application.</li>
        <li>Go to <strong>OAuth2 → General</strong> and add this Redirect URL:</li>
    </ol>
    <div class="redirect-box"><?php echo htmlspecialchars($redirectUrl, ENT_QUOTES, 'UTF-8'); ?></div>
    <p class="hint">Make sure this exact URL is listed under OAuth2 Redirects, then save changes.</p>

    <form method="post" style="margin-top:12px;">
        <h3 style="margin:8px 0;font-size:14px;">2. Enter Discord OAuth Credentials</h3>
        <label for="discord_client_id">Client ID</label>
        <input type="text" id="discord_client_id" name="discord_client_id" value="<?php echo htmlspecialchars($config['discord_client_id'] ?? '', ENT_QUOTES, 'UTF-8'); ?>" required>

        <label for="discord_client_secret">Client Secret</label>
        <input type="password" id="discord_client_secret" name="discord_client_secret" value="<?php echo htmlspecialchars($config['discord_client_secret'] ?? '', ENT_QUOTES, 'UTF-8'); ?>" required>

        <div class="actions">
            <button type="submit" class="btn-secondary">Save OAuth Settings</button>
            <a href="login.php" class="btn-primary" style="text-decoration:none;display:inline-flex;align-items:center;gap:6px;">
                <span>Connect with Discord</span>
            </a>
        </div>
    </form>

    <?php if (!empty($message)): ?>
        <div class="message"><?php echo htmlspecialchars($message, ENT_QUOTES, 'UTF-8'); ?></div>
    <?php endif; ?>

    <p style="margin-top:16px;font-size:12px;color:#6b7280;">
        After you log in with Discord successfully, the dashboard will switch into safe mode and require login for every visit.
    </p>
</div>
</body>
</html>
'''

    def _generate_login_php(self) -> str:
        """Branded login page with Discord OAuth entry point."""
        return '''<?php
require_once __DIR__ . '/lm_auth.php';

lm_start_session_if_needed();
lm_ensure_schema();
$config = lm_get_config();

// If already logged in, go straight to dashboard
if (lm_current_user()) {
    header('Location: index.php');
    exit;
}

$clientId = $config['discord_client_id'] ?? '';
$clientSecret = $config['discord_client_secret'] ?? '';
$oauthConfigured = $clientId && $clientSecret;

$scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
$host = $_SERVER['HTTP_HOST'] ?? 'localhost';
$basePath = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? ''), '/');
$redirectUrl = $config['oauth_redirect_url'] ?? sprintf('%s://%s%s/oauth_callback.php', $scheme, $host, $basePath);

// If the owner hit the "Login with Discord" button, start the OAuth flow
if (isset($_GET['action']) && $_GET['action'] === 'start_oauth') {
    if (!$oauthConfigured) {
        echo '<h1>OAuth not configured</h1><p>Please complete the setup form first.</p>';
        exit;
    }

    $state = bin2hex(random_bytes(16));
    $_SESSION['lm_oauth_state'] = $state;

    $params = [
        'client_id' => $clientId,
        'redirect_uri' => $redirectUrl,
        'response_type' => 'code',
        'scope' => 'identify',
        'state' => $state,
        'prompt' => 'consent',
    ];

    $query = http_build_query($params);
    $authUrl = 'https://discord.com/api/oauth2/authorize?' . $query;

    header('Location: ' . $authUrl);
    exit;
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Live Monitor – Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            margin: 0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: radial-gradient(circle at top, #0f172a 0, #020617 55%, #000 100%);
            color: #e5e7eb;
        }
        .login-shell {
            width: 100%;
            max-width: 880px;
            margin: 16px;
            border-radius: 18px;
            border: 1px solid rgba(148, 163, 184, 0.5);
            overflow: hidden;
            background: radial-gradient(circle at 0 0, rgba(59,130,246,0.25), transparent 55%),
                        radial-gradient(circle at 100% 100%, rgba(139,92,246,0.2), transparent 55%),
                        rgba(15,23,42,0.98);
            box-shadow: 0 24px 80px rgba(0,0,0,0.8);
            display: grid;
            grid-template-columns: minmax(0, 1.3fr) minmax(0, 1.1fr);
        }
        .login-visual {
            position: relative;
            background: radial-gradient(circle at 0 0, rgba(56,189,248,0.25), transparent 60%),
                        radial-gradient(circle at 100% 100%, rgba(250,204,21,0.25), transparent 60%);
            display: flex;
            align-items: flex-start;
            justify-content: center;
            padding: 22px;
        }
        .login-visual-inner {
            width: 100%;
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid rgba(148, 163, 184, 0.55);
            background: #020617;
        }
        .login-banner {
            width: 100%;
            height: 160px;
            object-fit: cover;
            display: block;
        }
        .login-visual-footer {
            padding: 12px 14px 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
        }
        .login-brand {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .login-brand img {
            width: 32px;
            height: 32px;
            border-radius: 8px;
        }
        .login-brand-title {
            font-size: 14px;
            font-weight: 600;
        }
        .login-brand-subtitle {
            font-size: 11px;
            color: #9ca3af;
        }
        .login-pill {
            font-size: 11px;
            padding: 4px 10px;
            border-radius: 999px;
            border: 1px solid rgba(56,189,248,0.7);
            background: rgba(15,23,42,0.9);
            color: #e5e7eb;
        }
        .login-main {
            padding: 22px 24px 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        .login-title {
            font-size: 22px;
            font-weight: 700;
        }
        .login-subtitle {
            font-size: 13px;
            color: #9ca3af;
            margin-top: 4px;
        }
        .login-list {
            margin: 10px 0 0;
            padding-left: 18px;
            font-size: 13px;
            color: #9ca3af;
        }
        .login-section-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #6b7280;
            margin-top: 12px;
            margin-bottom: 4px;
        }
        .login-callout {
            margin-top: 8px;
            padding: 8px 10px;
            border-radius: 10px;
            border: 1px solid rgba(56,189,248,0.5);
            background: rgba(15,23,42,0.9);
            font-size: 12px;
            color: #e5e7eb;
        }
        .login-button-row {
            margin-top: 14px;
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }
        .btn-discord {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 9px 16px;
            border-radius: 999px;
            border: none;
            background: #5865F2;
            color: #fff;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            box-shadow: 0 10px 30px rgba(88,101,242,0.5);
        }
        .btn-discord:hover {
            background: #4f5adf;
        }
        .btn-secondary {
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            background: transparent;
            color: #e5e7eb;
            padding: 8px 14px;
            font-size: 12px;
        }
        .login-footer {
            margin-top: auto;
            font-size: 11px;
            color: #6b7280;
        }
        .login-footer a {
            color: #93c5fd;
            text-decoration: none;
        }
        @media (max-width: 860px) {
            .login-shell {
                grid-template-columns: minmax(0, 1fr);
            }
            .login-visual {
                display: none;
            }
        }
    </style>
</head>
<body>
<div class="login-shell">
    <div class="login-visual">
        <div class="login-visual-inner">
            <img src="assets/banner.png" alt="Zoryx Framework" class="login-banner">
            <div class="login-visual-footer">
                <div class="login-brand">
                    <img src="assets/zoryx-framework.png" alt="Zoryx Icon">
                    <div>
                        <div class="login-brand-title">Zoryx Discord Bot Framework</div>
                        <div class="login-brand-subtitle">Live Monitor Dashboard</div>
                    </div>
                </div>
                <div class="login-pill">Self-hosted control panel</div>
            </div>
        </div>
    </div>
    <div class="login-main">
        <div>
            <div class="login-title">Login with Discord</div>
            <div class="login-subtitle">
                After logging in, access is granted only if your Discord user ID has been added by the bot owner.
            </div>
            <ul class="login-list">
                <li><strong>Bot owner</strong>: claim the dashboard and manage Roles &amp; Access.</li>
                <li><strong>Helpers</strong>: operate the bot depending on your assigned role.</li>
                <li><strong>Visitors</strong>: view-only access if the owner enabled it for you.</li>
            </ul>
        </div>

        <div>
            <div class="login-section-label">Authentication</div>
            <div class="login-callout">
                This dashboard uses Discord OAuth2 with the <code>identify</code> scope only. Your Discord ID and name are stored
                in the local <code>dashboard.sqlite</code> database for access control and audit logging.
            </div>
            <div class="login-button-row">
                <?php if ($oauthConfigured): ?>
                    <a href="?action=start_oauth" class="btn-discord">
                        <span>Login with Discord</span>
                    </a>
                <?php else: ?>
                    <button class="btn-secondary" disabled>OAuth not configured – run /livemonitor quickstart</button>
                <?php endif; ?>
            </div>
        </div>

        <div class="login-footer">
            Zoryx Discord Bot Framework · Live Monitor. Configure OAuth once via the one-time setup URL, then return here to log in.
        </div>
    </div>
</div>
</body>
</html>
'''

    def _generate_oauth_callback_php(self) -> str:
        """Handle Discord OAuth2 callback, claim dashboard, and create sessions."""
        return '''<?php
require_once __DIR__ . '/lm_auth.php';

lm_start_session_if_needed();
lm_ensure_schema();
$pdo = lm_db();
$config = lm_get_config();

if (!isset($_GET['state']) || !isset($_SESSION['lm_oauth_state']) || !hash_equals($_SESSION['lm_oauth_state'], $_GET['state'])) {
    http_response_code(400);
    echo '<h1>Invalid OAuth state</h1><p>Please try logging in again.</p>';
    exit;
}
unset($_SESSION['lm_oauth_state']);

if (isset($_GET['error'])) {
    lm_log_audit('LOGIN_FAILED', 'OAUTH', null, ['error' => $_GET['error']]);
    echo '<h1>Discord Login Failed</h1><p>' . htmlspecialchars($_GET['error'], ENT_QUOTES, 'UTF-8') . '</p>';
    exit;
}

$code = $_GET['code'] ?? null;
if (!$code) {
    http_response_code(400);
    echo '<h1>Missing code</h1><p>Discord did not return an authorization code.</p>';
    exit;
}

$clientId = $config['discord_client_id'] ?? '';
$clientSecret = $config['discord_client_secret'] ?? '';
if (!$clientId || !$clientSecret) {
    echo '<h1>OAuth not configured</h1><p>Please complete the setup form first.</p>';
    exit;
}

$scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
$host = $_SERVER['HTTP_HOST'] ?? 'localhost';
$basePath = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? ''), '/');
$redirectUrl = $config['oauth_redirect_url'] ?? sprintf('%s://%s%s/oauth_callback.php', $scheme, $host, $basePath);

$tokenResponse = null;

// Exchange code for access token
$ch = curl_init('https://discord.com/api/oauth2/token');
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query([
    'client_id' => $clientId,
    'client_secret' => $clientSecret,
    'grant_type' => 'authorization_code',
    'code' => $code,
    'redirect_uri' => $redirectUrl,
]));

$result = curl_exec($ch);
if ($result === false) {
    lm_log_audit('LOGIN_FAILED', 'OAUTH', null, ['error' => 'curl_error']);
    echo '<h1>OAuth Error</h1><p>Failed to contact Discord.</p>';
    exit;
}

$tokenResponse = json_decode($result, true);
if (!is_array($tokenResponse) || empty($tokenResponse['access_token'])) {
    lm_log_audit('LOGIN_FAILED', 'OAUTH', null, ['error' => 'no_access_token', 'raw' => $result]);
    echo '<h1>OAuth Error</h1><p>Discord did not return an access token.</p>';
    exit;
}

$accessToken = $tokenResponse['access_token'];

// Fetch Discord user profile
$ch = curl_init('https://discord.com/api/users/@me');
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'Authorization: Bearer ' . $accessToken,
]);
$userResult = curl_exec($ch);
if ($userResult === false) {
    lm_log_audit('LOGIN_FAILED', 'PROFILE', null, ['error' => 'profile_fetch_failed']);
    echo '<h1>OAuth Error</h1><p>Failed to fetch user profile from Discord.</p>';
    exit;
}

$user = json_decode($userResult, true);
if (!is_array($user) || empty($user['id'])) {
    lm_log_audit('LOGIN_FAILED', 'PROFILE', null, ['error' => 'invalid_profile', 'raw' => $userResult]);
    echo '<h1>OAuth Error</h1><p>Discord did not return a valid user.</p>';
    exit;
}

$discordId = $user['id'];
$displayName = $user['global_name'] ?? ($user['username'] ?? 'unknown');
$avatarUrl = null;
if (!empty($user['avatar'])) {
    $avatarUrl = sprintf('https://cdn.discordapp.com/avatars/%s/%s.png', $discordId, $user['avatar']);
}

$pdo->beginTransaction();
try {
    $config = lm_get_config();

    // First claim: no owner yet
    if (empty($config['setup_completed']) || empty($config['owner_discord_id'])) {
        $config['owner_discord_id'] = $discordId;
        $config['setup_completed'] = 1;
        $config['setup_token'] = null;
        lm_save_config($config);

        $stmt = $pdo->prepare('INSERT INTO dashboard_users (discord_user_id, display_name, avatar_url, role) VALUES (:did, :name, :avatar, :role)');
        $stmt->execute([
            ':did' => $discordId,
            ':name' => $displayName,
            ':avatar' => $avatarUrl,
            ':role' => 'OWNER',
        ]);

        $userId = (int)$pdo->lastInsertId();
        $_SESSION['lm_user_id'] = $userId;
        lm_log_audit('DASHBOARD_CLAIMED', 'USER', $discordId, []);
        lm_log_audit('LOGIN_SUCCESS', 'USER', $discordId, ['role' => 'OWNER']);
    } else {
        // Existing dashboard: only allow registered users
        $stmt = $pdo->prepare('SELECT * FROM dashboard_users WHERE discord_user_id = :did LIMIT 1');
        $stmt->execute([':did' => $discordId]);
        $existing = $stmt->fetch();
        if (!$existing) {
            $pdo->commit();
            lm_log_audit('LOGIN_DENIED', 'USER', $discordId, []);
            http_response_code(403);
            echo '<h1>Access denied</h1><p>Your Discord account is not allowed to use this dashboard. Ask the owner to add you.</p>';
            exit;
        }

        // Update display name/avatar on every login for freshness
        $upd = $pdo->prepare('UPDATE dashboard_users SET display_name = :name, avatar_url = :avatar WHERE id = :id');
        $upd->execute([
            ':name' => $displayName,
            ':avatar' => $avatarUrl,
            ':id' => $existing['id'],
        ]);

        $_SESSION['lm_user_id'] = $existing['id'];
        lm_log_audit('LOGIN_SUCCESS', 'USER', $discordId, ['role' => $existing['role'] ?? 'UNKNOWN']);
    }

    $pdo->commit();
} catch (Throwable $e) {
    $pdo->rollBack();
    lm_log_audit('LOGIN_FAILED', 'INTERNAL', null, ['error' => $e->getMessage()]);
    http_response_code(500);
    echo '<h1>Internal error</h1><p>Login failed unexpectedly.</p>';
    exit;
}

header('Location: index.php');
exit;
?>
'''

    def _generate_logout_php(self) -> str:
        """Simple logout endpoint that destroys the dashboard session and redirects to login."""
        return '''<?php
require_once __DIR__ . '/lm_auth.php';

lm_start_session_if_needed();
lm_ensure_schema();
$user = lm_current_user();
if ($user) {
    lm_log_audit('LOGOUT', 'USER', $user['discord_user_id'] ?? null, []);
}

// Clear session
$_SESSION = [];
if (ini_get('session.use_cookies')) {
    $params = session_get_cookie_params();
    setcookie(session_name(), '', time() - 42000,
        $params['path'], $params['domain'],
        $params['secure'], $params['httponly']
    );
}
session_destroy();

header('Location: login.php');
exit;
?>
'''

    def _generate_backup_dashboard_php(self) -> str:
        """Endpoint to download a zip backup of the dashboard PHP files and data directory."""
        return '''<?php
require_once __DIR__ . '/lm_auth.php';

lm_start_session_if_needed();
lm_ensure_schema();

$user = lm_current_user();
if (!$user) {
    http_response_code(403);
    echo 'Not logged in';
    exit;
}

$roleName = $user['role'] ?? 'VISITOR';
$roleTier = lm_resolve_role_tier($roleName);
$perms = lm_role_permissions($roleName, $roleTier);

if (empty($perms['control_backup'])) {
    http_response_code(403);
    echo 'You do not have permission to create dashboard backups.';
    exit;
}

if (!class_exists('ZipArchive')) {
    http_response_code(500);
    echo 'ZipArchive extension is required to create backups.';
    exit;
}

$root = __DIR__;
$zip = new ZipArchive();
$filename = 'dashboard_backup_' . date('Ymd_His') . '.zip';
$tmpPath = sys_get_temp_dir() . DIRECTORY_SEPARATOR . $filename;

if ($zip->open($tmpPath, ZipArchive::CREATE | ZipArchive::OVERWRITE) !== true) {
    http_response_code(500);
    echo 'Unable to create backup.';
    exit;
}

$rii = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root));

foreach ($rii as $file) {
    if ($file->isDir()) {
        continue;
    }
    $path = $file->getPathname();
    $relative = substr($path, strlen($root) + 1);

    // Skip existing backup archives to avoid recursion
    if (preg_match('/\\.zip$/i', $relative)) {
        continue;
    }

    $zip->addFile($path, $relative);
}

$zip->close();

lm_log_audit('DASHBOARD_BACKUP_CREATED', 'BACKUP', $filename, []);

header('Content-Type: application/zip');
header('Content-Disposition: attachment; filename="' . $filename . '"');
header('Content-Length: ' . filesize($tmpPath));

readfile($tmpPath);
@unlink($tmpPath);
exit;
?>
'''

    def _generate_owner_audit_php(self) -> str:
        """Owner-only audit log viewer with basic search + filters."""
        return '''<?php
require_once __DIR__ . '/lm_auth.php';

lm_start_session_if_needed();
lm_ensure_schema();
lm_require_owner();
$pdo = lm_db();

$q = trim($_GET['q'] ?? '');
$actionFilter = trim($_GET['action'] ?? '');
$page = max(1, (int)($_GET['page'] ?? 1));
$limit = 50;
$offset = ($page - 1) * $limit;

$where = [];
$params = [];

if ($q !== '') {
    $where[] = '(actor_discord_id LIKE :q OR target_id LIKE :q OR meta_json LIKE :q)';
    $params[':q'] = '%' . $q . '%';
}

if ($actionFilter !== '') {
    $where[] = 'action = :action';
    $params[':action'] = $actionFilter;
}

$sqlWhere = $where ? ('WHERE ' . implode(' AND ', $where)) : '';

// CSV export (used by the Security & Logs "Export Logs" button)
if (isset($_GET['export']) && $_GET['export'] === 'csv') {
    header('Content-Type: text/csv; charset=UTF-8');
    header('Content-Disposition: attachment; filename="audit_logs_' . date('Ymd_His') . '.csv"');

    $exportSql = 'SELECT timestamp, action, actor_discord_id, target_type, target_id, meta_json FROM audit_logs ' . $sqlWhere . ' ORDER BY timestamp DESC';
    $exportStmt = $pdo->prepare($exportSql);
    $exportStmt->execute($params);

    $out = fopen('php://output', 'w');
    if ($out !== false) {
        fputcsv($out, ['timestamp', 'action', 'actor_discord_id', 'target_type', 'target_id', 'meta_json']);
        while ($row = $exportStmt->fetch(PDO::FETCH_ASSOC)) {
            fputcsv($out, [
                $row['timestamp'] ?? '',
                $row['action'] ?? '',
                $row['actor_discord_id'] ?? '',
                $row['target_type'] ?? '',
                $row['target_id'] ?? '',
                $row['meta_json'] ?? '',
            ]);
        }
        fclose($out);
    }
    exit;
}

$totalSql = 'SELECT COUNT(*) AS c FROM audit_logs ' . $sqlWhere;
$stmt = $pdo->prepare($totalSql);
$stmt->execute($params);
$total = (int)($stmt->fetch()['c'] ?? 0);

$listSql = 'SELECT * FROM audit_logs ' . $sqlWhere . ' ORDER BY timestamp DESC LIMIT :limit OFFSET :offset';
$stmt = $pdo->prepare($listSql);
foreach ($params as $k => $v) {
    $stmt->bindValue($k, $v, PDO::PARAM_STR);
}
$stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
$stmt->bindValue(':offset', $offset, PDO::PARAM_INT);
$stmt->execute();
$rows = $stmt->fetchAll();

$pages = max(1, (int)ceil($total / $limit));
$currentPage = min($page, $pages);

function h($s) {
    return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');
}

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Owner Audit Log</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #020617;
            color: #e5e7eb;
            margin: 0;
            padding: 12px;
        }
        h1 {
            margin: 0 0 8px 0;
            font-size: 18px;
        }
        form {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 10px;
        }
        input[type="text"], select {
            padding: 6px 8px;
            border-radius: 6px;
            border: 1px solid rgba(148, 163, 184, 0.5);
            background: #020617;
            color: #e5e7eb;
            font-size: 12px;
        }
        button {
            padding: 6px 10px;
            border-radius: 6px;
            border: none;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
        }
        .btn-primary {
            background: #3b82f6;
            color: white;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        th, td {
            padding: 6px 8px;
            border-bottom: 1px solid rgba(31, 41, 55, 0.9);
            text-align: left;
        }
        th {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #9ca3af;
        }
        tr:nth-child(even) td {
            background: #020617;
        }
        tr:nth-child(odd) td {
            background: #030712;
        }
        .meta {
            max-width: 260px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
        }
        .pager {
            margin-top: 8px;
            font-size: 11px;
            color: #9ca3af;
        }
        .pager a {
            color: #93c5fd;
            text-decoration: none;
            margin-right: 6px;
        }
    </style>
</head>
<body>
    <h1>Audit Log (Owner)</h1>
    <form method="get">
        <input type="text" name="q" placeholder="Search user, target, meta" value="<?php echo h($q); ?>">
        <select name="action">
            <option value="">All actions</option>
            <option value="LOGIN_SUCCESS" <?php echo $actionFilter === 'LOGIN_SUCCESS' ? 'selected' : ''; ?>>LOGIN_SUCCESS</option>
            <option value="LOGIN_FAILED" <?php echo $actionFilter === 'LOGIN_FAILED' ? 'selected' : ''; ?>>LOGIN_FAILED</option>
            <option value="LOGIN_DENIED" <?php echo $actionFilter === 'LOGIN_DENIED' ? 'selected' : ''; ?>>LOGIN_DENIED</option>
            <option value="DASHBOARD_CLAIMED" <?php echo $actionFilter === 'DASHBOARD_CLAIMED' ? 'selected' : ''; ?>>DASHBOARD_CLAIMED</option>
            <option value="OAUTH_CONFIG_UPDATED" <?php echo $actionFilter === 'OAUTH_CONFIG_UPDATED' ? 'selected' : ''; ?>>OAUTH_CONFIG_UPDATED</option>
        </select>
        <button type="submit" class="btn-primary">Filter</button>
    </form>

    <table>
        <thead>
            <tr>
                <th>Time</th>
                <th>Action</th>
                <th>Actor</th>
                <th>Target</th>
                <th>Meta</th>
            </tr>
        </thead>
        <tbody>
        <?php if (!$rows): ?>
            <tr><td colspan="5">No entries</td></tr>
        <?php else: ?>
            <?php foreach ($rows as $row): ?>
                <tr>
                    <td><?php echo h($row['timestamp']); ?></td>
                    <td><?php echo h($row['action']); ?></td>
                    <td><?php echo h($row['actor_discord_id'] ?? ''); ?></td>
                    <td><?php echo h($row['target_type'] . ':' . $row['target_id']); ?></td>
                    <td class="meta"><?php echo h($row['meta_json'] ?? ''); ?></td>
                </tr>
            <?php endforeach; ?>
        <?php endif; ?>
        </tbody>
    </table>

    <div class="pager">
        Page <?php echo $currentPage; ?> of <?php echo $pages; ?> (<?php echo $total; ?> entries)
        <?php if ($currentPage > 1): ?>
            <a href="?<?php echo http_build_query(['q' => $q, 'action' => $actionFilter, 'page' => $currentPage - 1]); ?>">Prev</a>
        <?php endif; ?>
        <?php if ($currentPage < $pages): ?>
            <a href="?<?php echo http_build_query(['q' => $q, 'action' => $actionFilter, 'page' => $currentPage + 1]); ?>">Next</a>
        <?php endif; ?>
    </div>
</body>
</html>
'''

    def _generate_owner_roles_php(self) -> str:
        """Owner-only JSON API for managing dashboard_users roles."""
        return '''<?php
require_once __DIR__ . '/lm_auth.php';

lm_start_session_if_needed();
lm_ensure_schema();
lm_require_owner();
$pdo = lm_db();
$config = lm_get_config();

header('Content-Type: application/json');

// Load custom role profiles (aliases)
$customRoles = [];
try {
    $stmtRoles = $pdo->query('SELECT id, name, base_role, description, permissions_json, created_at FROM dashboard_roles ORDER BY name ASC');
    $rowsRoles = $stmtRoles->fetchAll();
    foreach ($rowsRoles as $r) {
        $perms = [];
        if (!empty($r['permissions_json'])) {
            $tmp = json_decode($r['permissions_json'], true);
            if (is_array($tmp)) {
                $perms = $tmp;
            }
        }
        $customRoles[] = [
            'id' => (int)($r['id'] ?? 0),
            'name' => $r['name'],
            'base_role' => strtoupper($r['base_role'] ?? 'VISITOR'),
            'description' => $r['description'] ?? '',
            'permissions' => $perms,
            'system' => false,
        ];
    }
} catch (Throwable $e) {
    $customRoles = [];
}

$builtinRoles = [
    [
        'name' => 'OWNER',
        'base_role' => 'OWNER',
        'description' => 'Dashboard owner (full access)',
        'system' => true,
    ],
    [
        'name' => 'HELPER',
        'base_role' => 'HELPER',
        'description' => 'Built-in helper role',
        'system' => true,
    ],
    [
        'name' => 'VISITOR',
        'base_role' => 'VISITOR',
        'description' => 'View-only visitor role',
        'system' => true,
    ],
];

$allRoles = array_merge($builtinRoles, $customRoles);

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    if (($_GET['format'] ?? '') === 'json') {
        $stmt = $pdo->query('SELECT id, discord_user_id, display_name, avatar_url, role, created_at FROM dashboard_users ORDER BY role DESC, created_at ASC');
        $rows = $stmt->fetchAll();
        echo json_encode([
            'success' => true,
            'owner_discord_id' => $config['owner_discord_id'] ?? null,
            'users' => $rows,
            'roles' => $allRoles,
        ]);
        exit;
    }
    echo json_encode(['success' => false, 'error' => 'Use ?format=json for this endpoint']);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['success' => false, 'error' => 'Method not allowed']);
    exit;
}

$raw = file_get_contents('php://input');
$data = json_decode($raw, true);
if (!is_array($data)) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Invalid JSON body']);
    exit;
}

$action = $data['action'] ?? '';

try {
    if ($action === 'add') {
        $did = trim($data['discord_user_id'] ?? '');
        $name = trim($data['display_name'] ?? '');
        $role = strtoupper(trim($data['role'] ?? 'VISITOR'));
        if (!$did) {
            throw new RuntimeException('Discord user ID is required');
        }
        if ($role === 'OWNER') {
            throw new RuntimeException('OWNER role is reserved for the original claimant');
        }
        // Allow HELPER / VISITOR and any custom role name defined in dashboard_roles
        if (!in_array($role, ['HELPER', 'VISITOR'], true)) {
            $check = $pdo->prepare('SELECT COUNT(*) AS c FROM dashboard_roles WHERE UPPER(name) = :name');
            $check->execute([':name' => $role]);
            $row = $check->fetch();
            $exists = isset($row['c']) ? (int)$row['c'] > 0 : false;
            if (!$exists) {
                throw new RuntimeException('Unknown role: ' . $role . '. Create a role profile first.');
            }
        }

        $stmt = $pdo->prepare('INSERT OR IGNORE INTO dashboard_users (discord_user_id, display_name, avatar_url, role) VALUES (:did, :name, NULL, :role)');
        $stmt->execute([
            ':did' => $did,
            ':name' => $name ?: $did,
            ':role' => $role,
        ]);
        lm_log_audit('ROLE_ADDED', 'USER', $did, ['role' => $role]);
        echo json_encode(['success' => true, 'message' => 'User added']);
        exit;
    }

    if ($action === 'update_role') {
        $userId = (int)($data['user_id'] ?? 0);
        $role = strtoupper(trim($data['role'] ?? ''));
        if (!$userId) {
            throw new RuntimeException('Invalid user or role');
        }
        if ($role === 'OWNER') {
            throw new RuntimeException('OWNER role is reserved for the original claimant');
        }
        // Allow HELPER / VISITOR and any custom dashboard_roles.name
        if (!in_array($role, ['HELPER', 'VISITOR'], true)) {
            $check = $pdo->prepare('SELECT COUNT(*) AS c FROM dashboard_roles WHERE UPPER(name) = :name');
            $check->execute([':name' => $role]);
            $row = $check->fetch();
            $exists = isset($row['c']) ? (int)$row['c'] > 0 : false;
            if (!$exists) {
                throw new RuntimeException('Unknown role: ' . $role . '. Create a role profile first.');
            }
        }
        $stmt = $pdo->prepare('SELECT * FROM dashboard_users WHERE id = :id LIMIT 1');
        $stmt->execute([':id' => $userId]);
        $u = $stmt->fetch();
        if (!$u) {
            throw new RuntimeException('User not found');
        }
        if ($u['role'] === 'OWNER' && $role !== 'OWNER') {
            throw new RuntimeException('Cannot demote OWNER via web UI');
        }

        $stmt = $pdo->prepare('UPDATE dashboard_users SET role = :role WHERE id = :id');
        $stmt->execute([':role' => $role, ':id' => $userId]);
        lm_log_audit('ROLE_UPDATED', 'USER', $u['discord_user_id'], ['old' => $u['role'], 'new' => $role]);
        echo json_encode(['success' => true, 'message' => 'Role updated']);
        exit;
    }

    if ($action === 'delete') {
        $userId = (int)($data['user_id'] ?? 0);
        if (!$userId) {
            throw new RuntimeException('Invalid user');
        }
        $stmt = $pdo->prepare('SELECT * FROM dashboard_users WHERE id = :id LIMIT 1');
        $stmt->execute([':id' => $userId]);
        $u = $stmt->fetch();
        if (!$u) {
            throw new RuntimeException('User not found');
        }
        if ($u['role'] === 'OWNER') {
            throw new RuntimeException('Cannot remove OWNER');
        }

        $del = $pdo->prepare('DELETE FROM dashboard_users WHERE id = :id');
        $del->execute([':id' => $userId]);
        lm_log_audit('ROLE_REMOVED', 'USER', $u['discord_user_id'], ['role' => $u['role']]);
        echo json_encode(['success' => true, 'message' => 'User removed']);
        exit;
    }

    // Create a new custom role profile
    if ($action === 'role_create') {
        $name = strtoupper(trim($data['name'] ?? ''));
        $base = strtoupper(trim($data['base_role'] ?? 'VISITOR'));
        $desc = trim($data['description'] ?? '');
        $perms = $data['permissions'] ?? null;
        if (!$name) {
            throw new RuntimeException('Role name is required');
        }
        if (in_array($name, ['OWNER', 'HELPER', 'VISITOR'], true)) {
            throw new RuntimeException('This name is reserved for built-in roles');
        }
        if (!in_array($base, ['OWNER', 'HELPER', 'VISITOR'], true)) {
            throw new RuntimeException('Invalid base role');
        }
        $stmt = $pdo->prepare('SELECT COUNT(*) AS c FROM dashboard_roles WHERE UPPER(name) = :name');
        $stmt->execute([':name' => $name]);
        $row = $stmt->fetch();
        if (isset($row['c']) && (int)$row['c'] > 0) {
            throw new RuntimeException('A role with this name already exists');
        }
        $jsonPerms = is_array($perms) ? json_encode($perms) : null;
        $ins = $pdo->prepare('INSERT INTO dashboard_roles (name, base_role, description, permissions_json) VALUES (:name, :base, :description, :perms)');
        $ins->execute([
            ':name' => $name,
            ':base' => $base,
            ':description' => $desc,
            ':perms' => $jsonPerms,
        ]);
        lm_log_audit('ROLE_PROFILE_CREATED', 'ROLE', $name, ['base_role' => $base]);
        echo json_encode(['success' => true, 'message' => 'Role created']);
        exit;
    }

    // Update an existing custom role profile (base tier / description)
    if ($action === 'role_update') {
        $id = (int)($data['id'] ?? 0);
        $base = strtoupper(trim($data['base_role'] ?? 'VISITOR'));
        $desc = trim($data['description'] ?? '');
        $perms = $data['permissions'] ?? null;
        if (!$id) {
            throw new RuntimeException('Invalid role');
        }
        if (!in_array($base, ['OWNER', 'HELPER', 'VISITOR'], true)) {
            throw new RuntimeException('Invalid base role');
        }
        $stmt = $pdo->prepare('SELECT * FROM dashboard_roles WHERE id = :id LIMIT 1');
        $stmt->execute([':id' => $id]);
        $role = $stmt->fetch();
        if (!$role) {
            throw new RuntimeException('Role not found');
        }
        $jsonPerms = is_array($perms) ? json_encode($perms) : null;
        $upd = $pdo->prepare('UPDATE dashboard_roles SET base_role = :base, description = :description, permissions_json = :perms WHERE id = :id');
        $upd->execute([
            ':base' => $base,
            ':description' => $desc,
            ':perms' => $jsonPerms,
            ':id' => $id,
        ]);
        lm_log_audit('ROLE_PROFILE_UPDATED', 'ROLE', $role['name'], ['base_role' => $base]);
        echo json_encode(['success' => true, 'message' => 'Role updated']);
        exit;
    }

    // Delete a custom role profile (must not be in use)
    if ($action === 'role_delete') {
        $id = (int)($data['id'] ?? 0);
        if (!$id) {
            throw new RuntimeException('Invalid role');
        }
        $stmt = $pdo->prepare('SELECT * FROM dashboard_roles WHERE id = :id LIMIT 1');
        $stmt->execute([':id' => $id]);
        $role = $stmt->fetch();
        if (!$role) {
            throw new RuntimeException('Role not found');
        }
        $name = strtoupper($role['name']);
        if (in_array($name, ['OWNER', 'HELPER', 'VISITOR'], true)) {
            throw new RuntimeException('Cannot delete built-in roles');
        }
        $checkUsers = $pdo->prepare('SELECT COUNT(*) AS c FROM dashboard_users WHERE UPPER(role) = :name');
        $checkUsers->execute([':name' => $name]);
        $row = $checkUsers->fetch();
        if (isset($row['c']) && (int)$row['c'] > 0) {
            throw new RuntimeException('Cannot delete a role that is still assigned to users');
        }
        $del = $pdo->prepare('DELETE FROM dashboard_roles WHERE id = :id');
        $del->execute([':id' => $id]);
        lm_log_audit('ROLE_PROFILE_DELETED', 'ROLE', $name, []);
        echo json_encode(['success' => true, 'message' => 'Role deleted']);
        exit;
    }

    throw new RuntimeException('Unknown action');
} catch (Throwable $e) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
    exit;
}
?>
'''

    def _generate_owner_db_php(self) -> str:
        """RBAC-aware JSON API for inspecting the local dashboard SQLite database."""
        return '''<?php
require_once __DIR__ . '/lm_auth.php';

lm_start_session_if_needed();
lm_ensure_schema();

header('Content-Type: application/json');

$user = lm_current_user();
if (!$user) {
    http_response_code(401);
    echo json_encode(['success' => false, 'error' => 'Not logged in']);
    exit;
}

$roleName = $user['role'] ?? 'VISITOR';
$roleTier = lm_resolve_role_tier($roleName);
$rolePerms = lm_role_permissions($roleName, $roleTier);

if (empty($rolePerms['view_database'])) {
    http_response_code(403);
    echo json_encode(['success' => false, 'error' => 'You do not have permission to view the dashboard database.']);
    exit;
}

$pdo = lm_db();
$action = $_GET['action'] ?? 'tables';

try {
    if ($action === 'tables') {
        $tables = [];
        $stmt = $pdo->query("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC");
        while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
            $name = $row['name'] ?? null;
            if (!$name) {
                continue;
            }
            $count = null;
            try {
                $cntStmt = $pdo->query("SELECT COUNT(*) AS c FROM " . $pdo->quote($name));
                $cntRow = $cntStmt->fetch(PDO::FETCH_ASSOC);
                if ($cntRow && isset($cntRow['c'])) {
                    $count = (int)$cntRow['c'];
                }
            } catch (Throwable $e) {
                $count = null;
            }
            $tables[] = [
                'name' => $name,
                'count' => $count,
            ];
        }
        echo json_encode(['success' => true, 'tables' => $tables]);
        exit;
    }

    if ($action === 'rows') {
        $table = $_GET['table'] ?? '';
        if (!$table || !preg_match('/^[A-Za-z0-9_]+$/', $table)) {
            http_response_code(400);
            echo json_encode(['success' => false, 'error' => 'Invalid table name']);
            exit;
        }
        $limit = isset($_GET['limit']) ? (int)$_GET['limit'] : 100;
        $offset = isset($_GET['offset']) ? (int)$_GET['offset'] : 0;
        if ($limit < 1) $limit = 1;
        if ($limit > 1000) $limit = 1000;
        if ($offset < 0) $offset = 0;

        $sql = sprintf('SELECT * FROM "%s" LIMIT :limit OFFSET :offset', $table);
        $stmt = $pdo->prepare($sql);
        $stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
        $stmt->bindValue(':offset', $offset, PDO::PARAM_INT);
        $stmt->execute();
        $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

        echo json_encode([
            'success' => true,
            'table' => $table,
            'limit' => $limit,
            'offset' => $offset,
            'rows' => $rows,
        ]);
        exit;
    }

    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Unknown action']);
    exit;
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'Database error: ' . $e->getMessage()]);
    exit;
}
?>
'''

    def _generate_receive_php(self, token: str) -> str:
        return '''<?php
    ini_set('memory_limit', '256M');
    ini_set('post_max_size', '50M');
    ini_set('upload_max_filesize', '50M');

    define('SECRET_TOKEN', '{{TOKEN}}');

    header('Content-Type: application/json');

    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {{
        http_response_code(405);
        die(json_encode(['error' => 'Only POST requests allowed']));
    }}

    $token = $_GET['token'] ?? null;
    if (!$token || $token !== SECRET_TOKEN) {{
        http_response_code(403);
        die(json_encode(['error' => 'Invalid token']));
    }}

    $package = $_GET['package'] ?? 'unknown';
    $validPackages = ['core', 'commands', 'plugins', 'hooks', 'extensions', 'system_details', 'events', 'filesystem', 'fileops', 'assets'];

    if (!in_array($package, $validPackages)) {{
        http_response_code(400);
        die(json_encode(['error' => 'Invalid package name']));
    }}

    $jsonPayload = file_get_contents('php://input');
    if (empty($jsonPayload)) {{
        http_response_code(400);
        die(json_encode(['error' => 'No data received']));
    }}

    $decoded = json_decode($jsonPayload);
    if (json_last_error() !== JSON_ERROR_NONE) {{
        http_response_code(400);
        die(json_encode(['error' => 'Invalid JSON: ' . json_last_error_msg()]));
    }}

    // Special handling for branding assets: write base64-encoded files
    // into an /assets directory next to this script so the dashboard can
    // use them automatically.
    if ($package === 'assets') {{
        if (!is_array($decoded)) {{
            http_response_code(400);
            die(json_encode(['error' => 'Assets payload must be a JSON array']));
        }}

        $assetsDir = __DIR__ . DIRECTORY_SEPARATOR . 'assets';
        if (!is_dir($assetsDir)) {{
            mkdir($assetsDir, 0755, true);
        }}

        $written = 0;
        foreach ($decoded as $asset) {{
            $filename = $asset->filename ?? null;
            $content  = $asset->content ?? null;
            if (!$filename || !$content) {{
                continue;
            }}
            $safeName = basename($filename);
            $target   = $assetsDir . DIRECTORY_SEPARATOR . $safeName;
            $binary   = base64_decode($content, true);
            if ($binary === false) {{
                continue;
            }}
            if (file_put_contents($target, $binary, LOCK_EX) !== false) {{
                chmod($target, 0644);
                $written++;
            }}
        }}

        http_response_code(200);
        echo json_encode(['success' => true, 'message' => 'Assets uploaded', 'count' => $written]);
        exit;
    }}

    $outputFile = "monitor_data_$package.json";

    if (file_put_contents($outputFile, $jsonPayload, LOCK_EX) === false) {{
        http_response_code(500);
        die(json_encode(['error' => 'Could not write data']));
    }}

    chmod($outputFile, 0644);

    http_response_code(200);
    echo json_encode(['success' => true, 'message' => 'Package received', 'package' => $package, 'size' => strlen($jsonPayload)]);
    ?>'''.replace('{{TOKEN}}', token)
    
    def _generate_get_commands_php(self, token: str) -> str:
        return '''<?php
define('SECRET_TOKEN', '{{TOKEN}}');
$commandFile = 'pending_commands.json';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {{
    http_response_code(405);
    die(json_encode(['error' => 'Only GET requests allowed']));
}}

$token = $_GET['token'] ?? null;
if (!$token || $token !== SECRET_TOKEN) {{
    http_response_code(403);
    die(json_encode(['error' => 'Invalid token']));
}}

if (!file_exists($commandFile)) {{
    echo json_encode([]);
    exit;
}}

$commands = json_decode(file_get_contents($commandFile), true) ?? [];

if (file_put_contents($commandFile, json_encode([]), LOCK_EX) === false) {{
    http_response_code(500);
    die(json_encode(['error' => 'Could not clear commands']));
}}

echo json_encode($commands);
?>'''.replace('{{TOKEN}}', token)
    
    def _generate_send_command_php(self, token: str) -> str:
        return '''<?php
require_once __DIR__ . '/lm_auth.php';

lm_start_session_if_needed();
lm_ensure_schema();
$user = lm_current_user();
if (!$user) {
    http_response_code(403);
    header('Content-Type: application/json');
    echo json_encode(['error' => 'Not logged in']);
    exit;
}

$roleName = $user['role'] ?? 'VISITOR';
$roleTier = lm_resolve_role_tier($roleName);
$rolePerms = lm_role_permissions($roleName, $roleTier);

define('SECRET_TOKEN', '{{TOKEN}}');
$commandFile = 'pending_commands.json';

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Only POST requests allowed']);
    exit;
}

$token = $_GET['token'] ?? null;
if (!$token || $token !== SECRET_TOKEN) {
    http_response_code(403);
    echo json_encode(['error' => 'Invalid token']);
    exit;
}

$payload = file_get_contents('php://input');
if (empty($payload)) {
    http_response_code(400);
    echo json_encode(['error' => 'No command received']);
    exit;
}

$data = json_decode($payload, true);
if (json_last_error() !== JSON_ERROR_NONE) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid JSON']);
    exit;
}

$command = $data['command'] ?? '';
$params  = $data['params'] ?? [];

// Role-based allow lists
$ownerOnly = [
    'shutdown_bot',
    'plugin_registry_set_enforcement',
    'af_force_release_lock',
    'leave_guild',
    'backup_bot_directory',
];

$helperAndOwner = [
    'reload_extension',
    'load_extension',
    'unload_extension',
    'clear_cache',
    'set_auto_reload',
    'set_extensions_auto_load',
    'send_chat_message',
    'write_file',
    'read_file',
    'list_dir',
    'rename_file',
    'create_dir',
    'delete_path',
    'generate_framework_diagnostics',
    'af_invalidate_cache_entry',
];

$permissionBased = [
    'fetch_marketplace_extensions',
    'download_marketplace_extension',
    'load_downloaded_extension',
];

$visitorAllowed = [
    'request_chat_history',
];

function lm_command_allowed_for_permissions(string $command, array $perms): bool {
    switch ($command) {
        case 'shutdown_bot':
        case 'generate_framework_diagnostics':
        case 'af_invalidate_cache_entry':
        case 'af_force_release_lock':
            return !empty($perms['control_core']);
        case 'reload_extension':
        case 'load_extension':
        case 'unload_extension':
        case 'plugin_registry_set_enforcement':
        case 'set_auto_reload':
        case 'set_extensions_auto_load':
            return !empty($perms['control_plugins']);
        case 'write_file':
        case 'read_file':
        case 'list_dir':
        case 'rename_file':
        case 'create_dir':
        case 'delete_path':
            return !empty($perms['control_files']);
        case 'send_chat_message':
            return !empty($perms['control_chat']);
        case 'request_chat_history':
            return !empty($perms['view_chat']);
        case 'enable_hook':
        case 'disable_hook':
        case 'reset_circuit':
            return !empty($perms['control_hooks']);
        case 'leave_guild':
            return !empty($perms['control_guilds']);
        case 'backup_bot_directory':
            return !empty($perms['control_backup']);
        case 'fetch_marketplace_extensions':
        case 'download_marketplace_extension':
        case 'load_downloaded_extension':
            return !empty($perms['control_marketplace']) || !empty($perms['control_plugins']);
        default:
            return true;
    }
}

$allowed = false;
if (in_array($command, $ownerOnly, true)) {
    $allowed = ($roleTier === 'OWNER');
} elseif (in_array($command, $helperAndOwner, true)) {
    $allowed = in_array($roleTier, ['OWNER', 'HELPER'], true);
} elseif (in_array($command, $permissionBased, true)) {
    // Permission-based commands: anyone can use if they have the right permission
    $allowed = lm_command_allowed_for_permissions($command, $rolePerms);
} elseif (in_array($command, $visitorAllowed, true)) {
    $allowed = true;
} else {
    // Unknown commands: default deny
    $allowed = false;
}

// Double-check permissions for tier-based commands
if ($allowed && !in_array($command, $permissionBased, true) && !lm_command_allowed_for_permissions($command, $rolePerms)) {
    $allowed = false;
}

if (!$allowed) {
    lm_log_audit('COMMAND_DENIED', 'DASHBOARD', $command, [
        'role_name' => $roleName,
        'role_tier' => $roleTier,
        'user_id'   => $user['discord_user_id'] ?? null,
    ]);
    http_response_code(403);
    echo json_encode(['error' => 'Not allowed for your role']);
    exit;
}

// Queue command for the bot to consume
$commands = [];
if (file_exists($commandFile)) {
    $existing = file_get_contents($commandFile);
    $commands = json_decode($existing, true) ?? [];
}

$commands[] = [
    'command'   => $command,
    'params'    => $params,
    'timestamp' => time(),
];

if (file_put_contents($commandFile, json_encode($commands), LOCK_EX) === false) {
    http_response_code(500);
    echo json_encode(['error' => 'Could not save command']);
    exit;
}

lm_log_audit('COMMAND_QUEUED', 'DASHBOARD', $command, [
    'role_name' => $roleName,
    'role_tier' => $roleTier,
    'user_id'   => $user['discord_user_id'] ?? null,
]);

echo json_encode(['success' => true, 'message' => 'Command queued']);
?>'''.replace('{{TOKEN}}', token)


async def setup(bot):
    await bot.add_cog(LiveMonitor(bot))
    logger.info("Live Monitor cog loaded successfully")