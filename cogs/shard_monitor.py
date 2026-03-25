"""
# ===================================================================================
#
#   Copyright (c) 2026 TheHolyOneZ
#
#   This script is part of the ZDBF (Zoryx Discord Bot Framework).
#   This file is considered source-available and is not open-source.
#
#   You are granted permission to:
#   - View, read, and learn from this source code.
#   - Use this script 'as is' within the ZDBF.
#   - Run this script in multiple instances of your own ZDBF-based projects,
#     provided the license and script remain intact.
#
#   You are strictly prohibited from:
#   - Copying and pasting more than four (4) consecutive lines of this code
#     into other projects without explicit permission.
#   - Redistributing this script or any part of it. The only official source
#     is the GitHub repository: https://github.com/TheHolyOneZ/discord-bot-framework
#   - Modifying this license text.
#   - Removing any attribution or mention of the original author (TheHolyOneZ)
#     or the project names (ZDBF, TheZ).
#
#   This script is intended for use ONLY within the ZDBF ecosystem.
#   Use in any other framework is a direct violation of this license.
#
#   For issues, support, or feedback, please create an issue on the official
#   GitHub repository or contact the author through the official Discord server.
#
#   This software is provided "as is", without warranty of any kind, express or
#   implied, including but not limited to the warranties of merchantability,
#   fitness for a particular purpose and noninfringement. In no event shall the
#   authors or copyright holders be liable for any claim, damages or other
#   liability, whether in an action of contract, tort or otherwise, arising from,
#   out of or in connection with the software or the use or other dealings in the
#   software.
#
# ===================================================================================
"""
# Advanced Shard Monitor - v2.0.0 | Created by TheHolyOneZ
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import time
import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
import json
from pathlib import Path

logger = logging.getLogger('discord.cogs.shard_monitor')

BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", 0))


def is_bot_owner():
    """Check if user is the bot owner — BOT_OWNER_ID env var, with application_info() fallback."""
    async def predicate(ctx):
        if BOT_OWNER_ID and ctx.author.id == BOT_OWNER_ID:
            return True
        try:
            app_info = await ctx.bot.application_info()
            if ctx.author.id == app_info.owner.id:
                return True
        except Exception:
            pass
        raise commands.CheckFailure("This command is restricted to the bot owner only.")
    return commands.check(predicate)


