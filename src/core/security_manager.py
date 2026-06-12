import discord
import datetime
from typing import Dict, List, Optional, Any
from src.utils.logger import setup_logger

logger = setup_logger("security_manager")

# In-memory tracking for raid protection
join_timestamps: List[datetime.datetime] = []
lockdown_until: Optional[datetime.datetime] = None

# In-memory tracking for repeated verification failures
# user_id -> total_failed_verifications_count
total_verification_failures: Dict[int, int] = {}

class SecurityAlertView(discord.ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id
        
        # Dynamically set custom_ids for persistence tracking in on_interaction
        self.ban_btn.custom_id = f"sec_ban_{target_user_id}"
        self.kick_btn.custom_id = f"sec_kick_{target_user_id}"
        self.dismiss_btn.custom_id = f"sec_dismiss_{target_user_id}"

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass # Handled dynamically in on_interaction for persistence

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.secondary, emoji="👢")
    async def kick_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass # Handled dynamically in on_interaction for persistence

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.success, emoji="✅")
    async def dismiss_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass # Handled dynamically in on_interaction for persistence


class SecurityManager:
    def __init__(self, guild: discord.Guild):
        self.guild = guild

    async def get_staff_logs_channel(self) -> Optional[discord.TextChannel]:
        """Resolves the staff logs channel."""
        chan = discord.utils.get(self.guild.text_channels, name="┃📊・staff-logs")
        if not chan:
            for ch in self.guild.text_channels:
                if "LOG" in ch.name.upper() or "📊" in ch.name:
                    chan = ch
                    break
        return chan

    def check_raid(self) -> bool:
        """Checks if a raid is occurring based on join frequency (joins > 5 in 10 seconds)."""
        global lockdown_until
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Lift lockdown if time expired
        if lockdown_until and now > lockdown_until:
            lockdown_until = None
            logger.info("Raid protection lockdown automatically lifted.")
            
        if lockdown_until:
            return True

        # Append current join
        join_timestamps.append(now)
        
        # Clean timestamps older than 10 seconds
        ten_seconds_ago = now - datetime.timedelta(seconds=10)
        while join_timestamps and join_timestamps[0] < ten_seconds_ago:
            join_timestamps.pop(0)

        # Trigger lockdown if joins exceed limit
        if len(join_timestamps) >= 5:
            lockdown_until = now + datetime.timedelta(minutes=2)
            logger.warning(f"Raid detected! Lockdown active until {lockdown_until.isoformat()}")
            return True
            
        return False

    async def evaluate_member(self, member: discord.Member) -> Dict[str, Any]:
        """
        Evaluates a newly joined member for security risks.
        Returns a dictionary containing risk status and details.
        """
        reasons = []
        is_risky = False
        risk_level = "LOW"
        
        # 1. Check account age (alt account detection)
        account_age_days = (discord.utils.utcnow() - member.created_at).days
        if account_age_days < 7:
            reasons.append(f"🚨 **Critical Alt**: Account age is only **{account_age_days} days**.")
            is_risky = True
            risk_level = "CRITICAL"
        elif account_age_days < 30:
            reasons.append(f"⚠️ **Suspicious Alt**: Account age is **{account_age_days} days**.")
            is_risky = True
            risk_level = "MEDIUM"

        # 2. Check default avatar
        if member.avatar is None:
            reasons.append("🖼️ **Default Avatar**: User has no custom profile picture.")
            is_risky = True
            if risk_level != "CRITICAL":
                risk_level = "MEDIUM"

        # 3. Check suspicious username
        name_lower = member.name.lower()
        suspicious_terms = ["nitro", "free", "gift", "selling", "promote", "invite", "steam"]
        for term in suspicious_terms:
            if term in name_lower:
                reasons.append(f"🔤 **Suspicious Username**: Username contains term **'{term}'**.")
                is_risky = True
                risk_level = "CRITICAL"
                break

        # 4. Check for invite link in display name
        if "discord.gg/" in member.display_name.lower():
            reasons.append("🔗 **Advertising Name**: Display name contains a Discord invite link.")
            is_risky = True
            risk_level = "CRITICAL"

        # 5. Check if repeated verification failures exist
        total_fails = total_verification_failures.get(member.id, 0)
        if total_fails >= 5:
            reasons.append(f"❌ **Repeated Verification Failures**: Failed captcha **{total_fails} times**.")
            is_risky = True
            risk_level = "CRITICAL"

        return {
            "is_risky": is_risky,
            "risk_level": risk_level,
            "reasons": reasons,
            "account_age": account_age_days
        }

    async def handle_suspicious_member(self, member: discord.Member, evaluation: Dict[str, Any]) -> None:
        """Sends an interactive alert card to the staff logs channel."""
        staff_logs = await self.get_staff_logs_channel()
        if not staff_logs:
            logger.warning("Could not find staff logs channel to post security alert.")
            return

        risk_colors = {
            "CRITICAL": discord.Color.red(),
            "MEDIUM": discord.Color.orange(),
            "LOW": discord.Color.gold()
        }
        color = risk_colors.get(evaluation["risk_level"], discord.Color.gold())

        embed = discord.Embed(
            title=f"🛡️ Security Alert: {evaluation['risk_level']} Risk User Joined",
            description=f"Suspicious account join detected in **{self.guild.name}**.\n\n"
                        f"**User**: {member.mention} ({member.name})\n"
                        f"**User ID**: `{member.id}`\n"
                        f"**Created**: {member.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"**Account Age**: `{evaluation['account_age']} days`\n\n"
                        f"**Flags Triggered**:\n" + "\n".join(evaluation["reasons"]),
            color=color,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
        embed.set_footer(text="FAIZxCHEATS Security Protocol")

        view = SecurityAlertView(member.id)
        
        try:
            await staff_logs.send(embed=embed, view=view)
            logger.info(f"Posted security alert card for {member.name} in #{staff_logs.name}")
        except Exception as e:
            logger.error(f"Failed to send security alert embed to staff logs: {e}")

    async def notify_raid(self, member: discord.Member) -> None:
        """Alerts staff that a raid has been detected and lockdown is active."""
        staff_logs = await self.get_staff_logs_channel()
        if not staff_logs:
            return

        embed = discord.Embed(
            title="⚠️ CRITICAL ALERT: Raid Protection Triggered!",
            description=f"A mass join raid has been detected in the server!\n"
                        f"The server verification gates have been put in **Lockdown Mode** for the next 2 minutes.\n\n"
                        f"**Flagged User Join**: {member.mention} ({member.name})\n"
                        f"**Lockdown Status**: active (Verifications paused)",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Raid Protection Mode")
        
        try:
            await staff_logs.send(content="@here 🚨 **RAID PROTECTION LOCKDOWN ACTIVE**", embed=embed)
            logger.warning("Raid protection alert posted to staff logs.")
        except Exception as e:
            logger.error(f"Failed to post raid protection alert: {e}")

    async def post_scam_alert(self, member: discord.Member, channel: discord.abc.GuildChannel, score: int, reasons: List[str], text: str, action_taken: str, image_url: Optional[str] = None):
        """Sends an urgent staff alert card for high-risk scam detections."""
        staff_logs = await self.get_staff_logs_channel()
        if not staff_logs:
            logger.warning("Could not find staff logs channel to post scam alert.")
            return

        embed = discord.Embed(
            title="🚨 Urgent Scam Shield Detection",
            description=f"A high-risk scam message was detected and processed.\n\n"
                        f"**User**: {member.mention} ({member.name})\n"
                        f"**Channel**: {channel.mention}\n"
                        f"**Scam Risk Score**: `{score}/100` (CRITICAL)\n"
                        f"**Action Taken**: {action_taken}\n\n"
                        f"**Trigger Reasons**:\n" + "\n".join(reasons),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        if image_url:
            embed.set_image(url=image_url)
        embed.set_footer(text="FAIZxCHEATS Anti-Scam Shield Protocol")

        view = SecurityAlertView(member.id)

        try:
            await staff_logs.send(content="@here 🚨 **CRITICAL SCAM DETECTED**", embed=embed, view=view)
            logger.info(f"Posted urgent scam alert card for {member.name} in #{staff_logs.name}")
        except Exception as e:
            logger.error(f"Failed to send scam alert embed: {e}")


async def handle_security_action(interaction: discord.Interaction, action: str, target_user_id: int):
    """Processes staff clicks on security alert warning cards."""
    guild = interaction.guild
    staff_member = interaction.user
    if not guild or not isinstance(staff_member, discord.Member):
        return

    # Check permission
    if not staff_member.guild_permissions.administrator and not discord.utils.get(staff_member.roles, name="Staff"):
        await interaction.response.send_message("❌ You do not have permission to execute this administrative action.", ephemeral=True)
        return

    await interaction.response.defer()

    # Look up target user
    target_member = guild.get_member(target_user_id)
    target_name = f"User ID {target_user_id}"
    
    try:
        if action == "ban":
            if target_member:
                target_name = target_member.name
                await target_member.ban(reason=f"FAIZxCHEATS Security Alert: Banned by staff {staff_member.name}")
            else:
                await guild.ban(discord.Object(id=target_user_id), reason=f"FAIZxCHEATS Security Alert: Banned by staff {staff_member.name}")
            status_text = f"🔨 **Banned** by {staff_member.mention}"
            
        elif action == "kick":
            if target_member:
                target_name = target_member.name
                await target_member.kick(reason=f"FAIZxCHEATS Security Alert: Kicked by staff {staff_member.name}")
                status_text = f"👢 **Kicked** by {staff_member.mention}"
            else:
                await interaction.followup.send("❌ User is no longer in the server and cannot be kicked.", ephemeral=True)
                return
                
        elif action == "dismiss":
            if target_member:
                target_name = target_member.name
            status_text = f"✅ **Dismissed** by {staff_member.mention}"
            
        # Edit the original alert card message to disable buttons and update footer
        msg = interaction.message
        if msg:
            # Recreate embed with updated footer
            embed = msg.embeds[0]
            embed.set_footer(text=f"Status: {status_text} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Disable buttons
            view = discord.ui.View.from_message(msg)
            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
                    
            await msg.edit(embed=embed, view=view)
            await interaction.followup.send(f"Successfully processed action: {action.upper()} for {target_name}.", ephemeral=True)
            
    except Exception as e:
        logger.error(f"Failed to execute administrative security action: {e}")
        await interaction.followup.send(f"❌ Failed to execute action: {e}", ephemeral=True)
