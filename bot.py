# bot.py
import os
os.environ["DISCORD_NO_VOICE"] = "true"  # Disable voice/audio to prevent audioop import issues

import discord
from discord.ext import commands
from discord import app_commands
import asyncio

# ---------------- CONFIG ----------------
TOKEN = os.environ.get("DISCORD_TOKEN")  # Add in Render env vars
DEFAULT_LOG_CHANNEL_NAME = "evx-guard-logs"

# ---------------- INTENTS ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.emojis_and_stickers = True
intents.bans = True
intents.guild_reactions = True
intents.webhooks = True
intents.invites = True

# ---------------- BOT INIT ----------------
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- GLOBAL DATA ----------------
features = {
    "Antinuke": {
        "Ban": False,
        "Kick": False,
        "Prune": False,
        "Bot Add": False,
        "Server Update": False,
        "Member Role Update": False,
        "Channel Create": False,
        "Channel Delete": False,
        "Channel Update": False,
        "Role Create": False,
        "Role Delete": False,
        "Role Update": False,
        "Mention @everyone": False,
        "Webhook Management": False,
        "Emojis & Stickers Management": False
    },
    "Automod": {
        "Bad Words Filter": False,
        "Link Filter": False,
        "Invite Filter": False,
        "Caps Filter": False,
        "Spam Filter": False,
        "Mention Spam Filter": False,
        "Image Filter": False,
        "Emoji Filter": False,
        "Sticker Filter": False,
        "Swear Jar": False
    }
}

whitelist = {}
BAD_WORDS = ["badword1", "badword2", "swear"]  # Example

log_channel = None

# ---------------- HELPER FUNCTIONS ----------------
def is_whitelisted(user_id: int, category: str, feature: str):
    if user_id in whitelist:
        return feature in whitelist[user_id].get(category.lower(), [])
    return False

async def get_audit_log_user(guild: discord.Guild, event_type, target_id):
    await asyncio.sleep(1)
    async for entry in guild.audit_logs(limit=5, action=event_type):
        if entry.target.id == target_id:
            return entry.user
    return None

async def ensure_log_channel(guild: discord.Guild):
    global log_channel
    for channel in guild.text_channels:
        if channel.name == DEFAULT_LOG_CHANNEL_NAME:
            log_channel = channel
            return
    log_channel = await guild.create_text_channel(DEFAULT_LOG_CHANNEL_NAME)

