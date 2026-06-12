import os
import sys
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Ensure the root folder is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.logger import setup_logger
from src.utils.helpers import load_yaml_config
from src.core.scam_manager import ScamManager

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
        self.scam_manager = ScamManager()

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

        # Startup staff resources setup disabled.

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

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Check permissions: ignore administrators and Staff role
        member = message.author
        if isinstance(member, discord.Member):
            is_staff = member.guild_permissions.administrator or discord.utils.get(member.roles, name="Staff") is not None
            if is_staff:
                await self.process_commands(message)
                return

        # Scan message
        score, reasons, raw_text = await self.scam_manager.scan_message_scams(message)
        
        if score >= self.scam_manager.config["risk_thresholds"]["delete"]:
            # Action logic
            action_taken = "Deleted Message"
            delete_msg = True
            warn_user = False
            timeout_user = False
            urgent_alert = False
            
            if score >= self.scam_manager.config["risk_thresholds"]["alert"]:
                timeout_user = True
                urgent_alert = True
                action_taken = "Delete Message, Timeout (1h) & Urgent Staff Alert"
            elif score >= self.scam_manager.config["risk_thresholds"]["timeout"]:
                timeout_user = True
                action_taken = "Delete Message & Timeout (1h)"
            elif score >= self.scam_manager.config["risk_thresholds"]["warn"]:
                warn_user = True
                action_taken = "Delete Message & Warning DM"
                
            # Execute actions
            if delete_msg:
                try:
                    await message.delete()
                except Exception as e:
                    logger.error(f"Failed to delete scam message: {e}")
                    
            if warn_user:
                try:
                    embed = discord.Embed(
                        title=f"Warning from {message.guild.name}",
                        description=f"Your message was flagged as a potential scam and deleted.\nReason: {', '.join(reasons)}",
                        color=discord.Color.orange(),
                        timestamp=discord.utils.utcnow()
                    )
                    await member.send(embed=embed)
                except Exception as e:
                    logger.warning(f"Could not send warning DM to {member.name}: {e}")
                    
            if timeout_user:
                try:
                    import datetime
                    await member.timeout(datetime.timedelta(hours=1), reason=f"Scam Shield flag ({score}/100)")
                except Exception as e:
                    logger.error(f"Failed to timeout user {member.name}: {e}")
                    
            # Log to scam-alerts channel
            alert_chan_name = self.scam_manager.config.get("alert_channel", "scam-alerts")
            alert_channel = discord.utils.get(message.guild.text_channels, name=alert_chan_name)
            if not alert_channel:
                try:
                    category = discord.utils.get(message.guild.categories, name="👑 STAFF")
                    overwrites = {
                        message.guild.default_role: discord.PermissionOverwrite(view_channel=False)
                    }
                    alert_channel = await message.guild.create_text_channel(
                        name=alert_chan_name,
                        category=category,
                        overwrites=overwrites,
                        reason="Auto-creating scam alerts channel"
                    )
                except Exception as e:
                    logger.error(f"Failed to create scam alerts channel: {e}")
                    
            image_url = message.attachments[0].url if message.attachments else None
            
            if alert_channel:
                try:
                    log_embed = discord.Embed(
                        title="🛡️ Scam Shield Event Log",
                        color=discord.Color.red() if score >= 80 else discord.Color.orange(),
                        timestamp=discord.utils.utcnow()
                    )
                    log_embed.add_field(name="User", value=f"{member.mention} ({member.name} - ID: {member.id})", inline=True)
                    log_embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                    log_embed.add_field(name="Message ID", value=message.id, inline=True)
                    log_embed.add_field(name="Risk Score", value=f"**{score}/100**", inline=True)
                    log_embed.add_field(name="Action Taken", value=action_taken, inline=True)
                    log_embed.add_field(name="Reasons Triggered", value="\n".join(reasons) or "None", inline=False)
                    log_embed.add_field(name="Scanned Content", value=raw_text[:1024], inline=False)
                    
                    if image_url:
                        log_embed.set_image(url=image_url)
                        
                    await alert_channel.send(embed=log_embed)
                except Exception as e:
                    logger.error(f"Failed to post log to scam alerts channel: {e}")
                    
            if urgent_alert:
                try:
                    from src.core.security_manager import SecurityManager
                    sec_mgr = SecurityManager(message.guild)
                    await sec_mgr.post_scam_alert(member, message.channel, score, reasons, raw_text, action_taken, image_url)
                except Exception as e:
                    logger.error(f"Failed to post urgent staff scam alert: {e}")
                    
            # Save history log in manager
            self.scam_manager.log_detection(
                user_id=member.id,
                username=member.name,
                channel_id=message.channel.id,
                message_id=message.id,
                score=score,
                reasons=reasons,
                text=raw_text,
                action=action_taken,
                image_url=image_url
            )
            # Skip command processing for deleted scam messages
            return

        await self.process_commands(message)

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
