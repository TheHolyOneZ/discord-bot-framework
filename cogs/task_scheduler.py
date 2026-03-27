"""
Persistent Task Scheduler
Cron-like scheduling system that persists jobs to the database and survives restarts.
Extensions and users can create recurring tasks (send messages, emit hooks, run callbacks).

Supports standard cron expressions (minute hour day month weekday):
    "*/5 * * * *"      — every 5 minutes
    "0 9 * * 1"        — every Monday at 9:00 AM
    "30 12 1 * *"      — 12:30 PM on the 1st of every month
    "0 0 * * *"        — daily at midnight

Task types:
    - message: Send a message to a channel
    - hook: Emit a framework event hook
    - log: Write a log entry (useful for scheduled diagnostics)

Slash commands:
    /schedule create   — Create a new scheduled task
    /schedule list     — List tasks for this guild
    /schedule delete   — Delete a task
    /schedule toggle   — Enable/disable a task
    /schedule info     — Show task details
"""
# MIT License — Copyright (c) 2026 TheHolyOneZ
# Part of the Zoryx Discord Bot Framework
# https://github.com/TheHolyOneZ/discord-bot-framework

from discord.ext import commands, tasks
import discord
from discord import app_commands
import logging
import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger('discord.cogs.task_scheduler')


class CronParser:
    """
    Minimal cron expression parser.
    Supports: *, */N, N, N-M, N,M,O for each of 5 fields.
    Fields: minute(0-59) hour(0-23) day(1-31) month(1-12) weekday(0-6, 0=Monday)
    """

    FIELD_RANGES = [
        (0, 59),   # minute
        (0, 23),   # hour
        (1, 31),   # day of month
        (1, 12),   # month
        (0, 6),    # day of week (0=Monday, 6=Sunday)
    ]

    FIELD_NAMES = ["minute", "hour", "day", "month", "weekday"]

    @classmethod
    def validate(cls, expression: str) -> Optional[str]:
        parts = expression.strip().split()
        if len(parts) != 5:
            return f"Expected 5 fields (minute hour day month weekday), got {len(parts)}"

        for i, part in enumerate(parts):
            low, high = cls.FIELD_RANGES[i]
            err = cls._validate_field(part, low, high, cls.FIELD_NAMES[i])
            if err:
                return err

        return None

    @classmethod
    def _validate_field(cls, field: str, low: int, high: int, name: str) -> Optional[str]:
        for segment in field.split(","):
            segment = segment.strip()
            if segment == "*":
                continue
            if segment.startswith("*/"):
                try:
                    step = int(segment[2:])
                    if step < 1 or step > high:
                        return f"{name}: step */{ segment[2:]} out of range (1-{high})"
                except ValueError:
                    return f"{name}: invalid step '{segment}'"
                continue
            if "-" in segment:
                range_parts = segment.split("-")
                if len(range_parts) != 2:
                    return f"{name}: invalid range '{segment}'"
                try:
                    a, b = int(range_parts[0]), int(range_parts[1])
                    if a < low or b > high or a > b:
                        return f"{name}: range {a}-{b} out of bounds ({low}-{high})"
                except ValueError:
                    return f"{name}: invalid range '{segment}'"
                continue
            try:
                val = int(segment)
                if val < low or val > high:
                    return f"{name}: value {val} out of range ({low}-{high})"
            except ValueError:
                return f"{name}: invalid value '{segment}'"
        return None

    @classmethod
    def matches(cls, expression: str, dt: datetime) -> bool:
        parts = expression.strip().split()
        if len(parts) != 5:
            return False

        values = [dt.minute, dt.hour, dt.day, dt.month, dt.weekday()]

        for i, part in enumerate(parts):
            low, high = cls.FIELD_RANGES[i]
            if not cls._field_matches(part, values[i], low, high):
                return False
        return True

    @classmethod
    def _field_matches(cls, field: str, value: int, low: int, high: int) -> bool:
        for segment in field.split(","):
            segment = segment.strip()
            if segment == "*":
                return True
            if segment.startswith("*/"):
                step = int(segment[2:])
                if (value - low) % step == 0:
                    return True
                continue
            if "-" in segment:
                a, b = segment.split("-")
                if int(a) <= value <= int(b):
                    return True
                continue
            if int(segment) == value:
                return True
        return False

    @classmethod
    def next_run(cls, expression: str, after: datetime) -> Optional[datetime]:
        """Searches up to 366 days ahead. Returns None if no match found."""
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = after + timedelta(days=366)

        while candidate < limit:
            if cls.matches(expression, candidate):
                return candidate
            candidate += timedelta(minutes=1)

        return None

    @classmethod
    def describe(cls, expression: str) -> str:
        parts = expression.strip().split()
        if len(parts) != 5:
            return expression

        minute, hour, day, month, weekday = parts

        if expression == "* * * * *":
            return "Every minute"
        if minute.startswith("*/") and hour == "*" and day == "*" and month == "*" and weekday == "*":
            return f"Every {minute[2:]} minutes"
        if hour.startswith("*/") and day == "*" and month == "*" and weekday == "*":
            return f"Every {hour[2:]} hours at minute {minute}"
        if day == "*" and month == "*" and weekday == "*":
            return f"Daily at {hour.zfill(2)}:{minute.zfill(2)}"
        if day == "*" and month == "*" and weekday != "*":
            days_map = {
                "0": "Monday", "1": "Tuesday", "2": "Wednesday",
                "3": "Thursday", "4": "Friday", "5": "Saturday", "6": "Sunday"
            }
            day_name = days_map.get(weekday, f"weekday {weekday}")
            return f"Every {day_name} at {hour.zfill(2)}:{minute.zfill(2)}"

        return expression


