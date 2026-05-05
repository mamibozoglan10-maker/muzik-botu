import os
import asyncio
import discord
from discord import app_commands
import yt_dlp

TOKEN = os.environ.get("DISCORD_TOKEN")

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "source_address": "0.0.0.0",
    "extract_flat": False,
    "skip_download": True,
    "youtube_include_dash_manifest": False,
    "youtube_include_hls_manifest": False,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)
queues = {}

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("url")
        self.thumbnail = data.get("thumbnail")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        if "entries" in data:
            data = data["entries"][0]
        return cls(discord.FFmpegPCMAudio(data["url"], **FFMPEG_OPTIONS), data=data)

async def play_next(interaction):
    queue = get_queue(interaction.guild.id)
    if queue:
        source = queue.pop(0)
        interaction.guild.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop))
        embed = discord.Embed(title="Şimdi Çalıyor", description=f"**{source.title}**", color=discord.Color.green())
        if source.thumbnail:
            embed.set_thumbnail(url=source.thumbnail)
        await interaction.channel.send(embed=embed)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"{bot.user} olarak giriş yapıldı!")

@tree.command(name="cal", description="Şarkı çalar")
@app_commands.describe(sarki="Şarkı adı veya YouTube linki")
async def play(interaction: discord.Interaction, sarki: str):
    if not interaction.user.voice:
        await interaction.response.send_message("Ses kanalına girin!", ephemeral=True)
        return
    await interaction.response.defer()
    vc = interaction.guild.voice_client
    if vc is None:
        vc = await interaction.user.voice.channel.connect()
    elif vc.channel != interaction.user.voice.channel:
        await vc.move_to(interaction.user.voice.channel)
    if not sarki.startswith("http"):
        sarki = f"{sarki} şarkı"
    try:
        source = await YTDLSource.from_url(sarki, loop=bot.loop)
    except Exception as e:
        await interaction.followup.send(f"Hata: {e}")
        return
    queue = get_queue(interaction.guild.id)
    if vc.is_playing() or vc.is_paused():
        queue.append(source)
        await interaction.followup.send(embed=discord.Embed(title="Sıraya Eklendi", description=f"**{source.title}**", color=discord.Color.blue()))
    else:
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop))
        embed = discord.Embed(title="Şimdi Çalıyor", description=f"**{source.title}**", color=discord.Color.green())
        if source.thumbnail:
            embed.set_thumbnail(url=source.thumbnail)
        await interaction.followup.send(embed=embed)

@tree.command(name="dur", description="Duraklatır")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("Duraklatıldı.")
    else:
        await interaction.response.send_message("Çalan bir şey yok.", ephemeral=True)

@tree.command(name="devam", description="Devam ettirir")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("Devam ediyor.")
    else:
        await interaction.response.send_message("Duraklatılmış bir şey yok.", ephemeral=True)

@tree.command(name="atla", description="Sonraki şarkıya geçer")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message("Atlandı.")
    else:
        await interaction.response.send_message("Çalan bir şey yok.", ephemeral=True)

@tree.command(name="durdur", description="Durdurur ve kanaldan ayrılır")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        queues[interaction.guild.id] = []
        vc.stop()
        await vc.disconnect()
        await interaction.response.send_message("Durduruldu.")
    else:
        await interaction.response.send_message("Bot kanalda değil.", ephemeral=True)

@tree.command(name="sira", description="Sırayı gösterir")
async def queue_list(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)
    if not queue:
        await interaction.response.send_message("Sıra boş.", ephemeral=True)
        return
    embed = discord.Embed(title="Müzik Sırası", color=discord.Color.purple())
    for i, s in enumerate(queue, 1):
        embed.add_field(name=f"{i}.", value=s.title, inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="ses", description="Ses seviyesi (0-100)")
@app_commands.describe(seviye="Ses seviyesi")
async def volume(interaction: discord.Interaction, seviye: int):
    vc = interaction.guild.voice_client
    if not vc:
        await interaction.response.send_message("Bot kanalda değil.", ephemeral=True)
        return
    if hasattr(vc.source, "volume"):
        vc.source.volume = max(0, min(100, seviye)) / 100
    await interaction.response.send_message(f"Ses: {seviye}%")

@tree.command(name="yardim", description="Komutları listeler")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="Komutlar", color=discord.Color.blurple())
    embed.add_field(name="/cal <şarkı>", value="Şarkı çalar", inline=False)
    embed.add_field(name="/dur", value="Duraklatır", inline=False)
    embed.add_field(name="/devam", value="Devam ettirir", inline=False)
    embed.add_field(name="/atla", value="Sonraki şarkı", inline=False)
    embed.add_field(name="/durdur", value="Durdurur ve ayrılır", inline=False)
    embed.add_field(name="/sira", value="Sırayı gösterir", inline=False)
    embed.add_field(name="/ses <0-100>", value="Ses ayarlar", inline=False)
    await interaction.response.send_message(embed=embed)

if __name__ == "__main__":
    if not TOKEN:
        print("DISCORD_TOKEN eksik!")
    else:
        bot.run(TOKEN)
