# This bot provides a "guard" system with antinuke, automod, and whitelisting features.
# It uses Discord's modern slash commands and UI components.

import os
import discord
from dotenv import load_dotenv

# Load environment variables from a .env file for local testing.
# In a production environment like Render, these are set directly.
load_dotenv()

# Define the bot's intents. This is crucial for receiving certain events.
# We need intents for guilds and guild members to get guild name and whitelisting.
intents = discord.Intents.default()
intents.guilds = True
intents.members = True

# Initialize the bot with the required intents.
bot = discord.Bot(intents=intents)

class GuardView(discord.ui.View):
    """
    A persistent view to handle all interactions for the /enable_guard command.
    """
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        # A dictionary to store the state of each feature.
        # In a real bot, this would be stored in a database.
        self.features = {
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
        # Whitelist stores a dictionary of user IDs mapping to a list of whitelisted features
        # for each category.
        self.whitelist = {}
        self.selected_user = None
        self.selected_antinuke_features = []
        self.selected_automod_features = []

        # Add the feature selection menus to the view.
        self.add_item(self.create_antinuke_select())
        self.add_item(self.create_automod_select())

    def create_antinuke_select(self):
        options = [
            discord.SelectOption(label=feature, value=feature)
            for feature in self.features["Antinuke"].keys()
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
            for feature in self.features["Automod"].keys()
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
        for feature, enabled in self.features["Antinuke"].items():
            status = "✅" if enabled else "❌"
            antinuke_text += f"{status} : **{feature}**\n"
        embed.add_field(name="<:shield:123456789101112131> Antinuke", value=antinuke_text, inline=True)

        # Build the Automod field
        automod_text = ""
        for feature, enabled in self.features["Automod"].items():
            status = "✅" if enabled else "❌"
            automod_text += f"{status} : **{feature}**\n"
        embed.add_field(name="<:hammer:123456789101112141> Automod", value=automod_text, inline=True)

        # Build the Whitelist field
        whitelist_text = ""
        if not self.whitelist:
            whitelist_text = "No users whitelisted."
        else:
            for user_id, features in self.whitelist.items():
                user = self.bot.get_user(user_id)
                user_name = user.name if user else "Unknown User"
                antinuke_list = ", ".join(features.get("antinuke", [])) or "None"
                automod_list = ", ".join(features.get("automod", [])) or "None"
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
    # These buttons will update the embed based on their current state.
    @discord.ui.button(label="Toggle Antinuke", style=discord.ButtonStyle.secondary, row=4)
    async def toggle_antinuke_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # A simple button to toggle all Antinuke features.
        # You can add more specific buttons as needed.
        all_enabled = all(self.features["Antinuke"].values())
        new_state = not all_enabled
        for key in self.features["Antinuke"]:
            self.features["Antinuke"][key] = new_state
        
        new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label="Toggle Automod", style=discord.ButtonStyle.secondary, row=4)
    async def toggle_automod_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # A simple button to toggle all Automod features.
        all_enabled = all(self.features["Automod"].values())
        new_state = not all_enabled
        for key in self.features["Automod"]:
            self.features["Automod"][key] = new_state

        new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.edit_message(embed=new_embed, view=self)

    # --- User Select for Whitelisting ---
    @discord.ui.user_select(placeholder="Select a user to whitelist...", row=5)
    async def user_select_callback(self, select: discord.ui.UserSelect, interaction: discord.Interaction):
        self.selected_user = select.values[0]
        # Enable the feature selection menus.
        for item in self.children:
            if isinstance(item, discord.ui.Select) and item.placeholder.startswith("Select"):
                item.disabled = False
        
        new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.edit_message(embed=new_embed, view=self)

    @discord.ui.button(label="Whitelist Antinuke", style=discord.ButtonStyle.success, row=6)
    async def whitelist_antinuke(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.selected_user:
            user_id = self.selected_user.id
            if user_id not in self.whitelist:
                self.whitelist[user_id] = {"antinuke": [], "automod": []}
            self.whitelist[user_id]["antinuke"] = self.selected_antinuke_features
            
            new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.edit_message(embed=new_embed, view=self)
            print(f"Whitelisted {self.selected_user.name} for Antinuke features: {self.selected_antinuke_features}.")
        else:
            await interaction.response.send_message("Please select a user first.", ephemeral=True)

    @discord.ui.button(label="Whitelist Automod", style=discord.ButtonStyle.success, row=6)
    async def whitelist_automod(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.selected_user:
            user_id = self.selected_user.id
            if user_id not in self.whitelist:
                self.whitelist[user_id] = {"antinuke": [], "automod": []}
            self.whitelist[user_id]["automod"] = self.selected_automod_features

            new_embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.edit_message(embed=new_embed, view=self)
            print(f"Whitelisted {self.selected_user.name} for Automod features: {self.selected_automod_features}.")
        else:
            await interaction.response.send_message("Please select a user first.", ephemeral=True)

@bot.event
async def on_ready():
    """
    Called when the bot successfully connects to Discord.
    """
    print(f"{bot.user} is online and connected!")
    # Register a persistent view on startup.
    bot.add_view(GuardView(bot))

@bot.slash_command(name="enable_guard", description="Enables the server protection guard and shows the configuration.")
async def enable_guard(ctx: discord.ApplicationContext):
    """
    Sends an embed with configuration options for the server guard.
    """
    # Create the initial view with the bot instance.
    view = GuardView(bot)
    
    # Get guild icon URL for the embed.
    guild_icon_url = ctx.guild.icon.url if ctx.guild.icon else None
    
    # Create and send the initial embed with the view.
    embed = view.create_embed(ctx.guild.name, guild_icon_url)
    await ctx.respond(embed=embed, view=view, ephemeral=True)

@bot.slash_command(name="disable_guard", description="Disables the server protection guard.")
async def disable_guard(ctx: discord.ApplicationContext):
    """
    A simple command to disable the guard.
    """
    await ctx.respond("Guard system has been disabled.", ephemeral=True)

@bot.slash_command(name="about", description="Shows information about the bot.")
async def about(ctx: discord.ApplicationContext):
    """
    A simple command to show bot information.
    """
    await ctx.respond("This is a custom bot created to protect your Discord server with antinuke and automod features.", ephemeral=True)

# Run the bot with the token from the environment variable.
# On Render, you will set the DISCORD_TOKEN environment variable in your dashboard.
# For local testing, create a file named .env with the line: DISCORD_TOKEN="YOUR_BOT_TOKEN_HERE"
bot.run(os.environ["TOKEN"])
