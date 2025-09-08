# bot.py
import os
import json
import asyncio
import discord
from discord.ext import commands
from discord import AuditLogAction

# Prevent voice-related imports on Python 3.13
os.environ["DISCORD_NO_VOICE"] = "true"

# --------- Config ----------
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set")

DATA_DIR = "data"
FEATURES_FILE = os.path.join(DATA_DIR, "features.json")
WHITELIST_FILE = os.path.join(DATA_DIR, "whitelist.json")

# --------- Intents ----------
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

# --------- Bot ----------
bot = commands.Bot(command_prefix="!", intents=intents)

# --------- In-memory state (will persist to disk) ----------
DEFAULT_FEATURES = {
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
        "Member Role Update": False,
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
    }
}

# basic bad words list — edit as needed
BAD_WORDS = ["badword1", "badword2", "anotherbadword", "swear"]

# thread-safety for file ops
file_lock = asyncio.Lock()

# create data dir
os.makedirs(DATA_DIR, exist_ok=True)

# load/save helpers
async def load_json(path, default):
    async with file_lock:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2)
            return default.copy()
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

async def save_json(path, data):
    async with file_lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

# initialize state
features = await load_json(FEATURES_FILE, DEFAULT_FEATURES)
whitelist = await load_json(WHITELIST_FILE, {})  # format: {guild_id: {user_id: {"antinuke": [...], "automod": [...]}}}

# ---------- Persistence convenience ----------
async def persist_state():
    await save_json(FEATURES_FILE, features)
    await save_json(WHITELIST_FILE, whitelist)

# ---------- Utility ----------
def is_whitelisted(guild_id: int, user_id: int, category: str, feature: str) -> bool:
    g = str(guild_id)
    u = str(user_id)
    return g in whitelist and u in whitelist[g] and feature in whitelist[g][u].get(category.lower(), [])

async def get_recent_audit_user(guild: discord.Guild, action: AuditLogAction, target_id: int):
    # attempt to find actor via recent audit entries
    try:
        # small delay to allow audit log to populate
        await asyncio.sleep(1)
        async for entry in guild.audit_logs(limit=5, action=action):
            # some audit entries have target as object/None; handle robustly
            try:
                if getattr(entry.target, "id", None) == target_id or entry.target == target_id:
                    return entry.user
            except Exception:
                continue
    except Exception:
        pass
    return None

