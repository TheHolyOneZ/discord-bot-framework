"""
Database Migration System
Provides versioned, sequential database schema migrations for the framework.
Tracks applied migrations in the main database, runs pending migrations on startup,
and exposes /fw_migrations for status inspection.

Migration files live in ./migrations/ as numbered Python files:
    001_add_user_preferences.py
    002_add_scheduled_tasks.py
    ...

Each migration file must define:
    async def up(db: SafeDatabaseManager) -> None:
        '''Apply this migration.'''
        ...

    description = "Human-readable description of what this migration does"
"""
# MIT License — Copyright (c) 2026 TheHolyOneZ
# Part of the Zoryx Discord Bot Framework
# https://github.com/TheHolyOneZ/discord-bot-framework

from discord.ext import commands
import discord
from discord import app_commands
import logging
import importlib.util
import traceback
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger('discord.cogs.db_migrations')


class Migration:

    def __init__(self, number: int, name: str, file_path: Path):
        self.number = number
        self.name = name
        self.file_path = file_path
        self.description = "No description"
        self._up_fn = None

    def load(self) -> bool:
        try:
            spec = importlib.util.spec_from_file_location(
                f"migration_{self.number:03d}", str(self.file_path)
            )
            if spec is None or spec.loader is None:
                logger.error(f"Migration {self.number:03d}: Could not create module spec for {self.file_path}")
                return False

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, 'up') or not callable(module.up):
                logger.error(f"Migration {self.number:03d}: Missing 'up' function in {self.file_path.name}")
                return False

            self._up_fn = module.up
            self.description = getattr(module, 'description', "No description")
            return True

        except Exception as e:
            logger.error(f"Migration {self.number:03d}: Failed to load {self.file_path.name}: {e}")
            logger.debug(traceback.format_exc())
            return False

    async def execute(self, db) -> bool:
        if self._up_fn is None:
            logger.error(f"Migration {self.number:03d}: Not loaded, cannot execute")
            return False

        try:
            await self._up_fn(db)
            return True
        except Exception as e:
            logger.error(f"Migration {self.number:03d}: Execution failed: {e}")
            logger.debug(traceback.format_exc())
            return False


