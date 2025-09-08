# bot.py
import os
import discord
import asyncio
from discord.ext import commands

# ---------------- CONFIG ----------------
TOKEN = os.environ.get("DISCORD_TOKEN")  # Set this in Render environment variables

# ---------------- INTENTS ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.emojis_and_stickers = True
intents.integrations = True
intents.webhooks = True
intents.guild_reactions = True
intents.bans = True
intents.invites = True
intents.presences = False
intents.typing = False

# ---------------- BOT INIT ----------------
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- FEATURES ----------------
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
    },
}

whitelist = {}
BAD_WORDS = ["badword1", "badword2", "anotherbadword", "swear"]


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
        options = [
            discord.SelectOption(label=feature, value=feature)
            for feature in features["Antinuke"].keys()
        ]
        select = discord.ui.Select(
            placeholder="Select Antinuke features to whitelist...",
            options=options,
            min_values=0,
            max_values=len(options),
            row=5,
            disabled=True
        )

        async def callback(interaction: discord.Interaction):
            self.selected_antinuke_features = select.values
            await interaction.response.defer()

        select.callback = callback
        return select

    def create_automod_select(self):
        options = [
            discord.SelectOption(label=feature, value=feature)
            for feature in features["Automod"].keys()
        ]
        select = discord.ui.Select(
            placeholder="Select Automod features to whitelist...",
            options=options,
            min_values=0,
            max_values=len(options),
            row=5,
            disabled=True
        )

        async def callback(interaction: discord.Interaction):
            self.selected_automod_features = select.values
            await interaction.response.defer()

        select.callback = callback
        return select

    def create_embed(self, guild_name, guild_icon_url):
        embed = discord.Embed(
            title=f"{guild_name} Guard System",
            color=discord.Color.blue()
        )
        if guild_icon_url:
            embed.set_thumbnail(url=guild_icon_url)

        antinuke_text = ""
        for feature, enabled in features["Antinuke"].items():
            status = "✅" if enabled else "❌"
            antinuke_text += f"{status} : **{feature}**\n"
        embed.add_field(name="🛡️ Antinuke", value=antinuke_text, inline=True)

        automod_text = ""
        for feature, enabled in features["Automod"].items():
            status = "✅" if enabled else "❌"
            automod_text += f"{status} : **{feature}**\n"
        embed.add_field(name="🔨 Automod", value=automod_text, inline=True)

        whitelist_text = ""
        if not whitelist:
            whitelist_text = "No users whitelisted."
        else:
            for user_id, user_features in whitelist.items():
                user = self.bot.get_user(user_id)
                user_name = user.name if user else "Unknown User"
                antinuke_list = ", ".join(user_features.get("antinuke", [])) or "None"
                automod_list = ", ".join(user_features.get("automod", [])) or "None"
                whitelist_text += f"**User:** {user_name}\n"
                whitelist_text += f"**Antinuke:** {antinuke_list}\n"
                whitelist_text += f"**Automod:** {automod_list}\n\n"

        embed.add_field(name="➕ User Whitelist", value=whitelist_text, inline=False)
        embed.set_footer(text="Powered by EvX Official")

        if self.selected_user:
            preview_text = f"**Selected User:** {self.selected_user.mention}\n"
            preview_text += f"**Antinuke Features:** {', '.join(self.selected_antinuke_features) or 'None'}\n"
            preview_text += f"**Automod Features:** {', '.join(self.selected_automod_features) or 'None'}"
            embed.add_field(name="Current Whitelist Selection", value=preview_text, inline=False)

        return embed

    @discord.ui.button(label="Toggle Antinuke", style=discord.ButtonStyle.secondary, row=4)
    async def toggle_antinuke_button(self, button, interaction):
        all_enabled = all(features["Antinuke"].values())
        new_state = not all_enabled
        for key in features["Antinuke"]:
            features["Antinuke"][key] = new_state
        new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label="Toggle Automod", style=discord.ButtonStyle.secondary, row=4)
    async def toggle_automod_button(self, button, interaction):
        all_enabled = all(features["Automod"].values())
        new_state = not all_enabled
        for key in features["Automod"]:
            features["Automod"][key] = new_state
        new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.user_select(placeholder="Select a user to whitelist...", row=5)
    async def user_select_callback(self, select, interaction):
        self.selected_user = select.values[0]
        for item in self.children:
            if isinstance(item, discord.ui.Select):
                item.disabled = False
        new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label="Whitelist Antinuke", style=discord.ButtonStyle.success, row=6)
    async def whitelist_antinuke(self, button, interaction):
        if self.selected_user:
            user_id = self.selected_user.id
            if user_id not in whitelist:
                whitelist[user_id] = {"antinuke": [], "automod": []}
            whitelist[user_id]["antinuke"] = self.selected_antinuke_features
            new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.edit_message(embed=new_embed, view=self)
        else:
            await interaction.response.send_message("Please select a user first.", ephemeral=True)

    @discord.ui.button(label="Whitelist Automod", style=discord.ButtonStyle.success, row=6)
    async def whitelist_automod(self, button, interaction):
        if self.selected_user:
            user_id = self.selected_user.id
            if user_id not in whitelist:
                whitelist[user_id] = {"antinuke": [], "automod": []}
            whitelist[user_id]["automod"] = self.selected_automod_features
            new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.edit_message(embed=new_embed, view=self)
        else:
            await interaction.response.send_message("Please select a user first.", ephemeral=True)


# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online and connected!")
    bot.add_view(GuardView(bot))
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Error syncing commands: {e}")


def is_whitelisted(user_id, category, feature):
    if user_id in whitelist:
        return feature in whitelist[user_id].get(category, [])
    return False


# ---------------- AUTOMOD ----------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if features["Automod"]["Bad Words Filter"] and not is_whitelisted(message.author.id, "automod", "Bad Words Filter"):
        content = message.content.lower()
        if any(word in content for word in BAD_WORDS):
            await message.delete()
            await message.channel.send(f"{message.author.mention}, that word is not allowed!", delete_after=5)

    if features["Automod"]["Link Filter"] and not is_whitelisted(message.author.id, "automod", "Link Filter"):
        content = message.content.lower()
        if "http://" in content or "https://" in content or ".com" in content:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, links are not allowed!", delete_after=5)


# ---------------- SLASH COMMANDS ----------------
@bot.tree.command(name="enable_guard", description="Enables the server protection guard and shows the configuration.")
async def enable_guard(interaction: discord.Interaction):
    view = GuardView(bot)
    guild_icon_url = interaction.guild.icon.url if interaction.guild.icon else None
    embed = view.create_embed(interaction.guild.name, guild_icon_url)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="disable_guard", description="Disables the server protection guard.")
async def disable_guard(interaction: discord.Interaction):
    global features, whitelist
    for category in features:
        for feature in features[category]:
            features[category][feature] = False
    whitelist = {}
    await interaction.response.send_message("Guard system has been disabled.", ephemeral=True)


@bot.tree.command(name="about", description="Shows information about the bot.")
async def about(interaction: discord.Interaction):
    await interaction.response.send_message("This is a custom bot created to protect your Discord server with antinuke and automod features.", ephemeral=True)


# ---------------- RUN BOT ----------------
bot.run(TOKEN)