class TaskScheduler(commands.Cog, name="Task Scheduler"):

    VALID_TASK_TYPES = ("message", "hook", "log")

    def __init__(self, bot):
        self.bot = bot
        self._tasks_cache: Dict[str, Dict[str, Any]] = {}
        self._initialized = False
        logger.info("TaskScheduler cog loaded")

    async def cog_load(self):
        await self._load_tasks()
        self._initialized = True
        self.scheduler_tick.start()

    def cog_unload(self):
        self.scheduler_tick.cancel()
        logger.info("TaskScheduler cog unloaded")

    async def _load_tasks(self):
        db = getattr(self.bot, 'db', None)
        if db is None or db.conn is None:
            logger.warning("TaskScheduler: No database connection available")
            return

        try:
            async with db.conn.execute(
                "SELECT * FROM scheduled_tasks"
            ) as cursor:
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                for row in rows:
                    task = dict(zip(columns, row))
                    # Normalize SQLite int 1/0 to Python bool
                    task["enabled"] = bool(task.get("enabled", 1))
                    self._tasks_cache[task["task_id"]] = task
            enabled_count = sum(1 for t in self._tasks_cache.values() if t.get("enabled"))
            logger.info(f"TaskScheduler: Loaded {len(self._tasks_cache)} task(s) ({enabled_count} enabled)")
        except Exception as e:
            # Table might not exist yet if migrations haven't run
            if "no such table" in str(e).lower():
                logger.info("TaskScheduler: scheduled_tasks table not found — run migration 001 first")
            else:
                logger.error(f"TaskScheduler: Failed to load tasks: {e}")

    async def _save_task(self, task: Dict[str, Any]) -> bool:
        db = getattr(self.bot, 'db', None)
        if db is None or db.conn is None:
            return False

        try:
            await db.conn.execute(
                "INSERT OR REPLACE INTO scheduled_tasks "
                "(task_id, guild_id, channel_id, creator_id, task_name, task_type, "
                "cron_expression, payload, enabled, last_run, next_run, run_count, "
                "max_runs, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task["task_id"], task.get("guild_id"), task.get("channel_id"),
                    task["creator_id"], task["task_name"], task["task_type"],
                    task["cron_expression"], task.get("payload", "{}"),
                    1 if task.get("enabled", True) else 0,
                    task.get("last_run"), task.get("next_run"),
                    task.get("run_count", 0), task.get("max_runs"),
                    task["created_at"], task["updated_at"]
                )
            )
            await db.conn.commit()
            return True
        except Exception as e:
            logger.error(f"TaskScheduler: Failed to save task {task.get('task_id')}: {e}")
            return False

    async def _delete_task_db(self, task_id: str) -> bool:
        db = getattr(self.bot, 'db', None)
        if db is None or db.conn is None:
            return False

        try:
            await db.conn.execute("DELETE FROM scheduled_tasks WHERE task_id = ?", (task_id,))
            await db.conn.commit()
            return True
        except Exception as e:
            logger.error(f"TaskScheduler: Failed to delete task {task_id}: {e}")
            return False

    @tasks.loop(seconds=30)
    async def scheduler_tick(self):
        now = datetime.now()

        for task_id, task in list(self._tasks_cache.items()):
            if not task.get("enabled", True):
                continue

            max_runs = task.get("max_runs")
            if max_runs is not None and task.get("run_count", 0) >= max_runs:
                task["enabled"] = False
                task["updated_at"] = now.isoformat()
                await self._save_task(task)
                logger.info(f"TaskScheduler: Task '{task['task_name']}' reached max_runs ({max_runs}), disabled")
                continue

            if CronParser.matches(task["cron_expression"], now):
                # Deduplicate: skip if already ran within the last 55 seconds
                last_run = task.get("last_run")
                if last_run:
                    try:
                        last_run_dt = datetime.fromisoformat(last_run)
                        if (now - last_run_dt).total_seconds() < 55:
                            continue
                    except (ValueError, TypeError):
                        pass

                await self._execute_task(task)

    @scheduler_tick.before_loop
    async def before_scheduler_tick(self):
        await self.bot.wait_until_ready()

    async def _execute_task(self, task: Dict[str, Any]):
        now = datetime.now()
        task_type = task.get("task_type", "log")
        task_name = task.get("task_name", "unknown")

        try:
            if task_type == "message":
                await self._execute_message_task(task)
            elif task_type == "hook":
                await self._execute_hook_task(task)
            elif task_type == "log":
                await self._execute_log_task(task)
            else:
                logger.warning(f"TaskScheduler: Unknown task type '{task_type}' for task '{task_name}'")
                return

            task["last_run"] = now.isoformat()
            task["run_count"] = task.get("run_count", 0) + 1
            next_run = CronParser.next_run(task["cron_expression"], now)
            task["next_run"] = next_run.isoformat() if next_run else None
            task["updated_at"] = now.isoformat()
            await self._save_task(task)

            logger.debug(f"TaskScheduler: Executed task '{task_name}' (run #{task['run_count']})")

        except Exception as e:
            logger.error(f"TaskScheduler: Failed to execute task '{task_name}': {e}")

    async def _execute_message_task(self, task: Dict[str, Any]):
        channel_id = task.get("channel_id")
        if not channel_id:
            logger.warning(f"TaskScheduler: Message task '{task['task_name']}' has no channel_id")
            return

        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            logger.warning(f"TaskScheduler: Channel {channel_id} not found for task '{task['task_name']}'")
            return

        if not isinstance(channel, discord.TextChannel):
            logger.warning(f"TaskScheduler: Channel {channel_id} is not a text channel")
            return

        try:
            payload = json.loads(task.get("payload", "{}"))
        except json.JSONDecodeError:
            payload = {}

        content = payload.get("content", "")
        embed_data = payload.get("embed")

        if embed_data:
            embed = discord.Embed.from_dict(embed_data)
            await channel.send(content=content or None, embed=embed)
        elif content:
            await channel.send(content)
        else:
            logger.warning(f"TaskScheduler: Message task '{task['task_name']}' has no content or embed")

    async def _execute_hook_task(self, task: Dict[str, Any]):
        emit_hook = getattr(self.bot, 'emit_hook', None)
        if emit_hook is None:
            logger.warning("TaskScheduler: No emit_hook available on bot — EventHooks cog not loaded?")
            return

        try:
            payload = json.loads(task.get("payload", "{}"))
        except json.JSONDecodeError:
            payload = {}

        hook_name = payload.get("hook_name", "scheduled_task")
        hook_data = payload.get("data", {})
        hook_data["_task_name"] = task.get("task_name")
        hook_data["_task_id"] = task.get("task_id")

        await emit_hook(hook_name, **hook_data)

    async def _execute_log_task(self, task: Dict[str, Any]):
        try:
            payload = json.loads(task.get("payload", "{}"))
        except json.JSONDecodeError:
            payload = {}

        message = payload.get("message", f"Scheduled task '{task['task_name']}' fired")
        level = payload.get("level", "INFO").upper()

        log_fn = getattr(logger, level.lower(), logger.info)
        log_fn(f"TaskScheduler [scheduled]: {message}")

    # ── Slash Commands ──────────────────────────────────────────────

    schedule_group = app_commands.Group(
        name="schedule",
        description="Manage persistent scheduled tasks"
    )

    @schedule_group.command(name="create", description="Create a new scheduled task")
    @app_commands.describe(
        name="Task name (unique within this guild)",
        cron="Cron expression: minute hour day month weekday (e.g. '0 9 * * 1' = Monday 9AM)",
        task_type="What the task does",
        channel="Channel for message tasks (required for message type)",
        content="Message content or JSON payload",
        max_runs="Maximum number of executions (leave empty for unlimited)"
    )
    @app_commands.choices(task_type=[
        app_commands.Choice(name="Send a message", value="message"),
        app_commands.Choice(name="Emit a hook event", value="hook"),
        app_commands.Choice(name="Write a log entry", value="log"),
    ])
    async def schedule_create(
        self,
        interaction: discord.Interaction,
        name: str,
        cron: str,
        task_type: str = "message",
        channel: Optional[discord.TextChannel] = None,
        content: Optional[str] = None,
        max_runs: Optional[int] = None
    ):
        if interaction.user.id != self.bot.bot_owner_id:
            if not interaction.guild or interaction.user.id != interaction.guild.owner_id:
                await interaction.response.send_message(
                    "This command requires bot owner or guild owner permissions.", ephemeral=True
                )
                return

        cron_error = CronParser.validate(cron)
        if cron_error:
            await interaction.response.send_message(
                f"Invalid cron expression: {cron_error}", ephemeral=True
            )
            return

        if task_type not in self.VALID_TASK_TYPES:
            await interaction.response.send_message(
                f"Invalid task type. Valid types: {', '.join(self.VALID_TASK_TYPES)}", ephemeral=True
            )
            return

        if task_type == "message" and channel is None:
            await interaction.response.send_message(
                "Message tasks require a target channel.", ephemeral=True
            )
            return

        if task_type == "message":
            payload = json.dumps({"content": content or ""})
        elif task_type == "hook":
            payload = json.dumps({"hook_name": content or "scheduled_task", "data": {}})
        elif task_type == "log":
            payload = json.dumps({"message": content or f"Scheduled: {name}", "level": "INFO"})
        else:
            payload = "{}"

        now = datetime.now()
        next_run = CronParser.next_run(cron, now)

        task = {
            "task_id": str(uuid.uuid4())[:12],
            "guild_id": interaction.guild_id,
            "channel_id": channel.id if channel else None,
            "creator_id": interaction.user.id,
            "task_name": name,
            "task_type": task_type,
            "cron_expression": cron,
            "payload": payload,
            "enabled": True,
            "last_run": None,
            "next_run": next_run.isoformat() if next_run else None,
            "run_count": 0,
            "max_runs": max_runs,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }

        success = await self._save_task(task)
        if not success:
            await interaction.response.send_message(
                "Failed to save task to database. Check logs for details.", ephemeral=True
            )
            return

        self._tasks_cache[task["task_id"]] = task

        embed = discord.Embed(
            title="Scheduled Task Created",
            color=0x00ff00,
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Name", value=f"```{name}```", inline=True)
        embed.add_field(name="Type", value=f"```{task_type}```", inline=True)
        embed.add_field(name="Schedule", value=f"```{CronParser.describe(cron)}```", inline=False)
        embed.add_field(name="Cron", value=f"```{cron}```", inline=True)
        if next_run:
            embed.add_field(name="Next Run", value=f"```{next_run.strftime('%Y-%m-%d %H:%M')}```", inline=True)
        if max_runs:
            embed.add_field(name="Max Runs", value=f"```{max_runs}```", inline=True)
        embed.add_field(name="Task ID", value=f"```{task['task_id']}```", inline=False)
        embed.set_footer(text="Task Scheduler")

        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"TaskScheduler: Task '{name}' created by {interaction.user} (ID: {task['task_id']})")

    @schedule_group.command(name="list", description="List scheduled tasks for this guild")
    async def schedule_list(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id

        guild_tasks = [
            t for t in self._tasks_cache.values()
            if t.get("guild_id") == guild_id
        ]

        if interaction.user.id == self.bot.bot_owner_id:
            global_tasks = [
                t for t in self._tasks_cache.values()
                if t.get("guild_id") is None
            ]
            guild_tasks.extend(global_tasks)

        if not guild_tasks:
            await interaction.response.send_message(
                "No scheduled tasks found for this guild.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Scheduled Tasks",
            description=f"**{len(guild_tasks)}** task(s)",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )

        for task in guild_tasks[:15]:
            status = "ON" if task.get("enabled", True) else "OFF"
            runs = task.get("run_count", 0)
            max_r = task.get("max_runs")
            runs_text = f"{runs}/{max_r}" if max_r else str(runs)

            desc = CronParser.describe(task["cron_expression"])
            next_run = task.get("next_run", "N/A")
            if next_run and next_run != "N/A":
                try:
                    next_run = datetime.fromisoformat(next_run).strftime("%m-%d %H:%M")
                except (ValueError, TypeError):
                    pass

            embed.add_field(
                name=f"[{status}] {task['task_name']}",
                value=f"```Type: {task['task_type']} | Runs: {runs_text}\n{desc}\nNext: {next_run}\nID: {task['task_id']}```",
                inline=False
            )

        if len(guild_tasks) > 15:
            embed.set_footer(text=f"Showing 15/{len(guild_tasks)} tasks")
        else:
            embed.set_footer(text="Task Scheduler")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @schedule_group.command(name="delete", description="Delete a scheduled task")
    @app_commands.describe(task_id="The task ID to delete")
    async def schedule_delete(self, interaction: discord.Interaction, task_id: str):
        task = self._tasks_cache.get(task_id)
        if not task:
            await interaction.response.send_message(
                f"Task `{task_id}` not found.", ephemeral=True
            )
            return

        if interaction.user.id != self.bot.bot_owner_id and interaction.user.id != task.get("creator_id"):
            await interaction.response.send_message(
                "You can only delete tasks you created.", ephemeral=True
            )
            return

        success = await self._delete_task_db(task_id)
        if success:
            del self._tasks_cache[task_id]
            await interaction.response.send_message(
                f"Task `{task['task_name']}` (`{task_id}`) deleted.", ephemeral=True
            )
            logger.info(f"TaskScheduler: Task '{task['task_name']}' deleted by {interaction.user}")
        else:
            await interaction.response.send_message(
                "Failed to delete task from database.", ephemeral=True
            )

    @schedule_group.command(name="toggle", description="Enable or disable a scheduled task")
    @app_commands.describe(task_id="The task ID to toggle")
    async def schedule_toggle(self, interaction: discord.Interaction, task_id: str):
        task = self._tasks_cache.get(task_id)
        if not task:
            await interaction.response.send_message(
                f"Task `{task_id}` not found.", ephemeral=True
            )
            return

        if interaction.user.id != self.bot.bot_owner_id and interaction.user.id != task.get("creator_id"):
            await interaction.response.send_message(
                "You can only toggle tasks you created.", ephemeral=True
            )
            return

        new_state = not task.get("enabled", True)
        task["enabled"] = new_state
        task["updated_at"] = datetime.now().isoformat()

        if new_state:
            next_run = CronParser.next_run(task["cron_expression"], datetime.now())
            task["next_run"] = next_run.isoformat() if next_run else None

        await self._save_task(task)
        state_text = "enabled" if new_state else "disabled"

        await interaction.response.send_message(
            f"Task `{task['task_name']}` is now **{state_text}**.", ephemeral=True
        )
        logger.info(f"TaskScheduler: Task '{task['task_name']}' {state_text} by {interaction.user}")

    @schedule_group.command(name="info", description="Show details of a scheduled task")
    @app_commands.describe(task_id="The task ID to inspect")
    async def schedule_info(self, interaction: discord.Interaction, task_id: str):
        task = self._tasks_cache.get(task_id)
        if not task:
            await interaction.response.send_message(
                f"Task `{task_id}` not found.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Task: {task['task_name']}",
            color=0x00ff00 if task.get("enabled") else 0xff0000,
            timestamp=discord.utils.utcnow()
        )

        embed.add_field(name="ID", value=f"```{task['task_id']}```", inline=True)
        embed.add_field(name="Type", value=f"```{task['task_type']}```", inline=True)
        embed.add_field(name="Status", value=f"```{'Enabled' if task.get('enabled') else 'Disabled'}```", inline=True)
        embed.add_field(name="Cron", value=f"```{task['cron_expression']}```", inline=True)
        embed.add_field(name="Schedule", value=f"```{CronParser.describe(task['cron_expression'])}```", inline=True)

        runs = task.get("run_count", 0)
        max_r = task.get("max_runs")
        embed.add_field(name="Runs", value=f"```{runs}/{max_r if max_r else 'unlimited'}```", inline=True)

        if task.get("last_run"):
            embed.add_field(name="Last Run", value=f"```{task['last_run'][:19]}```", inline=True)
        if task.get("next_run"):
            embed.add_field(name="Next Run", value=f"```{task['next_run'][:19]}```", inline=True)

        if task.get("channel_id"):
            embed.add_field(name="Channel", value=f"<#{task['channel_id']}>", inline=True)

        embed.add_field(name="Creator", value=f"<@{task['creator_id']}>", inline=True)
        embed.add_field(name="Created", value=f"```{task['created_at'][:19]}```", inline=True)

        embed.set_footer(text="Task Scheduler")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Public API for extensions ────────────────────────────────────

    async def create_task_programmatic(
        self,
        task_name: str,
        cron_expression: str,
        task_type: str = "hook",
        guild_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        creator_id: int = 0,
        payload: Optional[dict] = None,
        max_runs: Optional[int] = None
    ) -> Optional[str]:
        """Create a scheduled task from code. Returns task_id on success, None on failure."""
        cron_error = CronParser.validate(cron_expression)
        if cron_error:
            logger.error(f"TaskScheduler API: Invalid cron '{cron_expression}': {cron_error}")
            return None

        now = datetime.now()
        next_run = CronParser.next_run(cron_expression, now)

        task = {
            "task_id": str(uuid.uuid4())[:12],
            "guild_id": guild_id,
            "channel_id": channel_id,
            "creator_id": creator_id,
            "task_name": task_name,
            "task_type": task_type,
            "cron_expression": cron_expression,
            "payload": json.dumps(payload or {}),
            "enabled": True,
            "last_run": None,
            "next_run": next_run.isoformat() if next_run else None,
            "run_count": 0,
            "max_runs": max_runs,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }

        success = await self._save_task(task)
        if success:
            self._tasks_cache[task["task_id"]] = task
            logger.info(f"TaskScheduler API: Created task '{task_name}' (ID: {task['task_id']})")
            return task["task_id"]
        return None


async def setup(bot):
    await bot.add_cog(TaskScheduler(bot))
    logger.info("Task Scheduler cog loaded successfully")
