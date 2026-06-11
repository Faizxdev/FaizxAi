import discord
import io
import datetime
import random
import string
from typing import Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont
from src.utils.logger import setup_logger

logger = setup_logger("onboarding_manager")

# In-memory session tracking for security
captcha_sessions: Dict[int, str] = {}    # user_id -> captcha_code
attempts_count: Dict[int, int] = {}      # user_id -> failed_attempts_count
cooldowns: Dict[int, datetime.datetime] = {}  # user_id -> cooldown_expiry_time

class CaptchaGenerator:
    @staticmethod
    def generate_code(length: int = 5) -> str:
        # Avoid confusing characters like O, 0, I, 1, L
        chars = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1IL")
        return "".join(random.choice(chars) for _ in range(length))

    @staticmethod
    def generate_image(text: str) -> io.BytesIO:
        width, height = 220, 80
        image = Image.new("RGB", (width, height), color=(245, 245, 245))
        draw = ImageDraw.Draw(image)
        
        # Load a standard font, fallback if missing
        font = None
        font_paths = [
            "C:\\Windows\\Fonts\\Arial.ttf",
            "C:\\Windows\\Fonts\\consola.ttf",
            "C:\\Windows\\Fonts\\tahoma.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "arial.ttf"
        ]
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, 36)
                break
            except Exception:
                continue
                
        if not font:
            font = ImageFont.load_default()
            
        # Draw background noise lines
        for _ in range(12):
            x1 = random.randint(0, width)
            y1 = random.randint(0, height)
            x2 = random.randint(0, width)
            y2 = random.randint(0, height)
            color = (random.randint(120, 200), random.randint(120, 200), random.randint(120, 200))
            draw.line((x1, y1, x2, y2), fill=color, width=random.randint(1, 2))
            
        # Draw text characters
        char_w = width // (len(text) + 1)
        for i, char in enumerate(text):
            x = 15 + i * char_w + random.randint(-4, 4)
            y = 20 + random.randint(-6, 6)
            color = (random.randint(20, 100), random.randint(20, 100), random.randint(20, 100))
            draw.text((x, y), char, fill=color, font=font)
            
        # Draw noise points
        for _ in range(150):
            x = random.randint(0, width)
            y = random.randint(0, height)
            color = (random.randint(100, 180), random.randint(100, 180), random.randint(100, 180))
            draw.point((x, y), fill=color)
            
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        return buf

