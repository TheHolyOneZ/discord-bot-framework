# Changelog

All notable changes to the Zoryx Discord Bot Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.6.1.0] - 2026-02-16

### 🎉 Nice To Have Update - Enhanced User Experience

This release introduces quality-of-life improvements that enhance user convenience and provide server administrators with more granular control over bot behavior. While not essential for operation, these features significantly improve the day-to-day user experience.

---

### ✨ Added

#### **@Mention Prefix Support**
- **Feature:** Users can now invoke commands using `@BotName command` syntax
- **Why It's Nice:** Eliminates the "what's the prefix?" question - users can always mention the bot
- **Example:** `@BotName help` works just like `!help` or `/help`
- **Configuration:** Globally configurable via `config.json`
- **Default:** Enabled (can be disabled if preferred)

#### **Per-Guild Mention Prefix Configuration**
- **Feature:** Server administrators can enable/disable @mention prefix independently for their server
- **Why It's Nice:** Large servers may want to reduce noise, while small communities may prefer the convenience
- **Commands Added:**
  - `!mentionprefix enable` - Enable @mention prefix for the server
  - `!mentionprefix disable` - Disable @mention prefix for the server
  - `!mentionprefix status` - Check current configuration
- **Permission Required:** Administrator
- **Storage:** Per-guild settings saved in database

#### **Guild Settings Dashboard**
- **Feature:** New `!serversettings` command displays all server configuration at a glance
- **Why It's Nice:** Server admins can quickly review all bot settings without checking multiple commands
- **Shows:**
  - Custom prefix (if set)
  - Mention prefix status
  - Server information
  - Available command invocation methods
- **Permission Required:** Administrator

#### **New Framework Cog: GuildSettings**
- **Location:** `cogs/guild_settings.py`
- **Purpose:** Centralized management for per-guild configuration
- **Extensibility:** Easy to add more per-guild settings in the future
- **Features:**
  - Comprehensive error handling
  - Detailed user feedback via embeds
  - Full logging of configuration changes
  - Guild context validation

---

### 🔧 Changed

#### **Prefix Resolution System**
- **Updated:** `get_prefix()` method now checks per-guild database settings
- **Fallback Logic:** Uses global config if no guild-specific setting exists
- **Performance:** Minimal overhead - single database query per prefix check
- **Compatibility:** Fully backward compatible with existing prefix behavior

#### **Help Menu Display**
- **Enhanced:** Help menu now shows mention prefix option when enabled
- **Smart Display:** Automatically updates based on guild configuration
- **Example:** `Current Prefix: ! or @BotName` (when enabled)
- **DM Support:** Correctly displays global config in direct messages

#### **Database Schema**
- **Addition:** `guild_settings` table now supports `mention_prefix_enabled` key
- **Format:** Stores '1' (enabled) or '0' (disabled)
- **Migration:** No migration needed - created on-demand when first set
- **Cleanup:** Existing tables and data remain untouched

---

### 📚 Database Methods Added

#### **SafeDatabaseManager Extensions**
```python
# New methods in atomic_file_system.py
async def get_guild_mention_prefix_enabled(guild_id: int) -> Optional[bool]
async def set_guild_mention_prefix_enabled(guild_id: int, enabled: bool)
```
- **Purpose:** Store and retrieve per-guild mention prefix configuration
- **Returns:** `None` if no setting (uses global default), `True/False` otherwise
- **Thread-Safe:** Integrated with existing connection pooling system

---

### 📝 Configuration Changes

#### **config.json**
- **New Field:** `"allow_mention_prefix": true`
- **Default:** `true` (enabled)
- **Purpose:** Sets global default for servers without specific configuration
- **Impact:** No breaking changes - defaults to enabled for convenience

---

### 🎨 User Experience Improvements

#### **Command Invocation Methods**
Users now have **up to 3 ways** to invoke commands:
1. **Prefix Commands:** `!help` (traditional)
2. **Slash Commands:** `/help` (modern Discord UI)
3. **Mention Commands:** `@BotName help` (convenient, if enabled)

#### **Smart Help Integration**
- Help menu adapts to show available methods
- Clear indication when mention prefix is disabled
- Consistent display across all help views
- Back button maintains correct prefix information

---

### 🔒 Security & Permissions

#### **Administrator Protection**
- All new configuration commands require **Administrator** permission
- Guild-only commands - cannot be used in DMs
- Comprehensive permission error handling
- Clear error messages for unauthorized users

#### **Logging & Audit Trail**
- All configuration changes logged to bot logs
- Includes: guild ID, guild name, user who made change, and new setting
- Format: `"Mention prefix ENABLED for guild 123456 (ServerName) by User#1234"`

---

### 📖 Documentation

