"""
Plugin Registry Cog
Tracks metadata about loaded extensions and their provided features
Enables dependency resolution, conflict detection, and auto-documentation
"""

from discord.ext import commands
import discord
from typing import Dict, List, Optional, Set, Any, Tuple
from pathlib import Path
from datetime import datetime
import logging
import asyncio
import re

logger = logging.getLogger('discord')


class PluginMetadata:
    
    def __init__(self, name: str):
        self.name = name
        self.version = "unknown"
        self.author = "unknown"
        self.description = "No description"
        self.commands: Set[str] = set()
        self.cogs: Set[str] = set()
        self.dependencies: Dict[str, str] = {}
        self.conflicts_with: Set[str] = set()
        self.loaded_at = datetime.now().isoformat()
        self.load_time = 0.0
        self.file_path = None
        self.provides_hooks: List[str] = []
        self.listens_to_hooks: List[str] = []
        self.scan_errors: List[str] = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "commands": list(self.commands),
            "cogs": list(self.cogs),
            "dependencies": self.dependencies,
            "conflicts_with": list(self.conflicts_with),
            "loaded_at": self.loaded_at,
            "load_time": self.load_time,
            "file_path": str(self.file_path) if self.file_path else None,
            "provides_hooks": self.provides_hooks,
            "listens_to_hooks": self.listens_to_hooks,
            "scan_errors": self.scan_errors
        }


