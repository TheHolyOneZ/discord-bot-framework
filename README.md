# Discord Bot Framework

A powerful, modular Discord bot framework with dynamic extension loading, interactive help menus, and comprehensive logging. Perfect for developers who want to build feature-rich Discord bots with a clean, organized structure.

## ✨ Features

- **🔌 Dynamic Extension System**: Automatically loads all extensions from the `extensions/` folder
- **📚 Interactive Help Menu**: Beautiful dropdown-based help system with category organization
- **📄 Pagination Support**: Built-in pagination for commands with multiple pages
- **📊 Comprehensive Logging**: Dual logging system (permanent + current run logs)
- **🎨 Modern UI Components**: Pre-built buttons, dropdowns, and interactive elements
- **⚡ Easy to Extend**: Simple cog-based architecture for adding new features
- **🛡️ Permission Handling**: Built-in interaction checks and error handling

## 📋 Requirements

- Python 3.8 or higher | Built with py 3.12.7
- discord.py 2.0+      | Built with discord.py 2.6.3
- python-dotenv        | Built with dotenv 1.0.0

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/TheHolyOneZ/discord-bot-framework.git
cd discord-bot-framework

# Install dependencies
pip install -r requirements.txt
```

### 2. Setup

Create a `.env` file in the root directory:

```env
DISCORD_TOKEN=your_bot_token_here
```

### 3. Create Extensions Folder

```bash
mkdir extensions
```

### 4. Run the Bot

```bash
python main.py
```

## 📁 Project Structure

```
discord-bot-framework/
│
├── main.py              # Main bot file with help system
├── extensions/          # Place your cog files here
│   ├── example.py
│   └── ...
├── botlogs/            # Auto-generated log files
│   ├── permanent.log
│   └── current_run.log
├── .env                # Your bot token (don't commit!)
├── requirements.txt    # Python dependencies
└── README.md          # You are here
```

## 🔧 Creating Extensions

Extensions are organized as Discord.py cogs. Here's a simple example:

```python
import discord
from discord.ext import commands

class ExampleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(help="Says hello to the user")
    async def hello(self, ctx):
        await ctx.send(f"Hello, {ctx.author.mention}!")
    
    @commands.command(help="Adds two numbers together")
    async def add(self, ctx, num1: int, num2: int):
        result = num1 + num2
        await ctx.send(f"{num1} + {num2} = {result}")

async def setup(bot):
    await bot.add_cog(ExampleCog(bot))
```

Save this as `extensions/example.py` and the bot will automatically load it on startup!

## 📚 Help Menu Usage

The framework includes a sophisticated help menu system:

- **Command**: `!help`
- **Features**:
  - Dropdown menu for category selection
  - Automatic command organization by cog
  - Pagination for categories with many commands
  - Credits button with system information
  - User-specific interaction (only requester can use buttons)

## 🔍 Logging System

The bot uses a dual logging system:

- **`permanent.log`**: Appends all bot activity across runs
- **`current_run.log`**: Overwrites each time the bot starts (current session only)
- **Console output**: Real-time logging in your terminal

All logs include timestamps, log levels, and detailed information.

## ⚙️ Configuration

### Intents

The bot uses `discord.Intents.all()` by default. If you want to restrict this:

```python
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
# Add other intents as needed
```

### Command Prefix

Default prefix is `!`. To change it:

```python
bot = commands.Bot(command_prefix="?", intents=intents, help_command=None)
```

## 🎨 Customization

### Colors

The framework uses Discord's color scheme:
- Main menu: `0x2b2d31` (Dark gray)
- Categories: `0x5865f2` (Blurple)
- Credits: `0xffd700` (Gold)

Modify these in the embed creation sections of `main.py`.

### Emojis

The help menu uses Unicode emojis. Feel free to customize them or use custom Discord emojis.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. Make sure to:

1. Test your changes thoroughly
2. Follow the existing code style
3. Update documentation if needed
4. Respect the license terms (see LICENSE in `main.py`)

## 📜 License

This project is licensed under the MIT License with additional terms:

**Additional Terms:**
- The `CreditsButton` class must remain in all versions
- Original author credit ("TheHolyOneZ") must not be removed
- Credits button must remain visible and functional

See the full license in `main.py` for details.

## 🐛 Troubleshooting

### Bot won't start
- Verify your token in `.env` is correct
- Check that you have enabled the necessary intents in Discord Developer Portal

### Extensions not loading
- Ensure files are in the `extensions/` folder
- Check that each extension has an `async def setup(bot)` function
- Review `botlogs/current_run.log` for error details

### Help menu not showing commands
- Make sure your commands have the `help` parameter set
- Verify cogs are properly loaded (check logs)
- Ensure commands are not hidden

## 💡 Tips

- Use descriptive names for your extension files (e.g., `moderation.py`, `fun.py`)
- Add helpful descriptions to all commands using the `help` parameter
- Organize related commands into the same cog
- Check logs regularly to catch issues early

## 👤 Author

**TheHolyOneZ**
- GitHub: [@TheHolyOneZ](https://github.com/TheHolyOneZ)

---

⭐ If you find this framework helpful, please consider giving it a star!

Made with 💜 by TheHolyOneZ
