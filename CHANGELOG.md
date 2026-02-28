## [Update] — 2026-02-28 — v1.7.2.2 → v1.8.0.0

### `cogs/framework_diagnostics.py` 

#### Persistence
- [FIX] Alert channel now persisted to `./data/framework_diagnostics_config.json` — survives bot restarts, no longer needs to be re-set every time

#### Reliability
- [FIX] `bot.metrics` is no longer a hard dependency — all accesses wrapped with `getattr` fallbacks; cog loads and runs without crashing even if the main bot doesn't implement `bot.metrics`
- [FIX] Loop lag threshold is now configurable via `FW_LOOP_LAG_THRESHOLD_MS` env var (default: 500ms) — no longer hardcoded and no longer stored confusingly as seconds while being compared as ms

#### Accuracy
- [FIX] Loop lag now uses a rolling average of the last 10 readings instead of the raw instantaneous value — eliminates false alerts from single-tick jitter
- [FIX] Error rate now computed over a rolling 1-hour window (delta of 12 × 5-minute snapshots) instead of lifetime totals — an early error burst no longer permanently inflates the rate; `/fw_diagnostics` shows `(rolling 1h)` or `(lifetime)` to indicate which mode is active

#### History & Observability
- [ADD] Health check history: last 48 entries (4 hours) kept in memory and persisted to `./data/framework_health_history.json` after each health_monitor run
- [ADD] Error history: last 20 command errors kept in a deque; `on_command_error` now appends each error with timestamp and command name instead of overwriting a single field
- [ADD] `/fw_history [entries]` command — shows last N (1–20) health check snapshots with timestamp, status, error rate, and loop lag per entry
- [ADD] `/fw_errors` command — shows the last 20 command errors with timestamp, command name, and error message

#### Embed improvements
- [CHG] `/fw_diagnostics` health field now shows rolling window note, recent error count, and `(avg 10s)` annotation on loop lag


### `cogs/GeminiService.py` 

#### Security
- [FIX] `file` action is now restricted to bot owner only — previously any Discord user could read `.env`, `config.json`, database files, and any other file in the bot's working directory
- [FIX] `permission` action now accurately describes the real access model (`file` and `permission` = bot owner only; all other actions = everyone) instead of incorrectly stating all actions are public

#### Fixes
- [FIX] Per-user cooldown (15 s) and global max concurrency (3) are now enforced via a manual `_user_cooldowns` dict and `_active_requests` counter — `@commands.cooldown` / `@commands.max_concurrency` are silently ignored by discord.py for pure `@app_commands.command` handlers and have been removed; both limits now fire before `interaction.response.defer()` so the response is immediate and ephemeral
- [FIX] AI responses that exceed Discord's 4096-character embed limit now show a visible truncation notice (`Response truncated — ask a more specific question`) instead of cutting off silently
- [FIX] Context strings sent to Gemini are now capped at 8,000 characters — large plugin lists or database schemas no longer risk exceeding model token limits
- [FIX] Import coupling removed — `PluginRegistry` and `FrameworkDiagnostics` are no longer imported at module level; GeminiService loads gracefully even if those cogs are disabled

#### Additions
- [ADD] 60-second in-memory TTL cache for repeated identical queries on `diagnose`, `plugins`, `slash`, `hooks`, and `automations` actions — cache hits are noted in the embed footer
- [ADD] Gemini model is now configurable via `GEMINI_MODEL` environment variable (default: `gemini-2.5-flash-lite`)

---

### `cogs/backup_restore.py` — Restore expanded to cover all captured data

Previously the backup captured forum channels, stage channels, emojis, stickers, and server settings but silently skipped all of them during restore. This update makes restore match what backup captures.

#### Backup (capture) changes
- [FIX] Emoji images are now downloaded and stored as base64 inside the backup JSON at capture time — CDN URLs alone are useless after an emoji is deleted
- [FIX] Sticker images are now downloaded and stored as base64 inside the backup JSON at capture time (also adds the missing `url` field to sticker entries)
- [FIX] Server icon and banner are now downloaded and stored as base64 (`icon_b64`, `banner_b64`) inside the guild info block — restoring an icon no longer depends on the CDN URL remaining valid
- [ADD] Added `_download_image_b64()` async helper used by capture for all image downloads

#### Restore changes
- [ADD] Forum channels: restored via `guild.create_forum()`, skips duplicates by name
- [ADD] Stage channels: restored via `guild.create_stage_channel()`, skips duplicates by name
- [ADD] Emojis: restored from embedded base64 image data via `guild.create_custom_emoji()` — managed emojis are skipped
- [ADD] Stickers: restored from embedded base64 image data via `guild.create_sticker()` — requires re-backup for entries captured before this update
- [ADD] Server settings: restores name, verification level, default notifications, explicit content filter, AFK channel/timeout, premium progress bar via `guild.edit()`
- [ADD] Server icon: restored from embedded base64 data via `guild.edit(icon=bytes)`

#### Discord UI (RestoreSelectView)
- [ADD] Three new toggle buttons: **Emojis**, **Stickers**, **Server Settings**
- [CHG] **Bot Settings** moved to row 1 alongside the new buttons
- [CHG] **Select All** now includes emojis, stickers, and server_settings in its selection set
- [CHG] **Confirm Restore** moved to its own row (row 3) for visual clarity

---

### `cogs/live_monitor.py` — Dashboard restore parity

- [ADD] `_execute_dashboard_restore()` updated with the same new restore blocks: forum channels, stage channels, emojis (base64), stickers (base64), server settings + icon (base64)
- [ADD] PHP backup/restore UI: added **Forum Channels** and **Stage Channels** restore component checkboxes (Emojis, Stickers, Server Settings were already present in the UI but non-functional on the backend)
- [CHG] Default restore components in `_process_backup_actions()` extended to include `emojis`, `stickers`, `server_settings`

