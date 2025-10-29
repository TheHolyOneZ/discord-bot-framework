# Contributing to Discord Bot Framework

Thank you for considering contributing to this project! We welcome contributions from everyone.

## 📋 Table of Contents

- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Coding Standards](#coding-standards)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [License Requirements](#license-requirements)

## 🚀 Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/discord-bot-framework.git`
3. Create a new branch: `git checkout -b feature/your-feature-name`
4. Make your changes
5. Test thoroughly
6. Submit a pull request

## 🤝 How to Contribute

### Reporting Bugs

If you find a bug, please create an issue using the Bug Report template and include:

- Clear description of the bug
- Steps to reproduce
- Expected vs actual behavior
- Your environment (Python version, discord.py version, OS)
- Relevant logs from `botlogs/`

### Suggesting Features

We love new ideas! Create an issue using the Feature Request template with:

- Clear description of the feature
- Why it would be useful
- Example use cases
- Optional: Implementation suggestions

### Improving Documentation

Documentation improvements are always welcome:

- Fix typos or unclear instructions
- Add examples
- Improve existing explanations
- Translate documentation

### Contributing Code

1. Pick an issue or create one for discussion
2. Comment on the issue that you're working on it
3. Follow the coding standards below
4. Write clear, commented code
5. Test your changes thoroughly
6. Submit a pull request

## 💻 Coding Standards

### Python Style

- Follow PEP 8 guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and concise
- Use type hints where appropriate

### Example:

```python
async def example_command(ctx, user: discord.Member, reason: str = "No reason provided"):
    """
    Example command that demonstrates proper formatting.
    
    Args:
        ctx: The command context
        user: The member to target
        reason: Optional reason string
    """
    await ctx.send(f"Action taken on {user.mention}: {reason}")
```

### Code Organization

- Place extension files in the `extensions/` folder
- Use cogs for organizing related commands
- Keep `main.py` focused on core bot functionality
- Create helper functions for repeated code

### Comments

- Comment complex logic
- Use inline comments sparingly
- Prefer clear code over excessive comments
- Document why, not what

## 📝 Commit Guidelines

### Commit Message Format

```
type(scope): brief description

Longer description if needed

Fixes #issue_number
```

### Types:

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance tasks

### Examples:

```
feat(help): add pagination to help menu

fix(logging): resolve file handler permission error

docs(readme): update installation instructions
```

## 🔄 Pull Request Process

1. **Update Documentation**: Ensure README and relevant docs are updated
2. **Test Your Changes**: Run the bot and test all affected features
3. **Clean Commit History**: Squash commits if needed
4. **Fill Out PR Template**: Provide clear description of changes
5. **Link Issues**: Reference any related issues
6. **Wait for Review**: Maintainers will review and provide feedback
7. **Address Feedback**: Make requested changes promptly
8. **Approval**: Once approved, your PR will be merged

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] No new warnings generated
- [ ] Tested in a Discord server
- [ ] Related issues linked

## ⚖️ License Requirements

**IMPORTANT**: All contributions must respect the MIT License with Additional Terms:

### You MUST:

- Keep the original license notice in `main.py`
- Maintain the `CreditsButton` class functionality
- Preserve author attribution to "TheHolyOneZ"
- Not remove or obscure the credits button

### You CAN:

- Add your own features and extensions
- Modify existing code (except credits requirements)
- Add yourself to a contributors list
- Create derivative works (following license terms)

### Contributor Attribution

By contributing, you agree that:

- Your contributions will be under the same license
- You have the right to submit the work
- You understand the license requirements

We may add a `CONTRIBUTORS.md` file to acknowledge contributions.

## ❓ Questions?

If you have questions about contributing:

1. Check existing issues and discussions
2. Create a new issue with the "question" label
3. Reach out to [@TheHolyOneZ](https://github.com/TheHolyOneZ)

## 🙏 Thank You!

Every contribution, no matter how small, is valuable and appreciated!

---

Made with 💜 by the Discord Bot Framework community