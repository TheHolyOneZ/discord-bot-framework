# 📋 Changelog

All notable changes to the **Zoryx Discord Bot Framework** are documented in this file.

---

## 🚀 v1.7.0.0 — Advanced Shard System & Backup/Restore

**Release Date:** 2026-02-18  
**Previous Version:** 1.6.1.0

---

### ✨ New Features

#### 📊 Shard Monitor Cog (`cogs/shard_monitor.py`) — v2.0.0 (V1 =  Private) 

A complete real-time shard health monitoring system with an interactive dashboard.

- **Interactive Dashboard** (`/shardmonitor`) with 4 button-navigated tabs:
  - 📊 **Overview** — Cluster-wide stats, per-shard summary, alert configuration
  - 🏥 **Health** — Full health report with critical/warning/healthy breakdown
  - 📡 **Latency** — Visual latency bars per shard with min/avg/max statistics
  - 📈 **Events** — Per-shard counters (messages, commands, connects, disconnects, errors)
  - 🔄 **Refresh** — Refresh active tab with latest data
- **5 Hybrid Commands** (all Bot Owner Only):
  - `/shardmonitor` — Interactive dashboard
  - `/sharddetails <id>` — Deep-dive metrics for a specific shard
  - `/shardhealth` — Quick health report across all shards
  - `/shardalerts [#channel] [threshold]` — Configure automatic health alerts
  - `/shardreset [shard_id]` — Reset metrics for one or all shards
- **Enhanced ShardMetrics Class:**
  - Latency history tracking (120 samples with rolling window)
  - Per-shard event counters (messages, commands, guild joins/leaves)
  - Uptime percentage calculation
  - Connection/disconnection/reconnection tracking with timestamps
  - Consecutive failure tracking with error details
- **Three-Tier Health Check System:**
  - 🟢 Healthy — All metrics within normal range
  - 🟡 Warning — Latency >1s, no activity for 5+ min, or 3+ consecutive failures
  - 🔴 Critical — Latency >2s, 5+ consecutive failures, or currently disconnected
- **Alert System:**
  - Configurable alert channel with persistent storage (`./data/shard_monitor/alert_config.json`)
  - Configurable failure threshold (1–20, default: 3)
  - Automatic alert embeds sent on unhealthy shard detection
- **Background Tasks:**
  - `collect_metrics` — Records shard latency every 30 seconds
  - `health_check` — Evaluates shard health every 60 seconds
  - `save_metrics` — Persists metrics to disk every 5 minutes
- **Event Listeners:**
  - `on_message` — Per-shard message counter
  - `on_command` — Per-shard command counter
  - `on_shard_connect` / `on_shard_disconnect` / `on_shard_resumed` / `on_shard_ready`
  - `on_guild_join` / `on_guild_remove`
- **`.env` Toggle:** `ENABLE_SHARD_MONITOR=true/false` (default: `true`)

#### 🌐 Shard Manager Cog (`cogs/shard_manager.py`) — v1.0.0

A new IPC (Inter-Process Communication) system for running shards across multiple processes or servers.

- **TCP-Based IPC Protocol:**
  - Length-prefixed messages (4-byte header + JSON payload)
  - 1MB max message size
  - Nonce-based deduplication to prevent duplicate processing
- **IPC Server Mode** (primary cluster):
  - Hosts TCP server, handles client authentication
  - Tracks connected clients with heartbeat monitoring
  - Routes messages between clusters
  - Broadcasts cluster join/leave notifications
- **IPC Client Mode** (secondary clusters):
  - Connects to primary cluster's IPC server
  - Automatic reconnection with exponential backoff (5s → 120s max)
  - Sends heartbeats every 30 seconds
- **Message Types:**
  - `auth` / `auth_response` — Shared secret authentication
  - `heartbeat` / `heartbeat_ack` — Keep-alive with guild count
  - `stats_broadcast` — Cluster statistics exchange (every 60s)
  - `cluster_join` / `cluster_leave` — Connection notifications
  - `broadcast_message` — Owner-initiated text broadcast
- **Security:**
  - Shared secret authentication (`SHARD_IPC_SECRET`)
  - 10-second auth timeout for unauthenticated connections
  - No arbitrary code execution — safe preset queries only
  - Warning logged when using default secret
- **3 Hybrid Commands** (all Bot Owner Only):
  - `/clusters` — Show all connected clusters with stats, health, and global totals
  - `/ipcstatus` — IPC system diagnostics (mode, host, port, clients, heartbeats)
  - `/broadcastmsg <message>` — Broadcast text to all connected clusters
- **Background Task:**
  - `sync_stats` — Broadcasts cluster statistics every 60 seconds
- **`.env` Toggle:** `ENABLE_SHARD_MANAGER=true/false` (default: `false`)

