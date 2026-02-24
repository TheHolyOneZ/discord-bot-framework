"""
# ===================================================================================
#
#   Copyright (c) 2026 TheHolyOneZ
#
#   This script is part of the ZDBF (Zoryx Discord Bot Framework).
#   This file is considered source-available and is not open-source.
#
#   You are granted permission to:
#   - View, read, and learn from this source code.
#   - Use this script 'as is' within the ZDBF.
#   - Run this script in multiple instances of your own ZDBF-based projects,
#     provided the license and script remain intact.
#
#   You are strictly prohibited from:
#   - Copying and pasting more than four (4) consecutive lines of this code
#     into other projects without explicit permission.
#   - Redistributing this script or any part of it. The only official source
#     is the GitHub repository: https://github.com/TheHolyOneZ/discord-bot-framework
#   - Modifying this license text.
#   - Removing any attribution or mention of the original author (TheHolyOneZ)
#     or the project names (ZDBF, TheZ).
#
#   This script is intended for use ONLY within the ZDBF ecosystem.
#   Use in any other framework is a direct violation of this license.
#
#   For issues, support, or feedback, please create an issue on the official
#   GitHub repository or contact the author through the official Discord server.
#
#   This software is provided "as is", without warranty of any kind, express or
#   implied, including but not limited to the warranties of merchantability,
#   fitness for a particular purpose and noninfringement. In no event shall the
#   authors or copyright holders be liable for any claim, damages or other
#   liability, whether in an action of contract, tort or otherwise, arising from,
#   out of or in connection with the software or the use or other dealings in the
#   software.
#
# ===================================================================================
"""
# Backup & Restore System - v2.1.0 | Created by TheHolyOneZ
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import os
import io
import json
import time
import asyncio
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple, Set
from pathlib import Path
from collections import defaultdict
import traceback

logger = logging.getLogger('discord')

BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", 0))
MAX_BACKUPS_PER_GUILD = int(os.getenv("BACKUP_MAX_PER_GUILD", 25))
BACKUP_COOLDOWN_SECONDS = int(os.getenv("BACKUP_COOLDOWN", 300))
BACKUP_DATA_DIR = "./data/backups"
AUTO_BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_AUTO_INTERVAL", 0))
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", 0))

_UTC = timezone.utc


def _utcnow():
    return datetime.now(tz=_UTC)


def is_bot_owner():
    async def predicate(ctx):
        if ctx.author.id != BOT_OWNER_ID:
            raise commands.CheckFailure("This command is restricted to the bot owner only.")
        return True
    return commands.check(predicate)


def is_backup_authorized():
    async def predicate(ctx):
        if ctx.author.id == BOT_OWNER_ID:
            return True
        if not ctx.guild:
            raise commands.CheckFailure("This command can only be used in a server.")
        if ctx.author.guild_permissions.administrator:
            return True
        raise commands.CheckFailure("You need **Administrator** permission or be the bot owner to use backup commands.")
    return commands.check(predicate)


VERIFICATION_NAMES = {0: "None", 1: "Low", 2: "Medium", 3: "High", 4: "Highest"}


def _safe_channels(guild, attr):
    return list(getattr(guild, attr, None) or [])


def _capture_overwrites(channel):
    result = []
    for target, ow in channel.overwrites.items():
        allow, deny = ow.pair()
        result.append({
            "target_id": target.id,
            "target_type": "role" if isinstance(target, discord.Role) else "member",
            "allow": allow.value,
            "deny": deny.value,
        })
    return result


def _ts(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_UTC)
        epoch = int(dt.timestamp())
        return f"<t:{epoch}:f>", f"<t:{epoch}:R>"
    except Exception:
        return iso_str, ""


def _bar(cur, mx, length=20):
    filled = int((cur / mx) * length) if mx > 0 else 0
    return "\u2588" * filled + "\u2591" * (length - filled)


def _delta(cur, bk):
    d = cur - bk
    if d > 0:
        return f"+{d}"
    if d < 0:
        return str(d)
    return "0"


def _sz(b):
    if b < 1024:
        return f"{b} B"
    if b < 1048576:
        return f"{b/1024:.1f} KB"
    return f"{b/1048576:.2f} MB"


def _tch(entry):
    return sum(entry.get(k, 0) for k in ("text_channels_count", "voice_channels_count", "forum_channels_count", "stage_channels_count"))


class BackupSnapshot:

    @staticmethod
    def gen_id():
        return uuid.uuid4().hex[:12]

    @staticmethod
    def checksum(data):
        raw = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def calc_size(data):
        return len(json.dumps(data, default=str).encode("utf-8"))

    @staticmethod
    async def capture(guild: discord.Guild, bot, components=None):
        if components is None:
            components = {"roles", "channels", "categories", "emojis", "stickers", "server_settings", "bot_settings", "member_roles"}

        snap = {
            "version": "2.1.0",
            "captured_at": _utcnow().isoformat(),
            "guild": {
                "id": guild.id,
                "name": guild.name,
                "icon_url": str(guild.icon.url) if guild.icon else None,
                "banner_url": str(guild.banner.url) if guild.banner else None,
                "member_count": guild.member_count,
                "owner_id": guild.owner_id,
                "created_at": guild.created_at.isoformat(),
                "premium_tier": guild.premium_tier,
                "premium_subscription_count": guild.premium_subscription_count,
            },
            "roles": [],
            "categories": [],
            "text_channels": [],
            "voice_channels": [],
            "forum_channels": [],
            "stage_channels": [],
            "emojis": [],
            "stickers": [],
            "member_roles": [],
            "server_settings": {},
            "bot_settings": {},
        }

        if "server_settings" in components:
            snap["server_settings"] = {
                "verification_level": guild.verification_level.value,
                "default_notifications": guild.default_notifications.value,
                "explicit_content_filter": guild.explicit_content_filter.value,
                "afk_timeout": guild.afk_timeout,
                "afk_channel_id": guild.afk_channel.id if guild.afk_channel else None,
                "system_channel_id": guild.system_channel.id if guild.system_channel else None,
                "rules_channel_id": guild.rules_channel.id if guild.rules_channel else None,
                "public_updates_channel_id": guild.public_updates_channel.id if guild.public_updates_channel else None,
                "preferred_locale": str(guild.preferred_locale),
                "premium_progress_bar_enabled": guild.premium_progress_bar_enabled,
            }

        if "roles" in components:
            for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
                if role.is_default() or role.managed:
                    continue
                snap["roles"].append({
                    "id": role.id,
                    "name": role.name,
                    "color": role.color.value,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable,
                    "permissions_value": role.permissions.value,
                    "position": role.position,
                })

        if "categories" in components:
            for cat in guild.categories:
                snap["categories"].append({
                    "id": cat.id,
                    "name": cat.name,
                    "position": cat.position,
                    "nsfw": getattr(cat, "nsfw", False),
                    "overwrites": _capture_overwrites(cat),
                })

        if "channels" in components:
            for ch in guild.text_channels:
                snap["text_channels"].append({
                    "id": ch.id, "name": ch.name, "topic": ch.topic,
                    "slowmode_delay": ch.slowmode_delay, "nsfw": ch.nsfw,
                    "position": ch.position, "category_id": ch.category_id,
                    "default_auto_archive_duration": getattr(ch, "default_auto_archive_duration", None),
                    "overwrites": _capture_overwrites(ch),
                })
            for ch in guild.voice_channels:
                snap["voice_channels"].append({
                    "id": ch.id, "name": ch.name, "bitrate": ch.bitrate,
                    "user_limit": ch.user_limit, "position": ch.position,
                    "category_id": ch.category_id,
                    "rtc_region": str(ch.rtc_region) if ch.rtc_region else None,
                    "overwrites": _capture_overwrites(ch),
                })
            for ch in _safe_channels(guild, "forum_channels"):
                snap["forum_channels"].append({
                    "id": ch.id, "name": ch.name,
                    "topic": getattr(ch, "topic", None),
                    "nsfw": getattr(ch, "nsfw", False),
                    "slowmode_delay": getattr(ch, "slowmode_delay", 0),
                    "position": ch.position, "category_id": ch.category_id,
                    "overwrites": _capture_overwrites(ch),
                })
            for ch in _safe_channels(guild, "stage_channels"):
                snap["stage_channels"].append({
                    "id": ch.id, "name": ch.name,
                    "topic": getattr(ch, "topic", None),
                    "position": ch.position, "category_id": ch.category_id,
                    "overwrites": _capture_overwrites(ch),
                })

        if "emojis" in components:
            for e in guild.emojis:
                snap["emojis"].append({
                    "id": e.id, "name": e.name, "animated": e.animated,
                    "url": str(e.url), "managed": e.managed,
                })

        if "stickers" in components:
            for s in getattr(guild, "stickers", None) or []:
                snap["stickers"].append({
                    "id": s.id, "name": s.name,
                    "description": getattr(s, "description", None),
                    "emoji": getattr(s, "emoji", None),
                })

        if "member_roles" in components:
            try:
                if not guild.chunked:
                    await guild.chunk(cache=True)
                trackable = {
                    r.id for r in guild.roles
                    if not r.is_default() and not r.managed
                }
                for member in guild.members:
                    if member.bot:
                        continue
                    member_role_ids = [
                        r.id for r in member.roles
                        if r.id in trackable
                    ]
                    member_role_names = [
                        r.name for r in member.roles
                        if r.id in trackable
                    ]
                    if member_role_ids:
                        snap["member_roles"].append({
                            "user_id": member.id,
                            "username": str(member),
                            "role_ids": member_role_ids,
                            "role_names": member_role_names,
                        })
            except Exception as e:
                logger.warning(f"BackupRestore: Member roles capture failed for {guild.id}: {e}")

        if "bot_settings" in components:
            try:
                if hasattr(bot, "db") and bot.db:
                    snap["bot_settings"] = {
                        "custom_prefix": await bot.db.get_guild_prefix(guild.id),
                        "mention_prefix_enabled": await bot.db.get_guild_mention_prefix_enabled(guild.id),
                    }
            except Exception as e:
                logger.warning(f"BackupRestore: Bot settings capture failed for {guild.id}: {e}")

        return snap


