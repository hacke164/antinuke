import discord
from discord.ext import commands
from discord import app_commands, utils
import datetime
import os
import asyncio
from aiohttp import web

# ------------------- CONFIG -------------------
TOKEN = os.environ.get("TOKEN")

# ------------------- INTENTS -------------------
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.bans = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------- FEATURES AND TOGGLES -------------------
ANTINUKE_ENABLED = True
ANTIMOD_ENABLED = True
LOGGING_ENABLED = True

# Sub-features for Anti-Nuke
ANTINUKE_SUBFEATURES = {
    "ban": True,
    "kick": True,
    "prune": True,
    "bot_add": True
}

# Sub-features for Anti-Mod
ANTIMOD_SUBFEATURES = {
    "server_update": True,
    "member_role_update": True,
    "channel_create": True,
    "channel_delete": True,
    "channel_update": True,
    "role_create": True,
    "role_delete": True,
    "role_update": True,
    "mention_everyone": True,
    "webhook_management": True,
    "emojis_stickers_management": True
}

# Role-based toggles for main features
ROLE_ANTINUKE = {}  # role_id: True/False
ROLE_ANTIMOD = {}  # role_id: True/False

# Whitelist
whitelisted_roles = set()
whitelisted_members = set()

log_channel = None

# ------------------- HELPERS -------------------
def is_whitelisted(member: discord.Member):
    """Checks if a member or any of their roles are whitelisted."""
    if member.id in whitelisted_members:
        return True
    for role in member.roles:
        if role.id in whitelisted_roles:
            return True
    return False

def is_feature_enabled(category: str, feature: str):
    """Checks if a specific sub-feature is enabled."""
    if category == "antinuke":
        return ANTINUKE_ENABLED and ANTINUKE_SUBFEATURES.get(feature, True)
    elif category == "antimod":
        return ANTIMOD_ENABLED and ANTIMOD_SUBFEATURES.get(feature, True)
    return False

def role_allows(member: discord.Member, feature: str):
    """Checks if a member's role allows them to bypass a feature."""
    for role in member.roles:
        if feature == "antinuke" and ROLE_ANTINUKE.get(role.id, True):
            return True
        if feature == "antimod" and ROLE_ANTIMOD.get(role.id, True):
            return True
    return False

async def log_event(guild_name: str, guild_icon_url: str, title: str, description: str, color: discord.Color = discord.Color.blue()):
    """Logs an event to the designated log channel using an embed."""
    if LOGGING_ENABLED and log_channel:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text=f"Bot | Server: {guild_name}", icon_url=guild_icon_url)
        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            print(f"Failed to send log embed to {log_channel.name} due to missing permissions.")

async def punish_executor(executor: discord.Member):
    """Removes all roles from an unauthorized executor and logs it."""
    guild = executor.guild
    punishment_description = f"Attempted to remove all roles from {executor.mention} ({executor.id})."
    try:
        if executor.roles: # Check if the member has any roles
            await executor.edit(roles=[])
            punishment_description += " Roles successfully removed."
        else:
            punishment_description += " No roles to remove."
        await log_event(
            guild.name,
            guild.icon.url if guild.icon else None,
            "Punishment Issued",
            f"Unauthorized action by {executor.mention}.\n{punishment_description}",
            discord.Color.red()
        )
    except discord.Forbidden:
        await log_event(
            guild.name,
            guild.icon.url if guild.icon else None,
            "Punishment Failed",
            f"Failed to remove roles from {executor.mention} due to missing permissions.",
            discord.Color.orange()
        )
    except Exception as e:
        await log_event(
            guild.name,
            guild.icon.url if guild.icon else None,
            "Punishment Error",
            f"An unexpected error occurred while punishing {executor.mention}: {e}",
            discord.Color.orange()
        )

# ------------------- EVENTS -------------------
@bot.event
async def on_ready():
    global log_channel
    print(f"Logged in as {bot.user}")

    if bot.guilds:
        guild = bot.guilds[0]
        print(f"Connected to guild: {guild.name} ({guild.id})")

        existing = discord.utils.get(guild.text_channels, name="bot-logs")
        if existing:
            log_channel = existing
        else:
            try:
                log_channel = await guild.create_text_channel("bot-logs")
                await log_event(
                    guild.name,
                    guild.icon.url if guild.icon else None,
                    "Log Channel Initialized",
                    "Log channel created dynamically: `bot-logs`",
                    discord.Color.green()
                )
            except discord.Forbidden:
                print("Could not create 'bot-logs' channel due to missing permissions.")

    try:
        await bot.tree.sync()
        print("Slash commands synced globally")
    except Exception as e:
        print("Error syncing slash commands:", e)