#### 💾 Backup & Restore System (`cogs/backup_restore.py`) — v2.1.0

A full guild configuration snapshot system for disaster recovery, server migrations, and auditing. Now with member role snapshots, selective restore, auto-backup scheduling, and a full audit trail.

- **Full Guild Snapshots** capturing:
  - Roles (name, color, hoist, mentionable, permissions value, position)
  - Categories (name, position, NSFW, permission overwrites with target/allow/deny)
  - Text channels (name, topic, slowmode, NSFW, category, full permission overwrites)
  - Voice channels (name, bitrate, user limit, RTC region, category, full permission overwrites)
  - Forum channels and Stage channels (safe fallback if discord.py version lacks support)
  - Emojis (name, animated, URL, managed status)
  - Stickers (name, description, emoji)
  - Server settings (verification level, notification level, content filter, AFK, system channel, locale, boost bar)
  - **Member role assignments** — saves which non-bot members have which roles (requires Members Intent)
  - Bot settings (custom prefix, mention prefix configuration)
- **Interactive Dashboard** (`/backup`) with **5 button-navigated tabs**:
  - 📊 **Overview** — Storage usage bar, latest backup, current guild stats, cooldown timer
  - 📦 **Backups** — Paginated list with metadata (roles, channels, member snapshots, author, size)
  - 🔍 **Compare** — Drift analysis: current state vs latest backup with change counts
  - 📜 **Audit Log** — Every backup operation tracked (create, delete, restore, pin, verify, export)
  - 📈 **Analytics** — Trends, top creators, backup frequency, member snapshot counts
  - 🔄 **Refresh** + ◀ ▶ **Pagination** on all paginated tabs
  - 🗑️ **Delete** — Quick-delete from dashboard via dropdown selector with pin protection
- **13 Hybrid Commands:**
  - `/backup` — Interactive dashboard with 5 tabs
  - `/backupcreate [label]` — Create a full guild snapshot
  - `/backuprestore <id>` — Selective restore with component toggles (roles, categories, channels, member roles, bot settings)
  - `/backupview <id>` — Detailed backup inspection
  - `/backupdelete <id>` — Delete with two-step confirmation (respects pin protection)
  - `/backuplist` — Paginated backup list
  - `/backuppin <id>` — Pin/unpin to protect from deletion and cleanup
  - `/backupnote <id> <text>` — Annotate backups with notes
  - `/backupverify <id>` — SHA-256 checksum integrity verification
  - `/backupschedule <action> [hours]` — Per-guild auto-backup schedule (enable/disable/status)
  - `/backupdiff <id_a> <id_b>` — Compare any two backups (added/removed roles, channels, members)
  - `/backupexport <id>` — Export as JSON (Bot Owner only)
  - `/backupstats` — Global backup statistics (Bot Owner only)
- **Selective Restore Engine:**
  - Toggle individual components: roles, categories, channels, member roles, bot settings
  - Creates only missing roles, categories, and channels (skips existing by name)
  - Recreates permission overwrites with old→new role ID mapping
  - **Reapplies member role assignments** — gives members back the roles they had at backup time
  - **Role Sync mode** (off by default) — when enabled, does a full rewind: adds missing roles AND removes roles that weren't in the backup, restoring each member's roles to the exact state at backup time
  - Guild chunking ensures all members are loaded before processing
  - Restores bot settings with cache invalidation
  - Real-time progress updates and detailed results report
  - Per-guild restore lock prevents concurrent operations
- **Audit Log System:**
  - Tracks all operations with user ID, backup ID, and details
  - Per-guild storage, keeps last 200 entries
- **Auto-Backup Scheduler:**
  - Per-guild configurable interval (1–168 hours)
  - Background loop checks hourly, auto-backups flagged with 🔁
  - Requires `BACKUP_AUTO_INTERVAL` > 0 in `.env`
- **Retention Cleanup:**
  - Auto-deletion of old unpinned backups past threshold
  - Pinned backups always protected
  - Configurable via `BACKUP_RETENTION_DAYS`
- **Timezone-Aware Timestamps:**
  - All timestamps stored as UTC-aware ISO 8601 (`+00:00`)
  - Discord `<t:epoch:R>` formatting shows correct relative time in every user's local timezone
  - Backward-compatible with legacy naive timestamps
- **Safety & Abuse Protection:**
  - 5-minute cooldown per guild (configurable, bot owner gets bypass notification instead of silent skip)
  - Max 25 backups per guild (configurable)
  - Two-step confirmation for restore and delete
  - Interaction author verification on all buttons — only the invoker can interact
  - SHA-256 checksums, pin protection, restore lock
- **Permission System:**
  - Bot Owner: Full access + export + global stats
  - Administrator: Guild-scoped access to all commands
  - Delete protection: non-admin users can only delete their own backups
