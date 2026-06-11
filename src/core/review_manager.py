import discord
import json
import io
import datetime
from typing import Dict, Any, List, Optional
from src.utils.logger import setup_logger

logger = setup_logger("review_manager")

# In-memory temporary review states while waiting for proof uploads
# user_id -> { "rating": int, "comment": str, "modal_interaction": Interaction }
temp_reviews: Dict[int, Dict[str, Any]] = {}

async def fetch_reviews_from_logs(guild: discord.Guild) -> List[Dict[str, Any]]:
    """Fetches the reviews database file reviews_db.json from staff logs."""
    log_chan = discord.utils.get(guild.text_channels, name="┃📊・staff-logs")
    if not log_chan:
        for ch in guild.text_channels:
            if "LOG" in ch.name.upper() or "📊" in ch.name:
                log_chan = ch
                break
    if not log_chan:
        logger.warning("Could not locate staff-logs channel to fetch reviews.")
        return []

    try:
        async for msg in log_chan.history(limit=50):
            if msg.author == guild.me and msg.attachments:
                for att in msg.attachments:
                    if att.filename == "reviews_db.json":
                        content_bytes = await att.read()
                        data = json.loads(content_bytes.decode("utf-8"))
                        return data.get("reviews", [])
    except Exception as e:
        logger.error(f"Error fetching reviews database: {e}")
    return []

async def save_reviews_to_logs(guild: discord.Guild, reviews: List[Dict[str, Any]]) -> None:
    """Saves the reviews database by uploading it as a file attachment to staff logs."""
    log_chan = discord.utils.get(guild.text_channels, name="┃📊・staff-logs")
    if not log_chan:
        for ch in guild.text_channels:
            if "LOG" in ch.name.upper() or "📊" in ch.name:
                log_chan = ch
                break
    if not log_chan:
        logger.error("Could not locate staff-logs channel to save reviews.")
        return

    try:
        data = {"reviews": reviews}
        json_bytes = json.dumps(data, indent=2).encode("utf-8")
        file_data = io.BytesIO(json_bytes)
        discord_file = discord.File(file_data, filename="reviews_db.json")

        await log_chan.send(
            content="🔄 **Customer Reviews Database Auto-Sync Backup**",
            file=discord_file
        )
        logger.info("Saved reviews database to staff logs channel.")
    except Exception as e:
        logger.error(f"Failed to save reviews database: {e}")