@bot.event
async def on_member_join(member):
    # Emojis from the provided screenshot
    catty_emoji = "<:catty:1413454910372184086>"
    tick_emoji = "<:tick:1413454800141418626>"
    
    role_id = 1412416423652757556
    guild = member.guild
    role_to_assign = discord.utils.get(guild.roles, id=role_id)

    if role_to_assign:
        try:
            await member.add_roles(role_to_assign)
            await log_event(
                guild.name,
                guild.icon.url if guild.icon else None,
                "New Member Joined",
                f"Assigned role {role_to_assign.mention} to new member {member.mention} ({member.id}).",
                discord.Color.blue()
            )

            # Send a welcome message to the user's DMs
            welcome_embed = discord.Embed(
                title=f"Welcome to {guild.name}!",
                description=f"Hey there, {member.mention}! {catty_emoji} We're thrilled to have you here.\n\n"
                            f"Here's what I've done for you:\n"
                            f"{tick_emoji} Assigned you the role: **{role_to_assign.name}**\n"
                            f"{tick_emoji} Made sure you're safe by enabling our Anti-Nuke system.",
                color=discord.Color.from_rgb(0, 150, 255),
                timestamp=datetime.datetime.now()
            )
            welcome_embed.set_thumbnail(url=member.display_avatar.url)
            welcome_embed.set_footer(text=f"Bot | Server: {guild.name}", icon_url=guild.icon.url if guild.icon else None)

            try:
                await member.send(embed=welcome_embed)
                await log_event(
                    guild.name,
                    guild.icon.url if guild.icon else None,
                    "Welcome Message Sent",
                    f"Welcome message sent to {member.mention} via DM.",
                    discord.Color.green()
                )
            except discord.Forbidden:
                await log_event(
                    guild.name,
                    guild.icon.url if guild.icon else None,
                    "Welcome Message Failed",
                    f"Failed to send welcome message to {member.mention} because their DMs are closed.",
                    discord.Color.orange()
                )

        except discord.Forbidden:
            await log_event(
                guild.name,
                guild.icon.url if guild.icon else None,
                "Role Assignment Failed",
                f"Failed to assign role {role_to_assign.mention} to {member.mention} due to insufficient permissions.",
                discord.Color.orange()
            )
        except Exception as e:
            await log_event(
                guild.name,
                guild.icon.url if guild.icon else None,
                "Role Assignment Error",
                f"An unexpected error occurred while assigning a role to {member.mention}: {e}",
                discord.Color.red()
            )
    else:
        await log_event(
            guild.name,
            guild.icon.url if guild.icon else None,
            "Role Not Found",
            f"Could not find role with ID `{role_id}`. Please check if the role exists.",
            discord.Color.red()
        )

@bot.event
async def on_audit_log_entry_create(entry):
    executor = entry.user
    if executor == bot.user:
        return
    if is_whitelisted(executor) or role_allows(executor, "antinuke") or role_allows(executor, "antimod"):
        return
    guild = entry.guild
    
    action_map = {
        discord.AuditLogAction.kick: ("antinuke", "kick", "Unauthorized Kick"),
        discord.AuditLogAction.prune: ("antinuke", "prune", "Unauthorized Prune"),
        discord.AuditLogAction.bot_add: ("antinuke", "bot_add", "Unauthorized Bot Add"),
        discord.AuditLogAction.guild_update: ("antimod", "server_update", "Unauthorized Server Update"),
        discord.AuditLogAction.member_role_update: ("antimod", "member_role_update", "Unauthorized Member Role Update"),
        discord.AuditLogAction.webhook_create: ("antimod", "webhook_management", "Unauthorized Webhook Create"),
        discord.AuditLogAction.webhook_update: ("antimod", "webhook_management", "Unauthorized Webhook Update"),
        discord.AuditLogAction.webhook_delete: ("antimod", "webhook_management", "Unauthorized Webhook Delete"),
        discord.AuditLogAction.emoji_create: ("antimod", "emojis_stickers_management", "Unauthorized Emoji Create"),
        discord.AuditLogAction.emoji_update: ("antimod", "emojis_stickers_management", "Unauthorized Emoji Update"),
        discord.AuditLogAction.sticker_create: ("antimod", "emojis_stickers_management", "Unauthorized Sticker Create"),
        discord.AuditLogAction.sticker_update: ("antimod", "emojis_stickers_management", "Unauthorized Sticker Update")
    }

    action_info = action_map.get(entry.action)
    if not action_info:
        return

    category, feature_name, log_title = action_info

    if is_feature_enabled(category, feature_name):
        description = f"Executor: {executor.mention} ({executor.id})\nTarget: {entry.target}\nAction: {entry.action.name}"
        await log_event(guild.name, guild.icon.url if guild.icon else None, log_title, description, discord.Color.red())
        await punish_executor(executor)

        if entry.action == discord.AuditLogAction.webhook_create and entry.target:
            try:
                await entry.target.delete()
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Reverted Webhook Create", f"Deleted unauthorized webhook: {entry.target.name}", discord.Color.green())
            except discord.Forbidden:
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Failed to Revert Webhook Create", f"Could not delete webhook {entry.target.name} due to permissions.", discord.Color.orange())

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    if not is_feature_enabled("antinuke", "ban"):
        return

    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        executor = entry.user
        if executor == bot.user:
            return
        if not is_whitelisted(executor) and not role_allows(executor, "antinuke"):
            description = f"Executor: {executor.mention} ({executor.id})\nTarget: {user.mention} ({user.id})"
            await log_event(guild.name, guild.icon.url if guild.icon else None, "Unauthorized Ban", description, discord.Color.red())
            await punish_executor(executor)

