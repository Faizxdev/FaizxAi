import discord
from typing import Dict, Any, Union, Optional
from src.utils.logger import setup_logger

logger = setup_logger("permission_manager")

class PermissionManager:
    @staticmethod
    def create_overwrite(perm_dict: Dict[str, bool]) -> discord.PermissionOverwrite:
        """Create a PermissionOverwrite object from a dictionary of rules."""
        overwrite = discord.PermissionOverwrite()
        for perm_name, allowed in perm_dict.items():
            if hasattr(overwrite, perm_name):
                setattr(overwrite, perm_name, allowed)
            else:
                logger.warning(f"Unknown permission field: {perm_name}")
        return overwrite

    @staticmethod
    def resolve_overwrites(
        guild: discord.Guild, 
        overwrites_config: Dict[str, Dict[str, bool]]
    ) -> Dict[Union[discord.Role, discord.Member], discord.PermissionOverwrite]:
        """
        Map strings in configuration to actual discord.Role/discord.Member objects 
        with corresponding PermissionOverwrite rules.
        """
        resolved: Dict[Union[discord.Role, discord.Member], discord.PermissionOverwrite] = {}
        
        if not overwrites_config:
            return resolved

        for target_name, perms in overwrites_config.items():
            # Handle special @everyone string
            if target_name.lower() == "@everyone":
                resolved[guild.default_role] = PermissionManager.create_overwrite(perms)
                continue
            
            # Look up role
            role = discord.utils.get(guild.roles, name=target_name)
            if role:
                resolved[role] = PermissionManager.create_overwrite(perms)
                continue
            
            # Look up member (could be by name or ID)
            member = discord.utils.get(guild.members, name=target_name)
            if member:
                resolved[member] = PermissionManager.create_overwrite(perms)
                continue
                
            logger.warning(f"Could not resolve permission target: '{target_name}' in guild '{guild.name}'")

        return resolved
