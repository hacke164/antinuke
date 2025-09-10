# bot.py
"""
Guardian Bot — production-ready single-file (UI + backend + keep-alive)
- Slash commands: /about, /enable_guard, /disable_guard, /set_log_channel
- Interactive embed UI + toggles via buttons, whitelist modal
- Antinuke & AutoMod protections with safe punishments, rate-limits, logging
- Persistent JSON config (atomic + async via aiofiles)
- Built-in Flask keep-alive endpoint for UptimeRobot (runs in background thread)
- No audioop dependency
Run:
  export TOKEN="your_bot_token_here"
  python bot.py
"""

import os
import json
import asyncio
import datetime
import threading
import re
from typing import Any, Dict, Optional, List

import aiofiles
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, jsonify

### ---------------- CONFIG ---------------- ###
DATA_FILE = "data.json"
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("Set the TOKEN environment variable before running the bot.")

BOT_LOGO_URL = "https://i.imgur.com/4M34hi2.png"  # replace with your logo URL if desired
EMBED_COLOR = discord.Color.blurple()
KEEP_ALIVE_PORT = int(os.getenv("KEEP_ALIVE_PORT", "8080"))  # Render exposes a port

### ---------------- INTENTS ---------------- ###
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True  # needed for automod message scanning

### ---------------- GLOBALS ---------------- ###
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

_db_lock = asyncio.Lock()
_db: Dict[str, Any] = {}  # guild_id -> settings

DEFAULT_GUILD_SETTINGS = {
    "guard_enabled": False,
    "antinuke": {
        "channels_deleted": False,
        "channels_created": False,
        "roles_deleted": False,
        "roles_created": False,
        "webhooks_created": False,
        "member_bans": False,
        "member_kicks": False,
        "bots_added": False,
        "actions": {
            "remove_roles": False,
            "kick_member": False,
            "ban_member": False,
            "server_lockdown": False,
            "unverified_ban": False,
            "notify_admins": True
        }
    },
    "automod": {
        "link_invite_filter": False,
        "mass_mention_protection": False,
        "mass_mention_threshold": 5
    },
    "whitelist": {
        "antinuke": [],
        "automod": []
    },
    "log_channel_id": None,
    "recent_triggers": {}
}

### ---------------- PERSISTENCE ---------------- ###
async def load_db():
    global _db
    if not os.path.exists(DATA_FILE):
        _db = {}
        return
    async with _db_lock:
        try:
            async with aiofiles.open(DATA_FILE, "r", encoding="utf-8") as f:
                text = await f.read()
                _db = json.loads(text) if text else {}
        except Exception:
            _db = {}


async def save_db():
    async with _db_lock:
        tmp = DATA_FILE + ".tmp"
        try:
            async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
                await f.write(json.dumps(_db, indent=2))
            os.replace(tmp, DATA_FILE)
        except Exception as e:
            print("Failed saving DB:", e)


def ensure_guild(guild_id: int):
    sid = str(guild_id)
    if sid not in _db:
        _db[sid] = json.loads(json.dumps(DEFAULT_GUILD_SETTINGS))


### ---------------- HELPERS ---------------- ###
def tick(v: bool) -> str:
    return "✅" if v else "❌"


async def send_log_embed(guild: discord.Guild, embed: discord.Embed, settings: Dict[str, Any]):
    cid = settings.get("log_channel_id")
    if cid:
        ch = guild.get_channel(cid)
        if ch and ch.permissions_for(guild.me).send_messages:
            try:
                await ch.send(embed=embed)
                return
            except Exception:
                pass
    # fallback: DM owner and up to 2 admins
    owner = guild.owner
    if owner:
        try:
            await owner.send(embed=embed)
        except Exception:
            pass
    sent = 0
    for m in guild.members:
        if sent >= 2:
            break
        if m.guild_permissions.administrator and not m.bot and m != owner:
            try:
                await m.send(embed=embed)
                sent += 1
            except Exception:
                continue


def is_whitelisted(settings: Dict[str, Any], category: str, member: discord.Member) -> bool:
    # Owner and administrators implicitly whitelisted
    if member == member.guild.owner or member.guild_permissions.administrator:
        return True
    wl = settings.get("whitelist", {}).get(category, [])
    s = str(member.id)
    if s in wl:
        return True
    for r in member.roles:
        if str(r.id) in wl:
            return True
    return False


