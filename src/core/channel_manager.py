import discord
from typing import List, Dict, Any, Optional
from src.utils.logger import setup_logger
from src.core.permission_manager import PermissionManager

logger = setup_logger("channel_manager")

class ChannelManager:
    def __init__(self, guild: discord.Guild):
        self.guild = guild

    async def sync_channels(self, categories_config: List[Dict[str, Any]]) -> None:
        """
        Synchronize categories and channels from configuration.
        Ensures idempotent creations and updates.
        """
        for cat_index, cat_data in enumerate(categories_config):
            cat_name = cat_data.get("category")
            if not cat_name:
                continue

            # Parse category permissions
            cat_perms_config = cat_data.get("permissions", {})
            cat_overwrites = PermissionManager.resolve_overwrites(self.guild, cat_perms_config)

            # Get or create category
            category = await self._get_or_create_category(cat_name, cat_overwrites, cat_index)

            # Process channels under this category
            channels_list = cat_data.get("channels", [])
            for chan_index, chan_data in enumerate(channels_list):
                await self._sync_channel(category, chan_data, chan_index)

    async def _get_or_create_category(
        self, 
        name: str, 
        overwrites: dict, 
        position: int
    ) -> discord.CategoryChannel:
        """Get existing category by name or create a new one."""
        existing_categories = {cat.name.lower(): cat for cat in self.guild.categories}
        category = existing_categories.get(name.lower())

        if category:
            # Update position and permission overwrites if changed
            try:
                # Update overwrites
                # First clear existing overrides if we want strict sync, or merge. Let's update specified ones.
                needs_update = False
                for target, overwrite in overwrites.items():
                    existing_ow = category.overwrites_for(target)
                    if existing_ow != overwrite:
                        await category.set_permissions(target, overwrite=overwrite, reason="Sync category permissions")
                        needs_update = True
                
                if category.position != position:
                    await category.edit(position=position, reason="Sync category positions")
                    needs_update = True

                if needs_update:
                    logger.info(f"Updated category: {name}")
                else:
                    logger.debug(f"Category '{name}' is up to date.")
            except Exception as e:
                logger.error(f"Failed to update category '{name}': {e}")
        else:
            try:
                category = await self.guild.create_category(
                    name=name,
                    overwrites=overwrites,
                    position=position,
                    reason="Sync category configuration"
                )
                logger.info(f"Created category: {name}")
            except Exception as e:
                logger.error(f"Failed to create category '{name}': {e}")
                raise e
        return category

    async def _sync_channel(self, category: discord.CategoryChannel, chan_data: Dict[str, Any], position: int) -> None:
        """Sync a single channel inside a category."""
        name = chan_data.get("name")
        if not name:
            return

        chan_type_str = chan_data.get("type", "text").lower()
        topic = chan_data.get("topic", "")
        slowmode = int(chan_data.get("slowmode", 0))
        nsfw = bool(chan_data.get("nsfw", False))
        
        # Merge category level permissions and channel specific permissions
        chan_perms_config = chan_data.get("permissions", {})
        chan_overwrites = PermissionManager.resolve_overwrites(self.guild, chan_perms_config)
        
        # Start with category overwrites, let channel overrides take precedence
        merged_overwrites = category.overwrites.copy()
        merged_overwrites.update(chan_overwrites)

        # Look for existing channel in this category
        existing_channel = None
        for ch in category.channels:
            if ch.name.lower() == name.lower():
                existing_channel = ch
                break

        if existing_channel:
            # Update existing channel settings
            await self._update_channel(existing_channel, chan_type_str, topic, slowmode, nsfw, merged_overwrites, position)
        else:
            # Create channel
            await self._create_channel(category, name, chan_type_str, topic, slowmode, nsfw, merged_overwrites, position)

    async def _create_channel(
        self, 
        category: discord.CategoryChannel, 
        name: str, 
        chan_type: str, 
        topic: str, 
        slowmode: int, 
        nsfw: bool, 
        overwrites: dict,
        position: int
    ) -> None:
        """Create channel under a category with the correct type and settings."""
        try:
            if chan_type == "text":
                await self.guild.create_text_channel(
                    name=name,
                    category=category,
                    topic=topic,
                    slowmode_delay=slowmode,
                    nsfw=nsfw,
                    overwrites=overwrites,
                    position=position,
                    reason="Sync channels"
                )
            elif chan_type == "voice":
                await self.guild.create_voice_channel(
                    name=name,
                    category=category,
                    overwrites=overwrites,
                    position=position,
                    reason="Sync channels"
                )
            elif chan_type == "announcement" or chan_type == "news":
                await self.guild.create_text_channel(
                    name=name,
                    category=category,
                    type=discord.ChannelType.news,
                    topic=topic,
                    nsfw=nsfw,
                    overwrites=overwrites,
                    position=position,
                    reason="Sync channels"
                )
            elif chan_type == "stage":
                await self.guild.create_stage_channel(
                    name=name,
                    category=category,
                    overwrites=overwrites,
                    position=position,
                    reason="Sync channels"
                )
            elif chan_type == "forum":
                await self.guild.create_forum_channel(
                    name=name,
                    category=category,
                    topic=topic,
                    nsfw=nsfw,
                    overwrites=overwrites,
                    position=position,
                    reason="Sync channels"
                )
            else:
                # Default to text channel if type is unknown
                logger.warning(f"Unknown channel type '{chan_type}' for channel '{name}'. Defaulting to text channel.")
                await self.guild.create_text_channel(
                    name=name,
                    category=category,
                    topic=topic,
                    slowmode_delay=slowmode,
                    nsfw=nsfw,
                    overwrites=overwrites,
                    position=position,
                    reason="Sync channels"
                )
            logger.info(f"Created channel: {category.name} -> #{name} ({chan_type})")
        except Exception as e:
            logger.error(f"Failed to create channel '{name}' under category '{category.name}': {e}")

    async def _update_channel(
        self, 
        channel: discord.abc.GuildChannel, 
        chan_type_str: str,
        topic: str, 
        slowmode: int, 
        nsfw: bool, 
        overwrites: dict,
        position: int
    ) -> None:
        """Update existing channel parameters if they differ."""
        try:
            needs_update = False
            update_args = {}

            # Verify positions
            if channel.position != position:
                update_args["position"] = position
                needs_update = True

            # Text, News/Announcement, Forum specific properties
            if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                if channel.topic != topic:
                    update_args["topic"] = topic
                    needs_update = True
                if channel.nsfw != nsfw:
                    update_args["nsfw"] = nsfw
                    needs_update = True

            if isinstance(channel, discord.TextChannel):
                if channel.slowmode_delay != slowmode:
                    update_args["slowmode_delay"] = slowmode
                    needs_update = True

            # Sync overwrites
            # We will edit the permissions if they are different
            ow_updated = False
            # Clear existing overwrites not in our list if doing strict, but simple override update is safer
            for target, overwrite in overwrites.items():
                existing_ow = channel.overwrites_for(target)
                if existing_ow != overwrite:
                    await channel.set_permissions(target, overwrite=overwrite, reason="Sync channel permissions")
                    ow_updated = True

            if needs_update:
                await channel.edit(reason="Sync channel configuration", **update_args)
                logger.info(f"Updated channel settings: #{channel.name}")
            elif ow_updated:
                logger.info(f"Updated channel permissions: #{channel.name}")
            else:
                logger.debug(f"Channel #{channel.name} is up to date.")
        except Exception as e:
            logger.error(f"Failed to update channel #{channel.name}: {e}")
