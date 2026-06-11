# Discord Server Builder Bot

An automated, enterprise-grade Discord server infrastructure provisioner and management bot. It reads a YAML configuration file to build or sync roles, categories, channels, permissions, verification, support tickets, and AutoMod rules on a target guild.

## Features

- **Idempotency**: Existing channels, categories, and roles are updated in-place rather than recreated or duplicated.
- **Role Hierarchy**: Configures custom roles, colours, and permission sets.
- **Dynamic Category & Channel builder**: Supports text, voice, forum, stage, and announcement/news channels.
- **Permission Overwrite Engine**: Custom overrides per channel or category resolved from role names.
- **Persistent Verification System**: Auto-posts an interactive verification panel with buttons. Assigns "Verified" roles on click and strips "Unverified" roles.
- **Persistent Ticket System**: Supports multiple ticket desks (e.g. Sales, Tech Support, Billing) with button panels, transcripts, claims, and auto-closing logging.
- **AutoMod Configuration**: Configures spam, invite-spam, and mention-spam filters out of the box.
- **Slash Commands**: Rich slash command utility including moderation and server backups.
- **Backups**: Save the entire server structure to JSON backups (`/backup-create`) and restore them (`/backup-load`).

---

## Architecture

```
src/
├── bot.py                  # Entrypoint, connection & persistent view registration
├── config/
│   ├── server.yml          # Default server layout configuration
│   └── templates/          # Built-in layouts (VPS hosting business, gaming, etc.)
├── core/
│   ├── guild_builder.py    # Orchestration logic
│   ├── role_manager.py     # Idempotent role synchronization
│   ├── channel_manager.py  # Category and channel manager
│   ├── permission_manager.py# Overwrites mapping helper
│   ├── onboarding_manager.py# Persistent verification and ticketing views
│   ├── moderation_manager.py# AutoMod rules manager
│   └── backup_manager.py   # State exporting and importing
├── commands/
│   ├── backup.py           # Cog for backup commands
│   └── moderation.py       # Cog for moderation slash commands
└── utils/
    ├── helpers.py          # Configuration and parsing utils
    └── logger.py           # Structured logging
```

---

## Installation & Setup

1. **Python version**: Requires Python 3.12+
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   GUILD_ID=your_target_guild_id_here
   LOG_LEVEL=INFO
   ```
4. **Developer Portal Setup**:
   Ensure you enable all **Privileged Gateway Intents** (Presence Intent, Server Members Intent, Message Content Intent) in the Discord Developer Portal under Bot settings.
   Ensure the bot has the `Administrator` permission when inviting it to the target server.

---

## Run Bot

```bash
python src/bot.py
```

---

## Configurations & Templates

Configurations are specified in YAML format. Check out:
- [Default Config](file:///c:/Users/Firda/Documents/Serverbuilder/src/config/server.yml)
- [VPS Hosting Template](file:///c:/Users/Firda/Documents/Serverbuilder/src/config/templates/vps_hosting.yml)
- [Gaming Template](file:///c:/Users/Firda/Documents/Serverbuilder/src/config/templates/gaming.yml)

---

## Slash Commands

Moderators can use these slash commands in the server:

- `/ban [member] [reason]` - Ban a user
- `/kick [member] [reason]` - Kick a user
- `/timeout [member] [minutes] [reason]` - Timeout a user
- `/warn [member] [reason]` - Send a warn DM and logs it
- `/clear [amount]` - Purge chat messages
- `/lock` - Disables message sending for everyone in the current channel
- `/unlock` - Resets permissions to default in the current channel
- `/backup-create [filename]` - Export the entire layout of roles, categories, and channels to a JSON file in `data/`
- `/backup-load [filename]` - Import and apply a JSON layout to the server
