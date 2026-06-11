import discord
from typing import Dict, Any
from src.utils.logger import setup_logger
from src.core.role_manager import RoleManager
from src.core.channel_manager import ChannelManager
from src.core.onboarding_manager import OnboardingManager
from src.core.moderation_manager import ModerationManager
from src.core.store_manager import StoreManager

logger = setup_logger("guild_builder")

class GuildBuilder:
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.role_manager = RoleManager(guild)
        self.channel_manager = ChannelManager(guild)
        self.onboarding_manager = OnboardingManager(guild)
        self.moderation_manager = ModerationManager(guild)
        self.store_manager = StoreManager(guild)

    async def build(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the complete server sync operation.
        Returns a final report dictionary summarizing the changes.
        """
        logger.info(f"Starting server synchronization for guild: {self.guild.name} ({self.guild.id})")
        report = {
            "guild_name": self.guild.name,
            "status": "In Progress",
            "roles_synced": 0,
            "categories_synced": 0,
            "channels_synced": 0,
            "verification_status": "Not Configured",
            "tickets_status": "Not Configured",
            "moderation_status": "Not Configured",
            "products_synced": 0,
            "errors": []
        }

        # Step 1: Sync Roles
        roles_config = config.get("roles", [])
        if roles_config:
            try:
                logger.info("Syncing roles...")
                synced_roles = await self.role_manager.sync_roles(roles_config)
                report["roles_synced"] = len(synced_roles)
                logger.info(f"Successfully synced {len(synced_roles)} roles.")
            except Exception as e:
                err_msg = f"Failed syncing roles: {e}"
                logger.error(err_msg)
                report["errors"].append(err_msg)

        # Step 2: Sync Channels and Categories
        categories_config = config.get("categories", [])
        if categories_config:
            try:
                logger.info("Syncing channels and categories...")
                await self.channel_manager.sync_channels(categories_config)
                # Count current state
                report["categories_synced"] = len(self.guild.categories)
                report["channels_synced"] = len(self.guild.channels) - len(self.guild.categories)
                logger.info("Successfully synced channels.")
            except Exception as e:
                err_msg = f"Failed syncing channels: {e}"
                logger.error(err_msg)
                report["errors"].append(err_msg)

        # Step 2.5: Sync Store Products (Free Fire/Sell Server specific)
        products_config = config.get("products", [])
        if products_config:
            try:
                logger.info("Syncing store products and creating channels...")
                await self.store_manager.sync_store(config)
                report["products_synced"] = len(products_config)
                logger.info("Successfully synced store products.")
            except Exception as e:
                err_msg = f"Failed syncing store products: {e}"
                logger.error(err_msg)
                report["errors"].append(err_msg)

        # Step 3: Setup Verification System
        verification_config = config.get("verification", {})
        if verification_config and verification_config.get("enabled", False):
            try:
                logger.info("Setting up verification system...")
                await self.onboarding_manager.setup_verification(verification_config)
                report["verification_status"] = "Success"
            except Exception as e:
                err_msg = f"Failed verification setup: {e}"
                logger.error(err_msg)
                report["verification_status"] = f"Failed: {e}"
                report["errors"].append(err_msg)

        # Step 4: Setup Ticket System
        tickets_config = config.get("tickets", {})
        if tickets_config and tickets_config.get("enabled", False):
            try:
                logger.info("Setting up ticket system...")
                await self.onboarding_manager.setup_ticket_system(tickets_config)
                report["tickets_status"] = "Success"
            except Exception as e:
                err_msg = f"Failed ticket system setup: {e}"
                logger.error(err_msg)
                report["tickets_status"] = f"Failed: {e}"
                report["errors"].append(err_msg)

        # Step 5: Setup Moderation & AutoMod Rules
        moderation_config = config.get("moderation", {})
        if moderation_config:
            try:
                logger.info("Configuring moderation and AutoMod rules...")
                await self.moderation_manager.sync_moderation(moderation_config)
                report["moderation_status"] = "Success"
            except Exception as e:
                err_msg = f"Failed moderation setup: {e}"
                logger.error(err_msg)
                report["moderation_status"] = f"Failed: {e}"
                report["errors"].append(err_msg)

        if not report["errors"]:
            report["status"] = "Completed Successfully"
        else:
            report["status"] = f"Completed with {len(report['errors'])} errors"

        logger.info(f"Server synchronization report: {report}")
        return report