@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
        executor = entry.user
        if executor == bot.user:
            return
        if not is_whitelisted(executor) and not role_allows(executor, "antinuke"):
            if is_feature_enabled("antinuke", "kick"):
                description = f"Executor: {executor.mention} ({executor.id})\nTarget: {member.mention} ({member.id})"
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Unauthorized Kick", description, discord.Color.red())
                await punish_executor(executor)
    
    await log_event(guild.name, guild.icon.url if guild.icon else None, "Member Left", f"Member: {member.mention} ({member.id})", discord.Color.light_grey())


@bot.event
async def on_guild_role_create(role: discord.Role):
    if not is_feature_enabled("antimod", "role_create"):
        return
    guild = role.guild

    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
        executor = entry.user
        if executor == bot.user:
            return
        if not is_whitelisted(executor) and not role_allows(executor, "antimod"):
            description = f"Executor: {executor.mention} ({executor.id})\nCreated Role: {role.mention} ({role.id})"
            await log_event(guild.name, guild.icon.url if guild.icon else None, "Unauthorized Role Creation", description, discord.Color.red())
            await punish_executor(executor)
            try:
                await role.delete(reason="Unauthorized role creation detected by AntiMod.")
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Role Deleted", f"Deleted unauthorized role: {role.mention}", discord.Color.green())
            except discord.Forbidden:
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Role Deletion Failed", f"Could not delete unauthorized role {role.mention} due to missing permissions.", discord.Color.orange())

@bot.event
async def on_guild_role_delete(role: discord.Role):
    if not is_feature_enabled("antimod", "role_delete"):
        return
    guild = role.guild

    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
        executor = entry.user
        if executor == bot.user:
            return
        if not is_whitelisted(executor) and not role_allows(executor, "antimod"):
            description = f"Executor: {executor.mention} ({executor.id})\nDeleted Role: {role.name} ({role.id})"
            await log_event(guild.name, guild.icon.url if guild.icon else None, "Unauthorized Role Deletion", description, discord.Color.red())
            await punish_executor(executor)

@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    if not is_feature_enabled("antimod", "role_update"):
        return
    guild = after.guild

    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
        executor = entry.user
        if executor == bot.user:
            return
        if not is_whitelisted(executor) and not role_allows(executor, "antimod"):
            description = (
                f"Executor: {executor.mention} ({executor.id})\n"
                f"Before: {before.name} (ID: {before.id})\n"
                f"After: {after.name} (ID: {after.id})"
            )
            await log_event(guild.name, guild.icon.url if guild.icon else None, "Unauthorized Role Update", description, discord.Color.red())
            await punish_executor(executor)
            try:
                await after.edit(
                    name=before.name,
                    permissions=before.permissions,
                    color=before.color,
                    hoist=before.hoist,
                    mentionable=before.mentionable,
                    reason="Unauthorized role update detected by AntiMod."
                )
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Role Reverted", f"Reverted unauthorized update to role {after.mention}.", discord.Color.green())
            except discord.Forbidden:
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Role Revert Failed", f"Could not revert unauthorized update to role {after.mention} due to permissions.", discord.Color.orange())