async def log_verification_event(guild: discord.Guild, member: discord.Member, status: str, details: str):
    # Try finding verification logs, fallback to staff logs or general logs
    log_channel = discord.utils.get(guild.text_channels, name="verification-logs")
    if not log_channel:
        log_channel = discord.utils.get(guild.text_channels, name="┃📊・staff-logs")
    if not log_channel:
        for ch in guild.text_channels:
            if "LOG" in ch.name.upper() or "📊" in ch.name:
                log_channel = ch
                break
                
    if log_channel:
        embed = discord.Embed(
            title="🔒 Verification Log",
            color=discord.Color.green() if "Success" in status else discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
        embed.add_field(name="User", value=f"{member.mention} ({member.name})", inline=True)
        embed.add_field(name="User ID", value=member.id, inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Details", value=details, inline=False)
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to write verification log: {e}")

class CaptchaModal(discord.ui.Modal, title="Submit Captcha Verification Code"):
    code_input = discord.ui.TextInput(
        label="Enter Captcha Code (Case Insensitive)",
        placeholder="Type the 5-character code shown in the image...",
        min_length=5,
        max_length=5,
        required=True
    )

    def __init__(self, expected_code: str, verified_role_name: str, unverified_role_name: Optional[str] = None):
        super().__init__()
        self.expected_code = expected_code
        self.verified_role_name = verified_role_name
        self.unverified_role_name = unverified_role_name

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        
        user_input = self.code_input.value.strip().upper()
        user_id = member.id
        
        if user_input == self.expected_code:
            verified_role = discord.utils.get(guild.roles, name=self.verified_role_name)
            unverified_role = discord.utils.get(guild.roles, name=self.unverified_role_name) if self.unverified_role_name else None
            
            captcha_sessions.pop(user_id, None)
            attempts_count.pop(user_id, None)
            cooldowns.pop(user_id, None)
            
            try:
                if verified_role:
                    await member.add_roles(verified_role, reason="Verification Captcha completed successfully")
                if unverified_role:
                    await member.remove_roles(unverified_role, reason="Verification Captcha completed successfully")
                    
                await interaction.followup.send("🎉 **Verification Successful!** You have been granted access to the server.", ephemeral=True)
                await log_verification_event(guild, member, "Success", f"Verification complete. Captcha: {self.expected_code}")
            except Exception as e:
                logger.error(f"Error assigning role to {member.name}: {e}")
                await interaction.followup.send("❌ An error occurred assigning roles. Please contact staff.", ephemeral=True)
        else:
            from src.core.security_manager import total_verification_failures
            total_fails = total_verification_failures.get(user_id, 0) + 1
            total_verification_failures[user_id] = total_fails

            attempts = attempts_count.get(user_id, 0) + 1
            attempts_count[user_id] = attempts
            
            if attempts >= 3:
                cooldown_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
                cooldowns[user_id] = cooldown_time
                attempts_count.pop(user_id, None)
                captcha_sessions.pop(user_id, None)
                
                await interaction.followup.send(
                    "❌ **Verification Failed**: You entered the wrong code 3 times. "
                    "You have been placed on a **5-minute cooldown** before you can try again.",
                    ephemeral=True
                )
                await log_verification_event(guild, member, "Blocked (Cooldown)", f"Failed captcha 3 times. Placing on cooldown. User code: {user_input}, Captcha: {self.expected_code}")
            else:
                new_code = CaptchaGenerator.generate_code()
                captcha_sessions[user_id] = new_code
                buf = CaptchaGenerator.generate_image(new_code)
                file = discord.File(buf, filename="captcha.png")
                
                embed = discord.Embed(
                    title="Captcha Code Mismatched!",
                    description=f"❌ You entered the wrong code. You have **{3 - attempts} attempts** remaining.\n"
                                f"Please submit the new code shown below.",
                    color=discord.Color.red()
                )
                embed.set_image(url="attachment://captcha.png")
                
                view = CaptchaSubmitView(new_code, self.verified_role_name, self.unverified_role_name)
                await interaction.followup.send(embed=embed, file=file, view=view, ephemeral=True)
                await log_verification_event(guild, member, "Failed Attempt", f"Incorrect captcha attempt. Entered: {user_input}, Expected: {self.expected_code}. Attempts remaining: {3 - attempts}")

class CaptchaSubmitView(discord.ui.View):
    def __init__(self, code: str, verified_role_name: str, unverified_role_name: Optional[str] = None):
        super().__init__(timeout=120)
        self.code = code
        self.verified_role_name = verified_role_name
        self.unverified_role_name = unverified_role_name

    @discord.ui.button(label="Submit Code", style=discord.ButtonStyle.primary, emoji="✏️", custom_id="submit_captcha_code")
    async def submit_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CaptchaModal(self.code, self.verified_role_name, self.unverified_role_name)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Regenerate", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="regenerate_captcha")
    async def regenerate_captcha(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        if user_id in cooldowns:
            now = datetime.datetime.now(datetime.timezone.utc)
            if now < cooldowns[user_id]:
                rem = (cooldowns[user_id] - now).seconds // 60
                await interaction.followup.send(f"❌ You are on cooldown. Please wait {rem + 1} minute(s) before trying again.", ephemeral=True)
                return
            else:
                cooldowns.pop(user_id, None)

        new_code = CaptchaGenerator.generate_code()
        captcha_sessions[user_id] = new_code
        
        buf = CaptchaGenerator.generate_image(new_code)
        file = discord.File(buf, filename="captcha.png")
        
        embed = discord.Embed(
            title="Verification Captcha Challenge",
            description="Type the 5-character code shown below to complete your verification.",
            color=discord.Color.blurple()
        )
        embed.set_image(url="attachment://captcha.png")
        
        view = CaptchaSubmitView(new_code, self.verified_role_name, self.unverified_role_name)
        await interaction.followup.send(embed=embed, file=file, view=view, ephemeral=True)

class VerificationView(discord.ui.View):
    def __init__(self, verified_role_name: str, unverified_role_name: Optional[str] = None):
        super().__init__(timeout=None)
        self.verified_role_name = verified_role_name
        self.unverified_role_name = unverified_role_name

    @discord.ui.button(label="Verify Here", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify_button")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            return

        # 0. Check if already verified
        verified_role = discord.utils.get(guild.roles, name=self.verified_role_name)
        if verified_role and verified_role in member.roles:
            await interaction.followup.send("❌ **Already Verified**: You have already verified and have full access to the server!", ephemeral=True)
            return

        user_id = member.id

        # 1. Cooldown Check
        if user_id in cooldowns:
            now = datetime.datetime.now(datetime.timezone.utc)
            if now < cooldowns[user_id]:
                rem = (cooldowns[user_id] - now).seconds // 60
                await interaction.followup.send(f"❌ You are on cooldown. Please wait {rem + 1} minute(s) before trying again.", ephemeral=True)
                return
            else:
                cooldowns.pop(user_id, None)

        # 1.5. Repeated Failures Gate check
        from src.core.security_manager import total_verification_failures
        if total_verification_failures.get(user_id, 0) >= 5:
            await interaction.followup.send(
                "❌ **Verification Locked**: You have failed captcha verification too many times (5+ times). "
                "For security reasons, your account has been locked from verification. Please contact staff to verify manually.",
                ephemeral=True
            )
            return

        # 2. Account Age Check (Min 7 days)
        min_age_days = 7
        user_age = (discord.utils.utcnow() - member.created_at).days
        if user_age < min_age_days:
            await interaction.followup.send(
                f"❌ **Verification Denied**: Your account must be at least **{min_age_days} days** old. "
                f"Your current account age is only **{user_age} days**.",
                ephemeral=True
            )
            await log_verification_event(guild, member, "Denied", f"Account age check failed. Age: {user_age} days (Min: {min_age_days})")
            return

        # 3. Generate Captcha Challenge
        code = CaptchaGenerator.generate_code()
        captcha_sessions[user_id] = code
        
        buf = CaptchaGenerator.generate_image(code)
        file = discord.File(buf, filename="captcha.png")
        
        embed = discord.Embed(
            title="Verification Captcha Challenge",
            description="Type the 5-character code shown below to complete your verification.\n"
                        "Click **Submit Code** to enter the captcha. If the image is hard to read, click **Regenerate**.",
            color=discord.Color.blurple()
        )
        embed.set_image(url="attachment://captcha.png")
        
        view = CaptchaSubmitView(code, self.verified_role_name, self.unverified_role_name)
        await interaction.followup.send(embed=embed, file=file, view=view, ephemeral=True)
        await log_verification_event(guild, member, "Challenge Initiated", f"Prompted captcha challenge. Expected code: {code}")


class TicketControlView(discord.ui.View):
    def __init__(self, staff_role_name: str, log_channel_name: str):
        super().__init__(timeout=None)
        self.staff_role_name = staff_role_name
        self.log_channel_name = log_channel_name

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.primary, emoji="🙋‍♂️", custom_id="claim_ticket_button")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild or not isinstance(interaction.user, discord.Member):
            return

        # Check if staff
        staff_role = discord.utils.get(guild.roles, name=self.staff_role_name)
        if staff_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only support staff can claim tickets.", ephemeral=True)
            return

        await interaction.response.defer()
        
        # Disable claim button
        button.disabled = True
        button.label = f"Claimed by {interaction.user.display_name}"
        await interaction.message.edit(view=self)
        
        # Update ticket channel permissions
        channel = interaction.channel
        if isinstance(channel, discord.TextChannel):
            # Remove staff role general access and lock to claiming user
            await channel.set_permissions(interaction.user, read_messages=True, send_messages=True, reason="Ticket claimed")
            
            # Find the ticket creator (the member who was previously denied send_messages) and grant them messaging permissions
            for target, overwrite in channel.overwrites.items():
                if isinstance(target, discord.Member) and not target.bot and target != interaction.user:
                    overwrite.send_messages = True
                    await channel.set_permissions(target, overwrite=overwrite, reason="Ticket claimed - enabling creator messaging")
            
            await channel.send(f"Ticket has been claimed by {interaction.user.mention}. The channel is now unlocked for chat.")

            # Log claim
            log_chan = discord.utils.get(guild.text_channels, name=self.log_channel_name)
            if log_chan:
                embed = discord.Embed(
                    title="Ticket Claimed",
                    description=f"Ticket {channel.mention} claimed by {interaction.user.mention}.",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                await log_chan.send(embed=embed)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket_button")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        channel = interaction.channel
        if not guild or not channel or not isinstance(interaction.user, discord.Member):
            return

        # Check if staff or administrator
        staff_role = discord.utils.get(guild.roles, name=self.staff_role_name)
        is_staff = staff_role in interaction.user.roles if staff_role else False
        if not is_staff and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only support staff or administrators can close tickets.", ephemeral=True)
            return

        await interaction.response.send_message("Closing ticket and exporting transcript...", ephemeral=True)

        try:
            # Generate Transcript
            messages = []
            async for msg in channel.history(limit=None, oldest_first=True):
                time_str = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                messages.append(f"[{time_str}] {msg.author.name}#{msg.author.discriminator or '0000'} ({msg.author.id}): {msg.content}")
            
            transcript_text = "\n".join(messages)
            file_data = io.BytesIO(transcript_text.encode("utf-8"))
            discord_file = discord.File(file_data, filename=f"transcript-{channel.name}.txt")

            # Send transcript to log channel
            log_chan = discord.utils.get(guild.text_channels, name=self.log_channel_name)
            if log_chan:
                embed = discord.Embed(
                    title="Ticket Closed",
                    description=f"Ticket `{channel.name}` has been closed by {interaction.user.mention}.",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="Channel ID", value=channel.id)
                await log_chan.send(embed=embed, file=discord_file)

            # Delete channel
            await channel.delete(reason="Ticket closed")
        except Exception as e:
            logger.error(f"Error closing ticket channel {channel.name}: {e}")


class TicketPanelView(discord.ui.View):
    def __init__(self, staff_role_name: str, log_channel_name: str, category_name: str, ticket_types: List[Dict[str, Any]]):
        super().__init__(timeout=None)
        self.staff_role_name = staff_role_name
        self.log_channel_name = log_channel_name
        self.category_name = category_name
        self.ticket_types = ticket_types

        # Dynamically add buttons based on ticket types
        for idx, t_type in enumerate(self.ticket_types):
            name = t_type.get("name", "Support")
            custom_id = t_type.get("custom_id", f"ticket_btn_{idx}")
            emoji = t_type.get("emoji")
            
            # We construct a custom button handler for each type
            btn = discord.ui.Button(
                label=name,
                style=discord.ButtonStyle.primary,
                emoji=emoji,
                custom_id=custom_id
            )
            # Bind the callback
            btn.callback = self.make_callback(name, custom_id)
            self.add_item(btn)

    def make_callback(self, ticket_type_name: str, custom_id: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            user = interaction.user
            if not guild or not user:
                return

            # Resolve Category where ticket is created
            category = discord.utils.get(guild.categories, name=self.category_name)
            
            # Resolve roles
            staff_role = discord.utils.get(guild.roles, name=self.staff_role_name)
            
            # Create channel overrides: User and Staff get access, @everyone hidden, user restricted from sending messages until claimed
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True),
            }
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            channel_name = f"{ticket_type_name.lower().replace(' ', '-')}-{user.name}"
            
            try:
                ticket_channel = await guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    reason=f"Ticket created for {user.name}"
                )
                await interaction.followup.send(f"Ticket created! Access it here: {ticket_channel.mention}", ephemeral=True)

                # Send welcome message inside ticket channel
                embed = discord.Embed(
                    title=f"{ticket_type_name} Opened",
                    description=f"Welcome {user.mention}. Support will be with you shortly.\n"
                                f"Press **Claim Ticket** to lock the ticket to yourself (Staff only).\n"
                                f"Press **Close Ticket** to close the ticket and generate a transcript.",
                    color=discord.Color.blurple(),
                    timestamp=discord.utils.utcnow()
                )
                
                control_view = TicketControlView(self.staff_role_name, self.log_channel_name)
                await ticket_channel.send(content=f"{user.mention} Welcome! {staff_role.mention if staff_role else ''}", embed=embed, view=control_view)

                # Log ticket creation
                log_chan = discord.utils.get(guild.text_channels, name=self.log_channel_name)
                if log_chan:
                    log_embed = discord.Embed(
                        title="Ticket Created",
                        description=f"Ticket {ticket_channel.mention} created by {user.mention}.",
                        color=discord.Color.green(),
                        timestamp=discord.utils.utcnow()
                    )
                    log_embed.add_field(name="Ticket Type", value=ticket_type_name)
                    log_embed.add_field(name="User ID", value=user.id)
                    await log_chan.send(embed=log_embed)
            except Exception as e:
                logger.error(f"Failed to create ticket channel: {e}")
                await interaction.followup.send("Failed to create ticket channel. Admin help needed.", ephemeral=True)
                
        return callback


class OnboardingManager:
    def __init__(self, guild: discord.Guild):
        self.guild = guild

    async def setup_verification(self, config: Dict[str, Any]) -> None:
        """Sets up the verification channel, embed, and persistent verify button."""
        channel_name = config.get("channel", "┃🔒・verify")
        verified_role_name = config.get("verified_role", "Verified")
        unverified_role_name = config.get("unverified_role", "Unverified")
        embed_data = config.get("embed", {})
        
        # Check if any channel matches verify
        channel = None
        for ch in self.guild.text_channels:
            if "verify" in ch.name.lower() or "verification" in ch.name.lower() or "🔒" in ch.name:
                # Do not match staff logs or active ticket channels
                if not any(term in ch.name.lower() for term in ["log", "staff", "admin", "mod", "ticket"]):
                    channel = ch
                    break
                    
        if not channel:
            # Automatically create verification channel if missing
            category = discord.utils.get(self.guild.categories, name="🌸 ENTRANCE")
            if not category:
                for cat in self.guild.categories:
                    if "ENTRANCE" in cat.name.upper() or "WELCOME" in cat.name.upper():
                        category = cat
                        break
            overwrites = {
                self.guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
            }
            channel = await self.guild.create_text_channel(
                name="┃🔒・verify",
                category=category,
                overwrites=overwrites,
                reason="Verification channel created automatically"
            )
            logger.info(f"Created missing verification channel #┃🔒・verify")

        # === UNIVERSAL LOCKDOWN ===
        # Hide EVERY category from @everyone.
        # Only the verify channel will be explicitly visible to @everyone.
        verified_role = discord.utils.get(self.guild.roles, name=verified_role_name)

        for cat in self.guild.categories:
            cat_name = cat.name.upper()
            is_staff_cat = "STAFF" in cat_name

            # Always deny view_channel for @everyone on every category
            overwrite_everyone = cat.overwrites_for(self.guild.default_role)
            overwrite_everyone.view_channel = False
            try:
                await cat.set_permissions(
                    self.guild.default_role, overwrite=overwrite_everyone,
                    reason="Universal lockdown: Hide all categories from @everyone"
                )
            except Exception as e:
                logger.warning(f"Could not set @everyone perms on category '{cat.name}': {e}")

            # Give Verified role access to all non-STAFF categories
            if verified_role and not is_staff_cat:
                overwrite_verified = cat.overwrites_for(verified_role)
                overwrite_verified.view_channel = True
                try:
                    await cat.set_permissions(
                        verified_role, overwrite=overwrite_verified,
                        reason="Verification Security: Grant Verified role access to category"
                    )
                except Exception as e:
                    logger.warning(f"Could not set Verified perms on category '{cat.name}': {e}")

        # Explicitly make the verify channel visible to @everyone (override category lockdown)
        try:
            await channel.set_permissions(
                self.guild.default_role,
                view_channel=True,
                send_messages=False,
                reason="Verify channel must be visible to everyone"
            )
        except Exception as e:
            logger.warning(f"Could not expose verify channel to @everyone: {e}")

        # Purge previous verification messages to prevent duplicate panels
        try:
            already_posted = False
            async for msg in channel.history(limit=50):
                if msg.author == self.guild.me and msg.embeds and msg.embeds[0].title == embed_data.get("title", "Verify Here"):
                    already_posted = True
                    break
            
            if already_posted:
                logger.info("Verification embed already posted. Skipping.")
                return

            await channel.purge(limit=10, check=lambda m: m.author == self.guild.me)
        except Exception as e:
            logger.warning(f"Could not check history or purge verification channel: {e}")

        # Post embed and view
        title = embed_data.get("title", "Verify Here")
        desc = embed_data.get("description", "Click the button below to verify your account and get access.")
        color_hex = embed_data.get("color", "#2ecc71")
        color = parse_color(color_hex)

        embed = discord.Embed(title=title, description=desc, color=color)
        view = VerificationView(verified_role_name, unverified_role_name)
        
        try:
            await channel.send(embed=embed, view=view)
            logger.info("Verification embed and button setup complete.")
        except Exception as e:
            logger.error(f"Failed to send verification embed: {e}")

    async def setup_ticket_system(self, config: Dict[str, Any]) -> None:
        """Sets up the ticket panel channel, embed, and buttons for different tickets."""
        channel_name = config.get("channel", "create-ticket")
        category_name = config.get("category", "Support")
        staff_role_name = config.get("staff_role", "Support Team")
        log_channel_name = config.get("log_channel", "ticket-logs")
        embed_data = config.get("embed", {})
        ticket_types = config.get("types", [])

        channel = discord.utils.get(self.guild.text_channels, name=channel_name)
        if not channel:
            logger.warning(f"Ticket channel '{channel_name}' not found. Skipping ticket setup.")
            return

        # Clean/Check history for existing panel
        try:
            already_posted = False
            async for msg in channel.history(limit=50):
                if msg.author == self.guild.me and msg.embeds and msg.embeds[0].title == embed_data.get("title", "Create a Ticket"):
                    already_posted = True
                    break
            
            if already_posted:
                logger.info("Ticket panel embed already posted. Skipping.")
                return

            await channel.purge(limit=10, check=lambda m: m.author == self.guild.me)
        except Exception as e:
            logger.warning(f"Could not check history or purge ticket channel: {e}")

        title = embed_data.get("title", "Create a Ticket")
        desc = embed_data.get("description", "Click the button corresponding to your issue type to open a private ticket.")
        color_hex = embed_data.get("color", "#3498db")
        color = parse_color(color_hex)

        embed = discord.Embed(title=title, description=desc, color=color)
        view = TicketPanelView(staff_role_name, log_channel_name, category_name, ticket_types)
        
        try:
            await channel.send(embed=embed, view=view)
            logger.info("Ticket panel embed and buttons setup complete.")
        except Exception as e:
            logger.error(f"Failed to send ticket panel embed: {e}")

def parse_color(color_hex: Optional[str]) -> discord.Color:
    if not color_hex:
        return discord.Color.blurple()
    color_hex = color_hex.lstrip("#")
    try:
        return discord.Color(int(color_hex, 16))
    except ValueError:
        return discord.Color.blurple()

async def apply_channel_lockdown(guild: discord.Guild, config_data: dict) -> str:
    """
    Full lockdown:
    1. Every category → @everyone view_channel=False, Verified view_channel=True (non-staff)
    2. Every individual text/voice channel → REMOVE @everyone overwrite so it inherits the
       locked category. Channel-level overwrites beat category, so we MUST clear them.
    3. Verify channel gets an explicit @everyone view_channel=True to punch through.
    Safe to call on every bot startup.
    """
    verification_cfg = config_data.get("verification", {}) if config_data else {}
    verified_role_name = verification_cfg.get("verified_role", "Verified")
    verified_role = discord.utils.get(guild.roles, name=verified_role_name)

    # Find verify channel first so we can skip it during channel scrubbing
    verify_chan = None
    for ch in guild.text_channels:
        ch_name = ch.name.lower()
        if ("verify" in ch_name or "🔒" in ch.name) and not any(
            t in ch_name for t in ["log", "staff", "admin", "mod", "ticket"]
        ):
            verify_chan = ch
            break

    cats_locked = 0
    cats_verified = 0
    chans_scrubbed = 0

    for cat in guild.categories:
        cat_name = cat.name.upper()
        is_staff_cat = "STAFF" in cat_name

        # ── Step 1: Lock the CATEGORY for @everyone ──────────────────────────
        try:
            ow_cat_everyone = cat.overwrites_for(guild.default_role)
            ow_cat_everyone.view_channel = False
            await cat.set_permissions(
                guild.default_role, overwrite=ow_cat_everyone,
                reason="Lockdown: hide category from @everyone"
            )
            cats_locked += 1
        except Exception as e:
            logger.warning(f"Lockdown: cat @everyone fail '{cat.name}': {e}")

        # ── Step 2: Grant category to Verified (non-staff only) ───────────────
        if verified_role and not is_staff_cat:
            try:
                ow_cat_verified = cat.overwrites_for(verified_role)
                ow_cat_verified.view_channel = True
                await cat.set_permissions(
                    verified_role, overwrite=ow_cat_verified,
                    reason="Lockdown: grant Verified role category access"
                )
                cats_verified += 1
            except Exception as e:
                logger.warning(f"Lockdown: cat Verified fail '{cat.name}': {e}")

        # ── Step 3: Scrub @everyone overwrite from EVERY channel in this cat ──
        # Without this, channel-level @everyone=True overrides the category lock.
        all_channels = list(cat.text_channels) + list(cat.voice_channels)
        for ch in all_channels:
            if ch == verify_chan:
                continue  # skip — we'll handle it separately below

            try:
                # Remove explicit @everyone overwrite → channel inherits from category
                ow_ch = ch.overwrites_for(guild.default_role)
                if ow_ch.view_channel is not None:
                    ow_ch.view_channel = None  # neutral = inherit from category
                    await ch.set_permissions(
                        guild.default_role, overwrite=ow_ch if any(
                            v is not None for _, v in ow_ch
                        ) else None,
                        reason="Lockdown: clear channel @everyone overwrite (inherit category)"
                    )
                    chans_scrubbed += 1
            except Exception as e:
                logger.warning(f"Lockdown: chan scrub fail '#{ch.name}': {e}")

            # Also make sure Verified role has access at channel level if it had an explicit deny
            if verified_role and not is_staff_cat:
                try:
                    ow_ch_ver = ch.overwrites_for(verified_role)
                    if ow_ch_ver.view_channel is False:
                        ow_ch_ver.view_channel = None  # let category handle it
                        await ch.set_permissions(
                            verified_role, overwrite=ow_ch_ver,
                            reason="Lockdown: clear Verified deny on channel"
                        )
                except Exception:
                    pass

    # ── Step 4: Verify channel — explicitly visible to @everyone ─────────────
    if verify_chan:
        try:
            await verify_chan.set_permissions(
                guild.default_role,
                view_channel=True,
                send_messages=False,
                reason="Lockdown: verify channel pinned visible to @everyone"
            )
            logger.info(f"Lockdown: Verify channel '#{verify_chan.name}' visible to @everyone.")
        except Exception as e:
            logger.warning(f"Lockdown: Could not expose verify channel: {e}")

    summary = (
        f"✅ Lockdown applied:\n"
        f"• `{cats_locked}` categories hidden from `@everyone`\n"
        f"• `{cats_verified}` categories granted to `{verified_role_name}` role\n"
        f"• `{chans_scrubbed}` channels had their @everyone overwrite cleared\n"
        f"• Verify channel: {'visible ✅' if verify_chan else 'NOT FOUND ⚠️'}"
    )
    logger.info(f"Channel lockdown complete: {cats_locked} cats, {chans_scrubbed} chans scrubbed.")
    return summary
