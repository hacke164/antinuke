# bot.py
import os
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")  # set this in Render environment variables

if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set")

# Replace with your constants (update LOG_CHANNEL_ID if you want)
WELCOME_ROLE_ID = 1412416423652757556  # auto-role to give new members
LOG_CHANNEL_ID = None  # set to integer ID if you want a fixed log channel, or leave None to find by name

# Custom emoji IDs (replace with IDs from your server if different)
EMOJI_IDS = {
    "buy": 1414542537938698271,
    "tick": 1414542503721570345,
    "welcome": 1414542454056685631
}

# ---------------- INTENTS & BOT ----------------
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True

class SecurityBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, application_id=None)
        # in-memory stores (consider persisting to DB later)
        self.anti_nuke_enabled: dict[int, bool] = {}
        self.automod_enabled: dict[int, bool] = {}
        self.whitelist: dict[int, list[int]] = {}
        self.user_message_cache: dict[tuple[int,int], list[float]] = {}  # (guild_id,user_id) -> timestamps
        self.ticket_category_name = "Tickets"
        # mapping ticket channel id -> owner id
        self.open_tickets: dict[int, int] = {}

    async def setup_hook(self):
        # sync commands on startup
        await self.tree.sync()

bot = SecurityBot()

# ---------------- HELPERS ----------------
def is_admin() -> app_commands.check:
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You must have Administrator permissions.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

def get_custom_emoji_str(guild: discord.Guild, name: str) -> str:
    eid = EMOJI_IDS.get(name)
    if not eid:
        return ""
    emoji = guild.get_emoji(eid)
    if emoji:
        return str(emoji)
    # fallback to raw form (works if emoji is in a server the bot can access)
    return f"<:emoji_{name}:{eid}>"

async def send_log(guild: discord.Guild, embed: discord.Embed):
    # priority: LOG_CHANNEL_ID if set -> channel named "mod-logs" or "bot-logs" -> first channel bot can send in
    channel = None
    if LOG_CHANNEL_ID:
        channel = guild.get_channel(LOG_CHANNEL_ID) or bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages and ("mod" in ch.name.lower() or "log" in ch.name.lower() or "bot" in ch.name.lower()):
                channel = ch
                break
    if not channel:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                channel = ch
                break
    if channel:
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

# ---------------- WELCOME & AUTO-ROLE ----------------
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    # give role
    role = guild.get_role(WELCOME_ROLE_ID)
    if role:
        try:
            await member.add_roles(role, reason="Auto role assignment")
        except Exception:
            pass

    # emojis
    emoji_buy = get_custom_emoji_str(guild, "buy")
    emoji_tick = get_custom_emoji_str(guild, "tick")
    emoji_welcome = get_custom_emoji_str(guild, "welcome")

    # public welcome embed (system channel preferred)
    embed = discord.Embed(
        title=f"{emoji_welcome} Welcome to {guild.name}!",
        description=(f"{emoji_tick} {member.mention} — you have been assigned the starter role.\n\n"
                     f"Explore the server and have fun!\n\n"
                     f"{emoji_buy} DM **@exhaust_xx** to buy premium access."),
        color=discord.Color.green()
    )
    channel = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
    if channel:
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    # DM the user
    try:
        dm_embed = discord.Embed(
            title=f"{emoji_welcome} Welcome!",
            description=(f"Hey {member.name}, welcome to **{guild.name}**!\n\n"
                         f"{emoji_tick} You've received your starter role.\n"
                         f"{emoji_buy} DM **@exhaust_xx** to purchase premium features."),
            color=discord.Color.blue()
        )
        await member.send(embed=dm_embed)
    except Exception:
        pass