class BackupStorage:

    def __init__(self, file_handler=None):
        self.base_dir = Path(BACKUP_DATA_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.fh = file_handler
        self._cooldowns: Dict[int, float] = {}
        self._audit_lock = asyncio.Lock()

    def _gdir(self, gid):
        d = self.base_dir / str(gid)
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def _rj(self, path, default=None):
        if self.fh:
            data = await self.fh.atomic_read_json(path, use_cache=False)
            return data if data is not None else (default if default is not None else [])
        p = Path(path)
        if not p.exists():
            return default if default is not None else []
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default if default is not None else []

    async def _wj(self, path, data):
        if self.fh:
            return await self.fh.atomic_write_json(path, data)
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            return True
        except Exception:
            return False

    async def _ridx(self, gid):
        return await self._rj(str(self._gdir(gid) / "index.json"), [])

    async def _widx(self, gid, idx):
        return await self._wj(str(self._gdir(gid) / "index.json"), idx)

    def check_cd(self, gid):
        elapsed = time.time() - self._cooldowns.get(gid, 0)
        if elapsed < BACKUP_COOLDOWN_SECONDS:
            return int(BACKUP_COOLDOWN_SECONDS - elapsed)
        return None

    def set_cd(self, gid):
        self._cooldowns[gid] = time.time()

    async def audit(self, gid, action, uid, bid=None, details=""):
        async with self._audit_lock:
            log = await self._rj(str(self._gdir(gid) / "audit_log.json"), [])
            log.insert(0, {"timestamp": _utcnow().isoformat(), "action": action, "user_id": uid, "backup_id": bid, "details": details})
            await self._wj(str(self._gdir(gid) / "audit_log.json"), log[:200])

    async def get_audit(self, gid, limit=50):
        return (await self._rj(str(self._gdir(gid) / "audit_log.json"), []))[:limit]

    async def save(self, gid, snap, label, uid, pinned=False):
        idx = await self._ridx(gid)
        if len(idx) >= MAX_BACKUPS_PER_GUILD:
            return None

        bid = BackupSnapshot.gen_id()
        chk = BackupSnapshot.checksum(snap)
        sz = BackupSnapshot.calc_size(snap)

        entry = {
            "id": bid, "label": label, "timestamp": _utcnow().isoformat(),
            "author_id": uid, "checksum": chk, "size_bytes": sz,
            "pinned": pinned, "notes": "", "version": snap.get("version", "2.1.0"),
            "auto_backup": False,
            "roles_count": len(snap.get("roles", [])),
            "categories_count": len(snap.get("categories", [])),
            "text_channels_count": len(snap.get("text_channels", [])),
            "voice_channels_count": len(snap.get("voice_channels", [])),
            "forum_channels_count": len(snap.get("forum_channels", [])),
            "stage_channels_count": len(snap.get("stage_channels", [])),
            "emojis_count": len(snap.get("emojis", [])),
            "stickers_count": len(snap.get("stickers", [])),
            "member_roles_count": len(snap.get("member_roles", [])),
            "guild_name": snap.get("guild", {}).get("name", "Unknown"),
            "member_count": snap.get("guild", {}).get("member_count", 0),
        }

        ok = await self._wj(str(self._gdir(gid) / f"{bid}.json"), snap)
        if not ok:
            return None

        idx.insert(0, entry)
        await self._widx(gid, idx)
        await self.audit(gid, "create", uid, bid, f"Label: {label}")
        return entry

    async def get_list(self, gid):
        return await self._ridx(gid)

    async def get_snap(self, gid, bid):
        return await self._rj(str(self._gdir(gid) / f"{bid}.json"), None)

    async def delete(self, gid, bid, uid):
        idx = await self._ridx(gid)
        target = next((e for e in idx if e["id"] == bid), None)
        if not target:
            return False
        if target.get("pinned"):
            return False
        new_idx = [e for e in idx if e["id"] != bid]
        try:
            p = self._gdir(gid) / f"{bid}.json"
            if p.exists():
                p.unlink()
            if self.fh:
                self.fh.invalidate_cache(str(p))
        except Exception:
            pass
        await self._widx(gid, new_idx)
        await self.audit(gid, "delete", uid, bid, f"Label: {target.get('label', '')}")
        return True

    async def get_entry(self, gid, bid):
        return next((e for e in await self._ridx(gid) if e["id"] == bid), None)

    async def update_entry(self, gid, bid, updates):
        idx = await self._ridx(gid)
        for e in idx:
            if e["id"] == bid:
                e.update(updates)
                return await self._widx(gid, idx)
        return False

    async def toggle_pin(self, gid, bid, uid):
        idx = await self._ridx(gid)
        for e in idx:
            if e["id"] == bid:
                new = not e.get("pinned", False)
                e["pinned"] = new
                await self._widx(gid, idx)
                await self.audit(gid, "pin" if new else "unpin", uid, bid)
                return new
        return None

    async def verify(self, gid, bid):
        entry = await self.get_entry(gid, bid)
        if not entry:
            return False, "Entry not found"
        snap = await self.get_snap(gid, bid)
        if not snap:
            return False, "Snapshot file missing or corrupt"
        cur = BackupSnapshot.checksum(snap)
        stored = entry.get("checksum", "")
        if cur != stored:
            return False, f"Checksum mismatch: expected {stored}, got {cur}"
        return True, f"Verified \u2014 checksum {cur}"

    async def cleanup_old(self, gid, days):
        if days <= 0:
            return 0
        idx = await self._ridx(gid)
        cutoff = _utcnow() - timedelta(days=days)
        removed = 0
        new_idx = []
        for e in idx:
            if e.get("pinned"):
                new_idx.append(e)
                continue
            try:
                ts = datetime.fromisoformat(e["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=_UTC)
                if ts < cutoff:
                    try:
                        (self._gdir(gid) / f"{e['id']}.json").unlink(missing_ok=True)
                    except Exception:
                        pass
                    removed += 1
                    continue
            except Exception:
                pass
            new_idx.append(e)
        if removed:
            await self._widx(gid, new_idx)
        return removed

    async def get_schedule(self, gid):
        return await self._rj(str(self._gdir(gid) / "schedule.json"), None)

    async def set_schedule(self, gid, data):
        return await self._wj(str(self._gdir(gid) / "schedule.json"), data)

    async def global_stats(self):
        total = guilds = size = pinned = 0
        for d in self.base_dir.iterdir():
            if not d.is_dir():
                continue
            guilds += 1
            idx = await self._rj(str(d / "index.json"), [])
            total += len(idx)
            for e in idx:
                size += e.get("size_bytes", 0)
                if e.get("pinned"):
                    pinned += 1
        return {"total": total, "guilds": guilds, "size": size, "pinned": pinned}


class DashboardView(discord.ui.View):

    def __init__(self, cog, author, guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.author = author
        self.guild = guild
        self.tab = "overview"
        self.page = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("\u274c Only the person who ran this command can use these buttons.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True

    def _overview(self, bks):
        g = self.guild
        total = len(bks)
        pins = sum(1 for b in bks if b.get("pinned"))
        tsz = sum(b.get("size_bytes", 0) for b in bks)
        e = discord.Embed(
            title="\U0001f4be Backup & Restore \u2014 Dashboard",
            description=f"Managing snapshots for **{g.name}**\nEverything your server is \u2014 roles, channels, permissions, member roles \u2014 captured in a single click.",
            color=0x5865f2, timestamp=discord.utils.utcnow()
        )
        e.add_field(name="\U0001f4ca Storage", value=f"```\n{_bar(total, MAX_BACKUPS_PER_GUILD)} {total}/{MAX_BACKUPS_PER_GUILD}\nRemaining: {MAX_BACKUPS_PER_GUILD - total}  Pinned: {pins} \U0001f4cc\nSize: {_sz(tsz)}\n```", inline=False)
        if bks:
            b = bks[0]
            _, rel = _ts(b.get("timestamp", ""))
            pin = " \U0001f4cc" if b.get("pinned") else ""
            e.add_field(name=f"\U0001f551 Latest Snapshot{pin}", value=f"```\nID:    {b['id']}\nLabel: {b.get('label', '-')[:40]}\n```\nCreated {rel}", inline=True)
        else:
            e.add_field(name="\U0001f551 No Snapshots Yet", value="Your server has no backups.\nRun `/backupcreate` to take your first snapshot.", inline=True)
        forum_count = len(_safe_channels(g, "forum_channels"))
        stage_count = len(_safe_channels(g, "stage_channels"))
        e.add_field(name="\U0001f4cb Current Server State", value=f"```\nRoles:      {len(g.roles)-1}\nCategories: {len(g.categories)}\nText Ch:    {len(g.text_channels)}\nVoice Ch:   {len(g.voice_channels)}\nForum Ch:   {forum_count}\nStage Ch:   {stage_count}\nEmojis:     {len(g.emojis)}\nMembers:    {g.member_count}\nBoost Tier: {g.premium_tier}\n```", inline=True)
        cd = self.cog.storage.check_cd(g.id)
        if cd:
            e.add_field(name="\u23f3 Cooldown", value=f"Next backup available {f'<t:{int(time.time()) + cd}:R>'}", inline=False)
        e.set_footer(text=f"Guild: {g.id} \u2022 Backup System v2.1.0")
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        return e

    def _list(self, bks):
        pp = 5
        tp = max(1, (len(bks) + pp - 1) // pp)
        self.page = max(0, min(self.page, tp - 1))
        items = bks[self.page * pp:(self.page + 1) * pp]
        e = discord.Embed(
            title="\U0001f4e6 All Backups",
            description=f"**{self.guild.name}** \u2014 {len(bks)} snapshot(s) \u2022 Page {self.page+1}/{tp}",
            color=0x5865f2, timestamp=discord.utils.utcnow()
        )
        if not items:
            e.add_field(name="Nothing here yet", value="Run `/backupcreate` to take your first snapshot.", inline=False)
        for b in items:
            _, rel = _ts(b.get("timestamp", ""))
            pin = "\U0001f4cc " if b.get("pinned") else ""
            auto = "\U0001f501 " if b.get("auto_backup") else ""
            mr = b.get("member_roles_count", 0)
            mr_str = f" M:{mr}" if mr else ""
            e.add_field(
                name=f"{pin}{auto}`{b['id']}` \u2014 {b.get('label', '-')[:42]}",
                value=f"Created {rel} by <@{b.get('author_id', 0)}>\n```R:{b.get('roles_count',0)} C:{b.get('categories_count',0)} Ch:{_tch(b)} E:{b.get('emojis_count',0)}{mr_str} [{_sz(b.get('size_bytes',0))}]```",
                inline=False
            )
        e.set_footer(text="\U0001f4cc=Pinned  \U0001f501=Auto  M=Member Role Snapshots \u2022 /backupview <id>")
        return e

    def _compare(self, bks):
        g = self.guild
        cur = {"Roles": len(g.roles)-1, "Categories": len(g.categories), "Text Ch": len(g.text_channels), "Voice Ch": len(g.voice_channels), "Emojis": len(g.emojis)}
        e = discord.Embed(title="\U0001f50d Drift Analysis", description=f"How much has **{g.name}** changed since the last backup?", color=0x5865f2, timestamp=discord.utils.utcnow())
        if bks:
            b = bks[0]
            bk = {"Roles": b.get("roles_count",0), "Categories": b.get("categories_count",0), "Text Ch": b.get("text_channels_count",0), "Voice Ch": b.get("voice_channels_count",0), "Emojis": b.get("emojis_count",0)}
            drift = sum(abs(cur[k]-bk[k]) for k in cur)
            lvl = "\U0001f7e2 Minimal" if drift < 3 else "\U0001f7e1 Moderate" if drift < 10 else "\U0001f534 Significant"
            lines = [f"{'Item':<14} {'Now':>6} {'Backup':>6} {'Delta':>6}", "\u2500"*34]
            for k in cur:
                lines.append(f"{k:<14} {cur[k]:>6} {bk[k]:>6} {_delta(cur[k], bk[k]):>6}")
            e.add_field(name=f"\U0001f4ca Drift: {lvl}", value=f"```\n"+"\n".join(lines)+"\n```", inline=False)
            _, rel = _ts(b.get("timestamp", ""))
            e.add_field(name="Snapshot Age", value=rel, inline=True)
            e.add_field(name="Backup ID", value=f"`{b['id']}`", inline=True)
            e.add_field(name="Total Drift", value=f"**{drift}** items", inline=True)
            if drift >= 10:
                e.add_field(name="\U0001f4a1 Recommendation", value="Significant drift detected. Consider creating a new backup to capture the current state.", inline=False)
        else:
            e.add_field(name="No backups to compare against", value="Run `/backupcreate` to establish a baseline.", inline=False)
        return e

    def _audit(self, log):
        pp = 8
        tp = max(1, (len(log) + pp - 1) // pp)
        self.page = max(0, min(self.page, tp - 1))
        items = log[self.page * pp:(self.page + 1) * pp]
        e = discord.Embed(title="\U0001f4dc Audit Log", description=f"**{self.guild.name}** \u2014 {len(log)} entries \u2022 Page {self.page+1}/{tp}", color=0x5865f2, timestamp=discord.utils.utcnow())
        icons = {"create": "\U0001f4be", "delete": "\U0001f5d1\ufe0f", "restore": "\U0001f504", "pin": "\U0001f4cc", "unpin": "\U0001f4cc", "export": "\U0001f4e4", "verify": "\U0001f50d", "note": "\U0001f4dd", "auto_create": "\U0001f501", "schedule": "\u23f0", "cleanup": "\U0001f9f9"}
        if not items:
            e.add_field(name="No activity yet", value="Actions like creating, restoring, and deleting backups will appear here.", inline=False)
        else:
            lines = []
            for a in items:
                _, rel = _ts(a.get("timestamp", ""))
                icon = icons.get(a.get("action", ""), "\u2753")
                bid = f"`{a['backup_id']}`" if a.get("backup_id") else "\u2014"
                lines.append(f"{icon} **{a.get('action','?').upper()}** {bid} \u2022 <@{a.get('user_id',0)}> {rel}")
                if a.get("details"):
                    lines.append(f"  _{a['details'][:70]}_")
            e.description += "\n\n" + "\n".join(lines)
        e.set_footer(text="Every backup operation is tracked \u2022 Keeps last 200 entries")
        return e

    def _stats(self, bks):
        e = discord.Embed(title="\U0001f4c8 Analytics", description=f"Backup patterns for **{self.guild.name}**", color=0x5865f2, timestamp=discord.utils.utcnow())
        if not bks:
            e.add_field(name="No data yet", value="Create backups to see analytics here.")
            return e
        total = len(bks)
        pins = sum(1 for b in bks if b.get("pinned"))
        autos = sum(1 for b in bks if b.get("auto_backup"))
        tsz = sum(b.get("size_bytes", 0) for b in bks)
        total_members_saved = sum(b.get("member_roles_count", 0) for b in bks)
        e.add_field(name="\U0001f4ca Overview", value=f"```\nTotal:    {total}\nManual:   {total-autos}\nAuto:     {autos}\nPinned:   {pins}\nSize:     {_sz(tsz)}\nAvg Size: {_sz(tsz//total if total else 0)}\nMember Snapshots: {total_members_saved}\n```", inline=True)
        authors = defaultdict(int)
        for b in bks:
            authors[b.get("author_id", 0)] += 1
        top = sorted(authors.items(), key=lambda x: x[1], reverse=True)[:5]
        e.add_field(name="\U0001f465 Top Creators", value="\n".join(f"<@{u}>: **{c}** backups" for u, c in top) or "None", inline=True)
        if len(bks) >= 2:
            rd = bks[0].get("roles_count",0) - bks[-1].get("roles_count",0)
            cd = (bks[0].get("text_channels_count",0)+bks[0].get("voice_channels_count",0)) - (bks[-1].get("text_channels_count",0)+bks[-1].get("voice_channels_count",0))
            e.add_field(name="\U0001f4c9 Trends (Oldest \u2192 Latest)", value=f"```\nRoles:    {'+' if rd>=0 else ''}{rd}\nChannels: {'+' if cd>=0 else ''}{cd}\n```", inline=False)
        try:
            first = datetime.fromisoformat(bks[-1]["timestamp"])
            last = datetime.fromisoformat(bks[0]["timestamp"])
            if first.tzinfo is None:
                first = first.replace(tzinfo=_UTC)
            if last.tzinfo is None:
                last = last.replace(tzinfo=_UTC)
            days = max((last - first).days, 1)
            e.add_field(name="\u23f1\ufe0f Frequency", value=f"```{total/days:.1f} backups/day over {days} days```", inline=False)
        except Exception:
            pass
        return e

    async def refresh(self, interaction):
        bks = await self.cog.storage.get_list(self.guild.id)
        if self.tab == "overview":
            emb = self._overview(bks)
        elif self.tab == "list":
            emb = self._list(bks)
        elif self.tab == "compare":
            emb = self._compare(bks)
        elif self.tab == "audit":
            log = await self.cog.storage.get_audit(self.guild.id)
            emb = self._audit(log)
        elif self.tab == "stats":
            emb = self._stats(bks)
        else:
            emb = self._overview(bks)
        try:
            await interaction.response.edit_message(embed=emb, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=emb, view=self)

    @discord.ui.button(label="Overview", emoji="\U0001f4ca", style=discord.ButtonStyle.blurple, row=0)
    async def b_overview(self, interaction, button):
        self.tab = "overview"
        await self.refresh(interaction)

    @discord.ui.button(label="Backups", emoji="\U0001f4e6", style=discord.ButtonStyle.blurple, row=0)
    async def b_list(self, interaction, button):
        self.tab = "list"; self.page = 0
        await self.refresh(interaction)

    @discord.ui.button(label="Compare", emoji="\U0001f50d", style=discord.ButtonStyle.blurple, row=0)
    async def b_compare(self, interaction, button):
        self.tab = "compare"
        await self.refresh(interaction)

    @discord.ui.button(label="Audit", emoji="\U0001f4dc", style=discord.ButtonStyle.blurple, row=0)
    async def b_audit(self, interaction, button):
        self.tab = "audit"; self.page = 0
        await self.refresh(interaction)

    @discord.ui.button(label="Stats", emoji="\U0001f4c8", style=discord.ButtonStyle.gray, row=1)
    async def b_stats(self, interaction, button):
        self.tab = "stats"
        await self.refresh(interaction)

    @discord.ui.button(label="\u25c0", style=discord.ButtonStyle.gray, row=1)
    async def b_prev(self, interaction, button):
        if self.page > 0:
            self.page -= 1
        await self.refresh(interaction)

    @discord.ui.button(label="\u25b6", style=discord.ButtonStyle.gray, row=1)
    async def b_next(self, interaction, button):
        self.page += 1
        await self.refresh(interaction)

    @discord.ui.button(label="Refresh", emoji="\U0001f504", style=discord.ButtonStyle.gray, row=1)
    async def b_refresh(self, interaction, button):
        await self.refresh(interaction)

    @discord.ui.button(label="Delete Backup", emoji="\U0001f5d1\ufe0f", style=discord.ButtonStyle.danger, row=1)
    async def b_delete(self, interaction, button):
        bks = await self.cog.storage.get_list(self.guild.id)
        if not bks:
            await interaction.response.send_message(embed=discord.Embed(title="\u274c No Backups", description="There are no backups to delete.", color=0xff0000), ephemeral=True)
            return
        view = BackupDeleteView(self.cog, self.author, self.guild, bks)
        await interaction.response.send_message(
            embed=discord.Embed(title="\U0001f5d1\ufe0f Delete a Backup", description="Select a backup from the dropdown.\nPinned backups cannot be deleted \u2014 unpin them first with `/backuppin`.", color=0xff9900),
            view=view, ephemeral=True
        )


class SelectiveRestoreView(discord.ui.View):

    def __init__(self, cog, author, guild, bid, entry, snap):
        super().__init__(timeout=180)
        self.cog = cog
        self.author = author
        self.guild = guild
        self.bid = bid
        self.entry = entry
        self.snap = snap
        self.sel = {"roles", "channels", "categories", "bot_settings", "member_roles"}
        self.role_sync = False

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("\u274c Only the person who ran this command can use these buttons.", ephemeral=True)
            return False
        return True

    def _embed(self):
        _, rel = _ts(self.entry.get("timestamp", ""))
        ck = lambda k: "\u2705" if k in self.sel else "\u274c"
        mr = self.entry.get("member_roles_count", 0) or len(self.snap.get("member_roles", []))
        sync_icon = "\U0001f534" if self.role_sync else "\u26ab"
        e = discord.Embed(
            title="\u26a0\ufe0f Selective Restore",
            description=(
                f"Backup `{self.bid}` \u2014 **{self.entry.get('label', '-')}**\n"
                f"Created {rel}\n\n"
                f"Toggle what you want to restore, then hit confirm.\n"
                f"Only missing items are created. Existing items stay untouched. Nothing gets deleted."
            ),
            color=0xff9900, timestamp=discord.utils.utcnow()
        )
        e.add_field(name="\U0001f3af Restore Components", value=(
            f"{ck('roles')} **Roles** \u2014 {self.entry.get('roles_count',0)} roles (name, color, permissions)\n"
            f"{ck('categories')} **Categories** \u2014 {self.entry.get('categories_count',0)} categories (with overwrites)\n"
            f"{ck('channels')} **Channels** \u2014 {_tch(self.entry)} channels (topic, slowmode, overwrites)\n"
            f"{ck('member_roles')} **Member Roles** \u2014 {mr} members (reapply saved role assignments)\n"
            f"{ck('bot_settings')} **Bot Settings** \u2014 Prefix, mention config"
        ), inline=False)
        sync_desc = (
            f"{sync_icon} **Role Sync** \u2014 {'**ENABLED** \U0001f534' if self.role_sync else 'Disabled (safe mode)'}\n"
        )
        if self.role_sync:
            sync_desc += (
                "```diff\n"
                "- WARNING: DESTRUCTIVE MODE\n"
                "  For each member, this will:\n"
                "  + ADD roles they had in the backup but lost\n"
                "  - REMOVE roles they have now but didn't\n"
                "    have in the backup\n"
                "  This rewinds every member's roles to the\n"
                "  exact state they were in at backup time.\n"
                "```"
            )
        else:
            sync_desc += (
                "```\n"
                "Safe mode: only adds missing roles back.\n"
                "No roles will be removed from anyone.\n"
                "Toggle Role Sync ON to do a full rewind.\n"
                "```"
            )
        e.add_field(name="\U0001f500 Role Sync Mode", value=sync_desc, inline=False)
        e.add_field(name="\U0001f512 What you should know", value=(
            "```\n"
            "- Bot needs Administrator permission\n"
            "- Bot's role must be above roles it manages\n"
            "- Rate-limited by Discord (~2 members/sec)\n"
            "- Members must still be in the server\n"
            "- Guild will be chunked to load all members\n"
            "```"
        ), inline=False)
        e.set_footer(text="This confirmation expires in 3 minutes")
        return e

    def _tog(self, k):
        self.sel.symmetric_difference_update({k})

    @discord.ui.button(label="Roles", emoji="\U0001f3ad", style=discord.ButtonStyle.gray, row=0)
    async def t_roles(self, interaction, button):
        self._tog("roles")
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Categories", emoji="\U0001f4c2", style=discord.ButtonStyle.gray, row=0)
    async def t_cats(self, interaction, button):
        self._tog("categories")
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Channels", emoji="\U0001f4ac", style=discord.ButtonStyle.gray, row=0)
    async def t_ch(self, interaction, button):
        self._tog("channels")
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Members", emoji="\U0001f465", style=discord.ButtonStyle.gray, row=0)
    async def t_members(self, interaction, button):
        self._tog("member_roles")
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="\u2705 Confirm Restore", style=discord.ButtonStyle.danger, row=1)
    async def confirm(self, interaction, button):
        if not self.sel:
            await interaction.response.send_message("\u274c Select at least one component.", ephemeral=True)
            return
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(view=self)
        await self.cog._do_restore(interaction, self.guild, self.snap, self.entry, self.sel, self.role_sync)

    @discord.ui.button(label="Role Sync", emoji="\U0001f500", style=discord.ButtonStyle.gray, row=1)
    async def t_sync(self, interaction, button):
        self.role_sync = not self.role_sync
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Select All", emoji="\U0001f504", style=discord.ButtonStyle.blurple, row=2)
    async def sel_all(self, interaction, button):
        self.sel = {"roles", "channels", "categories", "bot_settings", "member_roles"}
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Bot Settings", emoji="\u2699\ufe0f", style=discord.ButtonStyle.gray, row=2)
    async def t_bot(self, interaction, button):
        self._tog("bot_settings")
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Cancel", emoji="\u274c", style=discord.ButtonStyle.gray, row=2)
    async def cancel(self, interaction, button):
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(embed=discord.Embed(title="\U0001f6ab Restore Cancelled", description="No changes were made to your server.", color=0x5865f2), view=self)


class DeleteConfirmView(discord.ui.View):

    def __init__(self, cog, author, gid, bid, label):
        super().__init__(timeout=60)
        self.cog = cog
        self.author = author
        self.gid = gid
        self.bid = bid
        self.label = label

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("\u274c Only the person who ran this command can confirm this.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="\U0001f5d1\ufe0f Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        ok = await self.cog.storage.delete(self.gid, self.bid, interaction.user.id)
        for c in self.children:
            c.disabled = True
        if ok:
            e = discord.Embed(title="\U0001f5d1\ufe0f Backup Deleted", description=f"`{self.bid}` \u2014 **{self.label}**\nPermanently removed. This cannot be undone.", color=0xff0000, timestamp=discord.utils.utcnow())
        elif ok is False:
            entry = await self.cog.storage.get_entry(self.gid, self.bid)
            if entry and entry.get("pinned"):
                e = discord.Embed(title="\U0001f4cc Cannot Delete", description="This backup is pinned. Unpin it first with `/backuppin`.", color=0xff9900)
            else:
                e = discord.Embed(title="\u274c Not Found", color=0xff0000)
        else:
            e = discord.Embed(title="\u274c Failed", color=0xff0000)
        await interaction.response.edit_message(embed=e, view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction, button):
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(embed=discord.Embed(title="Cancelled", description="Backup was not deleted.", color=0x5865f2), view=self)


class BackupDeleteSelect(discord.ui.Select):

    def __init__(self, cog, author, guild, backups):
        self.cog = cog
        self.author = author
        self.guild = guild
        options = []
        for b in backups[:25]:
            pin = "\U0001f4cc " if b.get("pinned") else ""
            label = f"{pin}{b['id']} \u2014 {b.get('label', '-')}"[:100]
            _, rel = _ts(b.get("timestamp", ""))
            desc = (f"PINNED \u2014 unpin first | {rel}" if b.get("pinned") else rel)[:100]
            options.append(discord.SelectOption(
                label=label,
                value=b["id"],
                description=desc,
                emoji="\U0001f4cc" if b.get("pinned") else "\U0001f5d1\ufe0f",
            ))
        super().__init__(placeholder="Select a backup to delete\u2026", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("\u274c Only the person who opened this dashboard can use it.", ephemeral=True)
            return
        bid = self.values[0]
        entry = await self.cog.storage.get_entry(self.guild.id, bid)
        if not entry:
            await interaction.response.send_message(embed=discord.Embed(title="\u274c Not Found", color=0xff0000), ephemeral=True)
            return
        if entry.get("pinned"):
            await interaction.response.send_message(embed=discord.Embed(title="\U0001f4cc Cannot Delete", description="This backup is pinned. Unpin it first with `/backuppin`.", color=0xff9900), ephemeral=True)
            return
        view = DeleteConfirmView(self.cog, self.author, self.guild.id, bid, entry.get("label", "-"))
        e = discord.Embed(
            title="\U0001f5d1\ufe0f Confirm Deletion",
            description=f"Permanently delete backup `{bid}`?\n**{entry.get('label', '-')}**\n\u26a0\ufe0f This cannot be undone.",
            color=0xff0000
        )
        await interaction.response.send_message(embed=e, view=view, ephemeral=True)


class BackupDeleteView(discord.ui.View):

    def __init__(self, cog, author, guild, backups):
        super().__init__(timeout=120)
        self.add_item(BackupDeleteSelect(cog, author, guild, backups))


class BackupRestore(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        fh = None
        try:
            from atomic_file_system import global_file_handler
            fh = global_file_handler
        except ImportError:
            pass
        self.storage = BackupStorage(file_handler=fh)
        self._locks: Dict[int, asyncio.Lock] = {}
        if AUTO_BACKUP_INTERVAL_HOURS > 0:
            self.auto_loop.start()
        if BACKUP_RETENTION_DAYS > 0:
            self.cleanup_loop.start()
        logger.info("BackupRestore cog loaded (v2.1.0)")

    def cog_unload(self):
        if self.auto_loop.is_running():
            self.auto_loop.cancel()
        if self.cleanup_loop.is_running():
            self.cleanup_loop.cancel()

    def _lock(self, gid):
        if gid not in self._locks:
            self._locks[gid] = asyncio.Lock()
        return self._locks[gid]

    @tasks.loop(hours=1)
    async def auto_loop(self):
        for guild in self.bot.guilds:
            try:
                sched = await self.storage.get_schedule(guild.id)
                if not sched or not sched.get("enabled"):
                    continue
                interval = sched.get("interval_hours", AUTO_BACKUP_INTERVAL_HOURS)
                last = sched.get("last_auto_backup")
                if last:
                    try:
                        last_dt = datetime.fromisoformat(last)
                        if last_dt.tzinfo is None:
                            last_dt = last_dt.replace(tzinfo=_UTC)
                        if _utcnow() - last_dt < timedelta(hours=interval):
                            continue
                    except Exception:
                        pass
                bks = await self.storage.get_list(guild.id)
                if len(bks) >= MAX_BACKUPS_PER_GUILD:
                    continue
                snap = await BackupSnapshot.capture(guild, self.bot)
                label = f"Auto-backup {_utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
                entry = await self.storage.save(guild.id, snap, label, self.bot.user.id)
                if entry:
                    await self.storage.update_entry(guild.id, entry["id"], {"auto_backup": True})
                    sched["last_auto_backup"] = _utcnow().isoformat()
                    await self.storage.set_schedule(guild.id, sched)
                    logger.info(f"BackupRestore: Auto-backup for guild {guild.id}")
            except Exception as e:
                logger.error(f"BackupRestore: Auto-backup failed for {guild.id}: {e}")

    @auto_loop.before_loop
    async def _wait1(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def cleanup_loop(self):
        for d in self.storage.base_dir.iterdir():
            if not d.is_dir():
                continue
            try:
                gid = int(d.name)
                removed = await self.storage.cleanup_old(gid, BACKUP_RETENTION_DAYS)
                if removed:
                    await self.storage.audit(gid, "cleanup", self.bot.user.id, details=f"Removed {removed} expired")
            except Exception:
                pass

    @cleanup_loop.before_loop
    async def _wait2(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="backup", help="Open the Backup & Restore dashboard (Admin/Owner)")
    @commands.guild_only()
    @is_backup_authorized()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def backup_cmd(self, ctx):
        bks = await self.storage.get_list(ctx.guild.id)
        v = DashboardView(self, ctx.author, ctx.guild)
        await ctx.send(embed=v._overview(bks), view=v)

    @commands.hybrid_command(name="backupcreate", help="Create a full guild backup snapshot (Admin/Owner)")
    @commands.guild_only()
    @is_backup_authorized()
    @app_commands.describe(label="Short label for this backup")
    async def backup_create(self, ctx, *, label: str = None):
        if not label:
            label = f"Backup {_utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
        if len(label) > 100:
            return await ctx.send(embed=discord.Embed(title="\u274c Label Too Long", description="Keep it under 100 characters.", color=0xff0000), ephemeral=True)

        cd = self.storage.check_cd(ctx.guild.id)
        if cd:
            if ctx.author.id == BOT_OWNER_ID:
                await ctx.send(embed=discord.Embed(title="\u26a0\ufe0f Cooldown Bypassed (Bot Owner)", description=f"A {cd}s cooldown is active for this guild, but you're the bot owner so it's skipped.", color=0xff9900), ephemeral=True)
            else:
                return await ctx.send(embed=discord.Embed(title="\u23f3 Cooldown Active", description=f"You can create the next backup {f'<t:{int(time.time()) + cd}:R>'}.", color=0xff9900), ephemeral=True)

        bks = await self.storage.get_list(ctx.guild.id)
        if len(bks) >= MAX_BACKUPS_PER_GUILD:
            return await ctx.send(embed=discord.Embed(title="\U0001f4e6 Storage Full", description=f"You've reached the maximum of **{MAX_BACKUPS_PER_GUILD}** backups.\nDelete old ones with `/backupdelete <id>` to make room.", color=0xff0000), ephemeral=True)

        prog = discord.Embed(
            title="\U0001f4be Creating Backup\u2026",
            description="Capturing your server's entire configuration.\nThis usually takes just a few seconds.",
            color=0xffaa00
        )
        prog.add_field(name="Progress", value="```\n\u23f3 Roles & permissions\n\u23f3 Channels & overwrites\n\u23f3 Emojis & stickers\n\u23f3 Loading all members\n\u23f3 Member role assignments\n\u23f3 Server & bot settings\n\u23f3 Saving snapshot\n```", inline=False)
        msg = await ctx.send(embed=prog)

        try:
            t0 = time.time()
            snap = await BackupSnapshot.capture(ctx.guild, self.bot)
            entry = await self.storage.save(ctx.guild.id, snap, label, ctx.author.id)
            elapsed = time.time() - t0

            if not entry:
                return await msg.edit(embed=discord.Embed(title="\u274c Backup Failed", description="Could not write to storage. Check disk space and permissions.", color=0xff0000))

            self.storage.set_cd(ctx.guild.id)
            mr_count = entry.get("member_roles_count", 0)
            mr_line = f"\nMembers:    {mr_count} role snapshots" if mr_count else "\nMembers:    0 (enable Members Intent for this)"

            e = discord.Embed(
                title="\u2705 Backup Created Successfully",
                description=f"**{label}**\nYour server is now preserved. If anything ever goes wrong, you can restore from this snapshot.",
                color=0x00ff00, timestamp=discord.utils.utcnow()
            )
            e.add_field(name="\U0001f4cb Snapshot", value=(
                f"```\n"
                f"ID:         {entry['id']}\n"
                f"Checksum:   {entry['checksum']}\n"
                f"Size:       {_sz(entry.get('size_bytes',0))}\n"
                f"{'='*30}\n"
                f"Roles:      {entry.get('roles_count',0)}\n"
                f"Categories: {entry.get('categories_count',0)}\n"
                f"Channels:   {_tch(entry)}\n"
                f"Emojis:     {entry.get('emojis_count',0)}\n"
                f"Stickers:   {entry.get('stickers_count',0)}"
                f"{mr_line}\n"
                f"{'='*30}\n"
                f"Captured in {elapsed:.2f}s\n"
                f"```"
            ), inline=False)
            e.add_field(name="\U0001f527 What's next?", value=(
                f"`/backupview {entry['id']}` \u2014 See everything inside\n"
                f"`/backuprestore {entry['id']}` \u2014 Restore if needed\n"
                f"`/backuppin {entry['id']}` \u2014 Protect from deletion"
            ), inline=False)
            e.set_footer(text=f"Created by {ctx.author}")
            await msg.edit(embed=e)
            logger.info(f"BackupRestore: {entry['id']} created for {ctx.guild.id} by {ctx.author} ({elapsed:.2f}s, {mr_count} member snapshots)")
        except Exception as ex:
            logger.error(f"BackupRestore: Create error for {ctx.guild.id}: {ex}")
            logger.debug(traceback.format_exc())
            await msg.edit(embed=discord.Embed(title="\u274c Something went wrong", description=f"```{str(ex)[:300]}```\nPlease try again. If this persists, check the bot logs.", color=0xff0000))

    @commands.hybrid_command(name="backuprestore", help="Restore guild from a backup (Admin/Owner)")
    @commands.guild_only()
    @is_backup_authorized()
    @app_commands.describe(backup_id="Backup ID to restore")
    async def backup_restore(self, ctx, backup_id: str):
        entry = await self.storage.get_entry(ctx.guild.id, backup_id)
        if not entry:
            return await ctx.send(embed=discord.Embed(title="\u274c Backup Not Found", description=f"No backup with ID `{backup_id}` exists for this server.\nUse `/backup` to browse your backups.", color=0xff0000), ephemeral=True)
        snap = await self.storage.get_snap(ctx.guild.id, backup_id)
        if not snap:
            return await ctx.send(embed=discord.Embed(title="\u274c Snapshot Corrupt", description="The backup data couldn't be read. Run `/backupverify` to check integrity.", color=0xff0000), ephemeral=True)
        v = SelectiveRestoreView(self, ctx.author, ctx.guild, backup_id, entry, snap)
        await ctx.send(embed=v._embed(), view=v)

    async def _do_restore(self, interaction, guild, snap, entry, components, role_sync=False):
        lock = self._lock(guild.id)
        if lock.locked():
            return await interaction.followup.send(embed=discord.Embed(title="\U0001f512 Restore Already Running", description="Please wait for the current restore to finish.", color=0xff9900), ephemeral=True)

        async with lock:
            prog = discord.Embed(title="\U0001f504 Restoring Your Server\u2026", description="Working through Discord's rate limits. This may take a few minutes for large servers.", color=0xffaa00, timestamp=discord.utils.utcnow())
            status = []
            msg = await interaction.followup.send(embed=prog, wait=True)
            res = {"created": 0, "skipped": 0, "failed": 0, "roles_added": 0, "roles_removed": 0, "members_processed": 0, "members_skipped": 0, "errors": []}
            t0 = time.time()
            role_map = {}
            cat_map = {}

            if "roles" in components:
                existing = {r.name.lower(): r for r in guild.roles}
                roles = snap.get("roles", [])
                status.append(f"\U0001f3ad Restoring {len(roles)} roles\u2026")
                prog.description = "```\n"+"\n".join(status)+"\n```"
                try: await msg.edit(embed=prog)
                except Exception: pass

                for rd in reversed(roles):
                    n = rd["name"]
                    if n.lower() in existing:
                        role_map[rd["id"]] = existing[n.lower()]
                        res["skipped"] += 1
                        continue
                    try:
                        nr = await guild.create_role(name=n, color=discord.Color(rd.get("color", 0)), hoist=rd.get("hoist", False), mentionable=rd.get("mentionable", False), permissions=discord.Permissions(rd.get("permissions_value", 0)), reason=f"Backup restore: {entry['id']}")
                        role_map[rd["id"]] = nr
                        res["created"] += 1
                        await asyncio.sleep(1)
                    except discord.Forbidden:
                        res["failed"] += 1; res["errors"].append(f"Role '{n}': Missing permissions")
                    except discord.HTTPException as e:
                        res["failed"] += 1; res["errors"].append(f"Role '{n}': {str(e)[:50]}")
                    except Exception as e:
                        res["failed"] += 1; res["errors"].append(f"Role '{n}': {str(e)[:50]}")
            else:
                for r in guild.roles:
                    role_map[r.id] = r

            if "categories" in components:
                existing = {c.name.lower(): c for c in guild.categories}
                cats = snap.get("categories", [])
                status.append(f"\U0001f4c2 Restoring {len(cats)} categories\u2026")
                prog.description = "```\n"+"\n".join(status)+"\n```"
                try: await msg.edit(embed=prog)
                except Exception: pass

                for cd in cats:
                    n = cd["name"]
                    if n.lower() in existing:
                        cat_map[cd["id"]] = existing[n.lower()]
                        res["skipped"] += 1
                        continue
                    try:
                        ow = self._ow(cd.get("overwrites", []), guild, role_map)
                        nc = await guild.create_category(name=n, overwrites=ow, reason=f"Backup restore: {entry['id']}")
                        cat_map[cd["id"]] = nc
                        res["created"] += 1
                        await asyncio.sleep(1)
                    except Exception as e:
                        res["failed"] += 1; res["errors"].append(f"Category '{n}': {str(e)[:50]}")
            else:
                for c in guild.categories:
                    cat_map[c.id] = c

            if "channels" in components:
                ex_text = {c.name.lower(): c for c in guild.text_channels}
                text_chs = snap.get("text_channels", [])
                status.append(f"\U0001f4ac Restoring {len(text_chs)} text channels\u2026")
                prog.description = "```\n"+"\n".join(status)+"\n```"
                try: await msg.edit(embed=prog)
                except Exception: pass

                for chd in text_chs:
                    n = chd["name"]
                    if n.lower() in ex_text:
                        res["skipped"] += 1; continue
                    try:
                        cat = cat_map.get(chd.get("category_id"))
                        ow = self._ow(chd.get("overwrites", []), guild, role_map)
                        await guild.create_text_channel(name=n, topic=chd.get("topic"), slowmode_delay=chd.get("slowmode_delay", 0), nsfw=chd.get("nsfw", False), category=cat, overwrites=ow, reason=f"Backup restore: {entry['id']}")
                        res["created"] += 1; await asyncio.sleep(1)
                    except Exception as e:
                        res["failed"] += 1; res["errors"].append(f"Text '{n}': {str(e)[:50]}")

                ex_voice = {c.name.lower(): c for c in guild.voice_channels}
                voice_chs = snap.get("voice_channels", [])
                status.append(f"\U0001f50a Restoring {len(voice_chs)} voice channels\u2026")
                prog.description = "```\n"+"\n".join(status)+"\n```"
                try: await msg.edit(embed=prog)
                except Exception: pass

                for chd in voice_chs:
                    n = chd["name"]
                    if n.lower() in ex_voice:
                        res["skipped"] += 1; continue
                    try:
                        cat = cat_map.get(chd.get("category_id"))
                        ow = self._ow(chd.get("overwrites", []), guild, role_map)
                        await guild.create_voice_channel(name=n, bitrate=min(chd.get("bitrate", 64000), guild.bitrate_limit), user_limit=chd.get("user_limit", 0), category=cat, overwrites=ow, reason=f"Backup restore: {entry['id']}")
                        res["created"] += 1; await asyncio.sleep(1)
                    except Exception as e:
                        res["failed"] += 1; res["errors"].append(f"Voice '{n}': {str(e)[:50]}")

            if "member_roles" in components:
                member_data = snap.get("member_roles", [])
                if member_data:
                    status.append(f"\U0001f465 {'Syncing' if role_sync else 'Restoring'} roles for {len(member_data)} members\u2026")
                    prog.description = "```\n"+"\n".join(status)+"\n```"
                    try: await msg.edit(embed=prog)
                    except Exception: pass

                    if not guild.chunked:
                        try:
                            await guild.chunk(cache=True)
                        except Exception as e:
                            res["errors"].append(f"Guild chunk failed: {str(e)[:60]}")

                    backup_role_names = {rd["id"]: rd["name"] for rd in snap.get("roles", [])}
                    guild_roles_by_name = {
                        r.name.lower(): r for r in guild.roles
                        if not r.is_default() and not r.managed
                    }
                    bot_top_role = guild.me.top_role if guild.me else None

                    def _resolve_role(old_id, old_name=None):
                        r = role_map.get(old_id)
                        if r:
                            return r
                        r = guild.get_role(old_id)
                        if r and not r.is_default() and not r.managed:
                            return r
                        name = old_name or backup_role_names.get(old_id)
                        if name:
                            r = guild_roles_by_name.get(name.lower())
                            if r:
                                return r
                        return None

                    for md in member_data:
                        member = guild.get_member(md["user_id"])
                        if not member or member.bot:
                            continue

                        current_role_ids = {r.id for r in member.roles if not r.is_default()}

                        backup_names = set()
                        target_roles = []
                        for i, old_rid in enumerate(md.get("role_ids", [])):
                            rn_list = md.get("role_names", [])
                            old_name = rn_list[i] if i < len(rn_list) else None
                            resolved = _resolve_role(old_rid, old_name)
                            if resolved:
                                target_roles.append(resolved)
                                backup_names.add(resolved.name.lower())

                        roles_to_add = [
                            r for r in target_roles
                            if r.id not in current_role_ids
                            and (not bot_top_role or r.position < bot_top_role.position)
                        ]

                        roles_to_remove = []
                        if role_sync:
                            for r in member.roles:
                                if r.is_default() or r.managed:
                                    continue
                                if bot_top_role and r.position >= bot_top_role.position:
                                    continue
                                if r.name.lower() not in backup_names:
                                    roles_to_remove.append(r)

                        changed = False
                        if roles_to_add:
                            try:
                                await member.add_roles(*roles_to_add, reason=f"Backup restore: {entry['id']}")
                                res["roles_added"] += len(roles_to_add)
                                changed = True
                            except Exception as e:
                                res["errors"].append(f"Add roles {member}: {str(e)[:50]}")

                        if roles_to_remove:
                            try:
                                await member.remove_roles(*roles_to_remove, reason=f"Backup role sync: {entry['id']}")
                                res["roles_removed"] += len(roles_to_remove)
                                changed = True
                            except Exception as e:
                                res["errors"].append(f"Remove roles {member}: {str(e)[:50]}")

                        if changed:
                            res["members_processed"] += 1
                            await asyncio.sleep(0.5)
                        else:
                            res["members_skipped"] += 1

            if "bot_settings" in components:
                status.append("\u2699\ufe0f Restoring bot settings\u2026")
                prog.description = "```\n"+"\n".join(status)+"\n```"
                try: await msg.edit(embed=prog)
                except Exception: pass
                bs = snap.get("bot_settings", {})
                if bs and hasattr(self.bot, "db") and self.bot.db:
                    try:
                        if bs.get("custom_prefix") is not None:
                            await self.bot.db.set_guild_prefix(guild.id, bs["custom_prefix"])
                            if hasattr(self.bot, "prefix_cache"):
                                await self.bot.prefix_cache.invalidate(guild.id)
                        if bs.get("mention_prefix_enabled") is not None:
                            await self.bot.db.set_guild_mention_prefix_enabled(guild.id, bs["mention_prefix_enabled"])
                    except Exception as e:
                        res["errors"].append(f"Bot settings: {str(e)[:60]}")

            elapsed = time.time() - t0
            sync_str = " SYNC" if role_sync else ""
            await self.storage.audit(guild.id, "restore", interaction.user.id, entry["id"], f"C:{res['created']} S:{res['skipped']} F:{res['failed']} +R:{res['roles_added']} -R:{res['roles_removed']} M:{res['members_processed']}{sync_str} [{','.join(components)}]")

            col = 0x00ff00 if res["failed"] == 0 else 0xff9900
            title = "\u2705 Restore Complete" if res["failed"] == 0 else "\u26a0\ufe0f Restore Completed with Errors"
            re = discord.Embed(title=title, description=f"Backup `{entry['id']}` has been applied to **{guild.name}**.", color=col, timestamp=discord.utils.utcnow())
            results_text = (
                f"\u2705 Created:          {res['created']}\n"
                f"\u23ed\ufe0f Skipped:          {res['skipped']} (already exist)\n"
                f"\u274c Failed:           {res['failed']}"
            )
            if "member_roles" in components:
                results_text += (
                    f"\n{'='*30}\n"
                    f"\U0001f465 Members touched:  {res['members_processed']}\n"
                    f"\u23ed\ufe0f Members ok:       {res['members_skipped']} (no changes needed)\n"
                    f"\u2795 Roles added:      {res['roles_added']}\n"
                )
                if role_sync:
                    results_text += f"\u2796 Roles removed:    {res['roles_removed']}\n"
                    results_text += f"\U0001f500 Mode:             Full Sync (add + remove)"
                else:
                    results_text += f"\U0001f500 Mode:             Safe (add only)"
            results_text += f"\n\u23f1\ufe0f Duration:         {elapsed:.1f}s"
            re.add_field(name="\U0001f4ca Results", value=f"```\n{results_text}\n```", inline=False)
            if res["errors"]:
                etxt = "\n".join(res["errors"][:10])
                if len(res["errors"]) > 10:
                    etxt += f"\n\u2026 +{len(res['errors'])-10} more"
                re.add_field(name="\u26a0\ufe0f Issues", value=f"```\n{etxt}\n```", inline=False)
            re.set_footer(text=f"Restored by {interaction.user}")
            await msg.edit(embed=re)
            logger.info(f"BackupRestore: Restore {entry['id']} for {guild.id} \u2014 C:{res['created']} S:{res['skipped']} F:{res['failed']} +R:{res['roles_added']} -R:{res['roles_removed']} M:{res['members_processed']}{sync_str} ({elapsed:.1f}s)")

    def _ow(self, data, guild, rmap):
        ow = {}
        for o in data:
            if o["target_type"] == "role":
                t = rmap.get(o["target_id"]) or guild.get_role(o["target_id"])
            else:
                t = guild.get_member(o["target_id"])
            if not t:
                continue
            ow[t] = discord.PermissionOverwrite.from_pair(discord.Permissions(o.get("allow", 0)), discord.Permissions(o.get("deny", 0)))
        return ow

    @commands.hybrid_command(name="backupview", help="Detailed backup info (Admin/Owner)")
    @commands.guild_only()
    @is_backup_authorized()
    @app_commands.describe(backup_id="Backup ID")
    async def backup_view(self, ctx, backup_id: str):
        entry = await self.storage.get_entry(ctx.guild.id, backup_id)
        if not entry:
            return await ctx.send(embed=discord.Embed(title="\u274c Not Found", color=0xff0000), ephemeral=True)
        snap = await self.storage.get_snap(ctx.guild.id, backup_id)
        ts_f, ts_r = _ts(entry.get("timestamp", ""))
        pin = " \U0001f4cc PINNED" if entry.get("pinned") else ""
        auto = " \U0001f501 Auto" if entry.get("auto_backup") else ""
        mr = entry.get("member_roles_count", 0) or (len(snap.get("member_roles", [])) if snap else 0)

        e = discord.Embed(title=f"\U0001f4cb Backup `{backup_id}`{pin}{auto}", description=f"**{entry.get('label', '-')}**", color=0x5865f2, timestamp=discord.utils.utcnow())
        e.add_field(name="\U0001f3f7\ufe0f Metadata", value=f"```\nID:        {entry['id']}\nChecksum:  {entry.get('checksum','?')}\nVersion:   {entry.get('version','?')}\nSize:      {_sz(entry.get('size_bytes',0))}\nServer:    {entry.get('guild_name','?')}\nMembers:   {entry.get('member_count',0)}\n```\nCreated {ts_f} ({ts_r})\nBy <@{entry.get('author_id',0)}>", inline=False)
        mr_line = f"\nMember Roles:{mr:>5}" if mr else ""
        e.add_field(name="\U0001f4ca Contents", value=f"```\nRoles:      {entry.get('roles_count',0):>5}\nCategories: {entry.get('categories_count',0):>5}\nText Ch:    {entry.get('text_channels_count',0):>5}\nVoice Ch:   {entry.get('voice_channels_count',0):>5}\nForum Ch:   {entry.get('forum_channels_count',0):>5}\nStage Ch:   {entry.get('stage_channels_count',0):>5}\nTotal Ch:   {_tch(entry):>5}\nEmojis:     {entry.get('emojis_count',0):>5}\nStickers:   {entry.get('stickers_count',0):>5}{mr_line}\n```", inline=True)

        if snap:
            bs = snap.get("bot_settings", {})
            ss = snap.get("server_settings", {})
            vl = VERIFICATION_NAMES.get(ss.get("verification_level", 0), "?") if ss else "N/A"
            e.add_field(name="\u2699\ufe0f Settings", value=f"```\nPrefix:      {bs.get('custom_prefix') or 'Default'}\nMention:     {'On' if bs.get('mention_prefix_enabled') else 'Off' if bs.get('mention_prefix_enabled') is not None else 'Global'}\nVerify:      {vl}\nAFK:         {ss.get('afk_timeout','?')}s\nBoost Bar:   {ss.get('premium_progress_bar_enabled','?')}\n```", inline=True)
            roles = snap.get("roles", [])
            if roles:
                rl = ", ".join(r["name"] for r in roles[:12])
                if len(roles) > 12:
                    rl += f" +{len(roles)-12}"
                e.add_field(name="\U0001f3ad Roles", value=f"```\n{rl}\n```", inline=False)

        if entry.get("notes"):
            e.add_field(name="\U0001f4dd Notes", value=entry["notes"][:500], inline=False)

        e.add_field(name="\U0001f527 Actions", value=f"`/backuprestore {backup_id}`\n`/backuppin {backup_id}` \u2014 {'Unpin' if entry.get('pinned') else 'Pin'}\n`/backupnote {backup_id} <text>`\n`/backupverify {backup_id}`\n`/backupdelete {backup_id}`", inline=False)
        await ctx.send(embed=e)

    @commands.hybrid_command(name="backupdelete", help="Delete a backup (Admin/Owner)")
    @commands.guild_only()
    @is_backup_authorized()
    @app_commands.describe(backup_id="Backup ID")
    async def backup_delete(self, ctx, backup_id: str):
        entry = await self.storage.get_entry(ctx.guild.id, backup_id)
        if not entry:
            return await ctx.send(embed=discord.Embed(title="\u274c Not Found", color=0xff0000), ephemeral=True)
        if entry.get("pinned"):
            return await ctx.send(embed=discord.Embed(title="\U0001f4cc Pinned Backup", description=f"This backup is pinned and protected from deletion.\nUnpin it first: `/backuppin {backup_id}`", color=0xff9900), ephemeral=True)
        if ctx.author.id != BOT_OWNER_ID and entry.get("author_id") != ctx.author.id and not ctx.author.guild_permissions.administrator:
            return await ctx.send(embed=discord.Embed(title="\u274c Permission Denied", description="You can only delete your own backups unless you have Administrator.", color=0xff0000), ephemeral=True)

        _, rel = _ts(entry.get("timestamp", ""))
        e = discord.Embed(title="\U0001f5d1\ufe0f Delete This Backup?", description=f"**ID:** `{entry['id']}`\n**Label:** {entry.get('label','-')}\n**Contents:** {entry.get('roles_count',0)} roles, {_tch(entry)} channels, {entry.get('member_roles_count',0)} member snapshots\nCreated {rel}\n\n\u26a0\ufe0f **This is permanent and cannot be undone.**", color=0xff9900)
        await ctx.send(embed=e, view=DeleteConfirmView(self, ctx.author, ctx.guild.id, backup_id, entry.get("label", "-")))

    @commands.hybrid_command(name="backuplist", help="List all backups (Admin/Owner)")
    @commands.guild_only()
    @is_backup_authorized()
    async def backup_list(self, ctx):
        bks = await self.storage.get_list(ctx.guild.id)
        v = DashboardView(self, ctx.author, ctx.guild)
        v.tab = "list"
        await ctx.send(embed=v._list(bks), view=v)

    @commands.hybrid_command(name="backuppin", help="Pin/unpin a backup (Admin/Owner)")
    @commands.guild_only()
    @is_backup_authorized()
    @app_commands.describe(backup_id="Backup ID")
    async def backup_pin(self, ctx, backup_id: str):
        r = await self.storage.toggle_pin(ctx.guild.id, backup_id, ctx.author.id)
        if r is None:
            return await ctx.send(embed=discord.Embed(title="\u274c Not Found", color=0xff0000), ephemeral=True)
        if r:
            await ctx.send(embed=discord.Embed(title="\U0001f4cc Backup Pinned", description=f"`{backup_id}` is now protected.\nIt won't be deleted by cleanup or manual deletion until unpinned.", color=0x00ff00))
        else:
            await ctx.send(embed=discord.Embed(title="\U0001f4cc Backup Unpinned", description=f"`{backup_id}` is no longer protected.\nIt can now be deleted normally.", color=0xff9900))

    @commands.hybrid_command(name="backupnote", help="Add note to a backup (Admin/Owner)")
    @commands.guild_only()
    @is_backup_authorized()
    @app_commands.describe(backup_id="Backup ID", note="Note text (max 500)")
    async def backup_note(self, ctx, backup_id: str, *, note: str):
        if len(note) > 500:
            return await ctx.send(embed=discord.Embed(title="\u274c Too Long", description="Notes are limited to 500 characters.", color=0xff0000), ephemeral=True)
        entry = await self.storage.get_entry(ctx.guild.id, backup_id)
        if not entry:
            return await ctx.send(embed=discord.Embed(title="\u274c Not Found", color=0xff0000), ephemeral=True)
        await self.storage.update_entry(ctx.guild.id, backup_id, {"notes": note})
        await self.storage.audit(ctx.guild.id, "note", ctx.author.id, backup_id, f"Note: {note[:80]}")
        await ctx.send(embed=discord.Embed(title="\U0001f4dd Note Saved", description=f"Backup `{backup_id}`:\n> {note}", color=0x00ff00))

    @commands.hybrid_command(name="backupverify", help="Verify backup integrity (Admin/Owner)")
    @commands.guild_only()
    @is_backup_authorized()
    @app_commands.describe(backup_id="Backup ID")
    async def backup_verify(self, ctx, backup_id: str):
        ok, message = await self.storage.verify(ctx.guild.id, backup_id)
        await self.storage.audit(ctx.guild.id, "verify", ctx.author.id, backup_id, message)
        if ok:
            await ctx.send(embed=discord.Embed(title="\u2705 Integrity Verified", description=f"Backup `{backup_id}` is intact.\n```{message}```", color=0x00ff00))
        else:
            await ctx.send(embed=discord.Embed(title="\u274c Integrity Check Failed", description=f"Backup `{backup_id}` may be corrupted.\n```{message}```", color=0xff0000))

    @commands.hybrid_command(name="backupschedule", help="Auto-backup schedule (Admin/Owner)")
    @commands.guild_only()
    @is_backup_authorized()
    @app_commands.describe(action="enable/disable/status", interval_hours="Hours between auto-backups (1-168)")
    async def backup_schedule(self, ctx, action: str, interval_hours: int = None):
        action = action.lower()
        sched = await self.storage.get_schedule(ctx.guild.id) or {}
        if action == "status":
            en = sched.get("enabled", False)
            iv = sched.get("interval_hours", AUTO_BACKUP_INTERVAL_HOURS)
            last = sched.get("last_auto_backup", "Never")
            last_display = "Never"
            if last != "Never":
                _, last_display = _ts(last)
            e = discord.Embed(title="\u23f0 Auto-Backup Schedule", description=f"**{ctx.guild.name}**", color=0x5865f2)
            e.add_field(name="Configuration", value=f"```\nStatus:   {'\u2705 Enabled' if en else '\u274c Disabled'}\nInterval: Every {iv} hours\n```\nLast run: {last_display}", inline=False)
            if AUTO_BACKUP_INTERVAL_HOURS <= 0:
                e.add_field(name="\u26a0\ufe0f Background Loop Inactive", value="Set `BACKUP_AUTO_INTERVAL` to a value > 0 in `.env` and restart the bot.", inline=False)
            return await ctx.send(embed=e)
        if action == "enable":
            iv = max(1, min(168, interval_hours or AUTO_BACKUP_INTERVAL_HOURS or 24))
            sched.update({"enabled": True, "interval_hours": iv})
            await self.storage.set_schedule(ctx.guild.id, sched)
            await self.storage.audit(ctx.guild.id, "schedule", ctx.author.id, details=f"Enabled every {iv}h")
            e = discord.Embed(title="\u2705 Auto-Backup Enabled", description=f"Automatic snapshots every **{iv} hours**.\nBackups will be labeled as auto-backups in the list.", color=0x00ff00)
            if AUTO_BACKUP_INTERVAL_HOURS <= 0:
                e.add_field(name="\u26a0\ufe0f Important", value="The background loop needs `BACKUP_AUTO_INTERVAL` > 0 in `.env`. Restart the bot after setting it.", inline=False)
            return await ctx.send(embed=e)
        if action == "disable":
            sched["enabled"] = False
            await self.storage.set_schedule(ctx.guild.id, sched)
            await self.storage.audit(ctx.guild.id, "schedule", ctx.author.id, details="Disabled")
            return await ctx.send(embed=discord.Embed(title="\u274c Auto-Backup Disabled", description="Automatic backups have been turned off for this server.", color=0xff9900))
        await ctx.send(embed=discord.Embed(title="\u274c Invalid Action", description="Use `enable`, `disable`, or `status`.", color=0xff0000), ephemeral=True)

    @commands.hybrid_command(name="backupdiff", help="Compare two backups (Admin/Owner)")
    @commands.guild_only()
    @is_backup_authorized()
    @app_commands.describe(id_a="First backup ID", id_b="Second backup ID")
    async def backup_diff(self, ctx, id_a: str, id_b: str):
        ea = await self.storage.get_entry(ctx.guild.id, id_a)
        eb = await self.storage.get_entry(ctx.guild.id, id_b)
        if not ea or not eb:
            return await ctx.send(embed=discord.Embed(title="\u274c Not Found", description=f"Missing: `{id_a if not ea else id_b}`", color=0xff0000), ephemeral=True)
        sa = await self.storage.get_snap(ctx.guild.id, id_a)
        sb = await self.storage.get_snap(ctx.guild.id, id_b)
        if not sa or not sb:
            return await ctx.send(embed=discord.Embed(title="\u274c Read Error", color=0xff0000), ephemeral=True)

        def names(s, key):
            return {x["name"] for x in s.get(key, [])}

        pairs = [("\U0001f3ad Roles", "roles"), ("\U0001f4c2 Categories", "categories"), ("\U0001f4ac Text Channels", "text_channels"), ("\U0001f50a Voice Channels", "voice_channels")]
        _, ra = _ts(ea.get("timestamp", ""))
        _, rb = _ts(eb.get("timestamp", ""))
        e = discord.Embed(title="\U0001f500 Backup Diff", description=f"**A:** `{id_a}` \u2014 {ea.get('label','')} ({ra})\n**B:** `{id_b}` \u2014 {eb.get('label','')} ({rb})", color=0x5865f2, timestamp=discord.utils.utcnow())

        total_changes = 0
        for label, key in pairs:
            na = names(sa, key)
            nb = names(sb, key)
            added = nb - na
            removed = na - nb
            total_changes += len(added) + len(removed)
            lines = []
            if added:
                items = ", ".join(sorted(added)[:6])
                if len(added) > 6: items += f" +{len(added)-6}"
                lines.append(f"+ Added ({len(added)}): {items}")
            if removed:
                items = ", ".join(sorted(removed)[:6])
                if len(removed) > 6: items += f" +{len(removed)-6}"
                lines.append(f"- Removed ({len(removed)}): {items}")
            if not lines:
                lines.append(f"No changes ({len(na & nb)} items)")
            e.add_field(name=label, value=f"```diff\n"+"\n".join(lines)+"\n```", inline=False)

        mr_a = {m["user_id"] for m in sa.get("member_roles", [])}
        mr_b = {m["user_id"] for m in sb.get("member_roles", [])}
        mr_added = len(mr_b - mr_a)
        mr_removed = len(mr_a - mr_b)
        if mr_a or mr_b:
            ml = []
            if mr_added:
                ml.append(f"+ {mr_added} new member snapshots")
            if mr_removed:
                ml.append(f"- {mr_removed} member snapshots removed")
            if not ml:
                ml.append(f"No changes ({len(mr_a & mr_b)} members)")
            e.add_field(name="\U0001f465 Member Roles", value=f"```diff\n"+"\n".join(ml)+"\n```", inline=False)

        e.set_footer(text=f"Total structural changes: {total_changes}")
        await ctx.send(embed=e)

    @commands.hybrid_command(name="backupexport", help="Export backup as JSON (Bot Owner only)")
    @commands.guild_only()
    @is_bot_owner()
    @app_commands.describe(backup_id="Backup ID")
    async def backup_export(self, ctx, backup_id: str):
        snap = await self.storage.get_snap(ctx.guild.id, backup_id)
        if not snap:
            return await ctx.send(embed=discord.Embed(title="\u274c Not Found", color=0xff0000), ephemeral=True)
        await self.storage.audit(ctx.guild.id, "export", ctx.author.id, backup_id)
        data = json.dumps(snap, indent=2, default=str)
        fn = f"backup_{ctx.guild.id}_{backup_id}.json"
        await ctx.send(
            embed=discord.Embed(title="\U0001f4e4 Backup Exported", description=f"`{backup_id}` \u2014 {_sz(len(data))}\n\u26a0\ufe0f This file contains your server's structure and member role data. Handle it securely.", color=0x00ff00),
            file=discord.File(fp=io.BytesIO(data.encode("utf-8")), filename=fn)
        )

    @commands.hybrid_command(name="backupstats", help="Global backup stats (Bot Owner only)")
    @is_bot_owner()
    async def backup_stats(self, ctx):
        s = await self.storage.global_stats()
        e = discord.Embed(title="\U0001f4ca Global Backup Statistics", description="Across all guilds using this bot instance.", color=0x5865f2, timestamp=discord.utils.utcnow())
        e.add_field(name="\U0001f4e6 Storage", value=f"```\nBackups: {s['total']}\nGuilds:  {s['guilds']}\nPinned:  {s['pinned']}\nSize:    {_sz(s['size'])}\n```", inline=True)
        e.add_field(name="\u2699\ufe0f Config", value=f"```\nMax/Guild:  {MAX_BACKUPS_PER_GUILD}\nCooldown:   {BACKUP_COOLDOWN_SECONDS}s\nAuto:       {AUTO_BACKUP_INTERVAL_HOURS}h {'(on)' if AUTO_BACKUP_INTERVAL_HOURS > 0 else '(off)'}\nRetention:  {BACKUP_RETENTION_DAYS}d {'(on)' if BACKUP_RETENTION_DAYS > 0 else '(off)'}\n```", inline=True)
        await ctx.send(embed=e)

    @backup_cmd.error
    @backup_create.error
    @backup_restore.error
    @backup_view.error
    @backup_delete.error
    @backup_list.error
    @backup_pin.error
    @backup_note.error
    @backup_verify.error
    @backup_schedule.error
    @backup_diff.error
    @backup_export.error
    @backup_stats.error
    async def _err(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send(embed=discord.Embed(title="\u274c Permission Denied", description=str(error), color=0xff0000), ephemeral=True)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(embed=discord.Embed(title="\u23f3 Cooldown", description=f"Try again {f'<t:{int(time.time()) + int(error.retry_after)}:R>'}.", color=0xff9900), ephemeral=True)
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("\u274c This command can only be used in a server.", ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=discord.Embed(title="\u274c Missing Argument", description=f"Required: `{error.param.name}`\nUse `/backup` for the dashboard.", color=0xff0000), ephemeral=True)
        else:
            logger.error(f"BackupRestore: {error}")
            logger.debug(traceback.format_exc())


async def setup(bot):
    enabled = os.getenv("ENABLE_BACKUP_RESTORE", "true").lower()
    if enabled not in ("true", "1", "yes"):
        logger.info("BackupRestore cog DISABLED via ENABLE_BACKUP_RESTORE")
        return
    await bot.add_cog(BackupRestore(bot))
    logger.info("BackupRestore cog setup complete (v2.1.0)")