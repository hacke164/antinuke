import discord
from discord.ext import commands
from discord import app_commands
import os

# ---------------- CONFIG ----------------
TOKEN = os.environ.get("TOKEN")  # Replace with your token if not using env vars
LOG_CHANNEL_NAME = "bot-logs"    # Channel name for logs

# ---------------- INTENTS ----------------
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True
intents.message_content = True

# ---------------- BOT ----------------
bot = commands.Bot(command_prefix="!", intents=intents)

# Store feature toggle states per guild
toggles = {}

def is_admin():
    """Check if user has Administrator permission."""
    def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        else:
            raise app_commands.CheckFailure("You must be an Administrator to use this command.")
    return app_commands.check(predicate)

# ------------- HELPER EMBED -------------
def feature_embed(guild: discord.Guild, feature: str, state: bool, details: list = None):
    embed = discord.Embed(
        title=f"{guild.name} | {feature} Settings",
        color=discord.Color.red() if not state else discord.Color.green()
    )
    embed.add_field(name="Status", value="✅ Enabled" if state else "❌ Disabled", inline=False)

    if details:
        for name, value in details:
            embed.add_field(name=name, value=value, inline=True)

    embed.set_footer(text=f"Toggled in {guild.name}")
    return embed

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔗 Synced {len(synced)} commands")
    except Exception as e:
        print(f"❌ Sync error: {e}")

# ---------------- FEATURES ----------------

# === AntiNuke Toggle ===
@bot.tree.command(name="antinuke", description="Toggle AntiNuke protection")
@is_admin()
async def antinuke(interaction: discord.Interaction, toggle: str):
    guild_id = interaction.guild.id
    toggles.setdefault(guild_id, {})
    toggles[guild_id]["antinuke"] = toggle.lower() == "on"

    details = [
        ("Ban Protection", "✅ Enabled" if toggle.lower() == "on" else "❌ Disabled"),
        ("Channel Delete Protection", "✅ Enabled" if toggle.lower() == "on" else "❌ Disabled"),
        ("Webhook Spam Protection", "✅ Enabled" if toggle.lower() == "on" else "❌ Disabled"),
    ]
    embed = feature_embed(interaction.guild, "AntiNuke", toggles[guild_id]["antinuke"], details)
    await interaction.response.send_message(embed=embed)

# === Whitelist Management ===
@bot.tree.command(name="whitelist", description="Whitelist a user from protections")
@is_admin()
async def whitelist(interaction: discord.Interaction, member: discord.Member):
    guild_id = interaction.guild.id
    toggles.setdefault(guild_id, {})
    whitelisted = toggles[guild_id].setdefault("whitelist", set())
    whitelisted.add(member.id)

    embed = feature_embed(
        interaction.guild,
        "Whitelist",
        True,
        [("Whitelisted User", f"{member.mention}")]
    )
    await interaction.response.send_message(embed=embed)

# === AutoMod ===
BANNED_WORDS = ["badword1", "badword2", "spamlink.com"]  # Add your list

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    guild_id = message.guild.id if message.guild else None
    if not guild_id or not toggles.get(guild_id, {}).get("automod", False):
        return

    # Check for violations
    if any(bad in message.content.lower() for bad in BANNED_WORDS):
        try:
            await message.delete()
        except:
            pass

        # Send warning in channel
        await message.channel.send(
            f"⚠️ {message.author.mention}, your message violated AutoMod rules and was removed."
        )

        # Log in bot-logs channel
        log_channel = discord.utils.get(message.guild.channels, name=LOG_CHANNEL_NAME)
        if log_channel:
            embed = discord.Embed(
                title="🚨 AutoMod Violation",
                description=f"**User:** {message.author.mention}\n**Message:** {message.content}",
                color=discord.Color.orange()
            )
            await log_channel.send(embed=embed)

# === Toggle AutoMod ===
@bot.tree.command(name="automod", description="Toggle AutoMod features")
@is_admin()
async def automod(interaction: discord.Interaction, toggle: str):
    guild_id = interaction.guild.id
    toggles.setdefault(guild_id, {})
    toggles[guild_id]["automod"] = toggle.lower() == "on"

    details = [
        ("Word Filter", "Active"),
        ("Spam Block", "Active"),
        ("Link Filter", "Active")
    ]
    embed = feature_embed(interaction.guild, "AutoMod", toggles[guild_id]["automod"], details)
    await interaction.response.send_message(embed=embed)

# ---------------- RUN ----------------
bot.run(TOKEN)
