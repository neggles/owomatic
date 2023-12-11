import gzip
import json
import logging
from asyncio import gather
from collections import OrderedDict
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from disnake import (
    Attachment,
    Embed,
    Message,
    MessageCommandInteraction,
    RawReactionActionEvent,
)
from disnake.ext import commands
from PIL import Image

import logsnake
from cogs.prompt_inspector.settings import get_inspector_settings
from cogs.prompt_inspector.ui import PromptView
from owomatic import LOG_FORMAT, LOGDIR_PATH
from owomatic.bot import Owomatic
from owomatic.settings import ChannelSettings

COG_UID = "prompt-inspector"

TRIGGER_EMOJI = "🔎"
IMAGE_EXTNS = [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".gif"]

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
            for i, attachment in enumerate(message.attachments):
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

        metadata = OrderedDict()
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
        for attachment, data in [(message.attachments[i], data) for i, data in metadata.items()]:
            try:
                logger.debug(f"Parsing and sending metadata for attachment {attachment.filename}...")
                embed = dict2embed(get_params_from_string(data), message)
                embed.set_image(url=attachment.url)
                view = PromptView(metadata=data, filename=attachment.filename)
                await dm_channel.send(embed=embed, view=view, mention_author=False)
            except ValueError:
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

        metadata = OrderedDict()
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
        for attachment, data in [(attachments[i], data) for i, data in metadata.items()]:
            try:
                logger.debug(f"Parsing and sending metadata for attachment {attachment.filename}...")
                embed = dict2embed(get_params_from_string(data), message)
                embed.set_image(url=attachment.url)
                view = PromptView(metadata=metadata)
                await ctx.author.send(embed=embed, view=view, mention_author=False)
                await ctx.send(content="Check your DMs.", ephemeral=True)
            except ValueError as e:
                await ctx.send(content="Something went wrong, sorry!", ephemeral=True)
                logger.exception("something broke while sending prompt info")
                raise e


def dict2embed(data: dict, context: Message) -> Embed:
    embed = Embed(color=context.author.color)
    for key, val in data.items():
        embed.add_field(name=key, value=f"`{val}`", inline="Prompt" not in key)
    embed.set_footer(text=f"Posted by {context.author}", icon_url=context.author.display_avatar.url)
    return embed


def read_info_from_image_stealth(image: Image.Image):
    # trying to read stealth pnginfo
    width, height = image.size
    pixels = image.load()

    has_alpha = True if image.mode == "RGBA" else False
    mode = None
    compressed = False
    binary_data = ""
    buffer_a = ""
    buffer_rgb = ""
    index_a = 0
    index_rgb = 0
    sig_confirmed = False
    confirming_signature = True
    reading_param_len = False
    reading_param = False
    read_end = False
    for x in range(width):
        for y in range(height):
            if has_alpha:
                r, g, b, a = pixels[x, y]
                buffer_a += str(a & 1)
                index_a += 1
            else:
                r, g, b = pixels[x, y]
            buffer_rgb += str(r & 1)
            buffer_rgb += str(g & 1)
            buffer_rgb += str(b & 1)
            index_rgb += 3
            if confirming_signature:
                if index_a == len("stealth_pnginfo") * 8:
                    decoded_sig = bytearray(
                        int(buffer_a[i : i + 8], 2) for i in range(0, len(buffer_a), 8)
                    ).decode("utf-8", errors="ignore")
                    if decoded_sig in {"stealth_pnginfo", "stealth_pngcomp"}:
                        confirming_signature = False
                        sig_confirmed = True
                        reading_param_len = True
                        mode = "alpha"
                        if decoded_sig == "stealth_pngcomp":
                            compressed = True
                        buffer_a = ""
                        index_a = 0
                    else:
                        read_end = True
                        break
                elif index_rgb == len("stealth_pnginfo") * 8:
                    decoded_sig = bytearray(
                        int(buffer_rgb[i : i + 8], 2) for i in range(0, len(buffer_rgb), 8)
                    ).decode("utf-8", errors="ignore")
                    if decoded_sig in {"stealth_rgbinfo", "stealth_rgbcomp"}:
                        confirming_signature = False
                        sig_confirmed = True
                        reading_param_len = True
                        mode = "rgb"
                        if decoded_sig == "stealth_rgbcomp":
                            compressed = True
                        buffer_rgb = ""
                        index_rgb = 0
            elif reading_param_len:
                if mode == "alpha":
                    if index_a == 32:
                        param_len = int(buffer_a, 2)
                        reading_param_len = False
                        reading_param = True
                        buffer_a = ""
                        index_a = 0
                else:
                    if index_rgb == 33:
                        pop = buffer_rgb[-1]
                        buffer_rgb = buffer_rgb[:-1]
                        param_len = int(buffer_rgb, 2)
                        reading_param_len = False
                        reading_param = True
                        buffer_rgb = pop
                        index_rgb = 1
            elif reading_param:
                if mode == "alpha":
                    if index_a == param_len:
                        binary_data = buffer_a
                        read_end = True
                        break
                else:
                    if index_rgb >= param_len:
                        diff = param_len - index_rgb
                        if diff < 0:
                            buffer_rgb = buffer_rgb[:diff]
                        binary_data = buffer_rgb
                        read_end = True
                        break
            else:
                # impossible
                read_end = True
                break
        if read_end:
            break
    if sig_confirmed and binary_data != "":
        # Convert binary string to UTF-8 encoded text
        byte_data = bytearray(int(binary_data[i : i + 8], 2) for i in range(0, len(binary_data), 8))
        try:
            if compressed:
                decoded_data = gzip.decompress(bytes(byte_data)).decode("utf-8")
            else:
                decoded_data = byte_data.decode("utf-8", errors="ignore")
            logger.debug(f"Got metadata: {decoded_data}")
            return decoded_data
        except Exception as e:
            logger.exception(e)
            pass
    return None


@lru_cache(maxsize=128)
def get_params_from_string(param_str: str) -> dict:
    logger.debug(f"Parsing parameters from string: {param_str}")
    try:
        param_dict = json.loads(param_str)
        param_str = param_dict["infotexts"]

    except json.JSONDecodeError:
        pass

    output_dict = {}
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
        try:
            key, value = param.split(": ")
            output_dict[key] = value
        except ValueError:
            pass
    logger.debug(f"got {len(output_dict.keys())} params, returning...")
    return output_dict


async def read_attachment_metadata(idx: int, attachment: Attachment, metadata: OrderedDict):
    """Allows downloading in bulk"""
    logger.debug(f"Reading attachment metadata from {attachment}")
    try:
        image_data = await attachment.read()
        logger.debug(f"Got file {attachment.filename}")
        with Image.open(BytesIO(image_data)) as img:
            logger.debug("Loading metadata from PNG text chunk")
            info: str = img.info.get("parameters", None)
            if info is None:
                logger.debug("No metadata found, trying to read from pixel data")
                info = read_info_from_image_stealth(img)
            if info is None:
                raise ValueError("No metadata found")
            if "Steps" not in info:
                raise ValueError("Invalid metadata")
            metadata[idx] = info
    except Exception as e:
        logger.error(f"{type(e).__name__}: {e}")


def setup(bot):
    bot.add_cog(PromptInspector(bot))
