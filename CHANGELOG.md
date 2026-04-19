## [Feature] — 2026-04-19 — v1.9.4.1 ✨ NEW

### `cogs/ZExtensionAI.py` — Conversational Reply Engine

**Upgrade to the ZExtensionAI cog.** All changes are backward-compatible — existing `!zai` / `/zai` commands and initial responses are unchanged. New behavior activates when a user replies to a bot ZAI message.

**Intent classification:**
- `_classify_reply_intent(text)` — distinguishes `"INSTALL"` (install/download/get/add/load), `"QUESTION"` (what/how/does/commands/tell me/etc. or `?`), and `"UNKNOWN"` (ignored silently).
- `_QUESTION_RE` regex covers 30+ question-signal words; no more "always assume install intent."
- `_INTEREST_RE` — separate lighter regex used to decide whether to show install buttons on follow-up answers (want/try/need/get/use/setup).

**Context-aware follow-up answers (`_handle_followup_question`):**
- `_fetch_ref_embed_text()` — fetches the bot's own previous embed (via `message.reference.resolved` or `channel.fetch_message`), strips portal/tip fields, injects the description + field values as `"Your previous response"` into the LLM prompt. The model now knows exactly what it said.
- `_build_followup_prompt(question, extensions, history, previous_response)` — new `previous_response` parameter injected between extension data and conversation history.
- `_fallback_followup(question, extensions)` — keyword-aware fallback (commands / version / author / status / setup) used when no LLM is available.

**Smart extension scoping:**
- `_pick_followup_extensions(text, extensions)` — resolves explicit name matches → ordinal words → anaphora ("it", "that one", "this") → all extensions. Returns a narrowed list.
- On follow-up, tries current focused set first; if no match found, tries `all_extensions` (full original search results) so ordinal references still work mid-conversation.
- Install path (`_handle_install_reply`) uses the same `_pick_followup_extensions` instead of the old `_pick_extension` (which always defaulted to index 0 — the root cause of wrong-extension installs).

**Conversation history chaining:**
- `_reply_store` entries now include `"history": []` (seeded by `_do_ask`).
- After each follow-up answer, the new reply message ID is also stored in `_reply_store` with `"extensions": focused` (the narrowed set from this turn), `"all_extensions"` (original full set), and `"history"` capped at 8 entries (4 turns).
- Conversations chain indefinitely — every reply is reply-able.

**Conditional install buttons:**
- `_ZAIResponseView` gains `show_install: bool = True` parameter.
- Follow-up answers pass `show_install = bool(_INTEREST_RE.search(message.content))` — install buttons appear only when the user's message contains download intent words, not on pure questions.

**User-facing awareness:**
- Every AI response (initial `_do_ask` + every follow-up) now includes a `💬 Keep chatting` embed field with example prompts so users always know they can reply.

**Bug fixes included:**
- Wrong extension installed when replying "install that one" mid-conversation — caused by stale full result list in chain store defaulting to `extensions[0]`. Fixed by storing `focused` in chain and using `_pick_followup_extensions` in install path.

---

## [Feature] — 2026-04-19 — v1.9.4.0

### `cogs/ZExtensionAI.py` — Local RAG-based Extension AI Assistant

**Brand-new cog.** A fully local, offline-capable AI assistant that answers questions about extensions from the Zygnal Extension Portal. No cloud API key required — runs entirely on your own hardware using a downloaded `.gguf` model.

**Architecture — Retrieval-Augmented Generation (RAG):**
- On startup, fetches all extensions from the portal API and caches them to `data/zai_extension_cache.json`.
- If `sentence-transformers` is installed, builds a local semantic embedding index (using `all-MiniLM-L6-v2`) for intelligent similarity search. Falls back to keyword search automatically if not available.
- If a `.gguf` model is present in `models/` and `llama-cpp-python` is installed, loads the model in-process via `llama-cpp-python`. Supports CPU, AMD ROCm (`DGGML_HIPBLAS`), and NVIDIA CUDA builds.
- Extension cache auto-refreshes every hour via a background task — new extensions added to the portal are picked up automatically with no restart required.

**Commands (all hybrid — work as both slash commands and `!` prefix / `@bot` mention):**
- `!zai <question>` / `/zai <question>` — Ask the AI anything about extensions (fallback, same as `ask`).
- `!zai ask <question>` / `/zai ask` — Get an AI-generated recommendation or answer sourced from portal extension data.
- `!zai find <keyword>` / `/zai find` — Search extensions by name, category, or keyword. Returns up to 6 results with descriptions and extracted commands.
- `!zai list` / `/zai list` — Show all extensions grouped by status with a preview list.
- `!zai status` / `/zai status` — Display engine status: extensions loaded, search mode, model loaded/name, last refresh time.
- `!zai refresh` / `/zai refresh` — Force-refresh the extension cache from the portal API. **Bot Owner only.**

