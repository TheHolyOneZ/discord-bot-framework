"""
Guild Settings Cog
Manages per-guild configuration settings including mention prefix, and other guild-specific options
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional

logger = logging.getLogger('discord')


class GuildSettings(commands.Cog):
    """
    Guild-specific settings management
    Allows server administrators to configure bot behavior per-guild
    """
    
    def __init__(self, bot):
        self.bot = bot
        logger.info("GuildSettings cog loaded")
    
    def cog_unload(self):
        logger.info("GuildSettings cog unloaded")
    
    async def cog_check(self, ctx):
        """Global check: requires guild context"""
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server!")
            return False
        return True
    
    @commands.hybrid_command(
        name="mentionprefix",
        help="Enable or disable @mention prefix for this server (Admin only)"
    )
    @commands.has_permissions(administrator=True)
    @app_commands.describe(
        action="Choose to enable or disable mention prefix"
    )
    async def mention_prefix(self, ctx, action: str):
        """
        Enable or disable @mention prefix for commands in this server
        
        Usage:
            !mentionprefix enable  - Allow @BotName prefix
            !mentionprefix disable - Disable @BotName prefix
            !mentionprefix status  - Check current setting
        """
        action = action.lower()
        
        if action not in ['enable', 'disable', 'status']:
            embed = discord.Embed(
                title="❌ Invalid Action",
                description="Please use: `enable`, `disable`, or `status`",
                color=0xff0000
            )
            embed.add_field(
                name="📖 Usage Examples",
                value=(
                    "```\n"
                    f"{ctx.prefix}mentionprefix enable\n"
                    f"{ctx.prefix}mentionprefix disable\n"
                    f"{ctx.prefix}mentionprefix status\n"
                    "```"
                ),
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        # Get current setting
        current_setting = await self.bot.db.get_guild_mention_prefix_enabled(ctx.guild.id)
        if current_setting is None:
            # No guild setting, using global default
            global_default = self.bot.config.get("allow_mention_prefix", True)
            current_text = f"Using global default: {'Enabled' if global_default else 'Disabled'}"
            current_enabled = global_default
        else:
            current_text = "Enabled ✅" if current_setting else "Disabled ❌"
            current_enabled = current_setting
        
        if action == 'status':
            # Show current status
            embed = discord.Embed(
                title="🔧 Mention Prefix Status",
                description=f"Current setting for **{ctx.guild.name}**",
                color=0x5865f2
            )
            embed.add_field(
                name="Status",
                value=f"```{current_text}```",
                inline=False
            )
            
            if current_enabled:
                embed.add_field(
                    name="✅ Users can invoke commands with:",
                    value=(
                        f"```\n"
                        f"• Prefix: {ctx.prefix}help\n"
                        f"• Slash: /help\n"
                        f"• Mention: @{self.bot.user.name} help\n"
                        f"```"
                    ),
                    inline=False
                )
            else:
                embed.add_field(
                    name="⚠️ Users can invoke commands with:",
                    value=(
                        f"```\n"
                        f"• Prefix: {ctx.prefix}help\n"
                        f"• Slash: /help\n"
                        f"• Mention: DISABLED\n"
                        f"```"
                    ),
                    inline=False
                )
            
            embed.set_footer(text=f"Server ID: {ctx.guild.id}")
            await ctx.send(embed=embed)
            return
        
        elif action == 'enable':
            if current_enabled:
                embed = discord.Embed(
                    title="ℹ️ Already Enabled",
                    description=f"Mention prefix is already enabled for **{ctx.guild.name}**",
                    color=0x5865f2
                )
                await ctx.send(embed=embed)
                return
            
            # Enable mention prefix
            await self.bot.db.set_guild_mention_prefix_enabled(ctx.guild.id, True)
            
            embed = discord.Embed(
                title="✅ Mention Prefix Enabled",
                description=f"Users can now use @{self.bot.user.name} to invoke commands!",
                color=0x00ff00
            )
            embed.add_field(
                name="📖 Example Usage",
                value=(
                    f"```\n"
                    f"@{self.bot.user.name} help\n"
                    f"@{self.bot.user.name} stats\n"
                    f"```"
                ),
                inline=False
            )
            embed.set_footer(text=f"Changed by {ctx.author}")
            await ctx.send(embed=embed)
            
            logger.info(f"Mention prefix ENABLED for guild {ctx.guild.id} ({ctx.guild.name}) by {ctx.author}")
            
        elif action == 'disable':
            if not current_enabled:
                embed = discord.Embed(
                    title="ℹ️ Already Disabled",
                    description=f"Mention prefix is already disabled for **{ctx.guild.name}**",
                    color=0x5865f2
                )
                await ctx.send(embed=embed)
                return
            
            # Disable mention prefix
            await self.bot.db.set_guild_mention_prefix_enabled(ctx.guild.id, False)
            
            embed = discord.Embed(
                title="⚠️ Mention Prefix Disabled",
                description=f"Users can no longer use @{self.bot.user.name} to invoke commands",
                color=0xff9900
            )
            embed.add_field(
                name="ℹ️ Commands still work with:",
                value=(
                    f"```\n"
                    f"• Prefix: {ctx.prefix}help\n"
                    f"• Slash: /help\n"
                    f"```"
                ),
                inline=False
            )
            embed.set_footer(text=f"Changed by {ctx.author}")
            await ctx.send(embed=embed)
            
            logger.info(f"Mention prefix DISABLED for guild {ctx.guild.id} ({ctx.guild.name}) by {ctx.author}")
    
    @commands.hybrid_command(
        name="serversettings",
        help="View all current server settings (Admin only)"
    )
    @commands.has_permissions(administrator=True)
    async def server_settings(self, ctx):
        """Display all current server configuration settings"""
        
        embed = discord.Embed(
            title=f"⚙️ Server Settings - {ctx.guild.name}",
            description="Current configuration for this server",
            color=0x5865f2,
            timestamp=discord.utils.utcnow()
        )
        
        # Get custom prefix
        custom_prefix = await self.bot.db.get_guild_prefix(ctx.guild.id)
        if custom_prefix:
            prefix_text = f"Custom: `{custom_prefix}`"
        else:
            default_prefix = self.bot.config.get("prefix", "!")
            prefix_text = f"Default: `{default_prefix}`"
        
        embed.add_field(
            name="🔖 Command Prefix",
            value=prefix_text,
            inline=True
        )
        
        # Get mention prefix setting
        mention_enabled = await self.bot.db.get_guild_mention_prefix_enabled(ctx.guild.id)
        if mention_enabled is None:
            # Using global default
            global_default = self.bot.config.get("allow_mention_prefix", True)
            mention_text = f"Global Default: {'✅ Enabled' if global_default else '❌ Disabled'}"
        else:
            mention_text = "✅ Enabled" if mention_enabled else "❌ Disabled"
        
        embed.add_field(
            name="📢 Mention Prefix",
            value=mention_text,
            inline=True
        )
        
        # Server info
        embed.add_field(
            name="📊 Server Info",
            value=(
                f"```\n"
                f"Members: {ctx.guild.member_count}\n"
                f"Owner: {ctx.guild.owner}\n"
                f"```"
            ),
            inline=False
        )
        
        # Command invocation methods
        current_prefix = custom_prefix if custom_prefix else self.bot.config.get("prefix", "!")
        mention_active = mention_enabled if mention_enabled is not None else self.bot.config.get("allow_mention_prefix", True)
        
        invocation_methods = [
            f"✅ Prefix: `{current_prefix}help`",
            f"✅ Slash: `/help`",
            f"{'✅' if mention_active else '❌'} Mention: `@{self.bot.user.name} help`"
        ]
        
        embed.add_field(
            name="📝 Command Invocation Methods",
            value="\n".join(invocation_methods),
            inline=False
        )
        
        embed.set_footer(text=f"Server ID: {ctx.guild.id} | Requested by {ctx.author}")
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
        
        await ctx.send(embed=embed)
    
    @mention_prefix.error
    async def mention_prefix_error(self, ctx, error):
        """Error handler for mentionprefix command"""
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="You need **Administrator** permission to use this command!",
                color=0xff0000
            )
            await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command cannot be used in DMs!")
        else:
            logger.error(f"Error in mentionprefix command: {error}")
    
    @server_settings.error
    async def server_settings_error(self, ctx, error):
        """Error handler for serversettings command"""
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="You need **Administrator** permission to use this command!",
                color=0xff0000
            )
            await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command cannot be used in DMs!")
        else:
            logger.error(f"Error in serversettings command: {error}")


async def setup(bot):
    """Load the GuildSettings cog"""
    await bot.add_cog(GuildSettings(bot))
    logger.info("GuildSettings cog setup complete")