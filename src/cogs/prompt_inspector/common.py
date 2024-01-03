import json
import logging
from asyncio import gather
from collections import OrderedDict
from enum import Enum
from functools import lru_cache
from io import BytesIO, StringIO
from pathlib import Path
from typing import Optional

from disnake import (
    Attachment,
    Embed,
    File,
    Message,
    MessageCommandInteraction,
    RawReactionActionEvent,
)
from disnake.ext import commands
from PIL import Image

import logsnake
from cogs.prompt_inspector.settings import get_inspector_settings
from cogs.prompt_inspector.stealth import read_info_from_image_stealth
from cogs.prompt_inspector.ui import PromptView
from owomatic import LOG_FORMAT, LOGDIR_PATH
from owomatic.bot import Owomatic
from owomatic.settings import ChannelSettings

COG_UID = "prompt_inspector"

TRIGGER_EMOJI = "🔎"
IMAGE_EXTNS = [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".gif"]
MAX_FIELDS = 24
MAX_SCAN_BYTES = 80 * 2**20

# get parent package name for base logger name
log_name = ".".join(__name__.split(".")[:-1])

# setup cog logger
logger = logsnake.setup_logger(
    level=logging.DEBUG,
    isRootLogger=False,
    name=log_name,
    formatter=logsnake.LogFormatter(fmt=LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"),
    logfile=LOGDIR_PATH.joinpath(f"{COG_UID}.log"),
    fileLoglevel=logging.DEBUG,
    maxBytes=2 * (2**20),
    backupCount=2,
)
logger.propagate = True


class MetadataType(str, Enum):
    Automatic1111 = "Steps:"
    ComfyUI = '"inputs"'
    NovelAI = "NovelAI"


class PromptInspector(commands.Cog, name=COG_UID):
    def __init__(self, bot) -> None:
        self.bot: Owomatic = bot
        self.config = get_inspector_settings()

    @property
    def channel_settings(self) -> list[ChannelSettings]:
        return [channel for guild in self.config.guilds for channel in guild.channels]

    @property
    def enabled_channel_ids(self) -> list[int]:
        return [channel.id for channel in self.channel_settings if channel.enabled]

    @commands.Cog.listener("on_message")
    async def on_message(self, message: Message):
        # monitor only channels in the config
        if message.channel.id in self.enabled_channel_ids and message.attachments:
            logger.debug(f"Got message {message.id} from {message.author.id} with attachments...")
            attachments = [x for x in message.attachments if Path(x.filename).suffix.lower() in IMAGE_EXTNS]
            for i, attachment in enumerate(attachments):
                metadata = OrderedDict()
                await read_attachment_metadata(i, attachment, metadata)
                if len(metadata.keys()) > 0:
                    await message.add_reaction(TRIGGER_EMOJI)
                    break

    @commands.Cog.listener("on_raw_reaction_add")
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        if payload.member.bot or payload.member.id == self.bot.user.id:
            return
        if payload.emoji.name != TRIGGER_EMOJI:
            return

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        if message is None or len(message.attachments) == 0:
            logger.debug(f"Got reaction on message {payload.message_id} but no attachments found.")
            return
        logger.debug(
            f"Got reaction on message {payload.message_id} with {len(message.attachments)} attachments."
        )

        metadata: OrderedDict[int, tuple[MetadataType, str]] = OrderedDict()
        tasks = [
            read_attachment_metadata(i, attachment, metadata)
            for i, attachment in enumerate(message.attachments)
            if Path(attachment.filename).suffix.lower() in IMAGE_EXTNS
        ]
        logger.debug(f"Fetching metadata for {len(tasks)} attachments...")
        tasks = await gather(*tasks)
        if not metadata:
            logger.debug("No metadata found.")
            return

        attachment: Attachment
        dm_channel = await payload.member.create_dm()
        for attachment, (kind, data) in [(message.attachments[i], data) for i, data in metadata.items()]:
            try:
                logger.debug(f"Parsing and sending metadata for attachment {attachment.filename}...")

                if kind == MetadataType.Automatic1111:
                    params, truncated = get_params_from_string(data)
                    embed = get_embed(kind.name, message, params, attachment.url, truncated)
                    view = PromptView(metadata=metadata, filename=attachment.filename)
                    await dm_channel.send(embed=embed, view=view)
                elif kind in [MetadataType.ComfyUI, MetadataType.NovelAI]:
                    embed = get_embed(kind.name, message, {}, attachment.url, False)
                    meta_file = File(StringIO(data), "parameters.json")
                    view = PromptView(metadata=meta_file, filename=attachment.filename)
                    await dm_channel.send(embed=embed, view=view, mention_author=False)
                    await dm_channel.send(file=meta_file)
                else:
                    logger.warning(f"Got unknown metadata kind: {kind} - what?")

            except ValueError:
                logger.exception("failed somewhere in the send")
                pass

    @commands.message_command(name="Inspect Prompt", dm_permission=True)
    async def inspect_message(self, ctx: MessageCommandInteraction):
        """Get raw list of parameters for every image in this post."""
        await ctx.response.defer(ephemeral=True)
        message = ctx.target

        attachments = [a for a in message.attachments if a.filename.lower().endswith(".png")]
        if not attachments:
            logger.debug(f"No PNG attachments found on message {message.id}")
            await ctx.send("This post contains no matching images.", ephemeral=True)
            return
        logger.debug(f"Found {len(attachments)} PNG attachments on message {message.id}")

        metadata: OrderedDict[int, tuple[MetadataType, str]] = OrderedDict()
        tasks = [
            read_attachment_metadata(i, attachment, metadata)
            for i, attachment in enumerate(message.attachments)
            if Path(attachment.filename).suffix.lower() in IMAGE_EXTNS
        ]
        tasks = await gather(*tasks)
        if not metadata:
            logger.debug(f"No metadata found in attachments for message {message.id}")
            await ctx.send(
                f"This post contains no image generation data.\n{message.author.mention} needs to install [this extension](<https://github.com/neggles/sd-webui-stealth-pnginfo>)",
                ephemeral=True,
            )
            return

        # Add the magnifying glass reaction if it's not there
        target_emoji = [x.emoji for x in ctx.target.reactions]
        if not any([TRIGGER_EMOJI in str(x) for x in target_emoji]):
            try:
                await ctx.target.add_reaction(TRIGGER_EMOJI)
            except Exception as e:
                logger.exception("Failed to add reaction to message")

        attachment: Attachment
        for attachment, (kind, data) in [(attachments[i], data) for i, data in metadata.items()]:
            try:
                logger.debug(f"Parsing and sending metadata for attachment {attachment.filename}...")

                if kind == MetadataType.Automatic1111:
                    params, truncated = get_params_from_string(data)
                    embed = get_embed(kind.name, message, params, attachment.url, truncated)
                    view = PromptView(metadata=params, filename=attachment.filename)
                    await ctx.author.send(embed=embed, view=view, mention_author=False)
                    await ctx.send(embed=embed, view=view, ephemeral=True)
                elif kind in [MetadataType.ComfyUI, MetadataType.NovelAI]:
                    embed = get_embed(kind.name, message, {}, attachment.url, False)
                    meta_file = File(StringIO(data), "parameters.json")
                    view = PromptView(metadata=meta_file, filename=attachment.filename)
                    await ctx.author.send(embed=embed, view=view, mention_author=False)
                    await ctx.author.send(file=meta_file)
                    await ctx.send(
                        content="found non-AUTOMATIC1111 metadata - check your DMs.", ephemeral=True
                    )
                else:
                    logger.warning(f"Got unknown metadata kind: {kind} - what?")
            except ValueError as e:
                await ctx.send(content="Something went wrong, sorry!", ephemeral=True)
                logger.exception("something broke while sending prompt info")
                raise e


def get_embed(
    title: Optional[str] = None,
    context: Message = ...,
    params: dict = {},
    image_url: Optional[str] = None,
    truncated: bool = False,
) -> Embed:
    logger.debug("Generating embed...")
    if title is not None:
        embed = Embed(title=f"{title} Parameters", color=context.author.color)
    else:
        embed = Embed(color=context.author.color)

    embed.set_footer(text=f"Posted by {context.author}", icon_url=context.author.display_avatar.url)
    if image_url is not None:
        embed.set_image(url=image_url)
    for key, val in params.items():
        embed.add_field(name=key, value=f"`{val}`", inline="Prompt" not in key)
    if truncated:
        logger.debug("Embed was truncated (too many params)")
        embed.add_field(name="Too many parameters!", value="Can't display all in embed!", inline=False)

    logger.debug("Embed generated")
    return embed


@lru_cache(maxsize=128)
def get_params_from_string(param_str: str) -> tuple[dict, bool]:
    logger.debug(f"Parsing parameters from string: {param_str}")
    try:
        param_dict = json.loads(param_str)
        param_str = param_dict["infotexts"]
    except json.JSONDecodeError:
        pass

    output_dict = {}
    truncated = False

    parts = param_str.split("Steps: ")
    prompts = parts[0]
    params = "Steps: " + parts[1]
    if "Negative prompt: " in prompts:
        output_dict["Prompt"] = prompts.split("Negative prompt: ")[0]
        output_dict["Negative Prompt"] = prompts.split("Negative prompt: ")[1]
        if len(output_dict["Negative Prompt"]) > 1000:
            output_dict["Negative Prompt"] = output_dict["Negative Prompt"][:1000] + "..."
    else:
        output_dict["Prompt"] = prompts
    if len(output_dict["Prompt"]) > 1000:
        output_dict["Prompt"] = output_dict["Prompt"][:1000] + "..."

    params = params.split(", ")
    for param in params:
        if len(output_dict.keys()) >= MAX_FIELDS:
            logger.debug("hit param count limit")
            truncated = True
            break
        try:
            key, value = param.split(": ")
            output_dict[key] = value
        except ValueError:
            pass

    logger.debug(f"got {len(output_dict.keys())} params, returning...")
    return output_dict, truncated


def read_info_from_metadata(image: Image.Image) -> Optional[str | dict]:
    logger.debug("Trying metadata load from PNG text chunk or JPEG EXIF")

    if info := image.info.get("parameters", None):
        logger.debug("Found 'parameters' key")
        return info
    if info := image.info.get("prompt", None):
        logger.debug("Found 'prompt' key")
        return info
    if "NovelAI" in image.info.get("Software", None):
        logger.debug("Found 'Software' key (NAI)")
        return image.info.copy()
    logger.debug("No data found in PNG/JPEG metadata")
    return None


def get_meta_type(info: str | dict) -> Optional[MetadataType]:
    if isinstance(info, dict):
        if "NovelAI" in info.get("Software", ""):
            logger.debug("Found NovelAI metadata")
            return MetadataType.NovelAI

    for kind in MetadataType:
        if kind.value in info:
            logger.debug(f"Found {kind.name} metadata")
            return kind
    return None


async def read_attachment_metadata(
    idx: int, attachment: Attachment, metadata: OrderedDict[int, tuple[MetadataType, str]]
) -> None:
    """Acquire ye metadata."""
    if attachment.size > MAX_SCAN_BYTES:
        logger.debug(f"Attachment size {attachment.size} bytes is above MAX_SCAN_BYTES")
        return

    CHECK_FUNCS = [
        read_info_from_metadata,
        read_info_from_image_stealth,
    ]

    logger.debug(f"Trying to read attachment metadata from {attachment}")
    info: Optional[str] = None
    try:
        image_data = await attachment.read()
        logger.debug(f"Got file {attachment.filename}")
        with Image.open(BytesIO(image_data)) as img:
            for func in CHECK_FUNCS:
                info = func(img)
                if info is not None:
                    break
            if info is None:
                raise ValueError("No metadata found")
            if (meta_type := get_meta_type(info)) is None:
                raise ValueError("Did not find a known metadata type.")

            if isinstance(info, dict):
                # special handling ig
                info["Comment"] = json.loads(info["Comment"])
                info = json.dumps(info, indent=2, ensure_ascii=False, skipkeys=True, default=str)
            metadata[idx] = meta_type, info
    except Exception:
        logger.exception(f"Error while processing {attachment}")
        pass


def setup(bot):
    bot.add_cog(PromptInspector(bot))
