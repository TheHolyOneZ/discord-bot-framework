# 🤖 Advanced Discord Bot Framework

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.0+-blue.svg)](https://github.com/Rapptz/discord.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> A production-ready, enterprise-grade Discord bot framework featuring atomic file operations, advanced permission systems, dynamic extension loading, comprehensive monitoring, modular framework cogs, and an integrated extension marketplace.

**Website**: [https://zygnalbot.com/bot-framework/](https://zygnalbot.com/bot-framework/)

---

## 📑 Table of Contents

- [✨ Overview](#-overview)
- [🌟 What Makes This Framework Special](#-what-makes-this-framework-special)
- [🎯 Core Features](#-core-features)
- [📋 Requirements](#-requirements)
- [🚀 Quick Start](#-quick-start)
- [📁 Project Structure](#-project-structure)
- [🎮 Built-in Commands](#-built-in-commands)
- [🛒 Extension Marketplace](#-extension-marketplace)
- [🔧 Creating Extensions](#-creating-extensions)
- [⚙️ Configuration Guide](#️-configuration-guide)
- [🗄️ Database System](#️-database-system)
- [📊 Framework Cogs System](#-framework-cogs-system)
- [🔐 Security Features](#-security-features)
- [🎨 Customization](#-customization)
- [🛠 Troubleshooting](#-troubleshooting)
- [📈 Performance Tips](#-performance-tips)
- [📜 License](#-license)
- [👤 Author](#-author)

---

## ✨ Overview

This Discord bot framework is a comprehensive, production-ready foundation for building scalable Discord bots. It combines enterprise-level architecture with developer-friendly features, providing everything you need from atomic file operations to an integrated extension marketplace.

Built with **discord.py 2.0+** and modern Python async patterns, this framework eliminates common pitfalls in bot development while providing powerful tools for both beginners and advanced developers.

---

## 🌟 What Makes This Framework Special

### 🏗️ Enterprise-Grade Architecture

**Atomic File Operations**
- Thread-safe file handling with built-in LRU caching (300s TTL, 1000 entry limit)
- Automatic lock management with cleanup threshold (500 locks)
- Zero data corruption through tempfile-based atomic writes
- Cache invalidation and TTL-based expiration
- Cross-platform compatibility (Windows/Linux)

**Advanced Database Management**
- Per-guild SQLite databases with automatic connection pooling
- WAL (Write-Ahead Logging) mode for concurrent access
- Automatic backup system on shutdown
- Orphaned connection cleanup
- Global and guild-specific data separation
- Command usage analytics and statistics tracking

**Safe Log Rotation**
- Automatic size-based rotation (10MB default)
- Configurable backup count (5 backups default)
- Age-based cleanup (30-day retention)
- Dual-mode logging: permanent + current session
- Structured logging with timestamps and levels

### 🎯 Developer Experience

**Hot-Reload System**
- File-watching based auto-reload (30s interval)
- Extension modification timestamps tracked
- Zero downtime during development
- Load time tracking per extension
- Graceful error handling during reload

**Intelligent Extension Loading**
- Automatic whitespace handling (converts spaces to underscores)
- Extension blacklist support
- Load time tracking and diagnostics
- Conflict detection through Plugin Registry
- Dependency resolution system

**Hybrid Command System**
- Seamless prefix and slash command support
- Automatic command type indicators in help menu
- Slash command limit protection (100 command cap)
- Graceful degradation to prefix-only mode
- Visual indicators: ⚡ (hybrid), 🔸 (prefix-only), 🔹 (limit reached)

### 🔌 Modular Framework Cogs

**Event Hooks System** (`cogs/event_hooks.py`)
- Internal event system for framework lifecycle events
- Priority-based callback execution
- Asynchronous queue processing (1000 event queue)
- Hook execution history (100 total, 20 per event)
- Built-in events: bot_ready, guild_joined, guild_left, command_executed, command_error
- Custom event emission support

**Plugin Registry** (`cogs/plugin_registry.py`)
- Automatic metadata extraction from extensions
- Dependency and conflict tracking
- Version management and author attribution
- Command and cog enumeration
- Load time tracking per plugin
- Auto-registration on extension load
- JSON-based registry persistence

**Framework Diagnostics** (`cogs/framework_diagnostics.py`)
- Real-time system health monitoring
- CPU and memory usage tracking
- Command/error rate metrics
- Uptime and latency monitoring
- Extension load time analysis
- Health status: healthy (<5% error rate) or degraded
- Automatic diagnostics generation every 5 minutes

**Slash Command Limiter** (`cogs/slash_command_limiter.py`)
- Monitors Discord's 100 global slash command limit
- Configurable thresholds: warning (90), safe limit (95)
- Automatic conversion to prefix-only mode
- Extension-level slash command disabling
- Visual progress bars in command output
- Integration with help system for command type display

### 🛒 Integrated Extension Marketplace

**Direct Extension Installation**
- Browse official extensions from within Discord
- Search by keywords, categories, or status
- One-click installation with confirmation
- Automatic file writing to `./extensions` directory
- Post-install instructions with load commands

**ZygnalID System**
- Unique 16-character bot identifier
- Automatic generation on first use
- Required for extension downloads
- Enables dedicated support and tracking
- Stored securely in `./data/marketplace/ZygnalID.txt`

**License Agreement**
- Mandatory acceptance before marketplace access
- Per-user tracking of acceptance
- Usage restrictions enforcement
- Extension-specific licensing support
- Terms displayed in interactive embed

**Dependency Management**
- `!marketplace fixdeps` command
- Automatic log parsing for `ModuleNotFoundError`
- pip-based dependency installation
- Success/failure reporting per package
- Duplicate installation prevention

**Advanced Features**
- Extension categories: Working, Beta, Broken
- Custom URL support for extensions
- Version tracking and display
- Author attribution
- Extension status indicators
- Pagination for large lists (5 per page)
- Dropdown menus for selection
- Cache system (300s TTL) for API calls
- Rate limit handling with retry logic

### 🎨 Modern User Interface

**Interactive Help System**
- Dropdown-based category navigation
- Pagination for large command lists (5 per page)
- Visual command type indicators
- Automatic cog organization
- User-specific interaction validation
- Credits button with framework info
- Dynamic back navigation
- Real-time command count per category

**Rich Embeds Everywhere**
- Color-coded responses (success=green, error=red, warning=yellow)
- Consistent styling across all commands
- Timestamp inclusion
- Footer information
- Thumbnail support
- Field-based organization
- Progress bars for visual feedback

**Auto-Delete Messages**
- Configurable delete timers (5-15s)
- Success message cleanup
- Error message cleanup
- Reduces channel clutter
- User-friendly experience

### 🔒 Advanced Security

**Multi-Tier Permission System**
1. **Bot Owner**: Full access (from BOT_OWNER_ID env variable)
2. **Guild Owner**: Server management commands
3. **Role-Based**: Per-command role requirements
4. **Discord Permissions**: Native permission integration
5. **Hardcoded Restrictions**: Owner-only command list

**Interaction Security**
- User-specific button/dropdown validation
- Interaction author verification
- Ephemeral error messages
- Timeout-based view expiration (180-300s)
- Session-based state management

**Data Protection**
- Atomic file operations prevent corruption
- Database WAL mode for ACID compliance
- Automatic backups before shutdown
- File locking mechanism
- Cache invalidation on writes
- Secure temporary file handling

### 📊 Comprehensive Monitoring

**Metrics Collection**
- Real-time command tracking (LRU cache, 100 command limit)
- Message processing statistics
- Error rate monitoring
- Uptime tracking
- Top command analytics
- Per-command usage counts in database

**Health Monitoring**
- Error rate calculation
- Status determination (healthy/degraded)
- Latency tracking
- Extension load time analysis
- Database connection monitoring
- Cache performance metrics

**Diagnostics Dashboard**
- System information (Python version, platform, architecture)
- Bot statistics (guilds, users, channels)
- Extension analysis (count, load times)
- Command registration (prefix + slash)
- Performance metrics (CPU, memory, threads)
- Database health status

### 🔧 Developer Tools

**Atomic File Testing**
- Built-in `!atomictest` command
- Write/read/cache performance benchmarking
- Concurrent operation testing (10 simultaneous writes)
- Data integrity verification
- Cache statistics display

**Cache Management**
- `!cachestats` command for monitoring
- File cache size tracking
- Lock count monitoring
- Prefix cache statistics
- Metrics cache info
- Database connection counts

**Integrity Checks**
- `!integritycheck` command
- File system validation
- Database connection testing
- Cache system verification
- Extension loading checks
- Shard status monitoring
- Memory usage analysis

**System Cleanup**
- `!cleanup` command
- __pycache__ directory removal
- Expired prefix cache cleanup
- File lock cleanup
- Orphaned database connection removal
- Statistics reporting

---

## 🎯 Core Features

### System Architecture

✅ **Atomic File Operations** - Thread-safe file handling with LRU caching  
✅ **SQLite Database** - Optimized with WAL mode and connection pooling  
✅ **Safe Log Rotation** - Automatic management with size and age limits  
✅ **Hot-Reload System** - File-watching based auto-reload (optional)  
✅ **Metrics Collection** - Real-time command tracking and analytics  
✅ **Framework Cogs** - Modular internal components with event system  
✅ **Auto-Sharding** - Built-in support for large-scale deployments  

### Command System

✅ **Hybrid Commands** - Both prefix and slash command support  
✅ **Permission Framework** - Multi-tier role-based access control  
✅ **Command Autocomplete** - Dynamic suggestions for slash commands  
✅ **Cooldown Management** - Built-in rate limiting  
✅ **Auto-Delete Messages** - Automatic cleanup of responses  
✅ **Slash Limit Protection** - Automatic prefix-only fallback  
✅ **Command Type Indicators** - Visual markers in help menu  

### Extension Marketplace

✅ **Integrated Browser** - Browse extensions from Discord  
✅ **Search & Filter** - Find extensions by keywords or category  
✅ **One-Click Install** - Direct installation to bot  
✅ **License Agreement** - Mandatory acceptance system  
✅ **ZygnalID Support** - Unique bot identification  
✅ **Dependency Auto-Fix** - Automatic missing package installation  
✅ **Version Tracking** - Extension versioning support  

### User Interface

✅ **Interactive Help** - Dropdown navigation with pagination  
✅ **Rich Embeds** - Modern Discord UI with color coding  
✅ **User Validation** - Security-checked interactions  
✅ **Progress Bars** - Visual feedback for operations  
✅ **Category Organization** - Automatic command grouping  

### Configuration

✅ **Per-Guild Settings** - Custom prefixes and configurations  
✅ **JSON Config System** - Centralized configuration  
✅ **Command Permissions** - Granular role requirements  
✅ **Extension Blacklist** - Selective loading control  
✅ **Framework Cog Control** - Enable/disable components  

### Monitoring & Analytics

✅ **Command Usage Stats** - Track popular commands  
✅ **Error Tracking** - Comprehensive error logging  
✅ **Uptime Monitoring** - Real-time bot statistics  
✅ **Performance Metrics** - Load times and query tracking  
✅ **Health Monitoring** - System diagnostics and alerts  
✅ **Hook History** - Event system execution tracking  

---

## 📋 Requirements

**Python**: 3.8+ (Built and tested with 3.12.7)  
**discord.py**: 2.0+ (Built with 2.6.3)
```
discord.py==2.6.3
python-dotenv==1.0.0
aiosqlite
aiofiles
rich
psutil
aiohttp
```

---

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/TheHolyOneZ/discord-bot-framework.git
cd discord-bot-framework
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Create `.env` File

Create `.env` in the root directory:
```env
DISCORD_TOKEN=your_bot_token_here
BOT_OWNER_ID=your_discord_user_id
```

**Getting Your User ID:**
1. Enable Developer Mode: User Settings → Advanced → Developer Mode
2. Right-click your username → Copy ID

**Getting Bot Token:**
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create New Application
3. Go to Bot section → Reset Token → Copy token

### 4. Configure Bot Intents

In the Discord Developer Portal:
1. Go to your application → Bot section
2. Enable these Privileged Gateway Intents:
   - ✅ Presence Intent
   - ✅ Server Members Intent
   - ✅ Message Content Intent

### 5. Run the Bot
```bash
python main.py
```

You should see a Rich console panel with bot statistics!

### 6. Invite Bot to Server

Generate invite URL in Developer Portal:
1. OAuth2 → URL Generator
2. Select Scopes: `bot`, `applications.commands`
3. Select Permissions: Administrator (or specific permissions)
4. Copy generated URL and open in browser

---

## 📁 Project Structure
```
discord-bot-framework/
│
├── main.py                      # Core bot logic and built-in commands
├── atomic_file_system.py        # Atomic operations and data management
│
├── extensions/                  # Your extension modules (auto-loaded)
│   ├── Put_Cogs_Extensions_here.txt
│   ├── example_logger.py        # Example extension
│   └── marketplace.py           # Extension Marketplace cog
│
├── cogs/                        # Framework internal cogs
│   ├── event_hooks.py           # Internal event system
│   ├── plugin_registry.py       # Plugin metadata & dependency tracking
│   ├── framework_diagnostics.py # Health monitoring
│   └── slash_command_limiter.py # Slash command protection
│
├── data/                        # Auto-generated data directory
│   ├── main.db                  # Global SQLite database
│   ├── main.db-wal              # WAL file for main DB
│   ├── main.db-shm              # Shared memory for main DB
│   ├── [guild_id]/              # Per-guild databases
│   │   ├── guild.db
│   │   └── guild_backup_*.db
│   ├── plugin_registry.json     # Plugin metadata cache
│   ├── framework_diagnostics.json # System diagnostics
│   ├── framework_health.json    # Health monitoring data
│   └── marketplace/
│       ├── ZygnalID.txt         # Unique bot identifier
│       └── license_accepted.json # License acceptance tracking
│
├── botlogs/                     # Log files
│   ├── permanent.log            # Persistent log (rotates at 10MB)
│   ├── permanent.log.1-5        # Backup logs
│   └── current_run.log          # Current session only
│
├── images/                      # Documentation images
│   ├── Terminal-1.png
│   ├── HelpMenu-Example.png
│   └── ... (showcase images)
│
├── config.json                  # Bot configuration (auto-generated)
├── .env                         # Environment variables (YOU CREATE THIS)
├── requirements.txt             # Python dependencies
├── README.md                    # This file
├── LICENSE                      # MIT License
├── SECURITY.md                  # Security policy
├── CODE_OF_CONDUCT.md           # Code of conduct
└── CONTRIBUTING.md              # Contribution guidelines
```

---

## 🎮 Built-in Commands

### 👥 User Commands

| Command | Description | Cooldown | Hybrid |
|---------|-------------|----------|--------|
| `!help` / `/help` | Interactive help menu with dropdown navigation | 10s | ✅ |
| `!stats` / `/stats` | Bot statistics, metrics, and framework info | 10s | ✅ |
| `!extensions` / `/extensions` | List loaded user extensions and framework cogs | 10s | ✅ |
| `!discordbotframework` | Framework information and feature list | 10s | ✅ |
| `!shardinfo` / `/shardinfo` | Shard information and distribution | 10s | ✅ |
| `!setprefix <prefix>` | Set custom prefix for your server (Admin only) | - | ✅ |
| `!config [cmd] [role]` | Configure command permissions (Owner only) | - | ✅ |

### 🛒 Marketplace Commands

| Command | Description | Cooldown | Hybrid |
|---------|-------------|----------|--------|
| `!marketplace` / `/marketplace` | Main marketplace menu with quick actions | 5s | ✅ |
| `!marketplace browse` | Browse all available extensions | 10s | ✅ |
| `!marketplace search <query>` | Search extensions by keywords | 10s | ✅ |
| `!marketplace install <id>` | Install extension by ID | 30s | ✅ |
| `!marketplace info <id>` | View detailed extension information | 5s | ✅ |
| `!marketplace refresh` | Refresh extension cache | 60s | ✅ |
| `!marketplace fixdeps` | Auto-install missing dependencies (Owner) | 60s | ✅ |
| `!marketplace myid` | View your ZygnalID (Owner only) | - | ✅ |

### 🔌 Plugin Registry Commands

| Command | Description | Cooldown | Hybrid |
|---------|-------------|----------|--------|
| `!plugins` / `/plugins` | List all registered plugins with metadata | 10s | ✅ |
| `!plugininfo <name>` | Detailed information about a plugin | 10s | ✅ |

### 📊 Framework Diagnostics Commands

| Command | Description | Cooldown | Hybrid |
|---------|-------------|----------|--------|
| `!diagnostics` / `/diagnostics` | Display framework health and diagnostics (Owner) | - | ✅ |
| `!slashlimit` / `/slashlimit` | Check slash command usage and limits | 10s | ✅ |

### 🪝 Event Hooks Commands

| Command | Description | Cooldown | Hybrid |
|---------|-------------|----------|--------|
| `!hooks` / `/hooks` | Display registered framework hooks (Owner) | - | ✅ |
| `!hookhistory [limit]` | Display hook execution history (Owner) | - | ✅ |

### 🔧 Owner-Only Commands

| Command | Description | Access |
|---------|-------------|--------|
| `!sync` / `/sync` | Force sync slash commands globally | Bot Owner |
| `!reload <extension>` | Hot-reload specific extension | Bot Owner |
| `!load <extension>` | Load extension | Bot Owner |
| `!unload <extension>` | Unload extension | Bot Owner |
| `!atomictest` | Test atomic file operations | Bot Owner |
| `!cachestats` | Display cache statistics | Bot Owner |
| `!dbstats` | Display database connection stats | Bot Owner |
| `!integritycheck` | Run full system integrity check | Bot Owner |
| `!cleanup` | Clean up system cache and temp files | Bot Owner |

---

## 🛒 Extension Marketplace

### Overview

The integrated Extension Marketplace allows you to browse, search, and install official extensions directly from Discord without manual file downloads.

### Features

✅ **Browse Extensions** - View all available extensions with pagination  
✅ **Search Functionality** - Find extensions by keywords  
✅ **Category Filtering** - Filter by status (Working, Beta, Broken)  
✅ **One-Click Install** - Direct installation to `./extensions` directory  
✅ **License Agreement** - Mandatory acceptance before use  
✅ **ZygnalID System** - Unique bot identification for support  
✅ **Dependency Management** - Automatic missing package installation  
✅ **Version Tracking** - View extension versions and update dates  

### First-Time Setup

1. **Run marketplace command:**
```bash
!marketplace
```

2. **Accept License Agreement:**
   - Read the terms carefully
   - Click "✅ Accept License" button
   - Acceptance is tracked per-user

3. **Browse Extensions:**
   - Use dropdown menu or buttons
   - Search by keywords
   - Filter by categories

### Installing Extensions

**Method 1: Interactive Menu**
```bash
!marketplace
# Click "Browse All" button
# Select extension from dropdown
# Click "📦 Install Extension"
# Confirm installation
```

**Method 2: Direct Install**
```bash
!marketplace install <extension_id>
```

**Post-Installation:**
After successful installation:
```bash
# Load the extension immediately
!load extension_name

# Or reload if already loaded
!reload extension_name

# Or restart bot for auto-load
```

### ZygnalID System

**What is ZygnalID?**
- Unique 16-character identifier for your bot
- Auto-generated on first marketplace use
- Required for extension downloads
- Enables dedicated support and tracking

**View Your ID:**
```bash
!marketplace myid
```
(Owner only, sent via DM for security)

**Activation:**
If your ID is invalid or not activated:
1. Join ZygnalBot Discord: `gg/sgZnXca5ts`
2. Verify yourself
3. Open ticket for "Zygnal ID Activation"
4. Provide your ZygnalID from `!marketplace myid`

### Dependency Management

**Automatic Fix:**
If extensions fail to load due to missing Python packages:
```bash
!marketplace fixdeps
```

This command:
1. Scans `botlogs/current_run.log` for `ModuleNotFoundError`
2. Extracts missing package names
3. Automatically runs `pip install <package>`
4. Reports success/failure per package
5. Provides next steps for loading extensions

**Manual Installation:**
```bash
pip install package_name
!reload extension_name
```

### Marketplace Categories

**Working** ✅
- Fully functional extensions
- Tested and verified
- Production-ready

**Beta** ⚠️
- Experimental features
- May have minor issues
- Actively developed

**Broken** ❌
- Known issues
- Not recommended for use
- Awaiting fixes

### Extension Information

View detailed information about any extension:
```bash
!marketplace info <extension_id>
```

Displays:
- Full description
- Version number
- Status (Working/Beta/Broken)
- File type (PY/TXT)
- Upload date
- Custom URL (if available)
- Installation instructions

### Searching Extensions

**By Keyword:**
```bash
!marketplace search moderation
```

**By Title or Description:**
The search is case-insensitive and matches:
- Extension titles
- Description text
- Details field

### Cache Management

The marketplace caches API responses for 300 seconds (5 minutes).

**Force Refresh:**
```bash
!marketplace refresh
```

Use this when:
- New extensions are added
- Extension details are updated
- Cache shows outdated information

---

## 🔧 Creating Extensions

### Basic Extension Template
```python
import discord
from discord.ext import commands
from discord import app_commands

class MyExtension(commands.Cog):
    """Description of your extension"""
    
    def __init__(self, bot):
        self.bot = bot
        print(f"{self.__class__.__name__} initialized")
    
    @commands.hybrid_command(
        name="example",
        help="An example command that works with both prefix and slash"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def example_command(self, ctx):
        """Command implementation"""
        embed = discord.Embed(
            title="✅ Success",
            description="This is an example command!",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Event listener example"""
        if message.author.bot:
            return
        # Your logic here
    
    def cog_unload(self):
        """Cleanup when extension is unloaded"""
        print(f"{self.__class__.__name__} unloaded")

async def setup(bot):
    """Required setup function"""
    await bot.add_cog(MyExtension(bot))
```

### Extension with Plugin Metadata
```python
import discord
from discord.ext import commands

# Plugin metadata (recommended for Plugin Registry)
__version__ = "1.0.0"
__author__ = "YourName"
__description__ = "A cool extension that does amazing things"
__dependencies__ = []  # List of required extensions
__conflicts__ = []     # List of incompatible extensions

class MyExtension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Register with Plugin Registry (if available)
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
        await ctx.send("Hello from my extension!")

async def setup(bot):
    await bot.add_cog(MyExtension(bot))
```

### Using Framework Event Hooks
```python
from discord.ext import commands
import discord

class HookedExtension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Register hooks if Event Hooks system is available
        if hasattr(bot, 'register_hook'):
            # Priority: higher executes first (default: 0)
            bot.register_hook("extension_loaded", self.on_ext_loaded, priority=5)
            bot.register_hook("command_executed", self.on_cmd_used)
            bot.register_hook("bot_ready", self.on_bot_ready)
    
    async def on_ext_loaded(self, bot, extension_name: str, **kwargs):
        """Called when any extension is loaded"""
        print(f"Extension loaded: {extension_name}")
    
    async def on_cmd_used(self, bot, command_name: str, author, **kwargs):
        """Called when any command is executed"""
        print(f"Command {command_name} used by {author}")
    
    async def on_bot_ready(self, bot, bot_user, **kwargs):
        """Called when bot becomes ready"""
        print(f"Bot is ready: {bot_user}")
    
    def cog_unload(self):
        """Cleanup: Unregister hooks when cog unloads"""
        if hasattr(self.bot, 'unregister_hook'):
            self.bot.unregister_hook("extension_loaded", self.on_ext_loaded)
            self.bot.unregister_hook("command_executed", self.on_cmd_used)
            self.bot.unregister_hook("bot_ready", self.on_bot_ready)

async def setup(bot):
    await bot.add_cog(HookedExtension(bot))
```

### Using Database System
```python
from discord.ext import commands
import discord

class DatabaseExtension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name="savedata")
    async def save_data(self, ctx, key: str, value: str):
        """Save data to guild database"""
        # Get guild-specific database connection
        conn = await self.bot.db._get_guild_connection(ctx.guild.id)
        
        # Create table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_data (
                key TEXT PRIMARY KEY,
                value TEXT,
                user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert or replace data
        await conn.execute(
            "INSERT OR REPLACE INTO custom_data (key, value, user_id) VALUES (?, ?, ?)",
            (key, value, ctx.author.id)
        )
        await conn.commit()
        
        await ctx.send(f"✅ Saved: {key} = {value}")
    
    @commands.hybrid_command(name="getdata")
    async def get_data(self, ctx, key: str):
        """Retrieve data from guild database"""
        conn = await self.bot.db._get_guild_connection(ctx.guild.id)
        
        async with conn.execute(
            "SELECT value, user_id FROM custom_data WHERE key = ?",
            (key,)
        ) as cursor:
            row = await cursor.fetchone()
            
            if row:
                await ctx.send(f"📄 {key} = {row['value']} (saved by <@{row['user_id']}>)")
            else:
                await ctx.send(f"❌ No data found for key: {key}")

async def setup(bot):
    await bot.add_cog(DatabaseExtension(bot))
```

### Using Atomic File Operations
```python
from discord.ext import commands
import discord
from atomic_file_system import global_file_handler
from datetime import datetime

class FileExtension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_file = "./data/my_extension_data.json"
    
    @commands.hybrid_command(name="saveconfig")
    async def save_config(self, ctx, setting: str, value: str):
        """Save configuration atomically"""
        
        # Read existing data (with caching)
        existing_data = await global_file_handler.atomic_read_json(
            self.data_file,
            use_cache=True
        ) or {}
        
        # Update data
        existing_data[setting] = {
            "value": value,
            "set_by": ctx.author.id,
            "timestamp": datetime.now().isoformat()
        }
        
        # Atomic write (invalidates cache)
        success = await global_file_handler.atomic_write_json(
            self.data_file,
            existing_data,
            invalidate_cache_after=True
        )
        
        if success:
            await ctx.send(f"✅ Configuration saved: {setting} = {value}")
        else:
            await ctx.send("❌ Failed to save configuration")
    
    @commands.hybrid_command(name="getconfig")
    async def get_config(self, ctx, setting: str = None):
        """Retrieve configuration"""
        
        # Read with caching enabled (300s TTL)
        data = await global_file_handler.atomic_read_json(
            self.data_file,
            use_cache=True
        )
        
        if not data:
            await ctx.send("❌ No configuration found")
            return
        
        if setting:
            if setting in data:
                config = data[setting]
                await ctx.send(
                    f"📄 {setting} = {config['value']}\n"
                    f"Set by: <@{config['set_by']}>\n"
                    f"Time: {config['timestamp']}"
                )
            else:
                await ctx.send(f"❌ Setting not found: {setting}")
        else:
            # Display all settings
            embed = discord.Embed(
                title="⚙️ All Configurations",
                color=0x5865f2
            )
            for key, config in data.items():
                embed.add_field(
                    name=key,
                    value=f"Value: {config['value']}\nSet by: <@{config['set_by']}>",
                    inline=False
                )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(FileExtension(bot))
```


### Advanced Extension with Permissions

```python
import discord
from discord.ext import commands
from discord import app_commands

class ModerationExtension(commands.Cog, name="Moderation"):
    """Moderation commands for server management"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(
        name="ban",
        help="Ban a user from the server"
    )
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban_user(
        self,
        ctx,
        member: discord.Member,
        *,
        reason: str = "No reason provided"
    ):
        """Ban a member with reason"""
        
        # Safety check
        if member.top_role >= ctx.author.top_role:
            await ctx.send("❌ You cannot ban this user (role hierarchy)")
            return
        
        # Perform ban
        await member.ban(reason=f"{reason} (By: {ctx.author})")
        
        # Log to database
        await self.bot.db.increment_command_usage("ban")
        
        # Send confirmation
        embed = discord.Embed(
            title="🔨 User Banned",
            description=f"**User:** {member.mention}\n**Reason:** {reason}",
            color=0xff0000,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Banned by {ctx.author}")
        
        await ctx.send(embed=embed)
        
        # Try to DM the user
        try:
            dm_embed = discord.Embed(
                title="You were banned",
                description=f"**Server:** {ctx.guild.name}\n**Reason:** {reason}",
                color=0xff0000
            )
            await member.send(embed=dm_embed)
        except:
            pass  # User has DMs disabled
    
    @commands.hybrid_command(
        name="kick",
        help="Kick a user from the server"
    )
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick_user(
        self,
        ctx,
        member: discord.Member,
        *,
        reason: str = "No reason provided"
    ):
        """Kick a member with reason"""
        
        if member.top_role >= ctx.author.top_role:
            await ctx.send("❌ You cannot kick this user (role hierarchy)")
            return
        
        await member.kick(reason=f"{reason} (By: {ctx.author})")
        await self.bot.db.increment_command_usage("kick")
        
        embed = discord.Embed(
            title="👢 User Kicked",
            description=f"**User:** {member.mention}\n**Reason:** {reason}",
            color=0xff9900,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Kicked by {ctx.author}")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ModerationExtension(bot))
```


### Extension with Background Tasks
```python
import discord
from discord.ext import commands, tasks
from datetime import datetime

class TaskExtension(commands.Cog):
    """Extension with background tasks"""
    
    def __init__(self, bot):
        self.bot = bot
        self.message_count = 0
        self.hourly_report.start()
    
    def cog_unload(self):
        """Stop tasks when unloading"""
        self.hourly_report.cancel()
    
    @tasks.loop(hours=1)
    async def hourly_report(self):
        """Send hourly statistics report"""
        channel_id = self.bot.config.get("reports_channel_id")
        if not channel_id:
            return
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
        
        embed = discord.Embed(
            title="📊 Hourly Report",
            description=f"Messages tracked: {self.message_count}",
            color=0x5865f2,
            timestamp=datetime.utcnow()
        )
        
        stats = self.bot.metrics.get_stats()
        embed.add_field(
            name="Bot Statistics",
            value=f"Commands: {stats['commands_processed']}\nErrors: {stats['error_count']}",
            inline=False
        )
        
        await channel.send(embed=embed)
        self.message_count = 0  # Reset counter
    
    @hourly_report.before_loop
    async def before_hourly_report(self):
        """Wait until bot is ready"""
        await self.bot.wait_until_ready()
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Track messages"""
        if not message.author.bot:
            self.message_count += 1

async def setup(bot):
    await bot.add_cog(TaskExtension(bot))
```
### Extension with Custom Checks
```python
import discord
from discord.ext import commands

def is_admin_or_owner():
    """Custom check for admin or bot owner"""
    async def predicate(ctx):
        if ctx.author.id == ctx.bot.bot_owner_id:
            return True
        if ctx.guild and ctx.author.guild_permissions.administrator:
            return True
        raise commands.CheckFailure("You must be an administrator or bot owner")
    return commands.check(predicate)

def has_any_role(*role_names):
    """Custom check for any of the specified roles"""
    async def predicate(ctx):
        if not ctx.guild:
            raise commands.CheckFailure("This command cannot be used in DMs")
        
        member_roles = [role.name for role in ctx.author.roles]
        if any(role in member_roles for role in role_names):
            return True
        
        raise commands.CheckFailure(f"You need one of these roles: {', '.join(role_names)}")
    return commands.check(predicate)

class CustomChecksExtension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name="adminonly")
    @is_admin_or_owner()
    async def admin_only_command(self, ctx):
        """Only admins and bot owner can use this"""
        await ctx.send("✅ You have admin privileges!")
    
    @commands.hybrid_command(name="staffonly")
    @has_any_role("Staff", "Moderator", "Admin")
    async def staff_only_command(self, ctx):
        """Only staff members can use this"""
        await ctx.send("✅ You are a staff member!")

async def setup(bot):
    await bot.add_cog(CustomChecksExtension(bot))

```

### Extension with Slash Command Options
```python

import discord
from discord.ext import commands
from discord import app_commands
from typing import Literal

class SlashOptionsExtension(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name="color")
    @app_commands.describe(
        color="Choose a color",
        intensity="Color intensity level"
    )
    async def color_command(
        self,
        ctx,
        color: Literal["red", "green", "blue"],
        intensity: int = 5
    ):
        """Command with slash options"""
        
        color_map = {
            "red": 0xff0000,
            "green": 0x00ff00,
            "blue": 0x0000ff
        }
        
        embed = discord.Embed(
            title=f"{color.capitalize()} Color",
            description=f"Intensity: {intensity}/10",
            color=color_map[color]
        )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="userinfo")
    @app_commands.describe(member="The member to get info about")
    async def userinfo_command(
        self,
        ctx,
        member: discord.Member = None
    ):
        """Get information about a user"""
        
        member = member or ctx.author
        
        embed = discord.Embed(
            title=f"User Info: {member}",
            color=member.color
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id, inline=True)
        embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
        embed.add_field(name="Roles", value=f"{len(member.roles)-1}", inline=True)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(SlashOptionsExtension(bot))
```

### ⚙️ Configuration Guide
#### Auto-Generated config.json
On first run, the bot creates config.json with default settings:

```python

{
    "prefix": "!",
    "owner_ids": [],
    "auto_reload": true,
    "status": {
        "type": "watching",
        "text": "{guilds} servers"
    },
    "database": {
        "base_path": "./data"
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
    "slash_limiter": {
        "max_limit": 100,
        "warning_threshold": 90,
        "safe_limit": 95
    },
    "framework": {
        "load_cogs": true,
        "enable_event_hooks": true,
        "enable_plugin_registry": true,
        "enable_framework_diagnostics": true,
        "enable_slash_command_limiter": true
    }
}
```

Configuration Options
Basic Settings
prefix (string)

Default command prefix
Default: "!"
Per-guild overrides supported via !setprefix

owner_ids (array)

Additional bot owner IDs
Default: []
Primary owner from BOT_OWNER_ID env variable

auto_reload (boolean)

Enable hot-reload for extensions
Default: true
Checks every 30 seconds for file changes

Status Configuration
status.type (string)

Activity type shown in Discord
Options: "playing", "watching", "listening", "competing"
Default: "watching"

status.text (string)

Status message with variables
Variables: {guilds}, {users}, {commands}
Default: "{guilds} servers"
Example: "with {users} users | {guilds} servers"

Database Configuration
database.base_path (string)

Base directory for database files
Default: "./data"
Contains main.db and per-guild databases

Logging Configuration
logging.level (string)

Logging level
Options: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
Default: "INFO"

logging.max_bytes (integer)

Max log file size before rotation
Default: 10485760 (10MB)

logging.backup_count (integer)

Number of backup log files to keep
Default: 5

Extensions Configuration
extensions.auto_load (boolean)

Automatically load all extensions on startup
Default: true

extensions.blacklist (array)

Extension names to skip during auto-load
Default: []
Example: ["debug_cog", "test_extension"]

Cooldowns Configuration
cooldowns.default_rate (integer)

Default number of command uses
Default: 3

cooldowns.default_per (float)

Default cooldown period in seconds
Default: 5.0

Slash Command Limiter
slash_limiter.max_limit (integer)

Discord's hard limit for slash commands
Default: 100
Should not be changed

slash_limiter.warning_threshold (integer)

Command count to trigger warnings
Default: 90
Logs warning at this count

slash_limiter.safe_limit (integer)

Command count to start prefix-only mode
Default: 95
New extensions become prefix-only

Framework Cogs
framework.load_cogs (boolean)

Load framework internal cogs
Default: true
Disable to use minimal framework

framework.enable_event_hooks (boolean)

Enable Event Hooks system
Default: true

framework.enable_plugin_registry (boolean)

Enable Plugin Registry system
Default: true

framework.enable_framework_diagnostics (boolean)

Enable Framework Diagnostics system
Default: true

framework.enable_slash_command_limiter (boolean)

Enable Slash Command Limiter
Default: true

Command Permissions
Configure role-based command access:


```
# Grant @Moderator access to ban command
!config ban @Moderator

# Add multiple roles
!config kick @Moderator
!config kick @Admin

# View current permissions
!config

# Remove restrictions
!config ban none
```
### Configuration Storage:
```
{
    "command_permissions": {
        "ban": [123456789, 987654321],
        "kick": [123456789]
    }
}
```


### Custom Prefixes
Set per-guild prefixes:
```
# Set prefix to ?
!setprefix ?

# Now commands work with ?
?help
?stats

# Slash commands always work regardless of prefix
/help
/stats
```
### Database Storage:
#### Stored in guild-specific database at ./data/[guild_id]/guild.db


### Environment Variables
Required .env file:



```
# Required
DISCORD_TOKEN=your_bot_token_here
BOT_OWNER_ID=your_discord_user_id

# Optional: Sharding (for large bots)
SHARD_COUNT=2

# SHARD_IDS can be commented out
SHARD_IDS=0,1
```
### Sharding Configuration:

- SHARD_COUNT: Total number of shards
- SHARD_IDS: Comma-separated list of shard IDs to run
  - Leave empty for auto-sharding


### 🗄️ Database System
#### Architecture
The framework uses a hybrid database approach:

1. Main Database (./data/main.db)
  - Global bot statistics
  - Command usage tracking
  - Framework-wide data

2. Per-Guild Databases (./data/[guild_id]/guild.db)
  - Guild-specific settings
  - Custom prefixes
  - Extension data per guild

#### Database Features
✅ WAL Mode - Write-Ahead Logging for concurrent access
✅ Connection Pooling - Automatic per-guild connection management
✅ Automatic Backups - Created on bot shutdown
✅ Orphan Cleanup - Removes connections for left guilds
✅ Atomic Operations - ACID compliance


#### Using the Database
#### Accessing Main Database

```python

# Direct access to main database
async with self.bot.db.conn.execute(
    "SELECT * FROM global_stats WHERE key = ?",
    ("some_key",)
) as cursor:
    row = await cursor.fetchone()
```
#### Accessing Guild Database
```python

# Get guild-specific connection
conn = await self.bot.db._get_guild_connection(guild_id)

# Execute queries
await conn.execute(
    "INSERT INTO custom_table (data) VALUES (?)",
    (data,)
)
await conn.commit()
```
#### Built-in Database Methods
```python

# Set guild prefix
await bot.db.set_guild_prefix(guild_id, "?")

# Get guild prefix
prefix = await bot.db.get_guild_prefix(guild_id)

# Increment command usage
await bot.db.increment_command_usage("command_name")

# Get command statistics
stats = await bot.db.get_command_stats()
# Returns: [(command_name, count), ...]

# Cleanup guild data
await bot.db.cleanup_guild(guild_id)

# Backup databases
await bot.db.backup()  # All guilds
await bot.db.backup(guild_id)  # Specific guild

```



### Database Schema
#### Main Database
global_stats
```

CREATE TABLE global_stats (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

#### Guild Database
#### guild_settings
```
CREATE TABLE guild_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
#### command_stats




```
CREATE TABLE command_stats (
    command_name TEXT PRIMARY KEY,
    usage_count INTEGER DEFAULT 0,
    last_used TIMESTAMP
)
```

### Database Maintenance
#### Automatic Maintenance (Every Hour):

- Cleans up orphaned connections
- Expires prefix cache entries
- Removes pycache directories
- Logs maintenance actions

Manual Cleanup:
```
!cleanup
```
View Database Stats:
```
!dbstats

```


### 📊 Framework Cogs System
#### Overview
**Framework cogs are internal system components that provide core functionality. They're located in ./cogs directory and are automatically loaded on startup (if enabled in config).**


#### Event Hooks System
File: cogs/event_hooks.py

**What It Does**
- Internal event system for framework lifecycle events
- Priority-based callback execution
- Asynchronous queue processing (1000 event capacity)
- Execution history tracking (100 total, 20 per event)
- Worker task for async event processing

#### Available Events: 

### Event Description Table

| Event Name            | Description                       | Parameters                               |
|-----------------------|-----------------------------------|-------------------------------------------|
| bot_ready             | Bot becomes ready                 | —                                         |
| guild_joined          | Bot joins a guild                 | guild                                     |
| guild_left            | Bot leaves a guild                | guild                                     |
| command_executed      | Command is executed               | command_name, author, guild               |
| command_error         | Command error occurs              | command_name, error, author, guild        |
| extension_loaded      | Extension is loaded (custom)      | extension_name                            |
| extension_unloaded    | Extension is unloaded (custom)    | extension_name                            |

#### Using Event Hooks

```python
# Register a hook
bot.register_hook("bot_ready", my_callback, priority=10)

# Hook callback signature
async def my_callback(bot, **kwargs):
    # bot: Bot instance
    # kwargs: Event-specific parameters
    pass

# Unregister a hook
bot.unregister_hook("bot_ready", my_callback)

# Emit custom events
await bot.emit_hook("custom_event", custom_param="value")

# List all registered hooks
hooks = bot.list_hooks()
# Returns: {"event_name": ["callback_name1", "callback_name2"], ...}

# Get execution history
history = bot.get_hook_history(limit=20)
```
#### Priority System

- Higher priority = executes first
- Default priority: 0
- Range: any integer
- Example: priority=15 runs before priority=10


#### Commands
```
# View registered hooks (Owner only)
!hooks

# View execution history (Owner only)
!hookhistory [limit]
```
# 🔐 Security Features

## Permission System

### Multi-Tier Hierarchy

#### **Bot Owner (Highest Priority)**

* Full access to all commands
* Defined in `BOT_OWNER_ID` environment variable
* Cannot be overridden

#### **Guild Owner**

* Access to server management commands
* Can configure command permissions
* Automatically detected via `guild.owner_id`

#### **Configured Roles**

* Per-command role requirements
* Set via `!config` command
* Stored in `config.json`

#### **Discord Permissions**

* Uses native Discord permission checks
* `@commands.has_permissions()`
* `@commands.bot_has_permissions()`

#### **Public Commands**

* No restrictions
* Available to all users

---

## Hardcoded Owner-Only Commands

These commands **cannot** be configured for other users:

```python
BOT_OWNER_ONLY_COMMANDS = [
    "reload", "load", "unload", "sync",
    "atomictest", "cachestats", "shardinfo",
    "dbstats", "integritycheck", "cleanup"
]
```

---

## Check Functions

### `is_bot_owner()`

```python
@commands.command()
@is_bot_owner()
async def owner_command(ctx):
    await ctx.send("Owner only!")
```

### `is_bot_owner_or_guild_owner()`

```python
@commands.command()
@is_bot_owner_or_guild_owner()
async def management_command(ctx):
    await ctx.send("Owner or guild owner!")
```

### `has_command_permission()`

```python
@commands.command()
@has_command_permission()
async def configurable_command(ctx):
    await ctx.send("Permission checked!")
```

---

# 🛡️ Interaction Security

### **User Validation**

```python
async def interaction_check(self, interaction):
    if interaction.user != self.author:
        await interaction.response.send_message(
            "❌ Only the command user can use this!",
            ephemeral=True
        )
        return False
    return True
```

### **View Timeouts**

* Default: **180–300 seconds**
* Automatically disables interactions after timeout
* Prevents stale UI elements

---

# 🗄️ Data Protection

## Atomic File Operations

Prevents:

* Data corruption during concurrent writes
* Partial file writes
* File locking issues

**How it works:**

1. Write to temporary file
2. Verify success
3. Atomic move to final location
4. Invalidate cache

---

## Database Safety

### **WAL Mode**

* Write-Ahead Logging
* Concurrent reads during writes
* ACID compliant
* Crash recovery

### **Connection Pooling**

* Per-guild isolation
* Automatic cleanup
* Lock-safe operation

### **Backups**

* Automatic on shutdown
* Manual via `!dbstats`
* Timestamped backup files

---

## File Locking

### **LRU Cache with Locks**

* Per-file lock acquisition
* Automatic cleanup (500 lock threshold)
* Prevents concurrent write conflicts

---

# 🛒 Marketplace Security

### **ZygnalID System**

* Unique bot identification
* Required for extension downloads
* Activation verification

### **License Agreement**

* Mandatory acceptance
* Per-user tracking
* Enforces usage restrictions

### **File Safety**

* Extensions stored in isolated directory
* Never auto-executed
* Manual loading required

---

# 🎨 Customization

## Embed Colors

Default color scheme:

```python
# Success
SUCCESS = 0x00ff00

# Error
ERROR = 0xff0000

# Warning
WARNING = 0xffff00

# Info
INFO = 0x5865f2

# Main Menu
MAIN_MENU = 0x2b2d31

# Credits
CREDITS = 0xffd700
```

### Custom Embed Example

```python
embed = discord.Embed(
    title="Custom Title",
    description="Custom Description",
    color=0x9b59b6  # Purple
)
```

---

## Emojis

Common Unicode emojis:

```python
# Status
"✅"  # Success
"❌"  # Error
"⚠️"  # Warning
"ℹ️"  # Info

# Actions
"🔄"  # Reload
"📊"  # Stats
"⚙️"  # Settings
"🔧"  # Tools

# Navigation
"◀"  # Previous
"▶"  # Next
"🏠"  # Home

# Categories
"📚"  # Help
"📦"  # Extensions
"🗄️"  # Database
"📊"  # Statistics
```

---

# 📝 Custom Status

Edit `config.json`:

```json
{
    "status": {
        "type": "watching",
        "text": "{guilds} servers | {users} users"
    }
}
```

### Available Types

* `playing`
* `watching`
* `listening`
* `competing`

### Available Variables

* `{guilds}` – Total server count
* `{users}` – Total user count
* `{commands}` – Total command count

---

# 🔧 Custom Prefix

### Global Default

```json
{
    "prefix": "?"
}
```

### Per-Guild

```bash
!setprefix ?
```

---

# 🆘 Custom Help Menu

```python
@bot.hybrid_command(name="myhelp")
async def custom_help(ctx):
    embed = discord.Embed(
        title="My Custom Help",
        description="Custom help menu",
        color=0x5865f2
)
# Add your fields
await ctx.send(embed=embed)
```

Then disable the built-in help in `main.py`:
Then disable the built-in help in `main.py`:
```python
bot = BotFrameWork(
    command_prefix=lambda b, m: b.get_prefix(m),
    intents=intents,
    help_command=None,  # Disable built-in help
    # ... other options
)
```

---

## 🛠 Troubleshooting

### Bot Won't Start

**Error: `DISCORD_TOKEN not found in .env!`**

Solution:
1. Create `.env` file in root directory
2. Add: `DISCORD_TOKEN=your_token_here`
3. Ensure no quotes around token
4. Ensure file is named `.env` not `.env.txt`

**Error: `BOT_OWNER_ID not found in .env!`**

Solution:
1. Add to `.env`: `BOT_OWNER_ID=your_user_id`
2. Get ID by enabling Developer Mode in Discord
3. Right-click your username → Copy ID

**Error: `discord.ext.commands.errors.ExtensionFailed`**

Solution:
1. Check logs: `cat botlogs/current_run.log`
2. Look for syntax errors in extension
3. Ensure all imports are available
4. Use `!marketplace fixdeps` for missing packages

### Extensions Not Loading

**Check logs:**
```bash
# Linux/Mac
cat botlogs/current_run.log | grep -i "extension"

# Windows
findstr /i "extension" botlogs\current_run.log
```

**Common Issues:**

1. **Missing `setup` function**
```python
   # Required in every extension
   async def setup(bot):
       await bot.add_cog(YourCog(bot))
```

2. **Syntax errors**
   - Check Python syntax
   - Ensure proper indentation
   - Validate imports

3. **Extension in blacklist**
   - Check `config.json` → `extensions.blacklist`
   - Remove extension name from list

4. **File not in `extensions/` directory**
   - Move file to `./extensions/`
   - Ensure `.py` extension

5. **Spaces in filename**
   - Framework auto-renames to underscores
   - Use `!load extension_name` (with underscores)

6. **Missing dependencies**
   - Use `!marketplace fixdeps`
   - Or manual: `pip install package_name`

### Slash Commands Not Syncing

**Manual sync:**
```bash
!sync
```

**Rate Limiting:**
- Discord limits syncs to ~2 per hour
- Bot automatically waits and retries
- Check logs for retry messages
- Wait 1 hour if rate limited

**Slash Command Limit Reached:**
```bash
# Check current usage
!slashlimit

# If at limit (100 commands):
# - New extensions become prefix-only
# - Existing slash commands still work
# - Unload unused extensions to free slots
```

**Verification:**
```bash
# Check registered commands
!extensions

# View slash command count
!stats
```

### Database Errors

**Error: `database is locked`**

Solution:
1. Ensure only one bot instance running
2. Wait for WAL checkpoint to complete
3. Restart bot if persists

**Backup and Reset:**
```bash
# Backup current database
cp data/main.db data/main.db.backup
cp -r data/[guild_id] data/[guild_id].backup

# Delete database (will regenerate)
rm data/main.db
rm -rf data/[guild_id]

# Restart bot
python main.py
```

**Check Database Stats:**
```bash
!dbstats
```

### Permission Errors

**"Missing Permissions" error:**

Solution:
1. Check bot has required Discord permissions
2. Verify role hierarchy (bot role above target roles)
3. Enable necessary intents in Developer Portal
4. Check bot permissions in channel settings

**"You don't have permission" error:**

Solution:
1. Check command permissions: `!config`
2. Verify your roles match requirements
3. Contact bot owner for access
4. Check if command is owner-only

### Memory/Performance Issues

**High Memory Usage:**

Solution:
1. Run `!cleanup` to clear caches
2. Check `!cachestats` for large caches
3. Reduce cache TTL in `atomic_file_system.py`
4. Restart bot periodically

**Slow Command Response:**

Solution:
1. Check `!stats` for latency
2. View `!dbstats` for connection issues
3. Run `!integritycheck` for system health
4. Check database file sizes
5. Consider sharding for large bots

### Marketplace Issues

**"Invalid or not activated" ZygnalID:**

Solution:
1. Get ID: `!marketplace myid` (Owner only)
2. Join ZygnalBot Discord: `gg/sgZnXca5ts`
3. Verify yourself in server
4. Open ticket for "Zygnal ID Activation"
5. Provide your ZygnalID in ticket

**Extension Install Failed:**

Solution:
1. Check error message for details
2. Verify bot has write permissions to `./extensions`
3. Ensure sufficient disk space
4. Try `!marketplace refresh`
5. Check logs: `botlogs/current_run.log`

**Missing Dependencies After Install:**

Solution:
```bash
# Automatic fix
!marketplace fixdeps

# Manual fix
pip install package_name
!reload extension_name
```

### Hot-Reload Not Working

**Issue:** File changes not detected

Solution:
1. Check `config.json` → `auto_reload: true`
2. Ensure file in `./extensions` directory
3. Wait 30 seconds for check cycle
4. Use manual reload: `!reload extension_name`
5. Check logs for reload errors

### Help Menu Issues

**Commands not showing:**

Solution:
1. Check command has `help` parameter
2. Ensure command not marked `hidden=True`
3. Verify cog loaded: `!extensions`
4. Check command registered: `!stats`

**Dropdown not working:**

Solution:
1. Ensure only command requester can use menu
2. Check view hasn't timed out (180s)
3. Verify bot has "Use Application Commands" permission
4. Try rerunning command

---

## 📈 Performance Tips

### Database Optimization

**Use Transactions for Bulk Operations:**
```python
async with bot.db.conn.execute("BEGIN"):
    for item in items:
        await bot.db.conn.execute(
            "INSERT INTO table VALUES (?)",
            (item,)
        )
    await bot.db.conn.commit()
```

**Index Frequently Queried Columns:**
```python
await conn.execute(
    "CREATE INDEX IF NOT EXISTS idx_user_id ON my_table(user_id)"
)
```

**Use LIMIT for Large Queries:**
```python
async with conn.execute(
    "SELECT * FROM large_table LIMIT 100"
) as cursor:
    rows = await cursor.fetchall()
```

### File Operations

**Use Caching for Read-Heavy Operations:**
```python
# Enable caching (300s TTL)
data = await global_file_handler.atomic_read_json(
    filepath,
    use_cache=True
)
```

**Disable Caching for Real-Time Data:**
```python
data = await global_file_handler.atomic_read_json(
    filepath,
    use_cache=False
)
```

**Batch File Operations:**
```python
# Bad: Multiple writes
for item in items:
    await global_file_handler.atomic_write_json(f"data/{item}.json", item_data)

# Good: Single write
combined_data = {item: item_data for item in items}
await global_file_handler.atomic_write_json("data/all_items.json", combined_data)
```

### Discord API

**Batch Messages:**
```python
# Bad: Individual messages
for user in users:
    await channel.send(f"Hello {user}")

# Good: Single message
await channel.send(f"Hello {', '.join(str(u) for u in users)}")
```

**Use Embeds for Rich Content:**
```python
# Embeds are more efficient than multiple messages
embed = discord.Embed(title="Data")
for key, value in data.items():
    embed.add_field(name=key, value=value)
await channel.send(embed=embed)
```

**Cache Guild/Member Data:**
```python
# Use intents to cache data
intents = discord.Intents.all()

# Access cached data (no API call)
member = guild.get_member(user_id)
```

### Extension Loading

**Blacklist Unused Extensions:**
```json
{
    "extensions": {
        "blacklist": ["debug_cog", "test_extension"]
    }
}
```

**Profile Extension Load Times:**
```python
# View load times
!extensions

# Check diagnostics
!diagnostics
```

### Memory Management

**Regular Cleanup:**
```bash
# Run periodically
!cleanup
```

**Monitor Cache Usage:**
```bash
!cachestats
```

**Limit Background Tasks:**
```python
# Increase interval for non-critical tasks
@tasks.loop(hours=6)  # Instead of minutes=5
async def background_task(self):
    pass
```

### Sharding

For bots in 2000+ guilds:
```.env
# Enable sharding
SHARD_COUNT=2
SHARD_IDS=0,1
```

**Benefits:**
- Distributes load across processes
- Reduces per-process memory
- Improved stability
- Better rate limit handling

---

## 📜 License

### MIT License
MIT License
Copyright (c) 2025 TheHolyOneZ
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
### Additional Terms

**IMPORTANT:** The following components must remain intact in all versions:

1. **CreditsButton class** in `main.py` - Must remain visible and functional
2. **Author attribution** - "TheHolyOneZ" must not be removed or altered
3. **Repository link** - GitHub link must remain in credits section
4. **Framework command** - `!discordbotframework` must remain with original features

**Marketplace License:**
Extensions downloaded through the marketplace have additional terms:
- Only usable within ZygnalBot ecosystem (including Zoryx Bot Framework)
- Cannot remove names: ZygnalBot, zygnalbot, TheHolyOneZ, TheZ
- Respect individual extension licenses
- No redistribution outside authorized systems

Violations result in ZygnalID deactivation and service ban.

---

## 🤝 Contributing

Contributions are welcome! Here's how to contribute:

### Guidelines

1. **Fork the Repository**
```bash
   git clone https://github.com/yourusername/discord-bot-framework.git
   cd discord-bot-framework
```

2. **Create Feature Branch**
```bash
   git checkout -b feature/amazing-feature
```

3. **Test Thoroughly**
   - Ensure bot starts without errors
   - Test all affected commands
   - Verify extensions load correctly
   - Check for memory leaks

4. **Follow Code Style**
   - Use type hints
   - Add docstrings to functions
   - Follow PEP 8 guidelines
   - Use meaningful variable names
   - Comment complex logic

5. **Update Documentation**
   - Update README.md if adding features
   - Add docstrings to new functions
   - Update CONTRIBUTING.md if needed

6. **Commit Changes**
```bash
   git add .
   git commit -m "Add amazing feature"
```

7. **Push to Branch**
```bash
   git push origin feature/amazing-feature
```

8. **Open Pull Request**
   - Describe changes clearly
   - Reference any related issues
   - Include screenshots if UI changes

### Code Style Example
```python
async def example_function(param: str) -> dict:
    """
    Brief description of function.
    
    Args:
        param: Description of parameter
    
    Returns:
        Description of return value
    
    Raises:
        ValueError: When param is invalid
    """
    if not param:
        raise ValueError("param cannot be empty")
    
    result = {"status": "success", "data": param}
    return result
```

### What to Contribute

**High Priority:**
- Bug fixes
- Performance improvements
- Documentation improvements
- Extension examples
- Test coverage

**Medium Priority:**
- New framework features
- Additional framework cogs
- UI/UX improvements
- Logging enhancements

**Low Priority:**
- Code refactoring
- Style improvements
- Comment additions

### Reporting Bugs

Use GitHub Issues with this template:
```markdown
**Bug Description:**
Clear description of the bug

**Steps to Reproduce:**
1. Step one
2. Step two
3. Error occurs

**Expected Behavior:**
What should happen

**Actual Behavior:**
What actually happens

**Environment:**
- Python version: 3.x.x
- discord.py version: 2.x.x
- OS: Windows/Linux/Mac

**Logs:**
```
Relevant log output

### Feature Requests

Use GitHub Issues with this template:
```markdown
**Feature Description:**
Clear description of the feature

**Use Case:**
Why this feature is needed

**Proposed Implementation:**
How it could be implemented

**Alternatives Considered:**
Other approaches considered
```

---

## 💬 Support

Need help? Have questions?

- **GitHub Issues**: [Report bugs or request features](https://github.com/TheHolyOneZ/discord-bot-framework/issues)
- **GitHub Discussions**: [Ask questions and discuss](https://github.com/TheHolyOneZ/discord-bot-framework/discussions)
- **ZygnalBot Discord**: `gg/sgZnXca5ts` (For marketplace support)

---

## 📚 Additional Resources

### Official Documentation

- **discord.py**: https://discordpy.readthedocs.io/
- **Discord Developer Portal**: https://discord.com/developers/applications
- **Python asyncio**: https://docs.python.org/3/library/asyncio.html
- **SQLite**: https://www.sqlite.org/docs.html
- **aiofiles**: https://github.com/Tinche/aiofiles
- **aiosqlite**: https://aiosqlite.omnilib.dev/

### Framework Website

- **ZygnalBot Framework**: https://zygnalbot.com/bot-framework/
- **Extension Marketplace**: https://zygnalbot.com/extension/
- **Documentation**: https://zygnalbot.com/docs/

### Learning Resources

**Discord Bot Development:**
- [Discord.py Guide](https://guide.pycord.dev/)
- [Discord API Documentation](https://discord.com/developers/docs/intro)

**Python Async Programming:**
- [Real Python - Async IO](https://realpython.com/async-io-python/)
- [Python Async/Await](https://docs.python.org/3/library/asyncio-task.html)

**Database Management:**
- [SQLite Tutorial](https://www.sqlitetutorial.net/)
- [WAL Mode Explained](https://www.sqlite.org/wal.html)

---

## 🎉 Showcase

Want to see the framework in action? Check the `/images` directory for screenshots:

- **Terminal-1.png** - Bot startup with Rich console
- **HelpMenu-Example.png** - Interactive help system
- **Marketplace-Preview.png** - Extension marketplace
- **Diagnostics.png** - Framework diagnostics dashboard
- **And more!**

---

## 👤 Author

**TheHolyOneZ**

- **GitHub**: [@TheHolyOneZ](https://github.com/TheHolyOneZ)
- **Website**: [zygnalbot.com](https://zygnalbot.com/)
- **Discord**: TheHolyOneZ

---

## 🌟 Acknowledgments

Special thanks to:

- **discord.py** - For the amazing Discord library
- **Contributors** - Everyone who has contributed to this project
- **Community** - For feedback, bug reports, and feature requests
- **You** - For using this framework!

---

<div align="center">

### ⭐ If you find this framework helpful, please consider giving it a star! ⭐

**Made with 💜 by TheHolyOneZ**

[GitHub Repository](https://github.com/TheHolyOneZ/discord-bot-framework) | [Website](https://zygnalbot.com/bot-framework/) | [Discord](gg/sgZnXca5ts)

---
