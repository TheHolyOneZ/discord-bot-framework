# 🌐 Shard Manager — Documentation

> **Version:** 1.0.0  
> **Author:** TheHolyOneZ  
> **Location:** `cogs/shard_manager.py`  
> **Permissions:** All commands are **Bot Owner Only** (`BOT_OWNER_ID` from `.env`)

---

## Overview

The Shard Manager enables **multi-process and multi-server sharding**. When your bot grows beyond what a single process can handle, you can split shards across multiple processes (or even machines). This cog provides the IPC (Inter-Process Communication) layer that lets those separate processes talk to each other.

### How It Works

```
┌──────────────────────────────────────────────────┐
│                   IPC Network                     │
│                                                   │
│  ┌─────────────┐    TCP/IP    ┌─────────────┐    │
│  │  Cluster 0   │◄──────────►│  Cluster 1   │    │
│  │  (Server)    │             │  (Client)    │    │
│  │  Shards 0-2  │             │  Shards 3-5  │    │
│  │  500 guilds  │             │  500 guilds  │    │
│  └─────────────┘             └─────────────┘    │
│         ▲                                         │
│         │           TCP/IP                        │
│         └──────────────────►┌─────────────┐      │
│                              │  Cluster 2   │     │
│                              │  (Client)    │     │
│                              │  Shards 6-8  │     │
│                              │  500 guilds  │     │
│                              └─────────────┘     │
└──────────────────────────────────────────────────┘
```

- **One cluster runs as `server`** — it hosts the IPC server that others connect to
- **Additional clusters run as `client`** — they connect to the server
- All clusters exchange stats, health data, and can broadcast messages

---

## .env Configuration

### Required Variables

| Variable | Default | Description |
|---|---|---|
| `ENABLE_SHARD_MANAGER` | `false` | Enable/disable the cog (**disabled by default**) |
| `SHARD_IPC_SECRET` | `change_me_please` | **Shared secret** for IPC authentication — MUST match on all clusters |
| `BOT_OWNER_ID` | *(required)* | Discord user ID for command access |

### IPC Variables

| Variable | Default | Description |
|---|---|---|
| `SHARD_IPC_HOST` | `127.0.0.1` | IPC server bind address (use `0.0.0.0` for multi-server) |
| `SHARD_IPC_PORT` | `20000` | IPC server port |
| `SHARD_IPC_MODE` | `server` | `server` for primary cluster, `client` for secondaries |
| `SHARD_CLUSTER_NAME` | `cluster-0` | Unique name to identify this cluster |

### Sharding Variables (Already in your framework)

| Variable | Default | Description |
|---|---|---|
| `SHARD_COUNT` | `1` | Total shard count across ALL clusters |
| `SHARD_IDS` | *(empty)* | Comma-separated shard IDs for THIS cluster |

---

## Setup Examples

### Single Server, Multiple Processes

For a bot with 6 shards split across 2 processes on the same machine:

**Process 1 (.env):**
```env
DISCORD_TOKEN=your_token
BOT_OWNER_ID=123456789
SHARD_COUNT=6
SHARD_IDS=0,1,2
ENABLE_SHARD_MANAGER=true
SHARD_IPC_MODE=server
SHARD_IPC_HOST=127.0.0.1
SHARD_IPC_PORT=20000
SHARD_IPC_SECRET=my_super_secret_key_123
SHARD_CLUSTER_NAME=cluster-0
```

**Process 2 (.env):**
```env
DISCORD_TOKEN=your_token
BOT_OWNER_ID=123456789
SHARD_COUNT=6
SHARD_IDS=3,4,5
ENABLE_SHARD_MANAGER=true
SHARD_IPC_MODE=client
SHARD_IPC_HOST=127.0.0.1
SHARD_IPC_PORT=20000
SHARD_IPC_SECRET=my_super_secret_key_123
SHARD_CLUSTER_NAME=cluster-1
```

### Multiple Servers (Different Machines)

Same concept, but change the IPC host:

**Server A (primary, .env):**
```env
SHARD_IPC_MODE=server
SHARD_IPC_HOST=0.0.0.0
SHARD_IPC_PORT=20000
SHARD_IPC_SECRET=very_long_random_secret_here
SHARD_CLUSTER_NAME=us-east-1
SHARD_COUNT=9
SHARD_IDS=0,1,2
```

**Server B (secondary, .env):**
```env
SHARD_IPC_MODE=client
SHARD_IPC_HOST=<Server_A_IP_Address>
SHARD_IPC_PORT=20000
SHARD_IPC_SECRET=very_long_random_secret_here
SHARD_CLUSTER_NAME=us-west-1
SHARD_COUNT=9
SHARD_IDS=3,4,5
```

