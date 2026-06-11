import discord
import re
import json
from typing import Dict, Any, List, Optional
from src.utils.logger import setup_logger
from src.core.store_manager import (
    fetch_products_from_logs,
    save_products_to_logs,
    slugify,
    parse_color,
    StoreSelectView
)
from src.utils.helpers import to_bold_unicode, normalize_name

logger = setup_logger("seller_manager")

def get_clean_emoji_for_channel(emoji_str: str) -> str:
    if not emoji_str:
        return "🛒"
    emoji_str = emoji_str.strip()
    if emoji_str.startswith("<") and emoji_str.endswith(">"):
        return "🛒"
    return emoji_str

async def get_seller_dashboard_embed(guild: discord.Guild, products: List[Dict[str, Any]]) -> discord.Embed:
    embed = discord.Embed(
        title="👑 SELLER MANAGEMENT DASHBOARD",
        description="Welcome to the Seller Control Panel. Staff can manage store products, pricing, stock levels, promotions, and announcements directly below without touching any code.",
        color=discord.Color.purple(),
        timestamp=discord.utils.utcnow()
    )
    
    if not products:
        embed.add_field(
            name="📦 Store Inventory",
            value="No products are currently configured in the database.",
            inline=False
        )
    else:
        products_text = ""
        for i, prod in enumerate(products, start=1):
            name = prod.get("name", "Unknown")
            emoji = prod.get("emoji", "🛒")
            price = prod.get("price", "$0.00")
            stock = prod.get("stock", "In Stock")
            promo = prod.get("promotion", "")
            
            # Stock indicator emoji
            stock_indicator = "🟢"
            if "out" in stock.lower():
                stock_indicator = "🔴"
            elif "limit" in stock.lower() or "few" in stock.lower():
                stock_indicator = "🟡"
                
            promo_indicator = f"🔥 `{promo}`" if promo and promo != "None" else "None"
            
            products_text += (
                f"**{i}. {emoji} {name}**\n"
                f"• Price: `{price}`\n"
                f"• Stock: {stock_indicator} `{stock}`\n"
                f"• Promotion: {promo_indicator}\n\n"
            )
        embed.add_field(name="📦 Current Products List", value=products_text, inline=False)
        
    embed.set_footer(text="FAIzxCHEATS Seller Controls • Serverless DB Linked")
    return embed

async def update_seller_panel_message(guild: discord.Guild, channel: discord.abc.GuildChannel):
    if not isinstance(channel, discord.TextChannel):
        return
        
    products = await fetch_products_from_logs(guild)
    embed = await get_seller_dashboard_embed(guild, products)
    
    panel_msg = None
    async for msg in channel.history(limit=50):
        if msg.author == guild.me and msg.embeds and msg.embeds[0].title == "👑 SELLER MANAGEMENT DASHBOARD":
            panel_msg = msg
            break
            
    if panel_msg:
        try:
            await panel_msg.edit(embed=embed, view=SellerControlView())
            logger.info("Updated existing Seller Management Dashboard panel.")
        except Exception as e:
            logger.error(f"Failed to edit Seller Management Dashboard panel: {e}")

