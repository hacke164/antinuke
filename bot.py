import discord
from discord.ext import commands
import os
import json
from discord import app_commands, Embed, Interaction, ButtonStyle, ui, Permissions
from discord.ui import Button, View
import http.server
import socketserver
import threading
from typing import Union

# --- Configuration and Data Persistence ---
CONFIG_FILE = 'config.json'

def load_config():
    """Loads configuration from a JSON file."""
    if not os.path.exists(CONFIG_FILE):
        return {
            "anti_nuke": {
                "mass_ban_detection": True,
                "mass_kick_detection": True,
                "channel_spam_detection": True,
                "role_spam_detection": True,
                "webhook_spam_detection": True,
                "bot_add_detection": True,
                "role_edit_detection": True,
                "channel_edit_detection": True,
                "role_permission_edit": True,
                "webhook_creation": True
            },
            "auto_mod": {
                "censor_bad_words": True,
                "spam_detection": True,
                "link_spam_detection": True,
                "invite_link_blocking": True,
                "caps_lock_detection": True,
                "mention_spam_detection": True,
                "sticker_spam_detection": True,
                "url_blocking": True,
                "file_blocking": True,
                "fast_message_typing": True
            },
            # New, more powerful permission structure
            "whitelisted_permissions": {}
        }
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(config_data):
    """Saves configuration to a JSON file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)

# --- Bot Initialization ---
# Get the bot token from the environment variable (Render hosting)
TOKEN = os.environ.get('TOKEN')
if not TOKEN:
    print("Error: TOKEN environment variable not set.")
    exit()

# Define bot intents to get the necessary permissions
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

# Initialize the bot with intents
bot = commands.Bot(command_prefix='!', intents=intents)
bot.config = load_config()
bot.bad_words = ["fuck", "shit", "asshole", "bitch"] # A simple list of words to demonstrate

# Define the animated emoji IDs
EMOJI_IDS = {
    "buy": "<a:buy:1414542537938698271>",
    "tick": "<a:tick:1414542503721570345>",
    "welcome": "<a:welcome:1414542454056685631>"
}

# --- Utility Functions ---
def is_whitelisted_for_feature(member_or_role: Union[discord.Member, discord.Role], module: str, feature: str):
    """Checks if a member or role is whitelisted for a specific feature."""
    permissions = bot.config["whitelisted_permissions"]
    target_id = str(member_or_role.id)

    if target_id in permissions:
        if module in permissions[target_id] and feature in permissions[target_id][module]:
            return permissions[target_id][module][feature]
    return False # Default to not whitelisted

# --- Bot Events ---
@bot.event
async def on_ready():
    """Confirms the bot is online and ready."""
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')
    # Sync slash commands with the guilds
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_member_join(member: discord.Member):
    """Handles new members joining the server and assigns a specific role."""
    guild = member.guild
    role_id_to_assign = 1412416423652757556
    role_to_assign = guild.get_role(role_id_to_assign)
    if role_to_assign:
        try:
            await member.add_roles(role_to_assign, reason="Automatically assigned new member role.")
            print(f"Assigned role '{role_to_assign.name}' to {member.name}")
        except discord.Forbidden:
            print(f"Failed to assign role to {member.name}: Bot lacks permissions.")
        except Exception as e:
            print(f"An error occurred while assigning role: {e}")
    else:
        print(f"Role with ID {role_id_to_assign} not found in guild.")
    welcome_embed = Embed(
        title=f"Welcome to {guild.name}!",
        description=f"Welcome {member.mention} to the server! Please make sure to read the rules.",
        color=0x4a90e2
    )
    welcome_embed.set_thumbnail(url=member.display_avatar.url)
    welcome_embed.set_footer(text=f"Member count: {guild.member_count}")
    try:
        await member.send(f"{EMOJI_IDS['welcome']} {member.mention}", embed=welcome_embed)
        print(f"Sent welcome DM to {member.name}")
    except discord.Forbidden:
        print(f"Failed to send welcome DM to {member.name}: User has DMs disabled.")

@bot.event
async def on_message(message: discord.Message):
    """
    A simple demonstration of how the new whitelisting system works.
    If the 'censor bad words' feature is enabled, this will check for bad words,
    but it will bypass the check if the user is whitelisted for that feature.
    """
    if message.author.bot:
        return
    
    if bot.config["auto_mod"]["censor_bad_words"]:
        # Check if the user is whitelisted to bypass this specific feature
        if is_whitelisted_for_feature(message.author, "auto_mod", "censor_bad_words"):
            print(f"User {message.author.name} is whitelisted for 'censor bad words', bypassing check.")
            return

        for word in bot.bad_words:
            if word in message.content.lower():
                await message.delete()
                await message.channel.send(f"Hey {message.author.mention}, that word is not allowed here.", delete_after=5)
                break
    
    await bot.process_commands(message)


# --- Antinuke Module Commands and Logic ---
class AntiNukeView(ui.View):
    """View with buttons for toggling Anti-Nuke features."""
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot = bot_instance
        for feature in bot_instance.config["anti_nuke"].keys():
            self.add_item(Button(label=feature.replace('_', ' ').title(), style=ButtonStyle.blurple, custom_id=f"antinuke_{feature}_btn"))
        self.update_buttons()

    def update_buttons(self):
        """Updates button styles based on current config."""
        config = self.bot.config["anti_nuke"]
        for item in self.children:
            if isinstance(item, Button):
                feature_name = item.custom_id.replace("antinuke_", "").replace("_btn", "")
                is_enabled = config.get(feature_name, False)
                item.style = ButtonStyle.green if is_enabled else ButtonStyle.red
                item.label = f"{'On' if is_enabled else 'Off'}: {feature_name.replace('_', ' ').title()}"

    async def callback(self, interaction: Interaction):
        """Handles button clicks."""
        user = interaction.user
        if not interaction.permissions.administrator:
            await interaction.response.send_message("You must have administrator permissions to use this.", ephemeral=True)
            return
        
        feature_id = interaction.data['custom_id'].replace("antinuke_", "").replace("_btn", "")
        current_state = self.bot.config["anti_nuke"].get(feature_id, False)
        new_state = not current_state
        self.bot.config["anti_nuke"][feature_id] = new_state
        save_config(self.bot.config)

        self.update_buttons()
        embed = create_antinuke_embed(self.bot.config["anti_nuke"], interaction.guild, interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="antinuke", description="Manage the Anti-Nuke module features.")
@app_commands.default_permissions(administrator=True)
async def antinuke(interaction: Interaction):
    """Sends an embed with buttons to manage Anti-Nuke features."""
    embed = create_antinuke_embed(bot.config["anti_nuke"], interaction.guild, interaction.user)
    view = AntiNukeView(bot)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

def create_antinuke_embed(config, guild, targetor=None):
    """Generates the Anti-Nuke embed with the new style."""
    embed = Embed(
        title="EvX Corporation™ Anti-Nuke",
        color=0x00aaff
    )
    embed.add_field(name="<a:tick:1414542503721570345> General Status", value="Click the buttons below to toggle features.", inline=False)
    
    for feature, enabled in config.items():
        status_emoji = "✅" if enabled else "❌"
        embed.add_field(
            name=f"{status_emoji} : {feature.replace('_', ' ').title()}",
            value="",
            inline=False
        )
    
    if targetor:
        embed.add_field(name="Executor", value=f"<@{targetor.id}>", inline=True)
        embed.add_field(name="Target", value=f"<@{targetor.id}>", inline=True)
    
    embed.set_footer(text="Developed by EvX")
    return embed

# --- Automod Module Commands and Logic ---
class AutoModView(ui.View):
    """View with buttons for toggling Auto-Mod features."""
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot = bot_instance
        for feature in bot_instance.config["auto_mod"].keys():
            self.add_item(Button(label=feature.replace('_', ' ').title(), style=ButtonStyle.blurple, custom_id=f"automod_{feature}_btn"))
        self.update_buttons()

    def update_buttons(self):
        """Updates button styles based on current config."""
        config = self.bot.config["auto_mod"]
        for item in self.children:
            if isinstance(item, Button):
                feature_name = item.custom_id.replace("automod_", "").replace("_btn", "")
                is_enabled = config.get(feature_name, False)
                item.style = ButtonStyle.green if is_enabled else ButtonStyle.red
                item.label = f"{'On' if is_enabled else 'Off'}: {feature_name.replace('_', ' ').title()}"

    async def callback(self, interaction: Interaction):
        """Handles button clicks."""
        user = interaction.user
        if not interaction.permissions.administrator:
            await interaction.response.send_message("You must have administrator permissions to use this.", ephemeral=True)
            return

        feature_id = interaction.data['custom_id'].replace("automod_", "").replace("_btn", "")
        current_state = self.bot.config["auto_mod"].get(feature_id, False)
        new_state = not current_state
        self.bot.config["auto_mod"][feature_id] = new_state
        save_config(self.bot.config)

        self.update_buttons()
        embed = create_automod_embed(self.bot.config["auto_mod"], interaction.guild, interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)

@bot.tree.command(name="automod", description="Manage the Auto-Mod module features.")
@app_commands.default_permissions(administrator=True)
async def automod(interaction: Interaction):
    """Sends an embed with buttons to manage Auto-Mod features."""
    embed = create_automod_embed(bot.config["auto_mod"], interaction.guild, interaction.user)
    view = AutoModView(bot)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

def create_automod_embed(config, guild, targetor=None):
    """Generates the Auto-Mod embed with the new style."""
    embed = Embed(
        title="EvX Corporation™ Auto-Mod",
        color=0x00aaff
    )
    embed.add_field(name="<a:tick:1414542503721570345> General Status", value="Click the buttons below to toggle features.", inline=False)
    
    for feature, enabled in config.items():
        status_emoji = "✅" if enabled else "❌"
        embed.add_field(
            name=f"{status_emoji} : {feature.replace('_', ' ').title()}",
            value="",
            inline=False
        )

    if targetor:
        embed.add_field(name="Executor", value=f"<@{targetor.id}>", inline=True)
        embed.add_field(name="Target", value=f"<@{targetor.id}>", inline=True)
    
    embed.set_footer(text="Developed by EvX")
    return embed

# --- Permission Management Commands ---
@bot.tree.command(name="set_permissions", description="Set or clear whitelisted permissions for a member or role.")
@app_commands.describe(
    target="The member or role to modify.",
    module="The module (Anti-Nuke or Auto-Mod).",
    feature="The specific feature to toggle.",
    state="Whether to enable (True) or disable (False) the permission."
)
@app_commands.choices(
    module=[
        app_commands.Choice(name="Anti-Nuke", value="anti_nuke"),
        app_commands.Choice(name="Auto-Mod", value="auto_mod")
    ],
    # Fix: Changed boolean values to strings, as choices only support string, int, or float.
    state=[
        app_commands.Choice(name="Enable (True)", value="true"),
        app_commands.Choice(name="Disable (False)", value="false")
    ]
)
@app_commands.default_permissions(administrator=True)
async def set_permissions(interaction: Interaction, target: Union[discord.Member, discord.Role], module: str, feature: str, state: str):
    """
    Sets a whitelisted permission for a member or role.
    Note: The 'state' parameter is a string due to Discord API limitations
    and is converted to a boolean inside the function.
    """
    # Convert the string state to a boolean
    boolean_state = state == "true"

    if module == "anti_nuke":
        features = list(bot.config["anti_nuke"].keys())
    elif module == "auto_mod":
        features = list(bot.config["auto_mod"].keys())
    else:
        await interaction.response.send_message("Invalid module selected.", ephemeral=True)
        return

    if feature not in features:
        await interaction.response.send_message(f"Feature '{feature}' not found in module '{module}'.", ephemeral=True)
        return

    permissions = bot.config["whitelisted_permissions"]
    target_id = str(target.id)

    if target_id not in permissions:
        permissions[target_id] = {"anti_nuke": {}, "auto_mod": {}}
    
    permissions[target_id][module][feature] = boolean_state
    save_config(bot.config)

    action = "enabled" if boolean_state else "disabled"
    embed = Embed(
        title="Permissions Updated",
        description=f"Permissions for {target.mention} have been updated.",
        color=0x2ecc71
    )
    embed.add_field(
        name=f"{feature.replace('_', ' ').title()}",
        value=f"**{action.capitalize()}** in the `{module.replace('_', ' ').title()}` module.",
        inline=False
    )
    embed.set_footer(text=f"Action requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@set_permissions.autocomplete('feature')
async def feature_autocomplete(interaction: Interaction, current: str):
    """Autocompletes the feature choices based on the module."""
    module = interaction.namespace.module
    if module == "anti_nuke":
        choices = list(bot.config["anti_nuke"].keys())
    elif module == "auto_mod":
        choices = list(bot.config["auto_mod"].keys())
    else:
        return []
    
    return [
        app_commands.Choice(name=f.replace('_', ' ').title(), value=f)
        for f in choices if current.lower() in f.lower()
    ]

@bot.tree.command(name="list_permissions", description="List the whitelisted permissions for a member or role.")
@app_commands.describe(target="The member or role to check.")
@app_commands.default_permissions(administrator=True)
async def list_permissions(interaction: Interaction, target: Union[discord.Member, discord.Role]):
    """Lists all permissions for a member or role."""
    permissions = bot.config["whitelisted_permissions"]
    target_id = str(target.id)

    if target_id not in permissions or (not permissions[target_id]["anti_nuke"] and not permissions[target_id]["auto_mod"]):
        await interaction.response.send_message(f"No custom permissions found for {target.mention}.", ephemeral=True)
        return

    embed = Embed(
        title=f"Whitelisted Permissions for {target.name}",
        description=f"Showing special permissions for {target.mention}.",
        color=0x3498db
    )
    
    # Anti-Nuke Permissions
    antinuke_perms = permissions[target_id].get("anti_nuke", {})
    antinuke_list = []
    for feature, state in antinuke_perms.items():
        status = "✅ Enabled" if state else "❌ Disabled"
        antinuke_list.append(f"`{feature.replace('_', ' ').title()}`: {status}")
    embed.add_field(
        name="Anti-Nuke Permissions",
        value="\n".join(antinuke_list) if antinuke_list else "No custom permissions set.",
        inline=False
    )

    # Auto-Mod Permissions
    automod_perms = permissions[target_id].get("auto_mod", {})
    automod_list = []
    for feature, state in automod_perms.items():
        status = "✅ Enabled" if state else "❌ Disabled"
        automod_list.append(f"`{feature.replace('_', ' ').title()}`: {status}")
    embed.add_field(
        name="Auto-Mod Permissions",
        value="\n".join(automod_list) if automod_list else "No custom permissions set.",
        inline=False
    )
    
    embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.avatar.url)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- Embed Creation Commands ---
@bot.tree.command(name="create_embed", description="Creates a custom embed message.")
@app_commands.describe(
    title="The title of the embed.",
    description="The main text of the embed.",
    color="The color of the embed (hex code, e.g., 0x3498db).",
    url="A URL for the title link.",
    image_url="A URL for the main image.",
    thumbnail_url="A URL for the thumbnail image."
)
@app_commands.default_permissions(administrator=True)
async def create_embed(interaction: Interaction, title: str, description: str, color: int = 0x3498db, url: str = None, image_url: str = None, thumbnail_url: str = None):
    """Creates a custom embed with provided details."""
    try:
        embed = Embed(
            title=title,
            description=description,
            color=color,
            url=url
        )
        if image_url:
            embed.set_image(url=image_url)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)

        embed.set_footer(text=f"Embed created by {interaction.user.name}", icon_url=interaction.user.avatar.url)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

# --- About Me Commands and Logic ---
class AboutView(ui.View):
    """View with a button to show developer information."""
    def __init__(self):
        super().__init__(timeout=180)
        
    @ui.button(label="Developer", style=ButtonStyle.primary)
    async def developer_button(self, interaction: Interaction, button: ui.Button):
        developer_embed = Embed(
            title="About the Developer",
            description="""
            EvX is a professional developer specializing in creating high-quality, reliable, and secure Discord bots. 
            He has a strong passion for coding and building tools that help communities grow and stay protected.
            
            This bot is a testament to his expertise and dedication.
            """,
            color=0x00aaff
        )
        developer_embed.set_footer(text="Thank you for supporting EvX!")
        await interaction.response.send_message(embed=developer_embed, ephemeral=True)

@bot.tree.command(name="about", description="Get information about the bot and the developer.")
async def about(interaction: Interaction):
    """Sends an embed with information about the bot."""
    about_embed = Embed(
        title="About EvX Corporation Bot",
        description="A powerful bot for server security and moderation, with features like Anti-Nuke, Auto-Mod, and custom embed creation.",
        color=0x4a90e2
    )
    about_embed.set_thumbnail(url=bot.user.avatar.url)
    about_embed.set_footer(text="Developed to keep your server safe.")
    
    view = AboutView()
    await interaction.response.send_message(embed=about_embed, view=view)


# --- Ticket Embed Creation ---
class TicketButton(ui.View):
    """View with a button to create a ticket."""
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot = bot_instance
        self.add_item(Button(label="Create Ticket", style=ButtonStyle.blurple, custom_id="create_ticket_btn"))

    @ui.button(label="Create Ticket", style=ButtonStyle.blurple, custom_id="create_ticket_btn")
    async def create_ticket(self, interaction: Interaction, button: Button):
        """Creates a ticket channel for the user."""
        guild = interaction.guild
        member = interaction.user
        ticket_channel_name = f"ticket-{member.name.lower()}-{member.discriminator}".replace("#", "")

        for channel in guild.channels:
            if channel.name == ticket_channel_name:
                await interaction.response.send_message("You already have an open ticket.", ephemeral=True)
                return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket_channel = await guild.create_text_channel(ticket_channel_name, overwrites=overwrites)
        
        await interaction.response.send_message(f"Your ticket has been created at {ticket_channel.mention}", ephemeral=True)

        ticket_embed = Embed(
            title=f"New Ticket from {member.name}",
            description="Our team will be with you shortly. Please explain your issue.",
            color=0x2ecc71
        )
        ticket_embed.set_footer(text=f"Ticket ID: {ticket_channel.id}")
        
        close_button_view = ui.View()
        close_button_view.add_item(Button(label="Close Ticket", style=ButtonStyle.red, custom_id="close_ticket_btn"))

        await ticket_channel.send(member.mention, embed=ticket_embed, view=close_button_view)

    @ui.button(label="Close Ticket", style=ButtonStyle.red, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: Interaction, button: Button):
        """Deletes the ticket channel."""
        channel = interaction.channel
        if channel.name.startswith("ticket-"):
            await interaction.response.send_message(f"{EMOJI_IDS['tick']} Closing this ticket in 5 seconds...")
            await discord.utils.sleep_until(discord.utils.utcnow() + discord.Timedelta(seconds=5))
            await channel.delete()
        else:
            await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)

@bot.tree.command(name="ticket_panel", description="Sends a ticket creation embed with a button.")
@app_commands.default_permissions(administrator=True)
async def ticket_panel(interaction: Interaction):
    """Sends a ticket panel with a button to create tickets."""
    ticket_embed = Embed(
        title="EvX Corporation™ Ticket System",
        description="Need help? Click the button below to create a private support ticket.",
        color=0x00aaff
    )
    ticket_embed.set_footer(text="Developed by EvX")

    view = TicketButton(bot)
    await interaction.response.send_message(embed=ticket_embed, view=view)

# --- Web Server for Render Deployment ---
class Handler(http.server.BaseHTTPRequestHandler):
    """Simple HTTP request handler."""
    def do_GET(self):
        """Responds to GET requests."""
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(bytes("<h1>Bot is running!</h1>", "utf-8"))

def run_web_server():
    """Runs a simple web server to satisfy Render's port check."""
    PORT = int(os.environ.get("PORT", 8080))
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving at port {PORT}")
        httpd.serve_forever()

# --- Start the bot and web server ---
@bot.event
async def on_connect():
    """Event that runs when the bot connects to Discord."""
    bot.add_view(AntiNukeView(bot))
    bot.add_view(AutoModView(bot))

if __name__ == "__main__":
    web_server_thread = threading.Thread(target=run_web_server, daemon=True)
    web_server_thread.start()
    bot.run(TOKEN)
