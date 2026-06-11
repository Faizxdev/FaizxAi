import discord
from typing import List, Dict, Any
from src.utils.logger import setup_logger
from src.utils.helpers import parse_color, parse_permissions

logger = setup_logger("role_manager")

class RoleManager:
    def __init__(self, guild: discord.Guild):
        self.guild = guild

    async def sync_roles(self, roles_config: List[Dict[str, Any]]) -> Dict[str, discord.Role]:
        """
        Synchronize roles from configuration.
        Creates roles if missing, updates attributes if they differ, and orders them.
        Returns a mapping of role names to discord.Role objects.
        """
        existing_roles = {role.name: role for role in self.guild.roles}
        synced_roles: Dict[str, discord.Role] = {}

        bot_member = self.guild.me
        bot_highest_role = bot_member.top_role

        # We will iterate through roles config
        for role_data in roles_config:
            name = role_data.get("name")
            if not name:
                continue

            color = parse_color(role_data.get("color"))
            hoist = bool(role_data.get("hoist", False))
            mentionable = bool(role_data.get("mentionable", False))
            perms_list = role_data.get("permissions", [])
            permissions = parse_permissions(perms_list)

            # Skip @everyone modifications if they're too restricted, or handle it carefully
            if name == "@everyone":
                everyone_role = self.guild.default_role
                synced_roles[name] = everyone_role
                # Can only edit permissions of @everyone
                try:
                    if everyone_role.permissions != permissions:
                        await everyone_role.edit(permissions=permissions, reason="Sync everyone role permissions")
                        logger.info(f"Updated @everyone permissions.")
                except Exception as e:
                    logger.warning(f"Could not update @everyone permissions: {e}")
                continue

            role = existing_roles.get(name)
            
            if role:
                # Update role if attributes differ
                # Check if bot can manage this role
                if role >= bot_highest_role and role != bot_highest_role:
                    logger.warning(f"Cannot update role '{name}' because it is equal or higher than the bot's highest role.")
                    synced_roles[name] = role
                    continue

                needs_update = False
                update_args = {}

                if role.color != color:
                    update_args["color"] = color
                    needs_update = True
                if role.hoist != hoist:
                    update_args["hoist"] = hoist
                    needs_update = True
                if role.mentionable != mentionable:
                    update_args["mentionable"] = mentionable
                    needs_update = True
                if role.permissions != permissions:
                    update_args["permissions"] = permissions
                    needs_update = True

                if needs_update:
                    try:
                        await role.edit(reason="Sync roles configuration", **update_args)
                        logger.info(f"Updated role: {name}")
                    except Exception as e:
                        logger.error(f"Failed to update role '{name}': {e}")
                else:
                    logger.debug(f"Role '{name}' is already up to date.")
                
                synced_roles[name] = role
            else:
                # Create role
                try:
                    role = await self.guild.create_role(
                        name=name,
                        color=color,
                        hoist=hoist,
                        mentionable=mentionable,
                        permissions=permissions,
                        reason="Sync roles configuration"
                    )
                    logger.info(f"Created role: {name}")
                    synced_roles[name] = role
                except Exception as e:
                    logger.error(f"Failed to create role '{name}': {e}")

        # Set role positions/ordering
        # In discord.py, we can edit role positions using guild.edit_role_positions.
        # We want roles to be ordered according to the YAML config (usually top down is highest to lowest or lowest to highest).
        # Let's assume YAML order lists roles from highest to lowest hierarchy.
        # So first role in list should have highest position.
        await self._reorder_roles(roles_config, synced_roles, bot_highest_role)

        return synced_roles

    async def _reorder_roles(
        self, 
        roles_config: List[Dict[str, Any]], 
        synced_roles: Dict[str, discord.Role],
        bot_highest_role: discord.Role
    ):
        """Reorder roles according to their configuration order (top listed is highest)."""
        # We need to construct a mapping of {role: position} or list of role positions.
        # Positions must be integers. The default @everyone is always at position 0.
        # Roles we can manage must be below bot_highest_role.
        role_order = [role_data.get("name") for role_data in roles_config if role_data.get("name") != "@everyone"]
        
        # We reverse because position 1 is lowest custom role, and higher is higher.
        # If config is [Owner, Admin, Moderator, Member], we want Owner to have highest position, Member lowest.
        role_order.reverse() 

        positions = {}
        current_pos = 1  # start above @everyone

        for name in role_order:
            role = synced_roles.get(name)
            if role and role < bot_highest_role:
                positions[role] = current_pos
                current_pos += 1

        if positions:
            try:
                # discord.py edit_role_positions accepts a dict of {role: position}
                await self.guild.edit_role_positions(positions, reason="Sync role hierarchy order")
                logger.info("Reordered roles successfully.")
            except Exception as e:
                logger.warning(f"Could not reorder roles: {e}. Check if bot has 'Manage Roles' permission or if role order requires higher permissions.")
