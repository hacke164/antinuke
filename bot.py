# This bot provides a "guard" system with antinuke, automod, and whitelisting features.
# It uses Discord's modern slash commands and UI components.

import os
import discord
import asyncio

# Define the bot's intents. This is crucial for receiving certain events.
# We need more intents now for the new event listeners.
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True  # Required to read message content for Automod
intents.emojis_and_stickers = True # Fixed this line from the original error
intents.integrations = True
intents.webhooks = True
intents.guild_messages = True
intents.guild_reactions = True
intents.guild_members = True
intents.bans = True
intents.guild_messages = True
intents.guild_messages = True
intents.presences = False
intents.typing = False
intents.integrations = True
intents.webhooks = True
intents.invites = True

# Initialize the bot with the required intents.
bot = discord.Bot(intents=intents)

# A dictionary to store the state of each feature and the whitelist.
# In a production bot, this would be stored in a database.
# Using a global dictionary for simplicity in this example.
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

# The list of bad words for the Automod feature.
BAD_WORDS = [
    "badword1",
    "badword2",
    "anotherbadword",
    "swear"
]

class GuardView(discord.ui.View):
    """
    A persistent view to handle all interactions for the /enable_guard command.
    """
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

    # Helper function to generate the embed based on the current state.
    def create_embed(self, guild_name, guild_icon_url):
        embed = discord.Embed(
            title=f"{guild_name} Guard System",
            color=discord.Color.blue()
        )
        if guild_icon_url:
            embed.set_thumbnail(url=guild_icon_url)

        # Build the Antinuke field
        antinuke_text = ""
        for feature, enabled in features["Antinuke"].items():
            status = "✅" if enabled else "❌"
            antinuke_text += f"{status} : **{feature}**\n"
        embed.add_field(name="<:shield:123456789101112131> Antinuke", value=antinuke_text, inline=True)

        # Build the Automod field
        automod_text = ""
        for feature, enabled in features["Automod"].items():
            status = "✅" if enabled else "❌"
            automod_text += f"{status} : **{feature}**\n"
        embed.add_field(name="<:hammer:123456789101112141> Automod", value=automod_text, inline=True)

        # Build the Whitelist field
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

        embed.add_field(name="<:plus:123456789101112151> User Whitelist", value=whitelist_text, inline=False)
        
        embed.set_footer(text="Powered by EvX Official")
        
        # Add a preview of the current selection.
        if self.selected_user:
            preview_text = f"**Selected User:** {self.selected_user.mention}\n"
            preview_text += f"**Antinuke Features:** {', '.join(self.selected_antinuke_features) or 'None'}\n"
            preview_text += f"**Automod Features:** {', '.join(self.selected_automod_features) or 'None'}"
            embed.add_field(name="Current Whitelist Selection", value=preview_text, inline=False)

        return embed

    # --- Buttons for Toggling Features ---
    @discord.ui.button(label="Toggle Antinuke", style=discord.ButtonStyle.secondary, row=4)
    async def toggle_antinuke_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        all_enabled = all(features["Antinuke"].values())
        new_state = not all_enabled
        for key in features["Antinuke"]:
            features["Antinuke"][key] = new_state
        
        new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label="Toggle Automod", style=discord.ButtonStyle.secondary, row=4)
    async def toggle_automod_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        all_enabled = all(features["Automod"].values())
        new_state = not all_enabled
        for key in features["Automod"]:
            features["Automod"][key] = new_state

        new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.edit_message(embed=new_embed, view=self)

    # --- User Select for Whitelisting ---
    @discord.ui.user_select(placeholder="Select a user to whitelist...", row=5)
    async def user_select_callback(self, select: discord.ui.UserSelect, interaction: discord.Interaction):
        self.selected_user = select.values[0]
        for item in self.children:
            if isinstance(item, discord.ui.Select) and item.placeholder.startswith("Select"):
                item.disabled = False
        
        new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label="Whitelist Antinuke", style=discord.ButtonStyle.success, row=6)
    async def whitelist_antinuke(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.selected_user:
            user_id = self.selected_user.id
            if user_id not in whitelist:
                whitelist[user_id] = {"antinuke": [], "automod": []}
            whitelist[user_id]["antinuke"] = self.selected_antinuke_features
            
            new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.edit_message(embed=new_embed, view=self)
            print(f"Whitelisted {self.selected_user.name} for Antinuke features: {self.selected_antinuke_features}.")
        else:
            await interaction.response.send_message("Please select a user first.", ephemeral=True)

    @discord.ui.button(label="Whitelist Automod", style=discord.ButtonStyle.success, row=6)
    async def whitelist_automod(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.selected_user:
            user_id = self.selected_user.id
            if user_id not in whitelist:
                whitelist[user_id] = {"antinuke": [], "automod": []}
            whitelist[user_id]["automod"] = self.selected_automod_features

            new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.edit_message(embed=new_embed, view=self)
            print(f"Whitelisted {self.selected_user.name} for Automod features: {self.selected_automod_features}.")
        else:
            await interaction.response.send_message("Please select a user first.", ephemeral=True)

@bot.event
async def on_ready():
    """Called when the bot successfully connects to Discord."""
    print(f"{bot.user} is online and connected!")
    bot.add_view(GuardView(bot))

# --- Antinuke Event Handlers ---
def is_whitelisted(user_id, category, feature):
    """Helper to check if a user is whitelisted for a specific feature."""
    if user_id in whitelist:
        return feature in whitelist[user_id].get(category, [])
    return False

async def get_audit_log_user(guild, event_type, target_id):
    """
    Tries to find the user responsible for an event using the audit log.
    This is the core of the antinuke system.
    """
    await asyncio.sleep(1) # Wait a moment for audit log to be updated
    async for entry in guild.audit_logs(limit=2, action=event_type):
        if entry.target.id == target_id:
            return entry.user
    return None

@bot.event
async def on_member_ban(guild, user):
    if not features["Antinuke"]["Ban"]: return
    
    # Get the user who performed the ban from the audit log
    ban_user = await get_audit_log_user(guild, discord.AuditLogAction.ban, user.id)
    if ban_user and not is_whitelisted(ban_user.id, "antinuke", "Ban"):
        await guild.unban(user, reason="Antinuke: Unauthorized ban.")
        # Optionally, kick/ban the malicious user and send an alert
        # await ban_user.kick(reason="Antinuke: Unauthorized ban.")
        print(f"Antinuke: Unbanned {user.name}. Ban was initiated by unauthorized user {ban_user.name}.")

@bot.event
async def on_member_remove(member):
    if not features["Antinuke"]["Kick"]: return
    
    # Check audit log for kick action
    kick_user = await get_audit_log_user(member.guild, discord.AuditLogAction.kick, member.id)
    if kick_user and not is_whitelisted(kick_user.id, "antinuke", "Kick"):
        # You cannot un-kick a user, so the action here is to punish the kicker
        # await kick_user.kick(reason="Antinuke: Unauthorized kick.")
        print(f"Antinuke: Unauthorized kick of {member.name} by {kick_user.name}. Action not reverted.")

@bot.event
async def on_guild_channel_create(channel):
    if not features["Antinuke"]["Channel Create"]: return
    
    # Check audit log for channel creation
    create_user = await get_audit_log_user(channel.guild, discord.AuditLogAction.channel_create, channel.id)
    if create_user and not is_whitelisted(create_user.id, "antinuke", "Channel Create"):
        await channel.delete(reason="Antinuke: Unauthorized channel creation.")
        print(f"Antinuke: Deleted unauthorized channel {channel.name} created by {create_user.name}.")

@bot.event
async def on_guild_channel_delete(channel):
    if not features["Antinuke"]["Channel Delete"]: return
    
    delete_user = await get_audit_log_user(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
    if delete_user and not is_whitelisted(delete_user.id, "antinuke", "Channel Delete"):
        # Recreate the channel with the original name and category, but permissions cannot be restored
        # automatically. You would need to store them beforehand.
        new_channel = await channel.guild.create_text_channel(
            name=channel.name, category=channel.category
        )
        print(f"Antinuke: Recreated channel {new_channel.name} after unauthorized deletion by {delete_user.name}.")

@bot.event
async def on_guild_channel_update(before, after):
    if not features["Antinuke"]["Channel Update"]: return

    update_user = await get_audit_log_user(after.guild, discord.AuditLogAction.channel_update, after.id)
    if update_user and not is_whitelisted(update_user.id, "antinuke", "Channel Update"):
        # Revert the channel back to its original state.
        await after.edit(name=before.name, topic=before.topic, category=before.category,
                         overwrites=before.overwrites, reason="Antinuke: Unauthorized channel update.")
        print(f"Antinuke: Reverted channel {after.name} after unauthorized update by {update_user.name}.")


# --- Automod Event Handlers ---
@bot.event
async def on_message(message):
    if message.author.bot: return
    
    # Bad Words Filter
    if features["Automod"]["Bad Words Filter"] and not is_whitelisted(message.author.id, "automod", "Bad Words Filter"):
        content = message.content.lower()
        if any(word in content for word in BAD_WORDS):
            await message.delete()
            await message.channel.send(f"{message.author.mention}, that word is not allowed!", delete_after=5)

    # Link Filter
    if features["Automod"]["Link Filter"] and not is_whitelisted(message.author.id, "automod", "Link Filter"):
        content = message.content.lower()
        if "http://" in content or "https://" in content or ".com" in content:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, links are not allowed!", delete_after=5)
            
    # Mention Spam Filter
    if features["Automod"]["Mention Spam Filter"] and not is_whitelisted(message.author.id, "automod", "Mention Spam Filter"):
        if len(message.mentions) > 5: # Limit to 5 mentions per message
            await message.delete()
            await message.channel.send(f"{message.author.mention}, you are mentioning too many people!", delete_after=5)


@bot.slash_command(name="enable_guard", description="Enables the server protection guard and shows the configuration.")
async def enable_guard(ctx: discord.ApplicationContext):
    view = GuardView(bot)
    guild_icon_url = ctx.guild.icon.url if ctx.guild.icon else None
    embed = view.create_embed(ctx.guild.name, guild_icon_url)
    await ctx.respond(embed=embed, view=view, ephemeral=True)

@bot.slash_command(name="disable_guard", description="Disables the server protection guard.")
async def disable_guard(ctx: discord.ApplicationContext):
    global features, whitelist
    for category in features:
        for feature in features[category]:
            features[category][feature] = False
    whitelist = {}
    await ctx.respond("Guard system has been disabled.", ephemeral=True)

@bot.slash_command(name="about", description="Shows information about the bot.")
async def about(ctx: discord.ApplicationContext):
    await ctx.respond("This is a custom bot created to protect your Discord server with antinuke and automod features.", ephemeral=True)

# Run the bot with the token from the environment variable.
bot.run(os.environ["TOKEN"])
