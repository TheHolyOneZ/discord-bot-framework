from discord.ext import commands, tasks
import discord
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import asyncio
import re
from collections import defaultdict
import aiohttp
import aiofiles
import random
import secrets

logger = logging.getLogger("discord")

class AdvancedConditionEngine:
    @staticmethod
    def evaluate(conditions: Dict[str, Any], context: Dict[str, Any]) -> bool:
        logic = conditions.get("logic", "AND")
        rules = conditions.get("rules", [])
        
        results = []
        for rule in rules:
            rule_type = rule.get("type")
            
            if rule_type == "time_range":
                now = datetime.now().time()
                start = datetime.strptime(rule["start"], "%H:%M").time()
                end = datetime.strptime(rule["end"], "%H:%M").time()
                results.append(start <= now <= end)
            
            elif rule_type == "day_of_week":
                allowed_days = rule["days"]
                current_day = datetime.now().strftime("%A")
                results.append(current_day in allowed_days)
            
            elif rule_type == "role_hierarchy":
                user_roles = context.get("user_roles", [])
                required_role_id = int(rule["role_id"])
                comparison = rule.get("comparison", "has")
                
                if comparison == "has":
                    results.append(required_role_id in user_roles)
                elif comparison == "above":
                    results.append(any(r > required_role_id for r in user_roles))
                elif comparison == "below":
                    results.append(any(r < required_role_id for r in user_roles))
            
            elif rule_type == "message_count":
                msg_count = context.get("message_count", 0)
                operator = rule["operator"]
                value = int(rule["value"])
                
                if operator == ">":
                    results.append(msg_count > value)
                elif operator == "<":
                    results.append(msg_count < value)
                elif operator == "==":
                    results.append(msg_count == value)
            
            elif rule_type == "user_age":
                created_at = context.get("user_created_at")
                if created_at:
                    age_days = (datetime.now() - created_at).days
                    min_days = int(rule.get("min_days", 0))
                    results.append(age_days >= min_days)
                else:
                    results.append(False)
            
            elif rule_type == "custom_variable":
                var_name = rule["variable"]
                operator = rule["operator"]
                value = rule["value"]
                actual_value = context.get(var_name)
                
                if operator == "==":
                    results.append(str(actual_value) == str(value))
                elif operator == "contains":
                    results.append(str(value) in str(actual_value))
        
        if logic == "AND":
            return all(results) if results else True
        else:
            return any(results) if results else False