@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    if not is_feature_enabled("antimod", "channel_create"):
        return
    guild = channel.guild

    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
        executor = entry.user
        if executor == bot.user:
            return
        if not is_whitelisted(executor) and not role_allows(executor, "antimod"):
            description = f"Executor: {executor.mention} ({executor.id})\nCreated Channel: {channel.mention} ({channel.id})"
            await log_event(guild.name, guild.icon.url if guild.icon else None, "Unauthorized Channel Creation", description, discord.Color.red())
            await punish_executor(executor)
            try:
                await channel.delete(reason="Unauthorized channel creation detected by AntiMod.")
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Channel Deleted", f"Deleted unauthorized channel: {channel.mention}", discord.Color.green())
            except discord.Forbidden:
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Channel Deletion Failed", f"Could not delete unauthorized channel {channel.mention} due to missing permissions.", discord.Color.orange())


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    if not is_feature_enabled("antimod", "channel_delete"):
        return
    guild = channel.guild

    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        executor = entry.user
        if executor == bot.user:
            return
        if not is_whitelisted(executor) and not role_allows(executor, "antimod"):
            description = f"Executor: {executor.mention} ({executor.id})\nDeleted Channel: #{channel.name} ({channel.id})"
            await log_event(guild.name, guild.icon.url if guild.icon else None, "Unauthorized Channel Deletion", description, discord.Color.red())
            await punish_executor(executor)

@bot.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
    if not is_feature_enabled("antimod", "channel_update"):
        return
    guild = after.guild

    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
        executor = entry.user
        if executor == bot.user:
            return
        if not is_whitelisted(executor) and not role_allows(executor, "antimod"):
            description = (
                f"Executor: {executor.mention} ({executor.id})\n"
                f"Before: #{before.name} (ID: {before.id})\n"
                f"After: #{after.name} (ID: {after.id})"
            )
            await log_event(guild.name, guild.icon.url if guild.icon else None, "Unauthorized Channel Update", description, discord.Color.red())
            await punish_executor(executor)
            try:
                await after.edit(
                    name=before.name,
                    category=before.category,
                    topic=before.topic,
                    slowmode_delay=before.slowmode_delay,
                    nsfw=before.nsfw,
                    overwrites=before.overwrites,
                    reason="Unauthorized channel update detected by AntiMod."
                )
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Channel Reverted", f"Reverted unauthorized update to channel {after.mention}.", discord.Color.green())
            except discord.Forbidden:
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Channel Revert Failed", f"Could not revert unauthorized update to channel {after.mention} due to permissions.", discord.Color.orange())

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return
    guild = message.guild

    if is_feature_enabled("antimod", "mention_everyone"):
        if '@everyone' in message.content or '@here' in message.content:
            if not is_whitelisted(message.author) and not role_allows(message.author, "antimod"):
                description = (
                    f"Executor: {message.author.mention} ({message.author.id})\n"
                    f"Channel: {message.channel.mention}\n"
                    f"Message: `{message.content}`"
                )
                await log_event(guild.name, guild.icon.url if guild.icon else None, "Unauthorized @everyone Mention", description, discord.Color.red())
                try:
                    await message.delete()
                    await punish_executor(message.author)
                    await message.channel.send(
                        embed=discord.Embed(
                            description="⚠️ Unauthorized use of `@everyone` or `@here` has been logged and the message deleted.",
                            color=discord.Color.red()
                        )
                    )
                except discord.Forbidden:
                    await log_event(
                        guild.name,
                        guild.icon.url if guild.icon else None,
                        "Message Deletion Failed",
                        f"Failed to delete message from {message.author.mention} due to missing permissions.",
                        discord.Color.orange()
                    )