class ReviewManager:
    def __init__(self, guild: discord.Guild):
        self.guild = guild

    async def get_reviews_channel(self) -> Optional[discord.TextChannel]:
        """Resolves the reviews text channel."""
        chan = discord.utils.get(self.guild.text_channels, name="┃⭐・reviews")
        if not chan:
            for ch in self.guild.text_channels:
                if "REVIEW" in ch.name.upper() or "⭐" in ch.name:
                    chan = ch
                    break
        return chan

    async def update_stats_panel(self) -> None:
        """Calculates review metrics and updates the pinned stats embed in the reviews channel."""
        reviews = await fetch_reviews_from_logs(self.guild)
        reviews_channel = await self.get_reviews_channel()
        if not reviews_channel:
            logger.warning("No reviews channel found to update stats panel.")
            return

        total_reviews = len(reviews)
        if total_reviews == 0:
            avg_rating = 0.0
            breakdown = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
        else:
            total_stars = sum(r.get("rating", 5) for r in reviews)
            avg_rating = round(total_stars / total_reviews, 1)
            breakdown = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
            for r in reviews:
                rating = int(r.get("rating", 5))
                if rating in breakdown:
                    breakdown[rating] += 1

        # Build rating bar strings
        def make_bar(count: int) -> str:
            if total_reviews == 0:
                percent = 0
            else:
                percent = int((count / total_reviews) * 10)
            return "█" * percent + "░" * (10 - percent) + f" ({count})"

        # Generate Star representation
        star_rep = "⭐" * int(round(avg_rating))
        if not star_rep:
            star_rep = "None"

        embed = discord.Embed(
            title="📈 FAIZxCHEATS | Customer Review Statistics",
            description=f"Our verified customer ratings breakdown. Buy with absolute confidence!\n\n"
                        f"**Average Rating**: `{avg_rating} / 5.0` | {star_rep}\n"
                        f"**Total Reviews**: `{total_reviews}`\n\n"
                        f"5 Star: `{make_bar(breakdown[5])}`\n"
                        f"4 Star: `{make_bar(breakdown[4])}`\n"
                        f"3 Star: `{make_bar(breakdown[3])}`\n"
                        f"2 Star: `{make_bar(breakdown[2])}`\n"
                        f"1 Star: `{make_bar(breakdown[1])}`",
            color=discord.Color.gold()
        )
        embed.set_footer(text="🛒 Verified Purchases Only • Updated Live")

        # Try to locate existing pinned message or stats message to update
        stats_msg = None
        try:
            # Check pinned messages first
            pins = await reviews_channel.pins()
            for msg in pins:
                if msg.author == self.guild.me and msg.embeds and "Customer Review Statistics" in msg.embeds[0].title:
                    stats_msg = msg
                    break
            
            # If not pinned, search history
            if not stats_msg:
                async for msg in reviews_channel.history(limit=50):
                    if msg.author == self.guild.me and msg.embeds and "Customer Review Statistics" in msg.embeds[0].title:
                        stats_msg = msg
                        break
        except Exception as e:
            logger.warning(f"Error checking message pins: {e}")

        try:
            if stats_msg:
                await stats_msg.edit(embed=embed)
                logger.info("Updated existing review stats embed panel.")
            else:
                new_msg = await reviews_channel.send(embed=embed)
                await new_msg.pin()
                logger.info("Posted and pinned a new review stats embed panel.")
        except Exception as e:
            logger.error(f"Failed to post/edit review stats embed: {e}")

    async def submit_review(self, user_id: int, username: str, rating: int, comment: str, proof_url: Optional[str] = None) -> None:
        """Compiles, logs, posts public card, and updates statistics for a review."""
        reviews = await fetch_reviews_from_logs(self.guild)
        
        # Check if user already reviewed to overwrite, or append
        new_rev = {
            "user_id": user_id,
            "username": username,
            "rating": rating,
            "comment": comment,
            "proof_url": proof_url,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        
        # Check duplicates
        replaced = False
        for i, r in enumerate(reviews):
            if r.get("user_id") == user_id:
                reviews[i] = new_rev
                replaced = True
                break
        if not replaced:
            reviews.append(new_rev)

        # Save to logs database
        await save_reviews_to_logs(self.guild, reviews)

        # Post the public review Embed card
        reviews_channel = await self.get_reviews_channel()
        if reviews_channel:
            stars = "⭐" * rating
            color = discord.Color.green() if rating >= 4 else (discord.Color.orange() if rating == 3 else discord.Color.red())
            
            embed = discord.Embed(
                title=f"Rating: {rating}/5 by {username}",
                description=f"**Rating**: {stars}\n\n"
                            f"**Feedback**:\n{comment}",
                color=color,
                timestamp=discord.utils.utcnow()
            )
            embed.set_thumbnail(url=self.guild.get_member(user_id).display_avatar.url if self.guild.get_member(user_id) else None)
            
            if rating >= 4:
                embed.set_footer(text="🔥 Verified Positive Review!")
            else:
                embed.set_footer(text="Verified Review")

            if proof_url:
                embed.set_image(url=proof_url)

            try:
                await reviews_channel.send(embed=embed)
                logger.info(f"Posted review card for {username} in #{reviews_channel.name}")
            except Exception as e:
                logger.error(f"Failed to post public review card: {e}")

        # Update stats
        await self.update_stats_panel()
