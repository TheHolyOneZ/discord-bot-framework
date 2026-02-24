# What's New in Version 1.7.2.0

This update introduces a comprehensive **Bot Status Configuration** system, fully integrated into the Live Monitor web dashboard. This feature allows for dynamic, multi-status rotation with customizable variables, providing a more engaging and informative presence for your bot on Discord.

---

## Bot Status Configuration — Now in the Dashboard

The new **Bot Status Configuration** card, located in the **System tab** of the Live Monitor dashboard, provides complete control over your bot's presence.

### Key Features

- **Multi-Status Rotator:** Create a list of different statuses for your bot to cycle through. Each status can have its own text, type (playing, watching, listening), and presence (online, idle, dnd).
- **Customizable Interval:** Set the rotation interval in seconds to control how frequently the bot's status updates.
- **Dynamic Variables:** Use variables like `{guilds}`, `{users}`, and `{commands}` in your status text, which will be automatically replaced with real-time data.
- **Live Editing:** Add, edit, and delete statuses directly from the dashboard. Changes are saved and applied instantly without needing to restart the bot.
- **Log Toggling:** A new toggle allows you to enable or disable logging for status updates, helping you monitor the rotator's activity in your bot's console.
- **Intuitive UI:** The interface provides clear input fields for status type, text, and presence, making it easy to configure complex rotations.

This new system replaces the previous static status configuration, offering a much more flexible and powerful way to manage your bot's presence.

