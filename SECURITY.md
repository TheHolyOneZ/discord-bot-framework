# Security Policy

## 🔒 Reporting a Vulnerability

If you discover a security vulnerability in this project, please help us by reporting it responsibly.

### How to Report

**DO NOT** create a public GitHub issue for security vulnerabilities.

Instead, please report security issues by:

1. **GitHub Security Advisory**: Use the [Security Advisory](https://github.com/TheHolyOneZ/discord-bot-framework/security/advisories) feature (preferred)
2. **Direct Contact**: Contact [@TheHolyOneZ](https://github.com/TheHolyOneZ) directly through GitHub

### What to Include

Please include the following information in your report:

- **Description**: Clear description of the vulnerability
- **Impact**: What could an attacker do with this vulnerability?
- **Reproduction**: Step-by-step instructions to reproduce
- **Affected Versions**: Which versions are affected?
- **Suggested Fix**: If you have ideas for fixing it (optional)
- **Your Contact**: How we can reach you for follow-up

### What to Expect

- **Acknowledgment**: We'll acknowledge your report within 48 hours
- **Updates**: We'll keep you informed about progress
- **Credit**: With your permission, we'll credit you in the fix announcement
- **Timeline**: We aim to address critical issues within 7 days

## 🛡️ Security Best Practices

### For Users

When using this bot framework, follow these security guidelines:

#### 1. **Protect Your Bot Token**

```env
# ✅ CORRECT: Store in .env file (add to .gitignore)
DISCORD_TOKEN=your_token_here

# ❌ NEVER do this:
# - Hardcode tokens in code
# - Commit .env to git
# - Share tokens publicly
# - Post tokens in screenshots
```

#### 2. **Manage Intents Carefully**

```python
# Only enable intents you actually need
intents = discord.Intents.default()
intents.message_content = True  # Only if needed
# Don't use Intents.all() in production unless necessary
```

#### 3. **Validate User Input**

```python
# Always validate and sanitize user input
@commands.command()
async def example(ctx, user_input: str):
    # Validate input
    if len(user_input) > 100:
        await ctx.send("Input too long!")
        return
    
    # Sanitize if needed
    safe_input = user_input.strip()
```

#### 4. **Use Permission Checks**

```python
# Always check permissions for sensitive commands
@commands.command()
@commands.has_permissions(administrator=True)
async def sensitive_command(ctx):
    await ctx.send("Admin only!")
```

#### 5. **Rate Limiting**

```python
# Implement cooldowns to prevent abuse
@commands.command()
@commands.cooldown(1, 5, commands.BucketType.user)
async def limited_command(ctx):
    await ctx.send("Rate limited command!")
```

#### 6. **Keep Dependencies Updated**

```bash
# Regularly update dependencies
pip install --upgrade discord.py
pip install --upgrade python-dotenv
```

#### 7. **Secure Your Server**

- Run the bot with minimal privileges
- Don't run as root/administrator
- Use a dedicated user account
- Keep your system updated

#### 8. **Monitor Logs**

- Regularly check `botlogs/` for suspicious activity
- Set up alerts for critical errors
- Rotate logs to prevent disk space issues

### For Developers

If you're contributing to this project:

#### 1. **Never Commit Secrets**

- Add `.env` to `.gitignore`
- Use environment variables for all secrets
- Review commits before pushing

#### 2. **Validate All Input**

- Never trust user input
- Validate types, lengths, and formats
- Sanitize data before processing

#### 3. **Secure File Operations**

```python
# Validate file paths
import os

def safe_file_read(filename):
    # Prevent directory traversal
    if ".." in filename or "/" in filename:
        raise ValueError("Invalid filename")
    
    safe_path = os.path.join("./extensions", filename)
    # Read file safely
```

#### 4. **Error Handling**

```python
# Don't expose sensitive info in errors
try:
    # risky operation
    pass
except Exception as e:
    logger.error(f"Error: {e}")
    # Don't send full error to user
    await ctx.send("An error occurred")
```

## 🚨 Known Security Considerations

### Bot Token Security

Your Discord bot token is like a password. If compromised:

- Attackers can control your bot
- They can access all servers your bot is in
- They can read messages (if intents enabled)

**If your token is compromised:**

1. Regenerate it immediately in Discord Developer Portal
2. Update your `.env` file
3. Review bot logs for suspicious activity
4. Consider rotating all related credentials

### Intents and Permissions

This framework uses `Intents.all()` by default for simplicity. In production:

- Only enable intents you need
- Request minimal permissions
- Regularly audit what data your bot accesses

### Extension Security

Extensions run with full bot privileges:

- Only load trusted extensions
- Review extension code before using
- Keep extensions updated
- Be cautious with third-party extensions

## 📋 Security Checklist

Before deploying your bot:

- [ ] Bot token stored in `.env` file
- [ ] `.env` added to `.gitignore`
- [ ] Using minimal required intents
- [ ] Permission checks on sensitive commands
- [ ] Rate limiting implemented
- [ ] Input validation in place
- [ ] Error handling doesn't expose secrets
- [ ] Logging configured properly
- [ ] Dependencies are up to date
- [ ] Running with non-root privileges

## 🔄 Security Updates

We take security seriously. When security issues are found:

1. We'll patch them as quickly as possible
2. Release a security advisory
3. Update affected versions
4. Notify users through GitHub

### Supported Versions

We provide security updates for:

- Latest release version
- Previous major version (when applicable)

## 📚 Resources

- [Discord.py Security Best Practices](https://discordpy.readthedocs.io/en/stable/faq.html#security)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security](https://python.readthedocs.io/en/latest/library/security_warnings.html)

## 🙏 Thank You

We appreciate responsible disclosure and the security community's help in keeping this project safe.

---

**Remember**: Security is everyone's responsibility! 🔒