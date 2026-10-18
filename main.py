import os
import asyncio
import discord

from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

# ================= CONFIGURATION =================

TARGET_CHANNEL_ID = 1442716165406195762
PING_ROLE_ID = 1323302918287261756
OWNER_ID = 1454060066675228746

IST = timezone(timedelta(hours=5, minutes=30))
TOKEN = os.getenv("DISCORD_TOKEN")

THUMBNAIL_URL = "https://cdn.corenexis.com/f/0ByJhZ5u4OF.jpeg"

# =================================================

intents = discord.Intents.default()


class EventState:
    def __init__(self, max_roster=10, max_waitlist=2):
        self.main_roster = []
        self.waitlist = []
        self.max_roster = max_roster
        self.max_waitlist = max_waitlist


def build_event_embed(state, closed=False):
    now = datetime.now(IST)

    embed = discord.Embed(
        title=(
            "🔒 Informal Signup Closed"
            if closed else "🟢 Informal Signup Open"
        ),
        color=0xED4245 if closed else 0xE67E22
    )

    embed.set_thumbnail(url=THUMBNAIL_URL)

    signup_list = "\n".join(
        f"{i + 1}. {name}"
        for i, (_, name) in enumerate(state.main_roster)
    ) or "*No one yet — be the first!*"

    backup_list = "\n".join(
        f"{i + 1}. {name}"
        for i, (_, name) in enumerate(state.waitlist)
    ) or "*No backup players*"

    embed.description = (
        "**Nickname format is mandatory:**\n"
        "**Name | ID**\n\n"
        f"**Time (IST)**\n{now.strftime('%H:%M')}\n\n"
        f"**Date**\n{now.strftime('%d %b %Y')}"
    )

    embed.add_field(
        name="Players Joined",
        value=f"{len(state.main_roster)}/{state.max_roster}",
        inline=True
    )

    embed.add_field(
        name="Slots Remaining",
        value=str(state.max_roster - len(state.main_roster)),
        inline=True
    )

    embed.add_field(
        name="Backup Players",
        value=f"{len(state.waitlist)}/{state.max_waitlist}",
        inline=False
    )

    embed.add_field(name="Signup List", value=signup_list, inline=False)
    embed.add_field(name="Backup List", value=backup_list, inline=False)
    embed.set_footer(text="Made By Max Standl")

    return embed


class EventSignupView(discord.ui.View):
    def __init__(self, state):
        super().__init__(timeout=None)
        self.state = state
        self.message = None
        self.closed = False

    async def refresh(self, interaction):
        await interaction.response.edit_message(
            embed=build_event_embed(self.state),
            view=self
        )

    async def close_signup(self):
        if self.closed:
            return

        self.closed = True

        for child in self.children:
            child.disabled = True

        if self.message:
            try:
                await self.message.edit(
                    embed=build_event_embed(self.state, closed=True),
                    view=self
                )
            except discord.HTTPException as error:
                print(f"Could not close signup panel: {error}")

    @discord.ui.button(
        label="Join Informal",
        style=discord.ButtonStyle.success
    )
    async def join_button(self, interaction, button):
        if self.closed:
            await interaction.response.send_message(
                "🔒 Signups are closed.",
                ephemeral=True
            )
            return

        user_id = interaction.user.id
        name = interaction.user.display_name

        if any(
            uid == user_id
            for uid, _ in self.state.main_roster + self.state.waitlist
        ):
            await interaction.response.send_message(
                "You have already signed up.",
                ephemeral=True
            )
            return

        if len(self.state.main_roster) < self.state.max_roster:
            self.state.main_roster.append((user_id, name))

        elif len(self.state.waitlist) < self.state.max_waitlist:
            self.state.waitlist.append((user_id, name))

        else:
            await interaction.response.send_message(
                "❌ The player roster and backup list are full.",
                ephemeral=True
            )
            return

        await self.refresh(interaction)

    @discord.ui.button(
        label="Leave Informal",
        style=discord.ButtonStyle.danger
    )
    async def leave_button(self, interaction, button):
        if self.closed:
            await interaction.response.send_message(
                "🔒 Signups are closed.",
                ephemeral=True
            )
            return

        user_id = interaction.user.id

        self.state.main_roster = [
            (uid, name)
            for uid, name in self.state.main_roster
            if uid != user_id
        ]

        self.state.waitlist = [
            (uid, name)
            for uid, name in self.state.waitlist
            if uid != user_id
        ]

        await self.refresh(interaction)


class SignupBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents
        )

        self.current_view = None
        self.current_close_task = None
        self.last_signup_hour = None
        self.schedule_enabled = True

    async def setup_hook(self):
        await self.tree.sync()
        self.hourly_signup.start()

    async def open_signup(self):
        channel = self.get_channel(TARGET_CHANNEL_ID)

        if channel is None:
            try:
                channel = await self.fetch_channel(TARGET_CHANNEL_ID)
            except discord.HTTPException as error:
                print(f"Could not find signup channel: {error}")
                return

        # Close the previous panel, if necessary.
        if self.current_view and not self.current_view.closed:
            await self.current_view.close_signup()

        # Cancel an old closing task.
        if (
            self.current_close_task
            and not self.current_close_task.done()
        ):
            self.current_close_task.cancel()

        state = EventState()
        view = EventSignupView(state)

        message = await channel.send(
            f"<@&{PING_ROLE_ID}> 🔔 Informal Signups Open!",
            embed=build_event_embed(state),
            view=view
        )

        view.message = message
        self.current_view = view

        # Close at XX:10 IST in the same hour.
        now = datetime.now(IST)
        close_time = now.replace(
            minute=10,
            second=0,
            microsecond=0
        )

        if close_time <= now:
            await view.close_signup()
            await channel.send("🔒 Informal signups are now closed.")
            return

        async def close_later():
            try:
                delay = (close_time - datetime.now(IST)).total_seconds()
                await asyncio.sleep(max(0, delay))

                await view.close_signup()
                await channel.send(
                    "🔒 Informal signups are now closed."
                )

            except asyncio.CancelledError:
                pass

            except discord.HTTPException as error:
                print(f"Could not send closing message: {error}")

        self.current_close_task = asyncio.create_task(close_later())

    @tasks.loop(seconds=5)
    async def hourly_signup(self):
        if not self.schedule_enabled:
            return

        now = datetime.now(IST)

        if now.minute == 0:
            hour_key = now.strftime("%Y-%m-%d %H")

            if hour_key != self.last_signup_hour:
                self.last_signup_hour = hour_key
                await self.open_signup()

    @hourly_signup.before_loop
    async def before_hourly_signup(self):
        await self.wait_until_ready()


bot = SignupBot()


@bot.event
async def on_ready():
    print(f"BOT IS ONLINE: {bot.user}")
    print("Signup schedule: every hour at XX:00 IST")
    print("Signups close at XX:10 IST")


@bot.tree.command(
    name="startinformalbot",
    description="Enable the hourly informal signup schedule"
)
async def startinformalbot(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ Only High Command can use this command.",
            ephemeral=True
        )
        return

    bot.schedule_enabled = True

    await interaction.response.send_message(
        "✅ Hourly signup schedule enabled. "
        "The next signup opens at the next hour (XX:00 IST).",
        ephemeral=True
    )


@bot.tree.command(
    name="stopinformalbot",
    description="Stop the hourly informal signup schedule"
)
async def stopinformalbot(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message(
            "❌ Only High Command can use this command.",
            ephemeral=True
        )
        return

    bot.schedule_enabled = False

    if bot.current_close_task and not bot.current_close_task.done():
        bot.current_close_task.cancel()

    if bot.current_view and not bot.current_view.closed:
        await bot.current_view.close_signup()

    await interaction.response.send_message(
        "🛑 Hourly signup schedule stopped.",
        ephemeral=True
    )


if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN missing. Add it to your .env file."
    )

bot.run(TOKEN)