class ShardMetrics:
    """Tracks metrics for a single shard"""
    
    def __init__(self, shard_id: int):
        self.shard_id = shard_id
        self.latency_history: deque = deque(maxlen=120)
        self.event_counts: Dict[str, int] = defaultdict(int)
        self.last_event_time: float = time.time()
        self.connect_count: int = 0
        self.disconnect_count: int = 0
        self.reconnect_count: int = 0
        self.last_connect: Optional[float] = None
        self.last_disconnect: Optional[float] = None
        self.error_count: int = 0
        self.last_error: Optional[dict] = None
        self.messages_processed: int = 0
        self.commands_executed: int = 0
        self.uptime_start: float = time.time()
        self.total_downtime: float = 0
        self._disconnect_start: Optional[float] = None
        self.last_health_check: float = time.time()
        self.consecutive_failures: int = 0
        self.guilds_joined: int = 0
        self.guilds_left: int = 0
        
    def record_latency(self, latency: float):
        """Record latency measurement"""
        self.latency_history.append({
            'timestamp': time.time(),
            'latency': latency
        })
        
    def record_event(self, event_name: str):
        """Record an event"""
        self.event_counts[event_name] += 1
        self.last_event_time = time.time()
        
    def record_connect(self):
        """Record shard connection"""
        self.connect_count += 1
        self.last_connect = time.time()
        self.consecutive_failures = 0
        if self._disconnect_start:
            self.total_downtime += time.time() - self._disconnect_start
            self._disconnect_start = None
        
    def record_disconnect(self):
        """Record shard disconnection"""
        self.disconnect_count += 1
        self.last_disconnect = time.time()
        if not self._disconnect_start:
            self._disconnect_start = time.time()
            
    def record_reconnect(self):
        """Record shard reconnection"""
        self.reconnect_count += 1
        if self._disconnect_start:
            self.total_downtime += time.time() - self._disconnect_start
            self._disconnect_start = None
        
    def record_error(self, error: str):
        """Record an error"""
        self.error_count += 1
        self.last_error = {'timestamp': time.time(), 'error': str(error)[:500]}
        self.consecutive_failures += 1
        
    def record_message(self):
        """Record message processed"""
        self.messages_processed += 1
        
    def record_command(self):
        """Record command executed"""
        self.commands_executed += 1
        
    def get_avg_latency(self) -> float:
        """Get average latency over history"""
        if not self.latency_history:
            return 0.0
        return sum(m['latency'] for m in self.latency_history) / len(self.latency_history)
    
    def get_min_latency(self) -> float:
        """Get minimum latency from history"""
        if not self.latency_history:
            return 0.0
        return min(m['latency'] for m in self.latency_history)
    
    def get_max_latency(self) -> float:
        """Get maximum latency from history"""
        if not self.latency_history:
            return 0.0
        return max(m['latency'] for m in self.latency_history)
    
    def get_current_latency(self) -> float:
        """Get most recent latency"""
        if not self.latency_history:
            return 0.0
        return self.latency_history[-1]['latency']
    
    def get_uptime_percentage(self) -> float:
        """Calculate uptime percentage"""
        total_time = time.time() - self.uptime_start
        if total_time == 0:
            return 100.0
        current_downtime = self.total_downtime
        if self._disconnect_start:
            current_downtime += time.time() - self._disconnect_start
        uptime = total_time - current_downtime
        return max(0.0, (uptime / total_time) * 100)
    
    def get_events_per_minute(self) -> float:
        """Get events per minute rate"""
        elapsed = time.time() - self.uptime_start
        if elapsed <= 0:
            return 0.0
        total_events = sum(self.event_counts.values())
        return (total_events / elapsed) * 60
    
    def is_healthy(self, threshold: int = 3) -> Tuple[bool, str]:
        """Check if shard is healthy"""
        avg_latency = self.get_avg_latency()
        if avg_latency > 1.0:
            return False, f"High latency: {avg_latency*1000:.0f}ms"

        time_since_event = time.time() - self.last_event_time
        if time_since_event > 300:
            return False, f"No activity for {time_since_event/60:.1f} minutes"

        if self.consecutive_failures >= threshold:
            return False, f"{self.consecutive_failures} consecutive failures"
        
        if self._disconnect_start:
            return False, "Currently disconnected"
        
        if self.last_disconnect and (time.time() - self.last_disconnect < 60):
            return False, "Recently disconnected"
        
        return True, "Healthy"
    
    def get_health_status(self) -> str:
        """Get health status emoji"""
        is_healthy, reason = self.is_healthy()
        if is_healthy:
            return "🟢"
        
        avg_latency = self.get_avg_latency()
        if avg_latency > 2.0 or self.consecutive_failures >= 5 or self._disconnect_start:
            return "🔴"
        return "🟡"
    
    def to_dict(self) -> dict:
        """Serialize metrics for saving"""
        return {
            'shard_id': self.shard_id,
            'latency_avg': self.get_avg_latency(),
            'latency_current': self.get_current_latency(),
            'latency_min': self.get_min_latency(),
            'latency_max': self.get_max_latency(),
            'events': dict(self.event_counts),
            'connects': self.connect_count,
            'disconnects': self.disconnect_count,
            'reconnects': self.reconnect_count,
            'errors': self.error_count,
            'messages': self.messages_processed,
            'commands': self.commands_executed,
            'uptime_pct': self.get_uptime_percentage(),
            'health_status': self.get_health_status(),
            'guilds_joined': self.guilds_joined,
            'guilds_left': self.guilds_left,
            'timestamp': time.time()
        }


