import discord
from discord import app_commands
from discord.ext import commands
from src.core.backup_manager import BackupManager
from src.core.guild_builder import GuildBuilder
from src.utils.logger import setup_logger

logger = setup_logger("backup_commands")

class Backup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="backup-create", description="Create a JSON backup of the server layout.")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_create(self, interaction: discord.Interaction, filename: str):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        try:
            file_path = BackupManager.save_backup(guild, filename)
            await interaction.followup.send(f"✅ Backup successfully created and saved to `{file_path}`.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            await interaction.followup.send(f"❌ Failed to create backup: {e}", ephemeral=True)

    @app_commands.command(name="backup-load", description="Load and apply a server backup configuration.")
    @app_commands.checks.has_permissions(administrator=True)
    async def backup_load(self, interaction: discord.Interaction, filename: str):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        try:
            # Read backup json
            backup_data = BackupManager.load_backup(filename)
            await interaction.followup.send(f"⌛ Applying backup layout from `{filename}`. This might take a few moments...", ephemeral=True)
            
            # Use GuildBuilder to apply
            builder = GuildBuilder(guild)
            report = await builder.build(backup_data)
            
            status_msg = f"✅ Backup restoration finished!\n**Status**: {report['status']}\n" \
                         f"- Roles Synced: {report['roles_synced']}\n" \
                         f"- Categories Synced: {report['categories_synced']}\n" \
                         f"- Channels Synced: {report['channels_synced']}"
                         
            if report["errors"]:
                status_msg += f"\n**Errors occurred**:\n- " + "\n- ".join(report["errors"][:5])
                
            # Log action
            log_chan = discord.utils.get(guild.text_channels, name="moderation-logs")
            if log_chan:
                embed = discord.Embed(
                    title="Backup Applied",
                    description=f"Server backup file `{filename}` was applied by {interaction.user.mention}.",
                    color=discord.Color.orange(),
                    timestamp=discord.utils.utcnow()
                )
                await log_chan.send(embed=embed)
                
            await interaction.followup.send(status_msg, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to load backup: {e}")
            await interaction.followup.send(f"❌ Failed to load backup: {e}", ephemeral=True)

    @backup_create.error
    @backup_load.error
    async def handle_errors(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You must have Administrator permissions to run backup commands.", ephemeral=True)
        else:
            logger.error(f"Backup command error: {error}")
            try:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
