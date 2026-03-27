"""
Config Schema Validator
Validates config.json against a defined schema on boot and on-demand.
Reports invalid types, missing required keys, unknown keys, and out-of-range values.
Prevents silent misconfigurations that cause runtime failures.

Slash commands:
    /fw_config_validate   — Run validation and show results
    /fw_config_schema     — Show the expected config schema
"""
# MIT License — Copyright (c) 2026 TheHolyOneZ
# Part of the Zoryx Discord Bot Framework
# https://github.com/TheHolyOneZ/discord-bot-framework

from discord.ext import commands
import discord
from discord import app_commands
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger('discord.cogs.config_validator')


# ── Schema Definition ──────────────────────────────────────────────────
#
# Each key maps to a spec dict with these fields:
#   type        — expected Python type (or tuple of types)
#   required    — bool, whether the key must exist
#   default     — default value (documentation only)
#   description — human-readable description
#   children    — nested schema dict for dict-type values
#   choices     — list of valid values (enum-like)
#   min / max   — numeric bounds (inclusive)
#   max_length  — maximum string length

CONFIG_SCHEMA = {
    "prefix": {
        "type": str,
        "required": True,
        "default": "!",
        "description": "Default command prefix",
        "max_length": 5,
    },
    "allow_mention_prefix": {
        "type": bool,
        "required": False,
        "default": True,
        "description": "Allow @bot mention as prefix",
    },
    "owner_ids": {
        "type": list,
        "required": False,
        "default": [],
        "description": "Additional owner IDs (list of ints)",
    },
    "auto_reload": {
        "type": bool,
        "required": False,
        "default": False,
        "description": "Enable hot-reload of extensions on file change",
    },
    "status": {
        "type": dict,
        "required": False,
        "default": {},
        "description": "Bot status configuration",
        "children": {
            "type": {
                "type": str,
                "required": False,
                "default": "watching",
                "description": "Activity type",
                "choices": ["playing", "watching", "listening", "competing", "streaming", "custom"],
            },
            "text": {
                "type": str,
                "required": False,
                "default": "{guilds} servers",
                "description": "Status text (supports {guilds}, {users}, {commands} placeholders)",
            },
            "presence": {
                "type": str,
                "required": False,
                "default": "online",
                "description": "Presence status",
                "choices": ["online", "dnd", "idle", "invisible"],
            },
            "statuses": {
                "type": list,
                "required": False,
                "default": [],
                "description": "List of rotating statuses (each with type, text, presence)",
            },
            "interval": {
                "type": (int, float),
                "required": False,
                "default": 300,
                "description": "Status rotation interval in seconds",
                "min": 10,
            },
            "log_status_updates": {
                "type": bool,
                "required": False,
                "default": False,
                "description": "Log status rotation changes",
            },
        },
    },
    "database": {
        "type": dict,
        "required": False,
        "default": {},
        "description": "Database configuration",
        "children": {
            "base_path": {
                "type": str,
                "required": False,
                "default": "./data",
                "description": "Base path for guild databases",
            },
            "path": {
                "type": str,
                "required": False,
                "default": "./data/bot.db",
                "description": "Main database path",
            },
        },
    },
    "logging": {
        "type": dict,
        "required": False,
        "default": {},
        "description": "Logging configuration",
        "children": {
            "level": {
                "type": str,
                "required": False,
                "default": "INFO",
                "description": "Log level",
                "choices": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            },
            "max_bytes": {
                "type": int,
                "required": False,
                "default": 10485760,
                "description": "Max log file size in bytes",
                "min": 1024,
            },
            "backup_count": {
                "type": int,
                "required": False,
                "default": 5,
                "description": "Number of log backup files to keep",
                "min": 0,
                "max": 50,
            },
        },
    },
    "extensions": {
        "type": dict,
        "required": False,
        "default": {},
        "description": "Extension loading configuration",
        "children": {
            "auto_load": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Auto-load extensions from ./extensions/ on startup",
            },
            "blacklist": {
                "type": list,
                "required": False,
                "default": [],
                "description": "List of extension names to skip during auto-load",
            },
        },
    },
    "cooldowns": {
        "type": dict,
        "required": False,
        "default": {},
        "description": "Default cooldown settings",
        "children": {
            "default_rate": {
                "type": int,
                "required": False,
                "default": 3,
                "description": "Default rate limit (commands per period)",
                "min": 1,
            },
            "default_per": {
                "type": (int, float),
                "required": False,
                "default": 5.0,
                "description": "Default cooldown period in seconds",
                "min": 0.5,
            },
        },
    },
    "command_permissions": {
        "type": dict,
        "required": False,
        "default": {},
        "description": "Per-command role requirements (command_name -> [role_ids])",
    },
    "slash_limiter": {
        "type": dict,
        "required": False,
        "default": {},
        "description": "Slash command limiter configuration",
        "children": {
            "max_limit": {
                "type": int,
                "required": False,
                "default": 100,
                "description": "Discord's slash command hard limit",
                "min": 1,
                "max": 100,
            },
            "warning_threshold": {
                "type": int,
                "required": False,
                "default": 90,
                "description": "Warning when this many commands are registered",
                "min": 1,
                "max": 100,
            },
            "safe_limit": {
                "type": int,
                "required": False,
                "default": 95,
                "description": "Start converting at this count",
                "min": 1,
                "max": 100,
            },
        },
    },
    "framework": {
        "type": dict,
        "required": True,
        "default": {},
        "description": "Framework cog toggle switches",
        "children": {
            "load_cogs": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Load framework cogs on startup",
            },
            "enable_event_hooks": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Enable EventHooks cog",
            },
            "enable_plugin_registry": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Enable PluginRegistry cog",
            },
            "enable_framework_diagnostics": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Enable FrameworkDiagnostics cog",
            },
            "enable_slash_command_limiter": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Enable SlashCommandLimiter cog",
            },
            "enable_shard_monitor": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Enable ShardMonitor cog",
            },
            "enable_shard_manager": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Enable ShardManager cog",
            },
            "enable_backup_restore": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Enable BackupRestore cog",
            },
            "enable_db_migrations": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Enable DatabaseMigrations cog",
            },
            "enable_task_scheduler": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Enable TaskScheduler cog",
            },
            "enable_config_validator": {
                "type": bool,
                "required": False,
                "default": True,
                "description": "Enable ConfigValidator cog",
            },
        },
    },
}


