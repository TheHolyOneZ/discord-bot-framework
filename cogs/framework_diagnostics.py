from discord.ext import commands, tasks
import discord
from datetime import datetime, timedelta
from pathlib import Path
import psutil
import platform
import sys
from typing import Dict, Any, Optional
import logging
import asyncio
import time

logger = logging.getLogger('discord')


class FrameworkDiagnostics(commands.Cog):
    
    def __init__(self, bot):
        self.bot = bot
        self.diagnostics_file = Path("./data/framework_diagnostics.json")
        self.health_file = Path("./data/framework_health.json")
        self.start_time = datetime.now()
        self.last_health_check = None
        self.alert_channel_id = None
        self.last_loop_check = time.monotonic()
        self.loop_lag_threshold = 0.5
        
        self.diagnostics_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.health_metrics = {
            "last_error": None,
            "event_loop_lag_ms": 0.0,
            "consecutive_write_failures": 0
        }
        
        self._process = None
    
    async def _get_process(self):
        if self._process is None:
            loop = asyncio.get_event_loop()
            self._process = await loop.run_in_executor(None, psutil.Process)
        return self._process
    
    async def _get_system_metrics(self) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        process = await self._get_process()
        
        def _collect_metrics():
            memory_info = process.memory_info()
            return {
                "memory_usage_mb": round(memory_info.rss / 1024 / 1024, 2),
                "cpu_percent": process.cpu_percent(interval=0.1),
                "threads": process.num_threads(),
                "open_files": len(process.open_files()),
                "connections": len(process.connections())
            }
        
        try:
            return await loop.run_in_executor(None, _collect_metrics)
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
            return {
                "memory_usage_mb": 0,
                "cpu_percent": 0,
                "threads": 0,
                "open_files": 0,
                "connections": 0
            }
    
    async def _check_event_loop_lag(self) -> float:
        current = time.monotonic()
        expected_interval = 1.0
        if hasattr(self, '_last_lag_check'):
            actual_interval = current - self._last_lag_check
            lag = max(0, actual_interval - expected_interval)
        else:
            lag = 0
        
        self._last_lag_check = current
        return lag * 1000
    
    def _calculate_error_rate(self) -> float:
        total_commands = self.bot.metrics.commands_processed
        total_errors = self.bot.metrics.error_count
        
        if total_commands > 0:
            return round((total_errors / total_commands) * 100, 2)
        return 0.0
    
    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Framework Diagnostics: Generating initial report")
        await self.generate_diagnostics()
        
        if not self.health_monitor.is_running():
            self.health_monitor.start()
        
        if not self.loop_lag_monitor.is_running():
            self.loop_lag_monitor.start()
    
    async def generate_diagnostics(self) -> Optional[Dict[str, Any]]:
        try:
            system_info = await self._get_system_metrics()
            error_rate = self._calculate_error_rate()
            
            diagnostics = {
                "generated_at": datetime.now().isoformat(),
                "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
                
                "bot": {
                    "username": str(self.bot.user),
                    "user_id": self.bot.user.id,
                    "discriminator": self.bot.user.discriminator,
                    "owner_id": self.bot.bot_owner_id,
                    "latency_ms": round(self.bot.latency * 1000, 2)
                },
                
                "environment": {
                    "python_version": platform.python_version(),
                    "discord_py_version": discord.__version__,
                    "platform": platform.platform(),
                    "architecture": platform.machine()
                },
                
                "extensions": {
                    "total_loaded": len([e for e in self.bot.extensions.keys() if e.startswith("extensions.")]),
                    "user_extensions": [e for e in self.bot.extensions.keys() if e.startswith("extensions.")],
                    "framework_cogs": [e for e in self.bot.extensions.keys() if e.startswith("cogs.")],
                    "load_times": dict(self.bot.extension_load_times)
                },
                
                "cogs": {
                    "total_loaded": len(self.bot.cogs),
                    "list": list(self.bot.cogs.keys())
                },
                
                "commands": {
                    "total_registered": len(self.bot.commands),
                    "slash_commands": len(self.bot.tree.get_commands()),
                    "command_list": [cmd.name for cmd in self.bot.commands]
                },
                
                "servers": {
                    "total_guilds": len(self.bot.guilds),
                    "total_users": len(self.bot.users),
                    "total_channels": sum(len(guild.channels) for guild in self.bot.guilds)
                },
                
                "performance": {
                    **system_info,
                    "commands_processed": self.bot.metrics.commands_processed,
                    "messages_seen": self.bot.metrics.messages_seen,
                    "error_count": self.bot.metrics.error_count,
                    "event_loop_lag_ms": round(self.health_metrics["event_loop_lag_ms"], 2)
                },
                
                "config": {
                    "prefix": self.bot.config.get("prefix", "!"),
                    "auto_reload": self.bot.config.get("auto_reload", False),
                    "extensions_auto_load": self.bot.config.get("extensions.auto_load", True)
                },
                
                "database": {
                    "connected": self.bot.db.conn is not None,
                    "path": str(self.bot.db.base_path)
                },
                
                "health": {
                    "error_rate": error_rate,
                    "last_error": self.health_metrics["last_error"],
                    "consecutive_write_failures": self.health_metrics["consecutive_write_failures"],
                    "event_loop_lag_ms": round(self.health_metrics["event_loop_lag_ms"], 2)
                }
            }
            
            try:
                await self.bot.config.file_handler.atomic_write_json(
                    str(self.diagnostics_file),
                    diagnostics
                )
                self.health_metrics["consecutive_write_failures"] = 0
                logger.info(f"Diagnostics write queued: {self.diagnostics_file}")
            except Exception as e:
                self.health_metrics["consecutive_write_failures"] += 1
                logger.error(f"Failed to queue diagnostics write: {e}")
                await self._send_alert(f"⚠️ Framework diagnostics write failed ({self.health_metrics['consecutive_write_failures']} consecutive): {e}")
            
            return diagnostics
        
        except Exception as e:
            logger.error(f"Failed to generate diagnostics: {e}", exc_info=True)
            await self._send_alert(f"❌ Critical: Framework diagnostics generation failed: {e}")
            return None
    
    @tasks.loop(seconds=1)
    async def loop_lag_monitor(self):
        lag = await self._check_event_loop_lag()
        self.health_metrics["event_loop_lag_ms"] = lag
        
        if lag > self.loop_lag_threshold * 1000:
            logger.warning(f"Event loop lag detected: {lag:.2f}ms")
            await self._send_alert(f"⚠️ Framework event loop lag: {lag:.2f}ms (threshold: {self.loop_lag_threshold * 1000}ms)")
    
    @tasks.loop(minutes=5)
    async def health_monitor(self):
        self.last_health_check = datetime.now()
        
        error_rate = self._calculate_error_rate()
        
        status = "healthy"
        if error_rate >= 10:
            status = "critical"
            await self._send_alert(f"🚨 Framework critical health: Error rate {error_rate}%")
        elif error_rate >= 5:
            status = "degraded"
            await self._send_alert(f"⚠️ Framework degraded health: Error rate {error_rate}%")
        
        health_status = {
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "error_rate": error_rate,
            "total_commands": self.bot.metrics.commands_processed,
            "total_errors": self.bot.metrics.error_count,
            "last_error": self.health_metrics["last_error"],
            "event_loop_lag_ms": round(self.health_metrics["event_loop_lag_ms"], 2),
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "latency_ms": round(self.bot.latency * 1000, 2)
        }
        
        try:
            await self.bot.config.file_handler.atomic_write_json(
                str(self.health_file),
                health_status
            )
            self.health_metrics["consecutive_write_failures"] = 0
        except Exception as e:
            self.health_metrics["consecutive_write_failures"] += 1
            logger.error(f"Failed to write health status: {e}")
            if self.health_metrics["consecutive_write_failures"] >= 3:
                await self._send_alert(f"🚨 Critical: Framework health write failed {self.health_metrics['consecutive_write_failures']} times")
    
    async def _send_alert(self, message: str):
        if not self.alert_channel_id:
            logger.warning(f"Framework Alert (no channel configured): {message}")
            return
        
        try:
            channel = self.bot.get_channel(self.alert_channel_id)
            if channel:
                embed = discord.Embed(
                    title="🔧 Framework Diagnostics Alert",
                    description=message,
                    color=0xff0000,
                    timestamp=discord.utils.utcnow()
                )
                await channel.send(embed=embed)
            else:
                logger.warning(f"Framework alert channel {self.alert_channel_id} not found: {message}")
        except Exception as e:
            logger.error(f"Failed to send framework alert: {e}")
    
    @loop_lag_monitor.before_loop
    async def before_loop_lag_monitor(self):
        await self.bot.wait_until_ready()
        self._last_lag_check = time.monotonic()
    
    @health_monitor.before_loop
    async def before_health_monitor(self):
        await self.bot.wait_until_ready()
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        self.health_metrics["last_error"] = {
            "command": ctx.command.name if ctx.command else "unknown",
            "error": str(error),
            "timestamp": datetime.now().isoformat()
        }
    
    @commands.hybrid_command(name="fw_diagnostics", help="Display framework diagnostics and health status (Bot Owner Only)")
    @commands.is_owner()
    async def fw_diagnostics_command(self, ctx):
        embed = discord.Embed(
            title="🔧 Framework Diagnostics",
            description="**Current framework health and status**",
            color=0x00ff00,
            timestamp=discord.utils.utcnow()
        )
        
        diag = await self.generate_diagnostics()
        
        if not diag:
            await ctx.send("❌ Failed to generate framework diagnostics report", ephemeral=True)
            return
        
        uptime = timedelta(seconds=int(diag["uptime_seconds"]))
        embed.add_field(
            name="⏱️ Uptime",
            value=f"```{str(uptime)}```",
            inline=True
        )
        
        embed.add_field(
            name="📡 Latency",
            value=f"```{diag['bot']['latency_ms']}ms```",
            inline=True
        )
        
        embed.add_field(
            name="💾 Memory",
            value=f"```{diag['performance']['memory_usage_mb']} MB```",
            inline=True
        )
        
        embed.add_field(
            name="🔌 Extensions",
            value=f"```{diag['extensions']['total_loaded']} user\n{len(diag['extensions']['framework_cogs'])} framework```",
            inline=True
        )
        
        embed.add_field(
            name="📝 Commands",
            value=f"```{diag['commands']['total_registered']} total\n{diag['commands']['slash_commands']} slash```",
            inline=True
        )
        
        embed.add_field(
            name="🌐 Servers",
            value=f"```{diag['servers']['total_guilds']} guilds\n{diag['servers']['total_users']} users```",
            inline=True
        )
        
        if diag['health']['error_rate'] >= 10:
            health_status = "🚨 Critical"
            embed.color = 0xff0000
        elif diag['health']['error_rate'] >= 5:
            health_status = "⚠️ Degraded"
            embed.color = 0xffa500
        else:
            health_status = "✅ Healthy"
        
        embed.add_field(
            name="🏥 Health",
            value=f"```{health_status}\nError Rate: {diag['health']['error_rate']}%\nLoop Lag: {diag['performance']['event_loop_lag_ms']:.2f}ms```",
            inline=False
        )
        
        embed.add_field(
            name="📊 Diagnostics Files",
            value=f"```Full Report: {self.diagnostics_file}\nHealth Status: {self.health_file}```",
            inline=False
        )
        
        embed.set_footer(text="Framework Diagnostics System")
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    @commands.hybrid_command(name="fw_alert_channel", help="Set the alert channel for framework diagnostics (Bot Owner Only)")
    @commands.is_owner()
    async def fw_alert_channel_command(self, ctx, channel: discord.TextChannel = None):
        if channel is None:
            channel = ctx.channel
        
        self.alert_channel_id = channel.id
        await ctx.send(f"✅ Framework diagnostics alert channel set to {channel.mention}", ephemeral=True)
    
    def cog_unload(self):
        if self.health_monitor.is_running():
            self.health_monitor.cancel()
        if self.loop_lag_monitor.is_running():
            self.loop_lag_monitor.cancel()
        logger.info("Framework Diagnostics: Cog unloaded")


async def setup(bot):
    await bot.add_cog(FrameworkDiagnostics(bot))
    logger.info("Framework Diagnostics cog loaded successfully")