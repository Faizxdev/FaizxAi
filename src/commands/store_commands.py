import discord
import json
from discord import app_commands
from discord.ext import commands
from src.core.store_manager import StoreSelectView, fetch_products_from_logs, save_products_to_logs, slugify
from src.utils.helpers import normalize_name
from src.utils.logger import setup_logger

logger = setup_logger("store_commands")

class StoreCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _add_product_logic(
        self,
        guild: discord.Guild,
        name: str,
        price: str,
        features: str,
        color: str = "#ff3e3e",
        prices: str = ""
    ) -> str:
        """Internal helper logic to add/update a product in the Cheat Store."""
        # Find store category & channel
        category = None
        for cat in guild.categories:
            if "STORE" in cat.name.upper() or "🛒" in cat.name:
                category = cat
                break

        if not category:
            return "❌ Store category not found. Please sync the server layout first."

        channel = None
        for ch in category.text_channels:
            if normalize_name(ch.name) == "storepanel":
                channel = ch
                break

        if not channel:
            # Create store-panel channel if it doesn't exist
            try:
                channel = await guild.create_text_channel(
                    name="┃ 🛒 ・ 𝐬𝐭𝐨𝐫𝐞-𝐩𝐚𝐧𝐞𝐥",
                    category=category,
                    overwrites=category.overwrites,
                    reason="Create store channel"
                )
            except Exception as e:
                return f"❌ Failed to create store panel channel: {e}"
        else:
            if channel.name != "┃ 🛒 ・ 𝐬𝐭𝐨𝐫𝐞-𝐩𝐚𝐧𝐞𝐥":
                try:
                    await channel.edit(name="┃ 🛒 ・ 𝐬𝐭𝐨𝐫𝐞-𝐩𝐚𝐧𝐞𝐥")
                except Exception as e:
                    logger.error(f"Failed to rename store panel channel: {e}")

        # Fetch existing products from logs database
        products = await fetch_products_from_logs(guild)

        # Locate existing store message if it exists
        store_msg = None
        async for msg in channel.history(limit=30):
            if msg.author == guild.me and msg.embeds and msg.embeds[0].title and "STORE" in msg.embeds[0].title.upper() and msg.embeds[0].title.startswith("⚡"):
                store_msg = msg
                break

        # Build new product payload
        new_prod = {
            "name": name,
            "price": price,
            "banner_color": color,
            "features": [f.strip() for f in features.split(";") if f.strip()],
            "prices": [p.strip() for p in prices.split(";") if p.strip()] if prices else [price]
        }

        # Update or append product
        replaced = False
        for i, prod in enumerate(products):
            if prod["name"].lower().strip() == name.lower().strip():
                products[i] = new_prod
                replaced = True
                break
        
        if not replaced:
            products.append(new_prod)

        # Save updated products list to logs
        await save_products_to_logs(guild, products)

        # Build updated master panel (completely clean description)
        embed = discord.Embed(
            title=f"⚡ {guild.name.upper()} STORE",
            description="Welcome to the premium cheat repository.\n\n"
                        "Select one of our premium products below using the dropdown to view its detailed features and pricing.",
            color=discord.Color.red()
        )
        embed.set_footer(text="🛒 Safe & Secure Payments • Instant Delivery")

        ticket_cfg = self.bot.config_data.get("tickets", {}) if hasattr(self.bot, "config_data") else {}
        staff_role_name = ticket_cfg.get("staff_role", "Staff")
        log_channel_name = ticket_cfg.get("log_channel", "┃📊・staff-logs")
        ticket_category_name = ticket_cfg.get("category", "━━━━━━━━━━━━\n🎟️ TICKETS\n━━━━━━━━━━━━")

        view = StoreSelectView(
            products=products,
            staff_role_name=staff_role_name,
            log_channel_name=log_channel_name,
            ticket_category_name=ticket_category_name
        )

        try:
            if store_msg:
                await store_msg.edit(embed=embed, view=view)
            else:
                await channel.send(embed=embed, view=view)
            
            action_str = "updated" if replaced else "added"
            return f"✅ Product **{name}** has been successfully {action_str} in the Cheat Store panel!"
        except Exception as e:
            logger.error(f"Failed to edit/send store panel: {e}")
            return f"❌ Failed to update the store panel message: {e}"

    async def _delete_product_logic(self, guild: discord.Guild, name: str) -> str:
        """Internal helper logic to delete a product from the Cheat Store."""
        category = None
        for cat in guild.categories:
            if "STORE" in cat.name.upper() or "🛒" in cat.name:
                category = cat
                break

        if not category:
            return "❌ Store category not found."

        channel = None
        for ch in category.text_channels:
            if normalize_name(ch.name) == "storepanel":
                channel = ch
                break

        if not channel:
            return "❌ Store panel channel not found."

        # Fetch existing products from logs database
        products = await fetch_products_from_logs(guild)

        # Locate existing store message if it exists
        store_msg = None
        async for msg in channel.history(limit=30):
            if msg.author == guild.me and msg.embeds and msg.embeds[0].title and "STORE" in msg.embeds[0].title.upper() and msg.embeds[0].title.startswith("⚡"):
                store_msg = msg
                break

        if not store_msg:
            return "❌ Store select panel message not found in the channel."

        # Find and remove product
        found = False
        updated_products = []
        for prod in products:
            if prod["name"].lower().strip() == name.lower().strip():
                found = True
            else:
                updated_products.append(prod)

        if not found:
            return f"❌ Product **{name}** not found in the Cheat Store database."

        # Save updated products list to logs
        await save_products_to_logs(guild, updated_products)

        # Build updated master panel (completely clean description)
        embed = discord.Embed(
            title=f"⚡ {guild.name.upper()} STORE",
            description="Welcome to the premium cheat repository.\n\n"
                        "Select one of our premium products below using the dropdown to view its detailed features and pricing.",
            color=discord.Color.red()
        )
        embed.set_footer(text="🛒 Safe & Secure Payments • Instant Delivery")

        ticket_cfg = self.bot.config_data.get("tickets", {}) if hasattr(self.bot, "config_data") else {}
        staff_role_name = ticket_cfg.get("staff_role", "Staff")
        log_channel_name = ticket_cfg.get("log_channel", "┃📊・staff-logs")
        ticket_category_name = ticket_cfg.get("category", "━━━━━━━━━━━━\n🎟️ TICKETS\n━━━━━━━━━━━━")

        view = StoreSelectView(
            products=updated_products,
            staff_role_name=staff_role_name,
            log_channel_name=log_channel_name,
            ticket_category_name=ticket_category_name
        )

        try:
            await store_msg.edit(embed=embed, view=view)
            return f"✅ Product **{name}** has been successfully deleted from the Cheat Store panel!"
        except Exception as e:
            logger.error(f"Failed to update store panel: {e}")
            return f"❌ Failed to update the store panel message: {e}"

    # --- Slash Commands ---

    @app_commands.command(name="add-product", description="Add or update a premium panel in the Cheat Store.")
    @app_commands.describe(
        name="Name of the product/panel (e.g. SilentAim Max)",
        price="Primary pricing option shown in dropdown (e.g. 100 INR / 2$ (1 Day))",
        features="Key features separated by semicolons (e.g. Aim Lock; No Recoil; ESP Box)",
        color="Hex code for the product banner (e.g. #ff3e3e)",
        prices="Full list of pricing options separated by semicolons (e.g. 1 Day - 100 INR; 30 Days - 1000 INR)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def add_product(
        self,
        interaction: discord.Interaction,
        name: str,
        price: str,
        features: str,
        color: str = "#ff3e3e",
        prices: str = ""
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return
        res = await self._add_product_logic(guild, name, price, features, color, prices)
        await interaction.followup.send(res, ephemeral=True)

    @app_commands.command(name="delete-product", description="Delete a premium panel from the Cheat Store.")
    @app_commands.describe(name="Name of the product/panel to delete")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_product(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return
        res = await self._delete_product_logic(guild, name)
        await interaction.followup.send(res, ephemeral=True)

    # --- Error Handlers ---

    @add_product.error
    @delete_product.error
    async def handle_slash_errors(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You must have Administrator permissions to run store configuration commands.", ephemeral=True)
        else:
            logger.error(f"Store slash command error: {error}")
            try:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(StoreCommands(bot))
