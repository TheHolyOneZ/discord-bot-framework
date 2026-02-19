# 📊 Shard Monitor — Documentation

> **Version:** 2.0.0  
> **Author:** TheHolyOneZ  
> **Location:** `cogs/shard_monitor.py`  
> **Permissions:** All commands are **Bot Owner Only** (`BOT_OWNER_ID` from `.env`)

---

## Overview

The Shard Monitor provides real-time visibility into your bot's shard health, latency, events, and reliability. It features an interactive dashboard with button navigation, automatic health alerts, persistent metrics, and detailed per-shard diagnostics.

---

## .env Configuration

| Variable | Default | Description |
|---|---|---|
| `ENABLE_SHARD_MONITOR` | `true` | Enable/disable the entire cog on startup |
| `SHARD_ALERT_THRESHOLD` | `3` | Consecutive failures before alert fires |
| `BOT_OWNER_ID` | *(required)* | Discord user ID — only this user can use commands |

### Example .env

```env
ENABLE_SHARD_MONITOR=true
SHARD_ALERT_THRESHOLD=3
BOT_OWNER_ID=123456789012345678
```

Set `ENABLE_SHARD_MONITOR=false` to completely disable the cog. The `setup()` function checks this before loading.

---

## config.json Integration

Add to the `framework` section of your `config.json`:

```json
"framework": {
    "enable_shard_monitor": true
}
```

The cog respects **both** the `.env` toggle AND the config.json toggle. The `.env` variable takes precedence (checked in `setup()`), while the `config.json` toggle is checked by the framework's `load_framework_cogs()` method.

---

## Commands

All commands are **hybrid** (work as both prefix and slash commands).

### `/shardmonitor`
**Interactive dashboard** with button navigation between four tabs:

| Tab | Description |
|---|---|
| 📊 Overview | Cluster stats, per-shard summary, alert config |
| 🏥 Health | Health report with healthy/warning/critical breakdown |
| 📡 Latency | Visual latency bars per shard, cluster latency stats |
| 📈 Events | Per-shard event counters (messages, commands, connects, errors) |
| 🔄 Refresh | Refresh the current tab with latest data |

**Cooldown:** 10 seconds per user

### `/sharddetails <shard_id>`
Deep-dive into a specific shard showing:
- Basic info (guilds, members, latency stats)
- Activity (messages, commands, guild joins/leaves)
- Reliability (uptime %, connects, disconnects, reconnects)
- Errors (total, consecutive failures, last error details)
- Connection history (last connect/disconnect timestamps)

**Cooldown:** 10 seconds per user

### `/shardhealth`
Quick health check report for all shards with:
- Overall status (Critical / Warning / Healthy)
- Summary counts
- Lists of problematic shards with reasons

**Cooldown:** 30 seconds per user

### `/shardalerts [channel] [threshold]`
Configure the automatic alert system:
- **channel:** Text channel to send alerts to (omit to disable)
- **threshold:** Number of consecutive failures before alerting (1-20)

Alert configuration persists to `./data/shard_monitor/alert_config.json`.

### `/shardreset [shard_id]`
Reset collected metrics:
- **shard_id:** Specific shard to reset, or `-1` to reset all shards

---

## Health Checks

The health check system runs every **60 seconds** and evaluates each shard on:

| Check | Threshold | Status |
|---|---|---|
| Average latency | > 1000ms | 🟡 Warning |
| Average latency | > 2000ms | 🔴 Critical |
| No activity | > 5 minutes | 🟡 Warning |
| Consecutive failures | ≥ 3 | 🟡 Warning |
| Consecutive failures | ≥ 5 | 🔴 Critical |
| Currently disconnected | — | 🔴 Critical |
| Recently disconnected | < 60 seconds ago | 🟡 Warning |

---

## Background Tasks

| Task | Interval | Description |
|---|---|---|
| `collect_metrics` | 30 seconds | Records latency from each shard |
| `health_check` | 1 minute | Evaluates health and sends alerts |
| `save_metrics` | 5 minutes | Persists metrics to `./data/shard_monitor/shard_metrics.json` |

---

## Event Listeners

The cog automatically tracks these Discord events per-shard:

| Event | Tracked Metric |
|---|---|
| `on_message` | Messages processed |
| `on_command` | Commands executed |
| `on_guild_join` | Guilds joined |
| `on_guild_remove` | Guilds left |
| `on_shard_connect` | Connection count |
| `on_shard_disconnect` | Disconnection count + downtime tracking |
| `on_shard_resumed` | Reconnection count |
| `on_shard_ready` | Shard ready events |

---

## Data Storage

```
./data/shard_monitor/
├── shard_metrics.json      # Periodic metrics snapshot
└── alert_config.json       # Alert channel & threshold config
```

---

## Permissions Summary

| Command | Who Can Use |
|---|---|
| `/shardmonitor` | Bot Owner only |
| `/sharddetails` | Bot Owner only |
| `/shardhealth` | Bot Owner only |
| `/shardalerts` | Bot Owner only |
| `/shardreset` | Bot Owner only |

**No commands are available to regular users or guild owners.** This is intentional — shard data is infrastructure-level information.

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Cog doesn't load | Check `ENABLE_SHARD_MONITOR=true` in `.env` and `enable_shard_monitor: true` in `config.json` |
| No metrics showing | Wait 30+ seconds for first collection cycle |
| Alerts not firing | Verify alert channel is set with `/shardalerts #channel` |
| "No activity" warnings | Normal on low-traffic bots — the 5-min threshold may trigger |
| Metrics reset on restart | Expected — metrics are in-memory with periodic disk snapshots |
