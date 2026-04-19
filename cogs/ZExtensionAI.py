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
# ZExtensionAI version: 1.9.4.1
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import asyncio
import json
import time
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger("discord.cogs.ZExtensionAI")

_PORTAL_BASE  = "https://zsync.eu/extension/view.php?id="
_PORTAL_STORE = "https://zsync.eu/extension/"


try:
    import aiohttp as _aiohttp
    _AIOHTTP_OK = True
except ImportError:
    _AIOHTTP_OK = False
    logger.critical("ZExtensionAI: aiohttp not installed — cannot fetch extension data.")

try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    np = None
    _NUMPY_OK = False

try:
    from sentence_transformers import SentenceTransformer as _SentenceTransformer
    _SBERT_OK = True
except ImportError:
    _SentenceTransformer = None
    _SBERT_OK = False
    logger.warning("ZExtensionAI: sentence-transformers not installed — keyword search mode.")

try:
    from llama_cpp import Llama as _Llama
    _LLAMA_OK = True
except ImportError:
    _Llama = None
    _LLAMA_OK = False
    logger.warning("ZExtensionAI: llama-cpp-python not installed — AI generation disabled.")


_API_URL     = "https://zsync.eu/extension/api/extensions.php?action=list"
_CACHE_FILE  = Path("./data/zai_extension_cache.json")
_MODEL_DIR   = Path("./models")
_CACHE_TTL   = 3600
_COOLDOWN    = 15
_TOP_K       = 5
_MAX_DETAIL  = 900
_MAX_TOKENS  = 512
_REPLY_TTL   = 1800   
_INSTALL_RE = re.compile(
    r"\b(install|download|get(?:\s+it)?|add(?:\s+it)?|load(?:\s+it)?|"
    r"grab(?:\s+it)?|set\s*(?:it\s*)?up|put\s+it\s+in)\b",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(
    r"\b(what|how|does|can(?:'t)?|is|are|which|why|tell|explain|show|list|describe|"
    r"who|where|when|give|works?|support|have|has|do(?:es)?|detail|more|info|help|"
    r"about|commands?|features?|use|usage|difference|vs|versus|compare|setup|"
    r"require|need|depend|config|enable|disable|permission|role|prefix|log)\b"
    r"|\?",
    re.IGNORECASE,
)
_ANAPHORA_RE  = re.compile(r"\b(it|that|this|the\s+extension|the\s+one|this\s+one)\b", re.IGNORECASE)
_INTEREST_RE  = re.compile(
    r"\b(install|download|get|add|load|grab|want|like|try|need|use|setup|set\s*up)\b",
    re.IGNORECASE,
)

def _portal_link(ext: dict) -> str:
    return f"{_PORTAL_BASE}{ext['id']}"


def _classify_reply_intent(text: str) -> str:
    
    if _INSTALL_RE.search(text):
        return "INSTALL"
    if _QUESTION_RE.search(text.strip()):
        return "QUESTION"
    return "UNKNOWN"


def _detect_install_intent(text: str) -> bool:
    return bool(_INSTALL_RE.search(text))


def _pick_extension(text: str, extensions: List[dict]) -> dict:
    
    text_lower = text.lower()
    for ext in extensions:
        if ext["title"].lower() in text_lower:
            return ext
    ordinals = [
        (["first", "1st", "one"], 0),
        (["second", "2nd", "two"], 1),
        (["third", "3rd", "three"], 2),
    ]
    for words, idx in ordinals:
        if any(w in text_lower for w in words) and idx < len(extensions):
            return extensions[idx]
    return extensions[0]


def _pick_followup_extensions(text: str, extensions: List[dict]) -> List[dict]:
    
    text_lower = text.lower()

    for ext in extensions:
        if ext["title"].lower() in text_lower:
            return [ext]

    ordinals = [
        (["first", "1st"], 0),
        (["second", "2nd"], 1),
        (["third", "3rd"], 2),
    ]
    for words, idx in ordinals:
        if any(w in text_lower for w in words) and idx < len(extensions):
            return [extensions[idx]]

    if _ANAPHORA_RE.search(text_lower):
        return [extensions[0]]

    return extensions


def _strip_md(text: str) -> str:
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`{3}[^\n]*\n(.*?)`{3}", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_commands(details: str) -> List[str]:
    hits = re.findall(r"`((?:/|!)\w[\w_ ]*(?:<[^>]+>|\[[^\]]+\])*)`", details)
    seen, out = set(), []
    for h in hits:
        key = h.lower()
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out[:6]

class _KnowledgeBase:
    def __init__(self) -> None:
        self.extensions: List[Dict[str, Any]] = []
        self._embeddings = None
        self._sbert = None
        self._last_refresh: float = 0.0
        self._lock = asyncio.Lock()

    async def initialise(self) -> None:
        if _SBERT_OK:
            await asyncio.to_thread(self._load_sbert)
        await self.refresh(force=True)

    async def refresh(self, force: bool = False) -> bool:
        if not force and (time.monotonic() - self._last_refresh) < _CACHE_TTL:
            return False
        async with self._lock:
            if not force and (time.monotonic() - self._last_refresh) < _CACHE_TTL:
                return False
            ok = await self._fetch()
            if ok and _SBERT_OK and self._sbert and _NUMPY_OK:
                await asyncio.to_thread(self._build_embeddings)
            return ok

    def search(self, query: str, top_k: int = _TOP_K) -> List[Dict[str, Any]]:
        if not self.extensions:
            return []
        if _SBERT_OK and self._sbert and self._embeddings is not None and _NUMPY_OK:
            return self._semantic_search(query, top_k)
        return self._keyword_search(query, top_k)

    def by_title(self, title: str) -> Optional[Dict[str, Any]]:
        tl = title.lower()
        exact = next((e for e in self.extensions if e["title"].lower() == tl), None)
        if exact:
            return exact
        return next((e for e in self.extensions if tl in e["title"].lower()), None)

    def _load_sbert(self) -> None:
        try:
            self._sbert = _SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("ZExtensionAI: SentenceTransformer (all-MiniLM-L6-v2) loaded.")
        except Exception as exc:
            logger.error(f"ZExtensionAI: SentenceTransformer load failed — {exc}")

    async def _fetch(self) -> bool:
        if not _AIOHTTP_OK:
            return self._load_cache()
        try:
            timeout = _aiohttp.ClientTimeout(total=15)
            async with _aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(_API_URL) as resp:
                    if resp.status != 200:
                        logger.error(f"ZExtensionAI: API returned HTTP {resp.status}")
                        return self._load_cache()
                    raw = await resp.json(content_type=None)
            if not raw.get("success") or "extensions" not in raw:
                return self._load_cache()
            self.extensions = raw["extensions"]
            self._last_refresh = time.monotonic()
            self._write_cache(raw)
            logger.info(f"ZExtensionAI: Fetched {len(self.extensions)} extensions from portal API.")
            return True
        except Exception as exc:
            logger.error(f"ZExtensionAI: API fetch failed — {exc}")
            return self._load_cache()

    def _write_cache(self, data: dict) -> None:
        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"ZExtensionAI: Cache write failed — {exc}")

    def _load_cache(self) -> bool:
        if not _CACHE_FILE.exists():
            logger.warning("ZExtensionAI: No cache and API unreachable — extension list empty.")
            return False
        try:
            data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            self.extensions = data.get("extensions", [])
            self._last_refresh = time.monotonic()
            logger.info(f"ZExtensionAI: Loaded {len(self.extensions)} extensions from cache.")
            return bool(self.extensions)
        except Exception as exc:
            logger.error(f"ZExtensionAI: Cache read failed — {exc}")
            return False

    def _build_embeddings(self) -> None:
        if not self.extensions or not self._sbert:
            return
        texts = [f"{e['title']}: {e['description']}" for e in self.extensions]
        try:
            self._embeddings = self._sbert.encode(
                texts, show_progress_bar=False, normalize_embeddings=True
            )
            logger.info(f"ZExtensionAI: Built {len(texts)} embeddings.")
        except Exception as exc:
            logger.error(f"ZExtensionAI: Embedding build failed — {exc}")

    def _semantic_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        try:
            q = self._sbert.encode([query], normalize_embeddings=True)[0]
            scores = np.dot(self._embeddings, q)
            indices = np.argsort(scores)[::-1][:top_k]
            result = []
            for i in indices:
                ext = dict(self.extensions[i])
                ext["_score"] = float(scores[i])
                result.append(ext)
            return result
        except Exception as exc:
            logger.error(f"ZExtensionAI: Semantic search error — {exc}")
            return self._keyword_search(query, top_k)

    def _keyword_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        terms = query.lower().split()
        scored: List[Tuple[float, dict]] = []
        for ext in self.extensions:
            blob = f"{ext['title']} {ext['description']} {ext.get('details', '')}".lower()
            score = sum(blob.count(t) for t in terms)
            if score:
                e = dict(ext)
                e["_score"] = float(score)
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