# ── Validation Engine ──────────────────────────────────────────────────

class ValidationResult:

    def __init__(self):
        self.errors: List[str] = []      # Must-fix issues
        self.warnings: List[str] = []    # Suspicious but not fatal
        self.info: List[str] = []        # Informational notes

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def total_issues(self) -> int:
        return len(self.errors) + len(self.warnings)


def validate_config(config: dict, schema: dict = None, path: str = "") -> ValidationResult:
    if schema is None:
        schema = CONFIG_SCHEMA

    result = ValidationResult()

    for key, spec in schema.items():
        full_key = f"{path}.{key}" if path else key

        if key not in config:
            if spec.get("required", False):
                result.errors.append(f"Missing required key: `{full_key}`")
            continue

        value = config[key]
        expected_type = spec.get("type")

        # _comment keys are silently skipped
        if key.startswith("_comment"):
            continue

        if expected_type is not None:
            if isinstance(expected_type, tuple):
                if not isinstance(value, expected_type):
                    type_names = "/".join(t.__name__ for t in expected_type)
                    result.errors.append(
                        f"`{full_key}`: expected {type_names}, got {type(value).__name__}"
                    )
                    continue
            else:
                if not isinstance(value, expected_type):
                    result.errors.append(
                        f"`{full_key}`: expected {expected_type.__name__}, got {type(value).__name__}"
                    )
                    continue

        choices = spec.get("choices")
        if choices and value not in choices:
            result.warnings.append(
                f"`{full_key}`: value `{value}` not in expected choices: {choices}"
            )

        if isinstance(value, (int, float)):
            min_val = spec.get("min")
            max_val = spec.get("max")
            if min_val is not None and value < min_val:
                result.warnings.append(f"`{full_key}`: value {value} is below minimum {min_val}")
            if max_val is not None and value > max_val:
                result.warnings.append(f"`{full_key}`: value {value} exceeds maximum {max_val}")

        if isinstance(value, str):
            max_length = spec.get("max_length")
            if max_length is not None and len(value) > max_length:
                result.warnings.append(
                    f"`{full_key}`: length {len(value)} exceeds max {max_length}"
                )

        children = spec.get("children")
        if children and isinstance(value, dict):
            child_result = validate_config(value, children, full_key)
            result.errors.extend(child_result.errors)
            result.warnings.extend(child_result.warnings)
            result.info.extend(child_result.info)

    # Unknown keys warn, not error — extensions may add custom keys
    known_keys = set(schema.keys())
    for key in config:
        if key.startswith("_comment"):
            continue
        full_key = f"{path}.{key}" if path else key
        if key not in known_keys:
            result.warnings.append(f"Unknown key: `{full_key}` (not in schema)")

    return result


# ── Cog ────────────────────────────────────────────────────────────────

