## [Fix] — 2026-03-04 — v1.9.0.0 → v1.9.1.0

14 confirmed bug fixes across 11 cogs

---

### `cogs/GeminiService.py`
- [FIX] Cooldown stamp `_user_cooldowns[user.id] = now` was written **before** the `_active_requests >= _MAX_CONCURRENT` check — a user rejected for capacity silently consumed their 15-second cooldown slot. Stamp now written only after all guards pass.

### `cogs/GeminiServiceHelper.py`
- [FIX] `_cmd_update_config` guard was `if owner_id is not None and requester_id != owner_id` — if `application_info()` raised an exception, `owner_id` stayed `None` and the guard was vacuously false, allowing any caller to update config. Guard inverted to `if owner_id is None or requester_id != owner_id` (deny-by-default).
- [KNOWN — UPCOMING] **Security:** `collect_dashboard_data()` iterates all sessions and includes every user's `aes_key` and full history in the polled JSON. Any authenticated dashboard user can currently read other users' encryption keys. Fix requires live_monitor to pass the authenticated dashboard user's Discord ID at data-collection time (currently hardcoded `None`). **Will be addressed in v1.9.2.0.**

### `cogs/live_monitor.py` 
- [FIX] `on_command` listener was defined twice in the same class. The duplicate `on_command` + `on_command_error` pair caused every prefix/hybrid command to be double-counted in `_command_usage` and logged twice in the dashboard event log. Duplicate block removed from both files.
- [FIX] `cog_unload` was deleting `plugin_registry.json` on every hot-reload, destroying PluginRegistry's persisted data owned by another cog. Deletion removed from both files — Live Monitor only cleans up its own files.
- [FIX] `asyncio.get_event_loop()` (deprecated Python 3.10+) replaced with `asyncio.get_running_loop()` in `live_monitor_helper.py` (`_get_process`, `_collect_monitor_data`).

### `cogs/EventHooksCreater.py`
- [FIX] `or True` on the `implemented` status check made the `"⚠️"` branch permanently unreachable — all templates always showed `"✅"` regardless of implementation status. Removed `or True`.

### `cogs/plugin_registry.py`
- [FIX] `self.bot.extension_load_times[name]` was accessed without a `hasattr` guard — raises `AttributeError` if the bot doesn't expose the attribute, silently aborting `register_plugin`. Replaced with `getattr(self.bot, 'extension_load_times', {}).get(name, 0.0)`.
- [FIX] `_auto_scan_extension` only called `cog.get_commands()`, missing all pure `@app_commands.command` slash commands. Added `cog.get_app_commands()` scan — `/pr_info` and `/pr_list` now report accurate command counts for GeminiService, EventHooksCreater, etc.

### `cogs/backup_restore.py`
- [FIX] `BackupSnapshot` version string hardcoded as `"2.1.0"` while the cog is v2.2.0 — new snapshots were mis-tagged. Updated to `"2.2.0"`.

### `cogs/framework_diagnostics.py`
- [FIX] `on_app_command_error` listener added — slash command errors (the majority of commands in this framework) were never tracked in `_error_history` or `health_metrics["last_error"]`. Rolling error rate was systematically undercounted.
- [FIX] `asyncio.get_event_loop()` (deprecated Python 3.10+) replaced with `asyncio.get_running_loop()` in `_get_process` and `_get_system_metrics`.

### `cogs/event_hooks.py`
- [FIX] `disable_hook()` unconditionally added any string to `disabled_hooks` and returned `True` — a typo in a hook ID silently "succeeded", making the "hook not found" branch in commands dead code. Now returns `False` for unknown hook IDs.

### `cogs/shard_monitor.py`
- [FIX] Health alert had no debounce — `_send_health_alert` fired on every 60-second tick while a shard stayed unhealthy, flooding the alert channel. Added `_last_alert_time` with a 5-minute cooldown per alert.

### `cogs/shard_manager.py`
- [FIX] `_heartbeat_loop` captured `guild_count` at `connect()` time and sent the stale frozen value on every heartbeat. Now reads `len(self.bot.guilds)` live on each tick.

### `cogs/Guild_settings.py`
- [FIX] `action` parameter typed as `str` — Discord showed a free-text field with no hints. Changed to `Literal["enable", "disable", "status"]` so Discord renders a dropdown in slash mode.

---
