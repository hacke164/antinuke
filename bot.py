# bot.py
import os
os.environ["DISCORD_NO_VOICE"] = "true"  # disable voice to avoid audioop imports on Python 3.13+

import json
import asyncio
import discord
from discord.ext import commands
from discord import AuditLogAction

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")  # set in Render or environment
DATA_DIR = "data"
FEATURES_FILE = os.path.join(DATA_DIR, "features.json")
WHITELIST_FILE = os.path.join(DATA_DIR, "whitelist.json")

LOG_CHANNEL_NAME = "server-logs"

# Default per-guild features structure
DEFAULT_GUILD_FEATURES = {
    "Antinuke": {
        "Ban": False,
        "Kick": False,
        "Channel Create": False,
        "Channel Delete": False,
        "Channel Update": False,
        "Role Create": False,
        "Role Delete": False,
        "Role Update": False,
        "Webhook Management": False,
        "Emojis & Stickers Management": False,
        "Server Update": False,
        "Member Role Update": False
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
    }
}

# Simple bad words sample (extend as needed)
BAD_WORDS = ["badword1", "badword2", "swear", "anotherbadword"]

# ---------------- INTENTS & BOT ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.emojis_and_stickers = True
intents.webhooks = True
intents.bans = True
intents.invites = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ---------------- STORAGE ----------------
os.makedirs(DATA_DIR, exist_ok=True)
io_lock = asyncio.Lock()


async def safe_load(path, default):
    async with io_lock:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2)
            return default.copy()
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return default.copy()


async def safe_save(path, data):
    async with io_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


# in-memory state (populated in on_ready)
features = {}   # structure: {guild_id: { "Antinuke":{...}, "Automod":{...} }}
whitelist = {}  # structure: {guild_id: {user_id: {"antinuke":[...], "automod":[...]}}}

# ---------------- Logging (per guild channel) ----------------
async def get_or_create_log_channel(guild: discord.Guild) -> discord.TextChannel:
    """Return an existing channel named LOG_CHANNEL_NAME in guild or create it."""
    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
    if channel:
        return channel
    # create with default permissions
    try:
        channel = await guild.create_text_channel(LOG_CHANNEL_NAME, reason="Creating log channel for Guard bot")
        return channel
    except Exception:
        # fallback: return None if cannot create
        return None


async def log_action(guild: discord.Guild, message: str):
    """Send a log message to the guild's log channel if available."""
    channel = await get_or_create_log_channel(guild)
    if channel:
        try:
            await channel.send(message)
        except Exception:
            pass


# ---------------- Helpers ----------------
def ensure_guild_defaults(gid: str):
    """Ensure features and whitelist have default entries for this guild id (string)."""
    if gid not in features:
        features[gid] = DEFAULT_GUILD_FEATURES.copy()
        # deep copy inner dicts
        features[gid]["Antinuke"] = DEFAULT_GUILD_FEATURES["Antinuke"].copy()
        features[gid]["Automod"] = DEFAULT_GUILD_FEATURES["Automod"].copy()
    if gid not in whitelist:
        whitelist[gid] = {}


def is_user_whitelisted(guild_id: int, user_id: int, category: str, feature: str) -> bool:
    """Check per-guild per-user per-feature whitelist.
    category should be 'antinuke' or 'automod' (lowercase)."""
    g = str(guild_id)
    u = str(user_id)
    if g not in whitelist:
        return False
    if u not in whitelist[g]:
        return False
    return feature in map(str, whitelist[g][u].get(category, []))


async def persist_all():
    await safe_save(FEATURES_FILE, features)
    await safe_save(WHITELIST_FILE, whitelist)


async def get_audit_actor(guild: discord.Guild, action: AuditLogAction, target_id: int):
    """Try to get actor who performed action by scanning recent audit log entries."""
    try:
        await asyncio.sleep(1)  # small delay to let audit log populate
        async for entry in guild.audit_logs(limit=6, action=action):
            try:
                # entry.target may be object or id
                target = entry.target
                tid = getattr(target, "id", None) or target
                if tid == target_id:
                    return entry.user
            except Exception:
                continue
    except Exception:
        return None
    return None


