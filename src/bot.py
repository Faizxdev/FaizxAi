import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Ensure the root folder is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.logger import setup_logger
from src.utils.helpers import load_yaml_config

# Load environment configuration
load_dotenv()

logger = setup_logger("bot")

class ServerBuilderBot(commands.Bot):
    def __init__(self, config_data: dict):
        intents = discord.Intents.default()
        
        # Conditionally enable privileged intents to prevent connection errors
        use_privileged = os.getenv("PRIVILEGED_INTENTS", "false").lower() == "true"
        if use_privileged:
            intents.message_content = True
            intents.members = True
            logger.info("Privileged gateway intents enabled in configuration.")
        else:
            logger.info("Privileged gateway intents disabled by default. Enable them in .env if needed.")
            
        intents.guilds = True
        
        super().__init__(command_prefix="!", intents=intents)
        self.config_data = config_data
        self.guild_synced = False

    async def setup_hook(self):
        # Load Cogs/extensions
        logger.info("Loading extensions...")
        await self.load_extension("src.commands.moderation")
        await self.load_extension("src.commands.backup")
        await self.load_extension("src.commands.ai_builder")
        await self.load_extension("src.commands.agent_command")
        await self.load_extension("src.commands.store_commands")
        await self.load_extension("src.commands.review_commands")
        await self.load_extension("src.commands.seller_commands")
        await self.load_extension("src.commands.verification_commands")
        logger.info("Extensions loaded.")

        # Register persistent UI views so button handlers survive restarts
        self._register_persistent_views()

    def _register_persistent_views(self):
        # 1. Verification System
        from src.core.onboarding_manager import VerificationView
        ver_cfg = self.config_data.get("verification", {}) if self.config_data else {}
        verified_role = ver_cfg.get("verified_role", "Verified")
        unverified_role = ver_cfg.get("unverified_role", "Unverified")
        self.add_view(VerificationView(verified_role, unverified_role))
        logger.info("Registered persistent VerificationView.")

        # 2. Ticket System Panel
        t_cfg = self.config_data.get("tickets", {})
        if t_cfg and t_cfg.get("enabled", False):
            from src.core.onboarding_manager import TicketPanelView
            staff_role = t_cfg.get("staff_role", "Support Team")
            log_chan = t_cfg.get("log_channel", "ticket-logs")
            category_name = t_cfg.get("category", "Support")
            ticket_types = t_cfg.get("types", [])
            self.add_view(TicketPanelView(staff_role, log_chan, category_name, ticket_types))
            logger.info("Registered persistent TicketPanelView.")

        # 3. Ticket control buttons inside active tickets
        if t_cfg:
            from src.core.onboarding_manager import TicketControlView
            staff_role = t_cfg.get("staff_role", "Support Team")
            log_chan = t_cfg.get("log_channel", "ticket-logs")
            self.add_view(TicketControlView(staff_role, log_chan))
            logger.info("Registered persistent TicketControlView.")

        # 4. Store Products Buy Buttons & Select Menu
        from src.core.store_manager import StoreSelectView
        ticket_cfg = self.config_data.get("tickets", {})
        staff_role = ticket_cfg.get("staff_role", "Staff")
        log_chan = ticket_cfg.get("log_channel", "┃📊・staff-logs")
        ticket_cat = ticket_cfg.get("category", "━━━━━━━━━━━━\n🎟️ TICKETS\n━━━━━━━━━━━━")

        # Register persistent selection view
        self.add_view(StoreSelectView(
            products=[],
            staff_role_name=staff_role,
            log_channel_name=log_chan,
            ticket_category_name=ticket_cat
        ))
        logger.info("Registered persistent StoreSelectView.")

        # 5. Seller Management Panel Dashboard
        from src.core.seller_manager import SellerControlView
        self.add_view(SellerControlView())
        logger.info("Registered persistent SellerControlView.")


    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            return
        if interaction.data and "custom_id" in interaction.data:
            custom_id = interaction.data["custom_id"]
            if isinstance(custom_id, str):
                for action in ["ban", "kick", "dismiss"]:
                    if custom_id.startswith(f"sec_{action}_"):
                        target_user_id = int(custom_id.split("_")[-1])
                        from src.core.security_manager import handle_security_action
                        await handle_security_action(interaction, action, target_user_id)
                        return

            if isinstance(custom_id, str) and custom_id.startswith("buy_prod_"):
                msg = interaction.message
                product_name = "Premium Product"
                price = "See Details"
                if msg and msg.embeds:
                    embed = msg.embeds[0]
                    if embed.title:
                        product_name = embed.title.replace("⚡", "").strip().title()
                    for field in embed.fields:
                        if "PRICING" in field.name.upper() or "PRICE" in field.name.upper():
                            price = field.value
                            break

                from src.core.store_manager import StoreProductBuyView
                ticket_cfg = self.config_data.get("tickets", {}) if self.config_data else {}
                staff_role = ticket_cfg.get("staff_role", "Staff")
                log_chan = ticket_cfg.get("log_channel", "┃📊・staff-logs")
                ticket_cat = ticket_cfg.get("category", "━━━━━━━━━━━━\n🎟️ TICKETS\n━━━━━━━━━━━━")

                buy_view = StoreProductBuyView(
                    product_name=product_name,
                    price=price,
                    staff_role_name=staff_role,
                    log_channel_name=log_chan,
                    ticket_category_name=ticket_cat
                )
                await buy_view.buy_callback(interaction)
                return


    async def on_ready(self):
        logger.info(f"Successfully logged in as {self.user.name} (ID: {self.user.id})")

        guild_id_str = os.getenv("GUILD_ID")
        if not guild_id_str:
            logger.error("GUILD_ID is not set in the environment variables.")
            return

        try:
            guild_id = int(guild_id_str)
        except ValueError:
            logger.error("GUILD_ID is not a valid integer.")
            return

        guild = self.get_guild(guild_id)
        if not guild:
            logger.error(f"Could not find target guild with ID: {guild_id_str}. Make sure the bot is invited to the guild.")
            return

        logger.info(f"Target guild detected: {guild.name} ({guild.id})")

        # Sync slash command tree to target guild
        try:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Synced application slash commands to guild: {guild.name}")
        except Exception as e:
            logger.error(f"Failed to sync application commands: {e}")

        # Auto-apply channel lockdown on every startup
        # Ensures all categories stay hidden from @everyone and only verify channel is visible
        try:
            from src.core.onboarding_manager import apply_channel_lockdown
            lockdown_summary = await apply_channel_lockdown(guild, self.config_data)
            logger.info(f"Startup lockdown applied: {lockdown_summary}")
        except Exception as e:
            logger.error(f"Failed to apply startup lockdown: {e}")

        # Sync staff resources channel
        try:
            from src.core.seller_manager import setup_staff_resources
            await setup_staff_resources(guild, self.config_data)
        except Exception as e:
            logger.error(f"Failed to setup staff resources: {e}")

        # Ready
        logger.info("Bot is ready and waiting for slash commands. Startup sync build disabled.")

    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        logger.info(f"New member joined: {member.name} in guild {guild.name}")
        
        # 1. Run Security Scam Prevention Checks
        from src.core.security_manager import SecurityManager
        sec_mgr = SecurityManager(guild)
        
        # Check for mass joins (raids)
        if sec_mgr.check_raid():
            await sec_mgr.notify_raid(member)
            return  # Suppress normal welcome flow during raids
            
        # Check suspicious profile/alt risk factors
        evaluation = await sec_mgr.evaluate_member(member)
        if evaluation["is_risky"]:
            await sec_mgr.handle_suspicious_member(member, evaluation)
            
        # Automatically assign Unverified role
        ver_cfg = self.config_data.get("verification", {}) if self.config_data else {}
        unver_role_name = ver_cfg.get("unverified_role", "Unverified")
        if unver_role_name:
            unver_role = discord.utils.get(guild.roles, name=unver_role_name)
            if unver_role:
                try:
                    await member.add_roles(unver_role, reason="New user joined, assigning Unverified role")
                    logger.info(f"Assigned unverified role to {member.name}")
                except Exception as e:
                    logger.error(f"Failed to assign unverified role to {member.name}: {e}")

        welcome_chan = discord.utils.get(guild.text_channels, name="┃👋・welcome")
        if not welcome_chan:
            for ch in guild.text_channels:
                if "WELCOME" in ch.name.upper() or "👋" in ch.name:
                    welcome_chan = ch
                    break
        if welcome_chan:
            try:
                await welcome_chan.send(f"Welcome {member.mention}  To {guild.name.upper()} ⚡")
                logger.info(f"Sent welcome message for {member.name} in #{welcome_chan.name}")
            except Exception as e:
                logger.error(f"Failed to send welcome message: {e}")


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token or token == "your_bot_token_here":
        logger.critical("DISCORD_TOKEN is missing or not configured in environment/secrets.")
        return

    # Check for config path, default to server.yml
    config_path = os.getenv("CONFIG_PATH", "src/config/server.yml")
    logger.info(f"Loading configuration from: {config_path}")
    
    config_data = {}
    if os.path.exists(config_path):
        try:
            config_data = load_yaml_config(config_path)
        except Exception as e:
            logger.warning(f"Failed to load configuration from {config_path}: {e}. Using empty defaults.")
    else:
        logger.warning(f"Configuration file {config_path} not found. Using empty defaults.")

    bot = ServerBuilderBot(config_data)
    bot.run(token)

if __name__ == "__main__":
    main()
