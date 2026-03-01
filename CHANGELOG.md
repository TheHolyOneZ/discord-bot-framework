## [Add] — 2026-03-01 — v1.9.0.0

---

### `cogs/GeminiServiceHelper.py` — **Fully new cog**

A dedicated AI assistant embedded directly inside the Live Monitor web dashboard. No slash commands — entirely dashboard-native, accessed from the new **AI Assistant** tab (tab 21).

#### Encryption
- [ADD] AES-256-CBC end-to-end encryption: server-side via Python `cryptography` library, client-side via native Web Crypto API (`crypto.subtle`) — no external CDN, no CSP issues
- [ADD] Per-user AES keys stored server-side; new users bootstrap a key in `localStorage` which is registered on first send
- [ADD] Encrypted session history persisted to `./data/gemini_dashboard_sessions.json`

#### Context tools (auto-injected based on message keywords)
- [ADD] **Framework Info** — live bot stats (version, guild count, loaded cogs)
- [ADD] **Extension/Cog Info** — docstring and slash commands for any loaded cog, detected by cog name appearing in the message
- [ADD] **File Structure** — lists root `.py` files, `cogs/`, `data/`, and notable project files
- [ADD] **README Search** — full hierarchical breadcrumb parse of `README.md`; up to 3,000 chars from the top 4 scoring sections
- [ADD] **Capabilities** — triggered by "what can you do"-style queries; lists all tools and what the AI cannot do
- [ADD] **File Reading** — sandboxed reader; allowed: root `*.py`, `cogs/*.py`, `data/*` (direct children only); always blocked: `.env`, `gemini_dashboard_sessions.json`, live monitor config JSON files

#### Attach File (Option C)
- [ADD] **Attach File** toolbar button opens an inline row with a live-filter autocomplete dropdown above the input
- [ADD] File list pre-fetched from Python on every data poll (`available_files` in `collect_dashboard_data`) — shows only allowed paths, no blocked files
- [ADD] Multiple files: each confirmed file becomes a removable chip tag; up to 3 files read per message and injected as separate `[Tool Context — File: …]` blocks
- [ADD] Auto-detect fallback: if no explicit attachment, the message text is scanned for filenames with known extensions and the file is read automatically

#### Chat UX
- [ADD] Optimistic message bubbles — user message appears immediately; removed if a confirmed user message arrives from the server
- [ADD] Smart scroll — only auto-scrolls if user was within 120 px of the bottom; never interrupts reading older history
- [ADD] Typing indicator — persists until the AI response arrives in history (not just on POST ACK)
- [ADD] Lock + Cancel — send button and textarea disabled while waiting for response; Cancel button removes the optimistic bubble and unlocks input
- [ADD] Client-side 15-second rate limit gate with countdown feedback
- [ADD] Markdown rendering — fenced code blocks, headers, bold, italic, inline code, lists, HR — XSS-safe via `gaiEsc()`, no external dependencies
- [ADD] Capabilities popup — animated glassmorphism modal from a toolbar button listing what the AI can and cannot do

#### Configuration & permissions
- [ADD] Config drawer (owner-only): live model and system prompt override without restart; respects `GEMINI_MODEL` env var (default `gemini-2.5-flash-lite`)
- [ADD] 4 dashboard permission flags: `view_gemini_chat`, `action_gemini_send`, `action_gemini_clear_history`, `action_gemini_config`
- [ADD] Requires `pip install cryptography`

---

### `cogs/live_monitor.py` + `ReUseInfos/live_monitor_helper.py` — GeminiServiceHelper integration

- [ADD] `'gemini'` added to `$validPackages` in `_generate_receive_php()` — without this `monitor_data_gemini.json` returned 404
- [ADD] `GeminiServiceHelper.collect_dashboard_data(discord_id)` called inside `_collect_monitor_data()` and merged under key `"gemini"` in the polled JSON
- [ADD] AI Assistant tab (tab 21) injected into generated `index.php` via `LiveMonitor._get_gemini_tab_html()` — HTML/CSS/JS fully embedded in `live_monitor_helper.py` for self-contained CGI-bin deployment; `GeminiServiceHelper.get_tab_html()` removed (dead code)
- [ADD] `geminiInit(monitorData, userId)` wired into the dashboard's existing 2-second data-poll cycle
- [ADD] `handle_command()` dispatch registered for `gemini_send_message`, `gemini_clear_history`, `gemini_update_config`