async def update_public_store_panel(guild: discord.Guild, products: List[Dict[str, Any]], bot_config_data: dict):
    # Locate the Store category
    category = None
    for cat in guild.categories:
        if "STORE" in cat.name.upper() or "🛒" in cat.name:
            category = cat
            break
    if not category:
        logger.warning("Could not find Store Category to update store-panel.")
        return

    channel_name = "┃ 🛒 ・ 𝐬𝐭𝐨𝐫𝐞-𝐩𝐚𝐧𝐞𝐥"
    channel = None
    for ch in category.text_channels:
        if normalize_name(ch.name) == "storepanel":
            channel = ch
            break

    # Resolve roles for proper lockdown
    verification_cfg = bot_config_data.get("verification", {})
    verified_role_name = verification_cfg.get("verified_role", "Verified")
    ticket_cfg_inner = bot_config_data.get("tickets", {})
    staff_role_name_inner = ticket_cfg_inner.get("staff_role", "Staff")
    verified_role = discord.utils.get(guild.roles, name=verified_role_name)
    staff_role = discord.utils.get(guild.roles, name=staff_role_name_inner)

    store_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False)
    }
    if verified_role:
        store_overwrites[verified_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=False, read_message_history=True
        )
    if staff_role:
        store_overwrites[staff_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_messages=True
        )

    if not channel:
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=store_overwrites,
                reason="Create store panel channel (was missing)"
            )
            logger.info(f"Created missing store panel channel: #{channel_name}")
        except Exception as e:
            logger.error(f"Failed to create store panel channel: {e}")
            return
    else:
        if channel.name != channel_name:
            try:
                await channel.edit(name=channel_name)
                logger.info(f"Renamed store panel channel to #{channel_name}")
            except Exception as e:
                logger.error(f"Failed to rename store panel channel to #{channel_name}: {e}")
        # Enforce lockdown perms even on existing channel
        try:
            await channel.edit(overwrites=store_overwrites)
        except Exception:
            pass

    # Find existing store message
    store_msg = None
    async for msg in channel.history(limit=30):
        if msg.author == guild.me and msg.embeds and msg.embeds[0].title and "STORE" in msg.embeds[0].title.upper() and msg.embeds[0].title.startswith("⚡"):
            store_msg = msg
            break

    embed = discord.Embed(
        title=f"⚡ {guild.name.upper()} STORE",
        description="Welcome to the premium cheat repository.\n\n"
                    "Select one of our premium products below using the dropdown to view its detailed features and pricing.",
        color=discord.Color.red()
    )
    embed.set_footer(text="🛒 Safe & Secure Payments • Instant Delivery")

    ticket_cfg = bot_config_data.get("tickets", {})
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
        logger.info("Updated public store panel select dropdown message.")
    except Exception as e:
        logger.error(f"Failed to send/edit public store panel: {e}")