**Server C (secondary, .env):**
```env
SHARD_IPC_MODE=client
SHARD_IPC_HOST=<Server_A_IP_Address>
SHARD_IPC_PORT=20000
SHARD_IPC_SECRET=very_long_random_secret_here
SHARD_CLUSTER_NAME=eu-central-1
SHARD_COUNT=9
SHARD_IDS=6,7,8
```

> ⚠️ **Important:** The `SHARD_IPC_SECRET` must be identical on ALL clusters. The server must bind to `0.0.0.0` (not `127.0.0.1`) for remote connections. Ensure the port is open in your firewall.

---

## config.json Integration

Add to the `framework` section:

```json
"framework": {
    "enable_shard_manager": true
}
```

Both `.env` (`ENABLE_SHARD_MANAGER`) and `config.json` toggles are respected. The `.env` takes precedence.

---

## Commands

All commands are **hybrid** (prefix + slash) and **Bot Owner Only**.

### `/clusters`
Shows all connected clusters with:
- Per-cluster stats (guilds, users, shards, latency, uptime)
- Connection health indicators (🟢🟡🔴)
- Global totals across all clusters
- IPC server/client status

**Cooldown:** 10 seconds

### `/ipcstatus`
Technical IPC diagnostics:
- Configuration (mode, host, port, secret masked)
- Server: connected clients with heartbeat times
- Client: connection status

**Cooldown:** 10 seconds

### `/broadcastmsg <message>`
Send a text message to all connected clusters via IPC. Useful for coordination or announcements between cluster operators.

**Max length:** 500 characters

---

## IPC Protocol

The IPC system uses a **length-prefixed TCP protocol**:

```
┌────────────┬──────────────────────────┐
│ 4 bytes    │ N bytes                  │
│ (uint32 BE)│ (JSON payload)           │
│ = N        │                          │
└────────────┴──────────────────────────┘
```

### Message Types

| Operation | Direction | Description |
|---|---|---|
| `auth` | Client → Server | Authentication with secret + cluster info |
| `auth_response` | Server → Client | Success/failure response |
| `heartbeat` | Client → Server | Keep-alive with guild count |
| `heartbeat_ack` | Server → Client | Heartbeat acknowledgement |
| `stats_broadcast` | Bidirectional | Cluster statistics update |
| `stats_request` | Bidirectional | Request stats from specific cluster |
| `guild_count_request` | Bidirectional | Request guild/user counts |
| `cluster_join` | Server → Clients | New cluster connected notification |
| `cluster_leave` | Server → Clients | Cluster disconnected notification |
| `broadcast_message` | Bidirectional | Text message broadcast |
| `eval_request` | Bidirectional | Safe preset query (guild_count, latency, etc.) |

### Security

- **Authentication:** Every connection must authenticate with the shared secret
- **Message size limit:** 1MB max per message
- **Nonce deduplication:** Prevents message replay
- **No eval:** The `eval_request` handler only supports preset safe queries — no arbitrary code execution
- **Timeout:** Unauthenticated connections are closed after 10 seconds

---

## Auto-Reconnection

The IPC client has built-in reconnection with exponential backoff:

| Attempt | Delay |
|---|---|
| 1st | 5 seconds |
| 2nd | 10 seconds |
| 3rd | 20 seconds |
| 4th | 40 seconds |
| ... | up to 120 seconds max |

On successful reconnection, the delay resets to 5 seconds.

---

## Data Storage

```
./data/shard_manager/
└── (reserved for future cluster state persistence)
```

Currently, cluster state is maintained in-memory and synchronized via IPC.

---

## Permissions Summary

| Command | Who Can Use |
|---|---|
| `/clusters` | Bot Owner only |
| `/ipcstatus` | Bot Owner only |
| `/broadcastmsg` | Bot Owner only |

**No commands are available to regular users.** Shard management is infrastructure-level.

---

## When Do You Need This?

| Scenario | Need Shard Manager? |
|---|---|
| < 2,500 guilds | ❌ No — single process is fine |
| 2,500 - 5,000 guilds | Maybe — if you experience performance issues |
| 5,000+ guilds | ✅ Yes — split across processes |
| Multiple servers/VPS | ✅ Yes — essential for coordination |
| Just want monitoring | ❌ No — use Shard Monitor instead |

Discord **requires** sharding at 2,500 guilds and **recommends** it earlier for larger guilds.

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Cog doesn't load | Check `ENABLE_SHARD_MANAGER=true` in `.env` |
| "Auth failed" | Verify `SHARD_IPC_SECRET` matches on all clusters |
| Can't connect | Check host/port, firewall rules, and that server cluster is running first |
| "Using default secret" warning | Set a proper `SHARD_IPC_SECRET` in `.env` |
| Cluster shows 🔴 | Heartbeat timeout — check if that process is still running |
| Stats show 0 guilds | Wait 60 seconds for first stats sync cycle |
| Port already in use | Change `SHARD_IPC_PORT` or check for conflicting processes |