class _LocalLLM:
    def __init__(self) -> None:
        self._llm = None
        self.model_name: str = ""
        self._lock = asyncio.Lock()

    @property
    def loaded(self) -> bool:
        return self._llm is not None

    def find_model(self) -> Optional[Path]:
        _MODEL_DIR.mkdir(parents=True, exist_ok=True)
        candidates = sorted(_MODEL_DIR.glob("*.gguf"), key=lambda p: p.stat().st_size, reverse=True)
        return candidates[0] if candidates else None

    def load(self) -> bool:
        if not _LLAMA_OK:
            return False
        path = self.find_model()
        if not path:
            logger.warning(f"ZExtensionAI: No .gguf file found in {_MODEL_DIR}/.")
            return False
        try:
            self._llm = _Llama(model_path=str(path), n_ctx=4096, n_gpu_layers=-1, verbose=False)
            self.model_name = path.name
            logger.info(f"ZExtensionAI: Model loaded — {path.name}")
            return True
        except Exception as exc:
            logger.error(f"ZExtensionAI: Model load failed — {exc}")
            return False

    async def generate(self, prompt: str) -> str:
        if not self._llm:
            return ""
        async with self._lock:
            try:
                out = await asyncio.to_thread(
                    self._llm, prompt,
                    max_tokens=_MAX_TOKENS, temperature=0.25, top_p=0.90,
                    repeat_penalty=1.1,
                    stop=["<|eot_id|>", "\nUser:", "\nHuman:", "\n\n\n\n"],
                    echo=False,
                )
                return out["choices"][0]["text"].strip()
            except Exception as exc:
                logger.error(f"ZExtensionAI: Generation error — {exc}")
                return ""

