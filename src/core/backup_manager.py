import os
import json
import discord
from typing import Dict, Any, List
from src.utils.logger import setup_logger

logger = setup_logger("backup_manager")

class BackupManager:
    @staticmethod
    def get_backup_dir() -> str:
        backup_dir = "data"
        os.makedirs(backup_dir, exist_ok=True)
        return backup_dir

    @classmethod
    def create_backup(cls, guild: discord.Guild) -> Dict[str, Any]:
        """Export roles, channels, and permissions to a dictionary."""
        backup_data = {
            "guild_name": guild.name,
            "guild_id": guild.id,
            "backup_time": discord.utils.utcnow().isoformat(),
            "roles": [],
            "categories": []
        }

        # 1. Backup roles (skip bot roles or integration roles if possible, but list all custom roles)
        # Sort roles by position descending
        sorted_roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)
        for role in sorted_roles:
            if role.is_default():  # @everyone
                name = "@everyone"
            elif role.is_integration() or role.is_bot_managed():
                # Skip system/integration roles
                continue
            else:
                name = role.name

            # Map permissions
            perms_list = [perm_name for perm_name, allowed in role.permissions if allowed]

            role_info = {
                "name": name,
                "color": f"#{role.color.value:06x}" if role.color.value else "#000000",
                "hoist": role.hoist,
                "mentionable": role.mentionable,
                "permissions": perms_list
            }
            backup_data["roles"].append(role_info)

        # 2. Backup categories and channels
        # Sort categories by position
        sorted_categories = sorted(guild.categories, key=lambda c: c.position)
        for cat in sorted_categories:
            # Map category overwrites
            cat_overwrites = {}
            for target, ow in cat.overwrites.items():
                target_name = target.name if isinstance(target, (discord.Role, discord.Member)) else str(target)
                # Map individual permissions in overwrite
                ow_dict = {}
                for perm, val in ow:
                    if val is not None:
                        ow_dict[perm] = val
                if ow_dict:
                    cat_overwrites[target_name] = ow_dict

            cat_info = {
                "category": cat.name,
                "permissions": cat_overwrites,
                "channels": []
            }

            # Map channels in category
            sorted_channels = sorted(cat.channels, key=lambda c: c.position)
            for chan in sorted_channels:
                chan_type = "text"
                if isinstance(chan, discord.VoiceChannel):
                    chan_type = "voice"
                elif isinstance(chan, discord.StageChannel):
                    chan_type = "stage"
                elif isinstance(chan, discord.ForumChannel):
                    chan_type = "forum"
                elif isinstance(chan, discord.TextChannel) and chan.is_news():
                    chan_type = "announcement"

                chan_overwrites = {}
                for target, ow in chan.overwrites.items():
                    target_name = target.name if isinstance(target, (discord.Role, discord.Member)) else str(target)
                    ow_dict = {}
                    for perm, val in ow:
                        if val is not None:
                            ow_dict[perm] = val
                    if ow_dict:
                        chan_overwrites[target_name] = ow_dict

                chan_info = {
                    "name": chan.name,
                    "type": chan_type,
                    "topic": getattr(chan, "topic", "") or "",
                    "slowmode": getattr(chan, "slowmode_delay", 0),
                    "nsfw": getattr(chan, "nsfw", False),
                    "permissions": chan_overwrites
                }
                cat_info["channels"].append(chan_info)

            backup_data["categories"].append(cat_info)

        return backup_data

    @classmethod
    def save_backup(cls, guild: discord.Guild, filename: str) -> str:
        """Create and write guild backup to JSON file."""
        if not filename.endswith(".json"):
            filename += ".json"
            
        backup_data = cls.create_backup(guild)
        file_path = os.path.join(cls.get_backup_dir(), filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, indent=4, ensure_ascii=False)
            
        logger.info(f"Backup created at: {file_path}")
        return file_path

    @classmethod
    def load_backup(cls, filename: str) -> Dict[str, Any]:
        """Load backup data from a file."""
        if not filename.endswith(".json"):
            filename += ".json"
            
        file_path = os.path.join(cls.get_backup_dir(), filename)
        if not os.path.exists(file_path):
            logger.error(f"Backup file not found: {file_path}")
            raise FileNotFoundError(f"Backup file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