class ShardMonitorView(discord.ui.View):
    """Interactive view for the shard monitor dashboard"""
    
    def __init__(self, cog, author: discord.User, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author = author
        self.current_page = "overview"
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Only the command user can interact with this.", ephemeral=True)
            return False
        return True
    
    @discord.ui.button(label="Overview", style=discord.ButtonStyle.blurple, emoji="📊", row=0)
    async def overview_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "overview"
        embed = self.cog._build_overview_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Health", style=discord.ButtonStyle.green, emoji="🏥", row=0)
    async def health_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "health"
        embed = self.cog._build_health_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Latency", style=discord.ButtonStyle.gray, emoji="📡", row=0)
    async def latency_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "latency"
        embed = self.cog._build_latency_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Events", style=discord.ButtonStyle.gray, emoji="📈", row=0)
    async def events_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "events"
        embed = self.cog._build_events_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.green, emoji="🔄", row=1)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        builder = {
            "overview": self.cog._build_overview_embed,
            "health": self.cog._build_health_embed,
            "latency": self.cog._build_latency_embed,
            "events": self.cog._build_events_embed,
        }
        embed = builder.get(self.current_page, self.cog._build_overview_embed)()
        await interaction.response.edit_message(embed=embed, view=self)


class ShardMonitor(commands.Cog):
    """
    Advanced Shard Monitoring System (Bot Owner Only)
    
    Tracks health, performance, latency, events, and provides
    real-time diagnostics for multi-shard deployments.
    
    All commands restricted to BOT_OWNER_ID.
    Toggle via ENABLE_SHARD_MONITOR in .env
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.metrics: Dict[int, ShardMetrics] = {}
        self.alert_channel_id: Optional[int] = None
        self.alert_threshold: int = int(os.getenv("SHARD_ALERT_THRESHOLD", 3))
        self.monitoring_enabled: bool = True
        self._last_alert_time: dict = {}
        self.data_dir = Path("./data/shard_monitor")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._load_alert_config()
        
        if hasattr(self.bot, 'shards') and self.bot.shards:
            for shard_id in self.bot.shards.keys():
                self.metrics[shard_id] = ShardMetrics(shard_id)
        else:
            self.metrics[0] = ShardMetrics(0)
        
        logger.info(f"ShardMonitor cog loaded | Shards tracked: {len(self.metrics)} | Alert threshold: {self.alert_threshold}")
    
    def _load_alert_config(self):
        """Load alert channel configuration from disk"""
        config_path = self.data_dir / "alert_config.json"
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                self.alert_channel_id = config.get('alert_channel_id')
                self.alert_threshold = config.get('alert_threshold', self.alert_threshold)
        except Exception as e:
            logger.error(f"Error loading shard alert config: {e}")
    
    async def _save_alert_config(self):
        """Save alert channel configuration to disk"""
        config_path = self.data_dir / "alert_config.json"
        data = {
            'alert_channel_id': self.alert_channel_id,
            'alert_threshold': self.alert_threshold
        }
        try:
            await asyncio.to_thread(
                lambda: config_path.write_text(json.dumps(data, indent=2))
            )
        except Exception as e:
            logger.error(f"Error saving shard alert config: {e}")
    
    async def cog_load(self):
        """Start monitoring tasks"""
        self.collect_metrics.start()
        self.health_check.start()
        self.save_metrics.start()
        logger.info("ShardMonitor tasks started")
    
    def cog_unload(self):
        """Stop monitoring tasks"""
        self.collect_metrics.cancel()
        self.health_check.cancel()
        self.save_metrics.cancel()
        logger.info("ShardMonitor cog unloaded")
    
    
    @tasks.loop(seconds=30)
    async def collect_metrics(self):
        """Collect metrics from all shards"""
        try:
            for shard_id, shard in self.bot.shards.items():
                if shard_id not in self.metrics:
                    self.metrics[shard_id] = ShardMetrics(shard_id)
                
                self.metrics[shard_id].record_latency(shard.latency)
                self.metrics[shard_id].record_event('metrics_collection')
                
        except Exception as e:
            logger.error(f"Error collecting shard metrics: {e}")
    
    @collect_metrics.before_loop
    async def before_collect_metrics(self):
        await self.bot.wait_until_ready()
    
    @tasks.loop(minutes=1)
    async def health_check(self):
        """Check health of all shards and send alerts"""
        try:
            unhealthy_shards = []
            
            for shard_id, metrics in self.metrics.items():
                is_healthy, reason = metrics.is_healthy(self.alert_threshold)
                if not is_healthy:
                    unhealthy_shards.append((shard_id, reason))
            
            if unhealthy_shards and self.alert_channel_id:
                now = time.time()
                if now - self._last_alert_time.get("last", 0) > 300:
                    self._last_alert_time["last"] = now
                    await self._send_health_alert(unhealthy_shards)
                
        except Exception as e:
            logger.error(f"Error during shard health check: {e}")
    
    @health_check.before_loop
    async def before_health_check(self):
        await self.bot.wait_until_ready()
    
    @tasks.loop(minutes=5)
    async def save_metrics(self):
        """Save metrics to disk for persistence"""
        try:
            metrics_data = {str(sid): m.to_dict() for sid, m in self.metrics.items()}
            filepath = self.data_dir / "shard_metrics.json"
            await asyncio.to_thread(
                lambda: filepath.write_text(json.dumps(metrics_data, indent=2))
            )
        except Exception as e:
            logger.error(f"Error saving shard metrics: {e}")
    
    @save_metrics.before_loop
    async def before_save_metrics(self):
        await self.bot.wait_until_ready()
    
    
    async def _send_health_alert(self, unhealthy_shards: List[Tuple[int, str]]):
        """Send health alert to configured channel"""
        try:
            channel = self.bot.get_channel(self.alert_channel_id)
            if not channel:
                return
            
            embed = discord.Embed(
                title="⚠️ Shard Health Alert",
                description=f"**{len(unhealthy_shards)} shard(s) reporting issues**",
                color=0xff9900,
                timestamp=discord.utils.utcnow()
            )
            
            for shard_id, reason in unhealthy_shards[:10]:
                metrics = self.metrics[shard_id]
                status = metrics.get_health_status()
                
                embed.add_field(
                    name=f"{status} Shard {shard_id}",
                    value=f"```{reason}\nLatency: {metrics.get_current_latency()*1000:.0f}ms\nUptime: {metrics.get_uptime_percentage():.1f}%```",
                    inline=True
                )
            
            embed.set_footer(text="Shard Monitor Alert System")
            await channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error sending shard health alert: {e}")
    
    
    def _build_overview_embed(self) -> discord.Embed:
        """Build the overview dashboard embed"""
        embed = discord.Embed(
            title="📊 Shard Monitor — Overview",
            description=f"**Monitoring {self.bot.shard_count} shard(s)**",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        total_guilds = len(self.bot.guilds)
        total_messages = sum(m.messages_processed for m in self.metrics.values())
        total_commands = sum(m.commands_executed for m in self.metrics.values())
        avg_latency = sum(m.get_avg_latency() for m in self.metrics.values()) / max(len(self.metrics), 1)
        
        embed.add_field(
            name="🌐 Cluster Stats",
            value=(
                f"```\n"
                f"Total Guilds:   {total_guilds:,}\n"
                f"Avg Latency:    {avg_latency*1000:.1f}ms\n"
                f"Messages:       {total_messages:,}\n"
                f"Commands:       {total_commands:,}\n"
                f"```"
            ),
            inline=False
        )
        
        healthy = sum(1 for m in self.metrics.values() if m.is_healthy()[0])
        unhealthy = len(self.metrics) - healthy
        avg_uptime = sum(m.get_uptime_percentage() for m in self.metrics.values()) / max(len(self.metrics), 1)
        
        embed.add_field(
            name="💚 Health",
            value=f"```✅ Healthy: {healthy}\n⚠️ Issues:  {unhealthy}```",
            inline=True
        )
        embed.add_field(
            name="⏱️ Avg Uptime",
            value=f"```{avg_uptime:.2f}%```",
            inline=True
        )
        
        if self.bot.shard_count <= 15:
            shard_lines = []
            for sid in sorted(self.metrics.keys()):
                m = self.metrics[sid]
                status = m.get_health_status()
                guilds = len([g for g in self.bot.guilds if g.shard_id == sid])
                lat = m.get_current_latency()
                shard_lines.append(f"{status} S{sid}: {guilds:,}g | {lat*1000:.0f}ms | {m.get_uptime_percentage():.1f}%")
            
            if shard_lines:
                embed.add_field(
                    name="📋 Shard Details",
                    value="```" + "\n".join(shard_lines) + "```",
                    inline=False
                )
        else:
            embed.add_field(
                name="ℹ️ Info",
                value=f"```{self.bot.shard_count} shards — use /sharddetails <id> for specifics```",
                inline=False
            )
        
        alert_status = f"#{self.bot.get_channel(self.alert_channel_id).name}" if self.alert_channel_id and self.bot.get_channel(self.alert_channel_id) else "Disabled"
        embed.add_field(
            name="🔔 Alerts",
            value=f"```Channel: {alert_status}\nThreshold: {self.alert_threshold} failures```",
            inline=False
        )
        
        embed.set_footer(text="Bot Owner Only • Use buttons to navigate")
        return embed
    
    def _build_health_embed(self) -> discord.Embed:
        """Build the health check embed"""
        healthy_shards = []
        warning_shards = []
        critical_shards = []
        
        for sid in sorted(self.metrics.keys()):
            m = self.metrics[sid]
            status = m.get_health_status()
            is_h, reason = m.is_healthy(self.alert_threshold)
            info = f"Shard {sid}: {reason}"
            
            if status == "🟢":
                healthy_shards.append(info)
            elif status == "🟡":
                warning_shards.append(info)
            else:
                critical_shards.append(info)
        
        if critical_shards:
            overall = "🔴 Critical — Immediate attention required"
            color = 0xff0000
        elif warning_shards:
            overall = "🟡 Warning — Monitor closely"
            color = 0xff9900
        else:
            overall = "🟢 Healthy — All systems operational"
            color = 0x00ff00
        
        embed = discord.Embed(
            title="🏥 Shard Monitor — Health Report",
            description=f"**{self.bot.shard_count} shard(s) checked**",
            color=color,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="🎯 Overall Status",
            value=f"```{overall}```",
            inline=False
        )
        
        embed.add_field(
            name="📊 Summary",
            value=f"```🟢 Healthy:  {len(healthy_shards)}\n🟡 Warning:  {len(warning_shards)}\n🔴 Critical: {len(critical_shards)}```",
            inline=False
        )
        
        if critical_shards:
            embed.add_field(
                name="🔴 Critical Shards",
                value="```" + "\n".join(critical_shards[:10]) + "```",
                inline=False
            )
        
        if warning_shards:
            embed.add_field(
                name="🟡 Warning Shards",
                value="```" + "\n".join(warning_shards[:10]) + "```",
                inline=False
            )
        
        embed.set_footer(text="Bot Owner Only • Auto-refreshes every 60s")
        return embed
    
    def _build_latency_embed(self) -> discord.Embed:
        """Build the latency details embed"""
        embed = discord.Embed(
            title="📡 Shard Monitor — Latency Details",
            description=f"**Latency across {self.bot.shard_count} shard(s)**",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        latency_lines = []
        for sid in sorted(self.metrics.keys()):
            m = self.metrics[sid]
            cur = m.get_current_latency() * 1000
            avg = m.get_avg_latency() * 1000
            mn = m.get_min_latency() * 1000
            mx = m.get_max_latency() * 1000
            
            bar_len = min(int(cur / 10), 20)
            bar_char = "█" if cur < 200 else "▓" if cur < 500 else "░"
            bar = bar_char * max(bar_len, 1)
            
            latency_lines.append(f"S{sid}: {cur:6.0f}ms {bar}")
        
        if latency_lines:
            chunk_size = 15
            for i in range(0, len(latency_lines), chunk_size):
                chunk = latency_lines[i:i+chunk_size]
                name = "📊 Current Latency" if i == 0 else f"📊 Continued ({i+1}-{i+len(chunk)})"
                embed.add_field(
                    name=name,
                    value="```" + "\n".join(chunk) + "```",
                    inline=False
                )
        
        all_avg = [m.get_avg_latency() * 1000 for m in self.metrics.values()]
        if all_avg:
            embed.add_field(
                name="📈 Cluster Latency Stats",
                value=(
                    f"```\n"
                    f"Cluster Avg:  {sum(all_avg)/len(all_avg):.1f}ms\n"
                    f"Best Shard:   {min(all_avg):.1f}ms\n"
                    f"Worst Shard:  {max(all_avg):.1f}ms\n"
                    f"Spread:       {max(all_avg) - min(all_avg):.1f}ms\n"
                    f"```"
                ),
                inline=False
            )
        
        embed.set_footer(text="Bot Owner Only • Measurements every 30s")
        return embed
    
    def _build_events_embed(self) -> discord.Embed:
        """Build the events/activity embed"""
        embed = discord.Embed(
            title="📈 Shard Monitor — Event Activity",
            description=f"**Activity across {self.bot.shard_count} shard(s)**",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        for sid in sorted(self.metrics.keys()):
            m = self.metrics[sid]
            status = m.get_health_status()
            time_since = time.time() - m.last_event_time
            
            embed.add_field(
                name=f"{status} Shard {sid}",
                value=(
                    f"```\n"
                    f"Messages:     {m.messages_processed:,}\n"
                    f"Commands:     {m.commands_executed:,}\n"
                    f"Connects:     {m.connect_count}\n"
                    f"Disconnects:  {m.disconnect_count}\n"
                    f"Reconnects:   {m.reconnect_count}\n"
                    f"Errors:       {m.error_count}\n"
                    f"Last Event:   {time_since:.0f}s ago\n"
                    f"```"
                ),
                inline=True
            )
            
            if sid >= 8:
                remaining = len(self.metrics) - 9
                if remaining > 0:
                    embed.add_field(
                        name="ℹ️",
                        value=f"```+{remaining} more shards (use /sharddetails)```",
                        inline=False
                    )
                break
        
        embed.set_footer(text="Bot Owner Only • Tracking since cog load")
        return embed
    
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Track messages per shard"""
        if message.guild:
            shard_id = message.guild.shard_id
            if shard_id in self.metrics:
                self.metrics[shard_id].record_message()
    
    @commands.Cog.listener()
    async def on_command(self, ctx):
        """Track commands per shard"""
        if ctx.guild:
            shard_id = ctx.guild.shard_id
            if shard_id in self.metrics:
                self.metrics[shard_id].record_command()
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Track guild joins per shard"""
        if guild.shard_id in self.metrics:
            self.metrics[guild.shard_id].guilds_joined += 1
            self.metrics[guild.shard_id].record_event('guild_join')
    
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """Track guild removals per shard"""
        if guild.shard_id in self.metrics:
            self.metrics[guild.shard_id].guilds_left += 1
            self.metrics[guild.shard_id].record_event('guild_remove')
    
    @commands.Cog.listener()
    async def on_shard_connect(self, shard_id):
        """Track shard connections"""
        if shard_id not in self.metrics:
            self.metrics[shard_id] = ShardMetrics(shard_id)
        self.metrics[shard_id].record_connect()
        logger.info(f"[ShardMonitor] Shard {shard_id} connected")
    
    @commands.Cog.listener()
    async def on_shard_disconnect(self, shard_id):
        """Track shard disconnections"""
        if shard_id in self.metrics:
            self.metrics[shard_id].record_disconnect()
        logger.warning(f"[ShardMonitor] Shard {shard_id} disconnected")
    
    @commands.Cog.listener()
    async def on_shard_resumed(self, shard_id):
        """Track shard reconnections"""
        if shard_id in self.metrics:
            self.metrics[shard_id].record_reconnect()
        logger.info(f"[ShardMonitor] Shard {shard_id} resumed")
    
    @commands.Cog.listener()
    async def on_shard_ready(self, shard_id):
        """Track shard ready events"""
        if shard_id not in self.metrics:
            self.metrics[shard_id] = ShardMetrics(shard_id)
        self.metrics[shard_id].record_event('shard_ready')
        logger.info(f"[ShardMonitor] Shard {shard_id} ready")
    
    
    @commands.hybrid_command(
        name="shardmonitor",
        help="Display the interactive shard monitoring dashboard (Bot Owner Only)"
    )
    @is_bot_owner()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def shard_monitor_cmd(self, ctx):
        """Show the interactive shard monitoring dashboard"""
        embed = self._build_overview_embed()
        view = ShardMonitorView(self, ctx.author)
        await ctx.send(embed=embed, view=view)
    
    @commands.hybrid_command(
        name="sharddetails",
        help="Get detailed metrics for a specific shard (Bot Owner Only)"
    )
    @is_bot_owner()
    @commands.cooldown(1, 10, commands.BucketType.user)
    @app_commands.describe(shard_id="The shard ID to inspect")
    async def shard_details(self, ctx, shard_id: int):
        """Show detailed metrics for a specific shard"""
        
        if shard_id not in self.bot.shards:
            embed = discord.Embed(
                title="❌ Shard Not Found",
                description=f"```Shard {shard_id} does not exist.\nValid shards: {', '.join(str(s) for s in sorted(self.bot.shards.keys()))}```",
                color=0xff0000
            )
            await ctx.send(embed=embed)
            return
        
        if shard_id not in self.metrics:
            await ctx.send(f"❌ No metrics available for shard {shard_id}")
            return
        
        metrics = self.metrics[shard_id]
        guilds_on_shard = len([g for g in self.bot.guilds if g.shard_id == shard_id])
        members_on_shard = sum(g.member_count or 0 for g in self.bot.guilds if g.shard_id == shard_id)
        
        is_healthy, health_reason = metrics.is_healthy()
        status = metrics.get_health_status()
        
        embed = discord.Embed(
            title=f"{status} Shard {shard_id} — Detailed Metrics",
            description=f"**Health: {health_reason}**",
            color=0x00ff00 if is_healthy else (0xff0000 if status == "🔴" else 0xff9900),
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="📊 Basic Info",
            value=(
                f"```\n"
                f"Guilds:          {guilds_on_shard:,}\n"
                f"Members:         {members_on_shard:,}\n"
                f"Current Latency: {metrics.get_current_latency()*1000:.1f}ms\n"
                f"Avg Latency:     {metrics.get_avg_latency()*1000:.1f}ms\n"
                f"Min Latency:     {metrics.get_min_latency()*1000:.1f}ms\n"
                f"Max Latency:     {metrics.get_max_latency()*1000:.1f}ms\n"
                f"```"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📈 Activity",
            value=(
                f"```\n"
                f"Messages:   {metrics.messages_processed:,}\n"
                f"Commands:   {metrics.commands_executed:,}\n"
                f"Guilds +/-: +{metrics.guilds_joined} / -{metrics.guilds_left}\n"
                f"Last Event: {time.time() - metrics.last_event_time:.0f}s ago\n"
                f"```"
            ),
            inline=True
        )
        
        embed.add_field(
            name="🔧 Reliability",
            value=(
                f"```\n"
                f"Uptime:      {metrics.get_uptime_percentage():.2f}%\n"
                f"Connects:    {metrics.connect_count}\n"
                f"Disconnects: {metrics.disconnect_count}\n"
                f"Reconnects:  {metrics.reconnect_count}\n"
                f"```"
            ),
            inline=True
        )
        
        if metrics.error_count > 0:
            embed.add_field(
                name="⚠️ Errors",
                value=(
                    f"```\n"
                    f"Total Errors:        {metrics.error_count}\n"
                    f"Consecutive Failures: {metrics.consecutive_failures}\n"
                    f"```"
                ),
                inline=False
            )
            
            if metrics.last_error:
                time_ago = time.time() - metrics.last_error['timestamp']
                embed.add_field(
                    name="🔴 Last Error",
                    value=f"```{metrics.last_error['error'][:200]}```\n*{time_ago:.0f} seconds ago*",
                    inline=False
                )
        
        if metrics.last_connect:
            embed.add_field(
                name="🟢 Last Connect",
                value=f"```{datetime.fromtimestamp(metrics.last_connect).strftime('%Y-%m-%d %H:%M:%S')}```",
                inline=True
            )
        
        if metrics.last_disconnect:
            embed.add_field(
                name="🔴 Last Disconnect",
                value=f"```{datetime.fromtimestamp(metrics.last_disconnect).strftime('%Y-%m-%d %H:%M:%S')}```",
                inline=True
            )
        
        embed.set_footer(text=f"Bot Owner Only • Shard {shard_id}/{self.bot.shard_count - 1}")
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="shardhealth",
        help="Get health check report for all shards (Bot Owner Only)"
    )
    @is_bot_owner()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def shard_health(self, ctx):
        """Show health status for all shards"""
        embed = self._build_health_embed()
        embed.set_footer(text=f"Bot Owner Only • Requested by {ctx.author}")
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="shardalerts",
        help="Configure shard health alert channel and threshold (Bot Owner Only)"
    )
    @is_bot_owner()
    @app_commands.describe(
        channel="Channel to send alerts to (leave empty to disable)",
        threshold="Number of consecutive failures before alerting (default: 3)"
    )
    async def shard_alerts(self, ctx, channel: Optional[discord.TextChannel] = None, threshold: Optional[int] = None):
        """Configure alert channel and threshold for shard monitoring"""
        
        if threshold is not None:
            self.alert_threshold = max(1, min(threshold, 20))
        
        if channel:
            self.alert_channel_id = channel.id
            await self._save_alert_config()
            
            embed = discord.Embed(
                title="✅ Shard Alerts Configured",
                description=(
                    f"**Alert Channel:** {channel.mention}\n"
                    f"**Failure Threshold:** {self.alert_threshold} consecutive failures"
                ),
                color=0x00ff00,
                timestamp=discord.utils.utcnow()
            )
            logger.info(f"[ShardMonitor] Alert channel set to #{channel.name} ({channel.id}), threshold: {self.alert_threshold}")
        else:
            self.alert_channel_id = None
            await self._save_alert_config()
            
            embed = discord.Embed(
                title="⚠️ Shard Alerts Disabled",
                description="Health alerts have been turned off.\nUse `/shardalerts #channel` to re-enable.",
                color=0xff9900,
                timestamp=discord.utils.utcnow()
            )
            logger.info("[ShardMonitor] Alerts disabled")
        
        embed.set_footer(text=f"Bot Owner Only • Changed by {ctx.author}")
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(
        name="shardreset",
        help="Reset metrics for a specific shard or all shards (Bot Owner Only)"
    )
    @is_bot_owner()
    @app_commands.describe(shard_id="Shard ID to reset (-1 for all shards)")
    async def shard_reset(self, ctx, shard_id: int = -1):
        """Reset shard metrics"""
        
        if shard_id == -1:
            for sid in self.metrics:
                self.metrics[sid] = ShardMetrics(sid)
            
            embed = discord.Embed(
                title="🔄 All Shard Metrics Reset",
                description=f"```Reset metrics for {len(self.metrics)} shard(s)```",
                color=0x00ff00,
                timestamp=discord.utils.utcnow()
            )
        elif shard_id in self.metrics:
            self.metrics[shard_id] = ShardMetrics(shard_id)
            
            embed = discord.Embed(
                title=f"🔄 Shard {shard_id} Metrics Reset",
                description=f"```All metrics for shard {shard_id} have been reset```",
                color=0x00ff00,
                timestamp=discord.utils.utcnow()
            )
        else:
            embed = discord.Embed(
                title="❌ Shard Not Found",
                description=f"```Shard {shard_id} does not exist```",
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
        
        embed.set_footer(text=f"Bot Owner Only • {ctx.author}")
        await ctx.send(embed=embed)


async def setup(bot):
    """Load the ShardMonitor cog (respects ENABLE_SHARD_MONITOR env var)"""
    enabled = os.getenv("ENABLE_SHARD_MONITOR", "true").lower()
    
    if enabled not in ("true", "1", "yes"):
        logger.info("ShardMonitor cog is DISABLED via ENABLE_SHARD_MONITOR env var")
        return
    
    await bot.add_cog(ShardMonitor(bot))
    logger.info("ShardMonitor cog setup complete")