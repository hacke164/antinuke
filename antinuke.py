# antinuke_bot.py
# Powerful AntiNuke + AutoMod + Auto-Logging + Whitelist (roles & members) bot
# Dependencies: discord.py (v2+), aiosqlite
# pip install -U discord.py aiosqlite

import os
import re
import asyncio
import aiosqlite
from collections import defaultdict, deque
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

# ---------- CONFIG ----------
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") or "PASTE-YOUR-TOKEN-HERE"
DATABASE = "antinuke.db"
DEFAULT_LOG_CHANNEL_NAME = "server-logs"
# thresholds: number of actions in WINDOW_SECONDS to trigger mitigation
DEFAULT_THRESHOLDS = {
    "ban": 3,
    "kick": 4,
    "role_delete": 2,
    "channel_delete": 2,
    "emoji_delete": 3,
    "action_window_seconds": 10
}
# Automod defaults
DEFAULT_AUTOMOD = {
    "enabled": True,
    "block_invites": True,
    "block_profanity": True,
    "profanity_list": ["badword1","badword2"],  # replace with real words
    "caps_percent_threshold": 0.8,
    "caps_length_threshold": 8,
    "max_repeated": 4,
    "max_messages_per_window": 7,
    "message_window_seconds": 8
}
# ----------------------------

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.bans = True
intents.emojis = True
intents.presences = False

bot = commands.Bot(command_prefix="!", intents=intents, application_id=None)  # application_id optional
tree = bot.tree

# per-user action history {guild_id: {user_id: deque((timestamp, action_type))}}
action_hist = defaultdict(lambda: defaultdict(lambda: deque()))

# message history for spam detection: {guild_id: {user_id: deque((timestamp, content))}}
msg_hist = defaultdict(lambda: defaultdict(lambda: deque()))

# small in-memory caches for quick settings access
guild_settings_cache = {}

