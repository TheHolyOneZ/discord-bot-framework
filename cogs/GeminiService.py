"""
# ===================================================================================
#
#   Copyright (c) 2026 TheHolyOneZ
#
#   This script is part of the ZDBF (Zoryx Discord Bot Framework).
#   This file is considered source-available and is not open-source.
#
#   You are granted permission to:
#   - View, read, and learn from this source code.
#   - Use this script 'as is' within the ZDBF.
#   - Run this script in multiple instances of your own ZDBF-based projects,
#     provided the license and script remain intact.
#
#   You are strictly prohibited from:
#   - Copying and pasting more than four (4) consecutive lines of this code
#     into other projects without explicit permission.
#   - Redistributing this script or any part of it. The only official source
#     is the GitHub repository: https://github.com/TheHolyOneZ/discord-bot-framework
#   - Modifying this license text.
#   - Removing any attribution or mention of the original author (TheHolyOneZ)
#     or the project names (ZDBF, TheZ).
#
#   This script is intended for use ONLY within the ZDBF ecosystem.
#   Use in any other framework is a direct violation of this license.
#
#   For issues, support, or feedback, please create an issue on the official
#   GitHub repository or contact the author through the official Discord server.
#
#   This software is provided "as is", without warranty of any kind, express or
#   implied, including but not limited to the warranties of merchantability,
#   fitness for a particular purpose and noninfringement. In no event shall the
#   authors or copyright holders be liable for any claim, damages or other
#   liability, whether in an action of contract, tort or otherwise, arising from,
#   out of or in connection with the software or the use or other dealings in the
#   software.
#
# ===================================================================================
"""
import discord
from discord.ext import commands
from discord import app_commands
import os
import google.generativeai as genai
from dotenv import load_dotenv
from atomic_file_system import AtomicFileHandler, SafeDatabaseManager
from cogs.plugin_registry import PluginRegistry
from cogs.framework_diagnostics import FrameworkDiagnostics
import aiosqlite
import aiofiles
import json
from typing import List, Dict, Optional
import tempfile
import glob as glob_lib
import asyncio
import time

load_dotenv()

async def ask_zdbf_autocomplete(interaction: discord.Interaction, current: str):
    
    choices = [
        "help", "framework", "plugins", "diagnose", "database", "file",
        "extension", "permission", "slash", "hooks", "automations", "readme"
    ]
    
    filtered_choices = [
        app_commands.Choice(name=choice, value=choice)
        for choice in choices if current.lower() in choice.lower()
    ]
    

    try:

        if not interaction.response.is_done():
            await interaction.response.autocomplete(filtered_choices)
    except discord.errors.NotFound:

        pass
    except discord.errors.HTTPException:

        pass
    except Exception:

        pass

