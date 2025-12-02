"""
CUSTOM LICENSE AGREEMENT FOR ZYGNALBOT EXTENSION MARKETPLACE
Copyright © 2025 TheHolyOneZ (TheZ)
All Rights Reserved

By using this marketplace extension, you agree to:
1. Only use downloaded extensions within the ZygnalBot ecosystem (including Zoryx Bot Framework)
2. Not remove, alter, or obscure any names: ZygnalBot, zygnalbot, TheHolyOneZ, TheZ
3. Respect individual extension licenses (found at the top of each downloaded file)
4. Not redistribute marketplace extensions outside of authorized systems

Violation of these terms will result in permanent ZygnalID deactivation and ban.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import aiohttp
import os
import asyncio
import logging
from datetime import datetime
import re
import io
from pathlib import Path

logger = logging.getLogger('discord')

class MarketplaceLicenseView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.accepted = False
    
    @discord.ui.button(label='✅ Accept License', style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can accept this.", ephemeral=True)
            return
        self.accepted = True
        self.stop()
        await interaction.response.edit_message(content="✅ License accepted! You can now use the marketplace.", view=None)
    
    @discord.ui.button(label='❌ Decline', style=discord.ButtonStyle.danger)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can decline this.", ephemeral=True)
            return
        self.accepted = False
        self.stop()
        await interaction.response.edit_message(content="❌ License declined. You cannot use the marketplace without accepting.", view=None)

class MarketplaceMenuView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.button(label='Browse All', style=discord.ButtonStyle.primary, emoji='📚')
    async def browse_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        data = await self.cog.fetch_extensions()
        if not data or data.get('error'):
            error_message = data.get('error', "Failed to fetch extensions!")
            embed = discord.Embed(title="❌ Error", description=error_message, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        extensions = data['extensions']
        view = ExtensionBrowserView(self.cog, extensions, 1)
        await view.send_page_interaction(interaction)
    
    @discord.ui.button(label='Search', style=discord.ButtonStyle.secondary, emoji='🔍')
    async def search_extensions(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SearchModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label='Categories', style=discord.ButtonStyle.secondary, emoji='📂')
    async def browse_categories(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        data = await self.cog.fetch_extensions()
        if not data or data.get('error'):
            error_message = data.get('error', "Failed to fetch extensions!")
            embed = discord.Embed(title="❌ Error", description=error_message, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        extensions = data['extensions']
        categories = {}
        for ext in extensions:
            status = ext.get('status', 'unknown').title()
            if status not in categories:
                categories[status] = []
            categories[status].append(ext)
        
        embed = discord.Embed(
            title="📂 Extension Categories",
            description="Browse extensions by status/category:",
            color=discord.Color.blue()
        )
        
        for category, exts in categories.items():
            embed.add_field(name=f"{category} ({len(exts)})", value=f"Extensions with {category.lower()} status", inline=True)
        
        embed.set_footer(text="Made By TheHolyOneZ")
        view = CategorySelectView(self.cog, categories)
        await interaction.followup.send(embed=embed, view=view)
    
    @discord.ui.button(label='Refresh', style=discord.ButtonStyle.success, emoji='🔄')
    async def refresh_cache(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        data = await self.cog.fetch_extensions(force_refresh=True)
        if data and data.get('extensions'):
            embed = discord.Embed(title="✅ Cache Refreshed", description=f"Successfully loaded {len(data['extensions'])} extensions!", color=discord.Color.green())
        else:
            error_message = data.get('error', "Failed to fetch extensions!")
            embed = discord.Embed(title="❌ Refresh Failed", description=error_message, color=discord.Color.red())
        embed.set_footer(text="Made By TheHolyOneZ")
        await interaction.followup.send(embed=embed, ephemeral=True)

class SearchModal(discord.ui.Modal):
    def __init__(self, cog):
        super().__init__(title="🔍 Search Extensions")
        self.cog = cog
        
        self.search_query = discord.ui.TextInput(
            label="Search Query",
            placeholder="Enter keywords to search for...",
            required=True,
            max_length=100
        )
        self.add_item(self.search_query)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        query = self.search_query.value
        
        data = await self.cog.fetch_extensions()
        if not data or data.get('error'):
            error_message = data.get('error', "Failed to fetch extensions!")
            embed = discord.Embed(title="❌ Error", description=error_message, color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        extensions = data['extensions']
        query_lower = query.lower()
        filtered_extensions = [
            ext for ext in extensions
            if query_lower in ext.get('title', '').lower() or 
               query_lower in ext.get('description', '').lower() or
               query_lower in ext.get('details', '').lower()
        ]
        
        if not filtered_extensions:
            embed = discord.Embed(title="🔍 Search Results", description=f"No extensions found matching '{query}'", color=discord.Color.orange())
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        view = ExtensionBrowserView(self.cog, filtered_extensions, 1, f"Search: {query}")
        await view.send_page_interaction(interaction)

class CategorySelectView(discord.ui.View):
    def __init__(self, cog, categories):
        super().__init__(timeout=300)
        self.cog = cog
        self.categories = categories
        
        options = []
        for category, exts in categories.items():
            emoji = "✅" if category == "Working" else "⚠️" if category == "Beta" else "❌" if category == "Broken" else "❓"
            options.append(discord.SelectOption(
                label=f"{category} ({len(exts)})",
                description=f"Browse {len(exts)} extensions with {category.lower()} status",
                emoji=emoji,
                value=category
            ))
        
        if options:
            select = discord.ui.Select(placeholder="Choose a category to browse...", options=options[:25])
            select.callback = self.category_selected
            self.add_item(select)
    
    async def category_selected(self, interaction: discord.Interaction):
        category = interaction.data['values'][0]
        extensions = self.categories[category]
        
        view = ExtensionBrowserView(self.cog, extensions, 1, f"Category: {category}")
        await view.send_page_interaction(interaction)

class ExtensionBrowserView(discord.ui.View):
    def __init__(self, cog, extensions, page=1, title_suffix=""):
        super().__init__(timeout=300)
        self.cog = cog
        self.extensions = extensions
        self.page = page
        self.title_suffix = title_suffix
        self.per_page = 5
        self.max_pages = max(1, (len(extensions) + self.per_page - 1) // self.per_page)
    
    def get_page_extensions(self):
        start = (self.page - 1) * self.per_page
        end = start + self.per_page
        return self.extensions[start:end]
    
    def create_embed(self):
        page_extensions = self.get_page_extensions()
        
        title = f"🛒 Extension Marketplace"
        if self.title_suffix:
            title += f" - {self.title_suffix}"
        
        embed = discord.Embed(
            title=title,
            description=f"Showing {len(page_extensions)} of {len(self.extensions)} extensions (Page {self.page}/{self.max_pages})",
            color=discord.Color.blue()
        )
        
        for ext in page_extensions:
            status_emoji = "✅" if ext['status'] == "working" else "⚠️" if ext['status'] == "beta" else "❌"
            
            value = f"**Description:** {ext['description'][:100]}{'...' if len(ext['description']) > 100 else ''}\n"
            value += f"**Version:** {ext['version']} | **Status:** {status_emoji} {ext['status'].title()}\n"
            value += f"**Type:** {ext['fileType'].upper()} | **Date:** {ext['date']}\n"
            value += f"**ID:** `{ext['id']}`"
            
            embed.add_field(name=f"📦 {ext['title']}", value=value, inline=False)
        
        embed.set_footer(text="Made By TheHolyOneZ • Use buttons to navigate or install extensions")
        return embed
    
    def update_buttons(self):
        self.clear_items()
        
        if self.page > 1:
            prev_button = discord.ui.Button(label='◀ Previous', style=discord.ButtonStyle.secondary)
            prev_button.callback = self.previous_page
            self.add_item(prev_button)
        
        if self.page < self.max_pages:
            next_button = discord.ui.Button(label='Next ▶', style=discord.ButtonStyle.secondary)
            next_button.callback = self.next_page
            self.add_item(next_button)
        
        page_extensions = self.get_page_extensions()
        info_select_options = []
        for ext in page_extensions:
            info_select_options.append(discord.SelectOption(
                label=f"{ext['title'][:50]}",
                description=f"ID: {ext['id']} | {ext['status'].title()}",
                value=str(ext['id']),
                emoji="📋"
            ))
        
        if info_select_options:
            info_select = discord.ui.Select(placeholder="📋 View Extension Details or Install...", options=info_select_options)
            info_select.callback = self.view_details
            self.add_item(info_select)
    
    async def previous_page(self, interaction: discord.Interaction):
        self.page = max(1, self.page - 1)
        self.update_buttons()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def next_page(self, interaction: discord.Interaction):
        self.page = min(self.max_pages, self.page + 1)
        self.update_buttons()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def view_details(self, interaction: discord.Interaction):
        ext_id = int(interaction.data['values'][0])
        extension = next((ext for ext in self.extensions if ext['id'] == ext_id), None)
        if not extension:
            await interaction.response.send_message("❌ Extension not found!", ephemeral=True)
            return
        
        view = ExtensionDetailView(self.cog, extension)
        await view.show_details_interaction(interaction)
    
    async def send_page(self, ctx):
        self.update_buttons()
        embed = self.create_embed()
        await ctx.send(embed=embed, view=self)
    
    async def send_page_interaction(self, interaction: discord.Interaction):
        self.update_buttons()
        embed = self.create_embed()
        await interaction.followup.send(embed=embed, view=self)

class ExtensionDetailView(discord.ui.View):
    def __init__(self, cog, extension):
        super().__init__(timeout=300)
        self.cog = cog
        self.extension = extension
        
        install_button = discord.ui.Button(label='📦 Install Extension', style=discord.ButtonStyle.success)
        install_button.callback = self.install_extension
        self.add_item(install_button)
        
        if extension.get('customUrl'):
            view_source_button = discord.ui.Button(label='🔗 View Source', style=discord.ButtonStyle.link, url=extension['customUrl'])
            self.add_item(view_source_button)
    
    def create_detail_embed(self):
        ext = self.extension
        status_emoji = "✅" if ext['status'] == "working" else "⚠️" if ext['status'] == "beta" else "❌"
        
        embed = discord.Embed(
            title=f"📦 {ext['title']}",
            description=ext['description'],
            color=discord.Color.green() if ext['status'] == "working" else discord.Color.orange() if ext['status'] == "beta" else discord.Color.red()
        )
        
        embed.add_field(name="🆔 ID", value=ext['id'], inline=True)
        embed.add_field(name="📊 Version", value=ext['version'], inline=True)
        embed.add_field(name="📄 File Type", value=ext['fileType'].upper(), inline=True)
        embed.add_field(name="📅 Date", value=ext['date'], inline=True)
        embed.add_field(name="🔧 Status", value=f"{status_emoji} {ext['status'].title()}", inline=True)
        embed.add_field(name="🔗 Custom URL", value="Yes" if ext.get('customUrl') else "No", inline=True)
        
        if ext.get('details'):
            details = ext['details']
            if len(details) > 1024:
                embed.add_field(name="📋 Details", value="Details are too long to display (see attached file)", inline=False)
            else:
                embed.add_field(name="📋 Details", value=details, inline=False)
        
        embed.set_footer(text="Made By TheHolyOneZ • Extension Marketplace")
        return embed
    
    async def install_extension(self, interaction: discord.Interaction):
        view = InstallConfirmView(self.cog, self.extension)
        embed = discord.Embed(
            title="📦 Install Extension",
            description=f"Are you sure you want to install **{self.extension['title']}**?",
            color=discord.Color.blue()
        )
        embed.add_field(name="Version", value=self.extension['version'], inline=True)
        embed.add_field(name="Status", value=self.extension['status'].title(), inline=True)
        embed.add_field(name="File Type", value=self.extension['fileType'].upper(), inline=True)
        embed.add_field(name="Description", value=self.extension['description'][:500] + "..." if len(self.extension['description']) > 500 else self.extension['description'], inline=False)
        embed.set_footer(text="Made By TheHolyOneZ • This will download and save the extension to your extensions folder")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def show_details_interaction(self, interaction: discord.Interaction):
        embed = self.create_detail_embed()
        details_file = None
        details = self.extension.get('details')
        if details and len(details) > 1024:
            details_file = discord.File(
                io.StringIO(details),
                filename=f"{self.extension['title'].replace(' ', '_')}_details.txt"
            )
        await interaction.response.send_message(embed=embed, view=self, file=details_file, ephemeral=True)

class InstallConfirmView(discord.ui.View):
    def __init__(self, cog, extension):
        super().__init__(timeout=60)
        self.cog = cog
        self.extension = extension
    
    @discord.ui.button(label='✅ Confirm Install', style=discord.ButtonStyle.success)
    async def confirm_install(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        embed = discord.Embed(
            title="📥 Installing Extension...",
            description=f"Downloading **{self.extension['title']}**...",
            color=discord.Color.blue()
        )
        await interaction.edit_original_response(embed=embed, view=None)
        
        filepath, message = await self.cog.download_extension(self.extension)
        
        if filepath:
            prefix = await self.cog.bot.get_prefix(interaction.message) if hasattr(interaction, 'message') and interaction.message else "!"
            if isinstance(prefix, list):
                prefix = prefix[0]
            
            ext_name = Path(filepath).stem
            
            embed = discord.Embed(
                title="✅ Extension Installed Successfully!",
                description=f"**{self.extension['title']}** has been installed to `{filepath}`",
                color=discord.Color.green()
            )
            embed.add_field(name="📁 File Location", value=f"`{filepath}`", inline=False)
            embed.add_field(
                name="🔄 Next Steps",
                value=f"**To load the extension, use ONE of these commands:**\n\n"
                      f"1️⃣ `{prefix}load {ext_name}` - Load the extension now\n"
                      f"2️⃣ `{prefix}reload {ext_name}` - If already loaded\n"
                      f"3️⃣ Restart the bot - Auto-loads all extensions\n\n"
                      f"**Extension name:** `{ext_name}`",
                inline=False
            )
            embed.add_field(
                name="⚠️ Important",
                value="• Extensions with spaces in filenames are auto-renamed with underscores\n"
                      "• Check bot logs for any loading errors\n"
                      "• Use the exact extension name shown above",
                inline=False
            )
        else:
            prefix = await self.cog.bot.get_prefix(interaction.message) if hasattr(interaction, 'message') and interaction.message else "!"
            if isinstance(prefix, list):
                prefix = prefix[0]
            
            if "403" in message or "Forbidden" in message:
                embed = discord.Embed(
                    title="❌ Installation Failed - Access Denied",
                    description=f"Failed to download **{self.extension['title']}**.",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="🔒 ZygnalID Not Activated",
                    value="Your ZygnalID is probably NOT activated or got deactivated.\n\n"
                          "**How to activate:**\n"
                          "1. Join the ZygnalBot Discord server: `gg/sgZnXca5ts`\n"
                          "2. Create a ticket with the category **Zygnal Activation**\n"
                          "3. Read the embed that got sent into the ticket\n"
                          "4. Provide the information requested\n"
                          "5. Wait for a supporter or TheHolyOneZ to activate it\n\n"
                          f"Use `{prefix}marketplace myid` to view your ZygnalID",
                    inline=False
                )
            else:
                embed = discord.Embed(
                    title="❌ Installation Failed",
                    description=f"Failed to download **{self.extension['title']}**.",
                    color=discord.Color.red()
                )
                embed.add_field(name="Error Details", value=message, inline=False)
                embed.add_field(
                    name="🔍 Troubleshooting",
                    value="• Check the error details above\n"
                          "• Ensure bot has write permissions\n"
                          "• Verify your ZygnalID is activated\n"
                          f"• Use `{prefix}marketplace myid` to view your ID",
                    inline=False
                )
        
        embed.set_footer(text="Made By TheHolyOneZ")
        await interaction.edit_original_response(embed=embed, view=None)
    
    @discord.ui.button(label='❌ Cancel', style=discord.ButtonStyle.danger)
    async def cancel_install(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ Installation Cancelled",
            description="Extension installation was cancelled.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=None)

class ExtensionMarketplace(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://zygnalbot.com/extension/api/extensions.php?action=list"
        self.extensions_folder = "./extensions"
        self.data_folder = "./data/marketplace"
        self.zygnal_id_file = os.path.join(self.data_folder, "ZygnalID.txt")
        self.license_accepted_file = os.path.join(self.data_folder, "license_accepted.json")
        self.cache = {}
        self.cache_time = None
        self.cache_duration = 300
        self.installed_deps_cache = set() 
        self.log_file_path = "botlogs/current_run.log"
        os.makedirs(self.data_folder, exist_ok=True)
        os.makedirs(self.extensions_folder, exist_ok=True)
    
    async def check_license_acceptance(self, user_id: int) -> bool:
        try:
            if os.path.exists(self.license_accepted_file):
                data = await self.bot.config.file_handler.atomic_read_json(self.license_accepted_file)
                if data and str(user_id) in data.get('accepted_users', []):
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking license acceptance: {e}")
            return False
    
    async def mark_license_accepted(self, user_id: int):
        try:
            data = {'accepted_users': []}
            if os.path.exists(self.license_accepted_file):
                existing = await self.bot.config.file_handler.atomic_read_json(self.license_accepted_file)
                if existing:
                    data = existing
            
            if str(user_id) not in data['accepted_users']:
                data['accepted_users'].append(str(user_id))
                await self.bot.config.file_handler.atomic_write_json(self.license_accepted_file, data)
            return True
        except Exception as e:
            logger.error(f"Error marking license accepted: {e}")
            return False
    
    async def show_license_agreement(self, ctx_or_interaction) -> bool:
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        user_id = ctx_or_interaction.user.id if is_interaction else ctx_or_interaction.author.id
        
        embed = discord.Embed(
            title="📜 ZygnalBot Marketplace License Agreement",
            description="**Please read and accept the following terms to use the marketplace:**",
            color=discord.Color.gold()
        )
        
        terms = [
            "1️⃣ Downloaded extensions may **ONLY** be used within the **ZygnalBot ecosystem** (including **Zoryx Bot Framework**)",
            "2️⃣ You must **NOT** remove, alter, or obscure the names: **ZygnalBot**, **zygnalbot**, **TheHolyOneZ**, **TheZ**",
            "3️⃣ Each extension has its **own license** at the top of the file - you must respect those terms",
            "4️⃣ Extensions **cannot** be redistributed outside authorized systems",
            "5️⃣ Violations will result in **permanent ZygnalID deactivation** and **ban from all services**"
        ]
        
        embed.add_field(name="📋 Terms & Conditions", value="\n\n".join(terms), inline=False)
        embed.add_field(name="⚖️ Legal Notice", value="By clicking 'Accept', you acknowledge you've read and agree to be bound by these terms.", inline=False)
        embed.set_footer(text="Copyright © 2025 TheHolyOneZ (TheZ) • All Rights Reserved")
        
        view = MarketplaceLicenseView(user_id)
        
        if is_interaction:
            await ctx_or_interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed, view=view)
        
        await view.wait()
        
        if view.accepted:
            await self.mark_license_accepted(user_id)
            return True
        return False
    
    async def cog_check(self, ctx):
        accepted = await self.check_license_acceptance(ctx.author.id)
        if not accepted:
            accepted = await self.show_license_agreement(ctx)
            if not accepted:
                raise commands.CheckFailure("You must accept the marketplace license to use these commands.")
        return True
    
    async def fetch_extensions(self, force_refresh=False):
        if not force_refresh and self.cache_time and (datetime.now() - self.cache_time).seconds < self.cache_duration:
            return self.cache
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('success'):
                            self.cache = data
                            self.cache_time = datetime.now()
                            return data
                        else:
                            logger.error("API returned success: false")
                            return None
                    elif response.status == 429:
                        return {"error": "Rate limit exceeded. Please try again in a moment."}
                    else:
                        logger.error(f"API request failed with status {response.status}")
                        return {"error": f"API request failed with status {response.status}"}
        except Exception as e:
            logger.error(f"Error fetching extensions: {e}")
            return {"error": f"Error fetching extensions: {e}"}
    
    async def download_extension(self, extension_data):
        try:
            zygnal_id = await self.ensure_zygnal_id()
            if not zygnal_id:
                error_msg = "Could not read or generate a ZygnalID. Please check file permissions."
                logger.error(error_msg)
                return None, error_msg
            
            query_suffix = f"&zygnalid={zygnal_id}"
            if extension_data.get('customUrl'):
                base_url = extension_data['customUrl']
                if base_url.startswith('http') and zygnal_id:
                    sep = '&' if ('?' in base_url) else '?'
                    download_url = f"{base_url}{sep}zygnalid={zygnal_id}"
                else:
                    download_url = base_url
            else:
                extension_id = extension_data['id']
                download_url = f"https://zygnalbot.com/extension/download.php?id={extension_id}{query_suffix}"
            
            response_text, error = await self._download_with_retry(download_url, max_retries=3)
            
            if error:
                return None, error
            
            if response_text and ("invalid" in response_text.lower() and "zygnalid" in response_text.lower()) or "not activated" in response_text.lower():
                error_message = (
                    "Your ZygnalID is **invalid or not activated**.\n\n"
                    "**To activate your ID, follow these steps:**\n"
                    "1. Go to the official ZygnalBot Discord server: `gg/sgZnXca5ts`\n"
                    "2. Verify yourself on the server.\n"
                    "3. Open a ticket for **Zygnal ID Activation**.\n"
                    "4. Read the embed sent in the ticket and provide the necessary information to start the activation process.\n\n"
                    "Use `/marketplace myid` to view your ID."
                )
                logger.error(f"Download failed due to ZygnalID issue")
                return None, error_message
            
            filename = f"{extension_data['title'].replace(' ', '_').lower()}.{extension_data['fileType']}"
            filename = re.sub(r'[^\w\-_\.]', '', filename)
            filepath = os.path.join(self.extensions_folder, filename)
            
            success = await self.bot.config.file_handler.atomic_write(filepath, response_text)
            if success:
                logger.info(f"Successfully downloaded extension to {filepath}")
                return filepath, "Success"
            else:
                return None, "Failed to write file using atomic handler"

        except Exception as e:
            error_msg = f"Download error: {e}"
            logger.error(error_msg)
            return None, error_msg
    
    async def ensure_zygnal_id(self) -> str:
        try:
            if os.path.exists(self.zygnal_id_file):
                content = await self.bot.config.file_handler.atomic_read(self.zygnal_id_file)
                if content:
                    return content.strip()
            
            import secrets
            alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
            new_id = ''.join(secrets.choice(alphabet) for _ in range(16))
            
            success = await self.bot.config.file_handler.atomic_write(self.zygnal_id_file, new_id)
            if success:
                return new_id
            return ""
        except Exception as e:
            logger.error(f"Failed to generate/read ZygnalID: {e}")
            return ""


    async def _download_with_retry(self, url: str, max_retries: int = 3) -> tuple[Optional[str], Optional[str]]:
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=60) as response:
                        if response.status == 200:
                            return await response.text(), None
                        elif response.status == 429:
                            retry_after = int(response.headers.get('Retry-After', 60))
                            if attempt < max_retries - 1:
                                logger.warning(f"Rate limited, retrying after {retry_after}s (attempt {attempt + 1}/{max_retries})")
                                await asyncio.sleep(retry_after)
                                continue
                            return None, "Rate limited (max retries reached)"
                        else:
                            return None, f"HTTP {response.status}"
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    logger.warning(f"Timeout, retrying (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None, "Timeout (max retries reached)"
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Error: {e}, retrying (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(2 ** attempt)
                    continue
                return None, f"Error: {e}"
        
        return None, "Max retries exceeded"
    @commands.hybrid_group(name='marketplace', aliases=['mp', 'mkt'], invoke_without_command=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def marketplace_group(self, ctx):
        if ctx.invoked_subcommand is None:
            await self.ensure_zygnal_id()
            embed = discord.Embed(
                title="🛒 Extension Marketplace",
                description="Browse and install extensions directly to your bot!",
                color=discord.Color.blue()
            )
            
            prefix = await self.bot.get_prefix(ctx.message)
            if isinstance(prefix, list):
                prefix = prefix[0]
            
            embed.add_field(
                name="📖 Available Commands",
                value=f"`{prefix}marketplace browse` - Browse all extensions\n"
                      f"`{prefix}marketplace search <query>` - Search extensions\n"
                      f"`{prefix}marketplace install <id>` - Install extension\n"
                      f"`{prefix}marketplace info <id>` - View details\n"
                      f"`{prefix}marketplace fixdeps` - Attempts to download dependencies for cogs/extensions that failed to load due to missing dependencies.\n"                      f"`{prefix}marketplace refresh` - Refresh list\n"
                      f"`{prefix}marketplace myid` - View your ZygnalID (Owner only)",
                inline=False
            )
            embed.add_field(
                name="⚡ Quick Actions",
                value="Use the buttons below for quick access to marketplace features!",
                inline=False
            )
            embed.set_footer(text="Made By TheHolyOneZ • ZygnalBot Marketplace v2.0")
            view = MarketplaceMenuView(self)
            await ctx.send(embed=embed, view=view)
    
    @marketplace_group.command(name='browse')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def browse_extensions(self, ctx, page: int = 1):
        await ctx.send("🔄 Loading extensions from marketplace...")
        data = await self.fetch_extensions()
        
        if not data or data.get('error'):
            error_message = data.get('error', "Failed to fetch extensions!")
            embed = discord.Embed(title="❌ Error", description=error_message, color=discord.Color.red())
            await ctx.send(embed=embed)
            return
        
        extensions = data['extensions']
        view = ExtensionBrowserView(self, extensions, page)
        await view.send_page(ctx)
    
    @marketplace_group.command(name='search')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def search_extensions(self, ctx, *, query: str):
        data = await self.fetch_extensions()
        if not data or data.get('error'):
            await ctx.send(f"❌ {data.get('error', 'Failed to fetch extensions')}")
            return
        
        query_lower = query.lower()
        filtered = [e for e in data['extensions'] if query_lower in e.get('title', '').lower() or 
                    query_lower in e.get('description', '').lower()]
        
        if not filtered:
            await ctx.send(f"🔍 No extensions found matching '{query}'")
            return
        
        view = ExtensionBrowserView(self, filtered, 1, f"Search: {query}")
        await view.send_page(ctx)
    
    @marketplace_group.command(name='install')
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def install_extension(self, ctx, extension_id: int):
        data = await self.fetch_extensions()
        if not data or data.get('error'):
            await ctx.send(f"❌ {data.get('error', 'Failed to fetch extensions')}")
            return
        
        extension = next((e for e in data['extensions'] if e['id'] == extension_id), None)
        if not extension:
            await ctx.send(f"❌ Extension with ID {extension_id} not found")
            return
        
        view = InstallConfirmView(self, extension)
        embed = discord.Embed(
            title="📦 Install Extension",
            description=f"Are you sure you want to install **{extension['title']}**?",
            color=discord.Color.blue()
        )
        embed.add_field(name="Version", value=extension['version'], inline=True)
        embed.add_field(name="Status", value=extension['status'].title(), inline=True)
        embed.add_field(name="File Type", value=extension['fileType'].upper(), inline=True)
        embed.set_footer(text="Made By TheHolyOneZ")
        await ctx.send(embed=embed, view=view)
    
    @marketplace_group.command(name='info')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def extension_info(self, ctx, extension_id: int):
        data = await self.fetch_extensions()
        if not data or data.get('error'):
            await ctx.send(f"❌ {data.get('error', 'Failed to fetch extensions')}")
            return
        
        ext = next((e for e in data['extensions'] if e['id'] == extension_id), None)
        if not ext:
            await ctx.send(f"❌ Extension with ID {extension_id} not found")
            return
        
        view = ExtensionDetailView(self, ext)
        embed = view.create_detail_embed()
        await ctx.send(embed=embed, view=view)
    
    @marketplace_group.command(name='refresh')
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def refresh_cache(self, ctx):
        msg = await ctx.send("🔄 Refreshing extension cache...")
        data = await self.fetch_extensions(force_refresh=True)
        
        if data and data.get('extensions'):
            embed = discord.Embed(
                title="✅ Cache Refreshed",
                description=f"Loaded {len(data['extensions'])} extensions",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(title="❌ Refresh Failed", 
                                description=data.get('error', 'Unknown error'), 
                                color=discord.Color.red())
        
        await msg.edit(content=None, embed=embed)
    @marketplace_group.command(name='fixdeps', description="Checks logs for failed cogs and attempts to install missing dependencies.")
    @commands.cooldown(1, 60, commands.BucketType.user)
    @commands.is_owner()
    async def fix_dependencies(self, ctx):
        await ctx.defer()


        log_file_path = "botlogs/current_run.log"
        
        if not os.path.exists(log_file_path):
            return await ctx.send(f"❌ Log file **`{log_file_path}`** not found. Cannot check for dependency errors. Please ensure the path is correct.", ephemeral=True)

        missing_modules = set()
        
        try:
            with open(log_file_path, 'r', encoding='utf-8') as f:
                log_content = f.read()
            


            pattern = re.compile(r"ModuleNotFoundError: No module named '([\w]+)'")
            
            for match in pattern.finditer(log_content):
                module_name = match.group(1)
                missing_modules.add(module_name)
                
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
            return await ctx.send(f"❌ Failed to read log file: {e}", ephemeral=True)

        if not missing_modules:
            embed = discord.Embed(
                title="✅ No Missing Dependencies Found",
                description="The log file does not show any `ModuleNotFoundError` from failed cog loading.",
                color=discord.Color.green()
            )
            return await ctx.send(embed=embed)

        await ctx.send(f"🔍 Found **{len(missing_modules)}** potential missing dependencies: `{', '.join(missing_modules)}`\n"
                       f"Attempting to install them now...", ephemeral=False)

        successfully_installed = []
        failed_to_install = []
        
        for module in missing_modules:
            try:

                process = await asyncio.create_subprocess_exec(
                    'pip', 'install', module,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    successfully_installed.append(module)
                else:

                    error_output = stderr.decode(errors='ignore').strip()
                    failed_to_install.append(f"{module} (Error: {error_output[:100]}...)")
                    logger.error(f"Failed to install {module}. Error: {error_output}")
                    
            except FileNotFoundError:

                failed_to_install.append(f"{module} (Error: pip command not found)")
                logger.error("PIP command not found. Ensure it is in the bot's path.")
            except Exception as e:
                failed_to_install.append(f"{module} (Error: {e})")
                logger.error(f"Installation of {module} failed: {e}")


        report_embed = discord.Embed(title="⚙️ Dependency Installation Report", color=discord.Color.blue())
        
        if successfully_installed:
            report_embed.add_field(
                name="✅ Installed Packages", 
                value="`" + "`, `".join(successfully_installed) + "`", 
                inline=False
            )
        
        if failed_to_install:
            report_embed.add_field(
                name="❌ Failed to Install", 
                value="\n".join(failed_to_install[:5]) + ("\n...(truncated)" if len(failed_to_install) > 5 else ""), 
                inline=False
            )
            report_embed.color = discord.Color.orange()

        if successfully_installed:

            prefix = await self.bot.get_prefix(ctx.message)
            if isinstance(prefix, list):
                prefix = prefix[0]
                
            report_embed.set_footer(text=f"Run {prefix}reload <extension_name> or restart the bot to load the extension now.")

        await ctx.send(embed=report_embed, ephemeral=False)    
    @marketplace_group.command(name='myid')
    async def myid(self, ctx):
        if ctx.author.id != self.bot.bot_owner_id:
            await ctx.send("❌ This command is bot owner only", delete_after=10)
            return
        
        zygnal_id = await self.ensure_zygnal_id()
        if zygnal_id:
            embed = discord.Embed(
                title="🔑 Your ZygnalID",
                description="Use this ID when contacting support for marketplace issues.",
                color=discord.Color.blue()
            )
            embed.add_field(name="ID", value=f"```{zygnal_id}```")
            try:
                await ctx.author.send(embed=embed)
                await ctx.message.add_reaction('✅')
            except discord.Forbidden:
                await ctx.send("❌ Couldn't DM you. Check your privacy settings.", delete_after=10)
        else:
            await ctx.send("❌ Failed to generate/read ZygnalID", delete_after=10)

async def setup(bot):
    await bot.add_cog(ExtensionMarketplace(bot))

