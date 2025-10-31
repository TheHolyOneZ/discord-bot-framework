# 🤖 Discord Bot Framework

A production-ready, enterprise-grade Discord bot framework featuring atomic file operations, advanced permission systems, dynamic extension loading, and comprehensive monitoring. Built for developers who demand reliability, scalability, and maintainability.

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.0+-blue.svg)](https://github.com/Rapptz/discord.py)


## ✨ Core Features

### 🔧 System Architecture
- **Atomic File Operations**: Thread-safe file handling with built-in caching (300s TTL)
- **SQLite Database**: Optimized with WAL mode, automatic backups, and connection pooling
- **Safe Log Rotation**: Automatic log management with configurable size limits and retention
- **Hot-Reload System**: Auto-reload extensions when files change (optional)
- **Metrics Collection**: Real-time command tracking, error monitoring, and performance analytics

### 🎯 Command System
- **Hybrid Commands**: Seamless prefix and slash command support
- **Permission Framework**: Role-based access control with bot/guild owner hierarchies
- **Command Autocomplete**: Dynamic command suggestions for slash commands
- **Cooldown Management**: Built-in rate limiting per user/guild/channel
- **Auto-Delete Messages**: Automatic cleanup of success/error messages

### 📚 User Interface
- **Interactive Help Menu**: Dropdown-based navigation with pagination
- **Category Organization**: Automatic command grouping by cog
- **Rich Embeds**: Modern Discord UI with color-coded responses
- **User-Specific Interactions**: Security-checked button/dropdown interactions

### ⚙️ Configuration
- **Per-Guild Settings**: Custom prefixes, permissions, and configurations
- **JSON Config System**: Centralized configuration with safe atomic writes
- **Command Permissions**: Granular role requirements per command
- **Extension Blacklist**: Selective extension loading control

### 📊 Monitoring & Analytics
- **Command Usage Stats**: Track most-used commands and patterns
- **Error Tracking**: Comprehensive error logging with stack traces
- **Uptime Monitoring**: Real-time bot statistics and health metrics
- **Performance Metrics**: Extension load times and database query tracking

## 📋 Requirements

```
Python 3.8+        (Built with 3.12.7)
discord.py 2.0+    (Built with 2.6.3)
python-dotenv 1.0.0
aiosqlite
aiofiles
rich
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
    "command_permissions": {}
}
```

### 4. Create Extensions Directory

```bash
mkdir extensions
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
│   └── fun.py
├── data/                      # Auto-generated data directory
│   ├── bot.db                 # SQLite database
│   └── bot.db.backup_*        # Automatic database backups
├── botlogs/                   # Log files
│   ├── permanent.log          # Persistent log (rotates at 10MB)
│   ├── permanent.log.1        # Backup logs
│   └── current_run.log        # Current session only
├── config.json                # Bot configuration (auto-generated)
├── .env                       # Environment variables (create this)
├── requirements.txt           # Python dependencies
└── README.md                  # You are here
```

## 🎮 Built-in Commands

### User Commands

| Command | Description | Cooldown |
|---------|-------------|----------|
| `!help` / `/help` | Interactive help menu with categories | 10s |
| `!stats` / `/stats` | Display bot statistics and metrics | 10s |
| `!extensions` / `/extensions` | List all loaded extensions | 10s |
| `!discordbotframework` | Framework information and features | 10s |
| `!setprefix <prefix>` | Set custom prefix for your server | - |
| `!config [command] [role]` | Configure command permissions | - |

### Owner-Only Commands

| Command | Description | Access |
|---------|-------------|--------|
| `!sync` / `/sync` | Force sync slash commands globally | Bot Owner |
| `!reload <extension>` | Hot-reload a specific extension | Bot Owner |
| `!load <extension>` | Load an extension | Bot Owner |
| `!unload <extension>` | Unload an extension | Bot Owner |
| `!atomictest` | Test atomic file operations | Bot Owner |

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

### Slash commands not syncing

**Manual sync:**
```bash
!sync
```

**Rate limiting:**
- Discord limits syncs to ~2 per hour
- Bot automatically handles rate limits
- Check logs for retry information

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
