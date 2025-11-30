"""
Plugin Registry Cog
Tracks metadata about loaded extensions and their provided features
Enables dependency resolution, conflict detection, and auto-documentation
"""

from discord.ext import commands
import discord
from typing import Dict, List, Optional, Set, Any
from pathlib import Path
from datetime import datetime
import logging
import inspect
import traceback
import asyncio


logger = logging.getLogger('discord')


class PluginMetadata:
    
    
    def __init__(self, name: str):
        self.name = name
        self.version = "unknown"
        self.author = "unknown"
        self.description = "No description"
        self.commands: Set[str] = set()
        self.cogs: Set[str] = set()
        self.dependencies: Set[str] = set()
        self.conflicts_with: Set[str] = set()
        self.loaded_at = datetime.now().isoformat()
        self.load_time = 0.0
        self.file_path = None
        self.provides_hooks: List[str] = []
        self.listens_to_hooks: List[str] = []
    
    def to_dict(self) -> Dict[str, Any]:
        
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "commands": list(self.commands),
            "cogs": list(self.cogs),
            "dependencies": list(self.dependencies),
            "conflicts_with": list(self.conflicts_with),
            "loaded_at": self.loaded_at,
            "load_time": self.load_time,
            "file_path": str(self.file_path) if self.file_path else None,
            "provides_hooks": self.provides_hooks,
            "listens_to_hooks": self.listens_to_hooks
        }