def _build_prompt(question: str, results: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for ext in results:
        details  = _strip_md(ext.get("details", ""))[:_MAX_DETAIL]
        cmds     = _extract_commands(ext.get("details", ""))
        cmd_line = f"Known commands: {', '.join(cmds)}" if cmds else ""
        blocks.append((
            f"[Extension: {ext['title']}]\n"
            f"Version: {ext['version']} | Status: {ext['status']} | Author: {ext.get('creator', 'Unknown')}\n"
            f"Description: {ext['description']}\n"
            f"{cmd_line}\n"
            f"Details:\n{details}"
        ).strip())
    context = "\n\n---\n\n".join(blocks)
    return (
        "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
        "You are ZDBF-AI, the official assistant for the Zygnal Discord Bot Framework. "
        "You help users discover, understand, and set up extensions from the Zygnal Extension Portal.\n"
        "Rules:\n"
        "- Answer ONLY from the extension data provided. Never invent commands or features.\n"
        "- Cite commands exactly as they appear in the data.\n"
        "- Map 'anti-nuke', 'moderation', 'logging', etc. to the most relevant extension.\n"
        "- If uncertain, list the options.\n"
        "- Be concise and Discord-friendly. No excessive markdown.\n"
        "- If nothing matches, say so honestly.\n"
        "<|eot_id|><|start_header_id|>user<|end_header_id|>\n"
        f"Extension portal data (top matches):\n\n{context}\n\n"
        f"Question: {question}\n"
        "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
    )


def _fallback_text(question: str, results: List[Dict[str, Any]]) -> str:
    lines = ["Here are the most relevant extensions from the Zygnal portal:\n"]
    for ext in results[:3]:
        cmds    = _extract_commands(ext.get("details", ""))
        cmd_str = f"\n> Commands: {', '.join(f'`{c}`' for c in cmds)}" if cmds else ""
        lines.append(
            f"**{ext['title']}** `v{ext['version']}`\n"
            f"> {ext['description'][:180]}{cmd_str}"
        )
    return "\n\n".join(lines)


def _fallback_followup(question: str, extensions: List[Dict[str, Any]]) -> str:
    
    q     = question.lower()
    lines = []
    for ext in extensions[:2]:
        cmds    = _extract_commands(ext.get("details", ""))
        details = _strip_md(ext.get("details", ""))[:300]
        if any(w in q for w in ("command", "cmd", "slash", "prefix", "!")):
            val = ", ".join(f"`{c}`" for c in cmds) if cmds else "No commands found in documentation."
            lines.append(f"**{ext['title']}** commands: {val}")
        elif any(w in q for w in ("version", "latest", "update", "release")):
            lines.append(f"**{ext['title']}** is at version `{ext['version']}`.")
        elif any(w in q for w in ("author", "creator", "who made", "made by")):
            lines.append(f"**{ext['title']}** was created by **{ext.get('creator', 'Unknown')}**.")
        elif any(w in q for w in ("status", "work", "broken", "stable", "bug")):
            si = "✅ working" if ext["status"] == "working" else f"⚠️ {ext['status']}"
            lines.append(f"**{ext['title']}** status: {si}.")
        elif any(w in q for w in ("setup", "install", "config", "require", "depend", "need")):
            lines.append(f"**{ext['title']}** — {details[:250]}")
        else:
            lines.append(
                f"**{ext['title']}** `v{ext['version']}`\n"
                f"> {ext['description'][:180]}\n"
                f"> {details[:180]}"
            )
    return "\n\n".join(lines) if lines else (
        "I couldn't find specific information about that in the extension data. "
        "Check the portal page for full details."
    )


def _build_followup_prompt(
    question: str,
    extensions: List[Dict[str, Any]],
    history: List[Tuple[str, str]],
    previous_response: str = "",
) -> str:
    blocks: List[str] = []
    for ext in extensions:
        details  = _strip_md(ext.get("details", ""))[:_MAX_DETAIL]
        cmds     = _extract_commands(ext.get("details", ""))
        cmd_line = f"Known commands: {', '.join(cmds)}" if cmds else ""
        blocks.append((
            f"[Extension: {ext['title']}]\n"
            f"Version: {ext['version']} | Status: {ext['status']} | Author: {ext.get('creator', 'Unknown')}\n"
            f"Description: {ext['description']}\n"
            f"{cmd_line}\n"
            f"Details:\n{details}"
        ).strip())
    context = "\n\n---\n\n".join(blocks)

    prev_text = ""
    if previous_response:
        prev_text = f"\n\nYour previous response that the user is replying to:\n{previous_response[:650]}\n"

    history_text = ""
    if history:
        history_text = "\n\nConversation so far:\n"
        for role, content in history[-6:]:
            prefix = "User" if role == "user" else "Assistant"
            history_text += f"{prefix}: {content[:350]}\n"

    return (
        "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n"
        "You are ZDBF-AI, the official assistant for the Zygnal Discord Bot Framework. "
        "The user is replying to one of your previous answers. Use the extension data, your previous "
        "response, and the conversation history as full context. Answer directly and concisely. "
        "Do not invent commands or features not listed in the data. No excessive markdown.\n"
        "<|eot_id|><|start_header_id|>user<|end_header_id|>\n"
        f"Extension data:\n\n{context}"
        f"{prev_text}"
        f"{history_text}\n\n"
        f"Follow-up: {question}\n"
        "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
    )

def _build_result_embed(ext_data: dict, filepath: str, load_exc: Optional[Exception]) -> discord.Embed:
    if load_exc is None:
        load_status = "✅ **Loaded and running now.**"
        color = discord.Color.green()
    elif isinstance(load_exc, commands.ExtensionAlreadyLoaded):
        ext_stem = Path(filepath).stem
        load_status = f"⚠️ Already loaded — run `!reload {ext_stem}` to apply the new file."
        color = discord.Color.yellow()
    elif isinstance(load_exc, commands.ExtensionFailed):
        ext_stem = Path(filepath).stem
        load_status = (
            f"⚠️ Downloaded but load failed: `{load_exc.original}`\n"
            f"Try `!marketplace fixdeps` for missing deps, then `!load {ext_stem}`."
        )
        color = discord.Color.orange()
    else:
        ext_stem = Path(filepath).stem
        load_status = f"⚠️ Downloaded but couldn't auto-load: `{load_exc}`\nRun `!load {ext_stem}` manually."
        color = discord.Color.orange()

    embed = discord.Embed(
        title=f"✅ {ext_data['title']} Installed!",
        description=f"File saved to `{filepath}`",
        color=color,
    )
    embed.add_field(name="Load Status", value=load_status,                              inline=False)
    embed.add_field(name="Version",     value=ext_data["version"],                      inline=True)
    embed.add_field(name="Author",      value=ext_data.get("creator", "Unknown"),       inline=True)
    embed.add_field(name="Portal Page", value=f"[Full readme & details]({_portal_link(ext_data)})", inline=False)
    embed.set_footer(text="ZExtensionAI • Zygnal Extension Portal")
    return embed


def _build_fail_embed(ext_data: dict, message: str) -> discord.Embed:
    embed = discord.Embed(
        title="❌ Download Failed",
        description=f"Could not download **{ext_data['title']}**.",
        color=discord.Color.red(),
    )
    if "403" in str(message) or "not activated" in str(message).lower() or "zygnalid" in str(message).lower():
        embed.add_field(
            name="🔑 ZygnalID Not Activated",
            value=(
                "Your ZygnalID isn't activated.\n\n"
                "**How to fix:**\n"
                "1. Join `discord.gg/sgZnXca5ts`\n"
                "2. Open a ticket → **Zygnal Activation** category\n"
                "3. Follow the instructions in the ticket\n\n"
                "Run `!marketplace myid` to see your ZygnalID."
            ),
            inline=False,
        )
    else:
        embed.add_field(name="Error", value=str(message)[:500], inline=False)
        embed.add_field(
            name="Manual Install",
            value=f"[Download from portal]({_portal_link(ext_data)}) and place in `extensions/`.",
            inline=False,
        )
    return embed

class _RetryInstallView(discord.ui.View):
    """
    Attached to a failed-download embed so the owner can retry with one click
    once they've sorted their ZygnalID activation.
    Re-shows itself on repeated failures so they can keep retrying.
    """

    def __init__(self, cog: "ZExtensionAI", ext_data: dict, owner_id: int) -> None:
        super().__init__(timeout=300)
        self._cog   = cog
        self._ext   = ext_data
        self._owner = owner_id

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._owner:
            await interaction.response.send_message("> ❌ Only the bot owner can retry.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔄 Try Again", style=discord.ButtonStyle.primary)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer()

        marketplace = self._cog._marketplace_cog()
        if not marketplace:
            embed = discord.Embed(
                title="❌ Marketplace Not Available",
                description=(
                    "The `ExtensionMarketplace` cog isn't loaded.\n"
                    f"Install manually from [the portal]({_portal_link(self._ext)})."
                ),
                color=discord.Color.red(),
            )
            await interaction.edit_original_response(embed=embed, view=None)
            return

        await interaction.edit_original_response(
            embed=discord.Embed(
                title="📥 Retrying Download…",
                description=f"Fetching **{self._ext['title']}** from the portal…",
                color=discord.Color.blue(),
            ),
            view=None,
        )

        filepath, msg = await marketplace.download_extension(self._ext)
        if not filepath:

            await interaction.edit_original_response(
                embed=_build_fail_embed(self._ext, msg),
                view=_RetryInstallView(self._cog, self._ext, self._owner),
            )
            return

        load_exc = await self._cog._try_load(Path(filepath).stem)
        await interaction.edit_original_response(
            embed=_build_result_embed(self._ext, filepath, load_exc),
            view=None,
        )
        logger.info(f"ZExtensionAI: (retry) installed {self._ext['title']} id={self._ext['id']} → {filepath}")

    async def on_timeout(self) -> None:
        self._cog = None

class _ReplyLicenseView(discord.ui.View):
    """
    Sent as a reply when the bot owner replies with install intent but hasn't
    accepted the marketplace license yet. Accept immediately triggers the install.
    """

    def __init__(self, cog: "ZExtensionAI", ext_data: dict, owner_id: int) -> None:
        super().__init__(timeout=300)
        self._cog     = cog
        self._ext     = ext_data
        self._owner   = owner_id

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._owner:
            await interaction.response.send_message("> ❌ Only the bot owner can do this.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Accept & Install", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer()
        marketplace = self._cog._marketplace_cog()
        if marketplace:
            await marketplace.mark_license_accepted(self._owner)

        await self._cog._do_install(interaction, self._ext)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        embed = discord.Embed(
            title="❌ Licence Declined",
            description=(
                "Installation cancelled.\n"
                "You can accept the marketplace licence at any time with `!marketplace`."
            ),
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def on_timeout(self) -> None:
        self._cog = None

class _InstallConfirmView(discord.ui.View):
    def __init__(self, cog: "ZExtensionAI", ext_data: dict, requester_id: int) -> None:
        super().__init__(timeout=60)
        self._cog         = cog
        self._ext         = ext_data
        self._requester   = requester_id

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._requester:
            await interaction.response.send_message("> ❌ Only the person who triggered this can confirm.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Confirm Install", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.defer()
        await self._cog._do_install(interaction, self._ext)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._guard(interaction):
            return
        await interaction.response.edit_message(
            embed=discord.Embed(title="Installation Cancelled", color=discord.Color.red()),
            view=None,
        )

    async def on_timeout(self) -> None:
        self._cog = None

class _ZAIResponseView(discord.ui.View):
    def __init__(
        self,
        cog: "ZExtensionAI",
        results: List[dict],
        author_id: int,
        show_install: bool = True,
    ) -> None:
        super().__init__(timeout=300)
        self._cog       = cog
        self._author_id = author_id

        if show_install:
            installable = [r for r in results if r.get("status") == "working"][:3]
            for ext in installable:
                self._add_install_button(ext)

        self.add_item(discord.ui.Button(
            label="🌐 Browse Portal",
            style=discord.ButtonStyle.link,
            url=_PORTAL_STORE,
        ))

    def _add_install_button(self, ext: dict) -> None:
        btn = discord.ui.Button(
            label=f"📦 Install {ext['title'][:22]}",
            style=discord.ButtonStyle.success,
        )
        btn.callback = self._make_callback(ext)
        self.add_item(btn)

    def _make_callback(self, ext_data: dict):
        async def _cb(interaction: discord.Interaction) -> None:
            owner_id = getattr(interaction.client, "bot_owner_id", None)
            if owner_id and interaction.user.id != owner_id:
                await interaction.response.send_message(
                    "> 🔒 Only the bot owner can install extensions.", ephemeral=True
                )
                return
            view  = _InstallConfirmView(self._cog, ext_data, interaction.user.id)
            si    = "✅" if ext_data["status"] == "working" else "⚠️"
            embed = discord.Embed(
                title=f"Install {ext_data['title']}?",
                description=ext_data["description"][:350],
                color=discord.Color.blue(),
            )
            embed.add_field(name="Version", value=ext_data["version"],                           inline=True)
            embed.add_field(name="Status",  value=f"{si} {ext_data['status'].title()}",           inline=True)
            embed.add_field(name="Author",  value=ext_data.get("creator", "Unknown"),            inline=True)
            embed.add_field(name="Portal",  value=f"[View details]({_portal_link(ext_data)})",   inline=False)
            embed.set_footer(text="Downloads to extensions/ and auto-loads the cog.")
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return _cb

    async def on_timeout(self) -> None:
        self._cog = None

class ZExtensionAI(commands.Cog):
    

    def __init__(self, bot: commands.Bot) -> None:
        self.bot  = bot
        self.kb   = _KnowledgeBase()
        self.llm  = _LocalLLM()
        self._ready              = False
        self._cooldowns:   Dict[int, float] = {}
        self._reply_store: Dict[int, dict]  = {}
        self._startup_task: Optional[asyncio.Task] = None



    async def cog_load(self) -> None:
        self._startup_task = asyncio.create_task(self._startup())
        self._auto_refresh.start()

    async def cog_unload(self) -> None:
        self._auto_refresh.cancel()
        if self._startup_task and not self._startup_task.done():
            self._startup_task.cancel()
            try:
                await self._startup_task
            except asyncio.CancelledError:
                pass
        self.llm._llm = None
        self.kb.extensions.clear()
        self.kb._embeddings = None
        self._reply_store.clear()

    async def _startup(self) -> None:
        try:
            await self.kb.initialise()
            await asyncio.to_thread(self.llm.load)
            self._ready = True
            logger.info(
                f"ZExtensionAI: Ready — {len(self.kb.extensions)} extensions, "
                f"model={'yes (' + self.llm.model_name + ')' if self.llm.loaded else 'no'}, "
                f"search={'semantic' if _SBERT_OK and self.kb._embeddings is not None else 'keyword'}."
            )
        except Exception as exc:
            logger.error(f"ZExtensionAI: Startup failed — {exc}")

    @tasks.loop(seconds=_CACHE_TTL)
    async def _auto_refresh(self) -> None:
        await self.kb.refresh()

    @_auto_refresh.before_loop
    async def _before_refresh(self) -> None:
        await self.bot.wait_until_ready()
        await asyncio.sleep(_CACHE_TTL)



    def _cooldown_remaining(self, user_id: int) -> float:
        last      = self._cooldowns.get(user_id, 0.0)
        remaining = _COOLDOWN - (time.monotonic() - last)
        if remaining > 0:
            return remaining
        if len(self._cooldowns) > 2000:
            cutoff = time.monotonic() - _COOLDOWN * 2
            self._cooldowns = {k: v for k, v in self._cooldowns.items() if v > cutoff}
        self._cooldowns[user_id] = time.monotonic()
        return 0.0

    async def _not_ready(self, ctx: commands.Context) -> bool:
        if not self._ready:
            await ctx.send("> **ZAI** is still starting up — please wait a moment.", ephemeral=True)
            return True
        return False

    def _marketplace_cog(self):
        return self.bot.cogs.get("ExtensionMarketplace")

    def _cleanup_reply_store(self) -> None:
        cutoff  = time.monotonic() - _REPLY_TTL
        expired = [k for k, v in self._reply_store.items() if v["ts"] < cutoff]
        for k in expired:
            del self._reply_store[k]

    async def _fetch_ref_embed_text(self, message: discord.Message) -> str:
        
        try:
            ref      = message.reference
            resolved = ref.resolved if ref else None
            if resolved is None and ref and ref.message_id:
                resolved = await message.channel.fetch_message(ref.message_id)
            if not resolved or not resolved.embeds:
                return ""
            emb   = resolved.embeds[0]
            parts = []
            if emb.description:
                parts.append(emb.description)
            for field in emb.fields:
                skip = {"🌐 View on Portal", "Portal Page", "💬 Tip", "Load Status"}
                if field.name and field.name not in skip and field.value:
                    parts.append(f"{field.name}: {field.value}")
            return _strip_md("\n".join(parts))[:700]
        except Exception:
            return ""



    async def _do_install(self, interaction: discord.Interaction, ext_data: dict) -> None:
        """
        Interaction-based install. Called from both button confirms and the
        inline reply-licence view. Expects interaction.response already deferred.
        """
        marketplace = self._marketplace_cog()
        if not marketplace:
            embed = discord.Embed(
                title="❌ Marketplace Not Available",
                description=(
                    "The `ExtensionMarketplace` cog isn't loaded.\n"
                    f"Install manually from [the portal]({_portal_link(ext_data)})."
                ),
                color=discord.Color.red(),
            )
            await interaction.edit_original_response(embed=embed, view=None)
            return

        accepted = await marketplace.check_license_acceptance(interaction.user.id)
        if not accepted:
            embed = discord.Embed(
                title="⚠️ Marketplace Licence Required",
                description="Run `!marketplace` or `/marketplace` to accept the licence, then try again.",
                color=discord.Color.orange(),
            )
            await interaction.edit_original_response(embed=embed, view=None)
            return

        await interaction.edit_original_response(
            embed=discord.Embed(
                title="📥 Downloading…",
                description=f"Fetching **{ext_data['title']}** from the portal…",
                color=discord.Color.blue(),
            ),
            view=None,
        )

        filepath, msg = await marketplace.download_extension(ext_data)
        if not filepath:
            await interaction.edit_original_response(
                embed=_build_fail_embed(ext_data, msg),
                view=_RetryInstallView(self, ext_data, interaction.user.id),
            )
            return

        load_exc = await self._try_load(Path(filepath).stem)
        await interaction.edit_original_response(
            embed=_build_result_embed(ext_data, filepath, load_exc),
            view=None,
        )
        logger.info(f"ZExtensionAI: (button) installed {ext_data['title']} id={ext_data['id']} → {filepath}")

    async def _do_install_from_message(
        self, trigger: discord.Message, ext_data: dict
    ) -> None:
        """
        Message-based install triggered by a reply. Sends its own progress
        message as a reply and edits it through to the final result.
        """
        marketplace = self._marketplace_cog()

        progress = await trigger.reply(
            embed=discord.Embed(
                title="📥 Downloading…",
                description=f"Fetching **{ext_data['title']}** from the Zygnal Extension Portal…",
                color=discord.Color.blue(),
            )
        )

        filepath, msg = await marketplace.download_extension(ext_data)
        if not filepath:
            await progress.edit(
                embed=_build_fail_embed(ext_data, msg),
                view=_RetryInstallView(self, ext_data, trigger.author.id),
            )
            return

        load_exc = await self._try_load(Path(filepath).stem)
        await progress.edit(embed=_build_result_embed(ext_data, filepath, load_exc))
        logger.info(f"ZExtensionAI: (reply) installed {ext_data['title']} id={ext_data['id']} → {filepath}")

    async def _try_load(self, ext_stem: str) -> Optional[Exception]:
        
        try:
            await self.bot.load_extension(f"extensions.{ext_stem}")
            return None
        except Exception as exc:
            return exc



    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if not message.reference or not message.reference.message_id:
            return

        ref_id = message.reference.message_id
        self._cleanup_reply_store()
        if ref_id not in self._reply_store:
            return

        owner_id = getattr(self.bot, "bot_owner_id", None)
        intent   = _classify_reply_intent(message.content)

        if intent == "INSTALL":
            if not owner_id or message.author.id != owner_id:
                await message.reply("> 🔒 Only the bot owner can install extensions.", mention_author=False)
                return
            await self._handle_install_reply(message, ref_id, owner_id)
        elif intent == "QUESTION":
            await self._handle_followup_question(message, ref_id)


    async def _handle_install_reply(
        self, message: discord.Message, ref_id: int, owner_id: int
    ) -> None:
        
        store_entry = self._reply_store[ref_id]
        extensions  = store_entry["extensions"]
        all_exts    = store_entry.get("all_extensions", extensions)


        candidates  = _pick_followup_extensions(message.content, extensions)
        if candidates == extensions and len(all_exts) > len(extensions):
            candidates = _pick_followup_extensions(message.content, all_exts)

        working = [e for e in candidates if e.get("status") == "working"] or candidates
        if not working:
            return

        ext_data = working[0]
        marketplace = self._marketplace_cog()

        if not marketplace:
            await message.reply(
                embed=discord.Embed(
                    title="❌ Marketplace Not Available",
                    description=(
                        "The `ExtensionMarketplace` cog isn't loaded — can't install automatically.\n"
                        f"[Download **{ext_data['title']}** manually from the portal]({_portal_link(ext_data)})"
                    ),
                    color=discord.Color.red(),
                ),
                mention_author=False,
            )
            return

        accepted = await marketplace.check_license_acceptance(message.author.id)
        if not accepted:
            embed = discord.Embed(
                title="📜 Marketplace Licence Agreement",
                description=(
                    f"Before I install **{ext_data['title']}**, you need to accept the marketplace licence.\n\n"
                    "**Terms:**\n"
                    "1️⃣ Extensions may only be used within the **ZygnalBot / ZDBF ecosystem**\n"
                    "2️⃣ Do **not** remove names: **ZygnalBot**, **TheHolyOneZ**, **TheZ**\n"
                    "3️⃣ Respect each extension's individual licence (top of each file)\n"
                    "4️⃣ Do **not** redistribute extensions outside authorised systems\n"
                    "5️⃣ Violations → permanent **ZygnalID deactivation & ban**\n\n"
                    "Accept below and the installation will start immediately."
                ),
                color=discord.Color.gold(),
            )
            embed.set_footer(text="Copyright © 2025 TheHolyOneZ (TheZ) • All Rights Reserved")
            await message.reply(embed=embed, view=_ReplyLicenseView(self, ext_data, owner_id), mention_author=False)
            return

        await self._do_install_from_message(message, ext_data)

    async def _handle_followup_question(
        self, message: discord.Message, ref_id: int
    ) -> None:
        
        store_entry   = self._reply_store[ref_id]
        extensions    = store_entry["extensions"]
        all_exts      = store_entry.get("all_extensions", extensions)
        history: List[Tuple[str, str]] = store_entry.get("history", [])

        remaining = self._cooldown_remaining(message.author.id)
        if remaining:
            await message.reply(
                f"> ⏳ Please wait **{remaining:.1f}s** before asking again.",
                mention_author=False,
            )
            return


        focused = _pick_followup_extensions(message.content, extensions)
        if focused == extensions and len(all_exts) > len(extensions):
            focused = _pick_followup_extensions(message.content, all_exts)
        previous_response = await self._fetch_ref_embed_text(message)
        show_install      = bool(_INTEREST_RE.search(message.content))

        async with message.channel.typing():
            if self.llm.loaded:
                prompt = _build_followup_prompt(message.content, focused, history, previous_response)
                answer = await self.llm.generate(prompt)
            else:
                answer = ""

            if not answer:
                answer      = _fallback_followup(message.content, focused)
                footer_note = "⚠️ Keyword mode — add a `.gguf` model to `models/` for full AI responses."
            else:
                footer_note = (
                    f"Context: {', '.join(e['title'] for e in focused[:2])} • Zygnal Extension Portal"
                )

            if len(answer) > 4000:
                answer = answer[:3990] + "\n…*(truncated)*"

            embed = discord.Embed(
                title="💬 ZDBF-AI",
                description=answer,
                color=discord.Color.from_rgb(88, 101, 242),
            )
            portal_links = "  ·  ".join(
                f"[{e['title']}]({_portal_link(e)})" for e in focused[:3]
            )
            embed.add_field(name="🌐 View on Portal", value=portal_links, inline=False)
            embed.add_field(
                name="💬 Keep chatting",
                value="Reply to this message — ask anything or say **install [name]** to download.",
                inline=False,
            )
            embed.set_footer(text=footer_note)

            view      = _ZAIResponseView(self, focused, message.author.id, show_install=show_install)
            reply_msg = await message.reply(embed=embed, view=view, mention_author=False)

            if reply_msg:
                new_history = history + [
                    ("user",      message.content),
                    ("assistant", answer),
                ]
                self._reply_store[reply_msg.id] = {
                    "extensions":     focused,
                    "all_extensions": extensions,
                    "ts":             time.monotonic(),
                    "history":        new_history[-8:],
                }



    @commands.hybrid_group(
        name="zai",
        fallback="ask",
        invoke_without_command=True,
        description="ZDBF Extension AI — ask questions about Zygnal extensions.",
    )
    @app_commands.describe(question="Your question about Zygnal extensions")
    async def zai(self, ctx: commands.Context, *, question: str) -> None:
        
        await self._do_ask(ctx, question)

    @zai.command(name="find", description="Search the extension portal by name or keyword.")
    @app_commands.describe(query="Extension name or category to search for")
    async def zai_find(self, ctx: commands.Context, *, query: str) -> None:
        
        if await self._not_ready(ctx):
            return
        results = self.kb.search(query, top_k=6)
        if not results:
            await ctx.send(
                f"> No extensions found matching **{discord.utils.escape_markdown(query)}**.\n"
                f"> Browse everything at {_PORTAL_STORE}",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title=f"Search: {query}",
            description=f"Found **{len(results)}** result(s) on the Zygnal Extension Portal.",
            color=discord.Color.blurple(),
        )
        for ext in results[:6]:
            si   = "✅" if ext["status"] == "working" else "⚠️"
            cmds = _extract_commands(ext.get("details", ""))
            cp   = f"\n`{'` · `'.join(cmds[:3])}`" if cmds else ""
            embed.add_field(
                name=f"{si} {ext['title']}  v{ext['version']}",
                value=(
                    f"{ext['description'][:130]}...{cp}\n"
                    f"*by {ext.get('creator', 'Unknown')}* · "
                    f"[View on Portal]({_portal_link(ext)})"
                ),
                inline=False,
            )
        embed.set_footer(text=f"Zygnal Extension Portal • {_PORTAL_STORE}")
        await ctx.send(embed=embed)

    @zai.command(name="list", description="List all available extensions on the portal.")
    async def zai_list(self, ctx: commands.Context) -> None:
        
        if await self._not_ready(ctx):
            return
        if not self.kb.extensions:
            await ctx.send("> Extension list is empty — try `/zai refresh`.")
            return
        working = [e for e in self.kb.extensions if e["status"] == "working"]
        other   = [e for e in self.kb.extensions if e["status"] != "working"]
        embed   = discord.Embed(
            title=f"Zygnal Extension Portal — {len(self.kb.extensions)} Extensions",
            description=(
                f"**{len(working)} working** · {len(other)} other status\n"
                f"Use `/zai find <keyword>` to search, `/zai ask <question>` for AI recommendations.\n"
                f"Browse everything at [{_PORTAL_STORE}]({_PORTAL_STORE})"
            ),
            color=discord.Color.blurple(),
        )
        chunk = working[:18]
        names = "  ".join(f"`{e['title']}`" for e in chunk)
        if len(working) > 18:
            names += f"\n*+{len(working) - 18} more — use `/zai find`*"
        embed.add_field(name="✅ Working Extensions", value=names or "None", inline=False)
        if other:
            embed.add_field(
                name="⚠️ Other Status",
                value="  ".join(f"`{e['title']}`" for e in other[:10]),
                inline=False,
            )
        embed.set_footer(text=f"Zygnal Extension Portal • {_PORTAL_STORE}")
        await ctx.send(embed=embed)

    @zai.command(name="status", description="Show ZExtensionAI system status.")
    async def zai_status(self, ctx: commands.Context) -> None:
        
        search_mode = (
            "Semantic (sentence-transformers)"
            if _SBERT_OK and self.kb._embeddings is not None
            else "Keyword only"
        )
        model_status = (
            f"✅ `{self.llm.model_name}`" if self.llm.loaded
            else ("❌ No `.gguf` in `models/`" if _LLAMA_OK else "❌ `llama-cpp-python` not installed")
        )
        last_refresh = "Never"
        if self.kb._last_refresh:
            ago = int(time.monotonic() - self.kb._last_refresh)
            last_refresh = f"{ago // 60}m {ago % 60}s ago"
        mp_status = "✅ Loaded" if self._marketplace_cog() else "❌ Not loaded (installs won't work)"
        embed = discord.Embed(
            title="ZExtensionAI — System Status",
            color=discord.Color.green() if self._ready else discord.Color.orange(),
        )
        embed.add_field(name="Ready",       value="✅ Yes" if self._ready else "⏳ Loading…", inline=True)
        embed.add_field(name="Extensions",  value=str(len(self.kb.extensions)),               inline=True)
        embed.add_field(name="Search",      value=search_mode,                                inline=False)
        embed.add_field(name="AI Model",    value=model_status,                               inline=False)
        embed.add_field(name="Marketplace", value=mp_status,                                  inline=False)
        embed.add_field(name="Last Refresh",value=last_refresh,                               inline=True)
        embed.add_field(name="Next Refresh",value=f"in ~{_CACHE_TTL // 60}m",                 inline=True)
        embed.set_footer(text="ZExtensionAI v1.9.4.0 • ZDBF")
        await ctx.send(embed=embed)

    @zai.command(name="refresh", description="Force refresh the extension cache. (Owner only)")
    @commands.is_owner()
    async def zai_refresh(self, ctx: commands.Context) -> None:
        
        msg = await ctx.send("> ⏳ Refreshing extension cache from portal API…")
        ok  = await self.kb.refresh(force=True)
        await msg.edit(
            content=(
                f"> ✅ Cache refreshed — **{len(self.kb.extensions)}** extensions loaded."
                if ok else
                "> ❌ Refresh failed. Check bot logs for details."
            )
        )



    async def _do_ask(self, ctx: commands.Context, question: str) -> None:
        remaining = self._cooldown_remaining(ctx.author.id)
        if remaining:
            await ctx.send(f"> ⏳ Please wait **{remaining:.1f}s** before asking again.", ephemeral=True)
            return
        if await self._not_ready(ctx):
            return

        async with ctx.typing():
            results = self.kb.search(question, top_k=_TOP_K)
            if not results:
                await ctx.send(
                    embed=discord.Embed(
                        title="No Matching Extensions",
                        description=(
                            "I couldn't find any relevant extensions for your question.\n"
                            f"Try `/zai list` to browse everything, or visit [{_PORTAL_STORE}]({_PORTAL_STORE})."
                        ),
                        color=discord.Color.orange(),
                    )
                )
                return

            answer = await self.llm.generate(_build_prompt(question, results)) if self.llm.loaded else ""
            if not answer:
                answer      = _fallback_text(question, results)
                footer_note = "⚠️ Keyword mode — add a `.gguf` model to `models/` for full AI responses."
            else:
                footer_note = f"Sources: {', '.join(r['title'] for r in results[:3])} • Zygnal Extension Portal"

            if len(answer) > 4000:
                answer = answer[:3990] + "\n…*(truncated)*"

            embed = discord.Embed(
                title="ZDBF Extension AI",
                description=answer,
                color=discord.Color.blurple(),
            )
            portal_links = "  ·  ".join(
                f"[{r['title']}]({_portal_link(r)})" for r in results[:3]
            )
            embed.add_field(name="🌐 View on Portal", value=portal_links, inline=False)
            embed.add_field(
                name="💬 Keep chatting",
                value='Reply to this message — "what does this one do?", "show commands", **install [name]**, etc.',
                inline=False,
            )
            embed.set_footer(text=footer_note)

            view = _ZAIResponseView(self, results, ctx.author.id)
            msg  = await ctx.send(embed=embed, view=view)


            if msg:
                self._reply_store[msg.id] = {
                    "extensions": results,
                    "ts":         time.monotonic(),
                    "history":    [],
                }

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ZExtensionAI(bot))
