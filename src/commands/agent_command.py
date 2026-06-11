import discord
from discord import app_commands
from discord.ext import commands
from src.core.discord_agent import DiscordAgent
from src.utils.logger import setup_logger

logger = setup_logger("agent_command")

class AgentCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="agent-run", description="Command the autonomous AI agent to perform server administration tasks.")
    @app_commands.checks.has_permissions(administrator=True)
    async def agent_run(self, interaction: discord.Interaction, task: str):
        # We defer the response as agent reasoning/tool-execution can take 10-30 seconds
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        # Restrict to Server Owner only!
        if interaction.user.id != guild.owner_id:
            await interaction.followup.send("❌ **Access Denied**: The autonomous agent command is restricted to the Server Owner only.", ephemeral=True)
            return

        try:
            await interaction.followup.send(f"🤖 **Initializing Autonomous Server Agent...**\nTask: *\"{task}\"*", ephemeral=True)
            
            # Instantiate and run agent
            agent = DiscordAgent(guild, self.bot)
            outcome = await agent.run_task(task)
            
            # Format report response
            report = f"✨ **Agent Task Execution Report** ✨\n\n" \
                     f"**Task**: *\"{task}\"*\n" \
                     f"**Outcome**:\n{outcome}"
                     
            # Send report in chunks of 1900 characters to prevent Discord 2000 character limit error
            if len(report) <= 1900:
                await interaction.followup.send(report, ephemeral=True)
            else:
                chunks = []
                current_chunk = []
                current_len = 0
                for line in report.splitlines(keepends=True):
                    if current_len + len(line) > 1900:
                        if current_chunk:
                            chunks.append("".join(current_chunk))
                            current_chunk = []
                            current_len = 0
                        if len(line) > 1900:
                            for i in range(0, len(line), 1900):
                                chunks.append(line[i:i+1900])
                        else:
                            current_chunk.append(line)
                            current_len = len(line)
                    else:
                        current_chunk.append(line)
                        current_len += len(line)
                if current_chunk:
                    chunks.append("".join(current_chunk))
                
                for idx, chunk in enumerate(chunks):
                    header = f"📄 **[Part {idx+1}/{len(chunks)}]**\n" if len(chunks) > 1 else ""
                    await interaction.followup.send(header + chunk, ephemeral=True)
            
            # Log agent activity to moderation/staff logs
            log_chan = discord.utils.get(guild.text_channels, name="┃📊・staff-logs")
            if not log_chan:
                for ch in guild.text_channels:
                    if "LOG" in ch.name.upper() or "📊" in ch.name:
                        log_chan = ch
                        break

            if log_chan:
                embed = discord.Embed(
                    title="Autonomous Agent Execution Complete",
                    description=f"AI Agent executed a server administration task commanded by {interaction.user.mention}.",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="Task Command", value=task, inline=False)
                embed.add_field(name="Outcome", value=outcome[:1024], inline=False)
                await log_chan.send(embed=embed)

        except Exception as e:
            logger.error(f"Error running agent command: {e}")
            await interaction.followup.send(f"❌ **Agent execution failed**: {e}", ephemeral=True)

    @agent_run.error
    async def handle_errors(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ You must have Administrator permissions to run agent tasks.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ You must have Administrator permissions to run agent tasks.", ephemeral=True)
            except Exception:
                pass
        else:
            logger.error(f"Agent command error: {error}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"An error occurred: {str(error)[:1500]}", ephemeral=True)
                else:
                    await interaction.followup.send(f"An error occurred: {str(error)[:1500]}", ephemeral=True)
            except Exception:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(AgentCommand(bot))
