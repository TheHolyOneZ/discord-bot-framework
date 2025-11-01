
# 🤖 Discord Bot Framework

A production-ready, enterprise-grade Discord bot framework featuring atomic file operations, advanced permission systems, dynamic extension loading, comprehensive monitoring, and modular framework cogs. Built for developers who demand reliability, scalability, and maintainability.

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.0+-blue.svg)](https://github.com/Rapptz/discord.py)

> Showcase images are available in the Images directory within this repository.

### Website: https://zygnalbot.com/bot-framework/

## ✨ Core Features

### 🔧 System Architecture
- **Atomic File Operations**: Thread-safe file handling with built-in caching (300s TTL)
- **SQLite Database**: Optimized with WAL mode, automatic backups, and connection pooling
- **Safe Log Rotation**: Automatic log management with configurable size limits and retention
- **Hot-Reload System**: Auto-reload extensions when files change (optional)
- **Metrics Collection**: Real-time command tracking, error monitoring, and performance analytics
- **Framework Cogs System**: Modular internal framework components with event hooks and plugin registry
- **Event Hooks System**: Internal event system for framework lifecycle events with priority-based callbacks
- **Plugin Registry**: Automatic metadata tracking, dependency resolution, and conflict detection for extensions
- **Framework Diagnostics**: Health monitoring, performance tracking, and system diagnostics
- **Slash Command Limiter**: Automatic protection against Discord's 100 slash command limit with graceful degradation

### 🎯 Command System
- **Hybrid Commands**: Seamless prefix and slash command support
- **Permission Framework**: Role-based access control with bot/guild owner hierarchies
- **Command Autocomplete**: Dynamic command suggestions for slash commands
- **Cooldown Management**: Built-in rate limiting per user/guild/channel
- **Auto-Delete Messages**: Automatic cleanup of success/error messages
- **Slash Limit Protection**: Automatic conversion to prefix-only when approaching Discord's 100 command limit
- **Command Status Indicators**: Visual indicators showing which commands support slash/prefix/both

### 🛒 Extension Marketplace
- **Integrated Marketplace**: Browse, search, and install official extensions directly from within the bot
- **Custom License Agreement**: Mandatory acceptance of licensing terms before installing extensions
- **ZygnalID Support**: Unique ID generation for extension tracking and dedicated support
- **Dependency Auto-Fix**: Automatic detection and installation of missing Python dependencies via `!marketplace fixdeps`
- **Enhanced Error Handling**: Better ZygnalID validation and activation guidance

### 📚 User Interface
- **Interactive Help Menu**: Dropdown-based navigation with pagination
- **Category Organization**: Automatic command grouping by cog
- **Rich Embeds**: Modern Discord UI with color-coded responses
- **User-Specific Interactions**: Security-checked button/dropdown interactions
- **Command Type Legend**: Visual indicators for hybrid, prefix-only, and slash-limited commands

### ⚙️ Configuration
- **Per-Guild Settings**: Custom prefixes, permissions, and configurations
- **JSON Config System**: Centralized configuration with safe atomic writes
- **Command Permissions**: Granular role requirements per command
- **Extension Blacklist**: Selective extension loading control
- **Framework Cog Control**: Enable/disable individual framework components via config

### 📊 Monitoring & Analytics
- **Command Usage Stats**: Track most-used commands and patterns
- **Error Tracking**: Comprehensive error logging with stack traces
- **Uptime Monitoring**: Real-time bot statistics and health metrics
- **Performance Metrics**: Extension load times and database query tracking
- **Framework Diagnostics**: System health monitoring with CPU, memory, and error rate tracking
- **Hook Execution History**: Track internal event system performance and errors
- **Plugin Dependency Tracking**: Monitor extension dependencies and conflicts

## 📋 Requirements

```
Python 3.8+        (Built with 3.12.7)
discord.py 2.0+    (Built with 2.6.3)
python-dotenv 1.0.0
aiosqlite
aiofiles
rich
psutil
```

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/TheHolyOneZ/discord-bot-framework.git
cd discord-bot-framework

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Setup

Create a `.env` file in the root directory:

```env
DISCORD_TOKEN=your_bot_token_here
BOT_OWNER_ID=your_discord_user_id
```

**Getting Your User ID:**
1. Enable Developer Mode in Discord (User Settings → Advanced)
2. Right-click your username → Copy ID

### 3. Initial Configuration

The bot will auto-generate `config.json` on first run with default settings:

```json
{
    "prefix": "!",
    "owner_ids": [],
    "auto_reload": true,
    "status": {
        "type": "watching",
        "text": "{guilds} servers"
    },
    "database": {
        "path": "./data/bot.db"
    },
    "logging": {
        "level": "INFO",
        "max_bytes": 10485760,
        "backup_count": 5
    },
    "extensions": {
        "auto_load": true,
        "blacklist": []
    },
    "cooldowns": {
        "default_rate": 3,
        "default_per": 5.0
    },
    "command_permissions": {},
    "framework": {
        "load_cogs": true,
        "enable_event_hooks": true,
        "enable_plugin_registry": true,
        "enable_framework_diagnostics": true,
        "enable_slash_command_limiter": true
    }
}
```

### 4. Create Required Directories

```bash
mkdir extensions
mkdir cogs
```

### 5. Run the Bot

```bash
python main.py
```

You should see a beautiful startup panel with bot statistics!

## 📁 Project Structure

```
discord-bot-framework/
│
├── main.py                    # Core bot logic and commands
├── atomic_file_system.py      # Atomic operations and data management
├── extensions/                # Your extension modules (auto-loaded)
│   ├── example.py
│   ├── moderation.py
│   ├── marketplace.py         # Extension Marketplace
│   └── fun.py
│
├── cogs/                      # Framework internal cogs
│   ├── event_hooks.py         # Internal event system
│   ├── plugin_registry.py     # Plugin metadata & dependency tracking
│   ├── framework_diagnostics.py  # Health monitoring
│   └── slash_command_limiter.py  # Slash command protection
│    
├── data/                      # Auto-generated data directory
│   ├── bot.db                 # SQLite database
│   ├── bot.db.backup_*        # Automatic database backups
│   ├── plugin_registry.json   # Plugin metadata cache
│   ├── framework_diagnostics.json  # System diagnostics
│   └── framework_health.json  # Health monitoring data
│
├── marketplace/               # Marketplace data
│   ├── ZygnalID.txt           # Unique bot identifier
│   └── license_accepted.json  # License acceptance tracking
│
├── botlogs/                   # Log files
│   ├── permanent.log          # Persistent log (rotates at 10MB)
│   ├── permanent.log.1        # Backup logs
│   └── current_run.log        # Current session only
│
├── config.json                # Bot configuration (auto-generated)
├── .env                       # Environment variables (create this)
├── requirements.txt           # Python dependencies
└── README.md                  # You are here
```

## 🎮 Built-in Commands

### User Commands

| Command | Description | Cooldown |
|---------|-------------|----------|
| `!help` / `/help` | Interactive help menu with categories and command type indicators | 10s |
| `!stats` / `/stats` | Display bot statistics, metrics, and framework info | 10s |
| `!extensions` / `/extensions` | List all loaded user extensions and framework cogs | 10s |
| `!discordbotframework` | Framework information and features | 10s |
| `!setprefix <prefix>` | Set custom prefix for your server | - |
| `!config [command] [role]` | Configure command permissions | - |
| `!marketplace` / `/marketplace` | Browse, search, and manage official extensions | 10s |
| `!plugins` / `/plugins` | List all registered plugins with metadata | 10s |
| `!plugininfo <name>` | View detailed information about a specific plugin | 10s |
| `!slashlimit` / `/slashlimit` | Check slash command usage and limits | 10s |

### Owner-Only Commands

| Command | Description | Access |
|---------|-------------|--------|
| `!sync` / `/sync` | Force sync slash commands globally | Bot Owner |
| `!reload <extension>` | Hot-reload a specific extension | Bot Owner |
| `!load <extension>` | Load an extension | Bot Owner |
| `!unload <extension>` | Unload an extension | Bot Owner |
| `!atomictest` | Test atomic file operations | Bot Owner |
| `!hooks` / `/hooks` | Display registered framework event hooks | Bot Owner |
| `!hookhistory` / `/hookhistory` | Display hook execution history | Bot Owner |
| `!diagnostics` / `/diagnostics` | Display framework diagnostics and health | Bot Owner |
| `!marketplace myid` | Retrieve the bot's unique ZygnalID for support | Bot Owner |
| `!marketplace fixdeps` | Auto-install missing Python dependencies from logs | Bot Owner |

## 🔧 Creating Extensions

### Basic Extension Template

```python
import discord
from discord.ext import commands
from discord import app_commands

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(
        name="example",
        help="An example command"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def example_command(self, ctx):
        """This command works with both ! and /"""
        await ctx.send("Hello from my extension!")
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Event listener example"""
        print(f"{member.name} joined the server!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

### Extension with Plugin Metadata

```python
import discord
from discord.ext import commands

# Plugin metadata (optional but recommended)
__version__ = "1.0.0"
__author__ = "YourName"
__description__ = "A cool extension that does amazing things"
__dependencies__ = []  # List required extensions
__conflicts__ = []     # List incompatible extensions

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Register plugin metadata if registry is available
        if hasattr(bot, 'register_plugin'):
            bot.register_plugin(
                name="my_extension",
                version=__version__,
                author=__author__,
                description=__description__,
                dependencies=__dependencies__,
                conflicts_with=__conflicts__
            )
    
    @commands.hybrid_command(name="example")
    async def example_command(self, ctx):
        await ctx.send("Example command!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

### Using Framework Event Hooks

```python
from discord.ext import commands
import discord

class MyHookedCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Register hooks if event system is available
        if hasattr(bot, 'register_hook'):
            # Register with priority (higher = executes first)
            bot.register_hook("extension_loaded", self.on_extension_loaded, priority=5)
            bot.register_hook("command_executed", self.on_command_used)
    
    async def on_extension_loaded(self, bot, extension_name: str, **kwargs):
        """Called when any extension is loaded"""
        print(f"Extension loaded: {extension_name}")
    
    async def on_command_used(self, bot, command_name: str, author, **kwargs):
        """Called when any command is executed"""
        print(f"Command {command_name} used by {author}")
    
    def cog_unload(self):
        # Unregister hooks when cog unloads
        if hasattr(self.bot, 'unregister_hook'):
            self.bot.unregister_hook("extension_loaded", self.on_extension_loaded)
            self.bot.unregister_hook("command_executed", self.on_command_used)

async def setup(bot):
    await bot.add_cog(MyHookedCog(bot))
```

### Advanced Extension with Permissions

```python
import discord
from discord.ext import commands
from discord import app_commands

class AdminCog(commands.Cog, name="Administration"):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(
        name="ban",
        help="Ban a user from the server"
    )
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban_user(
        self, 
        ctx, 
        member: discord.Member, 
        *, 
        reason: str = "No reason provided"
    ):
        await member.ban(reason=reason)
        
        embed = discord.Embed(
            title="✅ User Banned",
            description=f"**{member}** has been banned\n**Reason:** {reason}",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        
        # Log to database
        await self.bot.db.increment_command_usage("ban")

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
```

### Using the Database

```python
class DataCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name="setdata")
    async def set_data(self, ctx, key: str, value: str):
        # Direct database access
        await self.bot.db.conn.execute(
            "INSERT OR REPLACE INTO user_data (user_id, data) VALUES (?, ?)",
            (ctx.author.id, f"{key}:{value}")
        )
        await self.bot.db.conn.commit()
        await ctx.send(f"✅ Data saved: {key} = {value}")
    
    @commands.hybrid_command(name="getdata")
    async def get_data(self, ctx):
        async with self.bot.db.conn.execute(
            "SELECT data FROM user_data WHERE user_id = ?",
            (ctx.author.id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                await ctx.send(f"Your data: {row['data']}")
            else:
                await ctx.send("No data found!")
```

### Using Atomic File Operations

```python
from atomic_file_system import global_file_handler

class FileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "./data/my_cog_data.json"
    
    @commands.hybrid_command(name="savedata")
    async def save_data(self, ctx, *, data: str):
        save_data = {
            "user_id": ctx.author.id,
            "data": data,
            "timestamp": ctx.message.created_at.isoformat()
        }
        
        # Atomic write with automatic caching
        success = await global_file_handler.atomic_write_json(
            self.data_file, 
            save_data
        )
        
        if success:
            await ctx.send("✅ Data saved atomically!")
        else:
            await ctx.send("❌ Failed to save data")
    
    @commands.hybrid_command(name="loaddata")
    async def load_data(self, ctx):
        # Atomic read with caching (300s TTL)
        data = await global_file_handler.atomic_read_json(
            self.data_file,
            use_cache=True
        )
        
        if data:
            await ctx.send(f"📄 Cached data: {data}")
        else:
            await ctx.send("No data found!")
```

## ⚙️ Configuration Guide

### Framework Cogs Configuration

Enable or disable framework components:

```json
{
    "framework": {
        "load_cogs": true,
        "enable_event_hooks": true,
        "enable_plugin_registry": true,
        "enable_framework_diagnostics": true,
        "enable_slash_command_limiter": true
    }
}
```

### Command Permissions

Configure role-based access for commands:

```bash
# Allow @Moderator role to use the ban command
!config ban @Moderator

# Remove restrictions from a command
!config ban none

# View current permissions
!config
```

**Permission Hierarchy:**
1. Bot Owner (always has access)
2. Configured Roles (guild-specific)
3. Discord Permissions (for built-in checks)

### Custom Prefixes

Each server can have its own prefix:

```bash
# Set prefix to ?
!setprefix ?

# Now use: ?help instead of !help
```

### Extension Blacklist

Prevent specific extensions from loading:

```json
{
    "extensions": {
        "auto_load": true,
        "blacklist": ["debug_cog", "test_module"]
    }
}
```

### Status Configuration

Customize bot presence:

```json
{
    "status": {
        "type": "watching",
        "text": "{guilds} servers | {users} users"
    }
}
```

**Available types:** `playing`, `watching`, `listening`, `competing`  
**Variables:** `{guilds}`, `{users}`, `{commands}`

## 🔍 Database Schema

### Guild Settings
```sql
guild_id      INTEGER PRIMARY KEY
prefix        TEXT
settings      TEXT (JSON)
created_at    TIMESTAMP
```

### User Data
```sql
user_id       INTEGER PRIMARY KEY
data          TEXT (JSON)
last_seen     TIMESTAMP
```

### Command Stats
```sql
command_name  TEXT PRIMARY KEY
usage_count   INTEGER
last_used     TIMESTAMP
```

## 📊 Monitoring & Logs

### Log Levels

Configure in `config.json`:
```json
{
    "logging": {
        "level": "INFO",
        "max_bytes": 10485760,
        "backup_count": 5
    }
}
```

**Available levels:** `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

### Log Files

- **`permanent.log`**: Persistent across restarts, rotates at 10MB
- **`permanent.log.1-5`**: Backup log files
- **`current_run.log`**: Current session only, overwrites on restart

### Log Rotation

Automatic rotation occurs when:
- File size exceeds `max_bytes`
- Triggered every hour by background task
- Old logs (30+ days) are automatically cleaned

## 🛡️ Security Features

### Permission Checks
- **Interaction Validation**: Ensures only command requester can use UI elements
- **Owner-Only Commands**: Hardcoded protection for sensitive operations
- **Role Requirements**: Per-command role restrictions
- **Discord Permissions**: Integration with Discord's permission system

### Data Safety
- **Atomic Operations**: Prevents data corruption during writes
- **Database Backups**: Automatic backups on shutdown
- **WAL Mode**: Write-Ahead Logging for database integrity
- **File Locking**: Prevents concurrent write conflicts

## 🎨 Customization

### Embed Colors

Default color scheme:
```python
MAIN_MENU = 0x2b2d31    # Dark gray
CATEGORIES = 0x5865f2    # Discord Blurple
SUCCESS = 0x00ff00       # Green
ERROR = 0xff0000         # Red
WARNING = 0xffff00       # Yellow
CREDITS = 0xffd700       # Gold
```

### Emojis

The framework uses Unicode emojis. Customize in command embeds:
```python
embed.add_field(name="🔥 Popular", value="...")
embed.add_field(name="⭐ Featured", value="...")
```

## 🐛 Troubleshooting

### Bot won't start

**Issue:** `DISCORD_TOKEN not found in .env!`
- Ensure `.env` file exists in root directory
- Verify token is correct (no quotes needed)
- Check file is named exactly `.env` (not `.env.txt`)

**Issue:** `BOT_OWNER_ID not found in .env!`
- Add your Discord user ID to `.env`
- Ensure no spaces: `BOT_OWNER_ID=123456789`

### Extensions not loading

**Check logs:**
```bash
cat botlogs/current_run.log | grep -i "extension"
```

**Common issues:**
- Missing `async def setup(bot)` function
- Syntax errors in extension file
- Extension in blacklist
- File not in `extensions/` directory
- Missing Python dependencies (use `!marketplace fixdeps`)

### Slash commands not syncing

**Manual sync:**
```bash
!sync
```

**Rate limiting:**
- Discord limits syncs to ~2 per hour
- Bot automatically handles rate limits
- Check logs for retry information

**Slash command limit reached:**
- Use `!slashlimit` to check current usage
- Framework automatically converts commands to prefix-only when limit approaches
- Commands will show indicators in help menu

### Database errors

**Backup and reset:**
```bash
# Backup current database
cp data/bot.db data/bot.db.backup

# Delete database (will regenerate)
rm data/bot.db

# Restart bot
python main.py
```

### Permission errors

**"Missing Permissions" error:**
- Check bot has required permissions in Discord
- Verify role hierarchy (bot role above target roles)
- Enable necessary intents in Developer Portal

**"You don't have permission" error:**
- Check command permissions: `!config`
- Verify your roles match requirements
- Contact bot owner for access

### Missing Dependencies

**Use automatic dependency fixer:**
```bash
!marketplace fixdeps
```

This will scan logs for `ModuleNotFoundError` and automatically install missing packages.

## 🔄 Migration Guide

### From discord.py 1.x to 2.x

If upgrading from an older framework:

1. **Update imports:**
```python
# Old
from discord.ext import commands

# New (if using app commands)
from discord import app_commands
from discord.ext import commands
```

2. **Update bot initialization:**
```python
# Old
bot = commands.Bot(command_prefix="!")

# New
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
```

3. **Update cog setup:**
```python
# Old
def setup(bot):
    bot.add_cog(MyCog(bot))

# New
async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

## 📈 Performance Tips

### Optimize Database Queries

```python
# Use transactions for multiple writes
async with self.bot.db.conn.execute("BEGIN"):
    for item in items:
        await self.bot.db.conn.execute(
            "INSERT INTO table VALUES (?)", (item,)
        )
    await self.bot.db.conn.commit()
```

### Use Caching Effectively

```python
# Enable caching for frequently read files
data = await global_file_handler.atomic_read_json(
    filepath, 
    use_cache=True  # 300s cache
)

# Disable for real-time data
data = await global_file_handler.atomic_read_json(
    filepath, 
    use_cache=False
)
```

### Batch Operations

```python
# Bad: Individual messages
for user in users:
    await channel.send(f"Hello {user}")

# Good: Single message
await channel.send(f"Hello {', '.join(users)}")
```

## 🤝 Contributing

Contributions are welcome! Guidelines:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Test thoroughly**: Ensure bot starts and commands work
4. **Follow code style**: Match existing formatting
5. **Update documentation**: Add/update README sections
6. **Commit changes**: `git commit -m 'Add amazing feature'`
7. **Push to branch**: `git push origin feature/amazing-feature`
8. **Open Pull Request**

### Code Style

- Use type hints where applicable
- Add docstrings to public methods
- Follow PEP 8 guidelines
- Use meaningful variable names
- Comment complex logic

## 📜 License

This project is licensed under the MIT License with additional terms.

### MIT License

```
Copyright (c) 2025 TheHolyOneZ

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software...
```

### Additional Terms

**IMPORTANT:** The following components must remain intact in all versions:

1. **CreditsButton class** - Must remain visible and functional
2. **Author attribution** - "TheHolyOneZ" must not be removed or altered
3. **Repository link** - GitHub link must remain in credits
4. **Framework command** - `!discordbotframework` must remain intact with original features

See `main.py` for full license text.

## 💡 Advanced Features

### Framework Cogs System

The framework now includes modular internal cogs located in the `./cogs` directory:

- **Event Hooks**: Internal event system for lifecycle events
- **Plugin Registry**: Automatic metadata tracking and dependency resolution
- **Framework Diagnostics**: Real-time health monitoring and system diagnostics
- **Slash Command Limiter**: Automatic protection against Discord's command limit

### Event Hooks System

Register callbacks for framework lifecycle events:

```python
# Available hooks:
# - bot_ready: When bot becomes ready
# - guild_joined: When bot joins a guild
# - guild_left: When bot leaves a guild
# - command_executed: When a command is executed
# - command_error: When a command error occurs
# - extension_loaded: When an extension is loaded
# - extension_unloaded: When an extension is unloaded

# Register a hook
bot.register_hook("extension_loaded", my_callback, priority=10)

# Unregister a hook
bot.unregister_hook("extension_loaded", my_callback)

# List all hooks
hooks = bot.list_hooks()

# Get hook execution history
history = bot.get_hook_history(limit=20)
```

### Plugin Registry System

Automatic tracking of extension metadata:

```python
# Register plugin metadata
bot.register_plugin(
    name="my_extension",
    version="1.0.0",
    author="YourName",
    description="Extension description",
    dependencies=["other_extension"],
    conflicts_with=["incompatible_extension"]
)

# Get plugin info
info = bot.get_plugin_info("my_extension")

# Check dependencies
satisfied, missing = bot.check_dependencies("my_extension")

# Detect conflicts
has_conflicts, conflicts = bot.detect_conflicts("my_extension")

# Get all plugins
plugins = bot.get_all_plugins()
```

### Framework Diagnostics

Access comprehensive system diagnostics:

```python
# Get current diagnostics
diagnostics = await bot.generate_diagnostics()

# Available metrics:
# - Bot information (username, latency, owner)
# - Environment (Python version, platform, architecture)
# - Extensions (loaded count, load times)
# - Commands (total, slash commands)
# - Server statistics (guilds, users, channels)
# - Performance (memory, CPU, threads)
# - Health metrics (error rate, uptime)
```

### Slash Command Limiter

Automatic protection against Discord's 100 command limit:

```python
# Check if extension has slash disabled
is_disabled = bot.is_slash_disabled("my_extension")

# Get prefix-only commands
prefix_only = bot.get_prefix_only_commands()

# The limiter automatically:
# - Monitors slash command count
# - Warns at 90 commands (90% threshold)
# - Converts new extensions to prefix-only at 95 commands
# - Updates help menu with command type indicators
```

### Hot-Reload System

Enable automatic extension reloading:

```json
{
    "auto_reload": true
}
```

The bot will monitor `extensions/` and automatically reload modified files every 30 seconds.

### Metrics Dashboard

Access real-time metrics:

```python
# Get current statistics
stats = bot.metrics.get_stats()

# Available metrics:
# - uptime: Bot uptime in seconds
# - commands_processed: Total commands executed
# - messages_seen: Total messages processed
# - error_count: Total errors encountered
# - top_commands: Dict of most-used commands
```

### Command Usage Analytics

Track command popularity:

```python
# Get command statistics from database
stats = await bot.db.get_command_stats()

# Returns: [(command_name, usage_count), ...]
```

### Custom Checks

Create reusable permission checks:

```python
def is_admin():
    async def predicate(ctx):
        return ctx.author.guild_permissions.administrator
    return commands.check(predicate)

@commands.command()
@is_admin()
async def admin_command(ctx):
    await ctx.send("Admin only!")
```

## 🌟 Best Practices

### Error Handling

```python
@commands.command()
async def safe_command(ctx):
    try:
        # Your code here
        result = await some_operation()
        await ctx.send(f"Success: {result}")
    except Exception as e:
        logger.error(f"Error in safe_command: {e}")
        await ctx.send("❌ An error occurred!")
```

### Resource Cleanup

```python
class ResourceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
    
    def cog_unload(self):
        # Cleanup when cog is unloaded
        asyncio.create_task(self.session.close())
```

### Efficient Embeds

```python
# Reusable embed template
def create_embed(title, description, color=0x5865f2):
    return discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )

# Usage
embed = create_embed("Success", "Operation completed!")
await ctx.send(embed=embed)
```

## 🔗 Useful Links

- **discord.py Documentation**: https://discordpy.readthedocs.io/
- **Discord Developer Portal**: https://discord.com/developers/applications
- **Python asyncio Guide**: https://docs.python.org/3/library/asyncio.html
- **SQLite Documentation**: https://www.sqlite.org/docs.html

## 💬 Support

Need help? Have questions?

- **Issues**: [GitHub Issues](https://github.com/TheHolyOneZ/discord-bot-framework/issues)
- **Discussions**: [GitHub Discussions](https://github.com/TheHolyOneZ/discord-bot-framework/discussions)

## 👤 Author

**TheHolyOneZ**

- GitHub: [@TheHolyOneZ](https://github.com/TheHolyOneZ)

---

<div align="center">

⭐ **If you find this framework helpful, please consider giving it a star!** ⭐

Made with 💜 by TheHolyOneZ

</div>

</div>
