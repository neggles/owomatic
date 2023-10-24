import logging
from pathlib import Path
from typing import Optional

from disnake import (
    ApplicationCommandInteraction,
    FFmpegPCMAudio,
    PCMVolumeTransformer,
    VoiceChannel,
    VoiceClient,
    opus,
)
from disnake.ext import commands
from disnake.ext.commands import Param

import logsnake
from cogs.snaketalk.settings import get_snaketalk_settings
from owomatic import LOG_FORMAT, LOGDIR_PATH
from owomatic.bot import Owomatic
from owomatic.settings import ChannelSettings

COG_UID = "snaketalk"

TRIGGER_EMOJI = "🔎"

# setup cog logger
logger = logsnake.setup_logger(
    level=logging.DEBUG,
    isRootLogger=False,
    name=__name__,
    formatter=logsnake.LogFormatter(fmt=LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"),
    logfile=LOGDIR_PATH.joinpath(f"{COG_UID}.log"),
    fileLoglevel=logging.DEBUG,
    maxBytes=2 * (2**20),
    backupCount=2,
)
logger.propagate = True


class SnakeTalk(commands.Cog, name=COG_UID):
    def __init__(self, bot) -> None:
        self.bot: Owomatic = bot
        self.config = get_snaketalk_settings()
        self.vc: VoiceClient = None

    async def cog_load(self):
        if not opus.is_loaded() and self.config.libname is not None:
            logger.info(f"Loading Opus library {self.config.libname}...")
            opus.load_opus(self.config.libname)
        logger.info(f"{COG_UID} initialized.")

    def cog_unload(self):
        if self.vc is not None and self.vc.is_connected():
            self.bot.loop.run_until_complete(self.vc.disconnect())

    @property
    def channel_settings(self) -> list[ChannelSettings]:
        return [channel for guild in self.config.guilds for channel in guild.channels]

    @property
    def enabled_channel_ids(self) -> list[int]:
        return [channel.id for channel in self.channel_settings if channel.enabled]

    @commands.slash_command(
        name="vc", description="Voice commands", guild_ids=get_snaketalk_settings().guilds.enabled_ids
    )
    async def vc_group(self, ctx: ApplicationCommandInteraction):
        if ctx.guild.id not in self.config.guilds.enabled_ids:
            raise ValueError(f"Guild '{ctx.guild.name}' is not enabled for voice!")
        pass

    @vc_group.sub_command(name="join", description="Join a voice channel")
    async def vc_join(self, ctx: ApplicationCommandInteraction, *, channel: Optional[VoiceChannel] = None):
        if channel is None and ctx.author.voice.channel is not None:
            channel = ctx.author.voice.channel
        if not isinstance(channel, VoiceChannel):
            raise ValueError(f"Channel '{getattr(channel, 'name', 'Unknown')}' is not a voice channel!")
        await ctx.response.defer(ephemeral=True)
        if self.vc is not None and self.vc.is_connected():
            logger.info(f"Moving voice client to {channel}")
            await self.vc.move_to(channel=channel)
        else:
            logger.info(f"Connecting to voice channel {channel}")
            self.vc = await channel.connect()
        await ctx.send(f"Joined voice channel '{channel.name}' ({channel.id})", ephemeral=True)

    @vc_group.sub_command(name="leave", description="Leave all voice channels")
    async def vc_leave(self, ctx: ApplicationCommandInteraction):
        if self.vc is None:
            raise ValueError("Not connected to a voice channel!")
        await ctx.response.defer(ephemeral=True)
        logger.info("Disconnecting voice client")
        await self.vc.disconnect()
        self.vc = None
        await ctx.send("Left all voice channels.", ephemeral=True)

    @vc_group.sub_command(name="play", description="Play something")
    async def vc_play(
        self,
        ctx: ApplicationCommandInteraction,
        filepath: str,
        volume: Optional[int] = Param(None, ge=0, le=100),
    ):
        fpath: Path = Path(filepath).resolve()
        if not fpath.exists():
            raise FileNotFoundError(f"Path {filepath} does not exist!")
        # make sure we in channel
        await self.ensure_voice(ctx)
        # do a log
        logger.info(f"Playing file {fpath} in channel {self.vc.channel}")
        # make the source
        source = PCMVolumeTransformer(FFmpegPCMAudio(fpath))
        # set volume
        source.volume = (volume / 100) if volume is not None else (self.config.volume / 100)
        # play
        self.vc.play(source, after=lambda e: print(f"Player error: {e}") if e else None)
        return await ctx.send(f"Now playing: {filepath}", ephemeral=True)

    @vc_group.sub_command(name="volume", description="Set volume level")
    async def vc_volume(self, ctx: ApplicationCommandInteraction, volume: int = Param(ge=0, le=100)):
        if self.vc is not None and self.vc.source is not None:
            self.vc.source.volume = volume / 100
            logmsg = f"Set source volume to {round(volume)} %"
        else:
            logmsg = "No audio source is currently playing."
        logger.info(logmsg)
        return await ctx.send(logmsg, ephemeral=True)

    async def ensure_voice(self, ctx: ApplicationCommandInteraction):
        if self.vc is None:
            if ctx.author.voice:
                self.vc = await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.", ephemeral=True)
                raise commands.CommandError("Author not connected to a voice channel.")
        elif self.vc.is_playing():
            self.vc.stop()


def setup(bot):
    bot.add_cog(SnakeTalk(bot))
