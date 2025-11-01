"""
Framework Diagnostics Cog
Tracks and reports framework health, performance, and state
"""

from discord.ext import commands, tasks
import discord
from datetime import datetime, timedelta
from pathlib import Path
import psutil
import platform
import sys
from typing import Dict, Any
import logging

logger = logging.getLogger('discord')


class FrameworkDiagnostics(commands.Cog):
    
    
    def __init__(self, bot):
        self.bot = bot
        self.diagnostics_file = Path("./data/framework_diagnostics.json")
        self.health_file = Path("./data/framework_health.json")
        self.start_time = datetime.now()
        self.last_health_check = None
        

        self.diagnostics_file.parent.mkdir(parents=True, exist_ok=True)
        

        self.health_metrics = {
            "total_errors": 0,
            "total_commands": 0,
            "last_error": None,
            "error_rate": 0.0
        }
    
    @commands.Cog.listener()
    async def on_ready(self):
        
        logger.info("Framework Diagnostics: Generating initial report")
        await self.generate_diagnostics()
        

        if not self.health_monitor.is_running():
            self.health_monitor.start()
    
    async def generate_diagnostics(self) -> Dict[str, Any]:
        
        
        process = psutil.Process()
        memory_info = process.memory_info()
        
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
                "total_channels": sum(len(guild.channels) for guild in self.bot.guilds),
                "guild_list": [
                    {
                        "id": guild.id,
                        "name": guild.name,
                        "member_count": guild.member_count
                    }
                    for guild in self.bot.guilds
                ]
            },
            

            "performance": {
                "memory_usage_mb": round(memory_info.rss / 1024 / 1024, 2),
                "cpu_percent": process.cpu_percent(),
                "threads": process.num_threads(),
                "commands_processed": self.bot.metrics.commands_processed,
                "messages_seen": self.bot.metrics.messages_seen,
                "error_count": self.bot.metrics.error_count
            },
            

            "config": {
                "prefix": self.bot.config.get("prefix", "!"),
                "auto_reload": self.bot.config.get("auto_reload", False),
                "extensions_auto_load": self.bot.config.get("extensions.auto_load", True)
            },
            

            "database": {
                "connected": self.bot.db.conn is not None,
                "path": str(self.bot.db.db_path)
            },
            

            "health": self.health_metrics
        }
        

        try:
            await self.bot.config.file_handler.atomic_write_json(
                str(self.diagnostics_file),
                diagnostics
            )
            logger.info(f"Diagnostics written to {self.diagnostics_file}")
        except Exception as e:
            logger.error(f"Failed to write diagnostics: {e}")
        
        return diagnostics
    
    @tasks.loop(minutes=5)
    async def health_monitor(self):
        
        self.last_health_check = datetime.now()
        

        total_commands = self.bot.metrics.commands_processed
        total_errors = self.bot.metrics.error_count
        
        if total_commands > 0:
            self.health_metrics["error_rate"] = round(
                (total_errors / total_commands) * 100, 2
            )
        
        self.health_metrics["total_errors"] = total_errors
        self.health_metrics["total_commands"] = total_commands
        

        health_status = {
            "timestamp": datetime.now().isoformat(),
            "status": "healthy" if self.health_metrics["error_rate"] < 5 else "degraded",
            "metrics": self.health_metrics,
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "latency_ms": round(self.bot.latency * 1000, 2)
        }
        

        try:
            await self.bot.config.file_handler.atomic_write_json(
                str(self.health_file),
                health_status
            )
        except Exception as e:
            logger.error(f"Failed to write health status: {e}")
    
    @health_monitor.before_loop
    async def before_health_monitor(self):
        await self.bot.wait_until_ready()
    
    @commands.Cog.listener()
    async def on_command(self, ctx):
        
        self.health_metrics["total_commands"] += 1
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        
        self.health_metrics["total_errors"] += 1
        self.health_metrics["last_error"] = {
            "command": ctx.command.name if ctx.command else "unknown",
            "error": str(error),
            "timestamp": datetime.now().isoformat()
        }
    
    @commands.hybrid_command(name="diagnostics", help="Display framework diagnostics (Bot Owner Only)")
    @commands.is_owner()
    async def diagnostics_command(self, ctx):
        
        
        embed = discord.Embed(
            title="🔧 Framework Diagnostics",
            description="**Current framework health and status**",
            color=0x00ff00,
            timestamp=discord.utils.utcnow()
        )
        

        diag = await self.generate_diagnostics()
        

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
        

        health_status = "✅ Healthy" if diag['health']['error_rate'] < 5 else "⚠️ Degraded"
        embed.add_field(
            name="🏥 Health",
            value=f"```{health_status}\nError Rate: {diag['health']['error_rate']}%```",
            inline=False
        )
        

        embed.add_field(
            name="📁 Diagnostics Files",
            value=f"```Full Report: {self.diagnostics_file}\nHealth Status: {self.health_file}```",
            inline=False
        )
        
        embed.set_footer(text="Framework Diagnostics System")
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    def cog_unload(self):
        
        if self.health_monitor.is_running():
            self.health_monitor.cancel()
        logger.info("Framework Diagnostics: Cog unloaded")


async def setup(bot):
    
    await bot.add_cog(FrameworkDiagnostics(bot))
    logger.info("Framework Diagnostics cog loaded successfully")