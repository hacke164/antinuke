import os
import discord
from discord.ext import commands

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")  # set this in Render environment variables
os.environ["DISCORD_NO_VOICE"] = "true"


if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set")

# ---------------- INTENTS ----------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

# ---------------- BOT ----------------
bot = commands.Bot(command_prefix="!", intents=intents)


# ---------------- GUARD VIEW ----------------
class GuardView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.selected_user_id = None
        self.antinuke_enabled = False
        self.automod_enabled = False

    def create_embed(self, guild_name, guild_icon_url):
        embed = discord.Embed(
            title="🛡️ Server Protection Guard",
            description=f"Manage AntiNuke and AutoMod settings for **{guild_name}**",
            color=discord.Color.blurple()
        )
        if guild_icon_url:
            embed.set_thumbnail(url=guild_icon_url)

        embed.add_field(
            name="⚙️ AntiNuke",
            value=f"Status: {'🟢 Enabled' if self.antinuke_enabled else '🔴 Disabled'}",
            inline=True
        )
        embed.add_field(
            name="⚙️ AutoMod",
            value=f"Status: {'🟢 Enabled' if self.automod_enabled else '🔴 Disabled'}",
            inline=True
        )
        embed.add_field(
            name="👤 Selected User",
            value=f"<@{self.selected_user_id}>" if self.selected_user_id else "No user selected",
            inline=False
        )
        return embed

    # ---------- BUTTONS ----------
    @discord.ui.button(label="Toggle AntiNuke", style=discord.ButtonStyle.primary, row=0)
    async def toggle_antinuke(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.antinuke_enabled = not self.antinuke_enabled
        embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle AutoMod", style=discord.ButtonStyle.primary, row=0)
    async def toggle_automod(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.automod_enabled = not self.automod_enabled
        embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Whitelist User", style=discord.ButtonStyle.success, row=1)
    async def whitelist_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_user_id:
            await interaction.response.send_message(
                f"✅ <@{self.selected_user_id}> has been whitelisted from AntiNuke and AutoMod.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("⚠️ Please select a user first.", ephemeral=True)

    # ---------- SELECT MENUS ----------
    @discord.ui.select(
        placeholder="Select a user to whitelist...",
        row=2,
        select_type=discord.ComponentType.user_select
    )
    async def user_select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values:
            selected_user = select.values[0]
            self.selected_user_id = int(selected_user.id)
            embed = self.create_embed(interaction.guild.name, interaction.guild.icon.url if interaction.guild.icon else None)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("No user selected.", ephemeral=True)

    @discord.ui.select(
        placeholder="Select a role...",
        row=3,
        select_type=discord.ComponentType.role_select
    )
    async def role_select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values:
            role = select.values[0]
            await interaction.response.send_message(f"Selected role: {role.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("No role selected.", ephemeral=True)

    @discord.ui.select(
        placeholder="Select a channel...",
        row=4,
        select_type=discord.ComponentType.channel_select
    )
    async def channel_select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values:
            channel = select.values[0]
            await interaction.response.send_message(f"Selected channel: {channel.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("No channel selected.", ephemeral=True)


# ---------------- SLASH COMMANDS ----------------
@bot.tree.command(name="enable_guard", description="Enable server guard with AntiNuke + AutoMod settings.")
async def enable_guard(interaction: discord.Interaction):
    view = GuardView(bot)
    guild_icon_url = interaction.guild.icon.url if interaction.guild.icon else None
    embed = view.create_embed(interaction.guild.name, guild_icon_url)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="disable_guard", description="Disable the server guard.")
async def disable_guard(interaction: discord.Interaction):
    await interaction.response.send_message("🛑 Server Guard has been disabled.", ephemeral=True)


@bot.tree.command(name="about", description="About this bot.")
async def about(interaction: discord.Interaction):
    embed = discord.Embed(
        title="ℹ️ About This Bot",
        description="This is a multipurpose server protection bot with AntiNuke, AutoMod, and whitelisting.",
        color=discord.Color.green()
    )
    embed.set_footer(text="Developed with ❤️ using discord.py")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online and connected!")
    bot.add_view(GuardView(bot))
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")


# ---------------- RUN ----------------
bot.run(TOKEN)

