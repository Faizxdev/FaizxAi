import discord
import re
import json
import io
from typing import Dict, Any, List, Optional
from src.utils.logger import setup_logger
from src.utils.helpers import to_bold_unicode, normalize_name

logger = setup_logger("store_manager")

def slugify(text: str) -> str:
    """Helper to convert product names to simple custom_id slugs."""
    return re.sub(r'[^a-zA-Z0-9_-]', '', text.lower().replace(" ", "_"))

def parse_color(color_hex: str) -> discord.Color:
    color_hex = color_hex.lstrip("#")
    try:
        return discord.Color(int(color_hex, 16))
    except ValueError:
        return discord.Color.red()

async def fetch_products_from_logs(guild: discord.Guild) -> List[Dict[str, Any]]:
    """Fetches the products database by finding the last products_db.json attachment in staff logs."""
    log_chan = discord.utils.get(guild.text_channels, name="┃📊・staff-logs")
    if not log_chan:
        for ch in guild.text_channels:
            if "LOG" in ch.name.upper() or "📊" in ch.name:
                log_chan = ch
                break
    if not log_chan:
        logger.warning("Could not locate staff-logs channel to fetch products.")
        return []

    try:
        async for msg in log_chan.history(limit=50):
            if msg.author == guild.me and msg.attachments:
                for att in msg.attachments:
                    if att.filename == "products_db.json":
                        content_bytes = await att.read()
                        data = json.loads(content_bytes.decode("utf-8"))
                        return data.get("products", [])
    except Exception as e:
        logger.error(f"Error fetching products database from staff-logs: {e}")
    return []

async def save_products_to_logs(guild: discord.Guild, products: List[Dict[str, Any]]) -> None:
    """Saves the products database by uploading it as a file attachment to staff logs."""
    log_chan = discord.utils.get(guild.text_channels, name="┃📊・staff-logs")
    if not log_chan:
        for ch in guild.text_channels:
            if "LOG" in ch.name.upper() or "📊" in ch.name:
                log_chan = ch
                break
    if not log_chan:
        logger.error("Could not locate staff-logs channel to save products.")
        return

    try:
        data = {"products": products}
        json_bytes = json.dumps(data, indent=2).encode("utf-8")
        file_data = io.BytesIO(json_bytes)
        discord_file = discord.File(file_data, filename="products_db.json")

        await log_chan.send(
            content="🔄 **Cheat Store Database Auto-Sync Backup**",
            file=discord_file
        )
        logger.info("Saved products database to staff logs channel.")
    except Exception as e:
        logger.error(f"Failed to save products database to staff logs: {e}")

# Keeping for backward compatibility / reference
def extract_products_from_description(description: str) -> List[Dict[str, Any]]:
    return []

async def fetch_products_from_channel(channel: discord.TextChannel) -> List[Dict[str, Any]]:
    return await fetch_products_from_logs(channel.guild)


