"""
Event Hooks Cog
Provides internal event system for framework lifecycle events
Allows extensions to react to framework events programmatically
"""

from discord.ext import commands
import discord
from typing import Callable, Dict, List, Any
import logging
import asyncio
from datetime import datetime
import traceback

logger = logging.getLogger('discord')


class EventHooks(commands.Cog):
    
    
    def __init__(self, bot):
        self.bot = bot
        self.hooks: Dict[str, List[Callable]] = {}
        self.hook_history: List[Dict[str, Any]] = []
        self.max_history = 100
        

        bot.register_hook = self.register_hook
        bot.unregister_hook = self.unregister_hook
        bot.emit_hook = self.emit_hook
        bot.list_hooks = self.list_hooks
        bot.get_hook_history = self.get_hook_history
        
        logger.info("Event Hooks: System initialized")
    
    def register_hook(self, event_name: str, callback: Callable, priority: int = 0) -> bool:
        """
        Register a callback for framework events
        
        Args:
            event_name: Name of the event to listen for
            callback: Async function to call when event fires
            priority: Higher priority callbacks execute first (default: 0)
        
        Returns:
            bool: True if registered successfully
        """
        if not asyncio.iscoroutinefunction(callback):
            logger.error(f"Hook callback must be async: {callback.__name__}")
            return False
        
        if event_name not in self.hooks:
            self.hooks[event_name] = []
        

        self.hooks[event_name].append({
            "callback": callback,
            "priority": priority,
            "registered_at": datetime.now().isoformat()
        })
        

        self.hooks[event_name].sort(key=lambda x: x["priority"], reverse=True)
        
        logger.info(f"Hook registered: {event_name} -> {callback.__name__} (priority: {priority})")
        return True
    
    def unregister_hook(self, event_name: str, callback: Callable) -> bool:
        """
        Unregister a callback from an event
        
        Args:
            event_name: Name of the event
            callback: The callback function to remove
        
        Returns:
            bool: True if unregistered successfully
        """
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
    
    async def emit_hook(self, event_name: str, **kwargs) -> int:
        """
        Emit a framework event and call all registered callbacks
        
        Args:
            event_name: Name of the event to emit
            **kwargs: Data to pass to callbacks
        
        Returns:
            int: Number of callbacks executed successfully
        """
        if event_name not in self.hooks or not self.hooks[event_name]:
            return 0
        
        success_count = 0
        errors = []
        
        logger.debug(f"Emitting hook: {event_name} with {len(self.hooks[event_name])} callbacks")
        
        for hook_data in self.hooks[event_name]:
            callback = hook_data["callback"]
            try:
                await callback(bot=self.bot, **kwargs)
                success_count += 1
            except Exception as e:
                error_msg = f"Hook error in {event_name} -> {callback.__name__}: {e}"
                logger.error(error_msg)
                logger.debug(traceback.format_exc())
                errors.append(error_msg)
        

        self._add_to_history(event_name, success_count, errors, kwargs)
        
        return success_count
    
    def list_hooks(self) -> Dict[str, List[str]]:
        """
        Get a list of all registered hooks
        
        Returns:
            Dict mapping event names to callback names
        """
        return {
            event: [h["callback"].__name__ for h in callbacks]
            for event, callbacks in self.hooks.items()
        }
    
    def get_hook_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent hook execution history
        
        Args:
            limit: Maximum number of history entries to return
        
        Returns:
            List of hook execution records
        """
        return self.hook_history[-limit:]
    
    def _add_to_history(self, event_name: str, success_count: int, errors: List[str], kwargs: Dict):
        
        self.hook_history.append({
            "event": event_name,
            "timestamp": datetime.now().isoformat(),
            "success_count": success_count,
            "errors": errors,
            "kwargs_keys": list(kwargs.keys())
        })
        

        if len(self.hook_history) > self.max_history:
            self.hook_history = self.hook_history[-self.max_history:]
    

    
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
    
    @commands.hybrid_command(name="hooks", help="Display registered framework hooks (Bot Owner Only)")
    @commands.is_owner()
    async def hooks_command(self, ctx):
        
        
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
                callback_list.append(f"• {cb_name} (priority: {priority})")
            
            embed.add_field(
                name=f"📌 {event_name}",
                value="```" + "\n".join(callback_list) + "```",
                inline=False
            )
        

        total_hooks = sum(len(callbacks) for callbacks in self.hooks.values())
        embed.set_footer(text=f"Total hooks: {total_hooks} across {len(self.hooks)} events")
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    @commands.hybrid_command(name="hookhistory", help="Display hook execution history (Bot Owner Only)")
    @commands.is_owner()
    async def hook_history_command(self, ctx, limit: int = 10):
        
        
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
                value=f"```Time: {entry['timestamp']}\nSuccess: {entry['success_count']}{error_text}```",
                inline=False
            )
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    def cog_unload(self):
        

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
        
        logger.info("Event Hooks: Cog unloaded, methods removed from bot")


async def setup(bot):
    
    await bot.add_cog(EventHooks(bot))
    logger.info("Event Hooks cog loaded successfully")