**Prompt engineering:**
- Top-K matched extensions (default 5) are injected into a structured Llama-3 instruct prompt.
- Extension details (markdown) are stripped and trimmed to 900 chars per extension.
- Slash commands found in extension details are extracted and highlighted so the LLM cites them exactly.
- Temperature set to 0.25 for consistent, factual answers with minimal hallucination.

**Graceful degradation:** Every component is independently optional. The cog loads and functions correctly with none, some, or all optional dependencies installed:
- No `sentence-transformers` → keyword search.
- No `.gguf` model or `llama-cpp-python` → keyword-based fallback answer (still useful).
- No `aiohttp` (already in base requirements) → loads from cache file.

**New files:**
- `cogs/ZExtensionAI.py` — the cog.
- `data/zai_extension_cache.json` — auto-created on first run.
- `models/` — directory for `.gguf` model files (auto-created, gitignored).

---

## [Fix] — 2026-03-07 -> 2026-03-25                v1.9.1.0 → v1.9.2.0

41 confirmed bug fixes across 13 cogs

---

### `cogs/framework_diagnostics.py`
- [FIX] `generate_diagnostics()` accessed `self.bot.bot_owner_id`, `self.bot.extension_load_times`, `self.bot.db.conn`, `self.bot.db.base_path`, and `self.bot.config` without guards. Any one missing attribute raised `AttributeError` caught generically, returning `None` with no useful detail. All replaced with `getattr(...)` guards.
- [FIX] `loop_lag_monitor` ran every 1 second (86,400 scheduling events/day). Changed to `@tasks.loop(seconds=5)` and `expected_interval = 5.0`.
- [FIX] `_send_alert` called `.send()` unconditionally on any channel type. If the configured channel was a voice, stage, or forum channel, `send()` raised `HTTPException` caught generically. Added `isinstance(channel, discord.TextChannel)` check.
- [FIX] Write-failure alert in `generate_diagnostics()` fired on every failure with no debounce. Added `_last_write_alert_time` — alert only fires if >300 seconds since last write alert.

### `cogs/shard_monitor.py`
- [FIX] `save_metrics` and `_save_alert_config` used synchronous `open()` + `json.dump()` directly on the event loop, blocking all coroutines during disk writes. Both now use `await asyncio.to_thread(...)`. `_save_alert_config` is now `async def`.
- [FIX] `ShardMetrics.is_healthy()` hardcoded `consecutive_failures >= 3` regardless of the configurable `alert_threshold` on `ShardMonitor`. Added `threshold: int = 3` parameter. `health_check` and `_build_health_embed` now pass `self.alert_threshold`.

### `cogs/shard_manager.py`
- [FIX] `_seen_nonces` was a `set` trimmed via `set(list(...)[half:]` — `set` has no ordering so the "keep newest half" logic randomly discarded nonces, potentially re-allowing replay of recently seen ones. Replaced with `collections.deque(maxlen=10000)` which auto-drops the oldest.
- [FIX] `sync_stats` loop had no `try/except`. An unhandled exception silently killed the task permanently with no alert. Wrapped body in `try/except Exception as e: logger.error(...)`.

### `cogs/event_hooks.py`
- [FIX] Queue-full fallback in `emit_hook` called `await self._hook_queue.put(hook_data)` with no timeout on a still-full queue, suspending the emitter indefinitely. The `except asyncio.QueueFull` below it was dead code since `queue.put()` never raises `QueueFull`. Replaced fallback with `put_nowait()` inside `try/except asyncio.QueueFull`.
- [FIX] `hook_id` used `callback.__name__` — two callbacks in different cogs with the same function name shared one `hook_id`, causing one to overwrite the other. Changed to `callback.__module__.callback.__qualname__` for guaranteed uniqueness.
- [FIX] `disable_hook()` checked `if hook_id not in self.hooks` where `self.hooks` is keyed by event_name (e.g. `"bot_ready"`), not hook_id (e.g. `"bot_ready:module.func"`). This check always evaluated True, making `disable_hook` always return `False` — `/eh_disable` was completely broken (regression from v1.9.1.0). Now iterates hooks to find a matching `hook_id`.
- [FIX] `cog_unload` called `self._worker_task.cancel()` but did not await it, leaving cleanup from `CancelledError` unguaranteed. Changed `cog_unload` to `async def` and added `await self._worker_task` in `try/except asyncio.CancelledError`.

