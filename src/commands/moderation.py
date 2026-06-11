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

    @ban.error
    @kick.error
    @timeout.error
    @warn.error
    @clear.error
    @lock.error
    @unlock.error
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