#### **New Documentation Files**
- `QUICK_INSTALL.md` - 5-minute setup guide
- `COMPLETE_IMPLEMENTATION_GUIDE.md` - Full technical documentation with testing procedures
- Updated system features list in credits

#### **README Updates**
- Added "@Mention Prefix Support" to system features
- Updated command examples to show all three invocation methods

---

### 🚀 Technical Improvements

#### **Code Quality**
- Added comprehensive docstrings to all new methods
- Type hints maintained throughout
- Error handling for database operations
- Graceful fallbacks for missing configurations

#### **Performance**
- Minimal overhead - single database query per prefix resolution
- Existing prefix cache system remains intact
- No impact on slash command performance
- Efficient key-value storage in existing database schema

#### **Extensibility**
- `GuildSettings` cog designed for easy expansion
- Can add more per-guild settings without structural changes
- Database schema supports additional key-value pairs
- Modular cog architecture maintained

---

### 🔄 Migration Notes

#### **Upgrading from v1.6.0.1**
1. **No database migration required** - schema extends automatically
2. **Backward compatible** - existing configurations work unchanged
3. **Recommended:** Add `"allow_mention_prefix": true` to `config.json`
4. **Optional:** Copy `guild_settings.py` to `cogs/` folder for per-guild control

#### **Upgrading from Earlier Versions**
- Follow standard upgrade procedure
- Replace: `main.py`, `config.json`, `atomic_file_system.py`
- Add: `cogs/guild_settings.py` (optional but recommended)
- Restart bot - settings auto-initialize on first use

---

### 🐛 Bug Fixes

#### **Prefix Cache Compatibility**
- Mention prefix works seamlessly with existing prefix cache system
- Cache invalidation remains consistent
- No prefix cache memory leaks

#### **Help Menu Edge Cases**
- Fixed potential issues with mention display in DMs
- Corrected prefix info display in multi-page help menus
- Back button maintains accurate prefix information

---

### ⚠️ Breaking Changes

**None.** This is a fully backward-compatible update.

---

### 📊 Statistics

- **Files Modified:** 3 (`main.py`, `config.json`, `atomic_file_system.py`)
- **Files Added:** 1 (`cogs/guild_settings.py`)
- **Lines of Code Added:** ~350
- **New Commands:** 2 (`mentionprefix`, `serversettings`)
- **New Database Methods:** 2
- **Documentation Pages:** 3

---

### 🎯 Use Cases

#### **Small Community Servers**
- Enable mention prefix for easier command discovery
- New members don't need to ask "what's the prefix?"
- More intuitive for non-technical users

#### **Large Public Servers**
- Disable mention prefix to reduce notification noise
- Keep traditional prefix for cleaner chat
- Admins have full control over bot behavior

#### **Multi-Guild Bots**
- Different settings per server based on community preference
- No need to maintain separate bot instances
- Centralized configuration with local overrides

---

### 🔮 Future Enhancements

The `GuildSettings` cog architecture enables easy addition of:
- Per-guild command cooldowns
- Per-guild auto-delete timers
- Per-guild feature toggles
- Per-guild language preferences
- Custom welcome/leave messages
- Guild-specific logging channels

---

### 📞 Support

- **GitHub Issues:** [Report bugs or request features](https://github.com/TheHolyOneZ/discord-bot-framework/issues)
- **Discord:** `gg/sgZnXca5ts`
- **Documentation:** See `QUICK_INSTALL.md` and `COMPLETE_IMPLEMENTATION_GUIDE.md`

---

### 🙏 Acknowledgments

This update was designed with user feedback in mind, focusing on making the bot more intuitive for end-users while providing administrators with the control they need.

---

### 📝 Checklist for Upgrading

- [ ] Backup existing files (`main.py`, `config.json`, `atomic_file_system.py`)
- [ ] Replace files with v1.6.1.0 versions
- [ ] Add `"allow_mention_prefix": true` to `config.json` (if not present)
- [ ] Copy `guild_settings.py` to `cogs/` folder
- [ ] Restart bot
- [ ] Test with `!mentionprefix status` in a server
- [ ] Test with `@BotName help` to verify functionality
- [ ] Review logs for successful cog loading

---

## [1.6.0.1] - Previous Version

### Features
- AI Assistant (GeminiService Cog)
- Framework Diagnostics System
- Event Hooks System with Circuit Breaker
- Plugin Registry with Dependency Management
- Slash Command Limiter
- Live Monitor Dashboard
- Atomic File Operations
- Per-Guild Database System
- Hot-Reload Capability

---

**Note:** Version 1.6.1.0 builds upon the solid foundation of 1.6.0.1, adding user convenience features without compromising stability or performance.

---

**Full Changelog:** https://github.com/TheHolyOneZ/discord-bot-framework/compare/v1.6.0.1...v1.6.1.0