---

## [Update] — 2026-02-28 — v1.8.0.0 → v1.9.0.0

---

### `cogs/EventHooksCreater.py` — Full overhaul (5.5 → 9.0+)

#### Missing template handlers implemented
- [ADD] `leveling_system` — XP awarded per message with per-user cooldown, level calculation, level-up announcements to configured channel, role rewards at configured level thresholds; XP data persisted in memory and saved via the batch save task
- [ADD] `scheduled_announcement` — recurring message/embed sent to a configured channel at a configurable interval (hours); implemented as a per-hook `asyncio.Task` started on registration and cancelled on unregister/delete/disable
- [ADD] `ticket_system` — creates a private text channel per user in a configured category when they react with a configured emoji on a configured message; support role granted access automatically; channel named via template; reaction removed after ticket creation to keep the message clean
- [ADD] `voice_activity_tracker` — logs join, leave, and mute/unmute events to a configured log channel with embed; each event type independently togglable
- [ADD] `dynamic_voice_channels` — creates a temporary voice channel in a configured category when a user joins a designated trigger channel, moves the user into it, and deletes it automatically when it becomes empty; channel named via template; active temp channels tracked in memory

#### Dead code wired in
- [FIX] `_execute_actions` is now called by all new template handlers — the generic action pipeline (send_message, add_role, remove_role, timeout, send_dm, webhook, create_role, delay, trigger_hook) is no longer dead code
- [FIX] `AdvancedConditionEngine.evaluate()` is now called at the top of every handler before executing — hooks with conditions configured (time_range, day_of_week, role_hierarchy, message_count, user_age, custom_variable) now actually respect them

#### Security
- [FIX] `eval()` in `_format_message` replaced with a safe AST-based math evaluator — only numeric constants and basic operators (+, -, *, /) are permitted; no code execution possible

#### Reliability
- [FIX] Listener accumulation fixed — `_registered_hook_ids: set` tracks which hooks have active listeners; `_register_hook` skips registration if the hook is already registered, preventing duplicate listeners from piling up on restart or re-register
- [FIX] I/O on every execution removed — `_save_created_hooks()` is no longer called after every hook fires; execution_count and error_count are updated in memory and flushed by a new `_auto_save` background task (60-second interval, dirty flag); the analytics task already saves analytics every 5 minutes
- [FIX] Channel and role ID validation at registration time — invalid IDs (non-integer, channel/role not found in guild) now return a clear error from `create_hook()` instead of failing silently at runtime

#### New Discord commands (Bot Owner / Administrator)
- [ADD] `/hooks list [page]` — paginated list of all hooks in the current guild with template name, status (enabled/disabled), execution count, error count
- [ADD] `/hooks info <hook_id>` — detailed embed showing all params, conditions, execution stats, and last execution time for a specific hook
- [ADD] `/hooks delete <hook_id>` — delete a hook with confirmation; owner-only
- [ADD] `/hooks toggle <hook_id>` — enable or disable a hook
- [ADD] `/hooks create <template_id>` — shows required and optional parameters for the template and creates the hook with provided params via command options

---

### `cogs/plugin_registry.py` — Upgrade (8.0 → 9.5+)

#### Auto-scan completeness
- [ADD] `provides_hooks` and `listens_to_hooks` are now populated during auto-scan by reading `__provides_hooks__` and `__listens_to_hooks__` module-level attributes from extension modules

#### Persistence
- [FIX] Alert channel now persisted to `./data/plugin_registry_config.json` — survives restarts
- [FIX] `enforce_dependencies` and `enforce_conflicts` states now persisted to the same config file — no longer reset to `True` on restart after being disabled via `/pr_enforce`

#### Real enforcement
- [FIX] Enforcement is no longer advisory only — when `enforce_dependencies=True` and a plugin has missing or incompatible dependencies, `register_plugin()` now refuses to register it and returns an error; same for conflict enforcement

#### UX
- [FIX] `/pr_list` now uses paginated embeds (10 plugins per page with Prev/Next buttons) — no longer hits Discord's 25-field embed limit with large plugin sets

#### Resilience
- [FIX] `extension_loaded` / `extension_unloaded` hook registration no longer depends on EventHooks being loaded — fallback uses direct `bot.add_listener()` on `on_ready` if EventHooks is absent