def rate_limit_allows(settings: Dict[str, Any], key: str, window_seconds: int = 10, limit: int = 3) -> bool:
    now = datetime.datetime.utcnow().timestamp()
    rt = settings.setdefault("recent_triggers", {})
    arr = rt.get(key, [])
    arr = [t for t in arr if now - t < window_seconds]
    arr.append(now)
    rt[key] = arr
    return len(arr) <= limit


async def fetch_audit_actor(guild: discord.Guild, action: discord.AuditLogAction, target_id: Optional[int] = None):
    try:
        async for entry in guild.audit_logs(limit=6, action=action):
            if target_id is None:
                return entry.user
            try:
                if getattr(entry.target, "id", None) == target_id:
                    return entry.user
            except Exception:
                continue
    except Exception:
        return None
    return None


### ---------------- EMBED + UI BUILDERS ---------------- ###
def build_guard_embed(guild: Optional[discord.Guild], settings: Dict[str, Any]) -> discord.Embed:
    name = guild.name if guild else "Server"
    embed = discord.Embed(
        title=f"{name} • Guardian Protection",
        description="Premium protection controls — toggle features using the buttons below.\n\n"
                    "Be careful with auto punishments. Test in a private server first.",
        color=EMBED_COLOR,
        timestamp=datetime.datetime.utcnow()
    )
    if guild and guild.icon:
        embed.set_author(name=name, icon_url=str(guild.icon.url))
    embed.set_thumbnail(url=BOT_LOGO_URL or (bot.user.avatar.url if bot.user.avatar else None))

    ant = settings.get("antinuke", {})
    ant_text = ""
    keys = [
        ("channels_deleted", "Channels deleted"),
        ("channels_created", "Channels created"),
        ("roles_deleted", "Roles deleted"),
        ("roles_created", "Roles created"),
        ("webhooks_created", "Webhooks created"),
        ("member_bans", "Member bans"),
        ("member_kicks", "Member kicks"),
        ("bots_added", "Bots added"),
    ]
    for k, label in keys:
        ant_text += f"{tick(bool(ant.get(k, False)))} {label}\n"
    ant_text += "\n**Response actions:**\n"
    for k in ["remove_roles", "kick_member", "ban_member", "server_lockdown", "unverified_ban", "notify_admins"]:
        ant_text += f"{tick(bool(ant.get('actions', {}).get(k, False)))} {k}\n"
    embed.add_field(name="🛡 Antinuke", value=ant_text, inline=False)

    am = settings.get("automod", {})
    am_text = f"{tick(bool(am.get('link_invite_filter', False)))} Link & Invite Filtering\n"
    am_text += f"{tick(bool(am.get('mass_mention_protection', False)))} Mass Mention/Ping Protection (threshold {am.get('mass_mention_threshold', 5)})\n"
    embed.add_field(name="🤖 AutoMod", value=am_text, inline=False)

    wl = settings.get("whitelist", {})
    embed.add_field(name="📜 Whitelist", value=f"Antinuke: {len(wl.get('antinuke', []))} entries\nAutoMod: {len(wl.get('automod', []))} entries", inline=False)
    embed.set_footer(text="Click toggles below to change settings — admins only.")
    return embed


