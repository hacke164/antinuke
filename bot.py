import discord
from discord.ext import commands
import os
import json
from discord import app_commands, Embed, Interaction, ButtonStyle, ui, Permissions
from discord.ui import Button, View
import http.server
import socketserver
import threading

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
            "whitelisted_ids": []
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
intents.members = True  # Required for on_member_join
intents.message_content = True  # Required for message content monitoring
intents.guilds = True  # Required for guild and role info

# Initialize the bot with intents
bot = commands.Bot(command_prefix='!', intents=intents)
bot.config = load_config()

# Define the animated emoji IDs
EMOJI_IDS = {
    "buy": "<a:buy:1414542537938698271>",
    "tick": "<a:tick:1414542503721570345>",
    "welcome": "<a:welcome:1414542454056685631>"
}

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

    # Assign a specific role to new members
    # The role ID is hardcoded as requested by the user.
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

    # Send a welcome message as a DM to the new member
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

# --- Antinuke Module Commands and Logic ---
class AntiNukeView(ui.View):
    """View with buttons for toggling Anti-Nuke features."""
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot = bot_instance
        self.add_item(Button(label="Mass Ban Detection", style=ButtonStyle.blurple, custom_id="mass_ban_btn"))
        self.add_item(Button(label="Mass Kick Detection", style=ButtonStyle.blurple, custom_id="mass_kick_btn"))
        self.add_item(Button(label="Channel Spam Detection", style=ButtonStyle.blurple, custom_id="channel_spam_btn"))
        self.add_item(Button(label="Role Spam Detection", style=ButtonStyle.blurple, custom_id="role_spam_btn"))
        self.add_item(Button(label="Webhook Spam Detection", style=ButtonStyle.blurple, custom_id="webhook_spam_btn"))
        self.add_item(Button(label="Bot Add Detection", style=ButtonStyle.blurple, custom_id="bot_add_btn"))
        self.add_item(Button(label="Role Edit Detection", style=ButtonStyle.blurple, custom_id="role_edit_btn"))
        self.add_item(Button(label="Channel Edit Detection", style=ButtonStyle.blurple, custom_id="channel_edit_btn"))
        self.add_item(Button(label="Role Perms Edit", style=ButtonStyle.blurple, custom_id="role_perms_btn"))
        self.add_item(Button(label="Webhook Creation", style=ButtonStyle.blurple, custom_id="webhook_creation_btn"))
        self.update_buttons()

    def update_buttons(self):
        """Updates button styles based on current config."""
        config = self.bot.config["anti_nuke"]
        for item in self.children:
            if isinstance(item, Button):
                feature_name = item.custom_id.replace("_btn", "")
                is_enabled = config.get(feature_name, False)
                item.style = ButtonStyle.green if is_enabled else ButtonStyle.red
                item.label = f"{'On' if is_enabled else 'Off'}: {feature_name.replace('_', ' ').title()}"

    async def callback(self, interaction: Interaction):
        """Handles button clicks."""
        user = interaction.user
        if not interaction.permissions.administrator:
            await interaction.response.send_message("You must have administrator permissions to use this.", ephemeral=True)
            return

        feature_id = interaction.data['custom_id'].replace("_btn", "")
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
        title=f"{guild.name}™ Anti-Nuke",
        color=0x00aaff
    )
    embed.add_field(name="<a:tick:1414542503721570345> General Status", value=f"Click the buttons below to toggle features.", inline=False)
    
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
        self.add_item(Button(label="Censor Bad Words", style=ButtonStyle.blurple, custom_id="censor_bad_words_btn"))
        self.add_item(Button(label="Spam Detection", style=ButtonStyle.blurple, custom_id="spam_detection_btn"))
        self.add_item(Button(label="Link Spam Detection", style=ButtonStyle.blurple, custom_id="link_spam_detection_btn"))
        self.add_item(Button(label="Invite Link Blocking", style=ButtonStyle.blurple, custom_id="invite_link_blocking_btn"))
        self.add_item(Button(label="Caps Lock Detection", style=ButtonStyle.blurple, custom_id="caps_lock_detection_btn"))
        self.add_item(Button(label="Mention Spam Detection", style=ButtonStyle.blurple, custom_id="mention_spam_detection_btn"))
        self.add_item(Button(label="Sticker Spam Detection", style=ButtonStyle.blurple, custom_id="sticker_spam_detection_btn"))
        self.add_item(Button(label="URL Blocking", style=ButtonStyle.blurple, custom_id="url_blocking_btn"))
        self.add_item(Button(label="File Blocking", style=ButtonStyle.blurple, custom_id="file_blocking_btn"))
        self.add_item(Button(label="Fast Message Typing", style=ButtonStyle.blurple, custom_id="fast_message_typing_btn"))
        self.update_buttons()

    def update_buttons(self):
        """Updates button styles based on current config."""
        config = self.bot.config["auto_mod"]
        for item in self.children:
            if isinstance(item, Button):
                feature_name = item.custom_id.replace("_btn", "")
                is_enabled = config.get(feature_name, False)
                item.style = ButtonStyle.green if is_enabled else ButtonStyle.red
                item.label = f"{'On' if is_enabled else 'Off'}: {feature_name.replace('_', ' ').title()}"

    async def callback(self, interaction: Interaction):
        """Handles button clicks."""
        user = interaction.user
        if not interaction.permissions.administrator:
            await interaction.response.send_message("You must have administrator permissions to use this.", ephemeral=True)
            return

        feature_id = interaction.data['custom_id'].replace("_btn", "")
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
        title=f"{guild.name}™ Auto-Mod",
        color=0x00aaff
    )
    embed.add_field(name="<a:tick:1414542503721570345> General Status", value=f"Click the buttons below to toggle features.", inline=False)
    
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