async def sync_product_channels(guild: discord.Guild, products: List[Dict[str, Any]], bot_config_data: dict):
    # Locate Store category
    category = None
    for cat in guild.categories:
        if "STORE" in cat.name.upper() or "🛒" in cat.name:
            category = cat
            break
    if not category:
        logger.warning("Could not find Store Category to sync product channels.")
        return

    ticket_cfg = bot_config_data.get("tickets", {})
    staff_role_name = ticket_cfg.get("staff_role", "Staff")
    verification_cfg = bot_config_data.get("verification", {})
    verified_role_name = verification_cfg.get("verified_role", "Verified")

    # Keep track of valid channel names
    valid_channel_names = ["┃ 🛒 ・ 𝐬𝐭𝐨𝐫𝐞-𝐩𝐚𝐧𝐞𝐥"]
    
    for prod in products:
        name = prod.get("name")
        emoji = prod.get("emoji", "🛒")
        slug = slugify(name)
        
        # Use clean emoji for channel name
        chan_emoji = get_clean_emoji_for_channel(emoji)
        bold_name = to_bold_unicode(name.replace(" ", "-").replace("_", "-"))
        channel_name = f"┃ {chan_emoji} ・ {bold_name}"
        valid_channel_names.append(channel_name)

        # Find or create the channel under Store category
        chan = None
        prod_norm = normalize_name(name)
        for ch in category.text_channels:
            if normalize_name(ch.name) == prod_norm:
                chan = ch
                break

        # If it doesn't exist, create it!
        # If it exists, verify its name is exactly correct. If not, rename it.
        if chan:
            if chan.name != channel_name:
                try:
                    await chan.edit(name=channel_name)
                    logger.info(f"Renamed channel from #{chan.name} to #{channel_name}")
                except Exception as e:
                    logger.error(f"Failed to rename channel #{chan.name} to #{channel_name}: {e}")
        else:
            # @everyone hidden, Verified can see (read-only), Staff can manage
            verified_role = discord.utils.get(guild.roles, name=verified_role_name)
            staff_role = discord.utils.get(guild.roles, name=staff_role_name)
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False
                )
            }
            if verified_role:
                overwrites[verified_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    add_reactions=False,
                    read_message_history=True
                )
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_messages=True
                )
                
            try:
                chan = await guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    reason=f"Auto-creating channel for product: {name}"
                )
                logger.info(f"Created product channel: #{channel_name}")
            except Exception as e:
                logger.error(f"Failed to create channel {channel_name}: {e}")
                continue

        # Detect existing bot showcase embed message
        prod_msg = None
        async for m in chan.history(limit=15):
            if m.author == guild.me and m.embeds and m.embeds[0].title and name.upper() in m.embeds[0].title.upper():
                prod_msg = m
                break

        # Build detailed product embed
        features = prod.get("features", [])
        prices = prod.get("prices", [prod.get("price", "$0.00")])
        promo = prod.get("promotion", "")
        stock = prod.get("stock", "In Stock")
        gif_url = prod.get("gif_url", "")
        color_hex = prod.get("banner_color", "#ff3e3e")
        color = parse_color(color_hex)

        # Display emoji in title (supports custom Nitro emojis)
        display_emoji = emoji.strip() if emoji else "⚡"

        embed = discord.Embed(
            title=f"{display_emoji} {name.upper()}",
            description=(
                f"Welcome to the official showcase channel for **{name}**.\n"
                f"Here you can find detailed features, pricing options, and purchase instructions."
            ),
            color=color
        )

        features_text = "\n".join([f"✨ {f}" for f in features]) if features else "No features listed."
        embed.add_field(name="📋 Key Features", value=features_text, inline=False)

        prices_text = "\n".join([f"💵 `{p}`" for p in prices]) if prices else "No pricing listed."
        embed.add_field(name="💰 Pricing Plans", value=prices_text, inline=False)

        stock_emoji = "🟢"
        if "out" in stock.lower():
            stock_emoji = "🔴"
        elif "limit" in stock.lower() or "few" in stock.lower():
            stock_emoji = "🟡"
        embed.add_field(name="📦 Stock Level", value=f"{stock_emoji} **{stock}**", inline=True)

        if promo:
            embed.add_field(name="🔥 Active Promotion", value=f"🎉 **{promo}**", inline=True)

        embed.set_footer(text="🛒 Safe & Secure Payments • Instant Delivery via Ticket")

        # Buy button — supports custom Nitro emojis
        view = discord.ui.View(timeout=None)
        btn_emoji = None
        if emoji:
            emoji_str = emoji.strip()
            if emoji_str.startswith("<") and emoji_str.endswith(">"):
                match = re.match(r"<a?:([^:]+):([0-9]+)>", emoji_str)
                if match:
                    btn_emoji = discord.PartialEmoji(name=match.group(1), id=int(match.group(2)))
            else:
                btn_emoji = emoji_str

        btn = discord.ui.Button(
            label=f"Buy {name}",
            style=discord.ButtonStyle.success,
            emoji=btn_emoji or "🛒",
            custom_id=f"buy_prod_{slug}"
        )
        view.add_item(btn)

        try:
            if prod_msg:
                await prod_msg.edit(content=None, embed=embed, view=view)
            else:
                await chan.purge(limit=15, check=lambda m: m.author == guild.me)
                # Optional GIF banner above embed
                if gif_url:
                    try:
                        await chan.send(gif_url)
                    except Exception:
                        pass
                await chan.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Failed to post showcase embed in #{channel_name}: {e}")

    # Delete any channels in STORE category that are not valid (deprecated products)
    for ch in category.text_channels:
        ch_norm = normalize_name(ch.name)
        valid_norms = [normalize_name(n) for n in valid_channel_names]
        if ch_norm not in valid_norms:
            try:
                await ch.delete(reason="Deleting deprecated product channel.")
                logger.info(f"Deleted deprecated product channel: #{ch.name}")
            except Exception as e:
                logger.error(f"Failed to delete channel #{ch.name}: {e}")


