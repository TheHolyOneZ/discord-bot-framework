"""
Migration 001: Add scheduled_tasks table
Used by the Persistent Task Scheduler cog to store jobs that survive restarts.
"""

description = "Create scheduled_tasks table for persistent task scheduler"


async def up(db):
    """Apply this migration."""
    await db.conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            task_id TEXT PRIMARY KEY,
            guild_id INTEGER,
            channel_id INTEGER,
            creator_id INTEGER NOT NULL,
            task_name TEXT NOT NULL,
            task_type TEXT NOT NULL DEFAULT 'message',
            cron_expression TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_run TEXT,
            next_run TEXT,
            run_count INTEGER NOT NULL DEFAULT 0,
            max_runs INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    await db.conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_next_run
        ON scheduled_tasks(next_run) WHERE enabled = 1
    """)
    await db.conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_guild
        ON scheduled_tasks(guild_id)
    """)
    await db.conn.commit()
