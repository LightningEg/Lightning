"""Discord-native commands for the Lightning community (no finance database access)."""
from __future__ import annotations
import logging
import discord
from discord import app_commands
from discord.ext import commands
from config import Settings, validate_channel_name, validate_public_text

LOG = logging.getLogger(__name__)
settings = Settings.from_environ()
group = app_commands.Group(name="lightning", description="Lightning community tools")

class LightningBot(commands.Bot):
    async def setup_hook(self) -> None:
        guild = discord.Object(id=settings.guild_id)
        self.tree.add_command(group, guild=guild)
        await self.tree.sync(guild=guild)
        LOG.info("Commands synced to server %s", settings.guild_id)

intents = discord.Intents.none()
intents.guilds = True
bot = LightningBot(command_prefix=commands.when_mentioned, intents=intents)

async def operator_only(interaction: discord.Interaction) -> bool:
    if settings.is_operator(interaction.user.id, interaction.guild_id):
        return True
    await interaction.response.send_message("Only designated Lightning operators can use this command.", ephemeral=True)
    return False

def in_server(interaction: discord.Interaction, channel: discord.abc.GuildChannel) -> bool:
    return bool(interaction.guild and interaction.guild_id == settings.guild_id and channel.guild.id == settings.guild_id)

@group.command(name="ping", description="Check whether Lightning Bot is online")
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("Lightning Bot is online.", ephemeral=True)

@group.command(name="post", description="Post a message to a channel (operators only)")
@app_commands.describe(channel="Target text channel", message="Text to publish; mentions do not notify users")
async def post(interaction: discord.Interaction, channel: discord.TextChannel, message: str) -> None:
    if not await operator_only(interaction): return
    if not in_server(interaction, channel):
        await interaction.response.send_message("That channel is outside this server.", ephemeral=True)
        return
    try:
        content = validate_public_text(message)
        await channel.send(content, allowed_mentions=discord.AllowedMentions.none())
    except ValueError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    except discord.HTTPException:
        LOG.exception("Post failed")
        await interaction.response.send_message("Could not post; check channel permissions.", ephemeral=True)
        return
    await interaction.response.send_message(f"Posted in {channel.mention}.", ephemeral=True)

@group.command(name="channel", description="Create a text channel (operators only)")
async def channel(interaction: discord.Interaction, name: str, topic: str = "") -> None:
    if not await operator_only(interaction): return
    try: name = validate_channel_name(name)
    except ValueError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    if len(topic) > 1024:
        await interaction.response.send_message("Topic exceeds 1024 characters.", ephemeral=True)
        return
    assert interaction.guild is not None
    existing = discord.utils.get(interaction.guild.text_channels, name=name)
    if existing:
        await interaction.response.send_message(f"Already exists: {existing.mention}.", ephemeral=True)
        return
    try:
        created = await interaction.guild.create_text_channel(name=name, topic=topic, reason=f"Lightning operator {interaction.user.id}")
    except discord.HTTPException:
        LOG.exception("Create channel failed")
        await interaction.response.send_message("Could not create channel; check Manage Channels.", ephemeral=True)
        return
    await interaction.response.send_message(f"Created {created.mention}.", ephemeral=True)

@group.command(name="forum", description="Create a forum (operators only)")
async def forum(interaction: discord.Interaction, name: str, topic: str = "") -> None:
    if not await operator_only(interaction): return
    try: name = validate_channel_name(name)
    except ValueError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    if len(topic) > 1024:
        await interaction.response.send_message("Topic exceeds 1024 characters.", ephemeral=True)
        return
    assert interaction.guild is not None
    existing = discord.utils.get(interaction.guild.forums, name=name)
    if existing:
        await interaction.response.send_message(f"Already exists: {existing.mention}.", ephemeral=True)
        return
    try:
        created = await interaction.guild.create_forum(name=name, topic=topic, reason=f"Lightning operator {interaction.user.id}")
    except discord.HTTPException:
        LOG.exception("Create forum failed")
        await interaction.response.send_message("Could not create forum; check Manage Channels.", ephemeral=True)
        return
    await interaction.response.send_message(f"Created {created.mention}.", ephemeral=True)

@group.command(name="thread", description="Start a public discussion thread (operators only)")
async def thread(interaction: discord.Interaction, channel: discord.TextChannel, name: str, opening_message: str) -> None:
    if not await operator_only(interaction): return
    if not in_server(interaction, channel) or not (1 <= len(name.strip()) <= 100):
        await interaction.response.send_message("Use a channel in this server and a thread name of 1–100 characters.", ephemeral=True)
        return
    try:
        content = validate_public_text(opening_message)
        created = await channel.create_thread(name=name.strip(), type=discord.ChannelType.public_thread, reason=f"Lightning operator {interaction.user.id}")
        await created.send(content, allowed_mentions=discord.AllowedMentions.none())
    except ValueError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    except discord.HTTPException:
        LOG.exception("Create thread failed")
        await interaction.response.send_message("Could not complete thread; check permissions.", ephemeral=True)
        return
    await interaction.response.send_message(f"Created {created.mention}.", ephemeral=True)

class FeedbackModal(discord.ui.Modal, title="Feedback for Lightning"):
    feedback_title = discord.ui.TextInput(label="Topic", max_length=120)
    details = discord.ui.TextInput(label="Feedback (no private information)", style=discord.TextStyle.paragraph, max_length=1800)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not settings.feedback_channel_id:
            await interaction.response.send_message("Feedback is not configured.", ephemeral=True)
            return
        try:
            dest = bot.get_channel(settings.feedback_channel_id) or await bot.fetch_channel(settings.feedback_channel_id)
            if not isinstance(dest, discord.TextChannel) or dest.guild.id != settings.guild_id:
                await interaction.response.send_message("Feedback destination is invalid.", ephemeral=True)
                return
            embed = discord.Embed(title=str(self.feedback_title.value), description=str(self.details.value), color=0x64748B)
            embed.set_footer(text=f"Discord user ID {interaction.user.id}")
            await dest.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            LOG.exception("Feedback failed")
            await interaction.response.send_message("Could not submit feedback.", ephemeral=True)
            return
        await interaction.response.send_message("Feedback submitted.", ephemeral=True)

@group.command(name="feedback", description="Send feedback privately to the Lightning team")
@app_commands.checks.cooldown(1, 300.0)
async def feedback(interaction: discord.Interaction) -> None:
    if interaction.guild_id != settings.guild_id:
        await interaction.response.send_message("This command is only for Lightning's server.", ephemeral=True)
    elif not settings.feedback_channel_id:
        await interaction.response.send_message("Feedback is not configured.", ephemeral=True)
    else:
        await interaction.response.send_modal(FeedbackModal())

@group.error
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    message = ("Feedback can be submitted once every five minutes." if isinstance(error, app_commands.CommandOnCooldown)
               else "Command failed; contact a moderator.")
    LOG.error("Discord command error: %s", type(error).__name__)
    if interaction.response.is_done(): await interaction.followup.send(message, ephemeral=True)
    else: await interaction.response.send_message(message, ephemeral=True)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bot.run(settings.token, log_handler=None)
