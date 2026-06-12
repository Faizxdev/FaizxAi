import discord
import datetime
from discord import app_commands
from discord.ext import commands
from src.utils.logger import setup_logger

logger = setup_logger("moderation_commands")

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await interaction.response.defer()
        
        if member.top_role >= interaction.user.top_role and not interaction.guild.owner == interaction.user:
            await interaction.followup.send("You cannot ban someone with a higher or equal role to yours.", ephemeral=True)
            return

        try:
            await member.ban(reason=f"Banned by {interaction.user.name}: {reason}")
            await interaction.followup.send(f"Successfully banned {member.mention} for: {reason}")
            
            # Log moderation action
            await self._log_mod_action(interaction.guild, "Ban", member, interaction.user, reason)
        except Exception as e:
            logger.error(f"Failed to ban {member.name}: {e}")
            await interaction.followup.send(f"Failed to ban member: {e}", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await interaction.response.defer()
        
        if member.top_role >= interaction.user.top_role and not interaction.guild.owner == interaction.user:
            await interaction.followup.send("You cannot kick someone with a higher or equal role to yours.", ephemeral=True)
            return

        try:
            await member.kick(reason=f"Kicked by {interaction.user.name}: {reason}")
            await interaction.followup.send(f"Successfully kicked {member.mention} for: {reason}")
            
            # Log moderation action
            await self._log_mod_action(interaction.guild, "Kick", member, interaction.user, reason)
        except Exception as e:
            logger.error(f"Failed to kick {member.name}: {e}")
            await interaction.followup.send(f"Failed to kick member: {e}", ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout a member in the server.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
        await interaction.response.defer()
        
        if member.top_role >= interaction.user.top_role and not interaction.guild.owner == interaction.user:
            await interaction.followup.send("You cannot timeout someone with a higher or equal role to yours.", ephemeral=True)
            return

        try:
            duration = datetime.timedelta(minutes=minutes)
            await member.timeout(duration, reason=f"Timeout by {interaction.user.name}: {reason}")
            await interaction.followup.send(f"Successfully timed out {member.mention} for {minutes} minutes. Reason: {reason}")
            
            # Log moderation action
            await self._log_mod_action(interaction.guild, "Timeout", member, interaction.user, f"{minutes} min - {reason}")
        except Exception as e:
            logger.error(f"Failed to timeout {member.name}: {e}")
            await interaction.followup.send(f"Failed to timeout member: {e}", ephemeral=True)

    @app_commands.command(name="warn", description="Warn a member and send them a DM.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await interaction.response.defer()
        
        # Send warning DM
        dm_sent = False
        try:
            embed = discord.Embed(
                title=f"Warning from {interaction.guild.name}",
                description=f"You have been warned for: **{reason}**",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            await member.send(embed=embed)
            dm_sent = True
        except Exception as e:
            logger.warning(f"Could not DM user {member.name} warning: {e}")

        status = f"Warned {member.mention} for: {reason}"
        if not dm_sent:
            status += " (DM could not be delivered)"

        await interaction.followup.send(status)
        await self._log_mod_action(interaction.guild, "Warning", member, interaction.user, reason)

    @app_commands.command(name="clear", description="Clear a specified amount of messages.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, amount: int):
        if amount < 1:
            await interaction.response.send_message("Please specify an amount greater than 0.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await interaction.channel.purge(limit=amount)
            await interaction.followup.send(f"Successfully cleared {len(deleted)} messages.", ephemeral=True)
            
            # Log mod action (without member target)
            log_chan = discord.utils.get(interaction.guild.text_channels, name="moderation-logs")
            if log_chan:
                embed = discord.Embed(
                    title="Messages Cleared",
                    description=f"{interaction.user.mention} cleared {len(deleted)} messages in {interaction.channel.mention}.",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                await log_chan.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to clear messages: {e}")
            await interaction.followup.send(f"Failed to clear messages: {e}", ephemeral=True)

    @app_commands.command(name="lock", description="Lock the current channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction):
        await interaction.response.defer()
        channel = interaction.channel
        guild = interaction.guild
        
        try:
            await channel.set_permissions(guild.default_role, send_messages=False, reason=f"Channel locked by {interaction.user.name}")
            await interaction.followup.send(f"🔒 {channel.mention} has been locked.")
            await self._log_mod_action(guild, "Channel Lock", None, interaction.user, f"Channel {channel.name} locked.")
        except Exception as e:
            logger.error(f"Failed to lock channel {channel.name}: {e}")
            await interaction.followup.send(f"Failed to lock channel: {e}", ephemeral=True)

    @app_commands.command(name="unlock", description="Unlock the current channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction):
        await interaction.response.defer()
        channel = interaction.channel
        guild = interaction.guild
        
        try:
            await channel.set_permissions(guild.default_role, send_messages=None, reason=f"Channel unlocked by {interaction.user.name}")
            await interaction.followup.send(f"🔓 {channel.mention} has been unlocked.")
            await self._log_mod_action(guild, "Channel Unlock", None, interaction.user, f"Channel {channel.name} unlocked.")
        except Exception as e:
            logger.error(f"Failed to unlock channel {channel.name}: {e}")
            await interaction.followup.send(f"Failed to unlock channel: {e}", ephemeral=True)

    async def _log_mod_action(self, guild: discord.Guild, action: str, target: discord.Member, mod: discord.Member, reason: str):
        log_chan = discord.utils.get(guild.text_channels, name="moderation-logs")
        if not log_chan:
            return
            
        embed = discord.Embed(
            title=f"Moderation: {action}",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        if target:
            embed.add_field(name="Target User", value=f"{target.mention} ({target.name}#{target.discriminator or '0000'})", inline=False)
            embed.add_field(name="Target ID", value=target.id, inline=True)
            
        embed.add_field(name="Moderator", value=f"{mod.mention} ({mod.name})", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        
        try:
            await log_chan.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to write to moderation-logs: {e}")

    @app_commands.command(name="scan-channel-scams", description="Scan recent messages in this channel for scams and images.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def scan_channel_scams(self, interaction: discord.Interaction, limit: int = 50):
        await interaction.response.defer(ephemeral=True)
        
        limit = max(1, min(limit, 250))
        scam_mgr = getattr(self.bot, "scam_manager", None)
        if not scam_mgr:
            await interaction.followup.send("❌ Scam manager is not initialized.", ephemeral=True)
            return

        messages_scanned = 0
        images_scanned = 0
        scams_found = 0
        flagged_users = set()

        async for message in interaction.channel.history(limit=limit):
            if message.author.bot:
                continue
                
            messages_scanned += 1
            if message.attachments:
                for attachment in message.attachments:
                    if any(attachment.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]):
                        images_scanned += 1

            score, reasons, raw_text = await scam_mgr.scan_message_scams(message)
            if score >= scam_mgr.config["risk_thresholds"]["delete"]:
                scams_found += 1
                flagged_users.add(message.author.id)

        embed = discord.Embed(
            title="🔍 Scam Scan Audit Complete",
            color=discord.Color.green() if scams_found == 0 else discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Messages Scanned", value=str(messages_scanned), inline=True)
        embed.add_field(name="Images Scanned", value=str(images_scanned), inline=True)
        embed.add_field(name="Scams Found", value=str(scams_found), inline=True)
        embed.add_field(name="Users Flagged", value=str(len(flagged_users)), inline=True)
        embed.set_footer(text=interaction.guild.name)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="scam-history", description="Show a list of recent scam detections on the server.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def scam_history(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        
        limit = max(1, min(limit, 50))
        scam_mgr = getattr(self.bot, "scam_manager", None)
        if not scam_mgr or not scam_mgr.history:
            await interaction.followup.send("No recent scam detections found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📜 Recent Scam Detections",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )
        
        recent_events = list(reversed(scam_mgr.history))[:limit]
        for idx, event in enumerate(recent_events):
            val = (
                f"**User**: <@{event['user_id']}> ({event['username']})\n"
                f"**Score**: `{event['score']}/100`\n"
                f"**Action**: {event['action']}\n"
                f"**Reasons**: {', '.join(event['reasons']) or 'None'}\n"
                f"**Text**: `{event['text']}`"
            )
            embed.add_field(name=f"#{idx+1} - {event['timestamp'][:19].replace('T', ' ')}", value=val, inline=False)
            
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="scam-config", description="Configure Scam Shield settings dynamically.")
    @app_commands.checks.has_permissions(administrator=True)
    async def scam_config(
        self, 
        interaction: discord.Interaction, 
        delete_threshold: int = None, 
        warn_threshold: int = None, 
        timeout_threshold: int = None, 
        alert_channel: str = None,
        auto_delete: bool = None,
        auto_timeout: bool = None
    ):
        await interaction.response.defer(ephemeral=True)
        
        scam_mgr = getattr(self.bot, "scam_manager", None)
        if not scam_mgr:
            await interaction.followup.send("❌ Scam manager not initialized.", ephemeral=True)
            return

        # Update values
        if delete_threshold is not None:
            scam_mgr.config["risk_thresholds"]["delete"] = max(0, min(delete_threshold, 100))
        if warn_threshold is not None:
            scam_mgr.config["risk_thresholds"]["warn"] = max(0, min(warn_threshold, 100))
        if timeout_threshold is not None:
            scam_mgr.config["risk_thresholds"]["timeout"] = max(0, min(timeout_threshold, 100))
        if alert_channel is not None:
            scam_mgr.config["alert_channel"] = alert_channel.lower().replace("#", "").strip()
        if auto_delete is not None:
            scam_mgr.config["auto_delete"] = auto_delete
        if auto_timeout is not None:
            scam_mgr.config["auto_timeout"] = auto_timeout

        scam_mgr.save_config()

        embed = discord.Embed(
            title="⚙️ Scam Shield Configuration Updated",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Delete Threshold", value=f"Score >= {scam_mgr.config['risk_thresholds']['delete']}", inline=True)
        embed.add_field(name="Warn Threshold", value=f"Score >= {scam_mgr.config['risk_thresholds']['warn']}", inline=True)
        embed.add_field(name="Timeout Threshold", value=f"Score >= {scam_mgr.config['risk_thresholds']['timeout']}", inline=True)
        embed.add_field(name="Alert Channel", value=f"#{scam_mgr.config.get('alert_channel', 'scam-alerts')}", inline=True)
        embed.add_field(name="Auto Delete Active", value=str(scam_mgr.config.get("auto_delete", True)), inline=True)
        embed.add_field(name="Auto Timeout Active", value=str(scam_mgr.config.get("auto_timeout", True)), inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @ban.error
    @kick.error
    @timeout.error
    @warn.error
    @clear.error
    @lock.error
    @unlock.error
    @scan_channel_scams.error
    @scam_history.error
    @scam_config.error
    async def handle_errors(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You do not have the required permissions to run this command.", ephemeral=True)
        else:
            logger.error(f"Command execution error: {error}")
            try:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