# ---------------- Guard UI (View + programmatic selects) ----------------
class GuardView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild = guild
        self.selected_user = None
        self.selected_antinuke = []
        self.selected_automod = []

        # create Selects programmatically to avoid decorator compatibility issues
        ant_options = [discord.SelectOption(label=f) for f in DEFAULT_GUILD_FEATURES["Antinuke"].keys()]
        auto_options = [discord.SelectOption(label=f) for f in DEFAULT_GUILD_FEATURES["Automod"].keys()]

        self.antinuke_select = discord.ui.Select(
            placeholder="Select Antinuke features to whitelist (multi)...",
            options=ant_options,
            min_values=0,
            max_values=len(ant_options)
        )
        self.antinuke_select.callback = self._antinuke_select_cb
        self.add_item(self.antinuke_select)

        self.automod_select = discord.ui.Select(
            placeholder="Select Automod features to whitelist (multi)...",
            options=auto_options,
            min_values=0,
            max_values=len(auto_options)
        )
        self.automod_select.callback = self._automod_select_cb
        self.add_item(self.automod_select)

        # UserSelect (special component)
        try:
            user_sel = discord.ui.UserSelect(placeholder="Select a user to whitelist (single)...", min_values=1, max_values=1)
            user_sel.callback = self._user_select_cb
            self.add_item(user_sel)
        except Exception:
            # fallback: use a regular Select for mention strings (less ideal)
            pass

    # callbacks for selects
    async def _antinuke_select_cb(self, interaction: discord.Interaction):
        self.selected_antinuke = list(self.antinuke_select.values)
        await interaction.response.defer()

    async def _automod_select_cb(self, interaction: discord.Interaction):
        self.selected_automod = list(self.automod_select.values)
        await interaction.response.defer()

    async def _user_select_cb(self, interaction: discord.Interaction):
        # select.values[0] should be Member object
        try:
            val = interaction.data.get("resolved", None)
        except Exception:
            val = None
        # safer: use the built-in select values
        sel = None
        for child in self.children:
            if isinstance(child, discord.ui.UserSelect):
                vals = child.values
                if vals:
                    sel = vals[0]
                    break
        if sel:
            self.selected_user = sel
        await interaction.response.defer()

    def create_embed(self):
        gid = str(self.guild.id)
        ensure_guild_defaults(gid)
        ant = features[gid]["Antinuke"]
        auto = features[gid]["Automod"]

        embed = discord.Embed(title=f"{self.guild.name} Guard System", color=discord.Color.blue())
        if self.guild.icon:
            embed.set_thumbnail(url=self.guild.icon.url)

        ant_text = "\n".join(f"{'✅' if v else '❌'} **{k}**" for k, v in ant.items())
        auto_text = "\n".join(f"{'✅' if v else '❌'} **{k}**" for k, v in auto.items())
        embed.add_field(name="🛡️ Antinuke", value=ant_text or "None", inline=True)
        embed.add_field(name="🔨 Automod", value=auto_text or "None", inline=True)

        # whitelist preview for this guild
        wl_text = "No whitelisted users."
        gwl = whitelist.get(gid, {})
        if gwl:
            parts = []
            for uid, data in gwl.items():
                m = self.guild.get_member(int(uid))
                name = m.display_name if m else f"<@{uid}>"
                a = ", ".join(data.get("antinuke", [])) or "None"
                b = ", ".join(data.get("automod", [])) or "None"
                parts.append(f"**{name}**\nAntinuke: {a}\nAutomod: {b}")
            wl_text = "\n\n".join(parts)
        embed.add_field(name="➕ User Whitelist", value=wl_text, inline=False)

        if self.selected_user:
            preview = f"{self.selected_user.mention}\nAntinuke: {', '.join(self.selected_antinuke) or 'None'}\nAutomod: {', '.join(self.selected_automod) or 'None'}"
            embed.add_field(name="Current Selection", value=preview, inline=False)

        embed.set_footer(text="Powered by EvX Official")
        return embed

    # Buttons
    @discord.ui.button(label="Toggle Antinuke (all)", style=discord.ButtonStyle.secondary)
    async def toggle_ant_all(self, button: discord.ui.Button, interaction: discord.Interaction):
        gid = str(self.guild.id)
        ensure_guild_defaults(gid)
        all_on = all(features[gid]["Antinuke"].values())
        for k in features[gid]["Antinuke"]:
            features[gid]["Antinuke"][k] = not all_on
        await persist_all()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
        await log_action(self.guild, f"🔐 Antinuke toggled to {'ON' if not all_on else 'OFF'} by {interaction.user.mention}")

    @discord.ui.button(label="Toggle Automod (all)", style=discord.ButtonStyle.secondary)
    async def toggle_auto_all(self, button: discord.ui.Button, interaction: discord.Interaction):
        gid = str(self.guild.id)
        ensure_guild_defaults(gid)
        all_on = all(features[gid]["Automod"].values())
        for k in features[gid]["Automod"]:
            features[gid]["Automod"][k] = not all_on
        await persist_all()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
        await log_action(self.guild, f"🛡️ Automod toggled to {'ON' if not all_on else 'OFF'} by {interaction.user.mention}")

    @discord.ui.button(label="Whitelist (apply)", style=discord.ButtonStyle.success)
    async def whitelist_apply(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.selected_user:
            await interaction.response.send_message("Please select a user first.", ephemeral=True)
            return
        gid = str(self.guild.id)
        ensure_guild_defaults(gid)
        uid = str(self.selected_user.id)
        if gid not in whitelist:
            whitelist[gid] = {}
        whitelist[gid][uid] = {
            "antinuke": self.selected_antinuke,
            "automod": self.selected_automod
        }
        await persist_all()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
        await log_action(self.guild, f"✅ {self.selected_user.mention} whitelisted for Antinuke: {', '.join(self.selected_antinuke) or 'None'} · Automod: {', '.join(self.selected_automod) or 'None'} by {interaction.user.mention}")

    @discord.ui.button(label="Remove Whitelist (selected)", style=discord.ButtonStyle.danger)
    async def whitelist_remove(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.selected_user:
            await interaction.response.send_message("Please select a user first.", ephemeral=True)
            return
        gid = str(self.guild.id)
        uid = str(self.selected_user.id)
        if gid in whitelist and uid in whitelist[gid]:
            del whitelist[gid][uid]
            await persist_all()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
            await log_action(self.guild, f"❌ {self.selected_user.mention} removed from whitelist by {interaction.user.mention}")
        else:
            await interaction.response.send_message("That user is not whitelisted.", ephemeral=True)


# ---------------- Slash commands (admin only) ----------------
def admin_only():
    async def predicate(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You must be an administrator to use this command.", ephemeral=True)
            return False
        return True
    return discord.app_commands.check(predicate)


@tree.command(name="enable_guard", description="Open the Guard panel (admin only).")
@admin_only()
async def enable_guard(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    ensure_guild_defaults(gid)
    view = GuardView(interaction.guild)
    embed = view.create_embed()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@tree.command(name="disable_guard", description="Disable all guard features and clear whitelist for this guild.")
@admin_only()
async def disable_guard(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    features[gid] = {
        "Antinuke": {k: False for k in DEFAULT_GUILD_FEATURES["Antinuke"].keys()},
        "Automod": {k: False for k in DEFAULT_GUILD_FEATURES["Automod"].keys()}
    }
    whitelist.pop(gid, None)
    await persist_all()
    await interaction.response.send_message("Guard disabled and whitelist cleared for this server.", ephemeral=True)
    await log_action(interaction.guild, f"❌ Guard disabled and whitelist cleared by {interaction.user.mention}")


@tree.command(name="about", description="Info about this Guard bot.")
async def about(interaction: discord.Interaction):
    await interaction.response.send_message("Guard Bot — Antinuke + Automod + Whitelist (per-guild).", ephemeral=True)


@tree.command(name="show_whitelist", description="Show current whitelist for this server (admin only).")
@admin_only()
async def show_whitelist(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    ensure_guild_defaults(gid)
    gwl = whitelist.get(gid, {})
    if not gwl:
        await interaction.response.send_message("No users whitelisted on this server.", ephemeral=True)
        return
    lines = []
    for uid, data in gwl.items():
        member = interaction.guild.get_member(int(uid))
        name = member.display_name if member else f"<@{uid}>"
        lines.append(f"**{name}** — Antinuke: {', '.join(data.get('antinuke', [])) or 'None'}; Automod: {', '.join(data.get('automod', [])) or 'None'}")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


# ---------------- Antinuke event handlers ----------------
@bot.event
async def on_member_ban(guild, user):
    # guild param in on_member_ban is actually Guild object (discord.py signature)
    try:
        gid = str(guild.id)
        if not features.get(gid, {}).get("Antinuke", {}).get("Ban", False):
            return
        actor = await get_audit_actor(guild, AuditLogAction.ban, user.id)
        if actor and not is_user_whitelisted(guild.id, actor.id, "antinuke", "Ban"):
            # unban the user
            try:
                await guild.unban(user, reason="Antinuke: unauthorized ban")
                await log_action(guild, f"⛔ Unbanned {user} after unauthorized ban by {actor.mention}")
            except Exception as e:
                await log_action(guild, f"⚠️ Failed to unban {user}: {e}")
    except Exception as e:
        print("on_member_ban error:", e)


@bot.event
async def on_member_remove(member):
    try:
        guild = member.guild
        gid = str(guild.id)
        if not features.get(gid, {}).get("Antinuke", {}).get("Kick", False):
            return
        actor = await get_audit_actor(guild, AuditLogAction.kick, member.id)
        if actor and not is_user_whitelisted(guild.id, actor.id, "antinuke", "Kick"):
            await log_action(guild, f"⚠️ Unauthorized kick detected: {member.mention} was kicked by {actor.mention}")
            # optionally punish actor: await actor.kick(reason="Antinuke: unauthorized kick")
    except Exception as e:
        print("on_member_remove error:", e)


@bot.event
async def on_guild_channel_create(channel):
    try:
        guild = channel.guild
        gid = str(guild.id)
        if not features.get(gid, {}).get("Antinuke", {}).get("Channel Create", False):
            return
        actor = await get_audit_actor(guild, AuditLogAction.channel_create, channel.id)
        if actor and not is_user_whitelisted(guild.id, actor.id, "antinuke", "Channel Create"):
            try:
                await channel.delete(reason="Antinuke: unauthorized channel creation")
                await log_action(guild, f"🗑️ Deleted unauthorized channel {channel.name} created by {actor.mention}")
            except Exception as e:
                await log_action(guild, f"⚠️ Failed to delete unauthorized channel {channel.name}: {e}")
    except Exception as e:
        print("on_guild_channel_create error:", e)


@bot.event
async def on_guild_channel_delete(channel):
    try:
        guild = channel.guild
        gid = str(guild.id)
        if not features.get(gid, {}).get("Antinuke", {}).get("Channel Delete", False):
            return
        actor = await get_audit_actor(guild, AuditLogAction.channel_delete, channel.id)
        if actor and not is_user_whitelisted(guild.id, actor.id, "antinuke", "Channel Delete"):
            # recreate minimal text channel with same name
            try:
                new_channel = await guild.create_text_channel(name=channel.name, reason="Antinuke: restore deleted channel")
                await log_action(guild, f"🔁 Recreated channel {new_channel.name} after unauthorized deletion by {actor.mention}")
            except Exception as e:
                await log_action(guild, f"⚠️ Failed to recreate channel {channel.name}: {e}")
    except Exception as e:
        print("on_guild_channel_delete error:", e)


@bot.event
async def on_guild_channel_update(before, after):
    try:
        guild = after.guild
        gid = str(guild.id)
        if not features.get(gid, {}).get("Antinuke", {}).get("Channel Update", False):
            return
        actor = await get_audit_actor(guild, AuditLogAction.channel_update, after.id)
        if actor and not is_user_whitelisted(guild.id, actor.id, "antinuke", "Channel Update"):
            try:
                await after.edit(name=before.name, topic=before.topic, reason="Antinuke: revert channel update")
                await log_action(guild, f"🔄 Reverted update on channel {after.name} made by {actor.mention}")
            except Exception as e:
                await log_action(guild, f"⚠️ Failed to revert channel {after.name}: {e}")
    except Exception as e:
        print("on_guild_channel_update error:", e)


@bot.event
async def on_guild_role_create(role):
    try:
        guild = role.guild
        gid = str(guild.id)
        if not features.get(gid, {}).get("Antinuke", {}).get("Role Create", False):
            return
        actor = await get_audit_actor(guild, AuditLogAction.role_create, role.id)
        if actor and not is_user_whitelisted(guild.id, actor.id, "antinuke", "Role Create"):
            try:
                await role.delete(reason="Antinuke: unauthorized role creation")
                await log_action(guild, f"🗑️ Deleted unauthorized role {role.name} created by {actor.mention}")
            except Exception as e:
                await log_action(guild, f"⚠️ Failed to delete role {role.name}: {e}")
    except Exception as e:
        print("on_guild_role_create error:", e)


@bot.event
async def on_guild_role_delete(role):
    try:
        guild = role.guild
        gid = str(guild.id)
        if not features.get(gid, {}).get("Antinuke", {}).get("Role Delete", False):
            return
        actor = await get_audit_actor(guild, AuditLogAction.role_delete, role.id)
        if actor and not is_user_whitelisted(guild.id, actor.id, "antinuke", "Role Delete"):
            await log_action(guild, f"⚠️ Role {role.name} was deleted by {actor.mention} (no auto-restore implemented)")
    except Exception as e:
        print("on_guild_role_delete error:", e)


@bot.event
async def on_guild_role_update(before, after):
    try:
        guild = after.guild
        gid = str(guild.id)
        if not features.get(gid, {}).get("Antinuke", {}).get("Role Update", False):
            return
        actor = await get_audit_actor(guild, AuditLogAction.role_update, after.id)
        if actor and not is_user_whitelisted(guild.id, actor.id, "antinuke", "Role Update"):
            try:
                await after.edit(name=before.name, reason="Antinuke: revert role update")
                await log_action(guild, f"🔄 Reverted role update on {after.name} done by {actor.mention}")
            except Exception as e:
                await log_action(guild, f"⚠️ Failed to revert role {after.name}: {e}")
    except Exception as e:
        print("on_guild_role_update error:", e)


# ---------------- Automod: on_message ----------------
@bot.event
async def on_message(message: discord.Message):
    # ignore bots & DMs
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    gid = str(message.guild.id)
    ensure_guild_defaults(gid)

    # quick helper to check whitelist (per-user feature)
    def whitelisted(u_id, category, feat):
        return is_user_whitelisted(int(gid), int(u_id), category, feat)

    # Bad words
    if features[gid]["Automod"].get("Bad Words Filter", False):
        if not whitelisted(message.author.id, "automod", "Bad Words Filter"):
            content = (message.content or "").lower()
            if any(bw.lower() in content for bw in BAD_WORDS):
                try:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention}, that word is not allowed!", delete_after=6)
                    await log_action(message.guild, f"🚨 Automod: Deleted message by {message.author.mention} for bad language.")
                except Exception:
                    pass
                finally:
                    await bot.process_commands(message)
                    return

    # Link Filter
    if features[gid]["Automod"].get("Link Filter", False):
        if not whitelisted(message.author.id, "automod", "Link Filter"):
            cont = (message.content or "").lower()
            if "http://" in cont or "https://" in cont or ".com" in cont or ".gg/" in cont:
                try:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention}, links are not allowed!", delete_after=6)
                    await log_action(message.guild, f"🚨 Automod: Deleted link from {message.author.mention}")
                except Exception:
                    pass
                finally:
                    await bot.process_commands(message)
                    return

    # Invite Filter
    if features[gid]["Automod"].get("Invite Filter", False):
        if not whitelisted(message.author.id, "automod", "Invite Filter"):
            cont = (message.content or "").lower()
            if "discord.gg/" in cont or "discord.com/invite/" in cont:
                try:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention}, invites are not allowed!", delete_after=6)
                    await log_action(message.guild, f"🚨 Automod: Deleted invite from {message.author.mention}")
                except Exception:
                    pass
                finally:
                    await bot.process_commands(message)
                    return

    # Caps Filter
    if features[gid]["Automod"].get("Caps Filter", False):
        if not whitelisted(message.author.id, "automod", "Caps Filter"):
            content = message.content or ""
            if len(content) >= 8:
                letters = sum(1 for c in content if c.isalpha())
                up = sum(1 for c in content if c.isupper())
                if letters > 0 and up / letters > 0.7:
                    try:
                        await message.delete()
                        await message.channel.send(f"{message.author.mention}, please don't use excessive caps.", delete_after=6)
                        await log_action(message.guild, f"🚨 Automod: Deleted caps message from {message.author.mention}")
                    except Exception:
                        pass
                    finally:
                        await bot.process_commands(message)
                        return

    # Mention Spam Filter
    if features[gid]["Automod"].get("Mention Spam Filter", False):
        if not whitelisted(message.author.id, "automod", "Mention Spam Filter"):
            if len(message.mentions) > 5:
                try:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention}, too many mentions!", delete_after=6)
                    await log_action(message.guild, f"🚨 Automod: Deleted mention-spam from {message.author.mention}")
                except Exception:
                    pass
                finally:
                    await bot.process_commands(message)
                    return

    # Image Filter (attachments)
    if features[gid]["Automod"].get("Image Filter", False):
        if not whitelisted(message.author.id, "automod", "Image Filter"):
            for a in message.attachments:
                if a.content_type and a.content_type.startswith("image/"):
                    try:
                        await message.delete()
                        await message.channel.send(f"{message.author.mention}, images are not allowed!", delete_after=6)
                        await log_action(message.guild, f"🚨 Automod: Deleted image from {message.author.mention}")
                    except Exception:
                        pass
                    finally:
                        await bot.process_commands(message)
                        return

    # Let commands process
    await bot.process_commands(message)


# ---------------- on_ready (load state + ensure defaults + create log channels) ----------------
@bot.event
async def on_ready():
    global features, whitelist
    # load persistent state
    features = await safe_load(FEATURES_FILE, {})
    whitelist = await safe_load(WHITELIST_FILE, {})

    # ensure defaults per guild
    for g in bot.guilds:
        gid = str(g.id)
        ensure_guild_defaults(gid)
        # ensure log channel exists
        try:
            await get_or_create_log_channel(g)
        except Exception:
            pass

    # persist any added defaults
    await persist_all()

    # sync commands
    try:
        await tree.sync()
    except Exception:
        pass

    print(f"{bot.user} ready. Guilds: {len(bot.guilds)}")


# ---------------- Run ----------------
if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("TOKEN environment variable not set. Add it to Render environment variables.")
    bot.run(TOKEN)