class ProductSelectDropdown(discord.ui.Select):
    def __init__(self, products: List[Dict[str, Any]], action: str, config_data: dict):
        self.products = products
        self.action = action
        self.config_data = config_data
        
        options = []
        for prod in products:
            name = prod.get("name")
            prod_emoji = prod.get("emoji")
            
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
                value=name,
                emoji=emoji_obj or "🏷️"
            ))
            
        super().__init__(
            placeholder="Choose a product...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_name = self.values[0]
        selected_prod = None
        for p in self.products:
            if p["name"] == selected_name:
                selected_prod = p
                break
                
        if not selected_prod:
            await interaction.response.send_message("❌ Product not found.", ephemeral=True)
            return

        if self.action == "edit":
            modal = EditProductModal(selected_prod, self.config_data)
            await interaction.response.send_modal(modal)
        elif self.action == "stock":
            modal = UpdateStockModal(selected_prod, self.config_data)
            await interaction.response.send_modal(modal)
        elif self.action == "promo":
            modal = ManagePromotionModal(selected_prod, self.config_data)
            await interaction.response.send_modal(modal)


class AddProductModal(discord.ui.Modal, title="Add New Product"):
    name_input = discord.ui.TextInput(label="Product Name", placeholder="e.g. SilentAim Max", max_length=100)
    emoji_input = discord.ui.TextInput(label="Product Emoji", placeholder="e.g. 🎯, ⚡ or custom <:name:id> (leave blank for 🛒)", default="🛒", max_length=100, required=False)
    gif_input = discord.ui.TextInput(
        label="GIF URL (optional banner above post)",
        placeholder="e.g. https://media.giphy.com/media/.../giphy.gif",
        required=False,
        max_length=300
    )
    prices_input = discord.ui.TextInput(
        label="Pricing Options (Semicolon separated)", 
        style=discord.TextStyle.paragraph, 
        placeholder="e.g. 1 Day - 100 INR/$2; 30 Days - 1000 INR/$12; Lifetime - 2800 INR/$30",
        required=False,
        max_length=400
    )
    features_input = discord.ui.TextInput(
        label="Key Features (Semicolon separated)", 
        style=discord.TextStyle.paragraph, 
        placeholder="e.g. Aim Lock; No Recoil; ESP Box; Magic Bullet",
        max_length=400
    )

    def __init__(self, config_data: dict):
        super().__init__()
        self.config_data = config_data

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return
            
        name = self.name_input.value.strip()
        emoji = self.emoji_input.value.strip() or "🛒"
        gif_url = self.gif_input.value.strip() if self.gif_input.value else ""
        prices_raw = self.prices_input.value.strip()
        features_raw = self.features_input.value.strip()

        # Derive primary price from first pricing option
        price_list = [p.strip() for p in prices_raw.split(";") if p.strip()]
        price = price_list[0] if price_list else "See staff for pricing"

        new_prod = {
            "name": name,
            "emoji": emoji,
            "gif_url": gif_url,
            "price": price,
            "banner_color": "#ff3e3e",
            "features": [f.strip() for f in features_raw.split(";") if f.strip()],
            "prices": price_list if price_list else [price],
            "stock": "In Stock",
            "promotion": ""
        }

        products = await fetch_products_from_logs(guild)
        replaced = False
        for i, p in enumerate(products):
            if p["name"].lower().strip() == name.lower().strip():
                products[i] = new_prod
                replaced = True
                break
        if not replaced:
            products.append(new_prod)

        await save_products_to_logs(guild, products)
        await sync_product_channels(guild, products, self.config_data)
        await update_public_store_panel(guild, products, self.config_data)
        await update_seller_panel_message(guild, interaction.channel)

        action = "updated" if replaced else "added"
        await interaction.followup.send(f"✅ Product **{name}** has been successfully {action}!", ephemeral=True)


class EditProductModal(discord.ui.Modal):
    def __init__(self, product: Dict[str, Any], config_data: dict):
        super().__init__(title=f"Edit Product: {product.get('name')[:30]}")
        self.product = product
        self.config_data = config_data

        self.name_input = discord.ui.TextInput(
            label="Product Name", 
            default=product.get("name", ""), 
            max_length=100
        )
        self.emoji_input = discord.ui.TextInput(
            label="Product Emoji", 
            default=product.get("emoji", "🛒"), 
            placeholder="e.g. 🎯, ⚡ or custom <:name:id>", 
            max_length=100,
            required=False
        )
        self.gif_input = discord.ui.TextInput(
            label="GIF URL (optional)",
            default=product.get("gif_url", ""),
            placeholder="https://media.giphy.com/media/.../giphy.gif",
            required=False,
            max_length=300
        )
        self.prices_input = discord.ui.TextInput(
            label="Pricing Options (Semicolon separated)", 
            style=discord.TextStyle.paragraph, 
            default="; ".join(product.get("prices", [])),
            required=False,
            max_length=400
        )
        self.features_input = discord.ui.TextInput(
            label="Key Features (Semicolon separated)", 
            style=discord.TextStyle.paragraph, 
            default="; ".join(product.get("features", [])),
            max_length=400
        )

        self.add_item(self.name_input)
        self.add_item(self.emoji_input)
        self.add_item(self.gif_input)
        self.add_item(self.prices_input)
        self.add_item(self.features_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        old_name = self.product["name"]
        name = self.name_input.value.strip()
        emoji = self.emoji_input.value.strip() or "🛒"
        gif_url = self.gif_input.value.strip() if self.gif_input.value else self.product.get("gif_url", "")
        prices_raw = self.prices_input.value.strip()
        features_raw = self.features_input.value.strip()

        products = await fetch_products_from_logs(guild)
        for i, p in enumerate(products):
            if p["name"].lower().strip() == old_name.lower().strip():
                stock = p.get("stock", "In Stock")
                promo = p.get("promotion", "")
                banner_color = p.get("banner_color", "#ff3e3e")
                price_list = [pr.strip() for pr in prices_raw.split(";") if pr.strip()] if prices_raw else p.get("prices", [])
                price = price_list[0] if price_list else p.get("price", "See staff")
                
                products[i] = {
                    "name": name,
                    "emoji": emoji,
                    "gif_url": gif_url,
                    "price": price,
                    "banner_color": banner_color,
                    "features": [f.strip() for f in features_raw.split(";") if f.strip()],
                    "prices": price_list if price_list else [price],
                    "stock": stock,
                    "promotion": promo
                }
                break

        await save_products_to_logs(guild, products)
        await sync_product_channels(guild, products, self.config_data)
        await update_public_store_panel(guild, products, self.config_data)
        await update_seller_panel_message(guild, interaction.channel)

        await interaction.followup.send(f"✅ Product **{name}** details have been updated!", ephemeral=True)


class UpdateStockModal(discord.ui.Modal):
    def __init__(self, product: Dict[str, Any], config_data: dict):
        super().__init__(title=f"Stock for {product.get('name')[:30]}")
        self.product = product
        self.config_data = config_data

        self.stock_input = discord.ui.TextInput(
            label="Stock Level / Status",
            default=product.get("stock", "In Stock"),
            placeholder="e.g. In Stock, Out of Stock, 12 Keys Left",
            max_length=50
        )
        self.add_item(self.stock_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        stock_value = self.stock_input.value.strip()
        products = await fetch_products_from_logs(guild)
        for p in products:
            if p["name"].lower().strip() == self.product["name"].lower().strip():
                p["stock"] = stock_value
                break

        await save_products_to_logs(guild, products)
        await sync_product_channels(guild, products, self.config_data)
        await update_public_store_panel(guild, products, self.config_data)
        await update_seller_panel_message(guild, interaction.channel)

        await interaction.followup.send(f"✅ Stock for **{self.product['name']}** set to `{stock_value}`!", ephemeral=True)


class ManagePromotionModal(discord.ui.Modal):
    def __init__(self, product: Dict[str, Any], config_data: dict):
        super().__init__(title=f"Promo for {product.get('name')[:30]}")
        self.product = product
        self.config_data = config_data

        self.promo_input = discord.ui.TextInput(
            label="Promotion Tag (Leave blank to remove)",
            default=product.get("promotion", ""),
            placeholder="e.g. 10% OFF!, Special Offer, Double Glory",
            required=False,
            max_length=50
        )
        self.add_item(self.promo_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        promo_value = self.promo_input.value.strip()
        products = await fetch_products_from_logs(guild)
        for p in products:
            if p["name"].lower().strip() == self.product["name"].lower().strip():
                p["promotion"] = promo_value
                break

        await save_products_to_logs(guild, products)
        await sync_product_channels(guild, products, self.config_data)
        await update_public_store_panel(guild, products, self.config_data)
        await update_seller_panel_message(guild, interaction.channel)

        status = f"set to `{promo_value}`" if promo_value else "removed"
        await interaction.followup.send(f"✅ Promotion tag for **{self.product['name']}** has been {status}!", ephemeral=True)


class BroadcastModal(discord.ui.Modal, title="Publish Announcement"):
    title_input = discord.ui.TextInput(label="Announcement Title", placeholder="e.g. NEW CRACK RELEASED!", max_length=100)
    channel_input = discord.ui.TextInput(
        label="Target Channel (Name or ID)", 
        placeholder="e.g. ┃📢・announcements (leave blank for store-panel)", 
        required=False, 
        max_length=100
    )
    message_input = discord.ui.TextInput(
        label="Announcement Message", 
        style=discord.TextStyle.paragraph, 
        placeholder="Type details of your announcement here...",
        max_length=1500
    )
    color_input = discord.ui.TextInput(
        label="Banner Color",
        placeholder="e.g. #00ff00",
        required=False,
        max_length=7
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        title = self.title_input.value.strip()
        chan_val = self.channel_input.value.strip()
        message_text = self.message_input.value.strip()
        color_val = self.color_input.value.strip() or "#9b59b6"
        if color_val and not color_val.startswith("#"):
            color_val = f"#{color_val}"

        target_channel = None
        if chan_val:
            if chan_val.isdigit():
                target_channel = guild.get_channel(int(chan_val))
            if not target_channel:
                target_channel = discord.utils.get(guild.text_channels, name=chan_val)
            if not target_channel:
                for ch in guild.text_channels:
                    if chan_val.lower() in ch.name.lower():
                        target_channel = ch
                        break
        
        if not target_channel:
            for ch_name in ["┃📢・announcements", "announcements", "┃🛒・store-panel", "store-panel"]:
                target_channel = discord.utils.get(guild.text_channels, name=ch_name)
                if target_channel:
                    break

        if not target_channel:
            await interaction.followup.send("❌ Could not find a suitable channel to post the announcement.", ephemeral=True)
            return

        color = parse_color(color_val)
        embed = discord.Embed(
            title=f"📢 {title.upper()}",
            description=message_text,
            color=color,
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Published by {interaction.user.display_name}")
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

        try:
            await target_channel.send(embed=embed)
            await interaction.followup.send(f"✅ Announcement successfully published in {target_channel.mention}!", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to publish announcement: {e}")
            await interaction.followup.send(f"❌ Failed to send announcement: {e}", ephemeral=True)


class SellerControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Add Product",
        style=discord.ButtonStyle.primary,
        emoji="➕",
        custom_id="seller_btn_add_product"
    )
    async def add_product(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddProductModal(interaction.client.config_data if hasattr(interaction.client, "config_data") else {})
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Edit Product",
        style=discord.ButtonStyle.secondary,
        emoji="✏️",
        custom_id="seller_btn_edit_product"
    )
    async def edit_product(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        products = await fetch_products_from_logs(interaction.guild)
        if not products:
            await interaction.followup.send("❌ No products available to edit.", ephemeral=True)
            return

        view = discord.ui.View(timeout=60)
        view.add_item(ProductSelectDropdown(products, "edit", interaction.client.config_data if hasattr(interaction.client, "config_data") else {}))
        await interaction.followup.send("Select a product to edit:", view=view, ephemeral=True)

    @discord.ui.button(
        label="Update Stock",
        style=discord.ButtonStyle.secondary,
        emoji="📦",
        custom_id="seller_btn_update_stock"
    )
    async def update_stock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        products = await fetch_products_from_logs(interaction.guild)
        if not products:
            await interaction.followup.send("❌ No products available to update stock.", ephemeral=True)
            return

        view = discord.ui.View(timeout=60)
        view.add_item(ProductSelectDropdown(products, "stock", interaction.client.config_data if hasattr(interaction.client, "config_data") else {}))
        await interaction.followup.send("Select a product to update stock:", view=view, ephemeral=True)

    @discord.ui.button(
        label="Promotions",
        style=discord.ButtonStyle.success,
        emoji="🔥",
        custom_id="seller_btn_manage_promotions"
    )
    async def manage_promotions(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        products = await fetch_products_from_logs(interaction.guild)
        if not products:
            await interaction.followup.send("❌ No products available to manage promotions.", ephemeral=True)
            return

        view = discord.ui.View(timeout=60)
        view.add_item(ProductSelectDropdown(products, "promo", interaction.client.config_data if hasattr(interaction.client, "config_data") else {}))
        await interaction.followup.send("Select a product to apply promotion:", view=view, ephemeral=True)

    @discord.ui.button(
        label="Announcement",
        style=discord.ButtonStyle.danger,
        emoji="📢",
        custom_id="seller_btn_broadcast"
    )
    async def broadcast(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = BroadcastModal()
        await interaction.response.send_modal(modal)


async def setup_staff_resources(guild: discord.Guild, bot_config_data: dict):
    # Locate Staff category
    category = None
    for cat in guild.categories:
        if "STAFF" in cat.name.upper() or "👑" in cat.name:
            category = cat
            break

    # If no staff category exists, look for any category
    if not category:
        category = discord.utils.get(guild.categories, name="👑 STAFF")
        if not category:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False)
            }
            try:
                category = await guild.create_category(name="👑 STAFF", overwrites=overwrites, reason="Create Staff Category")
            except Exception as e:
                logger.error(f"Failed to create STAFF category: {e}")
                return

    ticket_cfg = bot_config_data.get("tickets", {}) if bot_config_data else {}
    staff_role_name = ticket_cfg.get("staff_role", "Staff")

    channel_name = "┃📌・staff-resources"
    chan = None
    for ch in category.text_channels:
        if ch.name.lower() == channel_name.lower() or "staff-resources" in ch.name.lower():
            chan = ch
            break

    if not chan:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False)
        }
        staff_role = discord.utils.get(guild.roles, name=staff_role_name)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False, add_reactions=False)
        
        for r in guild.roles:
            if r.permissions.administrator:
                overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        try:
            chan = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason="Creating staff resources channel"
            )
        except Exception as e:
            logger.error(f"Failed to create channel {channel_name}: {e}")
            return

    # Post or edit the staff resources guide
    guide_msg = None
    async for m in chan.history(limit=20):
        if m.author == guild.me and m.embeds and "STAFF COMMANDS GUIDE" in m.embeds[0].title:
            guide_msg = m
            break

    embed = discord.Embed(
        title="🛠️ STAFF COMMANDS GUIDE & RESOURCES",
        description="Welcome to the staff resources channel. Below is the list of all AI and staff-related administrative commands available in FAIZxCHEATS.",
        color=discord.Color.purple(),
        timestamp=discord.utils.utcnow()
    )

    embed.add_field(
        name="🤖 AI Commands (OWNER ONLY)",
        value="• `/agent-run <task>`: Commands the autonomous AI agent to perform server administration tasks.\n"
              "• `/ai-build <prompt>`: Automatically design and reconstruct the entire server layout.",
        inline=False
    )

    embed.add_field(
        name="👑 Store Seller Panel",
        value="• `/seller-panel`: Deploys the interactive Seller Management Panel to add/edit products, stock, promotions, and announcements.",
        inline=False
    )

    embed.add_field(
        name="🛒 Store Catalog Commands",
        value="• `/add-product <name> <price> <features> [color] [prices]`: Add/update a product.\n"
              "• `/delete-product <name>`: Delete a product.",
        inline=False
    )

    embed.add_field(
        name="⭐ Customer Reviews",
        value="• `/review-stats`: Manually refreshes the customer reviews statistics card.",
        inline=False
    )

    embed.add_field(
        name="🛡️ Scam & Raid Protection Buttons",
        value="• Interactive buttons (**Ban**, **Kick**, **Dismiss**) are attached to all staff security alerts for instant moderation.",
        inline=False
    )

    embed.set_footer(text="FAIzxCHEATS Staff Resources • Private & Confidential")
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)

    try:
        if guide_msg:
            await guide_msg.edit(embed=embed)
        else:
            await chan.purge(limit=10, check=lambda m: m.author == guild.me)
            await chan.send(embed=embed)
            logger.info("Posted staff resources commands guide.")
    except Exception as e:
        logger.error(f"Failed to post staff resources guide: {e}")