class PluginRegistry(commands.Cog):
    
    def __init__(self, bot):
        self.bot = bot
        self.registry: Dict[str, PluginMetadata] = {}
        self.registry_file = Path("./data/plugin_registry.json")
        self.enforce_dependencies = True
        self.enforce_conflicts = True
        self.alert_channel_id = None
        
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        
        bot.register_plugin = self.register_plugin
        bot.unregister_plugin = self.unregister_plugin
        bot.get_plugin_info = self.get_plugin_info
        bot.check_dependencies = self.check_dependencies
        bot.detect_conflicts = self.detect_conflicts
        bot.get_all_plugins = self.get_all_plugins
        bot.validate_plugin_load = self.validate_plugin_load
        
        logger.info("Plugin Registry: System initialized")
    
    @commands.Cog.listener()
    async def on_ready(self):
        await self.scan_loaded_extensions()
        
        if hasattr(self.bot, 'register_hook'):
            self.bot.register_hook("extension_loaded", self.on_extension_loaded_hook, priority=10)
            self.bot.register_hook("extension_unloaded", self.on_extension_unloaded_hook, priority=10)
            logger.info("Plugin Registry: Registered with event hooks system")
    
    async def scan_loaded_extensions(self):
        logger.info("Plugin Registry: Scanning loaded extensions")
        
        scan_tasks = []
        for ext_name in list(self.bot.extensions.keys()):
            if ext_name.startswith("cogs."):
                continue
            
            simple_name = ext_name.replace("extensions.", "")
            scan_tasks.append(self.register_plugin(simple_name, auto_scan=True))
        
        if scan_tasks:
            results = await asyncio.gather(*scan_tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Plugin Registry: Scan error: {result}")
        
        await self.save_registry()
        logger.info(f"Plugin Registry: Registered {len(self.registry)} plugins")
    
    def _parse_version(self, version: str) -> Tuple[int, ...]:
        try:
            return tuple(int(x) for x in re.findall(r'\d+', str(version)))
        except:
            return (0,)
    
    def _compare_versions(self, version1: str, version2: str, operator: str = ">=") -> bool:
        v1 = self._parse_version(version1)
        v2 = self._parse_version(version2)
        
        if operator == ">=":
            return v1 >= v2
        elif operator == ">":
            return v1 > v2
        elif operator == "==":
            return v1 == v2
        elif operator == "<=":
            return v1 <= v2
        elif operator == "<":
            return v1 < v2
        else:
            return True
    
    def _detect_circular_dependencies(self, name: str, visited: Set[str] = None, path: List[str] = None) -> Tuple[bool, Optional[List[str]]]:
        if visited is None:
            visited = set()
        if path is None:
            path = []
        
        if name in visited:
            cycle_start = path.index(name) if name in path else 0
            return True, path[cycle_start:] + [name]
        
        metadata = self.get_plugin_info(name)
        if not metadata:
            return False, None
        
        visited.add(name)
        path.append(name)
        
        for dep_name in metadata.dependencies.keys():
            has_cycle, cycle_path = self._detect_circular_dependencies(dep_name, visited.copy(), path.copy())
            if has_cycle:
                return True, cycle_path
        
        return False, None
    
    async def validate_plugin_load(self, name: str) -> Tuple[bool, List[str]]:
        errors = []
        
        metadata = self.get_plugin_info(name)
        if not metadata:
            return True, []
        
        if self.enforce_dependencies:
            deps_satisfied, missing = self.check_dependencies(name)
            if not deps_satisfied:
                errors.append(f"Missing dependencies: {', '.join(missing)}")
        
        if self.enforce_conflicts:
            has_conflicts, conflicts = self.detect_conflicts(name)
            if has_conflicts:
                errors.append(f"Conflicts with loaded plugins: {', '.join(conflicts)}")
        
        has_cycle, cycle_path = self._detect_circular_dependencies(name)
        if has_cycle:
            cycle_str = " -> ".join(cycle_path)
            errors.append(f"Circular dependency detected: {cycle_str}")
        
        return len(errors) == 0, errors
    
    async def register_plugin(
        self,
        name: str,
        version: str = "unknown",
        author: str = "unknown",
        description: str = "No description",
        dependencies: Dict[str, str] = None,
        conflicts_with: List[str] = None,
        auto_scan: bool = False
    ) -> PluginMetadata:
        if name in self.registry:
            logger.warning(f"Plugin '{name}' already registered, updating metadata")
        
        metadata = PluginMetadata(name)
        metadata.version = version
        metadata.author = author
        metadata.description = description
        metadata.dependencies = dependencies or {}
        metadata.conflicts_with = set(conflicts_with or [])
        
        if name in self.bot.extension_load_times:
            metadata.load_time = self.bot.extension_load_times[name]
        
        if auto_scan:
            full_name = f"extensions.{name}"
            if full_name in self.bot.extensions:
                await self._auto_scan_extension(metadata, full_name)
        
        self.registry[name] = metadata
        
        is_valid, validation_errors = await self.validate_plugin_load(name)
        if validation_errors:
            logger.warning(f"Plugin '{name}' registered with validation warnings: {'; '.join(validation_errors)}")
            await self._send_alert(f"⚠️ Plugin Registry: '{name}' has issues:\n" + "\n".join(f"- {e}" for e in validation_errors))
        else:
            logger.info(f"Plugin registered: {name}")
        
        return metadata
    
    async def _auto_scan_extension(self, metadata: PluginMetadata, full_ext_name: str):
        try:
            ext_module = self.bot.extensions.get(full_ext_name)
            
            if not ext_module:
                error = f"Extension module not found: {full_ext_name}"
                metadata.scan_errors.append(error)
                logger.warning(f"Plugin Registry: {error}")
                return
            
            for cog_name, cog in self.bot.cogs.items():
                if cog.__module__.startswith(full_ext_name):
                    metadata.cogs.add(cog_name)
                    
                    for cmd in cog.get_commands():
                        metadata.commands.add(cmd.name)
            
            if hasattr(ext_module, '__version__'):
                metadata.version = str(ext_module.__version__)
            
            if hasattr(ext_module, '__author__'):
                metadata.author = str(ext_module.__author__)
            
            if hasattr(ext_module, '__description__'):
                metadata.description = str(ext_module.__description__)
            
            if hasattr(ext_module, '__dependencies__'):
                deps = ext_module.__dependencies__
                if isinstance(deps, dict):
                    metadata.dependencies = deps
                elif isinstance(deps, list):
                    metadata.dependencies = {dep: ">=0.0.0" for dep in deps}
            
            if hasattr(ext_module, '__conflicts__'):
                conflicts = ext_module.__conflicts__
                if isinstance(conflicts, (list, set)):
                    metadata.conflicts_with = set(conflicts)
            
            if hasattr(ext_module, '__file__'):
                metadata.file_path = Path(ext_module.__file__)
            
        except Exception as e:
            error = f"Auto-scan failed: {str(e)}"
            metadata.scan_errors.append(error)
            logger.error(f"Plugin Registry: Error scanning {full_ext_name}: {e}", exc_info=True)
            await self._send_alert(f"❌ Plugin Registry: Failed to scan '{metadata.name}': {e}")
    
    def unregister_plugin(self, name: str) -> bool:
        if name in self.registry:
            del self.registry[name]
            logger.info(f"Plugin unregistered: {name}")
            return True
        return False
    
    def get_plugin_info(self, name: str) -> Optional[PluginMetadata]:
        return self.registry.get(name)
    
    def check_dependencies(self, name: str) -> Tuple[bool, List[str]]:
        metadata = self.get_plugin_info(name)
        if not metadata:
            return False, ["Plugin not registered"]
        
        missing = []
        version_mismatches = []
        
        for dep_name, required_version in metadata.dependencies.items():
            dep_metadata = self.get_plugin_info(dep_name)
            
            if not dep_metadata:
                missing.append(f"{dep_name} (not loaded)")
                continue
            
            if required_version and required_version != ">=0.0.0":
                operator = ">=" if ">=" in required_version else "=="
                version_str = required_version.replace(">=", "").replace("==", "").strip()
                
                if not self._compare_versions(dep_metadata.version, version_str, operator):
                    version_mismatches.append(
                        f"{dep_name} (requires {required_version}, found {dep_metadata.version})"
                    )
        
        all_issues = missing + version_mismatches
        return len(all_issues) == 0, all_issues
    
    def detect_conflicts(self, name: str) -> Tuple[bool, List[str]]:
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
                "enforcement": {
                    "dependencies": self.enforce_dependencies,
                    "conflicts": self.enforce_conflicts
                },
                "plugins": {
                    name: metadata.to_dict()
                    for name, metadata in self.registry.items()
                }
            }
            
            await self.bot.config.file_handler.atomic_write_json(
                str(self.registry_file),
                registry_data
            )
            logger.debug(f"Plugin registry saved: {self.registry_file}")
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")
    
    async def _send_alert(self, message: str):
        if not self.alert_channel_id:
            logger.warning(f"Plugin Registry Alert (no channel): {message}")
            return
        
        try:
            channel = self.bot.get_channel(self.alert_channel_id)
            if channel:
                embed = discord.Embed(
                    title="🔌 Plugin Registry Alert",
                    description=message,
                    color=0xffa500,
                    timestamp=discord.utils.utcnow()
                )
                await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send plugin alert: {e}")
    
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
    
    @commands.hybrid_command(name="pr_list", help="List all registered plugins with metadata")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def pr_list_command(self, ctx):
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
            status_icons = []
            
            if metadata.scan_errors:
                status_icons.append("⚠️")
            
            deps_ok, _ = self.check_dependencies(name)
            if not deps_ok:
                status_icons.append("❌")
            
            has_conflicts, _ = self.detect_conflicts(name)
            if has_conflicts:
                status_icons.append("⚠️")
            
            has_cycle, _ = self._detect_circular_dependencies(name)
            if has_cycle:
                status_icons.append("🔄")
            
            status = " ".join(status_icons) if status_icons else "✅"
            
            commands_text = f"Commands: {len(metadata.commands)}" if metadata.commands else "No commands"
            cogs_text = f"Cogs: {len(metadata.cogs)}" if metadata.cogs else "No cogs"
            
            value = f"```{status}\nVersion: {metadata.version}\n{commands_text}\n{cogs_text}\nLoad: {metadata.load_time:.3f}s```"
            
            embed.add_field(
                name=f"📦 {name}",
                value=value,
                inline=True
            )
        
        embed.set_footer(text=f"Registry: {self.registry_file}")
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    @commands.hybrid_command(name="pr_info", help="Get detailed information about a specific plugin")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def pr_info_command(self, ctx, plugin_name: str):
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
            deps_satisfied, issues = self.check_dependencies(plugin_name)
            deps_status = "✅ All satisfied" if deps_satisfied else f"❌ Issues: {', '.join(issues)}"
            deps_list = "\n".join(f"{name}: {ver}" for name, ver in metadata.dependencies.items())
            embed.add_field(
                name="🔌 Dependencies",
                value=f"```{deps_list}\n\n{deps_status}```",
                inline=False
            )
        
        if metadata.conflicts_with:
            has_conflicts, conflicts = self.detect_conflicts(plugin_name)
            conflict_status = "⚠️ Active conflicts!" if has_conflicts else "✅ No active conflicts"
            conflicts_list = ", ".join(sorted(metadata.conflicts_with))
            embed.add_field(
                name="⚠️ Conflicts With",
                value=f"```{conflicts_list}\n{conflict_status}```",
                inline=False
            )
        
        has_cycle, cycle_path = self._detect_circular_dependencies(plugin_name)
        if has_cycle:
            cycle_str = " → ".join(cycle_path)
            embed.add_field(
                name="🔄 Circular Dependency",
                value=f"```{cycle_str}```",
                inline=False
            )
        
        if metadata.scan_errors:
            errors_text = "\n".join(metadata.scan_errors)
            embed.add_field(
                name="⚠️ Scan Errors",
                value=f"```{errors_text}```",
                inline=False
            )
        
        embed.set_footer(text=f"Loaded at: {metadata.loaded_at}")
        
        await ctx.send(embed=embed)
        
        try:
            await ctx.message.delete()
        except:
            pass
    
    @commands.hybrid_command(name="pr_validate", help="Validate a plugin's dependencies and conflicts (Bot Owner Only)")
    @commands.is_owner()
    async def pr_validate_command(self, ctx, plugin_name: str):
        metadata = self.get_plugin_info(plugin_name)
        
        if not metadata:
            await ctx.send(f"❌ Plugin '{plugin_name}' not found", ephemeral=True)
            return
        
        is_valid, errors = await self.validate_plugin_load(plugin_name)
        
        embed = discord.Embed(
            title=f"🔍 Validation: {plugin_name}",
            color=0x00ff00 if is_valid else 0xff0000,
            timestamp=discord.utils.utcnow()
        )
        
        if is_valid:
            embed.description = "```✅ Plugin is valid and safe to load```"
        else:
            embed.description = "```❌ Plugin has validation issues:```"
            for i, error in enumerate(errors, 1):
                embed.add_field(
                    name=f"Issue {i}",
                    value=f"```{error}```",
                    inline=False
                )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="pr_enforce", help="Toggle dependency/conflict enforcement (Bot Owner Only)")
    @commands.is_owner()
    async def pr_enforce_command(self, ctx, mode: str):
        if mode.lower() == "deps":
            self.enforce_dependencies = not self.enforce_dependencies
            status = "enabled" if self.enforce_dependencies else "disabled"
            await ctx.send(f"✅ Dependency enforcement {status}", ephemeral=True)
        elif mode.lower() == "conflicts":
            self.enforce_conflicts = not self.enforce_conflicts
            status = "enabled" if self.enforce_conflicts else "disabled"
            await ctx.send(f"✅ Conflict enforcement {status}", ephemeral=True)
        else:
            await ctx.send("❌ Mode must be 'deps' or 'conflicts'", ephemeral=True)
    
    @commands.hybrid_command(name="pr_alert_channel", help="Set alert channel for plugin registry (Bot Owner Only)")
    @commands.is_owner()
    async def pr_alert_channel_command(self, ctx, channel: discord.TextChannel = None):
        if channel is None:
            channel = ctx.channel
        
        self.alert_channel_id = channel.id
        await ctx.send(f"✅ Plugin Registry alert channel set to {channel.mention}", ephemeral=True)
    
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
        if hasattr(self.bot, 'validate_plugin_load'):
            delattr(self.bot, 'validate_plugin_load')
        
        logger.info("Plugin Registry: Cog unloaded")


async def setup(bot):
    await bot.add_cog(PluginRegistry(bot))
    logger.info("Plugin Registry cog loaded successfully")