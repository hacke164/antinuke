# bot.py
import os
import json
import threading
from typing import Dict, Any, Optional, List

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import utcnow

# ---- KEEP ALIVE WEB SERVER ----
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "Guardian Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.start()


# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set. Set TOKEN in env variables.")

SETTINGS_FILE = "guild_settings.json"

# ---------------- INTENTS ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- FEATURE LISTS ----------------
ANTINUKE_FEATURES = [
    "channels_deleted",
    "channels_created",
    "roles_deleted",
    "roles_created",
    "webhooks_created",
    "member_bans",
    "member_kicks",
    "bots_added",
]

RESPONSE_ACTIONS = [
    "remove_roles",
    "kick_member",
    "ban_member",
    "server_lockdown",
    "unverified_ban",
    "notify_admins",
]

AUTOMOD_FEATURES = [
    "link_invite_filtering",
    "mass_mention_protection",
]

# ---------------- Persistence helpers ----------------
def load_settings() -> Dict[str, Any]:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(data: Dict[str, Any]):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print("Failed to save settings:", e)

settings = load_settings()  # keyed by guild id as string


def get_guild_settings(guild_id: int) -> Dict[str, Any]:
    gid = str(guild_id)
    if gid not in settings:
        settings[gid] = {
            "enabled": False,
            "antinuke": {feat: False for feat in ANTINUKE_FEATURES},
            "responses": {act: False for act in RESPONSE_ACTIONS},
            "automod": {feat: False for feat in AUTOMOD_FEATURES},
            "whitelist_users": [],  # store as strings
            "whitelist_roles": [],
            "locked": False,
            "mass_mention_threshold": 5,
        }
        save_settings(settings)
    return settings[gid]


# ---------------- Utilities ----------------
def format_feature_line(name: str, enabled: bool) -> str:
    mark = "✅" if enabled else "❌"
    return f"{mark} `{name}`"

def build_guard_embed(guild: discord.Guild, guild_settings: Dict[str, Any]) -> discord.Embed:
    e = discord.Embed(
        title=f"{guild.name} — Guardian Settings",
        description="Antinuke & AutoMod control panel",
        color=0x2F3136,
    )
    if guild.icon:
        try:
            e.set_author(name=guild.name, icon_url=guild.icon.url)
        except Exception:
            e.set_author(name=guild.name)
    # bot thumbnail
    try:
        e.set_thumbnail(url=bot.user.display_avatar.url)
    except Exception:
        pass

    e.add_field(
        name="Antinuke",
        value="\n".join([format_feature_line(k, guild_settings["antinuke"].get(k, False)) for k in ANTINUKE_FEATURES]) or "No features",
        inline=False,
    )
    e.add_field(
        name="Response Actions",
        value="\n".join([format_feature_line(k, guild_settings["responses"].get(k, False)) for k in RESPONSE_ACTIONS]) or "No actions",
        inline=False,
    )
    e.add_field(
        name="AutoMod",
        value="\n".join([format_feature_line(k, guild_settings["automod"].get(k, False)) for k in AUTOMOD_FEATURES]) or "No automod",
        inline=False,
    )
    e.add_field(
        name="Whitelist (Users / Roles)",
        value=f"Users: {', '.join(guild_settings.get('whitelist_users', [])) or 'None'}\nRoles: {', '.join(guild_settings.get('whitelist_roles', [])) or 'None'}",
        inline=False,
    )
    e.set_footer(text="Only administrators can change settings. Use Save / Update after whitelist changes to refresh the panel.")
    return e


async def is_whitelisted(guild_settings: Dict[str, Any], member: discord.Member) -> bool:
    # admins auto-whitelisted
    try:
        if member.guild_permissions.administrator:
            return True
    except Exception:
        pass
    if str(member.id) in [str(x) for x in guild_settings.get("whitelist_users", [])]:
        return True
    for r in member.roles:
        if str(r.id) in [str(x) for x in guild_settings.get("whitelist_roles", [])]:
            return True
    return False