class ToggleButton(discord.ui.Button):
    def __init__(self, guild_id: int, key_path: List[str], label: Optional[str] = None):
        super().__init__(style=discord.ButtonStyle.secondary, label=label or key_path[-1], custom_id=f"toggle:{guild_id}:{':'.join(key_path)}")
        self.guild_id = guild_id
        self.key_path = key_path

    async def callback(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You must be a server administrator to modify settings.", ephemeral=True)
            return
        sid = str(self.guild_id)
        ensure_guild(self.guild_id)
        settings = _db[sid]
        obj = settings
        for k in self.key_path[:-1]:
            obj = obj.setdefault(k, {})
        last = self.key_path[-1]
        obj[last] = not bool(obj.get(last, False))
        await save_db()
        # refresh embed & view
        await interaction.message.edit(embed=build_guard_embed(interaction.guild, settings), view=build_guard_view(self.guild_id))
        await interaction.response.send_message(f"Toggled `{last}` → {obj[last]}", ephemeral=True)


class SaveButton(discord.ui.Button):
    def __init__(self, guild_id: int):
        super().__init__(style=discord.ButtonStyle.success, label="Save & Apply", custom_id=f"save:{guild_id}")
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You must be a server administrator.", ephemeral=True)
            return
        # saved live already
        await interaction.response.send_message("Settings saved and applied.", ephemeral=True)


class ManageWhitelistButton(discord.ui.Button):
    def __init__(self, guild_id: int):
        super().__init__(style=discord.ButtonStyle.primary, label="Manage Whitelist", custom_id=f"wl:{guild_id}")
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You must be a server administrator.", ephemeral=True)
            return
        # show modal for add/remove
        modal = WhitelistModal(self.guild_id)
        await interaction.response.send_modal(modal)


class WhitelistModal(discord.ui.Modal, title="Manage Whitelist (add/remove)"):
    category = discord.ui.TextInput(label="Category (antinuke/automod)", placeholder="antinuke", required=True, max_length=20)
    entry = discord.ui.TextInput(label="Mention or ID (e.g., @user or @role or 123...)", placeholder="@user", required=True, max_length=100)
    action = discord.ui.TextInput(label="Action (add/remove)", placeholder="add", required=True, max_length=10)

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admin permissions required.", ephemeral=True)
            return
        cat = self.category.value.strip().lower()
        ent = self.entry.value.strip()
        act = self.action.value.strip().lower()
        if cat not in ("antinuke", "automod"):
            await interaction.response.send_message("Category must be 'antinuke' or 'automod'.", ephemeral=True)
            return
        # parse mention or id
        m_user = re.match(r"<@!?(?P<id>\d+)>", ent)
        m_role = re.match(r"<@&(?P<id>\d+)>", ent)
        target_id = None
        if m_user:
            target_id = m_user.group("id")
        elif m_role:
            target_id = m_role.group("id")
        elif ent.isdigit():
            target_id = ent
        if not target_id:
            await interaction.response.send_message("Couldn't parse the mention or ID.", ephemeral=True)
            return
        ensure_guild(self.guild_id)
        settings = _db[str(self.guild_id)]
        wl = settings.setdefault("whitelist", {}).setdefault(cat, [])
        if act == "add":
            if target_id in wl:
                await interaction.response.send_message("Already whitelisted.", ephemeral=True)
                return
            wl.append(target_id)
            await save_db()
            await interaction.response.send_message("Added to whitelist.", ephemeral=True)
        elif act == "remove":
            if target_id not in wl:
                await interaction.response.send_message("Not in whitelist.", ephemeral=True)
                return
            wl.remove(target_id)
            await save_db()
            await interaction.response.send_message("Removed from whitelist.", ephemeral=True)
        else:
            await interaction.response.send_message("Action must be 'add' or 'remove'.", ephemeral=True)


class GuardView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        # antinuke toggles
        keys = [
            ("Channels Deleted", ["antinuke", "channels_deleted"]),
            ("Channels Created", ["antinuke", "channels_created"]),
            ("Roles Deleted", ["antinuke", "roles_deleted"]),
            ("Roles Created", ["antinuke", "roles_created"]),
            ("Webhooks Created", ["antinuke", "webhooks_created"]),
            ("Member Bans", ["antinuke", "member_bans"]),
            ("Member Kicks", ["antinuke", "member_kicks"]),
            ("Bots Added", ["antinuke", "bots_added"]),
        ]
        for lbl, kp in keys:
            self.add_item(ToggleButton(guild_id, kp, label=lbl))
        # antinuke actions
        actions = [
            ("Remove Roles", ["antinuke", "actions", "remove_roles"]),
            ("Kick Member", ["antinuke", "actions", "kick_member"]),
            ("Ban Member", ["antinuke", "actions", "ban_member"]),
            ("Server Lockdown", ["antinuke", "actions", "server_lockdown"]),
            ("Unverified Ban", ["antinuke", "actions", "unverified_ban"]),
            ("Notify Admins", ["antinuke", "actions", "notify_admins"]),
        ]
        for lbl, kp in actions:
            self.add_item(ToggleButton(guild_id, kp, label=lbl))
        # automod toggles
        self.add_item(ToggleButton(guild_id, ["automod", "link_invite_filter"], label="Link/Invite Filter"))
        self.add_item(ToggleButton(guild_id, ["automod", "mass_mention_protection"], label="Mass Mention Protection"))
        # whitelist and save
        self.add_item(ManageWhitelistButton(guild_id))
        self.add_item(SaveButton(guild_id))


def build_guard_view(guild_id: int) -> GuardView:
    return GuardView(guild_id)


### ---------------- SLASH COMMANDS ---------------- ###
def admin_check(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator


@tree.command(name="about", description="About Guardian Bot")
async def about_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Guardian Bot — Server Protector",
        description="Your all-in-one Discord security solution.\n\n"
                    "Guardian Bot provides powerful, customizable protection against raids, spam, and malicious activity.",
        color=EMBED_COLOR,
        timestamp=datetime.datetime.utcnow()
    )
    if interaction.guild and interaction.guild.icon:
        embed.set_author(name=interaction.guild.name, icon_url=str(interaction.guild.icon.url))
    embed.set_thumbnail(url=BOT_LOGO_URL)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="enable_guard", description="Open the Guardian control panel (admin only)")
