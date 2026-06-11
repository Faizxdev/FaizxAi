import discord
from discord import app_commands
from discord.ext import commands
from src.utils.ai_generator import AIGenerator
from src.core.guild_builder import GuildBuilder
from src.utils.logger import setup_logger

logger = setup_logger("ai_builder_command")

class AIBuilder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ai-build", description="Automatically design and build a Discord server layout using real AI.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_build(self, interaction: discord.Interaction, prompt: str):
        # We defer the response as AI generation might take 5-15 seconds
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        # Restrict to Server Owner only!
        if interaction.user.id != guild.owner_id:
            await interaction.followup.send("❌ **Access Denied**: The AI Guild Architect is restricted to the Server Owner only.", ephemeral=True)
            return

        try:
            # Send warning and perform complete layout wipe
            await interaction.followup.send("⚠️ **Wiping server layout...** Removing existing channels, categories, and custom roles.", ephemeral=True)
            
            # 1. Delete all channels and categories except the current interaction channel
            for channel in list(guild.channels):
                if channel.id == interaction.channel.id:
                    continue
                if isinstance(interaction.channel, discord.abc.GuildChannel) and interaction.channel.category and channel.id == interaction.channel.category.id:
                    continue
                try:
                    await channel.delete(reason="AI rebuild wipe")
                except Exception as e:
                    logger.warning(f"Could not delete channel {channel.name}: {e}")
                    
            # 2. Delete all custom roles (skipping bot roles and @everyone)
            bot_highest_role = guild.me.top_role
            for role in list(guild.roles):
                if role.is_default() or role.managed:
                    continue
                if role >= bot_highest_role:
                    continue
                try:
                    await role.delete(reason="AI rebuild wipe")
                except Exception as e:
                    logger.warning(f"Could not delete role {role.name}: {e}")

            await interaction.followup.send("🤖 **Querying AI Guild Architect** to design your server layout based on your prompt... Please stand by.", ephemeral=True)
            
            # Call the AI API
            layout_data = await AIGenerator.generate_layout(prompt)
            logger.info("AI layout successfully generated.")
            
            await interaction.followup.send("🧱 **Layout designed successfully!** Beginning execution of the server building pipeline...", ephemeral=True)

            # Build the guild using GuildBuilder
            builder = GuildBuilder(guild)
            report = await builder.build(layout_data)

            # Build status message
            status_msg = f"✨ **AI Guild Builder execution complete!** ✨\n\n" \
                         f"**Status**: {report['status']}\n" \
                         f"**Roles Synced**: {report['roles_synced']}\n" \
                         f"**Categories Synced**: {report['categories_synced']}\n" \
                         f"**Channels Synced**: {report['channels_synced']}\n" \
                         f"**Store Products**: {report.get('products_synced', 0)}\n" \
                         f"**Verification System**: {report['verification_status']}\n" \
                         f"**Ticket System**: {report['tickets_status']}\n" \
                         f"**Moderation Setup**: {report['moderation_status']}"

            if report["errors"]:
                status_msg += f"\n\n⚠️ **Errors during construction**:\n- " + "\n- ".join(report["errors"][:5])

            # Post a nice embed to the moderation logs
            log_chan = discord.utils.get(guild.text_channels, name="┃📊・staff-logs")
            # Fallback checks
            if not log_chan:
                for ch in guild.text_channels:
                    if "LOG" in ch.name.upper() or "📊" in ch.name:
                        log_chan = ch
                        break

            if log_chan:
                embed = discord.Embed(
                    title="AI Guild Construction Complete",
                    description=f"Server was automatically reconstructed via AI generation by {interaction.user.mention}.",
                    color=discord.Color.purple(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="Prompt Used", value=prompt, inline=False)
                embed.add_field(name="Build Status", value=report["status"], inline=True)
                await log_chan.send(embed=embed)

            await interaction.followup.send(status_msg, ephemeral=True)
        except Exception as e:
            logger.error(f"Error executing AI builder command: {e}")
            await interaction.followup.send(f"❌ **Failed to generate or build server layout**: {e}", ephemeral=True)

    @ai_build.error
    async def handle_errors(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You must have Administrator permissions to invoke the AI Guild Architect.", ephemeral=True)
        else:
            logger.error(f"AI builder command error: {error}")
            try:
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AIBuilder(bot))