class DatabaseMigrations(commands.Cog, name="Database Migrations"):

    def __init__(self, bot):
        self.bot = bot
        self.migrations_dir = Path("./migrations")
        self._applied: List[Dict[str, Any]] = []
        self._pending: List[Migration] = []
        self._failed: List[Dict[str, Any]] = []
        self._initialized = False
        logger.info("DatabaseMigrations cog loaded")

    async def cog_load(self):
        await self._ensure_migrations_table()
        await self._run_pending_migrations()
        self._initialized = True

    def cog_unload(self):
        logger.info("DatabaseMigrations cog unloaded")

    async def _ensure_migrations_table(self):
        db = getattr(self.bot, 'db', None)
        if db is None or db.conn is None:
            logger.warning("DatabaseMigrations: No database connection available")
            return

        try:
            await db.conn.execute("""
                CREATE TABLE IF NOT EXISTS _schema_migrations (
                    migration_number INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success INTEGER DEFAULT 1
                )
            """)
            await db.conn.commit()
            logger.debug("DatabaseMigrations: Migrations table ready")
        except Exception as e:
            logger.error(f"DatabaseMigrations: Failed to create migrations table: {e}")

    def _discover_migrations(self) -> List[Migration]:
        if not self.migrations_dir.exists():
            self.migrations_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"DatabaseMigrations: Created migrations directory at {self.migrations_dir}")
            return []

        migrations = []
        for filepath in sorted(self.migrations_dir.glob("*.py")):
            stem = filepath.stem
            parts = stem.split("_", 1)
            if len(parts) < 2:
                logger.warning(f"DatabaseMigrations: Skipping {filepath.name} — expected format NNN_name.py")
                continue

            try:
                number = int(parts[0])
            except ValueError:
                logger.warning(f"DatabaseMigrations: Skipping {filepath.name} — prefix is not a number")
                continue

            name = parts[1]
            migrations.append(Migration(number, name, filepath))

        migrations.sort(key=lambda m: m.number)
        return migrations

    async def _get_applied_numbers(self) -> set:
        db = getattr(self.bot, 'db', None)
        if db is None or db.conn is None:
            return set()

        try:
            async with db.conn.execute(
                "SELECT migration_number FROM _schema_migrations WHERE success = 1"
            ) as cursor:
                rows = await cursor.fetchall()
                return {row[0] for row in rows}
        except Exception as e:
            logger.error(f"DatabaseMigrations: Failed to read applied migrations: {e}")
            return set()

    async def _get_applied_details(self) -> List[Dict[str, Any]]:
        db = getattr(self.bot, 'db', None)
        if db is None or db.conn is None:
            return []

        try:
            async with db.conn.execute(
                "SELECT migration_number, name, description, applied_at, success "
                "FROM _schema_migrations ORDER BY migration_number"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "number": row[0],
                        "name": row[1],
                        "description": row[2],
                        "applied_at": row[3],
                        "success": bool(row[4])
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"DatabaseMigrations: Failed to read migration details: {e}")
            return []

    async def _record_migration(self, migration: Migration, success: bool):
        db = getattr(self.bot, 'db', None)
        if db is None or db.conn is None:
            return

        try:
            await db.conn.execute(
                "INSERT OR REPLACE INTO _schema_migrations "
                "(migration_number, name, description, applied_at, success) "
                "VALUES (?, ?, ?, ?, ?)",
                (migration.number, migration.name, migration.description,
                 datetime.now().isoformat(), 1 if success else 0)
            )
            await db.conn.commit()
        except Exception as e:
            logger.error(f"DatabaseMigrations: Failed to record migration {migration.number:03d}: {e}")

    async def _run_pending_migrations(self):
        self._failed.clear()

        all_migrations = self._discover_migrations()
        if not all_migrations:
            logger.info("DatabaseMigrations: No migration files found")
            return

        applied_numbers = await self._get_applied_numbers()
        pending = [m for m in all_migrations if m.number not in applied_numbers]

        if not pending:
            logger.info(f"DatabaseMigrations: All {len(all_migrations)} migrations already applied")
            self._applied = await self._get_applied_details()
            return

        logger.info(f"DatabaseMigrations: {len(pending)} pending migration(s) to apply")

        applied_count = 0
        failed_count = 0

        for migration in pending:
            if not migration.load():
                self._failed.append({
                    "number": migration.number,
                    "name": migration.name,
                    "error": "Failed to load migration file"
                })
                await self._record_migration(migration, success=False)
                failed_count += 1
                # Stop on first failure — migrations are sequential
                logger.error(f"DatabaseMigrations: Stopping at migration {migration.number:03d} (load failure)")
                break

            logger.info(f"DatabaseMigrations: Applying migration {migration.number:03d}_{migration.name}...")
            success = await migration.execute(self.bot.db)

            if success:
                await self._record_migration(migration, success=True)
                applied_count += 1
                logger.info(f"DatabaseMigrations: Applied {migration.number:03d}_{migration.name}")
            else:
                self._failed.append({
                    "number": migration.number,
                    "name": migration.name,
                    "error": "Execution failed"
                })
                await self._record_migration(migration, success=False)
                failed_count += 1
                logger.error(f"DatabaseMigrations: Stopping at migration {migration.number:03d} (execution failure)")
                break

        self._applied = await self._get_applied_details()
        self._pending = [m for m in all_migrations if m.number not in await self._get_applied_numbers()]

        logger.info(
            f"DatabaseMigrations: Run complete — {applied_count} applied, "
            f"{failed_count} failed, {len(self._pending)} still pending"
        )

    @app_commands.command(name="fw_migrations", description="Show database migration status (Bot Owner Only)")
    async def migrations_status(self, interaction: discord.Interaction):
        if interaction.user.id != self.bot.bot_owner_id:
            await interaction.response.send_message(
                "This command is restricted to the bot owner.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        applied = await self._get_applied_details()
        all_migrations = self._discover_migrations()
        applied_numbers = {m["number"] for m in applied if m["success"]}
        pending = [m for m in all_migrations if m.number not in applied_numbers]
        failed = [m for m in applied if not m["success"]]

        total = len(all_migrations)
        color = 0x00ff00 if not failed and not pending else (0xff0000 if failed else 0xffa500)

        embed = discord.Embed(
            title="Database Migration Status",
            description=f"**{len(applied_numbers)}** applied, **{len(pending)}** pending, **{len(failed)}** failed out of **{total}** total",
            color=color,
            timestamp=discord.utils.utcnow()
        )

        if applied:
            applied_text = ""
            for m in applied[-10:]:
                status_icon = "+" if m["success"] else "!"
                applied_text += f"[{status_icon}] {m['number']:03d} {m['name']}\n"
                if m.get("applied_at"):
                    applied_text += f"    Applied: {m['applied_at'][:19]}\n"
            embed.add_field(
                name=f"Applied ({len(applied_numbers)})",
                value=f"```diff\n{applied_text.strip()}```" if applied_text.strip() else "```None```",
                inline=False
            )

        if pending:
            pending_text = "\n".join(f"{m.number:03d} {m.name}" for m in pending[:10])
            if len(pending) > 10:
                pending_text += f"\n... and {len(pending) - 10} more"
            embed.add_field(
                name=f"Pending ({len(pending)})",
                value=f"```{pending_text}```",
                inline=False
            )

        if failed:
            failed_text = "\n".join(f"{m['number']:03d} {m['name']}" for m in failed)
            embed.add_field(
                name=f"Failed ({len(failed)})",
                value=f"```diff\n- {failed_text}```",
                inline=False
            )

        if not all_migrations:
            embed.add_field(
                name="Info",
                value=f"```No migration files found in ./migrations/\nCreate files like: 001_description.py```",
                inline=False
            )

        embed.set_footer(text="Database Migration System")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="fw_migrate", description="Re-run pending migrations (Bot Owner Only)")
    async def run_migrations(self, interaction: discord.Interaction):
        if interaction.user.id != self.bot.bot_owner_id:
            await interaction.response.send_message(
                "This command is restricted to the bot owner.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        before_count = len(await self._get_applied_numbers())
        await self._run_pending_migrations()
        after_count = len(await self._get_applied_numbers())

        new_applied = after_count - before_count
        color = 0x00ff00 if not self._failed else 0xffa500

        embed = discord.Embed(
            title="Migration Run Complete",
            description=f"**{new_applied}** new migration(s) applied",
            color=color,
            timestamp=discord.utils.utcnow()
        )

        if self._failed:
            failed_text = "\n".join(
                f"{f['number']:03d} {f['name']}: {f['error']}" for f in self._failed
            )
            embed.add_field(
                name="Failed",
                value=f"```diff\n- {failed_text}```",
                inline=False
            )

        if self._pending:
            embed.add_field(
                name="Still Pending",
                value=f"```{len(self._pending)} migration(s) remain```",
                inline=False
            )

        embed.set_footer(text="Database Migration System")
        await interaction.followup.send(embed=embed, ephemeral=True)


    # ── Public API for extensions ────────────────────────────────────

    def is_migration_applied(self, migration_number: int) -> bool:
        """
        Check if a specific migration has been applied.

        Usage from an extension:
            migrations = bot.get_cog("Database Migrations")
            if migrations and migrations.is_migration_applied(1):
                # scheduled_tasks table exists, safe to use it
        """
        return any(
            m["number"] == migration_number and m["success"]
            for m in self._applied
        )

    @property
    def applied_migrations(self) -> List[Dict[str, Any]]:
        return list(self._applied)

    @property
    def failed_migrations(self) -> List[Dict[str, Any]]:
        return list(self._failed)


async def setup(bot):
    await bot.add_cog(DatabaseMigrations(bot))
    logger.info("Database Migrations cog loaded successfully")
