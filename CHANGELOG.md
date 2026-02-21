# What's New in Version 1.7.1.0

Two major systems that were previously only accessible through Discord commands are now fully integrated into the Live Monitor web dashboard: **Backup & Restore** and **Shard Management**. Everything you could do in Discord, you can now do from your browser — plus a few extras.

---

## Backup & Restore — Now in the Dashboard

The Backup & Restore tab gives you a complete overview of every server snapshot across all your guilds, with full management capabilities built right in.

### At a Glance

When you open the tab, you'll see global stats at the top — total backups, how many guilds have backups, total storage used, pinned count, cooldown timer, auto-backup interval, and retention policy. A storage utilization bar shows how much of your capacity is in use.

### Guild Sidebar

On the left, every guild with backups is listed with its backup count, total size, and schedule status. Click any guild to open its backup viewer.

### Backup Viewer

Once you select a guild, you'll see all its backups listed chronologically. Each entry shows the label, timestamp, role and channel counts, file size, and whether it was created manually or automatically. From here you can:

- **Create a new backup** directly from the dashboard with an optional custom label. The bot captures the full server snapshot — roles, channels, categories, emojis, stickers, member role assignments, and server settings — just like it would from a Discord command.
- **Delete a backup** you no longer need. Pinned backups are protected and must be unpinned first.
- **Restore a backup** using the restore modal, where you pick exactly which components to restore (roles, channels, categories, bot settings, member roles) and optionally enable full role sync mode.
- **Pin or unpin backups** with one click to protect important snapshots from automatic cleanup and deletion.
- **View full details** for any backup by expanding its detail panel, which shows everything — role count, category count, text/voice/forum/stage channel counts, emoji and sticker counts, member role assignments, total members at time of capture, file size, data integrity checksum, who created it, and any attached notes.

### Per-Guild Scheduling

Each guild has its own configuration panel where you can enable or disable automatic scheduled backups, set the interval in hours, and configure retention (how many days to keep old backups before they're automatically cleaned up). Changes are saved instantly and take effect on the next bot cycle.

### Restore Workflow

The restore process walks you through component selection, warns you about what will be affected, and shows a real-time log as the bot processes the operation. When it's done, you'll see a full results summary — how many items were created, skipped, or failed, how many members were processed, roles added or removed, duration, and any issues that came up. The button then changes to let you close the modal cleanly.

---

## Shard Manager — Now in the Dashboard

If your bot runs across multiple shards or IPC clusters, the new Shard Manager tab gives you real-time visibility into every shard's health and performance without needing to run commands in Discord.

### Overview

The top of the tab shows your total shard count, how many are healthy, how many have warnings, and your average latency across all shards. Below that, three info panels cover:

- **IPC Status** — your clustering mode, cluster name, and how many clients are connected to the IPC mesh.
- **Health Summary** — a breakdown of healthy, warning, and critical shards at a glance.
- **Global Totals** — total guilds, total users, and overall uptime across all shards.

### Health Bar

A visual health bar shows every shard as a colored block — green for healthy, yellow for warning, red for critical. Hover over any block to see that shard's ID, current latency, and the reason for its health status.

### Shard Detail Cards

Below the health bar, each shard gets its own detail card showing its current latency, guild count, health status and reason, connection/disconnection/reconnection history, error count, and event throughput. You can view detailed metrics and reset shard statistics from the dashboard.

### Cluster Map

If you're running multiple IPC clusters, the cluster map visualizes which shards belong to which cluster, their connection status, and how they're distributed across your infrastructure.

### Role-Based Access

Both tabs respect the dashboard's permission system. Server owners have full access by default, while custom roles can be granted granular permissions — separately controlling who can view backups, create them, delete them, restore them, edit scheduling configs, view shard details, or reset shard metrics.

---

## Summary of What's New

| Feature | Before 1.7.1.0 | Now |
|---|---|---|
| Create backups | Discord command only | Dashboard + Discord |
| Delete backups | Discord command only | Dashboard + Discord |
| Restore backups | Discord command only | Dashboard + Discord |
| Pin/unpin backups | Discord command only | Dashboard + Discord |
| View backup details | Discord command only | Dashboard + Discord |
| Configure backup schedules | Discord command only | Dashboard + Discord |
| Monitor shard health | Discord command only | Dashboard + Discord |
| View shard latency & metrics | Discord command only | Dashboard + Discord |
| Reset shard statistics | Discord command only | Dashboard + Discord |
| IPC cluster visualization | Not available | Dashboard |
| Visual shard health bar | Not available | Dashboard |
| Backup storage utilization | Not available | Dashboard |

All existing Discord commands continue to work exactly as before. The dashboard simply gives you an additional way to manage everything from your browser.