# ------------------- SLASH COMMANDS -------------------
# Whitelist
@bot.tree.command(name="whitelist_add", description="Add a member or role to the whitelist")
async def whitelist_add(interaction: discord.Interaction, target: discord.Member | discord.Role):
    embed = discord.Embed(title="Whitelist Update", timestamp=datetime.datetime.now())
    if isinstance(target, discord.Member):
        whitelisted_members.add(target.id)
        embed.description = f"✅ **{target.display_name}** ({target.id}) added to whitelist."
        embed.color = discord.Color.green()
    elif isinstance(target, discord.Role):
        whitelisted_roles.add(target.id)
        embed.description = f"✅ Role **{target.name}** ({target.id}) added to whitelist."
        embed.color = discord.Color.green()
    else:
        embed.description = "❌ Invalid target. Please specify a member or role."
        embed.color = discord.Color.red()
    embed.set_footer(text=f"Bot | Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="whitelist_remove", description="Remove a member or role from the whitelist")
async def whitelist_remove(interaction: discord.Interaction, target: discord.Member | discord.Role):
    embed = discord.Embed(title="Whitelist Update", timestamp=datetime.datetime.now())
    if isinstance(target, discord.Member):
        if target.id in whitelisted_members:
            whitelisted_members.discard(target.id)
            embed.description = f"🗑️ **{target.display_name}** ({target.id}) removed from whitelist."
            embed.color = discord.Color.orange()
        else:
            embed.description = f"ℹ️ **{target.display_name}** is not in the whitelist."
            embed.color = discord.Color.blue()
    elif isinstance(target, discord.Role):
        if target.id in whitelisted_roles:
            whitelisted_roles.discard(target.id)
            embed.description = f"🗑️ Role **{target.name}** ({target.id}) removed from whitelist."
            embed.color = discord.Color.orange()
        else:
            embed.description = f"ℹ️ Role **{target.name}** is not in the whitelist."
            embed.color = discord.Color.blue()
    else:
        embed.description = "❌ Invalid target. Please specify a member or role."
        embed.color = discord.Color.red()
    embed.set_footer(text=f"Bot | Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="check_whitelist", description="Check if a member or role is whitelisted")
async def check_whitelist(interaction: discord.Interaction, target: discord.Member | discord.Role):
    embed = discord.Embed(title="Whitelist Status", timestamp=datetime.datetime.now())
    is_whitelisted_status = False
    target_name = ""
    target_id = ""

    if isinstance(target, discord.Member):
        is_whitelisted_status = is_whitelisted(target)
        target_name = target.display_name
        target_id = target.id
    elif isinstance(target, discord.Role):
        is_whitelisted_status = target.id in whitelisted_roles
        target_name = target.name
        target_id = target.id

    if is_whitelisted_status:
        embed.description = f"✅ **{target_name}** ({target_id}) is currently **whitelisted**."
        embed.color = discord.Color.green()
    else:
        embed.description = f"❌ **{target_name}** ({target_id}) is **not whitelisted**."
        embed.color = discord.Color.red()
    embed.set_footer(text=f"Bot | Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed)

# Global toggles
@bot.tree.command(name="toggle_antinuke", description="Enable/Disable AntiNuke globally")
async def toggle_antinuke(interaction: discord.Interaction):
    global ANTINUKE_ENABLED
    ANTINUKE_ENABLED = not ANTINUKE_ENABLED
    status = "Enabled" if ANTINUKE_ENABLED else "Disabled"
    color = discord.Color.green() if ANTINUKE_ENABLED else discord.Color.red()

    embed = discord.Embed(
        title="AntiNuke Global Toggle",
        description=f"AntiNuke is now: **{status}**",
        color=color,
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text=f"Bot | Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="toggle_antimod", description="Enable/Disable AntiMod globally")
async def toggle_antimod(interaction: discord.Interaction):
    global ANTIMOD_ENABLED
    ANTIMOD_ENABLED = not ANTIMOD_ENABLED
    status = "Enabled" if ANTIMOD_ENABLED else "Disabled"
    color = discord.Color.green() if ANTIMOD_ENABLED else discord.Color.red()

    embed = discord.Embed(
        title="AntiMod Global Toggle",
        description=f"AntiMod is now: **{status}**",
        color=color,
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text=f"Bot | Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="toggle_logging", description="Enable/Disable Logging")
async def toggle_logging(interaction: discord.Interaction):
    global LOGGING_ENABLED
    LOGGING_ENABLED = not LOGGING_ENABLED
    status = "Enabled" if LOGGING_ENABLED else "Disabled"
    color = discord.Color.green() if LOGGING_ENABLED else discord.Color.red()

    embed = discord.Embed(
        title="Logging Toggle",
        description=f"Logging is now: **{status}**",
        color=color,
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text=f"Bot | Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed)

# Sub-feature toggles
@bot.tree.command(name="toggle_subfeature", description="Enable/Disable a specific AntiNuke or AntiMod feature")
@app_commands.choices(
    category=[
        app_commands.Choice(name="antinuke", value="antinuke"),
        app_commands.Choice(name="antimod", value="antimod")
    ],
    feature=[
        app_commands.Choice(name="ban", value="ban"),
        app_commands.Choice(name="kick", value="kick"),
        app_commands.Choice(name="prune", value="prune"),
        app_commands.Choice(name="bot_add", value="bot_add"),
        app_commands.Choice(name="server_update", value="server_update"),
        app_commands.Choice(name="member_role_update", value="member_role_update"),
        app_commands.Choice(name="channel_create", value="channel_create"),
        app_commands.Choice(name="channel_delete", value="channel_delete"),
        app_commands.Choice(name="channel_update", value="channel_update"),
        app_commands.Choice(name="role_create", value="role_create"),
        app_commands.Choice(name="role_delete", value="role_delete"),
        app_commands.Choice(name="role_update", value="role_update"),
        app_commands.Choice(name="mention_everyone", value="mention_everyone"),
        app_commands.Choice(name="webhook_management", value="webhook_management"),
        app_commands.Choice(name="emojis_stickers_management", value="emojis_stickers_management")
    ]
)
async def toggle_subfeature(interaction: discord.Interaction, category: str, feature: str):
    embed = discord.Embed(title=f"{category.title()} Sub-feature Toggle", timestamp=datetime.datetime.now())
    current_state = None

    if category == "antinuke":
        if feature in ANTINUKE_SUBFEATURES:
            ANTINUKE_SUBFEATURES[feature] = not ANTINUKE_SUBFEATURES[feature]
            current_state = ANTINUKE_SUBFEATURES[feature]
        else:
            embed.description = f"❌ Invalid AntiNuke feature: `{feature}`"
            embed.color = discord.Color.red()
    elif category == "antimod":
        if feature in ANTIMOD_SUBFEATURES:
            ANTIMOD_SUBFEATURES[feature] = not ANTIMOD_SUBFEATURES[feature]
            current_state = ANTIMOD_SUBFEATURES[feature]
        else:
            embed.description = f"❌ Invalid AntiMod feature: `{feature}`"
            embed.color = discord.Color.red()
    else:
        embed.description = f"❌ Invalid category: `{category}`. Please use 'antinuke' or 'antimod'."
        embed.color = discord.Color.red()

    if current_state is not None:
        status = "Enabled" if current_state else "Disabled"
        emoji = "✅" if current_state else "❌"
        embed.description = f"{emoji} {category.title()} feature **`{feature}`** is now: **{status}**"
        embed.color = discord.Color.green() if current_state else discord.Color.red()

    embed.set_footer(text=f"Bot | Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed)

# Role-based toggles
@bot.tree.command(name="role_toggle_antinuke", description="Enable/Disable AntiNuke for a role")
async def role_toggle_antinuke(interaction: discord.Interaction, role: discord.Role):
    current = ROLE_ANTINUKE.get(role.id, True)
    ROLE_ANTINUKE[role.id] = not current
    status = "Enabled" if ROLE_ANTINUKE[role.id] else "Disabled"
    color = discord.Color.green() if ROLE_ANTINUKE[role.id] else discord.Color.red()
    emoji = "✅" if ROLE_ANTINUKE[role.id] else "❌"

    embed = discord.Embed(
        title="Role-based AntiNuke Toggle",
        description=f"{emoji} AntiNuke for role **{role.name}** is now: **{status}**",
        color=color,
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text=f"Bot | Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="role_toggle_antimod", description="Enable/Disable AntiMod for a role")
async def role_toggle_antimod(interaction: discord.Interaction, role: discord.Role):
    current = ROLE_ANTIMOD.get(role.id, True)
    ROLE_ANTIMOD[role.id] = not current
    status = "Enabled" if ROLE_ANTIMOD[role.id] else "Disabled"
    color = discord.Color.green() if ROLE_ANTIMOD[role.id] else discord.Color.red()
    emoji = "✅" if ROLE_ANTIMOD[role.id] else "❌"

    embed = discord.Embed(
        title="Role-based AntiMod Toggle",
        description=f"{emoji} AntiMod for role **{role.name}** is now: **{status}**",
        color=color,
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text=f"Bot | Server: {interaction.guild.name}", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    await interaction.response.send_message(embed=embed)


# ------------------- WEB SERVER -------------------
async def web_server_handler(request):
    """Simple web server to respond to uptime pings."""
    return web.Response(text="Bot is awake!")

async def start_web_server():
    """Starts the aiohttp web server."""
    app = web.Application()
    app.router.add_get("/", web_server_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8080)))
    await site.start()
    print("Web server started.")

# ------------------- RUN -------------------
async def main():
    """Runs both the bot and the web server concurrently."""
    await asyncio.gather(
        start_web_server(),
        bot.start(TOKEN)
    )

if __name__ == "__main__":
    asyncio.run(main())
