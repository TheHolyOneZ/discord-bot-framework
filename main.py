

"""
MIT License + Addtional Terms

Copyright (c) 2025 TheHolyOneZ

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

ADDITIONAL TERMS:
1. The file **main.py**, and any version or derivative thereof, remains under
   the MIT License and can be freely modified, provided that this license
   and the original copyright notice remain intact.

2. The **CreditsButton** class (as originally defined in the Software) must
   remain present in all distributed, forked, or modified versions of the Software.
   Its functionality and visibility must not be removed or obscured.

   Specifically:
   - The Credits Button must continue to exist and be displayed in the same
     interface location as in the original version.
   - The Credits Button must contain visible credit to the original author,
     **"TheHolyOneZ"**, and a link or reference to the original repository:
     https://github.com/TheHolyOneZ/discord-bot-framework
   - The textual credit contents (embed fields such as “Created By”, “License”,
     and related original attribution text) must remain clearly visible and
     intact. Additional information may be added, but the original credits must
     not be removed, replaced, or hidden.

3. Altering, deleting, or renaming the author’s name **"TheHolyOneZ"** in this
   license or within the Credits Button is strictly prohibited.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"""

import discord
from discord.ext import commands
import os
import asyncio
import logging
from dotenv import load_dotenv

os.makedirs("./botlogs", exist_ok=True)

logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)

permanent_handler = logging.FileHandler(
    filename='./botlogs/permanent.log',
    encoding='utf-8',
    mode='a'
)


current_handler = logging.FileHandler(
    filename='./botlogs/current_run.log',
    encoding='utf-8',
    mode='w'
)

formatter = logging.Formatter('[{asctime}] [{levelname}] {name}: {message}', 
                            style='{', 
                            datefmt='%Y-%m-%d %H:%M:%S')

permanent_handler.setFormatter(formatter)
current_handler.setFormatter(formatter)

logger.addHandler(permanent_handler)
logger.addHandler(current_handler)


console = logging.StreamHandler()
console.setFormatter(formatter)
logger.addHandler(console)


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.event
async def on_ready():
    logger.info(f"Bot is online as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Connected to {len(bot.guilds)} servers")
    await load_extensions()
    logger.info("Bot ready!")

async def load_extensions():
    loaded = 0
    failed = 0
    
    for filename in os.listdir("./extensions"):
        if filename.endswith(".py"):
            try:
                await bot.load_extension(f"extensions.{filename[:-3]}")
                logger.info(f"✓ Extension loaded: {filename}")
                loaded += 1
            except Exception as e:
                logger.error(f"✗ Failed loading {filename}: {e}")
                failed += 1
    
    logger.info(f"Extensions: {loaded} loaded, {failed} failed")

@bot.command(name="help")
async def help_command(ctx):
    categories = {}
    
    # the script detects commands from extensions by looping through all loaded cogs
    # each cog represents an extension and get_commands returns all commands in that cog
    # if the cog has commands we add it to categories dict with cog name as key
    # command descriptions come from the help parameter in the command decorator
    # example: @commands.command(help="this does something cool")
    for cog_name, cog in bot.cogs.items():
        cmds = cog.get_commands()
        if cmds:
            categories[cog_name] = cmds
    
    embed = discord.Embed(
        title="📚 Help Menu",
        description="**Select a category from the dropdown menu**\n\n"
                    f"```Available Categories: {len(categories)}```",
        color=0x2b2d31,
        timestamp=discord.utils.utcnow()
    )
    
    embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    if not categories:
        embed.description = "❌ No commands available"
        await ctx.send(embed=embed)
        return
    
    view = HelpView(categories, ctx.author)
    await ctx.send(embed=embed, view=view)
    logger.info(f"Help menu requested by {ctx.author} in {ctx.guild}")

class HelpView(discord.ui.View):
    def __init__(self, categories, author):
        super().__init__(timeout=180)
        self.categories = categories
        self.author = author
        self.add_item(CategorySelect(categories))
        self.add_item(CreditsButton())
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message(
                "❌ Only the requester can use this menu!", 
                ephemeral=True
            )
            return False
        return True