async def enable_guard(interaction: discord.Interaction):
    if not admin_check(interaction):
        await interaction.response.send_message("Administrator permissions required.", ephemeral=True)
        return
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("Use this command in a server.", ephemeral=True)
        return
    ensure_guild(guild.id)
    await save_db()
    embed = build_guard_embed(guild, _db[str(guild.id)])
    view = build_guard_view(guild.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@tree.command(name="disable_guard", description="Disable Guardian protections for this server (admin only)")
async def disable_guard(interaction: discord.Interaction):
    if not admin_check(interaction):
        await interaction.response.send_message("Administrator permissions required.", ephemeral=True)
        return
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("Use in server.", ephemeral=True)
        return
    ensure_guild(guild.id)
    _db[str(guild.id)]["guard_enabled"] = False
    await save_db()
    await interaction.response.send_message("Guardian guard disabled for this server.", ephemeral=True)


@tree.command(name="set_log_channel", description="Set a channel for Guardian logs (admin only)")
async def set_log_channel(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    if not admin_check(interaction):
        await interaction.response.send_message("Administrator permissions required.", ephemeral=True)
        return
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("Use in server.", ephemeral=True)
        return
    ensure_guild(guild.id)
    _db[str(guild.id)]["log_channel_id"] = channel.id if channel else None
    await save_db()
    await interaction.response.send_message(f"Log channel updated to {channel.mention if channel else 'None'}.", ephemeral=True)


### ---------------- CORE PUNISH + HANDLERS ---------------- ###
async def perform_punishments(guild: discord.Guild, actor: Optional[discord.Member], category: str, target: Optional[Any], settings: Dict[str, Any]):
    if not settings.get("guard_enabled", False):
        return
    if not rate_limit_allows(settings, f"{category}:{actor.id if actor else 'anon'}", window_seconds=10, limit=2):
        return
    ant = settings.get("antinuke", {})
    actions = ant.get("actions", {})
    embed = discord.Embed(title="Guardian — Antinuke Trigger", color=discord.Color.red(), timestamp=datetime.datetime.utcnow())
    embed.add_field(name="Trigger", value=category, inline=False)
    if actor:
        embed.add_field(name="Actor", value=f"{actor} ({actor.id})", inline=True)
    if target:
        try:
            embed.add_field(name="Target", value=str(getattr(target, "name", str(target))), inline=True)
        except Exception:
            pass
    # remove_roles
    if actions.get("remove_roles", False) and isinstance(actor, discord.Member):
        try:
            if actor == guild.owner:
                embed.add_field(name="Remove roles", value="Prevented (owner)", inline=False)
            else:
                roles = [r for r in actor.roles if r != guild.default_role and r < guild.me.top_role]
                if roles and guild.me.guild_permissions.manage_roles:
                    await actor.remove_roles(*roles, reason="Guardian remove_roles")
                    embed.add_field(name="Remove roles", value=f"Removed {len(roles)} roles", inline=False)
        except Exception as e:
            embed.add_field(name="Remove roles failed", value=str(e), inline=False)
    # kick
    if actions.get("kick_member", False) and isinstance(actor, discord.Member):
        try:
            if actor == guild.owner:
                embed.add_field(name="Kick", value="Prevented (owner)", inline=False)
            elif guild.me.guild_permissions.kick_members:
                await actor.kick(reason=f"Guardian auto-kick for {category}")
                embed.add_field(name="Kick", value="Actor kicked", inline=False)
        except Exception as e:
            embed.add_field(name="Kick failed", value=str(e), inline=False)
    # ban
    if actions.get("ban_member", False) and isinstance(actor, discord.Member):
        try:
            if actor == guild.owner:
                embed.add_field(name="Ban", value="Prevented (owner)", inline=False)
            elif guild.me.guild_permissions.ban_members:
                await guild.ban(actor, reason=f"Guardian auto-ban for {category}", delete_message_days=1)
                embed.add_field(name="Ban", value="Actor banned", inline=False)
        except Exception as e:
            embed.add_field(name="Ban failed", value=str(e), inline=False)
    # server lockdown
    if actions.get("server_lockdown", False):
        count = 0
        if guild.me.guild_permissions.manage_channels:
            for ch in guild.text_channels:
                try:
                    overwrite = ch.overwrites_for(guild.default_role)
                    overwrite.send_messages = False
                    await ch.set_permissions(guild.default_role, overwrite=overwrite, reason="Guardian lockdown")
                    count += 1
                except Exception:
                    continue
            embed.add_field(name="Server lockdown", value=f"Locked {count} channels (where permitted)", inline=False)
        else:
            embed.add_field(name="Server lockdown", value="Bot lacks Manage Channels permission", inline=False)
    # unverified ban
    if actions.get("unverified_ban", False) and isinstance(actor, discord.Member):
        try:
            age_days = (datetime.datetime.utcnow() - actor.created_at).days
            if age_days < 7 and guild.me.guild_permissions.ban_members:
                await guild.ban(actor, reason="Guardian unverified_ban", delete_message_days=1)
                embed.add_field(name="Unverified ban", value=f"Banned actor (age {age_days}d)", inline=False)
        except Exception as e:
            embed.add_field(name="Unverified ban failed", value=str(e), inline=False)
    # notify_admins will be included in embed posting
    await send_log_embed(guild, embed, settings)


# events
@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    ensure_guild(guild.id)
    settings = _db[str(guild.id)]
    if not settings.get("guard_enabled", False) or not settings.get("antinuke", {}).get("channels_deleted", False):
        return
    actor = await fetch_audit_actor(guild, discord.AuditLogAction.channel_delete)
    if actor and isinstance(actor, discord.Member) and is_whitelisted(settings, "antinuke", actor):
        return
    await perform_punishments(guild, actor if isinstance(actor, discord.Member) else None, "channels_deleted", channel, settings)


@bot.event
async def on_guild_channel_create(channel):
    guild = channel.guild
    ensure_guild(guild.id)
    settings = _db[str(guild.id)]
    if not settings.get("guard_enabled", False) or not settings.get("antinuke", {}).get("channels_created", False):
        return
    actor = await fetch_audit_actor(guild, discord.AuditLogAction.channel_create)
    if actor and isinstance(actor, discord.Member) and is_whitelisted(settings, "antinuke", actor):
        return
    await perform_punishments(guild, actor if isinstance(actor, discord.Member) else None, "channels_created", channel, settings)


@bot.event
async def on_guild_role_delete(role):
    guild = role.guild
    ensure_guild(guild.id)
    settings = _db[str(guild.id)]
    if not settings.get("guard_enabled", False) or not settings.get("antinuke", {}).get("roles_deleted", False):
        return
    actor = await fetch_audit_actor(guild, discord.AuditLogAction.role_delete)
    if actor and isinstance(actor, discord.Member) and is_whitelisted(settings, "antinuke", actor):
        return
    await perform_punishments(guild, actor if isinstance(actor, discord.Member) else None, "roles_deleted", role, settings)


@bot.event
async def on_guild_role_create(role):
    guild = role.guild
    ensure_guild(guild.id)
    settings = _db[str(guild.id)]
    if not settings.get("guard_enabled", False) or not settings.get("antinuke", {}).get("roles_created", False):
        return
    actor = await fetch_audit_actor(guild, discord.AuditLogAction.role_create)
    if actor and isinstance(actor, discord.Member) and is_whitelisted(settings, "antinuke", actor):
        return
    await perform_punishments(guild, actor if isinstance(actor, discord.Member) else None, "roles_created", role, settings)


@bot.event
async def on_webhooks_update(channel):
    guild = channel.guild
    ensure_guild(guild.id)
    settings = _db[str(guild.id)]
    if not settings.get("guard_enabled", False) or not settings.get("antinuke", {}).get("webhooks_created", False):
        return
    actor = await fetch_audit_actor(guild, discord.AuditLogAction.webhook_create)
    if actor and isinstance(actor, discord.Member) and is_whitelisted(settings, "antinuke", actor):
        return
    await perform_punishments(guild, actor if isinstance(actor, discord.Member) else None, "webhooks_created", channel, settings)


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    ensure_guild(guild.id)
    settings = _db[str(guild.id)]
    if not settings.get("guard_enabled", False) or not settings.get("antinuke", {}).get("member_bans", False):
        return
    actor = await fetch_audit_actor(guild, discord.AuditLogAction.ban, target_id=user.id)
    if actor and isinstance(actor, discord.Member) and is_whitelisted(settings, "antinuke", actor):
        return
    await perform_punishments(guild, actor if isinstance(actor, discord.Member) else None, "member_bans", user, settings)


@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    ensure_guild(guild.id)
    settings = _db[str(guild.id)]
    if not settings.get("guard_enabled", False) or not settings.get("antinuke", {}).get("member_kicks", False):
        return
    actor = await fetch_audit_actor(guild, discord.AuditLogAction.kick, target_id=member.id)
    if actor and isinstance(actor, discord.Member) and is_whitelisted(settings, "antinuke", actor):
        return
    if actor:
        await perform_punishments(guild, actor if isinstance(actor, discord.Member) else None, "member_kicks", member, settings)


@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    ensure_guild(guild.id)
    settings = _db[str(guild.id)]
    if not settings.get("guard_enabled", False):
        return
    # bots added detection
    if member.bot and settings.get("antinuke", {}).get("bots_added", False):
        actor = await fetch_audit_actor(guild, discord.AuditLogAction.bot_add, target_id=member.id)
        if actor and isinstance(actor, discord.Member) and is_whitelisted(settings, "antinuke", actor):
            return
        await perform_punishments(guild, actor if isinstance(actor, discord.Member) else None, "bots_added", member, settings)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    guild = message.guild
    ensure_guild(guild.id)
    settings = _db[str(guild.id)]
    if not settings.get("guard_enabled", False):
        return
    author = message.author
    if is_whitelisted(settings, "automod", author):
        await bot.process_commands(message)
        return

    automod = settings.get("automod", {})
    # link/invite filter
    if automod.get("link_invite_filter", False):
        content = message.content.lower()
        if "discord.gg/" in content or "discord.com/invite" in content or "http://" in content or "https://" in content:
            try:
                await message.delete()
            except Exception:
                pass
            embed = discord.Embed(title="Guardian — AutoMod Link Blocked", color=discord.Color.orange(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name="User", value=f"{author} ({author.id})", inline=True)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.add_field(name="Content", value=(message.content[:1024] or "(empty)"), inline=False)
            await send_log_embed(guild, embed, settings)
            return

    # mass mention protection
    if automod.get("mass_mention_protection", False):
        thr = int(automod.get("mass_mention_threshold", 5))
        if len(message.mentions) >= thr:
            try:
                await message.delete()
            except Exception:
                pass
            embed = discord.Embed(title="Guardian — AutoMod Mass Mention", color=discord.Color.orange(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name="User", value=f"{author} ({author.id})", inline=True)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.add_field(name="Mentions Count", value=str(len(message.mentions)), inline=False)
            await send_log_embed(guild, embed, settings)
            return

    await bot.process_commands(message)


### ---------------- KEEP-ALIVE (Flask) ---------------- ###
app = Flask("guardian-keepalive")

@app.route("/")
def home():
    return jsonify({"status": "ok", "timestamp": datetime.datetime.utcnow().isoformat()})

def run_flask():
    # recommended for Render: use 0.0.0.0 and port from env
    host = "0.0.0.0"
    port = KEEP_ALIVE_PORT
    app.run(host=host, port=port, threaded=True)

### ---------------- STARTUP ---------------- ###
@bot.event
async def on_ready():
    # load DB on start
    await load_db()
    print(f"Logged in as {bot.user} (id: {bot.user.id}) — connected to {len(bot.guilds)} guilds")
    try:
        await tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print("Failed to sync slash commands:", e)

if __name__ == "__main__":
    # start keep-alive server in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    # load DB and run bot
    asyncio.run(load_db())
    bot.run(TOKEN)
