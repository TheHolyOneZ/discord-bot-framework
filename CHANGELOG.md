## [Patch] - 2026-02-25

### Fixed

#### `cogs/EventHooksCreater.py` — Async I/O fix
- `_save_analytics()` was a synchronous function called from an async background task (`analytics_task`, runs every 5 minutes). Using `open()` + `json.dump()` in a sync function inside an async context blocks the entire event loop until the write finishes — meaning the bot cannot process any messages, commands, or Discord heartbeats during that time.
- `_save_created_hooks()` had the same problem and is called in over a dozen places across async event handlers and command callbacks.
- **Fix:** Both functions converted to `async def` using `aiofiles`. All 13 call sites updated to `await self._save_created_hooks()`. `analytics_task` updated to `await self._save_analytics()`.
- Behaviour is identical — hooks and analytics are still saved to the same JSON files at the same times. Only the I/O is now non-blocking.

#### `cogs/GeminiService.py` — Path traversal fix
- The `/ask_zdbf` command's `file` and `extension` actions sanitized user-supplied file paths using `file.lstrip("./\\").replace("..", "")`. This was incorrect: `lstrip` strips individual characters from the left edge, not a literal prefix. A path like `cogs/../config.json` would survive the sanitization and resolve to `cogs/config.json`, potentially exposing files outside the intended scope.
- **Fix:** Replaced the string manipulation with `Path.resolve()` + `Path.relative_to()`. The resolved absolute path is checked to be inside the allowed directory (bot root for `file` action, `extensions/` for `extension` action) before the file is opened. If the path escapes the boundary, the command returns a clear access denied message.
- Behaviour for valid paths is identical. Paths that previously slipped through are now blocked.
