# Changelog

All notable changes to this project will be documented in this file.

## [1.6.0.1] - 2026-02-10

### ✨ Added

- **New Cog: `GeminiService` - AI Assistant**
  - Integrated a powerful AI assistant powered by the Google Gemini Pro model to provide deep insights into the bot's operation.

- **New Slash Command: `/ask_zdbf`**
  - A comprehensive command with multiple actions to query the AI about different aspects of the framework.
  - Features an interactive, paginated help menu (`/ask_zdbf action:help`) with buttons for easy navigation.

- **Context-Aware AI Actions:**
  - **`framework`**: Ask general questions about the ZDBF architecture, core cogs, and functionality.
  - **`plugins`**: Get an AI-powered analysis of all installed plugins by pulling live data from the `PluginRegistry`.
  - **`diagnose`**: Request an AI summary of the bot's current health and performance based on the latest `FrameworkDiagnostics` report.
  - **`database`**: Ask natural language questions about the bot's database schema.
  - **`file`**: Ask specific questions about the content of any file within the bot's directory. Includes security checks to prevent path traversal.
  - **`extension`**: A focused version of the `file` action, specifically for inspecting files in the `/extensions` folder.
  - **`slash`**: Inquire about the current status of the `SlashCommandLimiter`, including converted and blocked commands.
  - **`hooks`**: Get details about the internal `EventHooks` system, including registered hooks and recent activity.
  - **`automations`**: Ask about user-created automations managed by `EventHooksCreater`.
  - **`readme`**: Perform an intelligent search within the `README.md` file to find answers to specific questions.
  - **`permission`**: (Bot Owner Only) A placeholder for future permission management for the `/ask_zdbf` command.

- **Robust Interaction Handling:**
  - Automatically defers responses to prevent command timeouts during AI generation.
  - Includes comprehensive error handling for all actions and AI model interactions.
  - Secure file path handling to ensure safety.
