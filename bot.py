import discord
from discord.ext import commands
from discord import app_commands
import datetime
import os

# ------------------- CONFIG -------------------
TOKEN = os.environ.get("TOKEN")  # Use Render env variable, or replace with your token directly

# ------------------- INTENTS -------------------
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.bans = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------- FLAGS -------------------
ANTINUKE_ENABLED = True
ANTIMOD_ENABLED = True
LOGGING_ENABLED = True

ROLE_ANTINUKE = {}  # role_id: True/False
ROLE_ANTIMOD = {}   # role_id: True/False

whitelisted_roles = set()
whitelisted_members = set()

log_channel = None  # Will be set dynamically

# ------------------- HELPERS -------------------
def is_whitelisted(member: discord.Member):
    if member.id in whitelisted_members:
        return True
    for role in member.roles:
        if role.id in whitelisted_roles:
            return True
    return False

def role_allows(member: discord.Member, feature: str):
    for role in member.roles:
        if feature == "antinuke" and ROLE_ANTINUKE.get(role.id, True):
            return True
        if feature == "antimod" and ROLE_ANTIMOD.get(role.id, True):
            return True
    return False

async def log_event(message: str):
    if LOGGING_ENABLED and log_channel:
        await log_channel.send(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

# ------------------- EVENTS -------------------
@bot.event
async def on_ready():
    global log_channel
    print(f"Logged in as {bot.user}")

    # Automatically detect the first guild
    if bot.guilds:
        guild = bot.guilds[0]
        print(f"Connected to guild: {guild.name} ({guild.id})")

        # Try to find a log channel named 'bot-logs'
        existing = discord.utils.get(guild.text_channels, name="bot-logs")
        if existing:
            log_channel = existing
        else:
            # Create the channel dynamically
            log_channel = await guild.create_text_channel("bot-logs")
            await log_event("Log channel created dynamically: bot-logs")

    # Sync slash commands globally
    try:
        await bot.tree.sync()
        print("Slash commands synced globally")
    except Exception as e:
        print("Error syncing slash commands:", e)

# Anti-nuke & anti-mod
@bot.event
async def on_member_ban(guild, user):
    if ANTINUKE_ENABLED:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            executor = entry.user
            if not is_whitelisted(executor) and not role_allows(executor, "antinuke"):
                await log_event(f"Unauthorized ban by {executor} on {user}. Removing permissions!")
                try:
                    await executor.edit(roles=[])
                except:
                    pass

@bot.event
async def on_member_remove(member):
    await log_event(f"Member left: {member} ({member.id})")

@bot.event
async def on_member_join(member):
    await log_event(f"New member joined: {member} ({member.id})")

@bot.event
async def on_guild_role_create(role):
    if ANTIMOD_ENABLED:
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
            executor = entry.user
            if not is_whitelisted(executor) and not role_allows(executor, "antimod"):
                await log_event(f"Unauthorized role creation by {executor}. Deleting role {role.name}!")
                await role.delete()

@bot.event
async def on_guild_role_delete(role):
    if ANTIMOD_ENABLED:
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
            executor = entry.user
            if not is_whitelisted(executor) and not role_allows(executor, "antimod"):
                await log_event(f"Unauthorized role deletion by {executor}. Logging!")

@bot.event
async def on_guild_channel_create(channel):
    if ANTIMOD_ENABLED:
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
            executor = entry.user
            if not is_whitelisted(executor) and not role_allows(executor, "antimod"):
                await log_event(f"Unauthorized channel creation by {executor}. Deleting {channel.name}!")
                await channel.delete()

@bot.event
async def on_guild_channel_delete(channel):
    if ANTIMOD_ENABLED:
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            executor = entry.user
            if not is_whitelisted(executor) and not role_allows(executor, "antimod"):
                await log_event(f"Unauthorized channel deletion by {executor}. Logging!")

@bot.event
async def on_guild_update(before, after):
    if ANTIMOD_ENABLED:
        async for entry in after.audit_logs(limit=1, action=discord.AuditLogAction.guild_update):
            executor = entry.user
            if not is_whitelisted(executor) and not role_allows(executor, "antimod"):
                await log_event(f"Unauthorized guild update by {executor}.")

# ------------------- SLASH COMMANDS -------------------
# Whitelist
@bot.tree.command(name="whitelist_add", description="Add member to whitelist")
async def whitelist_add(interaction: discord.Interaction, member: discord.Member):
    whitelisted_members.add(member.id)
    await interaction.response.send_message(f"{member} added to whitelist.")

@bot.tree.command(name="whitelist_remove", description="Remove member from whitelist")
async def whitelist_remove(interaction: discord.Interaction, member: discord.Member):
    whitelisted_members.discard(member.id)
    await interaction.response.send_message(f"{member} removed from whitelist.")

@bot.tree.command(name="check_whitelist", description="Check if a member is whitelisted")
async def check_whitelist(interaction: discord.Interaction, member: discord.Member):
    status = member.id in whitelisted_members
    await interaction.response.send_message(f"{member} whitelisted: {status}")

# Global toggles
@bot.tree.command(name="toggle_antinuke", description="Enable/Disable AntiNuke")
async def toggle_antinuke(interaction: discord.Interaction):
    global ANTINUKE_ENABLED
    ANTINUKE_ENABLED = not ANTINUKE_ENABLED
    await interaction.response.send_message(f"AntiNuke Enabled: {ANTINUKE_ENABLED}")

@bot.tree.command(name="toggle_antimod", description="Enable/Disable AntiMod")
async def toggle_antimod(interaction: discord.Interaction):
    global ANTIMOD_ENABLED
    ANTIMOD_ENABLED = not ANTIMOD_ENABLED
    await interaction.response.send_message(f"AntiMod Enabled: {ANTIMOD_ENABLED}")

@bot.tree.command(name="toggle_logging", description="Enable/Disable Logging")
async def toggle_logging(interaction: discord.Interaction):
    global LOGGING_ENABLED
    LOGGING_ENABLED = not LOGGING_ENABLED
    await interaction.response.send_message(f"Logging Enabled: {LOGGING_ENABLED}")

# Role-based toggles
@bot.tree.command(name="role_toggle_antinuke", description="Enable/Disable AntiNuke for a role")
async def role_toggle_antinuke(interaction: discord.Interaction, role: discord.Role):
    current = ROLE_ANTINUKE.get(role.id, True)
    ROLE_ANTINUKE[role.id] = not current
    await interaction.response.send_message(f"Role {role.name} AntiNuke Enabled: {ROLE_ANTINUKE[role.id]}")

@bot.tree.command(name="role_toggle_antimod", description="Enable/Disable AntiMod for a role")
async def role_toggle_antimod(interaction: discord.Interaction, role: discord.Role):
    current = ROLE_ANTIMOD.get(role.id, True)
    ROLE_ANTIMOD[role.id] = not current
    await interaction.response.send_message(f"Role {role.name} AntiMod Enabled: {ROLE_ANTIMOD[role.id]}")

# ------------------- RUN -------------------
bot.run(TOKEN)