class HelpView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=86400)
        self.author_id = author_id
        self.current_page = 0
        self.pages = self._create_pages()
        self._interaction_lock = asyncio.Lock()  
        self._last_interaction_time = 0  

    def _create_pages(self) -> List[discord.Embed]:
        main_embed = discord.Embed(title="`/ask_zdbf` Help Menu", description="This is an interactive guide for the AI assistant. Use the buttons to navigate.", color=0x7289DA).set_footer(text="Page 1/12 - Main Menu")
        
        framework_embed = discord.Embed(title="Action: `framework`", color=0x7289DA)
        framework_embed.add_field(name="Description", value="Ask a general question about the bot's code, architecture, or functionality.", inline=False)
        framework_embed.add_field(name="Usage", value="`/ask_zdbf action:framework query:<your question>`", inline=False)
        framework_embed.add_field(name="Example", value="`/ask_zdbf action:framework query:What is the purpose of the PluginRegistry cog?`", inline=False)
        framework_embed.set_footer(text="Page 2/12 - Framework")

        plugins_embed = discord.Embed(title="Action: `plugins`", color=0x7289DA)
        plugins_embed.add_field(name="Description", value="Get an AI-powered analysis of installed plugins or ask a specific question.", inline=False)
        plugins_embed.add_field(name="Usage", value="`/ask_zdbf action:plugins query:[your question]`", inline=False)
        plugins_embed.add_field(name="Example", value="`/ask_zdbf action:plugins query:Which plugins have dependencies?`", inline=False)
        plugins_embed.set_footer(text="Page 3/12 - Plugins")

        diagnose_embed = discord.Embed(title="Action: `diagnose`", color=0x7289DA)
        diagnose_embed.add_field(name="Description", value="Get an AI-powered health report or ask about specific metrics.", inline=False)
        diagnose_embed.add_field(name="Usage", value="`/ask_zdbf action:diagnose query:[your question]`", inline=False)
        diagnose_embed.add_field(name="Example", value="`/ask_zdbf action:diagnose query:What is the current memory usage in MB?`", inline=False)
        diagnose_embed.set_footer(text="Page 4/12 - Diagnose")

        database_embed = discord.Embed(title="Action: `database`", color=0x7289DA)
        database_embed.add_field(name="Description", value="Ask a question about the bot's database in natural language.", inline=False)
        database_embed.add_field(name="Usage", value="`/ask_zdbf action:database query:<your question>`", inline=False)
        database_embed.add_field(name="Example", value="`/ask_zdbf action:database query:How many tables are in the database?`", inline=False)
        database_embed.set_footer(text="Page 5/12 - Database")

        file_embed = discord.Embed(title="Action: `file`", color=0x7289DA)
        file_embed.add_field(name="Description", value="Ask a specific question about a file's content.", inline=False)
        file_embed.add_field(name="Usage", value="`/ask_zdbf action:file file:<filepath> query:<your question>`", inline=False)
        file_embed.add_field(name="Example", value="`/ask_zdbf action:file file:cogs/GeminiService.py query:What does the GeminiService cog do?`", inline=False)
        file_embed.set_footer(text="Page 6/12 - File")

        extension_embed = discord.Embed(title="Action: `extension`", color=0x7289DA)
        extension_embed.add_field(name="Description", value="Inspect an extension file from the `/extensions` folder.", inline=False)
        extension_embed.add_field(name="Usage", value="`/ask_zdbf action:extension file:<filename> query:[question]`", inline=False)
        extension_embed.add_field(name="Example", value="`/ask_zdbf action:extension file:example_logger.py query:Summarize what this extension does.`", inline=False)
        extension_embed.set_footer(text="Page 7/12 - Extension")

        slash_embed = discord.Embed(title="Action: `slash`", color=0x7289DA)
        slash_embed.add_field(name="Description", value="Ask about the bot's slash command usage and the auto-conversion system.", inline=False)
        slash_embed.add_field(name="Usage", value="`/ask_zdbf action:slash query:[your question]`", inline=False)
        slash_embed.add_field(name="Example", value="`/ask_zdbf action:slash query:Are there any commands that have been converted to prefix commands?`", inline=False)
        slash_embed.set_footer(text="Page 8/12 - Slash Limiter")

        hooks_embed = discord.Embed(title="Action: `hooks`", color=0x7289DA)
        hooks_embed.add_field(name="Description", value="Ask about the internal framework (EventHooks) event system.", inline=False)
        hooks_embed.add_field(name="Usage", value="`/ask_zdbf action:hooks query:[your question]`", inline=False)
        hooks_embed.add_field(name="Example", value="`/ask_zdbf action:hooks query:List all registered event hooks.`", inline=False)
        hooks_embed.set_footer(text="Page 9/12 - Internal Hooks")

        automations_embed = discord.Embed(title="Action: `automations`", color=0x7289DA)
        automations_embed.add_field(name="Description", value="Ask about user-created automations (e.g., welcome messages, reaction roles).", inline=False)
        automations_embed.add_field(name="Usage", value="`/ask_zdbf action:automations query:[your question]`", inline=False)
        automations_embed.add_field(name="Example", value="`/ask_zdbf action:automations query:What are the statistics for all automations?`", inline=False)
        automations_embed.set_footer(text="Page 10/12 - User Automations")

        readme_embed = discord.Embed(title="Action: `readme`", color=0x7289DA)
        readme_embed.add_field(name="Description", value="Ask a question about the bot's `README.md` file. The AI will search and summarize relevant parts.", inline=False)
        readme_embed.add_field(name="Usage", value="`/ask_zdbf action:readme query:<your question>`", inline=False)
        readme_embed.add_field(name="Example", value="`/ask_zdbf action:readme query:How do I set up the live monitor?`", inline=False)
        readme_embed.set_footer(text="Page 11/12 - README")
        
        permission_embed = discord.Embed(title="Action: `permission` (Bot Owner Only)", color=0x7289DA)
        permission_embed.add_field(name="Description", value="Manage which users can use specific actions of this command.", inline=False)
        permission_embed.add_field(name="Usage", value="`/ask_zdbf action:permission`", inline=False)
        permission_embed.set_footer(text="Page 12/12 - Permission")
        
        return [main_embed, framework_embed, plugins_embed, diagnose_embed, database_embed, file_embed, extension_embed, slash_embed, hooks_embed, automations_embed, readme_embed, permission_embed]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        
        if interaction.user.id != self.author_id:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("You cannot interact with this help menu.", ephemeral=True)
            except (discord.errors.NotFound, discord.errors.HTTPException):
                pass
            return False
        return True

    async def _safe_edit(self, interaction: discord.Interaction, **kwargs):
        
        try:

            if not interaction.response.is_done():
                await interaction.response.edit_message(**kwargs)
            else:

                await interaction.edit_original_response(**kwargs)
        except discord.errors.NotFound:

            pass
        except discord.errors.HTTPException as e:

            print(f"HTTP error in button interaction: {e}")
        except Exception as e:

            print(f"Unexpected error in button interaction: {e}")

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.grey, custom_id="help_prev_button_final_v3")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        

        current_time = time.time()
        if current_time - self._last_interaction_time < 0.5:

            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except:
                pass
            return
        
        async with self._interaction_lock:
            self._last_interaction_time = current_time
            self.current_page = (self.current_page - 1) % len(self.pages)
            await self._safe_edit(interaction, embed=self.pages[self.current_page])

    @discord.ui.button(label="Next", style=discord.ButtonStyle.grey, custom_id="help_next_button_final_v3")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        

        current_time = time.time()
        if current_time - self._last_interaction_time < 0.5:

            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except:
                pass
            return
        
        async with self._interaction_lock:
            self._last_interaction_time = current_time
            self.current_page = (self.current_page + 1) % len(self.pages)
            await self._safe_edit(interaction, embed=self.pages[self.current_page])