# ---------------- ANTI-NUKE COMMANDS ----------------
@bot.tree.command(name="antinuke", description="Toggle or check anti-nuke protection")
@is_admin()
async def antinuke(interaction: discord.Interaction, action: Optional[str] = "status"):
    guild_id = interaction.guild.id
    if action.lower() == "toggle":
        current = bot.anti_nuke_enabled.get(guild_id, False)
        bot.anti_nuke_enabled[guild_id] = not current
        status_text = "✅ Enabled" if not current else "❌ Disabled"
        embed = discord.Embed(title=f"Anti-Nuke | {interaction.guild.name}",
                              description=f"Anti-Nuke has been **{status_text}**",
                              color=discord.Color.red())
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)
    else:  # status
        status_text = "✅ Enabled" if bot.anti_nuke_enabled.get(guild_id, False) else "❌ Disabled"
        embed = discord.Embed(title=f"Anti-Nuke | {interaction.guild.name}",
                              description=f"Current Status: {status_text}",
                              color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

# ---------------- AUTOMOD COMMANDS ----------------
@bot.tree.command(name="automod", description="Toggle or check AutoMod")
@is_admin()
async def automod(interaction: discord.Interaction, action: Optional[str] = "status"):
    guild_id = interaction.guild.id
    if action.lower() == "toggle":
        current = bot.automod_enabled.get(guild_id, False)
        bot.automod_enabled[guild_id] = not current
        status_text = "✅ Enabled" if not current else "❌ Disabled"
        embed = discord.Embed(title=f"AutoMod | {interaction.guild.name}",
                              description=f"AutoMod has been **{status_text}**",
                              color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)
    else:
        status_text = "✅ Enabled" if bot.automod_enabled.get(guild_id, False) else "❌ Disabled"
        embed = discord.Embed(title=f"AutoMod | {interaction.guild.name}",
                              description=f"Current Status: {status_text}",
                              color=discord.Color.purple())
        await interaction.response.send_message(embed=embed)

# ---------------- WHITELIST COMMANDS ----------------
@bot.tree.command(name="whitelist", description="Manage server whitelist")
@is_admin()
async def whitelist(interaction: discord.Interaction, action: str, member: Optional[discord.Member] = None):
    guild_id = interaction.guild.id
    bot.whitelist.setdefault(guild_id, [])

    if action.lower() == "add" and member:
        if member.id not in bot.whitelist[guild_id]:
            bot.whitelist[guild_id].append(member.id)
        e = discord.Embed(title=f"Whitelist | {interaction.guild.name}",
                          description=f"✅ {member.mention} added to whitelist.",
                          color=discord.Color.green())
        await interaction.response.send_message(embed=e)
        await send_log(interaction.guild, e)
        return

    if action.lower() == "remove" and member:
        if member.id in bot.whitelist[guild_id]:
            bot.whitelist[guild_id].remove(member.id)
            e = discord.Embed(title=f"Whitelist | {interaction.guild.name}",
                              description=f"❌ {member.mention} removed from whitelist.",
                              color=discord.Color.red())
            await interaction.response.send_message(embed=e)
            await send_log(interaction.guild, e)
            return
        else:
            await interaction.response.send_message("User not in whitelist.", ephemeral=True)
            return

    if action.lower() == "list":
        members = bot.whitelist.get(guild_id, [])
        desc = "\n".join(f"<@{m}>" for m in members) if members else "No users whitelisted."
        e = discord.Embed(title=f"Whitelist | {interaction.guild.name}", description=desc, color=discord.Color.blue())
        await interaction.response.send_message(embed=e)
        return

    await interaction.response.send_message("Invalid usage. Example: `/whitelist add @user`", ephemeral=True)

# ---------------- EMBED GENERATOR ----------------
@bot.tree.command(name="embed", description="Generate a custom embed (admin only)")
@is_admin()
async def embed_create(interaction: discord.Interaction, title: str, description: str, color: Optional[str] = "#3498db"):
    try:
        color_val = int(color.replace("#", ""), 16)
    except Exception:
        color_val = 0x3498db
    e = discord.Embed(title=title, description=description, color=color_val)
    e.set_footer(text=f"Requested by {interaction.user}")
    await interaction.response.send_message(embed=e)

# ---------------- AUTOMOD DETECTION (spam, mass mention, links, profanity) ----------------
BAD_WORDS = {"badword1", "badword2"}

@bot.event
async def on_message(message: discord.Message):
    # ignore bots and DMs
    if message.author.bot or message.guild is None:
        return

    guild_id = message.guild.id

    # whitelisted users skip automod
    if guild_id in bot.whitelist and message.author.id in bot.whitelist[guild_id]:
        await bot.process_commands(message)
        return

    # only run automod when enabled for guild
    if bot.automod_enabled.get(guild_id, False):
        # spam detection: 5 messages in 5 seconds
        key = (guild_id, message.author.id)
        ts_list = bot.user_message_cache.get(key, [])
        ts_list.append(message.created_at.timestamp())
        # keep last 6 timestamps
        ts_list = ts_list[-6:]
        bot.user_message_cache[key] = ts_list
        if len(ts_list) >= 5:
            if ts_list[-1] - ts_list[-5] < 5:  # 5 messages in <5 seconds
                try:
                    await message.delete()
                except Exception:
                    pass
                embed = discord.Embed(title="🚨 AutoMod — Spam Detected",
                                      description=f"{message.author.mention} was spamming messages and a message was removed.",
                                      color=discord.Color.orange())
                await send_log(message.guild, embed)
                # optionally notify channel
                try:
                    await message.channel.send(f"⚠️ {message.author.mention}, please avoid spamming.", delete_after=6)
                except Exception:
                    pass
                await bot.process_commands(message)
                return

        # mass mentions
        if len(message.mentions) >= 5 or message.mention_everyone:
            try:
                await message.delete()
            except Exception:
                pass
            embed = discord.Embed(title="🚨 AutoMod — Mass Mention",
                                  description=f"{message.author.mention} attempted to mass-mention users. Message removed.",
                                  color=discord.Color.orange())
            await send_log(message.guild, embed)
            try:
                await message.channel.send(f"⚠️ {message.author.mention}, mass mentions are not allowed.", delete_after=6)
            except Exception:
                pass
            await bot.process_commands(message)
            return

        # link blocking
        if "http://" in message.content or "https://" in message.content or "discord.gg/" in message.content:
            try:
                await message.delete()
            except Exception:
                pass
            embed = discord.Embed(title="🚨 AutoMod — Link Blocked",
                                  description=f"{message.author.mention} posted a link. Message removed.",
                                  color=discord.Color.orange())
            await send_log(message.guild, embed)
            try:
                await message.channel.send(f"⚠️ {message.author.mention}, posting links is not allowed here.", delete_after=6)
            except Exception:
                pass
            await bot.process_commands(message)
            return

        # profanity
        lower = message.content.lower()
        if any(bad in lower for bad in BAD_WORDS):
            try:
                await message.delete()
            except Exception:
                pass
            embed = discord.Embed(title="🚨 AutoMod — Profanity",
                                  description=f"{message.author.mention} used protected language. Message removed.",
                                  color=discord.Color.orange())
            await send_log(message.guild, embed)
            try:
                await message.channel.send(f"⚠️ {message.author.mention}, please avoid profanity.", delete_after=6)
            except Exception:
                pass
            await bot.process_commands(message)
            return

    # process commands at the end
    await bot.process_commands(message)

# ---------------- TICKET SYSTEM (interactive embed + buttons) ----------------
class TicketCreateView(discord.ui.View):
    def __init__(self, *, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="🎫 Create Ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        author = interaction.user

        # Create or find "Tickets" category
        category = discord.utils.get(guild.categories, name=bot.ticket_category_name)
        if not category:
            try:
                category = await guild.create_category(bot.ticket_category_name)
            except Exception:
                category = None

        # Build permissions: hide from @everyone, show to author and admins
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        # add admin roles (roles with administrator) to overwrites
        for role in guild.roles:
            if role.permissions.administrator:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)

        # create the channel
        chan_name = f"ticket-{author.name}-{author.discriminator}"
        try:
            channel = await guild.create_text_channel(chan_name, category=category, overwrites=overwrites, reason="Ticket created")
        except Exception:
            await interaction.response.send_message("⚠️ Failed to create ticket channel. Please contact staff.", ephemeral=True)
            return

        # store owner
        bot.open_tickets[channel.id] = author.id

        # ticket open embed
        emoji_tick = get_custom_emoji_str(guild, "tick")
        embed = discord.Embed(title="🎫 Ticket Created",
                              description=(f"{emoji_tick} {author.mention}, your ticket has been opened. "
                                           "Please describe your issue and a staff member will assist you shortly."),
                              color=discord.Color.blurple())
        # Close button view (for staff)
        close_view = TicketCloseView(owner_id=author.id)
        try:
            await channel.send(content=f"{author.mention}", embed=embed, view=close_view)
        except Exception:
            await channel.send(content=f"{author.mention}", embed=embed)

        # ack the user
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)
        # log creation
        log_embed = discord.Embed(title="🟢 Ticket Opened",
                                  description=f"Ticket {channel.mention} opened by {author.mention}",
                                  color=discord.Color.green())
        await send_log(guild, log_embed)

class TicketCloseView(discord.ui.View):
    def __init__(self, owner_id: int, *, timeout: Optional[float]=None):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # only admins or ticket owner can close
        is_admin_user = interaction.user.guild_permissions.administrator
        chan = interaction.channel
        owner_id = bot.open_tickets.get(chan.id)
        if not (is_admin_user or interaction.user.id == owner_id):
            await interaction.response.send_message("❌ Only staff or ticket owner may close this ticket.", ephemeral=True)
            return

        # archive (delete) channel or rename & lock
        try:
            await chan.edit(name=f"closed-{chan.name}", topic=f"Closed by {interaction.user}", reason="Ticket closed")
            # revoke member view by setting everyone no view
            await chan.set_permissions(interaction.guild.default_role, view_channel=False)
            # optionally remove ticket mapping
            bot.open_tickets.pop(chan.id, None)
            await chan.send(embed=discord.Embed(title="🔒 Ticket Closed", description=f"Closed by {interaction.user.mention}", color=discord.Color.red()))
            await send_log(interaction.guild, discord.Embed

bot.run(TOKEN)
