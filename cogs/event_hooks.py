"""
Event Hooks Cog
Provides internal event system for framework lifecycle events
Allows extensions to react to framework events programmatically
"""

from discord.ext import commands
import discord
from typing import Callable, Dict, List, Any, Optional
import logging
import asyncio
from datetime import datetime, timedelta
import traceback
import time

logger = logging.getLogger('discord')


class CircuitBreaker:
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures: Dict[str, List[datetime]] = {}
        self.disabled_until: Dict[str, datetime] = {}
    
    def record_failure(self, hook_id: str):
        if hook_id not in self.failures:
            self.failures[hook_id] = []
        
        self.failures[hook_id].append(datetime.now())
        
        recent_failures = [
            f for f in self.failures[hook_id]
            if (datetime.now() - f).total_seconds() < 300
        ]
        self.failures[hook_id] = recent_failures
        
        if len(recent_failures) >= self.failure_threshold:
            self.disabled_until[hook_id] = datetime.now() + timedelta(seconds=self.timeout)
            logger.warning(f"Circuit breaker opened for {hook_id} (disabled for {self.timeout}s)")
            return True
        
        return False
    
    def is_open(self, hook_id: str) -> bool:
        if hook_id not in self.disabled_until:
            return False
        
        if datetime.now() > self.disabled_until[hook_id]:
            del self.disabled_until[hook_id]
            self.failures[hook_id] = []
            logger.info(f"Circuit breaker closed for {hook_id}")
            return False
        
        return True
    
    def reset(self, hook_id: str):
        if hook_id in self.failures:
            del self.failures[hook_id]
        if hook_id in self.disabled_until:
            del self.disabled_until[hook_id]