class StoreProductBuyView(discord.ui.View):
    def __init__(self, product_name: str, price: str, staff_role_name: str = "Staff", log_channel_name: str = "┃📊・staff-logs", ticket_category_name: str = "━━━━━━━━━━━━\n🎟️ TICKETS\n━━━━━━━━━━━━"):
        slug = slugify(product_name)
        super().__init__(timeout=None)
        self.product_name = product_name
        self.price = price
        self.staff_role_name = staff_role_name
        self.log_channel_name = log_channel_name
        self.ticket_category_name = ticket_category_name

        # Create persistent button
        btn = discord.ui.Button(
            label="Buy Now",
            style=discord.ButtonStyle.success,
            emoji="🛒",
            custom_id=f"buy_prod_{slug}"
        )
        btn.callback = self.buy_callback
        self.add_item(btn)

    async def buy_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user
        if not guild or not user:
            return

        # Resolve Category where ticket is created
        category = discord.utils.get(guild.categories, name=self.ticket_category_name)
        if not category:
            for cat in guild.categories:
                if "TICKET" in cat.name.upper() or "🎟️" in cat.name:
                    category = cat
                    break

        staff_role = discord.utils.get(guild.roles, name=self.staff_role_name)
        
        # User and Staff get access, @everyone hidden, user restricted from sending messages until claimed
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        chan_slug = slugify(self.product_name)
        channel_name = f"💸-{chan_slug}-{user.name}"
        
        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Purchase ticket opened for {self.product_name}"
            )
            await interaction.followup.send(f"Purchase ticket created! Access it here: {ticket_channel.mention}", ephemeral=True)

            # Welcome embed in purchase ticket
            embed = discord.Embed(
                title=f"💳 Purchase Request: {self.product_name}",
                description=f"Hello {user.mention}!\n\n"
                            f"You have requested to purchase **{self.product_name}**.\n\n"
                            f"Our support/sales team will be with you shortly to assist with payment and deliver your product.",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            
            from src.core.onboarding_manager import TicketControlView
            control_view = TicketControlView(self.staff_role_name, self.log_channel_name)
            await ticket_channel.send(content=f"{user.mention} Welcome! {staff_role.mention if staff_role else ''}", embed=embed, view=control_view)

            # Log purchase ticket creation
            log_chan = discord.utils.get(guild.text_channels, name=self.log_channel_name)
            if log_chan:
                log_embed = discord.Embed(
                    title="Purchase Ticket Created",
                    description=f"User {user.mention} opened purchase ticket {ticket_channel.mention} for **{self.product_name}**.",
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow()
                )
                log_embed.add_field(name="Price", value=self.price)
                await log_chan.send(embed=log_embed)
        except Exception as e:
            logger.error(f"Failed to create purchase ticket channel: {e}")
            await interaction.followup.send("Failed to create ticket channel. Admin help needed.", ephemeral=True)


class StoreSelect(discord.ui.Select):
    def __init__(self, products: Optional[List[Dict[str, Any]]] = None, staff_role_name: str = "Staff", log_channel_name: str = "┃📊・staff-logs", ticket_category_name: str = "━━━━━━━━━━━━\n🎟️ TICKETS\n━━━━━━━━━━━━"):
        self.products = products or []
        self.staff_role_name = staff_role_name
        self.log_channel_name = log_channel_name
        self.ticket_category_name = ticket_category_name

        options = []
        for prod in self.products:
            name = prod.get("name")
            desc = prod.get("price", "View pricing info")
            prod_emoji = prod.get("emoji")
            
            if len(desc) > 100:
                desc = desc[:97] + "..."
                
            emoji_obj = None
            if prod_emoji:
                prod_emoji = prod_emoji.strip()
                if prod_emoji.startswith("<") and prod_emoji.endswith(">"):
                    match = re.match(r"<a?:([^:]+):([0-9]+)>", prod_emoji)
                    if match:
                        emoji_obj = discord.PartialEmoji(name=match.group(1), id=int(match.group(2)))
                else:
                    emoji_obj = prod_emoji

            options.append(discord.SelectOption(
                label=name,
                description=desc,
                value=slugify(name),
                emoji=emoji_obj or "⚡"
            ))

        if not options:
            options.append(discord.SelectOption(
                label="No Products Available",
                description="Check back later!",
                value="no_products",
                emoji="❌"
            ))

        super().__init__(
            placeholder="Select a premium panel...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="store_select_menu"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_slug = self.values[0]
        if selected_slug == "no_products":
            await interaction.response.send_message("No products currently active in store.", ephemeral=True)
            return

        # Load products dynamically from staff logs attachment!
        products = await fetch_products_from_logs(interaction.guild)

        selected_prod = None
        for prod in products:
            if slugify(prod.get("name")) == selected_slug:
                selected_prod = prod
                break

        if not selected_prod:
            await interaction.response.send_message("Product details could not be parsed from this panel.", ephemeral=True)
            return

        name = selected_prod.get("name")
        features = selected_prod.get("features", [])
        prices = selected_prod.get("prices", [selected_prod.get("price", "$0.00")])
        color_hex = selected_prod.get("banner_color", "#e74c3c")
        
        # Build embed (completely clean UI description)
        color = parse_color(color_hex)
        prod_emoji = selected_prod.get("emoji", "⚡")
        embed_emoji = prod_emoji.strip() if prod_emoji else "⚡"
        embed = discord.Embed(
            title=f"{embed_emoji} {name.upper()}",
            description="Here are the detailed features and pricing for this premium panel.",
            color=color
        )
        features_text = "\n".join([f"- {f}" for f in features])
        embed.add_field(name="✨ Features", value=features_text or "No features listed.", inline=False)
        
        prices_text = "\n".join([f"`{p}`" for p in prices])
        embed.add_field(name="💵 Pricing Structure", value=prices_text or "No pricing listed.", inline=False)
        embed.set_footer(text="🛒 Safe & Secure Payments • Instant Ticket Delivery")

        view = StoreSelectView(
            products=products,
            staff_role_name=self.staff_role_name,
            log_channel_name=self.log_channel_name,
            ticket_category_name=self.ticket_category_name,
            selected_product=selected_prod
        )

        await interaction.response.edit_message(embed=embed, view=view)


class StoreSelectView(discord.ui.View):
    def __init__(self, products: Optional[List[Dict[str, Any]]] = None, staff_role_name: str = "Staff", log_channel_name: str = "┃📊・staff-logs", ticket_category_name: str = "━━━━━━━━━━━━\n🎟️ TICKETS\n━━━━━━━━━━━━", selected_product: Optional[Dict[str, Any]] = None):
        super().__init__(timeout=None)
        self.products = products or []
        self.staff_role_name = staff_role_name
        self.log_channel_name = log_channel_name
        self.ticket_category_name = ticket_category_name

        # Add select menu
        self.add_item(StoreSelect(self.products, staff_role_name, log_channel_name, ticket_category_name))

        # Add Buy button if a product is selected
        if selected_product:
            name = selected_product.get("name")
            slug = slugify(name)
            prices = selected_product.get("prices", [selected_product.get("price", "$0.00")])
            main_price = prices[0] if prices else selected_product.get("price", "$0.00")
            
            btn_emoji = None
            prod_emoji = selected_product.get("emoji")
            if prod_emoji:
                prod_emoji = prod_emoji.strip()
                if prod_emoji.startswith("<") and prod_emoji.endswith(">"):
                    match = re.match(r"<a?:([^:]+):([0-9]+)>", prod_emoji)
                    if match:
                        btn_emoji = discord.PartialEmoji(name=match.group(1), id=int(match.group(2)))
                else:
                    btn_emoji = prod_emoji

            btn = discord.ui.Button(
                label=f"Buy {name}",
                style=discord.ButtonStyle.success,
                emoji=btn_emoji or "🛒",
                custom_id=f"buy_prod_{slug}"
            )
            self.add_item(btn)


class StoreManager:
    def __init__(self, guild: discord.Guild):
        self.guild = guild

    async def sync_store(self, config: Dict[str, Any]) -> None:
        """Post the default blank select panel if it does not exist."""
        # Locate the Store category
        category = None
        for cat in self.guild.categories:
            if "STORE" in cat.name.upper() or "🛒" in cat.name:
                category = cat
                break

        if not category:
            logger.warning("Could not find Store Category. Skipping store layout sync.")
            return

        ticket_cfg = config.get("tickets", {}) if config else {}
        staff_role_name = ticket_cfg.get("staff_role", "Staff")
        log_channel_name = ticket_cfg.get("log_channel", "┃📊・staff-logs")
        ticket_category_name = ticket_cfg.get("category", "━━━━━━━━━━━━\n🎟️ TICKETS\n━━━━━━━━━━━━")

        channel_name = "┃ 🛒 ・ 𝐬𝐭𝐨𝐫𝐞-𝐩𝐚𝐧𝐞𝐥"
        
        channel = None
        for ch in category.text_channels:
            if normalize_name(ch.name) == "storepanel":
                channel = ch
                break

        if not channel:
            overwrites = category.overwrites.copy()
            try:
                channel = await self.guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    reason="Create store channel"
                )
                logger.info(f"Created product channel: #{channel_name}")
            except Exception as e:
                logger.error(f"Failed to create product channel '{channel_name}': {e}")
                return
        else:
            if channel.name != channel_name:
                try:
                    await channel.edit(name=channel_name)
                    logger.info(f"Renamed store panel channel to #{channel_name}")
                except Exception as e:
                    logger.error(f"Failed to rename store panel channel to #{channel_name}: {e}")

        # Check if already posted
        already_posted = False
        async for msg in channel.history(limit=20):
            if msg.author == self.guild.me and msg.embeds and msg.embeds[0].title and "STORE" in msg.embeds[0].title.upper() and msg.embeds[0].title.startswith("⚡"):
                already_posted = True
                break

        if already_posted:
            logger.debug("Store select panel already posted.")
            return

        # Purge to keep it clean
        try:
            await channel.purge(limit=10, check=lambda m: m.author == self.guild.me)
        except Exception as e:
            logger.debug(f"Could not purge in #{channel_name}: {e}")

        # Fetch existing products from logs database
        products = await fetch_products_from_logs(self.guild)

        # Post the default master store selector panel (completely clean UI description)
        embed = discord.Embed(
            title=f"⚡ {self.guild.name.upper()} STORE",
            description="Welcome to the premium cheat repository.\n\n"
                        "Select one of our premium products below using the dropdown to view its detailed features and pricing.",
            color=discord.Color.red()
        )
        embed.set_footer(text="🛒 Safe & Secure Payments • Instant Delivery")

        view = StoreSelectView(
            products=products,
            staff_role_name=staff_role_name,
            log_channel_name=log_channel_name,
            ticket_category_name=ticket_category_name
        )

        try:
            await channel.send(embed=embed, view=view)
            logger.info(f"Posted store select panel in #{channel_name}.")
        except Exception as e:
            logger.error(f"Failed to post store select panel: {e}")