### `cogs/plugin_registry.py`
- [FIX] `PluginListView` had no `on_timeout` — after the 120s timeout the cog reference stayed alive and buttons remained visually enabled. Added `async def on_timeout` that clears `self._cog` and disables all buttons.

### `cogs/slash_command_limiter.py`
- [FIX] Debug log used `logging.FileHandler` with no rotation or size cap, growing indefinitely. Replaced with `logging.handlers.RotatingFileHandler(maxBytes=5MB, backupCount=2)`.
- [FIX] `/slashlimit` had no access control — any guild member could enumerate all blocked/converted command names. Added `@commands.is_owner()`.

---

### `cogs/GeminiService.py`
- [FIX] No `cog_load` validation for `GEMINI_API_KEY` — if the key was missing, the cog loaded silently and only failed at first invocation with a confusing error. Added `cog_load` that logs CRITICAL if the key is absent.
- [FIX] No `cog_unload` — hot-reloading left `_user_cooldowns` and `_ai_cache` populated with stale state from the previous config. Added `cog_unload` that clears both dicts.

### `cogs/GeminiServiceHelper.py`
- [FIX] Sessions were only written to disk synchronously on each message send. A crash between sends lost the latest entry. Added a `@tasks.loop(seconds=60)` auto-save task with a dirty flag — sessions are now also persisted periodically as a safety net.

### `cogs/live_monitor.py` + `ReUseInfos/live_monitor_helper.py`
- [FIX] `_load_config` caught JSON parse errors with a bare `except: pass` and returned defaults silently. Operators had no indication config was reset. Changed to `except Exception as e: logger.error(...)` including the config file path and exception detail.

### `cogs/EventHooksCreater.py`
- [FIX] `_cooldowns` dict accumulated one entry per (hook_id, user_id) pair seen and grew indefinitely. Added eviction in `_check_cooldown` — entries older than `cooldown_seconds * 2` are pruned on each cooldown check.
- [FIX] `_user_message_counts` grew indefinitely (one entry per unique user ever seen). Added a cleanup step in `analytics_task` (runs every 5 min) that caps the dict at 5,000 users by count.
- [FIX] `_execute_webhook` created a new `aiohttp.ClientSession` per invocation, defeating connection pooling. Added `self._http_session` created in `cog_load` and closed in `cog_unload`. `_execute_webhook` now reuses the shared session. Changed `cog_unload` to `async def`.

### `cogs/event_hooks.py`
- [FIX] `_add_to_history` per-event pruning used `h not in events_to_remove` where `events_to_remove` is a list of dicts — dict equality is O(n), making the pruning O(n²). Replaced with `{id(h) for h in ...}` set for O(n) membership checks.

### `cogs/shard_monitor.py`
- [FIX] `is_bot_owner()` returned False for the real bot owner when `BOT_OWNER_ID` was `0` (env var not set), locking the owner out of all commands. Updated predicate to try `BOT_OWNER_ID` first, then fall back to `application_info().owner.id`.

### `cogs/shard_manager.py`
- [FIX] Default `SHARD_IPC_SECRET = "change_me_please"` only logged a `WARNING` and continued loading, allowing IPC to run with a known-public secret. Escalated to `CRITICAL` log and early `return` — the cog will not load at all until a real secret is configured.

---

### `cogs/GeminiService.py` (MEDIUM batch)
- [FIX] Cache lookup happened after `PluginRegistry.get_all_plugins()`, `generate_diagnostics()`, etc. were already called — cache hits still paid the full I/O cost. Moved cache check to before context-gathering; a cache hit now skips all framework calls and returns immediately.
- [FIX] `_user_cooldowns` and `_ai_cache` grew without bound. Added `@tasks.loop(minutes=5)` `_cleanup_cache_task` that evicts cooldown entries older than `COOLDOWN_SECONDS * 2` and cache entries older than `CACHE_TTL`.
- [FIX] `_active_requests` was an unprotected plain integer. Replaced with `asyncio.Semaphore(_MAX_CONCURRENT)`. Guard uses `semaphore.locked()`, acquire/release in `finally`.

### `cogs/GeminiServiceHelper.py` (MEDIUM batch)
- [FIX] `_save_sessions` called `Path.write_text()` synchronously inside an async method, blocking the event loop on large session files. Wrapped with `await asyncio.to_thread(lambda: ...)`.
- [FIX] `_gather_tool_context` stopped at the first matching cog name with a `break`, silently ignoring further cog mentions in the same message. Removed `break` — all matching cog names are now collected.