class EventHooks(commands.Cog):
    
    def __init__(self, bot):
        self.bot = bot
        self.hooks: Dict[str, List[Dict]] = {}
        self.hook_history: List[Dict[str, Any]] = []
        self.max_history = 100
        self.max_history_per_event = 20
        self._hook_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._worker_task: Optional[asyncio.Task] = None
        self._worker_restart_count = 0
        self._max_worker_restarts = 10
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        self.hook_timeout = 10.0
        self.alert_channel_id = None
        self.disabled_hooks: set = set()
        
        self.metrics = {
            "total_emissions": 0,
            "total_executions": 0,
            "total_failures": 0,
            "queue_full_count": 0,
            "worker_restarts": 0
        }
        
        bot.register_hook = self.register_hook
        bot.unregister_hook = self.unregister_hook
        bot.emit_hook = self.emit_hook
        bot.list_hooks = self.list_hooks
        bot.get_hook_history = self.get_hook_history
        bot.disable_hook = self.disable_hook
        bot.enable_hook = self.enable_hook
        
        logger.info("Event Hooks: System initialized")
    
    async def cog_load(self):
        await self._start_worker()
        logger.info("Event Hooks: Worker task started")
    
    def cog_unload(self):
        if self._worker_task:
            self._worker_task.cancel()
        
        if hasattr(self.bot, 'register_hook'):
            delattr(self.bot, 'register_hook')
        if hasattr(self.bot, 'unregister_hook'):
            delattr(self.bot, 'unregister_hook')
        if hasattr(self.bot, 'emit_hook'):
            delattr(self.bot, 'emit_hook')
        if hasattr(self.bot, 'list_hooks'):
            delattr(self.bot, 'list_hooks')
        if hasattr(self.bot, 'get_hook_history'):
            delattr(self.bot, 'get_hook_history')
        if hasattr(self.bot, 'disable_hook'):
            delattr(self.bot, 'disable_hook')
        if hasattr(self.bot, 'enable_hook'):
            delattr(self.bot, 'enable_hook')
        
        logger.info("Event Hooks: Cog unloaded")
    
    async def _start_worker(self):
        if self._worker_task and not self._worker_task.done():
            return
        
        self._worker_task = asyncio.create_task(self._process_hook_queue())
        
        def worker_done_callback(task):
            if not task.cancelled():
                exc = task.exception()
                if exc:
                    logger.error(f"Hook worker crashed: {exc}")
                    asyncio.create_task(self._restart_worker())
        
        self._worker_task.add_done_callback(worker_done_callback)
    
    async def _restart_worker(self):
        if self._worker_restart_count >= self._max_worker_restarts:
            error_msg = f"Hook worker exceeded max restarts ({self._max_worker_restarts}), not restarting"
            logger.critical(error_msg)
            await self._send_alert(f"🚨 Event Hooks: {error_msg}")
            return
        
        self._worker_restart_count += 1
        self.metrics["worker_restarts"] += 1
        
        await asyncio.sleep(min(self._worker_restart_count * 2, 30))
        
        logger.warning(f"Restarting hook worker (attempt {self._worker_restart_count}/{self._max_worker_restarts})")
        await self._send_alert(f"⚠️ Event Hooks: Restarting worker (attempt {self._worker_restart_count})")
        
        await self._start_worker()
    
    def register_hook(self, event_name: str, callback: Callable, priority: int = 0) -> bool:
        if not asyncio.iscoroutinefunction(callback):
            logger.error(f"Hook callback must be async: {callback.__name__}")
            return False
        
        if event_name not in self.hooks:
            self.hooks[event_name] = []
        
        hook_id = f"{event_name}:{callback.__name__}"
        
        self.hooks[event_name].append({
            "callback": callback,
            "priority": priority,
            "registered_at": datetime.now().isoformat(),
            "hook_id": hook_id,
            "execution_count": 0,
            "failure_count": 0,
            "total_execution_time": 0.0
        })
        
        self.hooks[event_name].sort(key=lambda x: x["priority"], reverse=True)
        
        logger.info(f"Hook registered: {event_name} -> {callback.__name__} (priority: {priority})")
        return True
    
    def unregister_hook(self, event_name: str, callback: Callable) -> bool:
        if event_name not in self.hooks:
            return False
        
        original_count = len(self.hooks[event_name])
        self.hooks[event_name] = [
            h for h in self.hooks[event_name] 
            if h["callback"] != callback
        ]
        
        removed = original_count - len(self.hooks[event_name])
        
        if removed > 0:
            logger.info(f"Hook unregistered: {event_name} -> {callback.__name__}")
            return True
        
        return False
    
    def disable_hook(self, hook_id: str) -> bool:
        self.disabled_hooks.add(hook_id)
        logger.info(f"Hook disabled: {hook_id}")
        return True
    
    def enable_hook(self, hook_id: str) -> bool:
        if hook_id in self.disabled_hooks:
            self.disabled_hooks.remove(hook_id)
            self.circuit_breaker.reset(hook_id)
            logger.info(f"Hook enabled: {hook_id}")
            return True
        return False
    
    async def emit_hook(self, event_name: str, **kwargs) -> int:
        if event_name not in self.hooks or not self.hooks[event_name]:
            return 0
        
        self.metrics["total_emissions"] += 1
        
        hook_data = {
            "event_name": event_name,
            "kwargs": kwargs,
            "timestamp": datetime.now().isoformat(),
            "emit_time": time.monotonic()
        }
        
        try:
            await asyncio.wait_for(
                self._hook_queue.put(hook_data),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning(f"Hook queue full (backpressure applied), event delayed: {event_name}")
            try:
                await self._hook_queue.put(hook_data)
            except asyncio.QueueFull:
                self.metrics["queue_full_count"] += 1
                logger.error(f"Hook queue full after backpressure, dropping event: {event_name}")
                await self._send_alert(f"⚠️ Event Hooks: Queue full, dropped event '{event_name}'")
                return 0
        except asyncio.QueueFull:
            self.metrics["queue_full_count"] += 1
            logger.error(f"Hook queue full, dropping event: {event_name}")
            await self._send_alert(f"⚠️ Event Hooks: Queue full, dropped event '{event_name}'")
            return 0
        
        return len(self.hooks[event_name])
    
    async def _process_hook_queue(self):
        while True:
            try:
                hook_data = await self._hook_queue.get()
                event_name = hook_data["event_name"]
                kwargs = hook_data["kwargs"]
                emit_time = hook_data.get("emit_time", time.monotonic())
                
                queue_delay = (time.monotonic() - emit_time) * 1000
                
                if event_name not in self.hooks:
                    continue
                
                success_count = 0
                errors = []
                execution_times = []
                
                for hook_info in self.hooks[event_name]:
                    callback = hook_info["callback"]
                    hook_id = hook_info["hook_id"]
                    
                    if hook_id in self.disabled_hooks:
                        continue
                    
                    if self.circuit_breaker.is_open(hook_id):
                        continue
                    
                    start_time = time.monotonic()
                    
                    try:
                        await asyncio.wait_for(
                            callback(bot=self.bot, **kwargs),
                            timeout=self.hook_timeout
                        )
                        
                        execution_time = (time.monotonic() - start_time) * 1000
                        execution_times.append(execution_time)
                        
                        hook_info["execution_count"] += 1
                        hook_info["total_execution_time"] += execution_time
                        success_count += 1
                        self.metrics["total_executions"] += 1
                        
                    except asyncio.TimeoutError:
                        error_msg = f"Hook timeout ({self.hook_timeout}s) in {event_name} -> {callback.__name__}"
                        logger.error(error_msg)
                        errors.append(error_msg)
                        hook_info["failure_count"] += 1
                        self.metrics["total_failures"] += 1
                        
                        if self.circuit_breaker.record_failure(hook_id):
                            await self._send_alert(f"⚠️ Event Hooks: Circuit breaker opened for {hook_id}")
                        
                    except Exception as e:
                        error_msg = f"Hook error in {event_name} -> {callback.__name__}: {e}"
                        logger.error(error_msg)
                        logger.debug(traceback.format_exc())
                        errors.append(error_msg)
                        hook_info["failure_count"] += 1
                        self.metrics["total_failures"] += 1
                        
                        if self.circuit_breaker.record_failure(hook_id):
                            await self._send_alert(f"⚠️ Event Hooks: Circuit breaker opened for {hook_id}")
                
                self._add_to_history(event_name, success_count, errors, kwargs, execution_times, queue_delay)
                
            except asyncio.CancelledError:
                logger.info("Hook worker cancelled")
                break
            except Exception as e:
                logger.error(f"Hook worker error: {e}")
                logger.debug(traceback.format_exc())
                await asyncio.sleep(1)
    
    async def _send_alert(self, message: str):
        if not self.alert_channel_id:
            logger.warning(f"Event Hooks Alert (no channel): {message}")
            return
        
        try:
            channel = self.bot.get_channel(self.alert_channel_id)
            if channel:
                embed = discord.Embed(
                    title="🪝 Event Hooks Alert",
                    description=message,
                    color=0xffa500,
                    timestamp=discord.utils.utcnow()
                )
                await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send hook alert: {e}")
    
    def list_hooks(self) -> Dict[str, List[str]]:
        return {
            event: [h["callback"].__name__ for h in callbacks]
            for event, callbacks in self.hooks.items()
        }
    
    def get_hook_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.hook_history[-limit:]
    
    def _add_to_history(self, event_name: str, success_count: int, errors: List[str], 
                        kwargs: Dict, execution_times: List[float], queue_delay: float):
        avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0
        
        self.hook_history.append({
            "event": event_name,
            "timestamp": datetime.now().isoformat(),
            "success_count": success_count,
            "errors": errors,
            "kwargs_keys": list(kwargs.keys()),
            "avg_execution_time_ms": round(avg_execution_time, 2),
            "queue_delay_ms": round(queue_delay, 2)
        })
        
        if len(self.hook_history) > self.max_history:
            self.hook_history = self.hook_history[-self.max_history:]
        
        event_history = [h for h in self.hook_history if h["event"] == event_name]
        if len(event_history) > self.max_history_per_event:
            events_to_remove = event_history[:-self.max_history_per_event]
            self.hook_history = [h for h in self.hook_history if h not in events_to_remove]
    
    @commands.Cog.listener()
    async def on_ready(self):
        await self.emit_hook("bot_ready", bot_user=self.bot.user)
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.emit_hook("guild_joined", guild=guild)
    
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await self.emit_hook("guild_left", guild=guild)
    
    @commands.Cog.listener()
    async def on_command(self, ctx):
        await self.emit_hook(
            "command_executed",
            command_name=ctx.command.name,
            author=ctx.author,
            guild=ctx.guild
        )
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        await self.emit_hook(
            "command_error",
            command_name=ctx.command.name if ctx.command else "unknown",
            error=error,
            author=ctx.author,
            guild=ctx.guild
        )
    
    @commands.hybrid_command(name="eh_list", help="Display registered framework hooks (Bot Owner Only)")
    @commands.is_owner()
    async def eh_list_command(self, ctx):
        embed = discord.Embed(
            title="🪝 Framework Event Hooks",
            description="**Currently registered internal event hooks**",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        if not self.hooks:
            embed.description = "```No hooks registered```"
            await ctx.send(embed=embed)
            return
        
        for event_name, callbacks in sorted(self.hooks.items()):
            callback_list = []
            for hook_data in callbacks:
                cb_name = hook_data["callback"].__name__
                priority = hook_data["priority"]
                hook_id = hook_data["hook_id"]
                
                status = ""
                if hook_id in self.disabled_hooks:
                    status = "🔴 "
                elif self.circuit_breaker.is_open(hook_id):
                    status = "⚠️ "
                
                avg_time = (hook_data["total_execution_time"] / hook_data["execution_count"]) if hook_data["execution_count"] > 0 else 0
                
                callback_list.append(
                    f"{status}• {cb_name} (p:{priority} | "
                    f"exec:{hook_data['execution_count']} | "
                    f"fail:{hook_data['failure_count']} | "
                    f"avg:{avg_time:.1f}ms)"
                )
            
            embed.add_field(
                name=f"📌 {event_name}",
                value="```" + "\n".join(callback_list) + "```",
                inline=False
            )
        
        total_hooks = sum(len(callbacks) for callbacks in self.hooks.values())
        queue_size = self._hook_queue.qsize()
        
        embed.add_field(
            name="📊 Metrics",
            value=f"```Total Hooks: {total_hooks}\nQueue: {queue_size}/1000\nEmissions: {self.metrics['total_emissions']}\nExecutions: {self.metrics['total_executions']}\nFailures: {self.metrics['total_failures']}\nQueue Drops: {self.metrics['queue_full_count']}\nWorker Restarts: {self.metrics['worker_restarts']}```",
            inline=False
        )
        
        embed.set_footer(text="🔴 Disabled | ⚠️ Circuit Breaker Open")
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    @commands.hybrid_command(name="eh_history", help="Display hook execution history (Bot Owner Only)")
    @commands.is_owner()
    async def eh_history_command(self, ctx, limit: int = 10):
        if limit > 50:
            limit = 50
        
        embed = discord.Embed(
            title="📜 Hook Execution History",
            description=f"**Last {limit} hook executions**",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        history = self.get_hook_history(limit)
        
        if not history:
            embed.description = "```No hook history available```"
            await ctx.send(embed=embed)
            return
        
        for entry in history:
            status = "✅" if not entry["errors"] else "❌"
            error_text = f"\nErrors: {len(entry['errors'])}" if entry["errors"] else ""
            
            embed.add_field(
                name=f"{status} {entry['event']}",
                value=f"```Success: {entry['success_count']}\nAvg Exec: {entry.get('avg_execution_time_ms', 0):.1f}ms\nQueue Delay: {entry.get('queue_delay_ms', 0):.1f}ms{error_text}```",
                inline=False
            )
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    @commands.hybrid_command(name="eh_disable", help="Disable a problematic hook (Bot Owner Only)")
    @commands.is_owner()
    async def eh_disable_command(self, ctx, hook_id: str):
        success = self.disable_hook(hook_id)
        
        if success:
            await ctx.send(f"✅ Hook disabled: {hook_id}", ephemeral=True)
        else:
            await ctx.send(f"❌ Hook not found: {hook_id}", ephemeral=True)
    
    @commands.hybrid_command(name="eh_enable", help="Enable a disabled hook (Bot Owner Only)")
    @commands.is_owner()
    async def eh_enable_command(self, ctx, hook_id: str):
        success = self.enable_hook(hook_id)
        
        if success:
            await ctx.send(f"✅ Hook enabled: {hook_id}", ephemeral=True)
        else:
            await ctx.send(f"❌ Hook was not disabled: {hook_id}", ephemeral=True)
    
    @commands.hybrid_command(name="eh_alert_channel", help="Set alert channel for event hooks (Bot Owner Only)")
    @commands.is_owner()
    async def eh_alert_channel_command(self, ctx, channel: discord.TextChannel = None):
        if channel is None:
            channel = ctx.channel
        
        self.alert_channel_id = channel.id
        await ctx.send(f"✅ Event Hooks alert channel set to {channel.mention}", ephemeral=True)
    
    @commands.hybrid_command(name="eh_reset_circuit", help="Reset circuit breaker for a hook (Bot Owner Only)")
    @commands.is_owner()
    async def eh_reset_circuit_command(self, ctx, hook_id: str):
        self.circuit_breaker.reset(hook_id)
        await ctx.send(f"✅ Circuit breaker reset for: {hook_id}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(EventHooks(bot))
    logger.info("Event Hooks cog loaded successfully")