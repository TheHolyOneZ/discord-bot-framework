# IP Tracking & Privacy Policy

This document explains how user IP addresses are handled within the Zoryx Live Monitor Dashboard and how you can control your privacy.

## How IP Tracking Works

By default, the dashboard is configured to log the IP address of any user who attempts to log in or performs a sensitive action that is recorded in the audit log (`owner_audit.php`).

**Why is this enabled by default?**
IP logging is a standard security measure. It allows the bot owner to:
-   Identify and block malicious login attempts.
-   Trace unauthorized actions back to their source.
-   Ensure the security and integrity of the bot and its data.

## Your Privacy, Your Control

We believe in giving you control over your personal data. You can disable IP logging at any time.

**How to Disable IP Logging:**
1.  Log in to your Live Monitor Dashboard.
2.  In the main header, click on the **"Privacy Settings"** button.
3.  In the modal window that appears, toggle off the **"Allow IP Address Logging"** setting.
4.  Click **"Save Changes"**.

## How Disabling IP Logging Protects You

When you disable IP address logging, the system immediately stops recording your IP for any future actions.

**Technical Explanation:**
1.  **Saving Your Preference:** When you toggle the setting off, your choice is saved to your user profile in the dashboard's database and, crucially, updated in your current browser session.
2.  **The Audit Log Check:** The core function responsible for logging all actions (`lm_log_audit`) contains a specific privacy check.
3.  **Enforcing Your Choice:** Before writing any new entry to the audit log, this function checks your session for your privacy preference.
    -   If IP logging is **enabled**, it retrieves your IP address from the server and records it.
    -   If IP logging is **disabled**, the function intentionally writes a `null` value into the `ip_address` column of the log.

This ensures that once you opt out, your IP address is never stored in the audit log for any subsequent actions, including logins, failed logins, or any other audited event.