class PluginRegistry(commands.Cog):
    
    
    def __init__(self, bot):
        self.bot = bot
        self.registry: Dict[str, PluginMetadata] = {}
        self.registry_file = Path("./data/plugin_registry.json")
        

        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        

        bot.register_plugin = self.register_plugin
        bot.unregister_plugin = self.unregister_plugin
        bot.get_plugin_info = self.get_plugin_info
        bot.check_dependencies = self.check_dependencies
        bot.detect_conflicts = self.detect_conflicts
        bot.get_all_plugins = self.get_all_plugins
        
        logger.info("Plugin Registry: System initialized")
    
    @commands.Cog.listener()
    async def on_ready(self):
        
        await self.scan_loaded_extensions()
        

        if hasattr(self.bot, 'register_hook'):
            self.bot.register_hook("extension_loaded", self.on_extension_loaded_hook, priority=10)
            self.bot.register_hook("extension_unloaded", self.on_extension_unloaded_hook, priority=10)
            logger.info("Plugin Registry: Registered with event hooks system")
    
    async def scan_loaded_extensions(self):
        logger.info("Plugin Registry: Lazy-scanning loaded extensions")
        
        scan_tasks = []
        for ext_name in list(self.bot.extensions.keys()):
            if ext_name.startswith("cogs."):
                continue
            
            simple_name = ext_name.replace("extensions.", "")
            scan_tasks.append(self.register_plugin(simple_name, auto_scan=True))
        
        if scan_tasks:
            await asyncio.gather(*scan_tasks, return_exceptions=True)
        
        await self.save_registry()
        logger.info(f"Plugin Registry: Registered {len(self.registry)} plugins (async)")
    
    async def register_plugin(
        self,
        name: str,
        version: str = "unknown",
        author: str = "unknown",
        description: str = "No description",
        dependencies: List[str] = None,
        conflicts_with: List[str] = None,
        auto_scan: bool = False
    ) -> PluginMetadata:
        """
        Register a plugin and its metadata
        
        Args:
            name: Plugin name (without 'extensions.' prefix)
            version: Plugin version
            author: Plugin author
            description: Plugin description
            dependencies: List of required plugins
            conflicts_with: List of incompatible plugins
            auto_scan: If True, auto-detect commands and cogs
        
        Returns:
            PluginMetadata object
        """
        
        if name in self.registry:
            logger.warning(f"Plugin '{name}' already registered, updating metadata")
        
        metadata = PluginMetadata(name)
        metadata.version = version
        metadata.author = author
        metadata.description = description
        metadata.dependencies = set(dependencies or [])
        metadata.conflicts_with = set(conflicts_with or [])
        

        if name in self.bot.extension_load_times:
            metadata.load_time = self.bot.extension_load_times[name]
        

        if auto_scan:
            full_name = f"extensions.{name}"
            if full_name in self.bot.extensions:
                await self._auto_scan_extension(metadata, full_name)
        
        self.registry[name] = metadata
        logger.info(f"Plugin registered: {name}")
        
        return metadata
    
    async def _auto_scan_extension(self, metadata: PluginMetadata, full_ext_name: str):
        
        try:

            ext_module = self.bot.extensions.get(full_ext_name)
            
            if not ext_module:
                return
            

            for cog_name, cog in self.bot.cogs.items():
                if cog.__module__.startswith(full_ext_name):
                    metadata.cogs.add(cog_name)
                    

                    for cmd in cog.get_commands():
                        metadata.commands.add(cmd.name)
            

            if hasattr(ext_module, '__version__'):
                metadata.version = ext_module.__version__
            
            if hasattr(ext_module, '__author__'):
                metadata.author = ext_module.__author__
            
            if hasattr(ext_module, '__description__'):
                metadata.description = ext_module.__description__
            
            if hasattr(ext_module, '__dependencies__'):
                metadata.dependencies = set(ext_module.__dependencies__)
            
            if hasattr(ext_module, '__conflicts__'):
                metadata.conflicts_with = set(ext_module.__conflicts__)
            

            if hasattr(ext_module, '__file__'):
                metadata.file_path = Path(ext_module.__file__)
            
        except Exception as e:
            logger.error(f"Error auto-scanning extension {full_ext_name}: {e}")
    
    def unregister_plugin(self, name: str) -> bool:
        """
        Unregister a plugin from the registry
        
        Args:
            name: Plugin name to unregister
        
        Returns:
            bool: True if unregistered successfully
        """
        if name in self.registry:
            del self.registry[name]
            logger.info(f"Plugin unregistered: {name}")
            return True
        return False
    
    def get_plugin_info(self, name: str) -> Optional[PluginMetadata]:
        """
        Get metadata for a specific plugin
        
        Args:
            name: Plugin name
        
        Returns:
            PluginMetadata or None if not found
        """
        return self.registry.get(name)
    
    def check_dependencies(self, name: str) -> tuple[bool, List[str]]:
        """
        Check if all dependencies for a plugin are loaded
        
        Args:
            name: Plugin name to check
        
        Returns:
            (all_satisfied: bool, missing_dependencies: List[str])
        """
        metadata = self.get_plugin_info(name)
        if not metadata:
            return False, ["Plugin not registered"]
        
        missing = []
        for dep in metadata.dependencies:
            if dep not in self.registry:
                missing.append(dep)
        
        return len(missing) == 0, missing
    
    def detect_conflicts(self, name: str) -> tuple[bool, List[str]]:
        """
        Check if a plugin conflicts with any loaded plugins
        
        Args:
            name: Plugin name to check
        
        Returns:
            (has_conflicts: bool, conflicting_plugins: List[str])
        """
        metadata = self.get_plugin_info(name)
        if not metadata:
            return False, []
        
        conflicts = []
        

        for conflict in metadata.conflicts_with:
            if conflict in self.registry:
                conflicts.append(conflict)
        

        for other_name, other_meta in self.registry.items():
            if other_name != name and name in other_meta.conflicts_with:
                conflicts.append(other_name)
        
        return len(conflicts) > 0, conflicts
    
    def get_all_plugins(self) -> Dict[str, PluginMetadata]:
        
        return self.registry.copy()
    
    async def save_registry(self):
        try:
            registry_data = {
                "last_updated": datetime.now().isoformat(),
                "total_plugins": len(self.registry),
                "plugins": {
                    name: metadata.to_dict()
                    for name, metadata in self.registry.items()
                }
            }
            
            asyncio.create_task(
                self.bot.config.file_handler.atomic_write_json(
                    str(self.registry_file),
                    registry_data
                )
            )
            logger.debug(f"Plugin registry save queued: {self.registry_file}")
        except Exception as e:
            logger.error(f"Failed to queue registry save: {e}")
    

    
    async def on_extension_loaded_hook(self, bot, extension_name: str, **kwargs):
        
        simple_name = extension_name.replace("extensions.", "")
        

        if extension_name.startswith("cogs."):
            return
        
        await self.register_plugin(simple_name, auto_scan=True)
        await self.save_registry()
    
    async def on_extension_unloaded_hook(self, bot, extension_name: str, **kwargs):
        
        simple_name = extension_name.replace("extensions.", "")
        self.unregister_plugin(simple_name)
        await self.save_registry()
    

    
    @commands.hybrid_command(name="plugins", help="List all registered plugins")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def plugins_command(self, ctx):
        
        
        embed = discord.Embed(
            title="🔌 Registered Plugins",
            description=f"**Total plugins: {len(self.registry)}**",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        if not self.registry:
            embed.description = "```No plugins registered```"
            await ctx.send(embed=embed)
            return
        
        for name, metadata in sorted(self.registry.items()):
            commands_text = f"Commands: {len(metadata.commands)}" if metadata.commands else "No commands"
            cogs_text = f"Cogs: {len(metadata.cogs)}" if metadata.cogs else "No cogs"
            
            value = f"```Version: {metadata.version}\n{commands_text}\n{cogs_text}\nLoad time: {metadata.load_time:.3f}s```"
            
            embed.add_field(
                name=f"📦 {name}",
                value=value,
                inline=True
            )
        
        embed.set_footer(text=f"Registry file: {self.registry_file}")
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    @commands.hybrid_command(name="plugininfo", help="Get detailed information about a plugin")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def plugin_info_command(self, ctx, plugin_name: str):
        
        
        metadata = self.get_plugin_info(plugin_name)
        
        if not metadata:
            embed = discord.Embed(
                title="❌ Plugin Not Found",
                description=f"```Plugin '{plugin_name}' is not registered```",
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"📦 {metadata.name}",
            description=metadata.description,
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        

        embed.add_field(
            name="ℹ️ Information",
            value=f"```Version: {metadata.version}\nAuthor: {metadata.author}\nLoad time: {metadata.load_time:.3f}s```",
            inline=False
        )
        

        if metadata.commands:
            commands_list = ", ".join(sorted(metadata.commands))
            embed.add_field(
                name=f"📝 Commands ({len(metadata.commands)})",
                value=f"```{commands_list}```",
                inline=False
            )
        

        if metadata.cogs:
            cogs_list = ", ".join(sorted(metadata.cogs))
            embed.add_field(
                name=f"⚙️ Cogs ({len(metadata.cogs)})",
                value=f"```{cogs_list}```",
                inline=False
            )
        

        if metadata.dependencies:
            deps_satisfied, missing = self.check_dependencies(plugin_name)
            deps_status = "✅ All satisfied" if deps_satisfied else f"❌ Missing: {', '.join(missing)}"
            deps_list = ", ".join(sorted(metadata.dependencies))
            embed.add_field(
                name="📌 Dependencies",
                value=f"```{deps_list}\n{deps_status}```",
                inline=False
            )
        

        if metadata.conflicts_with:
            has_conflicts, conflicts = self.detect_conflicts(plugin_name)
            conflict_status = "⚠️ Conflicts detected!" if has_conflicts else "✅ No conflicts"
            conflicts_list = ", ".join(sorted(metadata.conflicts_with))
            embed.add_field(
                name="⚠️ Conflicts With",
                value=f"```{conflicts_list}\n{conflict_status}```",
                inline=False
            )
        
        embed.set_footer(text=f"Loaded at: {metadata.loaded_at}")
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    def cog_unload(self):
        

        if hasattr(self.bot, 'register_plugin'):
            delattr(self.bot, 'register_plugin')
        if hasattr(self.bot, 'unregister_plugin'):
            delattr(self.bot, 'unregister_plugin')
        if hasattr(self.bot, 'get_plugin_info'):
            delattr(self.bot, 'get_plugin_info')
        if hasattr(self.bot, 'check_dependencies'):
            delattr(self.bot, 'check_dependencies')
        if hasattr(self.bot, 'detect_conflicts'):
            delattr(self.bot, 'detect_conflicts')
        if hasattr(self.bot, 'get_all_plugins'):
            delattr(self.bot, 'get_all_plugins')
        
        logger.info("Plugin Registry: Cog unloaded, methods removed from bot")


async def setup(bot):
    
    await bot.add_cog(PluginRegistry(bot))
    logger.info("Plugin Registry cog loaded successfully")