class EventHooksCreater(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_file = Path("./data/event_hooks_creater.json")
        self.analytics_file = Path("./data/hook_analytics.json")
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.created_hooks = self._load_created_hooks()
        self.templates = self._get_templates()
        self._cooldowns = defaultdict(dict)
        self._analytics = self._load_analytics()
        self._user_message_counts = defaultdict(int)
        self._scheduled_tasks = {}
        
        self.condition_engine = AdvancedConditionEngine()
        self._register_all_hooks()
        self.analytics_task.start()
        
        logger.info(f"EventHooksCreater: Initialized with {len(self.created_hooks)} created hooks")
    
    def _load_analytics(self) -> Dict:
        if self.analytics_file.exists():
            try:
                with open(self.analytics_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    async def _save_analytics(self):
        try:
            content = json.dumps(self._analytics, indent=2)
            async with aiofiles.open(self.analytics_file, 'w', encoding='utf-8') as f:
                await f.write(content)
        except Exception as e:
            logger.error(f"Failed to save analytics: {e}")

    @tasks.loop(minutes=5)
    async def analytics_task(self):
        await self._save_analytics()
    
    def _track_execution(self, hook_id: str, success: bool = True, context: Dict = None):
        if hook_id not in self._analytics:
            self._analytics[hook_id] = {
                "total_executions": 0,
                "successful": 0,
                "failed": 0,
                "last_execution": None,
                "execution_times": [],
                "contexts": []
            }
        
        self._analytics[hook_id]["total_executions"] += 1
        if success:
            self._analytics[hook_id]["successful"] += 1
        else:
            self._analytics[hook_id]["failed"] += 1
        
        self._analytics[hook_id]["last_execution"] = datetime.now().isoformat()
        
        if context:
            self._analytics[hook_id]["contexts"].append({
                "timestamp": datetime.now().isoformat(),
                "user_id": context.get("user_id"),
                "guild_id": context.get("guild_id"),
                "success": success
            })
            
            if len(self._analytics[hook_id]["contexts"]) > 100:
                self._analytics[hook_id]["contexts"] = self._analytics[hook_id]["contexts"][-100:]
    
    def _check_cooldown(self, hook_id: str, user_id: int, cooldown_seconds: int) -> bool:
        if hook_id not in self._cooldowns:
            self._cooldowns[hook_id] = {}
        
        last_use = self._cooldowns[hook_id].get(user_id)
        if last_use:
            elapsed = (datetime.now() - last_use).total_seconds()
            if elapsed < cooldown_seconds:
                return False
        
        self._cooldowns[hook_id][user_id] = datetime.now()
        return True
    
    def _format_message(self, template: str, **kwargs) -> str:
        result = template
        
        for key, value in kwargs.items():
            result = result.replace(f"{{{key}}}", str(value))
        
        result = result.replace("{random:1-100}", str(random.randint(1, 100)))
        result = result.replace("{timestamp}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        result = result.replace("{date}", datetime.now().strftime("%Y-%m-%d"))
        result = result.replace("{time}", datetime.now().strftime("%H:%M:%S"))
        
        if "{math:" in result:
            math_pattern = r'\{math:([\d\+\-\*/\(\)\s]+)\}'
            for match in re.finditer(math_pattern, result):
                try:
                    expression = match.group(1)
                    value = eval(expression)
                    result = result.replace(match.group(0), str(value))
                except:
                    pass
        
        return result
    
    def _create_embed(self, embed_config: Dict[str, Any], **variables) -> discord.Embed:
        title = self._format_message(embed_config.get("title", ""), **variables)
        description = self._format_message(embed_config.get("description", ""), **variables)
        color_hex = embed_config.get("color", "7C3AED")
        
        try:
            color = int(color_hex, 16) if isinstance(color_hex, str) else color_hex
        except:
            color = 0x7C3AED
        
        embed = discord.Embed(
            title=title if title else None,
            description=description if description else None,
            color=color,
            timestamp=datetime.now() if embed_config.get("timestamp", True) else None
        )
        
        if embed_config.get("thumbnail"):
            thumb = self._format_message(embed_config["thumbnail"], **variables)
            if thumb == "avatar" and "user_avatar" in variables:
                embed.set_thumbnail(url=variables["user_avatar"])
            else:
                embed.set_thumbnail(url=thumb)
        
        if embed_config.get("image"):
            embed.set_image(url=self._format_message(embed_config["image"], **variables))
        
        if embed_config.get("footer"):
            embed.set_footer(text=self._format_message(embed_config["footer"], **variables))
        
        for field in embed_config.get("fields", []):
            name = self._format_message(field["name"], **variables)
            value = self._format_message(field["value"], **variables)
            embed.add_field(name=name, value=value, inline=field.get("inline", False))
        
        return embed
    
    async def _execute_webhook(self, webhook_url: str, payload: Dict):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, timeout=10) as resp:
                    status = resp.status
                    if status in [200, 204]:
                        logger.info(f"[WEBHOOK_BRIDGE] Webhook sent successfully (status: {status})")
                        return True
                    else:
                        text = await resp.text()
                        logger.error(f"[WEBHOOK_BRIDGE] Webhook failed with status {status}: {text}")
                        return False
        except Exception as e:
            logger.error(f"[WEBHOOK_BRIDGE] Webhook execution exception: {e}")
            return False
    
    async def _execute_actions(self, actions: List[Dict], context: Dict, hook: Dict):
        for action in actions:
            try:
                action_type = action.get("type")
                
                if action_type == "send_message":
                    channel_id = int(action["channel_id"])
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        if action.get("use_embed"):
                            embed_config = action["embed"]
                            embed = self._create_embed(embed_config, **context)
                            await channel.send(embed=embed)
                        else:
                            message = self._format_message(action["message"], **context)
                            await channel.send(message)
                
                elif action_type == "add_role":
                    member = context.get("member")
                    role_id = int(action["role_id"])
                    if member:
                        role = member.guild.get_role(role_id)
                        if role:
                            await member.add_roles(role)
                
                elif action_type == "remove_role":
                    member = context.get("member")
                    role_id = int(action["role_id"])
                    if member:
                        role = member.guild.get_role(role_id)
                        if role and role in member.roles:
                            await member.remove_roles(role)
                
                elif action_type == "timeout":
                    member = context.get("member")
                    duration = int(action.get("duration", 60))
                    if member:
                        await member.timeout(timedelta(seconds=duration))
                
                elif action_type == "send_dm":
                    member = context.get("member")
                    if member:
                        message = self._format_message(action["message"], **context)
                        try:
                            await member.send(message)
                        except:
                            pass
                
                elif action_type == "webhook":
                    webhook_url = action["url"]
                    payload = action.get("payload", {})
                    formatted_payload = json.loads(self._format_message(json.dumps(payload), **context))
                    await self._execute_webhook(webhook_url, formatted_payload)
                
                elif action_type == "create_role":
                    guild = context.get("guild")
                    if guild:
                        role_name = self._format_message(action["role_name"], **context)
                        color = discord.Color(int(action.get("color", "7C3AED"), 16))
                        await guild.create_role(name=role_name, color=color)
                
                elif action_type == "delay":
                    delay_seconds = int(action.get("seconds", 1))
                    await asyncio.sleep(delay_seconds)
                
                elif action_type == "trigger_hook":
                    target_hook_id = action["hook_id"]
                    target_hook = next((h for h in self.created_hooks if h["hook_id"] == target_hook_id), None)
                    if target_hook and target_hook.get("enabled"):
                        await self._execute_actions(target_hook.get("actions", []), context, target_hook)
                
            except Exception as e:
                logger.error(f"Action execution failed ({action_type}): {e}")
                self._track_execution(hook["hook_id"], success=False, context=context)
    
    def _get_templates(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "mega_welcome",
                "name": "Mega Welcome System",
                "description": "Advanced welcome with multi-action support, conditions, A/B testing, and role assignment",
                "event": "on_member_join",
                "category": "Welcome/Goodbye",
                "advanced": True,
                "icon": "wave",
                "params": [
                    {
                        "name": "welcome_channel_id",
                        "type": "channel",
                        "required": True,
                        "description": "Channel where welcome messages are sent"
                    },
                    {
                        "name": "welcome_message",
                        "type": "textarea",
                        "required": True,
                        "default": "Welcome {user} to {guild_name}! You are member #{member_count}!",
                        "description": "Welcome message template. Variables: {user}, {username}, {guild_name}, {member_count}"
                    },
                    {
                        "name": "use_embed",
                        "type": "boolean",
                        "required": False,
                        "default": True,
                        "description": "Send as embed instead of plain text"
                    },
                    {
                        "name": "embed_title",
                        "type": "text",
                        "required": False,
                        "default": "Welcome to {guild_name}!",
                        "description": "Embed title (if use_embed is true)"
                    },
                    {
                        "name": "embed_color",
                        "type": "color",
                        "required": False,
                        "default": "7C3AED",
                        "description": "Embed color hex code"
                    },
                    {
                        "name": "auto_role_id",
                        "type": "role",
                        "required": False,
                        "description": "Automatically assign this role to new members"
                    },
                    {
                        "name": "send_dm",
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Also send a DM to the new member"
                    },
                    {
                        "name": "dm_message",
                        "type": "textarea",
                        "required": False,
                        "default": "Welcome to {guild_name}! Check out #rules to get started!",
                        "description": "DM message template (if send_dm is true)"
                    }
                ]
            },
            {
                "id": "goodbye_system",
                "name": "Goodbye System",
                "description": "Send farewell messages when members leave",
                "event": "on_member_remove",
                "category": "Welcome/Goodbye",
                "advanced": False,
                "icon": "wave",
                "params": [
                    {
                        "name": "goodbye_channel_id",
                        "type": "channel",
                        "required": True,
                        "description": "Channel where goodbye messages are sent"
                    },
                    {
                        "name": "goodbye_message",
                        "type": "textarea",
                        "required": True,
                        "default": "Goodbye {username}! Thanks for being with us.",
                        "description": "Goodbye message template. Variables: {username}, {user_id}, {guild_name}"
                    },
                    {
                        "name": "use_embed",
                        "type": "boolean",
                        "required": False,
                        "default": True,
                        "description": "Send as embed"
                    }
                ]
            },
            {
                "id": "auto_role_on_reaction",
                "name": "Reaction Roles",
                "description": "Give roles when users react to specific messages",
                "event": "on_raw_reaction_add",
                "category": "Roles",
                "advanced": False,
                "icon": "zap",
                "params": [
                    {
                        "name": "message_id",
                        "type": "text",
                        "required": True,
                        "description": "The message ID to watch for reactions"
                    },
                    {
                        "name": "channel_id",
                        "type": "channel",
                        "required": True,
                        "description": "Channel containing the message"
                    },
                    {
                        "name": "role_emoji_map",
                        "type": "json",
                        "required": True,
                        "default": '{"👍": "ROLE_ID_HERE", "❤️": "ROLE_ID_HERE"}',
                        "description": "JSON mapping of emoji to role ID. Example: {\"👍\": \"123456789\", \"❤️\": \"987654321\"}"
                    },
                    {
                        "name": "remove_role_on_unreact",
                        "type": "boolean",
                        "required": False,
                        "default": True,
                        "description": "Remove role when user removes reaction"
                    }
                ]
            },
            {
                "id": "message_filter",
                "name": "Message Filter & Auto-Mod",
                "description": "Filter messages containing banned words or patterns",
                "event": "on_message",
                "category": "Moderation",
                "advanced": True,
                "icon": "shield",
                "params": [
                    {
                        "name": "banned_words",
                        "type": "textarea",
                        "required": True,
                        "description": "List of banned words, one per line"
                    },
                    {
                        "name": "action",
                        "type": "select",
                        "options": ["delete", "timeout", "warn", "log"],
                        "required": True,
                        "default": "delete",
                        "description": "Action to take when filter triggers"
                    },
                    {
                        "name": "timeout_duration",
                        "type": "number",
                        "required": False,
                        "default": 60,
                        "description": "Timeout duration in seconds (if action is timeout)"
                    },
                    {
                        "name": "log_channel_id",
                        "type": "channel",
                        "required": False,
                        "description": "Channel to log filter triggers"
                    },
                    {
                        "name": "ignore_roles",
                        "type": "text",
                        "required": False,
                        "description": "Comma-separated role IDs to ignore (mods, etc)"
                    },
                    {
                        "name": "case_sensitive",
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Make word matching case-sensitive"
                    }
                ]
            },
            {
                "id": "leveling_system",
                "name": "XP & Leveling System",
                "description": "Award XP for messages and level up users with role rewards",
                "event": "on_message",
                "category": "Gamification",
                "advanced": True,
                "icon": "chart",
                "params": [
                    {
                        "name": "xp_per_message",
                        "type": "number",
                        "required": True,
                        "default": 10,
                        "description": "XP awarded per message"
                    },
                    {
                        "name": "xp_cooldown",
                        "type": "number",
                        "required": True,
                        "default": 60,
                        "description": "Cooldown in seconds between XP awards per user"
                    },
                    {
                        "name": "levelup_channel_id",
                        "type": "channel",
                        "required": False,
                        "description": "Channel to announce level ups (optional)"
                    },
                    {
                        "name": "levelup_message",
                        "type": "textarea",
                        "required": False,
                        "default": "Congrats {user}! You reached level {level}!",
                        "description": "Level up message template"
                    },
                    {
                        "name": "role_rewards",
                        "type": "json",
                        "required": False,
                        "default": '{"5": "ROLE_ID", "10": "ROLE_ID"}',
                        "description": "JSON mapping of level to role ID for rewards"
                    }
                ]
            },
            {
                "id": "scheduled_announcement",
                "name": "Scheduled Announcements",
                "description": "Send recurring announcements at specific intervals",
                "event": "scheduled",
                "category": "Utility",
                "advanced": True,
                "icon": "clock",
                "params": [
                    {
                        "name": "announcement_channel_id",
                        "type": "channel",
                        "required": True,
                        "description": "Channel for announcements"
                    },
                    {
                        "name": "announcement_message",
                        "type": "textarea",
                        "required": True,
                        "description": "The announcement message"
                    },
                    {
                        "name": "interval_hours",
                        "type": "number",
                        "required": True,
                        "default": 24,
                        "description": "How often to send (in hours)"
                    },
                    {
                        "name": "use_embed",
                        "type": "boolean",
                        "required": False,
                        "default": True,
                        "description": "Send as embed"
                    }
                ]
            },
            {
                "id": "ticket_system",
                "name": "Support Ticket System",
                "description": "Create support tickets via reactions",
                "event": "on_raw_reaction_add",
                "category": "Utility",
                "advanced": True,
                "icon": "ticket",
                "params": [
                    {
                        "name": "trigger_message_id",
                        "type": "text",
                        "required": True,
                        "description": "Message ID that creates tickets when reacted to"
                    },
                    {
                        "name": "trigger_emoji",
                        "type": "text",
                        "required": True,
                        "default": "🎫",
                        "description": "Emoji that triggers ticket creation"
                    },
                    {
                        "name": "ticket_category_id",
                        "type": "text",
                        "required": True,
                        "description": "Category ID where ticket channels are created"
                    },
                    {
                        "name": "support_role_id",
                        "type": "role",
                        "required": True,
                        "description": "Role that can view tickets"
                    },
                    {
                        "name": "ticket_name_template",
                        "type": "text",
                        "required": False,
                        "default": "ticket-{username}",
                        "description": "Template for ticket channel names"
                    }
                ]
            },
            {
                "id": "voice_activity_tracker",
                "name": "Voice Activity Tracker",
                "description": "Track and log voice channel activity",
                "event": "on_voice_state_update",
                "category": "Analytics",
                "advanced": True,
                "icon": "volume",
                "params": [
                    {
                        "name": "log_channel_id",
                        "type": "channel",
                        "required": True,
                        "description": "Channel to log voice activity"
                    },
                    {
                        "name": "log_joins",
                        "type": "boolean",
                        "required": False,
                        "default": True,
                        "description": "Log when users join voice channels"
                    },
                    {
                        "name": "log_leaves",
                        "type": "boolean",
                        "required": False,
                        "default": True,
                        "description": "Log when users leave voice channels"
                    },
                    {
                        "name": "log_mutes",
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Log mute/unmute events"
                    }
                ]
            },
            {
                "id": "webhook_bridge",
                "name": "External Webhook Bridge",
                "description": "Send Discord events to external webhooks (Zapier, Make, etc)",
                "event": "on_message",
                "category": "Integration",
                "advanced": True,
                "icon": "link",
                "params": [
                    {
                        "name": "webhook_url",
                        "type": "text",
                        "required": True,
                        "description": "External webhook URL"
                    },
                    {
                        "name": "trigger_channels",
                        "type": "text",
                        "required": False,
                        "description": "Comma-separated channel IDs to monitor (empty = all channels)"
                    },
                    {
                        "name": "include_bots",
                        "type": "boolean",
                        "required": False,
                        "default": False,
                        "description": "Include messages from bots"
                    },
                    {
                        "name": "payload_template",
                        "type": "json",
                        "required": False,
                        "default": '{"content": "{message}", "author": "{username}", "channel": "{channel_id}"}',
                        "description": "Custom JSON payload template"
                    }
                ]
            },
            {
                "id": "dynamic_voice_channels",
                "name": "Dynamic Voice Channels",
                "description": "Auto-create temporary voice channels when users join a specific channel",
                "event": "on_voice_state_update",
                "category": "Utility",
                "advanced": True,
                "icon": "microphone",
                "params": [
                    {
                        "name": "trigger_channel_id",
                        "type": "text",
                        "required": True,
                        "description": "Voice channel that triggers temp channel creation"
                    },
                    {
                        "name": "category_id",
                        "type": "text",
                        "required": True,
                        "description": "Category where temp channels are created"
                    },
                    {
                        "name": "channel_name_template",
                        "type": "text",
                        "required": False,
                        "default": "{username}'s Channel",
                        "description": "Template for temp channel names"
                    },
                    {
                        "name": "user_limit",
                        "type": "number",
                        "required": False,
                        "default": 0,
                        "description": "Max users in temp channels (0 = unlimited)"
                    },
                    {
                        "name": "delete_when_empty",
                        "type": "boolean",
                        "required": False,
                        "default": True,
                        "description": "Delete temp channels when empty"
                    }
                ]
            }
        ]
    
    def _load_created_hooks(self) -> List[Dict[str, Any]]:
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"EventHooksCreater: Failed to load hooks: {e}")
        return []
    
    async def _save_created_hooks(self):
        try:
            # Create a copy without handler functions (not JSON serializable)
            serializable_hooks = []
            for hook in self.created_hooks:
                hook_copy = {k: v for k, v in hook.items() if not k.startswith('_')}
                serializable_hooks.append(hook_copy)

            content = json.dumps(serializable_hooks, indent=4)
            async with aiofiles.open(self.config_file, 'w', encoding='utf-8') as f:
                await f.write(content)
        except Exception as e:
            logger.error(f"EventHooksCreater: Failed to save hooks: {e}")
    
    def _register_all_hooks(self):
        for hook in self.created_hooks:
            if hook.get("enabled", True):
                try:
                    self._register_hook(hook)
                except Exception as e:
                    logger.error(f"EventHooksCreater: Failed to register hook {hook.get('hook_id')}: {e}")
    
    def _register_hook(self, hook: Dict[str, Any]):
        template_id = hook["template_id"]
        logger.info(f"[_register_hook] Registering hook {hook.get('hook_id')} with template {template_id}")
        
        if template_id == "mega_welcome":
            async def mega_welcome_handler(member):
                if member.guild.id != hook["guild_id"]:
                    return
                
                try:
                    channel_id = int(hook["params"].get("welcome_channel_id"))
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        return
                    
                    context = {
                        "user": member.mention,
                        "username": member.name,
                        "guild_name": member.guild.name,
                        "member_count": member.guild.member_count,
                        "user_avatar": member.display_avatar.url
                    }
                    
                    message = self._format_message(hook["params"]["welcome_message"], **context)
                    
                    if hook["params"].get("use_embed", True):
                        embed_title = self._format_message(hook["params"].get("embed_title", "Welcome!"), **context)
                        embed = discord.Embed(
                            title=embed_title,
                            description=message,
                            color=int(hook["params"].get("embed_color", "7C3AED"), 16),
                            timestamp=datetime.now()
                        )
                        embed.set_thumbnail(url=member.display_avatar.url)
                        await channel.send(embed=embed)
                    else:
                        await channel.send(message)
                    
                    if hook["params"].get("auto_role_id"):
                        role_id = int(hook["params"]["auto_role_id"])
                        role = member.guild.get_role(role_id)
                        if role:
                            await member.add_roles(role)
                    
                    if hook["params"].get("send_dm", False):
                        dm_message = self._format_message(hook["params"].get("dm_message", "Welcome!"), **context)
                        try:
                            await member.send(dm_message)
                        except:
                            pass
                    
                    self._track_execution(hook["hook_id"], success=True, context={"user_id": member.id, "guild_id": member.guild.id})
                    hook["execution_count"] = hook.get("execution_count", 0) + 1
                    await self._save_created_hooks()
                    
                except Exception as e:
                    hook["error_count"] = hook.get("error_count", 0) + 1
                    logger.error(f"Mega welcome error: {e}")
                    self._track_execution(hook["hook_id"], success=False)
                    await self._save_created_hooks()
            
            self.bot.add_listener(mega_welcome_handler, "on_member_join")
            hook["_handler"] = mega_welcome_handler
        
        elif template_id == "goodbye_system":
            async def goodbye_handler(member):
                if member.guild.id != hook["guild_id"]:
                    return
                
                try:
                    channel_id = int(hook["params"].get("goodbye_channel_id"))
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        return
                    
                    context = {
                        "username": member.name,
                        "user_id": member.id,
                        "guild_name": member.guild.name
                    }
                    
                    message = self._format_message(hook["params"]["goodbye_message"], **context)
                    
                    if hook["params"].get("use_embed", True):
                        embed = discord.Embed(
                            description=message,
                            color=0xFF4444,
                            timestamp=datetime.now()
                        )
                        await channel.send(embed=embed)
                    else:
                        await channel.send(message)
                    
                    self._track_execution(hook["hook_id"], success=True, context={"user_id": member.id, "guild_id": member.guild.id})
                    hook["execution_count"] = hook.get("execution_count", 0) + 1
                    await self._save_created_hooks()
                    
                except Exception as e:
                    hook["error_count"] = hook.get("error_count", 0) + 1
                    logger.error(f"Goodbye system error: {e}")
                    self._track_execution(hook["hook_id"], success=False)
                    await self._save_created_hooks()
            
            self.bot.add_listener(goodbye_handler, "on_member_remove")
            hook["_handler"] = goodbye_handler
        
        elif template_id == "webhook_bridge":
            async def webhook_bridge_handler(message):
                if message.guild and message.guild.id != hook["guild_id"]:
                    return
                
                if not hook["params"].get("include_bots", False) and message.author.bot:
                    return
                
                trigger_channels = hook["params"].get("trigger_channels", "")
                if trigger_channels:
                    channel_ids = [ch.strip() for ch in trigger_channels.split(",")]
                    if str(message.channel.id) not in channel_ids:
                        return
                
                try:
                    webhook_url = hook["params"]["webhook_url"]
                    payload_template = hook["params"].get("payload_template", {})
                    
                    if isinstance(payload_template, str):
                        payload_template = json.loads(payload_template)
                    
                    context = {
                        "message": message.content,
                        "username": message.author.name,
                        "user_id": str(message.author.id),
                        "channel_id": str(message.channel.id),
                        "channel_name": message.channel.name if hasattr(message.channel, 'name') else "DM",
                        "guild_id": str(message.guild.id) if message.guild else "DM",
                        "guild_name": message.guild.name if message.guild else "DM",
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    payload = {}
                    for key, value in payload_template.items():
                        if isinstance(value, str):
                            payload[key] = self._format_message(value, **context)
                        else:
                            payload[key] = value
                    
                    logger.info(f"[WEBHOOK_BRIDGE] Sending from {message.author.name}: '{message.content[:50]}...'")
                    success = await self._execute_webhook(webhook_url, payload)
                    
                    hook["execution_count"] = hook.get("execution_count", 0) + 1
                    if not success:
                        hook["error_count"] = hook.get("error_count", 0) + 1
                    self._track_execution(hook["hook_id"], success=success, context={"user_id": message.author.id, "guild_id": message.guild.id if message.guild else 0})
                    await self._save_created_hooks()
                    
                except Exception as e:
                    hook["execution_count"] = hook.get("execution_count", 0) + 1
                    hook["error_count"] = hook.get("error_count", 0) + 1
                    logger.error(f"[WEBHOOK_BRIDGE] Error: {e}", exc_info=True)
                    self._track_execution(hook["hook_id"], success=False)
                    await self._save_created_hooks()
            
            self.bot.add_listener(webhook_bridge_handler, "on_message")
            hook["_handler"] = webhook_bridge_handler
            logger.info(f"EventHooksCreater: Registered webhook_bridge handler for hook {hook['hook_id']}")
        
        elif template_id == "message_filter":
            async def message_filter_handler(message):
                if message.guild and message.guild.id != hook["guild_id"]:
                    return
                
                if message.author.bot:
                    return
                
                ignore_roles = hook["params"].get("ignore_roles", "")
                if ignore_roles and message.guild:
                    ignore_role_ids = [int(r.strip()) for r in ignore_roles.split(",") if r.strip().isdigit()]
                    if any(role.id in ignore_role_ids for role in message.author.roles):
                        return
                
                try:
                    banned_words = hook["params"]["banned_words"].split("\n")
                    banned_words = [w.strip() for w in banned_words if w.strip()]
                    
                    case_sensitive = hook["params"].get("case_sensitive", False)
                    content = message.content if case_sensitive else message.content.lower()
                    
                    triggered = False
                    for word in banned_words:
                        check_word = word if case_sensitive else word.lower()
                        if check_word in content:
                            triggered = True
                            break
                    
                    if not triggered:
                        return
                    
                    action = hook["params"].get("action", "delete")
                    
                    if action == "delete":
                        await message.delete()
                    elif action == "timeout" and message.guild:
                        timeout_duration = int(hook["params"].get("timeout_duration", 60))
                        await message.author.timeout(timedelta(seconds=timeout_duration), reason="Message filter triggered")
                    elif action == "warn":
                        try:
                            await message.author.send(f"⚠️ Your message in {message.guild.name} was flagged by the message filter.")
                        except:
                            pass
                    
                    if hook["params"].get("log_channel_id"):
                        log_channel = self.bot.get_channel(int(hook["params"]["log_channel_id"]))
                        if log_channel:
                            embed = discord.Embed(
                                title="🛡️ Message Filter Triggered",
                                description=f"**User:** {message.author.mention}\n**Channel:** {message.channel.mention}\n**Action:** {action}",
                                color=0xFF4444,
                                timestamp=datetime.now()
                            )
                            embed.add_field(name="Message Content", value=message.content[:1024], inline=False)
                            await log_channel.send(embed=embed)
                    
                    self._track_execution(hook["hook_id"], success=True, context={"user_id": message.author.id, "guild_id": message.guild.id if message.guild else 0})
                    hook["execution_count"] = hook.get("execution_count", 0) + 1
                    await self._save_created_hooks()
                    
                except Exception as e:
                    hook["error_count"] = hook.get("error_count", 0) + 1
                    logger.error(f"Message filter error: {e}")
                    self._track_execution(hook["hook_id"], success=False)
                    await self._save_created_hooks()
            
            self.bot.add_listener(message_filter_handler, "on_message")
            hook["_handler"] = message_filter_handler
        
        elif template_id == "auto_role_on_reaction":
            async def reaction_role_handler(payload):
                if payload.guild_id != hook["guild_id"]:
                    return
                
                try:
                    message_id = int(hook["params"]["message_id"])
                    if payload.message_id != message_id:
                        return
                    
                    role_emoji_map = hook["params"].get("role_emoji_map", {})
                    if isinstance(role_emoji_map, str):
                        role_emoji_map = json.loads(role_emoji_map)
                    
                    emoji_str = str(payload.emoji)
                    if emoji_str not in role_emoji_map:
                        return
                    
                    guild = self.bot.get_guild(payload.guild_id)
                    if not guild:
                        return
                    
                    role_id = int(role_emoji_map[emoji_str])
                    role = guild.get_role(role_id)
                    if not role:
                        return
                    
                    member = guild.get_member(payload.user_id)
                    if not member or member.bot:
                        return
                    
                    await member.add_roles(role)
                    
                    self._track_execution(hook["hook_id"], success=True, context={"user_id": member.id, "guild_id": guild.id})
                    hook["execution_count"] = hook.get("execution_count", 0) + 1
                    await self._save_created_hooks()
                    
                except Exception as e:
                    hook["error_count"] = hook.get("error_count", 0) + 1
                    logger.error(f"Reaction role error: {e}")
                    self._track_execution(hook["hook_id"], success=False)
                    await self._save_created_hooks()
            
            async def reaction_role_remove_handler(payload):
                if not hook["params"].get("remove_role_on_unreact", True):
                    return
                
                if payload.guild_id != hook["guild_id"]:
                    return
                
                try:
                    message_id = int(hook["params"]["message_id"])
                    if payload.message_id != message_id:
                        return
                    
                    role_emoji_map = hook["params"].get("role_emoji_map", {})
                    if isinstance(role_emoji_map, str):
                        role_emoji_map = json.loads(role_emoji_map)
                    
                    emoji_str = str(payload.emoji)
                    if emoji_str not in role_emoji_map:
                        return
                    
                    guild = self.bot.get_guild(payload.guild_id)
                    if not guild:
                        return
                    
                    role_id = int(role_emoji_map[emoji_str])
                    role = guild.get_role(role_id)
                    if not role:
                        return
                    
                    member = guild.get_member(payload.user_id)
                    if not member or member.bot:
                        return
                    
                    await member.remove_roles(role)
                    
                except Exception as e:
                    logger.error(f"Reaction role remove error: {e}")
            
            self.bot.add_listener(reaction_role_handler, "on_raw_reaction_add")
            self.bot.add_listener(reaction_role_remove_handler, "on_raw_reaction_remove")
            hook["_handler"] = reaction_role_handler
            hook["_handler_remove"] = reaction_role_remove_handler
        
        else:
            logger.warning(f"[_register_hook] No handler implementation for template '{template_id}' - hook will be created but won't trigger")
    
    def _unregister_hook(self, hook: Dict[str, Any]):
        if "_handler" in hook:
            event_name = hook["event"]
            if event_name != "scheduled":
                self.bot.remove_listener(hook["_handler"], event_name)
            del hook["_handler"]
        
        if "_handler_remove" in hook:
            self.bot.remove_listener(hook["_handler_remove"], "on_raw_reaction_remove")
            del hook["_handler_remove"]
        
        if hook["hook_id"] in self._scheduled_tasks:
            self._scheduled_tasks[hook["hook_id"]].cancel()
            del self._scheduled_tasks[hook["hook_id"]]
    
    def create_hook(self, template_id: str, params: Dict[str, Any], guild_id, created_by: str) -> Dict[str, Any]:
        guild_id = int(guild_id)
        
        template = next((t for t in self.templates if t["id"] == template_id), None)
        if not template:
            return {"success": False, "error": "Template not found"}
        
        for param in template["params"]:
            if param["required"] and param["name"] not in params:
                if "default" not in param:
                    return {"success": False, "error": f"Missing required parameter: {param['name']}"}
        
        hook_id = f"adv_{template_id}_{secrets.token_hex(8)}"
        
        hook = {
            "hook_id": hook_id,
            "template_id": template_id,
            "template_name": template["name"],
            "event": template["event"],
            "guild_id": guild_id,
            "params": params,
            "enabled": True,
            "advanced": template.get("advanced", False),
            "created_at": datetime.now().isoformat(),
            "created_by": created_by,
            "execution_count": 0,
            "error_count": 0
        }
        
        self.created_hooks.append(hook)
        asyncio.ensure_future(self._save_created_hooks())
        self._register_hook(hook)
        
        logger.info(f"EventHooksCreater: Created hook {hook_id} ({template['name']}) for guild {guild_id}")
        
        return {"success": True, "hook_id": hook_id, "hook": hook}
    
    def delete_hook(self, hook_id: str) -> Dict[str, Any]:
        hook = next((h for h in self.created_hooks if h["hook_id"] == hook_id), None)
        if not hook:
            return {"success": False, "error": "Hook not found"}
        
        self._unregister_hook(hook)
        self.created_hooks.remove(hook)
        asyncio.ensure_future(self._save_created_hooks())

        logger.info(f"EventHooksCreater: Deleted hook {hook_id}")
        
        return {"success": True}
    
    def toggle_hook(self, hook_id: str) -> Dict[str, Any]:
        hook = next((h for h in self.created_hooks if h["hook_id"] == hook_id), None)
        if not hook:
            return {"success": False, "error": "Hook not found"}
        
        if hook["enabled"]:
            self._unregister_hook(hook)
            hook["enabled"] = False
        else:
            self._register_hook(hook)
            hook["enabled"] = True
        
        asyncio.ensure_future(self._save_created_hooks())

        logger.info(f"EventHooksCreater: Toggled hook {hook_id} to {hook['enabled']}")
        
        return {"success": True, "enabled": hook["enabled"]}
    
    def get_templates(self) -> List[Dict[str, Any]]:
        return self.templates
    
    def get_all_created_hooks(self) -> List[Dict[str, Any]]:
        return [{k: v for k, v in hook.items() if not k.startswith("_")} for hook in self.created_hooks]
    
    def get_hooks_for_guild(self, guild_id: int) -> List[Dict[str, Any]]:
        return [{k: v for k, v in hook.items() if not k.startswith("_")} for hook in self.created_hooks if hook["guild_id"] == guild_id]
    
    def get_hook_stats(self) -> Dict[str, Any]:
        total = len(self.created_hooks)
        enabled = sum(1 for h in self.created_hooks if h.get("enabled", True))
        advanced = sum(1 for h in self.created_hooks if h.get("advanced", False))
        by_template = {}
        by_category = {}
        total_executions = sum(h.get("execution_count", 0) for h in self.created_hooks)
        total_errors = sum(h.get("error_count", 0) for h in self.created_hooks)
        
        for hook in self.created_hooks:
            template_id = hook["template_id"]
            if template_id not in by_template:
                by_template[template_id] = 0
            by_template[template_id] += 1
            
            template = next((t for t in self.templates if t["id"] == template_id), None)
            if template:
                category = template.get("category", "Other")
                if category not in by_category:
                    by_category[category] = 0
                by_category[category] += 1
        
        return {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
            "advanced": advanced,
            "by_template": by_template,
            "by_category": by_category,
            "total_executions": total_executions,
            "total_errors": total_errors,
            "success_rate": round((total_executions - total_errors) / total_executions * 100, 2) if total_executions > 0 else 100
        }
    
    def get_analytics(self, hook_id: Optional[str] = None) -> Dict:
        if hook_id:
            return self._analytics.get(hook_id, {})
        return self._analytics

async def setup(bot):
    await bot.add_cog(EventHooksCreater(bot))
    logger.info("EventHooksCreater cog loaded successfully")