async def apply_responses(guild: discord.Guild, executor: discord.Member, reason: str, guild_settings: Dict[str, Any]) -> List[str]:
    """
    Apply configured response actions to executor.
    Returns a list of results for logging.
    """
    results: List[str] = []
    try:
        if await is_whitelisted(guild_settings, executor):
            results.append("whitelisted")
            return results
    except Exception:
        results.append("whitelist_check_failed")

    # remove_roles
    if guild_settings["responses"].get("remove_roles"):
        try:
            roles_to_remove = [r for r in executor.roles if r != guild.default_role]
            if roles_to_remove:
                await executor.remove_roles(*roles_to_remove, reason=reason[:1900])
            results.append("removed_roles")
        except Exception as e:
            results.append(f"remove_roles_failed:{e}")

    # kick_member
    if guild_settings["responses"].get("kick_member"):
        try:
            await guild.kick(executor, reason=reason[:1900])
            results.append("kicked")
        except Exception as e:
            results.append(f"kick_failed:{e}")

    # ban_member
    if guild_settings["responses"].get("ban_member"):
        try:
            await guild.ban(executor, reason=reason[:1900])
            results.append("banned")
        except Exception as e:
            results.append(f"ban_failed:{e}")

    # notify_admins
    if guild_settings["responses"].get("notify_admins"):
        try:
            owner = guild.owner
            if owner:
                await owner.send(f"[Guardian] Action taken against {executor} ({executor.id}) in guild {guild.name}: {', '.join(results) or 'no action'}. Reason: {reason}")
            results.append("notified_owner")
        except Exception as e:
            results.append(f"notify_failed:{e}")

    # server_lockdown (set permission overwrite for @everyone in all text channels)
    if guild_settings["responses"].get("server_lockdown"):
        try:
            if not guild_settings.get("locked"):
                for channel in guild.text_channels:
                    try:
                        overwrite = channel.overwrites_for(guild.default_role)
                        overwrite.send_messages = False
                        await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Guardian server lockdown")
                    except Exception:
                        continue
                guild_settings["locked"] = True
                results.append("server_locked")
            else:
                for channel in guild.text_channels:
                    try:
                        await channel.set_permissions(guild.default_role, overwrite=None, reason="Guardian unlock")
                    except Exception:
                        continue
                guild_settings["locked"] = False
                results.append("server_unlocked")
        except Exception as e:
            results.append(f"server_lock_failed:{e}")

    # unverified_ban - example: ban accounts younger than 5 minutes (placeholder logic)
    if guild_settings["responses"].get("unverified_ban"):
        try:
            created = executor.created_at
            if (utcnow() - created).total_seconds() < 60 * 60 * 24 * 7:  # e.g., account < 7 days
                try:
                    await guild.ban(executor, reason="Guardian: unverified/new account")
                    results.append("unverified_banned")
                except Exception as e:
                    results.append(f"unverified_ban_failed:{e}")
        except Exception as e:
            results.append(f"unverified_check_failed:{e}")

    save_settings(settings)
    return results


# ---------------- Audit log helper ----------------
async def check_executor_from_audit(guild: discord.Guild, action: discord.AuditLogAction, target_id: Optional[int] = None, lookback_seconds: int = 8) -> Optional[discord.User]:
    """
    Try to find the executor of an audit log action. Returns a discord.User/Member or None.
    """
    try:
        async for entry in guild.audit_logs(limit=10, action=action):
            # If we can match target id, prefer it
            try:
                if target_id and getattr(entry.target, "id", None) == int(target_id):
                    return entry.user
            except Exception:
                pass
            # fallback: if very recent
            if (utcnow() - entry.created_at).total_seconds() <= lookback_seconds:
                return entry.user
    except Exception:
        return None
    return None


# ---------------- UI Components ----------------
class GuardView(discord.ui.View):
    def __init__(self, guild: discord.Guild, guild_settings: Dict[str, Any]):
        super().__init__(timeout=None)
        self.guild = guild
        self.guild_settings = guild_settings

        # Put Antinuke toggles first
        for feat in ANTINUKE_FEATURES:
            self.add_item(ToggleButton("antinuke", feat, guild_settings))

        # Response actions
        for act in RESPONSE_ACTIONS:
            self.add_item(ToggleButton("responses", act, guild_settings))

        # Automod toggles
        for feat in AUTOMOD_FEATURES:
            self.add_item(ToggleButton("automod", feat, guild_settings))

        # Whitelist editor + Save button at end
        self.add_item(WhitelistButton(guild_settings))
        self.add_item(SaveButton(guild_settings))


class ToggleButton(discord.ui.Button):
    def __init__(self, category: str, key: str, guild_settings: Dict[str, Any]):
        self.category = category
        self.key = key
        self.guild_settings = guild_settings
        enabled = guild_settings.get(category, {}).get(key, False)
        label = key
        style = discord.ButtonStyle.green if enabled else discord.ButtonStyle.danger
        super().__init__(label=label, style=style)

    async def callback(self, interaction: discord.Interaction):
        # Only admins allowed
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only administrators can change settings.", ephemeral=True)
            return

        # Toggle the setting
        current = self.guild_settings[self.category].get(self.key, False)
        self.guild_settings[self.category][self.key] = not current
        save_settings(settings)

        # Update this button's style
        self.style = discord.ButtonStyle.green if not current else discord.ButtonStyle.danger

        # Edit the original message in-place with updated embed and full view (so all button colors persist)
        try:
            embed = build_guard_embed(interaction.guild, self.guild_settings)
            await interaction.response.edit_message(embed=embed, view=self.view)
        except Exception:
            # fallback ephemeral confirmation
            await interaction.response.send_message(f"Toggled `{self.key}` to {'ON' if not current else 'OFF'}. (Could not update panel visually)", ephemeral=True)