### `cogs/EventHooksCreater.py` (MEDIUM batch)
- [FIX] `_execute_webhook` passed any user-supplied URL directly to `aiohttp.ClientSession.post()` with no validation, enabling SSRF to internal services. Added URL prefix check — only `discord.com`, `discordapp.com`, `ptb.discord.com`, and `canary.discord.com` webhook URLs are permitted.

### `cogs/plugin_registry.py` (MEDIUM batch)
- [FIX] `check_dependencies` operator extraction used `">=" if ">=" in required_version else "=="`, silently mapping `>1.0.0` or `<=2.0.0` to `==`. Replaced with `re.match(r'([><=!]+)', ...)` for correct extraction of any operator.
- [FIX] `save_registry` failures were logged but had no operator alert. Added `_save_failure_count` counter — after 3 consecutive failures `_send_alert` fires a critical message warning that disk state is stale.

### `cogs/backup_restore.py` (MEDIUM batch)
- [FIX] `_download_image_b64` created a new `aiohttp.ClientSession` per image. A backup with 50 emojis + stickers + icon + banner opened 57+ sessions sequentially. `capture()` now creates one shared session and passes it to all `_download_image_b64` calls via a new `session` parameter.
- [FIX] Banner was captured as base64 during backup but `_do_restore` never applied it. Added banner restore after icon restore in the `server_settings` block: `await guild.edit(banner=banner_bytes, ...)`.

### `cogs/event_hooks.py` (MEDIUM batch)
- [FIX] `alert_channel_id` was in-memory only — lost on every restart, leaving the alert system permanently silent after a reload. Added `_load_config`/`_save_config` backed by `./data/event_hooks_config.json`; `alert_channel_id` is persisted on every `/eh_alert_channel` call.
- [FIX] `_worker_restart_count` never reset — a bot that crashed twice a year could permanently exhaust its 10-restart budget. `_restart_worker` now resets the counter to 0 if the worker ran stably for >1 hour before the current crash.

### `cogs/Guild_settings.py` (MEDIUM batch)
- [FIX] `get_guild_mention_prefix_enabled`, `get_guild_prefix`, and `set_guild_mention_prefix_enabled` were called without `try/except`. A DB failure propagated to the global error handler with no user-friendly context. All DB calls now wrapped with `try/except Exception as e` — users see `"❌ Could not read/update guild settings — please try again."` and the error is logged at `ERROR` level.

### `[DEFERRED — live_monitor.py — MEDIUM]`
- **ClientSession per tick:** New `aiohttp.ClientSession` created on every data-push tick for every package. Fix requires refactoring `live_monitor.py` (29k lines) — deferred to a future release.
- **`_command_usage` unbounded:** Accumulates one entry per unique command name ever used. Fix requires same file — deferred.


---

## [Fix] — 2026-03-25 — v1.9.2.0 

18 fixes across `atomic_file_system.py`, `main.py`, and 8 cog files

---

### `atomic_file_system.py`
- [FIX] `_get_cache_key` hashed filepaths with MD5 for no reason — added CPU overhead with zero benefit. Replaced with using the filepath string directly as the cache key. Removed `hashlib` import.
- [FIX] `_get_lock` stored a creation timestamp but never updated it on use. `_cleanup_locks` used this stale timestamp, causing premature cleanup of actively-used locks. Lock timestamps now update on every access.
- [FIX] `atomic_write` had a double-close bug on Windows. `tempfile.mkstemp` returns an open fd, then `aiofiles.open` opened the same path by name — the fd was closed after writing, but could conflict with the aiofiles handle on Windows. Moved `os.close(temp_fd)` to immediately after `mkstemp`, before `aiofiles.open`. Removed the duplicate `os.close` in the error handler.
- [FIX] `SafeDatabaseManager.__init__` accepted a `file_handler` parameter that was stored but never used — misleading API. Removed the parameter and updated callers.
- [FIX] `SafeLogRotator.should_rotate` was `async` but only performed synchronous `Path.exists()` and `Path.stat()` calls. Made it a regular sync method. Updated callers.

