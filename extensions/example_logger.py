from discord.ext import commands
import logging

logger = logging.getLogger('discord')

class ExampleLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Register hooks when cog loads
        if hasattr(bot, 'register_hook'):
            bot.register_hook("extension_loaded", self.on_any_extension_loaded, priority=5)
            bot.register_hook("command_executed", self.on_any_command, priority=0)
    
    async def on_any_extension_loaded(self, bot, extension_name, **kwargs):
        """Called whenever ANY extension is loaded"""
        logger.info(f"[Logger] Extension loaded: {extension_name}")
    
    async def on_any_command(self, bot, command_name, author, guild, **kwargs):
        """Called whenever ANY command is executed"""
        logger.info(f"[Logger] Command '{command_name}' used by {author} in {guild}")
    
    def cog_unload(self):
        # Unregister hooks when cog unloads
        if hasattr(self.bot, 'unregister_hook'):
            self.bot.unregister_hook("extension_loaded", self.on_any_extension_loaded)
            self.bot.unregister_hook("command_executed", self.on_any_command)

async def setup(bot):
    await bot.add_cog(ExampleLogger(bot))