class SaveButton(discord.ui.Button):
    def __init__(self, guild_settings: Dict[str, Any]):
        self.guild_settings = guild_settings
        super().__init__(label="Save / Update", style=discord.ButtonStyle.blurple)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only administrators can save settings.", ephemeral=True)
            return
        save_settings(settings)
        embed = build_guard_embed(interaction.guild, self.guild_settings)
        try:
            await interaction.response.edit_message(embed=embed, view=self.view)
        except Exception:
            await interaction.response.send_message("Settings saved.", ephemeral=True)


class WhitelistButton(discord.ui.Button):
    def __init__(self, guild_settings: Dict[str, Any]):
        self.guild_settings = guild_settings
        super().__init__(label="Edit Whitelist", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only administrators can edit the whitelist.", ephemeral=True)
            return
        modal = WhitelistModal(self.guild_settings)
        await interaction.response.send_modal(modal)


class WhitelistModal(discord.ui.Modal, title="Modify Whitelist"):
    user_or_role = discord.ui.TextInput(label="User ID or Role ID", placeholder="Enter ID", required=True)
    action = discord.ui.TextInput(label="Action", placeholder="add/remove", required=True)

    def __init__(self, guild_settings: Dict[str, Any]):
        super().__init__()
        self.guild_settings = guild_settings

    async def on_submit(self, interaction: discord.Interaction):
        value = self.user_or_role.value.strip()
        action = self.action.value.strip().lower()
        if not value.isdigit():
            await interaction.response.send_message("ID must be numeric.", ephemeral=True)
            return
        id_str = str(value)

        if action == "add":
            if id_str not in self.guild_settings["whitelist_users"]:
                self.guild_settings["whitelist_users"].append(id_str)
            await interaction.response.send_message(f"Added {id_str} to whitelist (users). Click Save / Update to refresh panel.", ephemeral=True)
        elif action == "remove":
            self.guild_settings["whitelist_users"] = [x for x in self.guild_settings["whitelist_users"] if x != id_str]
            await interaction.response.send_message(f"Removed {id_str} from whitelist (users) if present. Click Save / Update to refresh panel.", ephemeral=True)
        else:
            await interaction.response.send_message("Action must be add or remove.", ephemeral=True)
        save_settings(settings)


# ---------------- Application Commands ----------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print("Failed to sync commands:", e)


@bot.tree.command(name="about", description="Show Guardian bot info")
async def about(interaction: discord.Interaction):
    e = discord.Embed(
        title="Guardian — Server Protection",
        description="Your all-in-one Discord security solution. Guardian Bot provides powerful, customizable protection against raids, spam, and malicious activity to ensure your server remains a safe and welcoming space for all members.",
        color=0x5865F2,
    )
    e.set_footer(text="Guardian Bot")
    await interaction.response.send_message(embed=e)


@bot.tree.command(name="enable_guard", description="Enable Guardian and open the control panel")
async def enable_guard(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only administrators can enable or configure the guard.", ephemeral=True)
        return
    if not interaction.guild:
        await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
        return
    gs = get_guild_settings(interaction.guild.id)
    gs["enabled"] = True
    save_settings(settings)
    embed = build_guard_embed(interaction.guild, gs)
    view = GuardView(interaction.guild, gs)
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="disable_guard", description="Disable Guardian for this server")
async def disable_guard(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only administrators can disable the guard.", ephemeral=True)
        return
    if not interaction.guild:
        await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
        return
    gs = get_guild_settings(interaction.guild.id)
    gs["enabled"] = False
    save_settings(settings)
    await interaction.response.send_message("Guardian disabled for this server.")


# ---------------- Antinuke & AutoMod Event Handlers ----------------
@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    guild = channel.guild
    gs = get_guild_settings(guild.id)
    if not gs.get("enabled"):
        return
    if not gs["antinuke"].get("channels_deleted", False):
        return
    executor = await check_executor_from_audit(guild, discord.AuditLogAction.channel_delete, target_id=channel.id)
    if not executor:
        return
    member = guild.get_member(executor.id) or executor
    if isinstance(member, discord.Member):
        await apply_responses(guild, member, f"Detected channel deleted: {channel.name}", gs)


@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    guild = channel.guild
    gs = get_guild_settings(guild.id)
    if not gs.get("enabled"):
        return
    if not gs["antinuke"].get("channels_created", False):
        return
    executor = await check_executor_from_audit(guild, discord.AuditLogAction.channel_create, target_id=channel.id)
    if not executor:
        return
    member = guild.get_member(executor.id) or executor
    if isinstance(member, discord.Member):
        await apply_responses(guild, member, f"Detected channel created: {channel.name}", gs)


@bot.event
async def on_guild_role_delete(role: discord.Role):
    guild = role.guild
    gs = get_guild_settings(guild.id)
    if not gs.get("enabled"):
        return
    if not gs["antinuke"].get("roles_deleted", False):
        return
    executor = await check_executor_from_audit(guild, discord.AuditLogAction.role_delete, target_id=role.id)
    if not executor:
        return
    member = guild.get_member(executor.id) or executor
    if isinstance(member, discord.Member):
        await apply_responses(guild, member, f"Detected role deleted: {role.name}", gs)


@bot.event
async def on_guild_role_create(role: discord.Role):
    guild = role.guild
    gs = get_guild_settings(guild.id)
    if not gs.get("enabled"):
        return
    if not gs["antinuke"].get("roles_created", False):
        return
    executor = await check_executor_from_audit(guild, discord.AuditLogAction.role_create, target_id=role.id)
    if not executor:
        return
    member = guild.get_member(executor.id) or executor
    if isinstance(member, discord.Member):
        await apply_responses(guild, member, f"Detected role created: {role.name}", gs)


@bot.event
async def on_webhooks_update(channel: discord.abc.GuildChannel):
    guild = channel.guild
    gs = get_guild_settings(guild.id)
    if not gs.get("enabled"):
        return
    if not gs["antinuke"].get("webhooks_created", False):
        return
    executor = await check_executor_from_audit(guild, discord.AuditLogAction.webhook_create)
    if not executor:
        return
    member = guild.get_member(executor.id) or executor
    if isinstance(member, discord.Member):
        await apply_responses(guild, member, f"Detected webhook change in {channel.name}", gs)


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    gs = get_guild_settings(guild.id)
    if not gs.get("enabled"):
        return
    if not gs["antinuke"].get("member_bans", False):
        return
    executor = await check_executor_from_audit(guild, discord.AuditLogAction.ban, target_id=user.id)
    if not executor:
        return
    member = guild.get_member(executor.id) or executor
    if isinstance(member, discord.Member):
        await apply_responses(guild, member, f"Detected ban of {user}", gs)


@bot.event
async def on_member_remove(member: discord.Member):
    """
    Could be voluntary leave or a kick. If kicks are enabled, look up the audit log for a recent kick.
    """
    guild = member.guild
    gs = get_guild_settings(guild.id)
    if not gs.get("enabled"):
        return
    if not gs["antinuke"].get("member_kicks", False):
        return
    executor = await check_executor_from_audit(guild, discord.AuditLogAction.kick, target_id=member.id)
    if not executor:
        return
    member_exec = guild.get_member(executor.id) or executor
    if isinstance(member_exec, discord.Member):
        await apply_responses(guild, member_exec, f"Detected kick of {member}", gs)


@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    gs = get_guild_settings(guild.id)
    if not gs.get("enabled"):
        return
    if not gs["antinuke"].get("bots_added", False):
        return
    if member.bot:
        executor = await check_executor_from_audit(guild, discord.AuditLogAction.bot_add, target_id=member.id)
        if not executor:
            return
        member_exec = guild.get_member(executor.id) or executor
        if isinstance(member_exec, discord.Member):
            await apply_responses(guild, member_exec, f"Detected bot added {member}", gs)


# ---------------- AutoMod: messages ----------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not message.guild:
        return
    gs = get_guild_settings(message.guild.id)
    if not gs.get("enabled"):
        return

    # Link & invite filtering
    if gs["automod"].get("link_invite_filtering", False):
        content = (message.content or "").lower()
        if "discord.gg/" in content or "http://" in content or "https://" in content:
            try:
                await message.delete()
            except Exception:
                pass
            # apply responses (ban/kick/remove roles/notify)
            try:
                author_member = message.guild.get_member(message.author.id)
                if author_member:
                    await apply_responses(message.guild, author_member, "AutoMod: link/invite detected", gs)
            except Exception:
                pass
            return

    # Mass mention protection
    if gs["automod"].get("mass_mention_protection", False):
        threshold = gs.get("mass_mention_threshold", 5)
        if len(message.mentions) >= threshold:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                author_member = message.guild.get_member(message.author.id)
                if author_member:
                    await apply_responses(message.guild, author_member, "AutoMod: mass mention", gs)
            except Exception:
                pass
            return

    await bot.process_commands(message)


# --------------- Start ---------------
if __name__ == "__main__":
    keep_alive()   # start Flask webserver
    bot.run(TOKEN)