### `main.py`
- [FIX] `PrefixCache` only cached the prefix string, not the mention-prefix setting. `get_guild_mention_prefix_enabled()` hit the database on every guild message (cache miss). Extended cache to store `(prefix, mention_enabled)` tuple — eliminates one DB query per message.
- [FIX] Help menu displayed `<@BOT_ID> commandname` instead of `!commandname` in category embeds. `get_prefix` returns a list like `['<@BOT_ID> ', '!']` when mention prefix is enabled; the code took `prefix[0]` (the mention) instead of `prefix[-1]` (the actual prefix). Fixed to use `prefix[-1]`.
- [FIX] `create_page_embed` was copy-pasted identically in `CategorySelect`, `PrevButton`, and `NextButton` (3 copies, ~50 lines each). Extracted into a single shared `_create_command_page_embed()` function.
- [FIX] `status_update_task` bypassed the bot's own `SafeConfig` — did raw `open("config.json")` + `json.load()` on every tick, ignoring the atomic file system and its cache. Replaced with `self.config.data`.
- [FIX] Every `@is_bot_owner()` command also had an inner `check_app_command_permissions()` call — redundant since the decorator already validates ownership for both prefix and slash contexts. Removed the inner check from 9 owner-only commands (`cleanup`, `atomic_test_main`, `cachestats`, `sync`, `reload`, `load`, `unload`, `dbstats`, `integritycheck`).
- [FIX] ~30 bare `except: pass` blocks (mostly wrapping `ctx.message.delete()`) swallowed all exceptions including `KeyboardInterrupt` and `SystemExit`. Replaced with `except (discord.HTTPException, discord.NotFound): pass` for message deletions and `except OSError: pass` for file removals.
- [FIX] `on_ready` called `sync_commands()` — `on_ready` fires on every reconnect, not just the first connect. While a `_slash_synced` guard prevented duplicate syncs, the call belonged in `setup_hook` which runs exactly once. Moved sync to `setup_hook`, removed from `on_ready`.
- [FIX] `reload_command` and `load_command` had identical space-to-underscore rename logic (~45 lines each). Extracted into `_resolve_extension_path()` helper returning `(resolved_name, rename_message, error_embed)`.
- [FIX] `cleanup_command` and `cachestats_command` referenced wrong dict keys from `get_cache_stats()` — `cache_stats['size']` instead of `cache_stats['cache_size']`, `cache_stats['locks']` instead of `cache_stats['active_locks']`, `file_stats['max_size']` instead of `file_stats['max_cache_size']`. Both commands raised `KeyError` at runtime. Fixed all key names.

### Cog files — logger namespaces
- [FIX] All 8 cog files used `logging.getLogger('discord')`, making it impossible to filter logs per-cog. Changed to `logging.getLogger('discord.cogs.<name>')` in: `event_hooks.py`, `framework_diagnostics.py`, `backup_restore.py`, `Guild_settings.py`, `EventHooksCreater.py`, `plugin_registry.py`, `shard_manager.py`, `shard_monitor.py`. Child loggers inherit parent handlers — no config changes needed.

### `cogs/GeminiService.py`
- [FIX] Called `load_dotenv()` redundantly — already called in `main.py` before any cogs load. Removed along with the unused `from dotenv import load_dotenv` import.

### `cogs/Guild_settings.py`
- [FIX] `mention_prefix` command had an unreachable validation block (`if action not in [...]`) — the `Literal["enable", "disable", "status"]` type annotation already constrains the parameter at the discord.py/slash-command level. Removed 18 lines of dead code.




### `[KNOWN — UPCOMING v1.9.3.0]`
- **GeminiServiceHelper:** `collect_dashboard_data()` still exposes all users' AES keys and session histories. Fix requires `live_monitor` to pass the authenticated OAuth user's Discord ID to `collect_dashboard_data()` instead of `None`.











---

## [Fix] — 2026-03-04 — v1.9.0.0 → v1.9.1.0

14 confirmed bug fixes across 11 cogs

---

### `cogs/GeminiService.py`
- [FIX] Cooldown stamp `_user_cooldowns[user.id] = now` was written **before** the `_active_requests >= _MAX_CONCURRENT` check — a user rejected for capacity silently consumed their 15-second cooldown slot. Stamp now written only after all guards pass.

### `cogs/GeminiServiceHelper.py`
- [FIX] `_cmd_update_config` guard was `if owner_id is not None and requester_id != owner_id` — if `application_info()` raised an exception, `owner_id` stayed `None` and the guard was vacuously false, allowing any caller to update config. Guard inverted to `if owner_id is None or requester_id != owner_id` (deny-by-default).
- [KNOWN — UPCOMING] **Security:** `collect_dashboard_data()` iterates all sessions and includes every user's `aes_key` and full history in the polled JSON. Any authenticated dashboard user can currently read other users' encryption keys. Fix requires live_monitor to pass the authenticated dashboard user's Discord ID at data-collection time (currently hardcoded `None`). **Will be addressed in v1.9.3.0.**

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