# --- Whitelisting Commands ---
@bot.tree.command(name="whitelist", description="Add or remove a user from the whitelist.")
@app_commands.describe(member="The member to add/remove.", action="Whether to add or remove the member.")
@app_commands.choices(action=[
    app_commands.Choice(name="add", value="add"),
    app_commands.Choice(name="remove", value="remove")
])
@app_commands.default_permissions(administrator=True)
async def whitelist(interaction: Interaction, member: discord.Member, action: str):
    """Adds or removes a member from the bot's whitelist."""
    whitelisted_ids = bot.config["whitelisted_ids"]
    user_id = str(member.id)

    if action == "add":
        if user_id in whitelisted_ids:
            await interaction.response.send_message(f"{member.mention} is already whitelisted.", ephemeral=True)
        else:
            whitelisted_ids.append(user_id)
            save_config(bot.config)
            await interaction.response.send_message(f"{EMOJI_IDS['tick']} {member.mention} has been added to the whitelist.", ephemeral=True)
    elif action == "remove":
        if user_id not in whitelisted_ids:
            await interaction.response.send_message(f"{member.mention} is not in the whitelist.", ephemeral=True)
        else:
            whitelisted_ids.remove(user_id)
            save_config(bot.config)
            await interaction.response.send_message(f"{EMOJI_IDS['tick']} {member.mention} has been removed from the whitelist.", ephemeral=True)

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

        # Check if a ticket channel already exists for the user
        for channel in guild.channels:
            if channel.name == ticket_channel_name:
                await interaction.response.send_message("You already have an open ticket.", ephemeral=True)
                return

        # Create a new private channel for the ticket
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket_channel = await guild.create_text_channel(ticket_channel_name, overwrites=overwrites)
        
        await interaction.response.send_message(f"Your ticket has been created at {ticket_channel.mention}", ephemeral=True)

        # Send a message inside the ticket channel
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
        title=f"{interaction.guild.name}™ Ticket System",
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
if __name__ == "__main__":
    # Start the web server in a separate thread
    web_server_thread = threading.Thread(target=run_web_server, daemon=True)
    web_server_thread.start()

    # Start the bot
    bot.run(TOKEN)