# ---------------- GUARD VIEW ----------------
class GuardView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.selected_user = None
        self.selected_antinuke_features = []
        self.selected_automod_features = []

        self.add_item(self.create_antinuke_select())
        self.add_item(self.create_automod_select())

    def create_antinuke_select(self):
        options = [discord.SelectOption(label=f, value=f) for f in features["Antinuke"].keys()]
        select = discord.ui.Select(
            placeholder="Select Antinuke features...",
            options=options,
            min_values=0,
            max_values=len(options),
            disabled=True
        )
        async def callback(interaction: discord.Interaction):
            self.selected_antinuke_features = select.values
            await interaction.response.defer()
        select.callback = callback
        return select

    def create_automod_select(self):
        options = [discord.SelectOption(label=f, value=f) for f in features["Automod"].keys()]
        select = discord.ui.Select(
            placeholder="Select Automod features...",
            options=options,
            min_values=0,
            max_values=len(options),
            disabled=True
        )
        async def callback(interaction: discord.Interaction):
            self.selected_automod_features = select.values
            await interaction.response.defer()
        select.callback = callback
        return select

    def create_embed(self, guild_name, guild_icon_url):
        embed = discord.Embed(title=f"{guild_name} Guard System", color=discord.Color.blue())
        if guild_icon_url:
            embed.set_thumbnail(url=guild_icon_url)

        antinuke_text = "\n".join([f"{'✅' if v else '❌'} **{k}**" for k,v in features["Antinuke"].items()])
        automod_text = "\n".join([f"{'✅' if v else '❌'} **{k}**" for k,v in features["Automod"].items()])

        embed.add_field(name="🛡 Antinuke", value=antinuke_text, inline=True)
        embed.add_field(name="🔨 Automod", value=automod_text, inline=True)

        whitelist_text = ""
        if not whitelist:
            whitelist_text = "No users whitelisted."
        else:
            for uid, uf in whitelist.items():
                user = self.bot.get_user(uid)
                uname = user.name if user else "Unknown"
                ant_list = ", ".join(uf.get("antinuke", [])) or "None"
                auto_list = ", ".join(uf.get("automod", [])) or "None"
                whitelist_text += f"**{uname}**\nAntinuke: {ant_list}\nAutomod: {auto_list}\n\n"

        embed.add_field(name="➕ User Whitelist", value=whitelist_text, inline=False)

        if self.selected_user:
            preview = f"**Selected User:** {self.selected_user.mention}\n"
            preview += f"Antinuke: {', '.join(self.selected_antinuke_features) or 'None'}\n"
            preview += f"Automod: {', '.join(self.selected_automod_features) or 'None'}"
            embed.add_field(name="Current Selection", value=preview, inline=False)

        embed.set_footer(text="Powered by EvX Official")
        return embed

    # ---------------- BUTTONS ----------------
    @discord.ui.button(label="Toggle Antinuke", style=discord.ButtonStyle.secondary)
    async def toggle_antinuke(self, button, interaction: discord.Interaction):
        all_enabled = all(features["Antinuke"].values())
        for k in features["Antinuke"]:
            features["Antinuke"][k] = not all_enabled
        await interaction.response.edit_message(embed=self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None), view=self)

    @discord.ui.button(label="Toggle Automod", style=discord.ButtonStyle.secondary)
    async def toggle_automod(self, button, interaction: discord.Interaction):
        all_enabled = all(features["Automod"].values())
        for k in features["Automod"]:
            features["Automod"][k] = not all_enabled
        await interaction.response.edit_message(embed=self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None), view=self)

    @discord.ui.user_select(placeholder="Select user to whitelist")
    async def select_user(self, select, interaction: discord.Interaction):
        self.selected_user = select.values[0]
        for item in self.children:
            if isinstance(item, discord.ui.Select) and item.placeholder.startswith("Select"):
                item.disabled = False
        await interaction.response.edit_message(embed=self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None), view=self)

    @discord.ui.button(label="Whitelist Antinuke", style=discord.ButtonStyle.success)
    async def whitelist_antinuke(self, button, interaction: discord.Interaction):
        if not self.selected_user:
            await interaction.response.send_message("Select a user first.", ephemeral=True)
            return
        uid = self.selected_user.id
        if uid not in whitelist:
            whitelist[uid] = {"antinuke": [], "automod": []}
        whitelist[uid]["antinuke"] = self.selected_antinuke_features
        await interaction.response.edit_message(embed=self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None), view=self)

    @discord.ui.button(label="Whitelist Automod", style=discord.ButtonStyle.success)
    async def whitelist_automod(self, button, interaction: discord.Interaction):
        if not self.selected_user:
            await interaction.response.send_message("Select a user first.", ephemeral=True)
            return
        uid = self.selected_user.id
        if uid not in whitelist:
            whitelist[uid] = {"antinuke": [], "automod": []}
        whitelist[uid]["automod"] = self.selected_automod_features
        await interaction.response.edit_message(embed=self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None), view=self)

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    bot.add_view(GuardView(bot))
    for guild in bot.guilds:
        await ensure_log_channel(guild)

@bot.event
async def on_message(message):
    if message.author.bot: return

    # Automod Filters
    if features["Automod"]["Bad Words Filter"] and not is_whitelisted(message.author.id, "automod", "Bad Words Filter"):
        if any(b in message.content.lower() for b in BAD_WORDS):
            await message.delete()
            await message.channel.send(f"{message.author.mention}, that word is not allowed!", delete_after=5)

    if features["Automod"]["Link Filter"] and not is_whitelisted(message.author.id, "automod", "Link Filter"):
        if "http://" in message.content.lower() or "https://" in message.content.lower():
            await message.delete()
            await message.channel.send(f"{message.author.mention}, links are not allowed!", delete_after=5)

# ---------------- SLASH COMMANDS ----------------
@bot.tree.command(name="enable_guard", description="Enable the server guard system")
async def enable_guard(interaction: discord.Interaction):
    view = GuardView(bot)
    await ensure_log_channel(interaction.guild)
    embed = view.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="disable_guard", description="Disable the server guard system")
async def disable_guard(interaction: discord.Interaction):
    global features, whitelist
    for category in features:
        for feat in features[category]:
            features[category][feat] = False
    whitelist.clear()
    await interaction.response.send_message("Guard system disabled.", ephemeral=True)

@bot.tree.command(name="about", description="Bot info")
async def about(interaction: discord.Interaction):
    await interaction.response.send_message("EvX Guard Bot - Antinuke + Automod protection system.", ephemeral=True)

# ---------------- RUN ----------------
bot.run(TOKEN)
