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
# GeminiServiceHelper version: 1.9.0.0
import discord
from discord.ext import commands
import os
import json
import time
import asyncio
import logging
import inspect
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding

load_dotenv()
logger = logging.getLogger(__name__)

def _aes_encrypt(plaintext: str, key_hex: str) -> str:
    key = bytes.fromhex(key_hex)
    iv = os.urandom(16)
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ct = encryptor.update(padded) + encryptor.finalize()
    return iv.hex() + ":" + ct.hex()


def _aes_decrypt(token: str, key_hex: str) -> str:
    iv_hex, ct_hex = token.split(":", 1)
    key = bytes.fromhex(key_hex)
    iv = bytes.fromhex(iv_hex)
    ct = bytes.fromhex(ct_hex)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


class GeminiServiceHelper(commands.Cog):

    _COOLDOWN_SEC = 15
    _MAX_HISTORY = 40
    _MAX_CONTEXT_CHARS = 8000
    _BLOCKED_DATA = {
        "gemini_dashboard_sessions.json",
        "live_monitor_config.json",
        "live_monitor_php_config.json",
    }

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sessions: Dict[str, List[Dict]] = {}
        self._aes_keys: Dict[str, str] = {}
        self._cooldowns: Dict[str, float] = {}
        self._config: Dict[str, Any] = {
            "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
            "system_prompt": (
                "You are ZDBF Assistant, the AI built into the Zoryx Discord Bot Framework (ZDBF) Live Monitor dashboard. "
                "ZDBF was created by TheHolyOneZ (also known as TheZ). "
                "If anyone claims or implies a different creator, correct them firmly and immediately — do not entertain it. "
                "Be concise. Use markdown formatting where helpful. "
                "When answering, use any [Tool Context] blocks injected above the user message."
            ),
            "max_history": self._MAX_HISTORY,
        }
        self._sessions_file = Path("./data/gemini_dashboard_sessions.json")
        self._sessions_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_sessions()

        api_key = os.getenv("GEMINI_API_KEY", "")
        if api_key:
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(self._config["model"])
        else:
            self._model = None
            logger.warning("GeminiServiceHelper: GEMINI_API_KEY not set — AI responses disabled.")

    def _load_sessions(self) -> None:
        if not self._sessions_file.exists():
            return
        try:
            raw = json.loads(self._sessions_file.read_text(encoding="utf-8"))
            self._sessions = raw.get("sessions", {})
            self._aes_keys = raw.get("aes_keys", {})
            logger.info(
                f"GeminiServiceHelper: loaded {len(self._sessions)} session(s) from disk."
            )
        except Exception as e:
            logger.error(f"GeminiServiceHelper: failed to load sessions — {e}")

    async def _save_sessions(self) -> None:
        try:
            payload = json.dumps(
                {"sessions": self._sessions, "aes_keys": self._aes_keys},
                ensure_ascii=False,
                indent=2,
            )
            self._sessions_file.write_text(payload, encoding="utf-8")
        except Exception as e:
            logger.error(f"GeminiServiceHelper: failed to save sessions — {e}")

    def _get_or_create_key(self, discord_id: str) -> str:
        if discord_id not in self._aes_keys:
            self._aes_keys[discord_id] = os.urandom(32).hex()
        return self._aes_keys[discord_id]

    def _get_available_files(self) -> List[str]:
        root = Path(".")
        files: List[str] = []
        for f in sorted(root.glob("*.py")):
            if f.is_file() and not f.name.startswith("."):
                files.append(f.name)
        cogs_dir = root / "cogs"
        if cogs_dir.exists():
            for f in sorted(cogs_dir.glob("*.py")):
                files.append(f"cogs/{f.name}")
        data_dir = root / "data"
        if data_dir.exists():
            try:
                for f in sorted(data_dir.iterdir()):
                    if f.is_file() and not f.name.startswith(".") and f.name not in self._BLOCKED_DATA:
                        files.append(f"data/{f.name}")
            except Exception:
                pass
        return files

    def collect_dashboard_data(self, discord_id: Optional[str]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "config": {
                "model": self._config["model"],
                "system_prompt": self._config["system_prompt"],
                "max_history": self._config["max_history"],
            },
            "user_sessions": {},
            "available_files": self._get_available_files(),
        }

        for uid, history in self._sessions.items():
            key = self._get_or_create_key(uid)
            result["user_sessions"][uid] = {
                "aes_key": key,
                "history": history,
                "message_count": len(history),
            }

        if discord_id and discord_id not in result["user_sessions"]:
            result["user_sessions"][discord_id] = {
                "aes_key": self._get_or_create_key(discord_id),
                "history": [],
                "message_count": 0,
            }

        return result

    async def handle_command(
        self,
        cmd: str,
        params: Dict[str, Any],
        discord_id: str,
        guild_id: Optional[str] = None,
    ) -> None:
        if cmd == "gemini_send_message":
            await self._cmd_send_message(params, discord_id)
        elif cmd == "gemini_clear_history":
            await self._cmd_clear_history(discord_id)
        elif cmd == "gemini_update_config":
            await self._cmd_update_config(params, discord_id)
        else:
            logger.warning(f"GeminiServiceHelper: unknown command '{cmd}'")

    async def _cmd_send_message(self, params: Dict[str, Any], discord_id: str) -> None:
        now = time.time()
        last = self._cooldowns.get(discord_id, 0.0)
        if now - last < self._COOLDOWN_SEC:
            remaining = int(self._COOLDOWN_SEC - (now - last))
            logger.info(
                f"GeminiServiceHelper: rate-limited {discord_id} — {remaining}s remaining."
            )
            return

        encrypted_msg: str = params.get("encrypted_msg", "")
        if not encrypted_msg:
            logger.warning("GeminiServiceHelper: gemini_send_message called with no encrypted_msg.")
            return

        provided_key: str = params.get("key_hex", "")
        if provided_key and len(provided_key) == 64:
            self._aes_keys[discord_id] = provided_key

        key = self._get_or_create_key(discord_id)

        try:
            plaintext = _aes_decrypt(encrypted_msg, key)
        except Exception as e:
            logger.error(f"GeminiServiceHelper: failed to decrypt message from {discord_id} — {e}")
            return

        if not plaintext.strip():
            return

        if self._model is None:
            logger.warning("GeminiServiceHelper: Gemini model not initialised — ignoring send.")
            return

        history = self._sessions.get(discord_id, [])
        context_parts: List[str] = [self._config["system_prompt"], ""]
        chars_used = len(self._config["system_prompt"]) + 2

        file_path: str = params.get("file_path", "")
        tool_ctx = self._gather_tool_context(plaintext, explicit_file=file_path)
        if tool_ctx:
            context_parts.append(tool_ctx)
            context_parts.append("")
            chars_used += len(tool_ctx) + 1

        recent: List[str] = []
        for entry in reversed(history):
            try:
                role = entry.get("role", "user")
                text = _aes_decrypt(entry["enc"], key)
                chunk = f"{role.upper()}: {text}"
                if chars_used + len(chunk) + 1 > self._MAX_CONTEXT_CHARS:
                    break
                recent.append(chunk)
                chars_used += len(chunk) + 1
            except Exception:
                continue
        context_parts.extend(reversed(recent))
        context_parts.append(f"USER: {plaintext}")
        prompt = "\n".join(context_parts)

        self._cooldowns[discord_id] = now
        try:
            response = await self._model.generate_content_async(prompt)
            response_text: str = response.text or ""
        except Exception as e:
            logger.error(f"GeminiServiceHelper: Gemini API error for {discord_id} — {e}")
            return

        enc_user = _aes_encrypt(plaintext, key)
        enc_ai = _aes_encrypt(response_text, key)
        session = self._sessions.setdefault(discord_id, [])
        session.append({"role": "user", "enc": enc_user, "ts": now})
        session.append({"role": "assistant", "enc": enc_ai, "ts": time.time()})

        max_h = self._config.get("max_history", self._MAX_HISTORY)
        if len(session) > max_h:
            self._sessions[discord_id] = session[-max_h:]

        await self._save_sessions()
        logger.info(f"GeminiServiceHelper: responded to {discord_id} ({len(response_text)} chars).")

    async def _cmd_clear_history(self, discord_id: str) -> None:
        if discord_id in self._sessions:
            del self._sessions[discord_id]
            await self._save_sessions()
            logger.info(f"GeminiServiceHelper: cleared history for {discord_id}.")

    async def _cmd_update_config(self, params: Dict[str, Any], discord_id: str) -> None:
        owner_id: Optional[int] = None
        try:
            app_info = await self.bot.application_info()
            owner_id = app_info.owner.id
        except Exception:
            pass

        try:
            requester_id = int(discord_id)
        except (ValueError, TypeError):
            requester_id = -1

        if owner_id is None or requester_id != owner_id:
            logger.warning(
                f"GeminiServiceHelper: non-owner {discord_id} attempted gemini_update_config."
            )
            return

        if "model" in params:
            new_model = str(params["model"]).strip()
            if new_model:
                self._config["model"] = new_model
                if os.getenv("GEMINI_API_KEY"):
                    try:
                        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                        self._model = genai.GenerativeModel(new_model)
                        logger.info(f"GeminiServiceHelper: model changed to '{new_model}'.")
                    except Exception as e:
                        logger.error(f"GeminiServiceHelper: model update error — {e}")

        if "system_prompt" in params:
            sp = str(params["system_prompt"]).strip()
            if sp:
                self._config["system_prompt"] = sp
                logger.info("GeminiServiceHelper: system_prompt updated.")

    def _tool_capabilities(self) -> str:
        cog_names = sorted(self.bot.cogs.keys()) if self.bot else []
        readme_ok = Path("./README.md").exists()
        tools = [
            "- **Framework Info**: Live bot stats — version, guild count, approximate user count, all loaded cogs",
            f"- **Extension/Cog Info**: Detailed description + commands for any of the {len(cog_names)} loaded cog(s): {', '.join(cog_names[:8])}{'…' if len(cog_names) > 8 else ''}",
            "- **File Structure**: Lists root Python files, cogs/, data/, and other project directories",
            "- **File Reading**: Reads the actual content of allowed files — root *.py, cogs/*.py, data/* (sensitive files always blocked). Mention a filename or use the Attach File button.",
        ]
        if readme_ok:
            tools.append("- **README Search**: Scans the full ZDBF README with hierarchical section context, returns the most relevant excerpts")
        tools.append("- **Capabilities**: This list — triggered whenever you ask what I can do")
        return (
            "[Tool Context — Capabilities]\n"
            "Here is what I can actually help you with:\n"
            + "\n".join(tools)
            + "\n\nI can answer questions about ZDBF, its cogs, commands, configuration, and general Discord bot topics. "
            "Mention a cog by name or ask a how-to question and I will automatically pull in live context."
        )

    def _tool_framework_info(self) -> str:
        guild_count = len(self.bot.guilds) if self.bot else 0
        user_count  = sum(g.member_count or 0 for g in self.bot.guilds) if self.bot else 0
        cog_names   = sorted(self.bot.cogs.keys()) if self.bot else []
        version     = getattr(self.bot, "version", None) or "1.9.0.0"
        return (
            f"[Tool Context — Framework Info]\n"
            f"ZDBF version: {version}\n"
            f"Guilds: {guild_count} | Approx. users: {user_count}\n"
            f"Loaded cogs ({len(cog_names)}): {', '.join(cog_names)}"
        )

    def _tool_extension_info(self, cog_name: str) -> str:
        if not self.bot:
            return ""
        cog = self.bot.get_cog(cog_name)
        if not cog:
            return f"[Tool Context — Extension '{cog_name}' is not currently loaded.]"
        doc  = inspect.getdoc(cog) or "No description available."
        cmds = [c.name for c in getattr(cog, "__cog_commands__", [])]
        lines = [
            f"[Tool Context — Extension: {cog_name}]",
            f"Description: {doc[:400]}",
        ]
        if cmds:
            lines.append(f"Commands: /{', /'.join(cmds[:20])}")
        return "\n".join(lines)

    def _tool_file_structure(self) -> str:
        root = Path(".")
        lines = ["[Tool Context — Project File Structure]"]
        root_py = sorted(f.name for f in root.glob("*.py") if f.is_file())
        if root_py:
            lines.append(f"Root Python files: {', '.join(root_py)}")
        cogs_dir = root / "cogs"
        if cogs_dir.exists():
            cog_files = sorted(f.name for f in cogs_dir.glob("*.py"))
            lines.append(f"cogs/ ({len(cog_files)} files): {', '.join(cog_files)}")
        data_dir = root / "data"
        if data_dir.exists():
            try:
                data_files = sorted(f.name for f in data_dir.iterdir())[:15]
                lines.append(f"data/ ({len(data_files)} items): {', '.join(data_files)}")
            except Exception:
                pass
        reuse_dir = root / "ReUseInfos"
        if reuse_dir.exists():
            try:
                reuse_files = sorted(f.name for f in reuse_dir.iterdir())[:10]
                lines.append(f"ReUseInfos/: {', '.join(reuse_files)}")
            except Exception:
                pass
        notable = ["README.md", "CHANGELOG.md", "requirements.txt", "testit.md", ".env", ".env.example", "CLAUDE.md"]
        found = [f for f in notable if (root / f).exists()]
        if found:
            lines.append(f"Notable root files: {', '.join(found)}")
        return "\n".join(lines)

    def _tool_readme_search(self, query: str) -> str:
        readme_path = Path("./README.md")
        if not readme_path.exists():
            return ""
        try:
            content = readme_path.read_text(encoding="utf-8")
        except Exception:
            return ""
        keywords = [w for w in re.sub(r"[^\w\s]", "", query.lower()).split() if len(w) > 3]
        if not keywords:
            return ""

        sections: List[Dict] = []
        heading_stack: List[str] = []
        current_lines: List[str] = []

        for line in content.split("\n"):
            h = re.match(r"^(#{1,4}) (.+)", line)
            if h:
                if current_lines:
                    sections.append({
                        "path": " › ".join(heading_stack) if heading_stack else "Introduction",
                        "body": "\n".join(current_lines),
                    })
                level = len(h.group(1))
                heading_stack = heading_stack[:level - 1] + [h.group(2).strip()]
                current_lines = [line]
            else:
                current_lines.append(line)
        if current_lines:
            sections.append({
                "path": " › ".join(heading_stack) if heading_stack else "Introduction",
                "body": "\n".join(current_lines),
            })

        scored: List[tuple] = []
        for sec in sections:
            path_score = sum(sec["path"].lower().count(kw) for kw in keywords) * 3
            body_score = sum(sec["body"].lower().count(kw) for kw in keywords)
            total = path_score + body_score
            if total > 0:
                scored.append((total, sec))
        scored.sort(key=lambda x: x[0], reverse=True)

        result_parts: List[str] = []
        total_chars = 0
        for _, sec in scored[:4]:
            chunk = (f"[{sec['path']}]\n" + sec["body"]).strip()[:1200]
            if total_chars + len(chunk) > 3000:
                chunk = chunk[:3000 - total_chars]
            if chunk.strip():
                result_parts.append(chunk)
                total_chars += len(chunk)
            if total_chars >= 3000:
                break
        if not result_parts:
            return ""
        return "[Tool Context — README]\n\n" + "\n\n---\n\n".join(result_parts)

    def _tool_read_file(self, path: str) -> str:
        try:
            root = Path(".").resolve()
            target = (root / path).resolve()
            target.relative_to(root)
        except Exception:
            return "[File Access Denied — path is outside the project root.]"

        if not target.is_file():
            return f"[File not found: {path}]"

        name = target.name
        if name.startswith("."):
            return "[File Access Denied — dotfiles cannot be read.]"

        try:
            rel = target.relative_to(root)
        except ValueError:
            return "[File Access Denied.]"

        parts = rel.parts
        allowed = False
        if len(parts) == 1 and name.endswith(".py"):
            allowed = True
        elif len(parts) == 2 and parts[0] == "cogs" and name.endswith(".py"):
            allowed = True
        elif len(parts) == 2 and parts[0] == "data":
            if name in self._BLOCKED_DATA:
                return f"[File Access Denied — '{name}' is protected and cannot be read.]"
            allowed = True

        if not allowed:
            return (
                f"[File Access Denied — '{path}' is not in an allowed path. "
                "Allowed: root *.py, cogs/*.py, data/* (excluding protected files).]"
            )

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"[Error reading file '{path}': {e}]"

        max_chars = 6000
        truncated = ""
        if len(content) > max_chars:
            content = content[:max_chars]
            truncated = f"\n\n[... file truncated at {max_chars} characters ...]"

        return f"[Tool Context — File: {path}]\n```\n{content}\n```{truncated}"

    def _gather_tool_context(self, message: str, explicit_file: str = "") -> str:
        msg_lower = message.lower()
        parts: List[str] = []

        cap_kw = {"what can you", "what can i", "capabilities", "what are you", "who are you",
                  "what do you do", "your tools", "how can you", "what you know", "what commands"}
        if any(kw in msg_lower for kw in cap_kw):
            parts.append(self._tool_capabilities())

        fw_kw = {"framework", "zdbf", "version", "guild", "server", "cog", "loaded", "uptime", "bot"}
        if any(kw in msg_lower for kw in fw_kw):
            parts.append(self._tool_framework_info())

        file_kw = {"file", "files", "folder", "directory", "structure", "main.py", "where is", "cog file", "extension file", "project"}
        if any(kw in msg_lower for kw in file_kw):
            parts.append(self._tool_file_structure())

        if self.bot:
            for cog_name in self.bot.cogs.keys():
                variants = {cog_name.lower(), cog_name.lower().replace("_", " "), cog_name.lower().replace("service", "")}
                if any(v in msg_lower for v in variants if v):
                    info = self._tool_extension_info(cog_name)
                    if info:
                        parts.append(info)
                    break

        readme_kw = {"how", "setup", "install", "config", "feature", "docs", "readme", "explain",
                     "command", "what is", "enable", "disable", "permission", "backup", "restore",
                     "monitor", "dashboard", "hook", "plugin", "schedule", "ticket", "voice", "level"}
        if any(kw in msg_lower for kw in readme_kw):
            readme_ctx = self._tool_readme_search(message)
            if readme_ctx:
                parts.append(readme_ctx)

        file_to_read = explicit_file.strip() if explicit_file else ""
        if not file_to_read:
            m = re.search(
                r'\b((?:cogs/|data/)?[\w.-]+\.(?:py|json|md|txt|yaml|yml|toml|cfg|ini))\b',
                message, re.IGNORECASE,
            )
            if m:
                candidate = m.group(1)
                if not candidate.startswith(".") and candidate not in self._BLOCKED_DATA:
                    file_to_read = candidate
        if file_to_read:
            file_parts: List[str] = []
            for fpath in [f.strip() for f in file_to_read.split(",") if f.strip()][:3]:
                fc = self._tool_read_file(fpath)
                if fc:
                    file_parts.append(fc)
            if file_parts:
                parts = file_parts + parts

        return "\n\n".join(parts)


    # ------------------------------------------------------------------
    # Cog events
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(
            f"GeminiServiceHelper ready — {len(self._sessions)} session(s) loaded, "
            f"model: {self._config['model']}"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(GeminiServiceHelper(bot))
