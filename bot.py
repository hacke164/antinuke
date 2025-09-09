# bot.py
import os
import json
from typing import Dict, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import utcnow

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set.")

SETTINGS_FILE = "guild_settings.json"

# ---------------- INTENTS ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- FEATURES ----------------
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
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_settings(data: Dict[str, Any]):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

settings = load_settings()  # dictionary keyed by guild_id (str)


def get_guild_settings(guild_id: int) -> Dict[str, Any]:
    gid = str(guild_id)
    if gid not in settings:
        settings[gid] = {
            "enabled": False,
            "antinuke": {feat: False for feat in ANTINUKE_FEATURES},
            "responses": {act: False for act in RESPONSE_ACTIONS},
            "automod": {feat: False for feat in AUTOMOD_FEATURES},
            "whitelist_users": [],
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
        e.set_author(name=guild.name, icon_url=guild.icon.url)
    e.set_thumbnail(url=bot.user.display_avatar.url)

    e.add_field(
        name="Antinuke",
        value="\n".join([format_feature_line(k, guild_settings["antinuke"].get(k, False)) for k in ANTINUKE_FEATURES]),
        inline=False,
    )
    e.add_field(
        name="Response Actions",
        value="\n".join([format_feature_line(k, guild_settings["responses"].get(k, False)) for k in RESPONSE_ACTIONS]),
        inline=False,
    )
    e.add_field(
        name="AutoMod",
        value="\n".join([format_feature_line(k, guild_settings["automod"].get(k, False)) for k in AUTOMOD_FEATURES]),
        inline=False,
    )
    e.add_field(
        name="Whitelist",
        value=f"Users: {', '.join(guild_settings.get('whitelist_users', [])) or 'None'}\nRoles: {', '.join(guild_settings.get('whitelist_roles', [])) or 'None'}",
        inline=False,
    )
    e.set_footer(text="Click the buttons below to toggle each option. Only admins can change settings.")
    return e


# ---------------- UI Components ----------------
class GuardView(discord.ui.View):
    def __init__(self, guild: discord.Guild, guild_settings: Dict[str, Any]):
        super().__init__(timeout=None)
        self.guild = guild
        self.guild_settings = guild_settings

        for feat in ANTINUKE_FEATURES:
            self.add_item(ToggleButton("antinuke", feat, guild_settings))

        for act in RESPONSE_ACTIONS:
            self.add_item(ToggleButton("responses", act, guild_settings))

        for feat in AUTOMOD_FEATURES:
            self.add_item(ToggleButton("automod", feat, guild_settings))

        self.add_item(WhitelistButton(guild_settings))
        self.add_item(SaveButton(guild_settings))


class ToggleButton(discord.ui.Button):
    def __init__(self, category: str, key: str, guild_settings: Dict[str, Any]):
        self.category = category
        self.key = key
        self.guild_settings = guild_settings
        enabled = guild_settings[category].get(key, False)
        label = f"{key}"
        style = discord.ButtonStyle.green if enabled else discord.ButtonStyle.danger
        super().__init__(label=label, style=style)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return
        current = self.guild_settings[self.category].get(self.key, False)
        self.guild_settings[self.category][self.key] = not current
        save_settings(settings)

        # update button color
        self.style = discord.ButtonStyle.green if not current else discord.ButtonStyle.danger

        # rebuild embed
        embed = build_guard_embed(interaction.guild, self.guild_settings)
        await interaction.response.edit_message(embed=embed, view=self)


class SaveButton(discord.ui.Button):
    def __init__(self, guild_settings: Dict[str, Any]):
        self.guild_settings = guild_settings
        super().__init__(label="Save / Update", style=discord.ButtonStyle.blurple)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admins only.", ephemeral=True)
            return
        save_settings(settings)
        embed = build_guard_embed(interaction.guild, self.guild_settings)
        await interaction.response.edit_message(embed=embed, view=self.view)


class WhitelistButton(discord.ui.Button):
    def __init__(self, guild_settings: Dict[str, Any]):
        self.guild_settings = guild_settings
        super().__init__(label="Edit Whitelist", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admins only.", ephemeral=True)
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
            await interaction.response.send_message(f"Added {id_str} to whitelist.", ephemeral=True)
        elif action == "remove":
            self.guild_settings["whitelist_users"] = [x for x in self.guild_settings["whitelist_users"] if x != id_str]
            await interaction.response.send_message(f"Removed {id_str} from whitelist.", ephemeral=True)
        else:
            await interaction.response.send_message("Action must be add/remove.", ephemeral=True)

        save_settings(settings)


# ---------------- Commands ----------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()

@bot.tree.command(name="about", description="Show Guardian bot info")
async def about(interaction: discord.Interaction):
    e = discord.Embed(
        title="Guardian — Server Protection",
        description="Your all-in-one Discord security solution. Guardian Bot provides powerful, customizable protection against raids, spam, and malicious activity to ensure your server remains a safe and welcoming space for all members.",
        color=0x5865F2,
    )
    e.set_footer(text="Guardian Bot")
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="enable_guard", description="Enable Guardian and open panel")
async def enable_guard(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Admins only.", ephemeral=True)
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
        await interaction.response.send_message("Admins only.", ephemeral=True)
        return
    gs = get_guild_settings(interaction.guild.id)
    gs["enabled"] = False
    save_settings(settings)
    await interaction.response.send_message("Guardian disabled.")

# ---------------- Run ----------------
if __name__ == "__main__":
    bot.run(TOKEN)