class ConfigValidator(commands.Cog, name="Config Validator"):

    def __init__(self, bot):
        self.bot = bot
        self._last_result: Optional[ValidationResult] = None
        self._extension_schemas: Dict[str, dict] = {}
        logger.info("ConfigValidator cog loaded")

    def _get_merged_schema(self) -> dict:
        merged = dict(CONFIG_SCHEMA)
        for ext_name, ext_schema in self._extension_schemas.items():
            for key, spec in ext_schema.items():
                if key in merged:
                    logger.warning(
                        f"ConfigValidator: Extension '{ext_name}' tried to override "
                        f"framework key '{key}' — skipped"
                    )
                    continue
                merged[key] = spec
        return merged

    def register_extension_schema(self, extension_name: str, schema: dict):
        """
        Register config schema keys for an extension.
        Call from cog_load() so custom keys are validated instead of flagged as "Unknown key".
        Call unregister_extension_schema() from cog_unload() to clean up.
        """
        self._extension_schemas[extension_name] = schema
        logger.info(
            f"ConfigValidator: Extension '{extension_name}' registered "
            f"{len(schema)} config key(s): {', '.join(schema.keys())}"
        )

    def unregister_extension_schema(self, extension_name: str):
        if extension_name in self._extension_schemas:
            del self._extension_schemas[extension_name]
            logger.info(f"ConfigValidator: Extension '{extension_name}' schema unregistered")

    async def cog_load(self):
        config = getattr(self.bot, 'config', None)
        if config is None:
            logger.warning("ConfigValidator: No config available on bot")
            return

        data = config.data if hasattr(config, 'data') else {}
        result = validate_config(data, self._get_merged_schema())
        self._last_result = result

        if result.is_valid and not result.warnings:
            logger.info("ConfigValidator: config.json is valid (no issues)")
        else:
            if result.errors:
                for err in result.errors:
                    logger.error(f"ConfigValidator: {err}")
            if result.warnings:
                for warn in result.warnings:
                    logger.warning(f"ConfigValidator: {warn}")

            logger.info(
                f"ConfigValidator: Validation complete — "
                f"{len(result.errors)} error(s), {len(result.warnings)} warning(s)"
            )

    def cog_unload(self):
        logger.info("ConfigValidator cog unloaded")

    @app_commands.command(name="fw_config_validate", description="Validate config.json against the schema (Bot Owner Only)")
    async def config_validate(self, interaction: discord.Interaction):
        if interaction.user.id != self.bot.bot_owner_id:
            await interaction.response.send_message(
                "This command is restricted to the bot owner.", ephemeral=True
            )
            return

        config = getattr(self.bot, 'config', None)
        if config is None:
            await interaction.response.send_message(
                "No config available.", ephemeral=True
            )
            return

        data = config.data if hasattr(config, 'data') else {}
        result = validate_config(data, self._get_merged_schema())
        self._last_result = result

        if result.is_valid and not result.warnings:
            color = 0x00ff00
            title = "Config Validation: All Clear"
        elif result.errors:
            color = 0xff0000
            title = "Config Validation: Errors Found"
        else:
            color = 0xffa500
            title = "Config Validation: Warnings"

        embed = discord.Embed(
            title=title,
            description=f"**{len(result.errors)}** error(s), **{len(result.warnings)}** warning(s)",
            color=color,
            timestamp=discord.utils.utcnow()
        )

        if result.errors:
            error_text = "\n".join(f"- {e}" for e in result.errors[:10])
            if len(result.errors) > 10:
                error_text += f"\n... and {len(result.errors) - 10} more"
            embed.add_field(
                name=f"Errors ({len(result.errors)})",
                value=f"```diff\n- {error_text}```"[:1024],
                inline=False
            )

        if result.warnings:
            warn_text = "\n".join(f"! {w}" for w in result.warnings[:10])
            if len(result.warnings) > 10:
                warn_text += f"\n... and {len(result.warnings) - 10} more"
            embed.add_field(
                name=f"Warnings ({len(result.warnings)})",
                value=f"```fix\n{warn_text}```"[:1024],
                inline=False
            )

        if result.is_valid and not result.warnings:
            embed.add_field(
                name="Status",
                value="```diff\n+ config.json matches the expected schema```",
                inline=False
            )

        embed.set_footer(text="Config Validator")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="fw_config_schema", description="Show the expected config.json schema (Bot Owner Only)")
    async def config_schema(self, interaction: discord.Interaction):
        if interaction.user.id != self.bot.bot_owner_id:
            await interaction.response.send_message(
                "This command is restricted to the bot owner.", ephemeral=True
            )
            return

        lines = []
        merged = self._get_merged_schema()
        self._format_schema(merged, lines, indent=0)

        schema_text = "\n".join(lines)
        if len(schema_text) > 3900:
            schema_text = schema_text[:3900] + "\n..."

        embed = discord.Embed(
            title="Config Schema Reference",
            description=f"```yaml\n{schema_text}```",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        ext_count = len(self._extension_schemas)
        ext_text = f" | {ext_count} extension schema(s) registered" if ext_count else ""
        embed.set_footer(text=f"Config Validator | Keys marked [*] are required{ext_text}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _format_schema(self, schema: dict, lines: list, indent: int = 0):
        prefix = "  " * indent
        for key, spec in schema.items():
            expected_type = spec.get("type")
            type_name = ""
            if isinstance(expected_type, tuple):
                type_name = "/".join(t.__name__ for t in expected_type)
            elif expected_type is not None:
                type_name = expected_type.__name__

            required = " [*]" if spec.get("required") else ""
            default = spec.get("default", "")
            default_str = f" = {default}" if default != "" and default != {} and default != [] else ""

            desc = spec.get("description", "")
            choices = spec.get("choices")
            choices_str = f" ({', '.join(str(c) for c in choices)})" if choices else ""

            lines.append(f"{prefix}{key}: {type_name}{required}{default_str}{choices_str}")
            if desc:
                lines.append(f"{prefix}  # {desc}")

            children = spec.get("children")
            if children:
                self._format_schema(children, lines, indent + 1)


async def setup(bot):
    await bot.add_cog(ConfigValidator(bot))
    logger.info("Config Validator cog loaded successfully")