class CategorySelect(discord.ui.Select):
    def __init__(self, categories):
        options = [
            discord.SelectOption(
                label=cog_name,
                description=f"{len(cmds)} commands available",
                emoji="📁"
            )
            for cog_name, cmds in categories.items()
        ]
        super().__init__(
            placeholder="📂 Select a category...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.categories = categories
    
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        cmds = self.categories[selected]
        
        
        page = 0
        per_page = 5
        total_pages = (len(cmds) - 1) // per_page + 1
        
        embed = self.create_page_embed(selected, cmds, page, per_page, total_pages)
        
        view = CategoryView(selected, cmds, page, per_page, total_pages, interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)
        logger.info(f"{interaction.user} selected category '{selected}'")
    
    def create_page_embed(self, category, cmds, page, per_page, total_pages):
        start = page * per_page
        end = start + per_page
        
        embed = discord.Embed(
            title=f"📂 {category}",
            description=f"```Total Commands: {len(cmds)} | Page {page + 1}/{total_pages}```\n",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        for cmd in cmds[start:end]:
            cmd_help = cmd.help or "No description available"
            embed.add_field(
                name=f"▸ !{cmd.name}",
                value=f"```{cmd_help}```",
                inline=False
            )
        
        embed.set_footer(text=f"Category: {category}")
        
        return embed

class CategoryView(discord.ui.View):
    def __init__(self, category, cmds, page, per_page, total_pages, author):
        super().__init__(timeout=180)
        self.category = category
        self.cmds = cmds
        self.page = page
        self.per_page = per_page
        self.total_pages = total_pages
        self.author = author
        
        if total_pages > 1:
            self.add_item(PrevButton())
            self.add_item(NextButton())
        
        self.add_item(BackButton())
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message(
                "❌ Only the requester can use this menu!", 
                ephemeral=True
            )
            return False
        return True

class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, label="◀ Previous", row=1)
    
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if view.page > 0:
            view.page -= 1
        
        embed = self.create_page_embed(view.category, view.cmds, view.page, view.per_page, view.total_pages)
        await interaction.response.edit_message(embed=embed, view=view)
    
    def create_page_embed(self, category, cmds, page, per_page, total_pages):
        start = page * per_page
        end = start + per_page
        
        embed = discord.Embed(
            title=f"📂 {category}",
            description=f"```Total Commands: {len(cmds)} | Page {page + 1}/{total_pages}```\n",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        for cmd in cmds[start:end]:
            cmd_help = cmd.help or "No description available"
            embed.add_field(
                name=f"▸ !{cmd.name}",
                value=f"```{cmd_help}```",
                inline=False
            )
        
        embed.set_footer(text=f"Category: {category}")
        
        return embed

class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, label="Next ▶", row=1)
    
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if view.page < view.total_pages - 1:
            view.page += 1
        
        embed = self.create_page_embed(view.category, view.cmds, view.page, view.per_page, view.total_pages)
        await interaction.response.edit_message(embed=embed, view=view)
    
    def create_page_embed(self, category, cmds, page, per_page, total_pages):
        start = page * per_page
        end = start + per_page
        
        embed = discord.Embed(
            title=f"📂 {category}",
            description=f"```Total Commands: {len(cmds)} | Page {page + 1}/{total_pages}```\n",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        for cmd in cmds[start:end]:
            cmd_help = cmd.help or "No description available"
            embed.add_field(
                name=f"▸ !{cmd.name}",
                value=f"```{cmd_help}```",
                inline=False
            )
        
        embed.set_footer(text=f"Category: {category}")
        
        return embed

class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.blurple, label="🏠 Back to Main", row=1)
    
    async def callback(self, interaction: discord.Interaction):
        categories = {}
        
        for cog_name, cog in interaction.client.cogs.items():
            cmds = cog.get_commands()
            if cmds:
                categories[cog_name] = cmds
        
        embed = discord.Embed(
            title="📚 Help Menu",
            description="**Select a category from the dropdown menu**\n\n"
                        f"```Available Categories: {len(categories)}```",
            color=0x2b2d31,
            timestamp=discord.utils.utcnow()
        )
        
        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        embed.set_thumbnail(url=interaction.client.user.display_avatar.url)
        
        view = HelpView(categories, interaction.user)
        await interaction.response.edit_message(embed=embed, view=view)




class CreditsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, label="ℹ️ Credits", row=1)
    
    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="✨ Credits & System Info",
            description="**This **MAIN** bot system was crafted with care**",
            color=0xffd700,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="👤 Created By",
            value="```TheHolyOneZ```\n\nRepository\nhttps://github.com/TheHolyOneZ/discord-bot-framework",
            inline=False
        )
        
        embed.add_field(
            name="🔧 System Features",
            value=(
                "```• Dynamic Extension Loading System\n"
                "• Advanced Help Menu Structure\n"
                "• Interactive Dropdown Menus\n"
                "• Automatic Category Organization\n"
                "• Extension Info & Dynamic Loading\n"
                "• Pagination Support\n"
                "• Logging System```"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📜 License",
            value="```MIT License - Free to modify```",
            inline=False
        )
        
        embed.set_footer(text="Made with 💜 by TheHolyOneZ")
        embed.set_thumbnail(url=interaction.client.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)




@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    logger.error(f"Command Error in {ctx.guild}: {error}")





if __name__ == "__main__":
    if not TOKEN:
        logger.critical("DISCORD_TOKEN not found in .env!")
        exit(1)
    
    try:
        bot.run(TOKEN, log_handler=None)
    except Exception as e:
        logger.critical(f"Bot failed to start: {e}")




