import discord
from discord import app_commands
from discord.ext import commands
from src.core.onboarding_manager import OnboardingManager, apply_channel_lockdown
from src.utils.logger import setup_logger

logger = setup_logger("verification_commands")


class VerificationCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="setup-verification",
        description="Post or refresh the verification embed and apply channel lockdown (admin only)."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_verification(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Must be used inside a guild.", ephemeral=True)
            return

        config_data = getattr(self.bot, "config_data", {}) or {}
        ver_cfg = config_data.get("verification", {})

        # If no config, use sensible defaults
        if not ver_cfg:
            ver_cfg = {
                "channel": "┃🔒・verify",
                "verified_role": "Verified",
                "unverified_role": "Unverified",
                "embed": {
                    "title": "Verify Here",
                    "description": (
                        "Welcome! Click the button below to verify your account "
                        "and unlock access to the server."
                    ),
                    "color": "#2ecc71"
                }
            }

        try:
            mgr = OnboardingManager(guild)
            await mgr.setup_verification(ver_cfg)
            lockdown_summary = await apply_channel_lockdown(guild, config_data)
            await interaction.followup.send(
                f"✅ **Verification setup complete!**\n\n{lockdown_summary}",
                ephemeral=True
            )
            logger.info(f"setup-verification run by {interaction.user} in {guild.name}")
        except Exception as e:
            logger.error(f"setup-verification error: {e}")
            await interaction.followup.send(f"❌ Error during setup: `{e}`", ephemeral=True)

    @app_commands.command(
        name="lockdown",
        description="Apply channel permission lockdown — hide all channels from unverified users (admin only)."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def lockdown(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        config_data = getattr(self.bot, "config_data", {}) or {}
        try:
            summary = await apply_channel_lockdown(guild, config_data)
            await interaction.followup.send(summary, ephemeral=True)
        except Exception as e:
            logger.error(f"lockdown error: {e}")
            await interaction.followup.send(f"❌ Error: `{e}`", ephemeral=True)

    @setup_verification.error
    @lockdown.error
    async def admin_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            try:
                await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send("❌ Administrator permissions required.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VerificationCommands(bot))
