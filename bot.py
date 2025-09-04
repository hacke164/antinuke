import discord
from discord.ext import commands
from discord import app_commands
import datetime

# ------------------- CONFIG -------------------
TOKEN = "YOUR_BOT_TOKEN"  # Replace with your bot token
GUILD_ID = 123456789012345678  # Replace with your server ID
OWNER_ID = 123456789012345678  # Your Discord ID for full access
LOG_CHANNEL_ID = 123456789012345678  # Logs channel
WHITELISTED_ROLES = [111111111111111111]  # Role IDs allowed to manage
WHITELISTED_MEMBERS = [OWNER_ID]  # Members allowed to manage
# ----------------------------------------------

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

# ------------------- HELPERS -------------------
def is_whitelisted(member: discord.Member):
    if member.id in WHITELISTED_MEMBERS:
        return True
    for role in member.roles:
        if role.id in WHITELISTED_ROLES:
            return True
    return False

def role_allows(member: discord.Member, feature: str):
    # feature = 'antinuke' or 'antimod'
    for role in member.roles:
        if feature == "antinuke" and ROLE_ANTINUKE.get(role.id, True):
            return True
        if feature == "antimod" and ROLE_ANTIMOD.get(role.id, True):
            return True
    return False

async def log_event(message: str):
    if LOGGING_ENABLED:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            channel = guild.get_channel(LOG_CHANNEL_ID)
            if channel:
                await channel.send(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

# ------------------- EVENTS -------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(e)

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
@bot.tree.command(name="whitelist_add", description="Add member to whitelist", guild=discord.Object(id=GUILD_ID))
async def whitelist_add(interaction: discord.Interaction, member: discord.Member):
    if member.id not in WHITELISTED_MEMBERS:
        WHITELISTED_MEMBERS.append(member.id)
        await interaction.response.send_message(f"{member} added to whitelist.")
    else:
        await interaction.response.send_message(f"{member} is already whitelisted.")

@bot.tree.command(name="whitelist_remove", description="Remove member from whitelist", guild=discord.Object(id=GUILD_ID))
async def whitelist_remove(interaction: discord.Interaction, member: discord.Member):
    if member.id in WHITELISTED_MEMBERS:
        WHITELISTED_MEMBERS.remove(member.id)
        await interaction.response.send_message(f"{member} removed from whitelist.")
    else:
        await interaction.response.send_message(f"{member} is not whitelisted.")

@bot.tree.command(name="check_whitelist", description="Check if a member is whitelisted", guild=discord.Object(id=GUILD_ID))
async def check_whitelist(interaction: discord.Interaction, member: discord.Member):
    status = is_whitelisted(member)
    await interaction.response.send_message(f"{member} whitelisted: {status}")

# Global toggle
@bot.tree.command(name="toggle_antinuke", description="Enable/Disable AntiNuke", guild=discord.Object(id=GUILD_ID))
async def toggle_antinuke(interaction: discord.Interaction):
    global ANTINUKE_ENABLED
    ANTINUKE_ENABLED = not ANTINUKE_ENABLED
    await interaction.response.send_message(f"AntiNuke Enabled: {ANTINUKE_ENABLED}")

@bot.tree.command(name="toggle_antimod", description="Enable/Disable AntiMod", guild=discord.Object(id=GUILD_ID))
async def toggle_antimod(interaction: discord.Interaction):
    global ANTIMOD_ENABLED
    ANTIMOD_ENABLED = not ANTIMOD_ENABLED
    await interaction.response.send_message(f"AntiMod Enabled: {ANTIMOD_ENABLED}")

@bot.tree.command(name="toggle_logging", description="Enable/Disable Logging", guild=discord.Object(id=GUILD_ID))
async def toggle_logging(interaction: discord.Interaction):
    global LOGGING_ENABLED
    LOGGING_ENABLED = not LOGGING_ENABLED
    await interaction.response.send_message(f"Logging Enabled: {LOGGING_ENABLED}")

# Role-based toggles
@bot.tree.command(name="role_toggle_antinuke", description="Enable/Disable AntiNuke for a role", guild=discord.Object(id=GUILD_ID))
async def role_toggle_antinuke(interaction: discord.Interaction, role: discord.Role):
    current = ROLE_ANTINUKE.get(role.id, True)
    ROLE_ANTINUKE[role.id] = not current
    await interaction.response.send_message(f"Role {role.name} AntiNuke Enabled: {ROLE_ANTINUKE[role.id]}")

@bot.tree.command(name="role_toggle_antimod", description="Enable/Disable AntiMod for a role", guild=discord.Object(id=GUILD_ID))
async def role_toggle_antimod(interaction: discord.Interaction, role: discord.Role):
    current = ROLE_ANTIMOD.get(role.id, True)
    ROLE_ANTIMOD[role.id] = not current
    await interaction.response.send_message(f"Role {role.name} AntiMod Enabled: {ROLE_ANTIMOD[role.id]}")

# ------------------- RUN -------------------
bot.run(TOKEN)