# ---------- Guard UI ----------
class GuardView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild = guild
        self.selected_user: discord.Member | None = None
        self.selected_antinuke = []
        self.selected_automod = []

    def _guild_features(self):
        # returns features snapshot for embed
        ant = features.get("Antinuke", {})
        auto = features.get("Automod", {})
        return ant, auto

    def create_embed(self):
        ant, auto = self._guild_features()
        embed = discord.Embed(title=f"{self.guild.name} Guard System", color=discord.Color.blurple())
        if self.guild.icon:
            embed.set_thumbnail(url=self.guild.icon.url)
        ant_text = "\n".join(f"{'✅' if v else '❌'} **{k}**" for k, v in ant.items())
        auto_text = "\n".join(f"{'✅' if v else '❌'} **{k}**" for k, v in auto.items())
        embed.add_field(name="🛡️ Antinuke", value=ant_text or "None", inline=True)
        embed.add_field(name="🔨 Automod", value=auto_text or "None", inline=True)

        # whitelist display
        g = str(self.guild.id)
        wl_text = "No users whitelisted."
        if g in whitelist and whitelist[g]:
            parts = []
            for uid, data in whitelist[g].items():
                user = self.guild.get_member(int(uid))
                name = user.display_name if user else f"<@{uid}>"
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

    # toggle buttons for features (global toggles)
    @discord.ui.button(label="Toggle Antinuke", style=discord.ButtonStyle.secondary)
    async def toggle_ant(self, button: discord.ui.Button, interaction: discord.Interaction):
        # flip all antinuke features
        ant = features.setdefault("Antinuke", {})
        all_on = all(ant.values())
        for k in list(ant.keys()):
            ant[k] = not all_on
        await persist_state()
        await interaction.response.edit_message(embed=self.create_embed())

    @discord.ui.button(label="Toggle Automod", style=discord.ButtonStyle.secondary)
    async def toggle_auto(self, button: discord.ui.Button, interaction: discord.Interaction):
        auto = features.setdefault("Automod", {})
        all_on = all(auto.values())
        for k in list(auto.keys()):
            auto[k] = not all_on
        await persist_state()
        await interaction.response.edit_message(embed=self.create_embed())

    # user select (component type user_select)
    @discord.ui.select(placeholder="Select a user to whitelist...", select_type=discord.ComponentType.user_select)
    async def user_sel(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values:
            # select.values[0] should be a Member object for user_select
            member = select.values[0]
            # Sometimes discord.py returns str IDs. Try to handle both.
            if isinstance(member, str):
                member = interaction.guild.get_member(int(member)) or await bot.fetch_user(int(member))
            self.selected_user = member
            await interaction.response.edit_message(embed=self.create_embed())
        else:
            await interaction.response.send_message("No user selected.", ephemeral=True)

    # select menus for antinuke and automod choices (regular option selects)
    @discord.ui.select(placeholder="Pick antinuke features (multi)", min_values=0, max_values=10,
                       options=[discord.SelectOption(label=k) for k in DEFAULT_FEATURES["Antinuke"].keys()])
    async def ant_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_antinuke = select.values
        await interaction.response.defer()
        await interaction.followup.edit_message(interaction.message.id, embed=self.create_embed(), view=self, wait=False)

    @discord.ui.select(placeholder="Pick automod features (multi)", min_values=0, max_values=10,
                       options=[discord.SelectOption(label=k) for k in DEFAULT_FEATURES["Automod"].keys()])
    async def auto_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_automod = select.values
        await interaction.response.defer()
        await interaction.followup.edit_message(interaction.message.id, embed=self.create_embed(), view=self, wait=False)

    @discord.ui.button(label="Whitelist (Apply)", style=discord.ButtonStyle.success)
    async def apply_whitelist(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.selected_user:
            await interaction.response.send_message("Select a user first.", ephemeral=True)
            return
        g = str(self.guild.id)
        u = str(self.selected_user.id)
        if g not in whitelist:
            whitelist[g] = {}
        whitelist[g][u] = {
            "antinuke": self.selected_antinuke,
            "automod": self.selected_automod
        }
        await persist_state()
        await interaction.response.edit_message(embed=self.create_embed())
        await interaction.followup.send(f"✅ {self.selected_user.mention} whitelisted.", ephemeral=True)

# ---------- Slash Commands ----------
@bot.tree.command(name="enable_guard", description="Open guard UI (Antinuke + Automod). Admins only.")
async def enable_guard(interaction: discord.Interaction):
    # permission check
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only administrators can use this command.", ephemeral=True)
        return
    view = GuardView(interaction.guild)
    embed = view.create_embed()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="disable_guard", description="Disable all guard features and clear whitelist. Admins only.")
async def disable_guard(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only administrators can use this command.", ephemeral=True)
        return
    # reset features and whitelist for this guild
    for cat in features:
        for k in features[cat]:
            features[cat][k] = False
    g = str(interaction.guild.id)
    if g in whitelist:
        del whitelist[g]
    await persist_state()
    await interaction.response.send_message("Guard disabled and whitelist cleared.", ephemeral=True)

@bot.tree.command(name="about", description="About the Guard bot.")
async def about(interaction: discord.Interaction):
    await interaction.response.send_message("Guard Bot — Antinuke + Automod + Whitelisting. Built with discord.py.", ephemeral=True)

# ---------- Events: Antinuke handlers ----------
@bot.event
async def on_member_ban(guild, user):
    try:
        if not features.get("Antinuke", {}).get("Ban", False):
            return
        actor = await get_recent_audit_user(guild, AuditLogAction.ban, user.id)
        if actor and not is_whitelisted(guild.id, actor.id, "antinuke", "Ban"):
            # attempt unban
            await guild.unban(user, reason="Antinuke: unauthorized ban")
            # punish actor if desired (commented)
            # await actor.kick(reason="Antinuke: unauthorized ban")
            print(f"Antinuke: unbanned {user} after unauthorized ban by {actor}")
    except Exception as e:
        print("on_member_ban error:", e)

@bot.event
async def on_member_remove(member):
    try:
        if not features.get("Antinuke", {}).get("Kick", False):
            return
        actor = await get_recent_audit_user(member.guild, AuditLogAction.kick, member.id)
        if actor and not is_whitelisted(member.guild.id, actor.id, "antinuke", "Kick"):
            print(f"Antinuke: detected unauthorized kick of {member} by {actor}")
            # optionally punish actor
    except Exception as e:
        print("on_member_remove error:", e)

@bot.event
async def on_guild_channel_create(channel):
    try:
        if not features.get("Antinuke", {}).get("Channel Create", False):
            return
        actor = await get_recent_audit_user(channel.guild, AuditLogAction.channel_create, channel.id)
        if actor and not is_whitelisted(channel.guild.id, actor.id, "antinuke", "Channel Create"):
            await channel.delete(reason="Antinuke: unauthorized channel creation")
            print(f"Antinuke: deleted unauthorized channel {channel.name} by {actor}")
    except Exception as e:
        print("on_guild_channel_create error:", e)

@bot.event
async def on_guild_channel_delete(channel):
    try:
        if not features.get("Antinuke", {}).get("Channel Delete", False):
            return
        # Recreate minimal channel
        actor = await get_recent_audit_user(channel.guild, AuditLogAction.channel_delete, channel.id)
        if actor and not is_whitelisted(channel.guild.id, actor.id, "antinuke", "Channel Delete"):
            await channel.guild.create_text_channel(name=channel.name, reason="Antinuke: restore deleted channel")
            print(f"Antinuke: recreated channel {channel.name} after deletion by {actor}")
    except Exception as e:
        print("on_guild_channel_delete error:", e)

@bot.event
async def on_guild_channel_update(before, after):
    try:
        if not features.get("Antinuke", {}).get("Channel Update", False):
            return
        actor = await get_recent_audit_user(after.guild, AuditLogAction.channel_update, after.id)
        if actor and not is_whitelisted(after.guild.id, actor.id, "antinuke", "Channel Update"):
            # revert a few properties
            await after.edit(name=before.name, topic=before.topic, reason="Antinuke: revert channel update")
            print(f"Antinuke: reverted channel update on {after.name} by {actor}")
    except Exception as e:
        print("on_guild_channel_update error:", e)

@bot.event
async def on_guild_role_create(role):
    try:
        if not features.get("Antinuke", {}).get("Role Create", False):
            return
        actor = await get_recent_audit_user(role.guild, AuditLogAction.role_create, role.id)
        if actor and not is_whitelisted(role.guild.id, actor.id, "antinuke", "Role Create"):
            await role.delete(reason="Antinuke: unauthorized role creation")
            print(f"Antinuke: deleted role {role.name} by {actor}")
    except Exception as e:
        print("on_guild_role_create error:", e)

@bot.event
async def on_guild_role_delete(role):
    try:
        if not features.get("Antinuke", {}).get("Role Delete", False):
            return
        actor = await get_recent_audit_user(role.guild, AuditLogAction.role_delete, role.id)
        if actor and not is_whitelisted(role.guild.id, actor.id, "antinuke", "Role Delete"):
            print(f"Antinuke: role {role.name} was deleted by {actor} (no auto-restore implemented)")
    except Exception as e:
        print("on_guild_role_delete error:", e)

@bot.event
async def on_guild_role_update(before, after):
    try:
        if not features.get("Antinuke", {}).get("Role Update", False):
            return
        actor = await get_recent_audit_user(after.guild, AuditLogAction.role_update, after.id)
        if actor and not is_whitelisted(after.guild.id, actor.id, "antinuke", "Role Update"):
            # minimal revert (name)
            await after.edit(name=before.name, reason="Antinuke: revert role update")
            print(f"Antinuke: reverted role update on {after.name} by {actor}")
    except Exception as e:
        print("on_guild_role_update error:", e)

# ---------- Automod ----------
@bot.event
async def on_message(message):
    # run through automod checks
    if message.author.bot:
        return

    g = message.guild
    if not g:
        return

    # BAD WORDS
    if features.get("Automod", {}).get("Bad Words Filter", False) and not is_whitelisted(g.id, message.author.id, "automod", "Bad Words Filter"):
        content = (message.content or "").lower()
        if any(w.lower() in content for w in BAD_WORDS):
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention}, that word is not allowed!", delete_after=5)
                return
            except Exception:
                pass

    # LINKS
    if features.get("Automod", {}).get("Link Filter", False) and not is_whitelisted(g.id, message.author.id, "automod", "Link Filter"):
        content = (message.content or "").lower()
        if "http://" in content or "https://" in content or ".com" in content or ".gg/" in content:
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention}, links are not allowed!", delete_after=5)
                return
            except Exception:
                pass

    # INVITES
    if features.get("Automod", {}).get("Invite Filter", False) and not is_whitelisted(g.id, message.author.id, "automod", "Invite Filter"):
        content = (message.content or "").lower()
        if "discord.gg/" in content or "discord.com/invite/" in content:
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention}, server invites are not allowed!", delete_after=5)
                return
            except Exception:
                pass

    # CAPS (simple heuristic)
    if features.get("Automod", {}).get("Caps Filter", False) and not is_whitelisted(g.id, message.author.id, "automod", "Caps Filter"):
        content = message.content or ""
        if len(content) >= 8:
            letters = sum(1 for c in content if c.isalpha())
            upper = sum(1 for c in content if c.isupper())
            if letters > 0 and upper / letters > 0.7:
                try:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention}, please do not use excessive caps.", delete_after=5)
                    return
                except Exception:
                    pass

    # MENTION SPAM
    if features.get("Automod", {}).get("Mention Spam Filter", False) and not is_whitelisted(g.id, message.author.id, "automod", "Mention Spam Filter"):
        if len(message.mentions) > 5:
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention}, too many mentions!", delete_after=5)
                return
            except Exception:
                pass

    # IMAGE FILTER (attachments)
    if features.get("Automod", {}).get("Image Filter", False) and not is_whitelisted(g.id, message.author.id, "automod", "Image Filter"):
        if message.attachments:
            # naive: block if any attachment is an image
            for a in message.attachments:
                if a.content_type and a.content_type.startswith("image/"):
                    try:
                        await message.delete()
                        await message.channel.send(f"{message.author.mention}, images are not allowed in this channel.", delete_after=5)
                        return
                    except Exception:
                        pass

    # allow other commands (commands extension)
    await bot.process_commands(message)

# ---------- Ready ----------
@bot.event
async def on_ready():
    print(f"{bot.user} ready — guilds: {len(bot.guilds)}")
    bot.add_view(GuardView(next(iter(bot.guilds)) if bot.guilds else None))
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} app commands")
    except Exception as e:
        print("Failed to sync commands:", e)

# ---------- Run ----------
if __name__ == "__main__":
    bot.run(TOKEN)
