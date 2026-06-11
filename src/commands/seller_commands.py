import discord
from discord import app_commands
from discord.ext import commands
from src.core.seller_manager import SellerControlView, get_seller_dashboard_embed, fetch_products_from_logs
from src.utils.logger import setup_logger

logger = setup_logger("seller_commands")

class SellerCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="seller-panel", description="Deploy the persistent Seller Control Panel dashboard.")
    @app_commands.checks.has_permissions(administrator=True)
    async def seller_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        if not guild:
            return
            
        products = await fetch_products_from_logs(guild)
        embed = await get_seller_dashboard_embed(guild, products)
        view = SellerControlView()
        
        await interaction.followup.send(embed=embed, view=view)

    @seller_panel.error
    async def seller_panel_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You must have Administrator permissions to deploy the seller panel.", ephemeral=True)
        else:
            logger.error(f"Seller panel command error: {error}")
            try:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SellerCommands(bot))