class GeminiService(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = None
        self.db_manager = None
        self.file_handler = None
        
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model_name = "gemini-2.0-flash-lite"
        
        self.model = genai.GenerativeModel(model_name)
        print(f"[GeminiService] Using model: {model_name}")
        
        db_path = os.getenv("DATABASE_PATH", "bot_data.db")
        self.db_manager = SafeDatabaseManager(db_path)
        self.file_handler = AtomicFileHandler()
        
    @app_commands.command(name="ask_zdbf", description="Ask the ZDBF AI assistant about various bot aspects.")
    @app_commands.describe(
        action="The action to perform (help, framework, plugins, etc.)",
        query="The specific question you want to ask (optional for some actions).",
        file="The file to inspect (required for 'file' and 'extension' actions)."
    )
    @app_commands.autocomplete(action=ask_zdbf_autocomplete)
    async def ask_zdbf_slash(
        self,
        interaction: discord.Interaction,
        action: str,
        query: Optional[str] = None,
        file: Optional[str] = None
    ):
        
        

        try:
            await interaction.response.defer(ephemeral=(action != "help"))
        except discord.errors.NotFound:

            return
        except discord.errors.HTTPException:

            return
        
        try:
            action = action.lower()


            if action == "help":
                view = HelpView(interaction.user.id)
                try:

                    await interaction.followup.send(embed=view.pages[0], view=view, ephemeral=False)
                except discord.errors.NotFound:

                    pass
                return


            if action == "permission":
                app_info = await self.bot.application_info()
                if interaction.user.id != app_info.owner.id:
                    return await interaction.followup.send("This action is restricted to the bot owner.", ephemeral=True)

                embed = discord.Embed(
                    title="Permission Management",
                    description="This feature allows you to control who can use which actions of `/ask_zdbf`.\n\n"
                                "**Currently:** All users can use all actions.\n\n"
                                "To restrict actions, you would need to implement a permission system in your database.",
                    color=0x7289DA
                )
                return await interaction.followup.send(embed=embed, ephemeral=True)





            strict_prompt = (
                "You are an AI assistant for the ZDBF (Zoryx Discord Bot Framework). "
                "Your job is to answer questions about the bot's code, configuration, and data. "
                "Always provide accurate, concise, and helpful responses. "
                "If you don't have enough information, say so clearly."
            )

            embed = discord.Embed(color=0x7289DA)
            context = ""
            final_query = query or "Please provide an overview of this component."


            if action == "framework":

                context = (
                    "The ZDBF (Zoryx Discord Bot Framework) is a modular Discord bot framework using discord.py. "
                    "Key features include:\n"
                    "- **Cog-based Architecture**: Core functionalities are separated into cogs like `PluginRegistry`, `FrameworkDiagnostics`, and `GeminiService`.\n"
                    "- **Atomic File System**: `atomic_file_system.py` provides thread-safe file operations to prevent data corruption.\n"
                    "- **Plugin Registry**: `cogs/plugin_registry.py` manages extensions (plugins), tracking metadata, dependencies, and conflicts.\n"
                    "- **Event Hooks**: An internal system (`cogs/event_hooks.py`) allows cogs to communicate and extend functionality without direct dependencies.\n"
                    "- **Slash Command Limiter**: `cogs/slash_command_limiter.py` automatically converts slash commands to prefix commands if Discord's 100-command limit is reached.\n"
                    "- **Diagnostics**: `cogs/framework_diagnostics.py` monitors bot health, performance, and configuration."
                )
                final_query = query or "Explain the overall purpose and architecture of the bot framework."

            elif action == "plugins":
                plugin_registry = self.bot.get_cog("PluginRegistry")
                if not plugin_registry:
                    return await interaction.followup.send("PluginRegistry cog not found.", ephemeral=True)
                
                plugins = plugin_registry.get_all_plugins()
                plugin_data = {name: data.to_dict() for name, data in plugins.items()}
                
                context = f"Here is the data for all installed plugins:\n\n{json.dumps(plugin_data, indent=2)}"
                final_query = query or "Provide a summary of all installed plugins, including their status and dependencies."

            elif action == "diagnose":
                diagnostics = self.bot.get_cog("FrameworkDiagnostics")
                if not diagnostics:
                    return await interaction.followup.send("FrameworkDiagnostics cog not found.", ephemeral=True)
                
                report = await diagnostics.generate_diagnostics()
                context = f"Here is the current diagnostic report:\n\n{json.dumps(report, indent=2)}"
                final_query = query or "Summarize the health and performance of the bot based on the diagnostic report."

            elif action == "slash":
                slash_limiter = self.bot.get_cog("SlashLimiter")
                if not slash_limiter:
                    return await interaction.followup.send("SlashLimiter cog not found.", ephemeral=True)
                
                limit_status = await slash_limiter.check_slash_command_limit()
                converted = slash_limiter.get_converted_commands()
                blocked = list(slash_limiter._blocked_commands.keys())
                
                slash_context = {
                    "limit_status": limit_status,
                    "converted_commands": converted,
                    "blocked_commands": blocked
                }
                context = f"Here is the data from the SlashCommandLimiter:\n\n{json.dumps(slash_context, indent=2)}"
                final_query = query or "Summarize the current slash command limit status, including any converted or blocked commands."

            elif action == "hooks":
                event_hooks = self.bot.get_cog("EventHooks")
                if not event_hooks:
                    return await interaction.followup.send("EventHooks cog not found.", ephemeral=True)
                
                hooks_list = event_hooks.list_hooks()
                history = event_hooks.get_hook_history(limit=20)
                metrics = event_hooks.metrics
                
                hooks_context = {
                    "registered_hooks": hooks_list,
                    "execution_history": history,
                    "metrics": metrics
                }
                context = f"Here is the data for the internal framework EventHooks system:\n\n{json.dumps(hooks_context, indent=2)}"
                final_query = query or "Provide an overview of the internal event hooks system, highlighting the number of registered hooks and recent activity."

            elif action == "automations":
                hook_creator = self.bot.get_cog("EventHooksCreater")
                if not hook_creator:
                    return await interaction.followup.send("EventHooksCreater cog not found.", ephemeral=True)
                
                stats = hook_creator.get_hook_stats()
                created = hook_creator.get_all_created_hooks()
                
                automations_context = {
                    "statistics": stats,
                    "created_automations": created
                }
                context = f"Here is the data for user-created automations from EventHooksCreater:\n\n{json.dumps(automations_context, indent=2)}"
                final_query = query or "Summarize the user-created automations, including total counts, executions, and error rates."
            
            elif action == "database":
                if not self.db_manager:
                    return await interaction.followup.send("Database manager not found.", ephemeral=True)
                
                schema_info = {}
                try:
                    if not self.db_manager.conn:
                        await self.db_manager.connect()
                    

                    cursor = await self.db_manager.conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
                    tables = await cursor.fetchall()
                    schema_info["main_database"] = {row[0]: row[1] for row in tables}
                except aiosqlite.OperationalError:

                    schema_info["main_database"] = {"error": "Could not fetch schema. This may be because a non-SQLite database is in use."}
                except Exception as e:
                    schema_info["main_database"] = {"error": f"An unexpected error occurred while fetching schema: {e}"}

                schema_info["guild_databases"] = "Each server has its own database with tables like 'guild_settings' and 'command_stats'."

                context = f"Here is the database schema and table information:\n\n{json.dumps(schema_info, indent=2)}"
                final_query = query or "Describe the purpose of each table in the database."

            elif action == "file" or action == "extension":
                if not file:
                    return await interaction.followup.send(f"You must provide a filename for the `{action}` action.", ephemeral=True)
                
                base_path = "extensions/" if action == "extension" else ""
                

                safe_filename = file.lstrip("./\\").replace("..", "")
                file_path = os.path.join(base_path, safe_filename)
                
                if not os.path.exists(file_path):
                    return await interaction.followup.send(f"File not found: `{file_path}`", ephemeral=True)

                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        file_content = await f.read()
                    context = f"Here is the content of the file `{file_path}`:\n\n```python\n{file_content}\n```"
                    final_query = query or f"Explain the purpose of the file `{file_path}`."
                except Exception as e:
                    return await interaction.followup.send(f"Error reading file `{file_path}`: {e}", ephemeral=True)

            elif action == "readme":
                if not query:
                    return await interaction.followup.send("You must provide a query for the `readme` action.", ephemeral=True)
                
                if not os.path.exists("README.md"):
                    return await interaction.followup.send("`README.md` not found.", ephemeral=True)
                
                try:
                    async with aiofiles.open("README.md", "r", encoding="utf-8") as f:
                        lines = await f.readlines()
                    
                    search_results = []
                    query_words = set(query.lower().split())



                    required_matches = 2 if len(query_words) > 1 else 1

                    for i, line in enumerate(lines):
                        line_lower = line.lower()
                        found_words = sum(1 for word in query_words if word in line_lower)
                        
                        if found_words >= required_matches:
                            start = max(0, i - 5)
                            end = min(len(lines), i + 6)
                            search_results.append(f"... (line ~{i+1}) ...\n{''.join(lines[start:end])}")
                    
                    if not search_results:
                        context = "No direct matches found in README.md for the query. The full file is too large to display. Try a different query."
                    else:
                        context = "\n".join(sorted(list(set(search_results))))
                        
                except Exception as e:
                    return await interaction.followup.send(f"Error searching `README.md`: {e}", ephemeral=True)

                final_query = f"Based on the following snippets from the README.md file, please answer this question: {query}"

            else:
                return await interaction.followup.send(f"Unknown action: `{action}`. Use `/ask_zdbf action:help` for a list of commands.", ephemeral=True)


            prompt = f"{strict_prompt}\n\n== CONTEXT ==\n{context}\n\n== QUERY ==\n{final_query}"
            
            try:
                response = await self.model.generate_content_async(prompt)
                response_text = response.text
                
                embed.title = f"ZDBF Assistant | Action: `{action}`"
                embed.description = response_text[:4096]
                
                await interaction.followup.send(embed=embed, ephemeral=True)

            except Exception as e:
                await interaction.followup.send(f"An error occurred with the AI model: {e}", ephemeral=True)

        except discord.errors.NotFound:

            pass
        except Exception as e:

            try:
                await interaction.followup.send(f"An error occurred while processing action '{action}': {e}", ephemeral=True)
            except:

                print(f"Fatal error in ask_zdbf command: {e}")

async def setup(bot):
    await bot.add_cog(GeminiService(bot))
