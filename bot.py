import os
import discord
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("TOKEN")  # Render environment variable

# ----- CONFIG -----
WELCOME_ROLE_ID = 1412416423652757556  # Auto role
LOG_CHANNEL_ID = 1414542537938698271   # Replace with your mod-log channel ID

# Custom emojis (from your screenshot)
EMOJI_BUY = "<:buy:1414542537938698271>"
EMOJI_TICK = "<:tick:1414542503721570345>"
EMOJI_WELCOME = "<:welcome:1414542454056685631>"

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True

class SecurityBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.anti_nuke_enabled = {}
        self.automod_enabled = {}
        self.whitelist = {}
        self.user_message_cache = {}  # For spam detection

    async def setup_hook(self):
        await self.tree.sync()

bot = SecurityBot()

# ---------------- ADMIN CHECK ----------------
def is_admin():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("❌ You need Administrator rights to use this command.", ephemeral=True)
        return False
    return app_commands.check(predicate)

# ---------------- WELCOME MESSAGE ----------------
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    role = guild.get_role(WELCOME_ROLE_ID)
    if role:
        await member.add_roles(role, reason="Auto role assignment")

    # Public welcome embed
    embed = discord.Embed(
        title=f"{EMOJI_WELCOME} Welcome to {guild.name}!",
        description=f"{EMOJI_TICK} {member.mention}, you have been given the default role.\n\n"
                    f"Chat freely and explore the server!\n"
                    f"{EMOJI_BUY} DM **@exhaust_xx** to buy premium access.",
        color=discord.Color.green()
    )
    channel = guild.system_channel or guild.text_channels[0]
    if channel:
        await channel.send(embed=embed)

    # DM the new user
    try:
        dm_embed = discord.Embed(
            title=f"{EMOJI_WELCOME} Welcome to {guild.name}!",
            description=f"Hey {member.mention}, welcome aboard!\n\n"
                        f"{EMOJI_TICK} You’ve been assigned your starter role.\n"
                        f"{EMOJI_BUY} To purchase special access, DM **@exhaust_xx**.",
            color=discord.Color.blue()
        )
        await member.send(embed=dm_embed)
    except Exception:
        pass

# ---------------- ANTINUKE ----------------
@bot.tree.command(name="antinuke", description="Toggle or check anti-nuke")
@is_admin()
async def antinuke(interaction: discord.Interaction, action: str):
    guild_id = interaction.guild.id
    if action.lower() == "toggle":
        current = bot.anti_nuke_enabled.get(guild_id, False)
        bot.anti_nuke_enabled[guild_id] = not current
        status = "✅ Enabled" if not current else "❌ Disabled"
        embed = discord.Embed(title=f"Anti-Nuke | {interaction.guild.name}",
                              description=f"Anti-Nuke has been **{status}**",
                              color=discord.Color.red())
        await interaction.response.send_message(embed=embed)

        log = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log:
            await log.send(f"🔐 Anti-Nuke {status} by {interaction.user.mention}")

    elif action.lower() == "status":
        status = "✅ Enabled" if bot.anti_nuke_enabled.get(guild_id, False) else "❌ Disabled"
        embed = discord.Embed(title=f"Anti-Nuke | {interaction.guild.name}",
                              description=f"Current Status: {status}",
                              color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

# ---------------- AUTOMOD ----------------
@bot.tree.command(name="automod", description="Toggle or check automod")
@is_admin()
async def automod(interaction: discord.Interaction, action: str):
    guild_id = interaction.guild.id
    if action.lower() == "toggle":
        current = bot.automod_enabled.get(guild_id, False)
        bot.automod_enabled[guild_id] = not current
        status = "✅ Enabled" if not current else "❌ Disabled"
        embed = discord.Embed(title=f"AutoMod | {interaction.guild.name}",
                              description=f"AutoMod has been **{status}**",
                              color=discord.Color.green())
        await interaction.response.send_message(embed=embed)

        log = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log:
            await log.send(f"⚔️ AutoMod {status} by {interaction.user.mention}")

    elif action.lower() == "status":
        status = "✅ Enabled" if bot.automod_enabled.get(guild_id, False) else "❌ Disabled"
        embed = discord.Embed(title=f"AutoMod | {interaction.guild.name}",
                              description=f"Current Status: {status}",
                              color=discord.Color.purple())
        await interaction.response.send_message(embed=embed)

# ---------------- AUTOMOD DETECTION ----------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    guild_id = message.guild.id if message.guild else None

    if guild_id and bot.automod_enabled.get(guild_id, False):
        # Spam detection
        user_id = message.author.id
        if user_id not in bot.user_message_cache:
            bot.user_message_cache[user_id] = []
        bot.user_message_cache[user_id].append(message.created_at.timestamp())

        # Keep only last 5 messages
        bot.user_message_cache[user_id] = bot.user_message_cache[user_id][-5:]

        if len(bot.user_message_cache[user_id]) >= 5:
            time_diff = bot.user_message_cache[user_id][-1] - bot.user_message_cache[user_id][0]
            if time_diff < 5:  # 5 messages in 5 seconds
                await message.delete()
                log = message.guild.get_channel(LOG_CHANNEL_ID)
                if log:
                    await log.send(f"🚨 Spam detected: {message.author.mention} was sending messages too quickly.")

        # Mass mention detection
        if len(message.mentions) >= 5 or message.mention_everyone:
            await message.delete()
            log = message.guild.get_channel(LOG_CHANNEL_ID)
            if log:
                await log.send(f"🚨 Mass mention detected: {message.author.mention} tried to ping many users.")

    await bot.process_commands(message)

# ---------------- WHITELIST ----------------
@bot.tree.command(name="whitelist", description="Manage whitelist")
@is_admin()
async def whitelist(interaction: discord.Interaction, action: str, member: discord.Member = None):
    guild_id = interaction.guild.id
    if guild_id not in bot.whitelist:
        bot.whitelist[guild_id] = []

    if action.lower() == "add" and member:
        bot.whitelist[guild_id].append(member.id)
        embed = discord.Embed(title=f"Whitelist | {interaction.guild.name}",
                              description=f"✅ {member.mention} has been **whitelisted**.",
                              color=discord.Color.green())
        await interaction.response.send_message(embed=embed)

    elif action.lower() == "remove" and member:
        if member.id in bot.whitelist[guild_id]:
            bot.whitelist[guild_id].remove(member.id)
            embed = discord.Embed(title=f"Whitelist | {interaction.guild.name}",
                                  description=f"❌ {member.mention} has been **removed** from whitelist.",
                                  color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("User not in whitelist.", ephemeral=True)

    elif action.lower() == "list":
        members = [f"<@{m}>" for m in bot.whitelist[guild_id]]
        desc = "\n".join(members) if members else "No users whitelisted."
        embed = discord.Embed(title=f"Whitelist | {interaction.guild.name}",
                              description=desc,
                              color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Invalid usage. Try `/whitelist add @user`")

# ---------------- EMBED CREATOR ----------------
@bot.tree.command(name="embed", description="Create a custom embed")
@is_admin()
async def embed_create(interaction: discord.Interaction, title: str, description: str, color: str = "#3498db"):
    try:
        color_val = int(color.replace("#", ""), 16)
    except ValueError:
        color_val = 0x3498db
    embed = discord.Embed(title=title, description=description, color=color_val)
    embed.set_footer(text=f"Requested by {interaction.user}")
    await interaction.response.send_message(embed=embed)

# ---------------- RUN ----------------
bot.run(TOKEN)