- **`.env` Toggle:** `ENABLE_BACKUP_RESTORE=true/false` (default: `true`)`

---

### 🔧 Modified Files

#### `main.py`

4 patches applied to integrate the new cogs:

1. **Owner-Only Commands List** (line ~103):
   - Added 8 commands to `BOT_OWNER_ONLY_COMMANDS`:
     `shardmonitor`, `sharddetails`, `shardhealth`, `shardalerts`, `shardreset`, `clusters`, `ipcstatus`, `broadcastmsg`
   - Added `backupexport` and `backupstats` to owner-only list (backup export and global stats restricted to bot owner)
   - Ensures all shard and backup-export commands are restricted to `BOT_OWNER_ID`

2. **Cog Load Order** (line ~222):
   - Added `"shard_monitor"`, `"shard_manager"`, and `"backup_restore"` to the `load_order` list
   - All load after `framework_diagnostics` and before `EventHooksCreater`

3. **Graceful IPC Shutdown** (line ~519):
   - Added `shard_manager_cog._shutdown_ipc()` call in the `close()` method
   - Runs before database close to cleanly terminate TCP connections
   - Wrapped in try/except to prevent shutdown failures

4. **Enhanced `on_ready` Panel** (line ~606):
   - Now displays shard IDs in the startup Rich console panel
   - Shows Shard Monitor and Shard Manager enable/disable status
   - Example output:
     ```
     Shards: 2
     Shard IDs: 0, 1
     Shard Monitor: Enabled
     Shard Manager: Enabled
     Backup System: Enabled
     ```

#### `config.json`

- Added to `framework` section:
  ```json
  "enable_shard_monitor": true,
  "enable_shard_manager": true,
  "enable_backup_restore": true
  ```
- Both shard cogs respect `.env` toggles (`ENABLE_SHARD_MONITOR`, `ENABLE_SHARD_MANAGER`) which take precedence
- Backup system respects `.env` toggle (`ENABLE_BACKUP_RESTORE`) which takes precedence

#### `README.md`

Major update (+616 lines, 3998 → 4614):

- Updated header banner to v1.7.0.0
- Added Shard Monitor and Shard Manager to Table of Contents
- Added full feature descriptions in "Modular Framework Cogs" section
- Updated Core Features checklist
- Added both cogs + docs to Project Structure
- Added `.env.example` to Project Structure
- Added shard data directories to Project Structure
- Added complete Shard Monitor Commands table (5 commands + dashboard tabs + health thresholds)
- Added complete Shard Manager Commands table (3 commands)
- Updated Owner-Only Commands table (8 new entries)
- Updated Quick Start `.env` section with all shard variables
- Updated `config.json` documentation with new framework entries
- Updated Environment Variables section with full shard variable reference
- Added **📊 Shard Monitor System** section (architecture diagram, usage guide, alerts, testing)
- Added **🌐 Shard Manager System** section (architecture diagram, setup guides, IPC protocol, auto-reconnect)
- Added 8 new troubleshooting entries (4 monitor + 4 manager)
- Expanded Performance Tips → Sharding with multi-process examples

---

### 📄 New Files

| File | Size | Description |
|------|------|-------------|
| `cogs/shard_monitor.py` | ~38 KB | Shard health monitoring cog (v2.0.0) |
| `cogs/shard_manager.py` | ~33 KB | Multi-process IPC shard manager cog (v1.0.0) |
| `cogs/backup_restore.py` | ~42 KB | Backup & Restore system cog (v2.1.0) |
| `cogs/SHARD_MONITOR_DOCS.md` | ~5.5 KB | Shard Monitor documentation |
| `cogs/SHARD_MANAGER_DOCS.md` | ~9.5 KB | Shard Manager documentation |
| `.env.example` | ~3 KB | Complete environment variable reference template |
| `MAIN_PY_CHANGES.md` | ~4 KB | Detailed diff of main.py patches |
| `CHANGELOG.md` | — | This file |

---

### ⚙️ New Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_SHARD_MONITOR` | `true` | Enable/disable the Shard Monitor cog |
| `SHARD_ALERT_THRESHOLD` | `3` | Consecutive failures before alert fires (1–20) |
| `ENABLE_SHARD_MANAGER` | `false` | Enable/disable the Shard Manager cog |
| `SHARD_IPC_MODE` | `server` | IPC role: `server` (primary) or `client` (secondary) |
| `SHARD_IPC_HOST` | `127.0.0.1` | IPC bind address (`0.0.0.0` for remote) |
| `SHARD_IPC_PORT` | `20000` | IPC TCP port |
| `SHARD_IPC_SECRET` | `change_me_please` | Shared auth secret (MUST match all clusters) |
| `SHARD_CLUSTER_NAME` | `cluster-0` | Unique name for this cluster |
| `ENABLE_BACKUP_RESTORE` | `true` | Enable/disable the Backup & Restore cog |
| `BACKUP_MAX_PER_GUILD` | `25` | Maximum backup snapshots per guild (1–100) |
| `BACKUP_COOLDOWN` | `300` | Seconds between backup creations per guild |
| `BACKUP_AUTO_INTERVAL` | `0` | Hours between auto-backups (0 = disabled) |
| `BACKUP_RETENTION_DAYS` | `0` | Days to keep unpinned backups (0 = keep forever) |

