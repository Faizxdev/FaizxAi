import discord
import asyncio
from discord import app_commands
from discord.ext import commands
from src.core.review_manager import ReviewManager, temp_reviews
from src.utils.logger import setup_logger

logger = setup_logger("review_commands")

class ReviewStarsInput(discord.ui.TextInput):
    def __init__(self):
        super().__init__(
            label="Rating (1 to 5 Stars)",
            placeholder="Type 5, 4, 3, 2, or 1...",
            min_length=1,
            max_length=1,
            required=True
        )

class ReviewCommentInput(discord.ui.TextInput):
    def __init__(self):
        super().__init__(
            label="Your Review / Comments",
            style=discord.TextStyle.paragraph,
            placeholder="Tell us what you think of our products and services...",
            min_length=10,
            max_length=800,
            required=True
        )

class ReviewModal(discord.ui.Modal, title="Submit Customer Review"):
    stars = ReviewStarsInput()
    comment = ReviewCommentInput()

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user
        if not guild or not member:
            return

        # Validate stars input
        try:
            rating = int(self.stars.value.strip())
            if rating < 1 or rating > 5:
                raise ValueError
        except ValueError:
            await interaction.followup.send("❌ **Invalid Rating**: Please enter a valid number between 1 and 5.", ephemeral=True)
            return

        comment_text = self.comment.value.strip()
        user_id = member.id

        # Save to temp review state
        temp_reviews[user_id] = {
            "rating": rating,
            "comment": comment_text,
            "done": False
        }

        # Prompt for image proof
        embed = discord.Embed(
            title="📸 Purchase Proof Screenshot (Optional)",
            description="Your review comments have been received!\n\n"
                        "To complete your review, **upload/attach a screenshot proof** in this chat within **60 seconds**.\n"
                        "If you do not want to add a screenshot, click the **Skip Proof** button below.",
            color=discord.Color.blue()
        )
        view = ReviewProofView(self.bot, user_id, rating, comment_text)
        prompt_msg = await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        # Wait for file upload in the current channel
        def check_msg(msg):
            return msg.author.id == user_id and msg.attachments and msg.channel.id == interaction.channel.id

        try:
            # We listen for 60 seconds
            msg = await self.bot.wait_for("message", check=check_msg, timeout=60.0)
            
            # If the user already clicked skip in the meantime, ignore
            if temp_reviews.get(user_id, {}).get("done", False):
                return

            proof_url = msg.attachments[0].url
            
            # Clean up user's uploaded image message to keep channel tidy
            try:
                await msg.delete()
            except Exception:
                pass

            # Complete review
            temp_reviews[user_id]["done"] = True
            mgr = ReviewManager(guild)
            await mgr.submit_review(user_id, member.display_name, rating, comment_text, proof_url)
            
            await interaction.followup.send("🎉 **Review Submitted Successfully!** Thank you for your feedback.", ephemeral=True)
            temp_reviews.pop(user_id, None)

        except asyncio.TimeoutError:
            # Check if user already skipped
            if user_id in temp_reviews and not temp_reviews[user_id].get("done", False):
                temp_reviews[user_id]["done"] = True
                mgr = ReviewManager(guild)
                await mgr.submit_review(user_id, member.display_name, rating, comment_text, None)
                await interaction.followup.send("⏰ **Timeout**: Review submitted automatically without a screenshot proof.", ephemeral=True)
                temp_reviews.pop(user_id, None)


class ReviewProofView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int, rating: int, comment: str):
        super().__init__(timeout=60.0)
        self.bot = bot
        self.user_id = user_id
        self.rating = rating
        self.comment = comment

    @discord.ui.button(label="Skip Proof", style=discord.ButtonStyle.secondary, emoji="⏭️", custom_id="skip_proof_button")
    async def skip_proof(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        # Check if already processed
        if user_id in temp_reviews and not temp_reviews[user_id].get("done", False):
            temp_reviews[user_id]["done"] = True
            guild = interaction.guild
            member = interaction.user
            
            mgr = ReviewManager(guild)
            await mgr.submit_review(user_id, member.display_name, self.rating, self.comment, None)
            
            await interaction.followup.send("🎉 **Review Submitted Successfully!** (Proof screenshot skipped)", ephemeral=True)
            temp_reviews.pop(user_id, None)
            self.stop()


class ReviewCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="review", description="Submit a rating and feedback review for FAIZxCHEATS.")
    async def review(self, interaction: discord.Interaction):
        # Verification check: require Verified role
        guild = interaction.guild
        member = interaction.user
        if not guild or not isinstance(member, discord.Member):
            return

        # Find Verified or Customer roles
        verified_role = discord.utils.get(guild.roles, name="Verified")
        customer_role = discord.utils.get(guild.roles, name="Customer")
        
        is_verified = (verified_role in member.roles) if verified_role else False
        is_customer = (customer_role in member.roles) if customer_role else False
        
        # If neither role is found or user has neither, reject
        if not is_verified and not is_customer and not member.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ **Verification Required**: You must complete verification or purchase a product to leave reviews.",
                ephemeral=True
            )
            return

        # Open modal
        modal = ReviewModal(self.bot)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="review-stats", description="Force refresh the customer reviews statistics embed card.")
    @app_commands.checks.has_permissions(administrator=True)
    async def review_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return
            
        mgr = ReviewManager(guild)
        await mgr.update_stats_panel()
        await interaction.followup.send("📈 **Review statistics panel has been updated successfully!**", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ReviewCommands(bot))