# ---------- DB helpers ----------
async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            log_channel_id INTEGER,
            thresholds_json TEXT,
            automod_json TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS whitelist_roles (
            guild_id INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, role_id)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS whitelist_members (
            guild_id INTEGER,
            member_id INTEGER,
            PRIMARY KEY (guild_id, member_id)
        )""")
        await db.commit()

async def load_guild_settings(guild_id):
    """Load settings from DB or apply defaults and cache them."""
    if guild_id in guild_settings_cache:
        return guild_settings_cache[guild_id]
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT log_channel_id, thresholds_json, automod_json FROM guild_settings WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        if row:
            import json
            log_channel_id, thresholds_json, automod_json = row
            settings = {
                "log_channel_id": log_channel_id,
                "thresholds": json.loads(thresholds_json) if thresholds_json else DEFAULT_THRESHOLDS.copy(),
                "automod": json.loads(automod_json) if automod_json else DEFAULT_AUTOMOD.copy()
            }
        else:
            settings = {
                "log_channel_id": None,
                "thresholds": DEFAULT_THRESHOLDS.copy(),
                "automod": DEFAULT_AUTOMOD.copy()
            }
            await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, log_channel_id, thresholds_json, automod_json) VALUES (?, ?, ?, ?)",
                              (guild_id, None, None, None))
            await db.commit()
    guild_settings_cache[guild_id] = settings
    return settings

async def set_log_channel_in_db(guild_id, channel_id):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, log_channel_id) VALUES (?, ?)", (guild_id, channel_id))
        await db.commit()
    guild_settings_cache.pop(guild_id, None)

async def is_whitelisted_role(guild_id, role_id):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT 1 FROM whitelist_roles WHERE guild_id=? AND role_id=?", (guild_id, role_id))
        return await cur.fetchone() is not None

async def is_whitelisted_member(guild_id, member_id):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT 1 FROM whitelist_members WHERE guild_id=? AND member_id=?", (guild_id, member_id))
        return await cur.fetchone() is not None

async def add_whitelist_role(guild_id, role_id):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("INSERT OR IGNORE INTO whitelist_roles (guild_id, role_id) VALUES (?, ?)", (guild_id, role_id))
        await db.commit()

async def remove_whitelist_role(guild_id, role_id):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM whitelist_roles WHERE guild_id=? AND role_id=?", (guild_id, role_id))
        await db.commit()

async def add_whitelist_member(guild_id, member_id):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("INSERT OR IGNORE INTO whitelist_members (guild_id, member_id) VALUES (?, ?)", (guild_id, member_id))
        await db.commit()

async def remove_whitelist_member(guild_id, member_id):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM whitelist_members WHERE guild_id=? AND member_id=?", (guild_id, member_id))
        await db.commit()

async def list_whitelist_roles(guild_id):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT role_id FROM whitelist_roles WHERE guild_id=?", (guild_id,))
        rows = await cur.fetchall()
        return [r[0] for r in rows]

async def list_whitelist_members(guild_id):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT member_id FROM whitelist_members WHERE guild_id=?", (guild_id,))
        rows = await cur.fetchall()
        return [r[0] for r in rows]

# ---------- Utilities ----------
def now_ts():
    return datetime.utcnow().timestamp()

async def get_log_channel(guild: discord.Guild):
    settings = await load_guild_settings(guild.id)
    if settings["log_channel_id"]:
        ch = guild.get_channel(settings["log_channel_id"])
        if ch:
            return ch
    # fallback: try to find channel by name or create one
    ch = discord.utils.get(guild.text_channels, name=DEFAULT_LOG_CHANNEL_NAME)
    if ch:
        await set_log_channel_in_db(guild.id, ch.id)
        return ch
    # try to create
    try:
        ch = await guild.create_text_channel(DEFAULT_LOG_CHANNEL_NAME, reason="Auto-created log channel for anti-nuke bot")
        await set_log_channel_in_db(guild.id, ch.id)
        return ch
    except Exception:
        return None

async def log_to_channel(guild: discord.Guild, title: str, desc: str):
    ch = await get_log_channel(guild)
    if ch:
        embed = discord.Embed(title=title, description=desc, timestamp=datetime.utcnow(), color=discord.Color.red())
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

def is_whitelisted(guild_id, user: discord.abc.Snowflake):
    # wrapper to use async check where needed
    raise RuntimeError("Use async check is_whitelisted_member/is_whitelisted_role")

# ---------- Action tracking & mitigation ----------
async def record_action_and_mitigate(guild: discord.Guild, moderator: discord.Member, action: str):
    settings = await load_guild_settings(guild.id)
    thresholds = settings["thresholds"]
    window = thresholds.get("action_window_seconds", DEFAULT_THRESHOLDS["action_window_seconds"])

    dq = action_hist[guild.id][moderator.id]
    now = datetime.utcnow().timestamp()
    dq.append((now, action))
    # purge old
    while dq and now - dq[0][0] > window:
        dq.popleft()

    # count actions by type
    counts = defaultdict(int)
    for tstamp, act in dq:
        counts[act] += 1

    # decide if any threshold exceeded
    punish = None
    if counts.get("ban", 0) >= thresholds.get("ban", DEFAULT_THRESHOLDS["ban"]):
        punish = "ban"
    elif counts.get("kick", 0) >= thresholds.get("kick", DEFAULT_THRESHOLDS["kick"]):
        punish = "kick"
    elif counts.get("role_delete", 0) >= thresholds.get("role_delete", DEFAULT_THRESHOLDS["role_delete"]):
        punish = "role_delete"
    elif counts.get("channel_delete", 0) >= thresholds.get("channel_delete", DEFAULT_THRESHOLDS["channel_delete"]):
        punish = "channel_delete"
    elif counts.get("emoji_delete", 0) >= thresholds.get("emoji_delete", DEFAULT_THRESHOLDS["emoji_delete"]):
        punish = "emoji_delete"

    if punish:
        # if moderator is whitelisted, do nothing
        if await is_whitelisted_member(guild.id, moderator.id):
            await log_to_channel(guild, "Whitelist bypass", f"{moderator.mention} triggered a threshold but is whitelisted.")
            return
        # remove manage roles perms from user by removing highest role that is manageable
        try:
            # Ban as last resort
            if punish == "ban":
                await guild.ban(moderator, reason="Antinuke: excessive destructive actions")
                await log_to_channel(guild, "Moderator banned", f"{moderator} was banned for excessive destructive actions.")
            elif punish == "kick":
                await guild.kick(moderator, reason="Antinuke: excessive destructive actions")
                await log_to_channel(guild, "Moderator kicked", f"{moderator} was kicked for excessive destructive actions.")
            else:
                # attempt to remove permissions: demote their top role (best-effort)
                top_role = None
                if isinstance(moderator, discord.Member):
                    roles = [r for r in moderator.roles if r < guild.me.top_role]
                    if roles:
                        top_role = roles[-1]
                if top_role:
                    try:
                        await top_role.edit(permissions=discord.Permissions(0), reason="Antinuke: revoking perms from suspected account")
                        await log_to_channel(guild, "Role perms stripped", f"{moderator}'s top role {top_role.name} had perms stripped.")
                    except Exception:
                        await log_to_channel(guild, "Failed strip role perms", f"Couldn't strip perms from {top_role} - check bot permissions.")
                else:
                    await log_to_channel(guild, "No manageable role", f"Could not demote {moderator}. Consider manual action.")
        except Exception as e:
            await log_to_channel(guild, "Mitigation failed", f"Failed to mitigate {moderator}: {e}")

# ---------- Reversion helpers ----------
async def recreate_role(guild: discord.Guild, role: discord.Role):
    try:
        new = await guild.create_role(
            name=role.name,
            permissions=role.permissions,
            colour=role.colour,
            hoist=role.hoist,
            mentionable=role.mentionable,
            reason="Antinuke: restoring deleted role"
        )
        # attempt to set position similar to old (best effort)
        try:
            await new.edit(position=role.position)
        except Exception:
            pass
        await log_to_channel(guild, "Role restored", f"Role `{role.name}` was recreated.")
    except Exception as e:
        await log_to_channel(guild, "Role restore failed", f"Failed to recreate role `{role.name}`: {e}")

async def recreate_channel(guild: discord.Guild, channel: discord.abc.GuildChannel):
    try:
        # channel is a deleted channel object - try to clone if possible
        if isinstance(channel, discord.TextChannel):
            new = await guild.create_text_channel(name=channel.name, overwrites=channel.overwrites, topic=channel.topic, slowmode_delay=getattr(channel, 'slowmode_delay', 0), reason="Antinuke: restore deleted channel")
        elif isinstance(channel, discord.VoiceChannel):
            new = await guild.create_voice_channel(name=channel.name, overwrites=channel.overwrites, bitrate=getattr(channel, 'bitrate', 64000), reason="Antinuke: restore deleted channel")
        else:
            new = await guild.create_text_channel(name=channel.name, reason="Antinuke: restore deleted channel")
        await log_to_channel(guild, "Channel restored", f"Channel `{channel.name}` was recreated.")
    except Exception as e:
        await log_to_channel(guild, "Channel restore failed", f"Failed to recreate channel `{getattr(channel,'name', 'unknown')}`: {e}")

# ---------- Events watchers ----------

@bot.event
async def on_ready():
    await init_db()
    print(f"Bot ready. Logged in as {bot.user} (ID: {bot.user.id})")
    # sync commands
    try:
        await tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print("Failed to sync slash commands:", e)

@bot.event
async def on_guild_role_delete(role):
    # role param is the deleted role object (best-effort)
    guild = role.guild
    # find responsible mod via audit logs
    try:
        async for entry in guild.audit_logs(limit=6, action=discord.AuditLogAction.role_delete):
            if entry.target.id == role.id:
                moderator = entry.user
                await record_action_and_mitigate(guild, moderator, "role_delete")
                # revert
                await recreate_role(guild, role)
                await log_to_channel(guild, "Role deleted", f"Role `{role.name}` deleted by **{moderator}**. Recreated.")
                return
    except Exception:
        pass
    # fallback: log and try recreate
    await recreate_role(guild, role)
    await log_to_channel(guild, "Role deleted", f"Role `{role.name}` deleted (moderator unknown). Attempted recreate.")

@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    try:
        async for entry in guild.audit_logs(limit=6, action=discord.AuditLogAction.channel_delete):
            # entry.target is the channel-like object; compare name
            if getattr(entry.target, "id", None) == channel.id or getattr(entry.target, "name", None) == channel.name:
                moderator = entry.user
                await record_action_and_mitigate(guild, moderator, "channel_delete")
                await recreate_channel(guild, channel)
                await log_to_channel(guild, "Channel deleted", f"Channel `{channel.name}` deleted by **{moderator}**. Recreated.")
                return
    except Exception:
        pass
    await recreate_channel(guild, channel)
    await log_to_channel(guild, "Channel deleted", f"Channel `{channel.name}` deleted (moderator unknown). Attempted recreate.")

@bot.event
async def on_guild_emojis_update(guild, before, after):
    # if emojis were removed, try to detect who removed them and punish
    removed = {e.name: e for e in before if e not in after}
    if not removed:
        return
    try:
        async for entry in guild.audit_logs(limit=8, action=discord.AuditLogAction.emoji_delete):
            moderator = entry.user
            # count as emoji_delete
            await record_action_and_mitigate(guild, moderator, "emoji_delete")
            await log_to_channel(guild, "Emoji deleted", f"{len(removed)} emoji(s) deleted by {moderator}.")
            # cannot restore emoji easily without asset, so just log
            return
    except Exception:
        await log_to_channel(guild, "Emoji changes", f"{len(removed)} emoji(s) removed but audit logs couldn't be read.")

@bot.event
async def on_member_ban(guild, user):
    # note: this event does not give the banner; inspect audit logs for details
    try:
        async for entry in guild.audit_logs(limit=8, action=discord.AuditLogAction.ban):
            # entry.target is the user banned
            if entry.target.id == user.id:
                moderator = entry.user
                await record_action_and_mitigate(guild, moderator, "ban")
                await log_to_channel(guild, "Member banned", f"{user} was banned by {moderator}")
                return
    except Exception:
        await log_to_channel(guild, "Member banned", f"{user} was banned but could not find audit log entry.")

# ---------- Automod: message checks ----------
INVITE_REGEX = re.compile(r"(https?:\/\/)?(www\.)?(discord\.(gg|io|me|li)|discordapp\.com\/invite)\/\S+", re.I)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not message.guild:
        return

    settings = await load_guild_settings(message.guild.id)
    automod = settings["automod"]

    # log message to history for spam detection
    user_deque = msg_hist[message.guild.id][message.author.id]
    now = datetime.utcnow().timestamp()
    user_deque.append((now, message.content))
    while user_deque and now - user_deque[0][0] > automod.get("message_window_seconds", DEFAULT_AUTOMOD["message_window_seconds"]):
        user_deque.popleft()

    # quick whitelist checks
    if await is_whitelisted_member(message.guild.id, message.author.id):
        # allow whitelisted members
        return

    # automod checks
    # block invite links
    if automod.get("block_invites", True):
        if INVITE_REGEX.search(message.content):
            try:
                await message.delete()
            except Exception:
                pass
            await log_to_channel(message.guild, "Invite blocked", f"Blocked invite posted by {message.author}: `{message.content}`")
            return

    # profanity
    if automod.get("block_profanity", True):
        for w in automod.get("profanity_list", []):
            if w.lower() in message.content.lower():
                try:
                    await message.delete()
                except Exception:
                    pass
                await log_to_channel(message.guild, "Profanity blocked", f"{message.author} used blocked word `{w}` in message.")
                return

    # caps spam
    raw = message.content or ""
    if len(raw) >= automod.get("caps_length_threshold", 8):
        letters = [c for c in raw if c.isalpha()]
        if letters:
            upper = sum(1 for c in letters if c.isupper())
            if upper / len(letters) >= automod.get("caps_percent_threshold", 0.8):
                try:
                    await message.delete()
                except Exception:
                    pass
                await log_to_channel(message.guild, "Caps blocked", f"Deleted all-caps message from {message.author}: `{raw[:200]}`")
                return

    # repeated messages (spam)
    if len(user_deque) >= automod.get("max_repeated", 4):
        # check duplicates
        contents = [c for ts, c in user_deque]
        if len(set(contents)) <= 1:
            try:
                await message.delete()
            except Exception:
                pass
            await log_to_channel(message.guild, "Spam blocked", f"{message.author} was sending repeated messages.")
            return

    # rate-based spam: too many messages in window
    if len(user_deque) >= automod.get("max_messages_per_window", 7):
        try:
            await message.delete()
        except Exception:
            pass
        await log_to_channel(message.guild, "Spam rate blocked", f"{message.author} sent too many messages in short time.")
        return

    # store last message per user for duplicate detection (simple)
    # allow other bots/commands to run
    await bot.process_commands(message)

# ---------- Slash commands for whitelist & settings ----------
@tree.command(name="whitelist_add_role", description="Whitelist a role from antinuke/automod actions (role mention)")
@app_commands.describe(role="Role to whitelist")
async def wh_add_role(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await add_whitelist_role(interaction.guild.id, role.id)
    await interaction.response.send_message(f"Role {role.mention} added to whitelist.", ephemeral=True)

@tree.command(name="whitelist_remove_role", description="Remove a role from whitelist")
@app_commands.describe(role="Role to remove")
async def wh_remove_role(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await remove_whitelist_role(interaction.guild.id, role.id)
    await interaction.response.send_message(f"Role {role.mention} removed from whitelist.", ephemeral=True)

@tree.command(name="whitelist_add_member", description="Whitelist a member from antinuke/automod actions")
@app_commands.describe(member="Member to whitelist")
async def wh_add_member(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await add_whitelist_member(interaction.guild.id, member.id)
    await interaction.response.send_message(f"{member.mention} added to whitelist.", ephemeral=True)

@tree.command(name="whitelist_remove_member", description="Remove a member from whitelist")
@app_commands.describe(member="Member to remove")
async def wh_remove_member(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await remove_whitelist_member(interaction.guild.id, member.id)
    await interaction.response.send_message(f"{member.mention} removed from whitelist.", ephemeral=True)

@tree.command(name="whitelist_list", description="List whitelisted roles and members")
async def wh_list(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    role_ids = await list_whitelist_roles(interaction.guild.id)
    member_ids = await list_whitelist_members(interaction.guild.id)
    roles = [interaction.guild.get_role(rid) for rid in role_ids if interaction.guild.get_role(rid)]
    members = [interaction.guild.get_member(mid) for mid in member_ids if interaction.guild.get_member(mid)]
    text = f"**Whitelisted Roles:**\n" + (", ".join(r.mention for r in roles) if roles else "None") + "\n\n"
    text += "**Whitelisted Members:**\n" + (", ".join(m.mention for m in members) if members else "None")
    await interaction.response.send_message(text, ephemeral=True)

@tree.command(name="set_log_channel", description="Set the logging channel for anti-nuke events")
@app_commands.describe(channel="Channel to send logs to")
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    await set_log_channel_in_db(interaction.guild.id, channel.id)
    # clear cached settings
    guild_settings_cache.pop(interaction.guild.id, None)
    await interaction.response.send_message(f"Log channel set to {channel.mention}", ephemeral=True)

@tree.command(name="show_thresholds", description="Show current anti-nuke thresholds")
async def show_thresholds(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    settings = await load_guild_settings(interaction.guild.id)
    await interaction.response.send_message(f"Current thresholds:\n```{settings['thresholds']}```", ephemeral=True)

@tree.command(name="set_threshold", description="Set a threshold parameter (e.g. ban, kick, role_delete, channel_delete, emoji_delete, action_window_seconds)")
@app_commands.describe(key="Threshold key", value="Integer value")
async def set_threshold(interaction: discord.Interaction, key: str, value: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    settings = await load_guild_settings(interaction.guild.id)
    if key not in settings["thresholds"]:
        await interaction.response.send_message("Unknown key. Keys: " + ", ".join(settings["thresholds"].keys()), ephemeral=True)
        return
    settings["thresholds"][key] = int(value)
    # persist
    import json, aiosqlite as _a
    async with _a.connect(DATABASE) as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, log_channel_id, thresholds_json, automod_json) VALUES (?, ?, ?, ?)",
                         (interaction.guild.id, settings.get("log_channel_id"), json.dumps(settings["thresholds"]), json.dumps(settings["automod"])))
        await db.commit()
    guild_settings_cache.pop(interaction.guild.id, None)
    await interaction.response.send_message(f"Threshold {key} set to {value}", ephemeral=True)

@tree.command(name="automod_toggle", description="Enable or disable automod features")
@app_commands.describe(feature="feature name", enabled="true/false")
async def automod_toggle(interaction: discord.Interaction, feature: str, enabled: bool):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return
    settings = await load_guild_settings(interaction.guild.id)
    # feature could be top-level like 'enabled' or 'block_invites' etc.
    if feature not in settings["automod"]:
        await interaction.response.send_message("Unknown automod feature. Keys: " + ", ".join(settings["automod"].keys()), ephemeral=True)
        return
    settings["automod"][feature] = enabled
    import json, aiosqlite as _a
    async with _a.connect(DATABASE) as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, log_channel_id, thresholds_json, automod_json) VALUES (?, ?, ?, ?)",
                         (interaction.guild.id, settings.get("log_channel_id"), json.dumps(settings["thresholds"]), json.dumps(settings["automod"])))
        await db.commit()
    guild_settings_cache.pop(interaction.guild.id, None)
    await interaction.response.send_message(f"Automod {feature} set to {enabled}", ephemeral=True)

# ---------- Safety: admin action logging ----------
@bot.event
async def on_guild_role_create(role):
    await log_to_channel(role.guild, "Role created", f"Role `{role.name}` was created by (unknown) — check audit logs if suspicious.")

@bot.event
async def on_guild_channel_create(channel):
    await log_to_channel(channel.guild, "Channel created", f"Channel `{channel.name}` was created.")

# ---------- Startup: create DB ----------
async def startup():
    await init_db()

# ---------- Run bot ----------
if __name__ == "__main__":
    # ensure DB init before login
    asyncio.run(init_db())
    bot.run(BOT_TOKEN)