---

### 🎮 New Commands (21 total)

| Command | Cog | Description | Permission |
|---------|-----|-------------|------------|
| `/shardmonitor` | Shard Monitor | Interactive dashboard with button navigation | Bot Owner |
| `/sharddetails <id>` | Shard Monitor | Detailed metrics for specific shard | Bot Owner |
| `/shardhealth` | Shard Monitor | Health report for all shards | Bot Owner |
| `/shardalerts [#ch] [n]` | Shard Monitor | Configure alert channel and threshold | Bot Owner |
| `/shardreset [id]` | Shard Monitor | Reset metrics (-1 for all) | Bot Owner |
| `/clusters` | Shard Manager | Show all connected clusters | Bot Owner |
| `/ipcstatus` | Shard Manager | IPC system diagnostics | Bot Owner |
| `/broadcastmsg <msg>` | Shard Manager | Broadcast to all clusters | Bot Owner |
| `/backup` | Backup & Restore | Interactive dashboard with 5 tabs and pagination | Administrator |
| `/backupcreate [label]` | Backup & Restore | Create full guild snapshot (roles, channels, members, settings) | Administrator |
| `/backuprestore <id>` | Backup & Restore | Selective restore with component toggles | Administrator |
| `/backupview <id>` | Backup & Restore | Detailed backup inspection | Administrator |
| `/backupdelete <id>` | Backup & Restore | Delete a backup with confirmation | Administrator |
| `/backuplist` | Backup & Restore | Paginated list of all backups | Administrator |
| `/backuppin <id>` | Backup & Restore | Pin/unpin backup (protect from deletion) | Administrator |
| `/backupnote <id> <text>` | Backup & Restore | Add note to a backup | Administrator |
| `/backupverify <id>` | Backup & Restore | Verify backup integrity via SHA-256 | Administrator |
| `/backupschedule <action>` | Backup & Restore | Configure auto-backup schedule | Administrator |
| `/backupdiff <id_a> <id_b>` | Backup & Restore | Compare two backups side by side | Administrator |
| `/backupexport <id>` | Backup & Restore | Export backup as JSON file | Bot Owner |
| `/backupstats` | Backup & Restore | Global backup statistics | Bot Owner |

---

### 🔄 Backward Compatibility

- **No breaking changes.** All new features are additive.
- Shard Monitor is enabled by default but harmless with 1 shard — it simply tracks shard 0.
- Shard Manager is disabled by default (`ENABLE_SHARD_MANAGER=false`).
- Backup & Restore is enabled by default; stores data in `./data/backups/`.
- Existing commands, extensions, and configuration are unaffected.
- If `.env` variables are missing, all cogs fall back to safe defaults.

---

### 📝 Notes

- Both shard cogs follow the existing framework pattern: owner-only permissions via `is_bot_owner()` decorator, hybrid commands, `.env` + `config.json` dual-toggle system.
- The Backup & Restore cog (v2.1.0) uses a dual-tier permission model: Bot Owner has full access, while server Administrators can manage backups for their own guild. Export and global stats are restricted to Bot Owner. Member role snapshots require the Members Gateway Intent — without it, member roles will be empty in backups.
- All backup timestamps are stored as UTC-aware ISO 8601 strings, ensuring Discord's `<t:epoch:R>` formatting displays correctly in every user's local timezone regardless of server location.
- The IPC protocol uses a simple length-prefixed TCP format. For production multi-server deployments, set a strong `SHARD_IPC_SECRET` and ensure the IPC port is firewalled appropriately.
- Discord requires sharding at 2,500 guilds. The Shard Manager is only needed when splitting shards across multiple processes (typically 5,000+ guilds or for high-availability setups).
- All shard and backup-export commands are added to the `BOT_OWNER_ONLY_COMMANDS` list in `main.py`, ensuring they cannot be used by anyone other than the bot owner regardless of Discord permissions.

---

### ❤️ Credits

Developed for the **Zoryx Discord Bot Framework** by **TheHolyOneZ**  

---

*Previous release: [v1.6.1.0 — @Mention Prefix & Per-Guild Configuration]*
