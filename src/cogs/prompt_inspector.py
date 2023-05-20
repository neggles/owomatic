from functools import lru_cache
import gzip
import json
import logging
from asyncio import gather
from collections import OrderedDict
from io import BytesIO
from typing import List, Optional

import logsnake
from async_lru import alru_cache
from disnake import (
    Attachment,
    ButtonStyle,
    Embed,
    Message,
    MessageCommandInteraction,
    MessageInteraction,
    RawReactionActionEvent,
)
from disnake.ext import commands
from disnake.ui import Button, View, button
from owomatic import DATADIR_PATH, LOG_FORMAT, LOGDIR_PATH
from owomatic.bot import Owomatic
from PIL import Image

COG_UID = "prompt-inspector"

CONFIG_FILE = DATADIR_PATH / f"{COG_UID}.json"

# TRIGGER_EMOJI = "📝"
TRIGGER_EMOJI = "🔎"

# setup cog logger
logger = logsnake.setup_logger(
    level=logging.DEBUG,
    isRootLogger=False,
    name=COG_UID,
    formatter=logsnake.LogFormatter(fmt=LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"),
    logfile=LOGDIR_PATH.joinpath(f"{COG_UID}.log"),
    fileLoglevel=logging.DEBUG,
    maxBytes=2 * (2**20),
    backupCount=2,
)


class PromptView(View):
    def __init__(self, metadata: str, timeout: float = 3600.0):
        super().__init__(timeout=timeout)
        self.metadata: Optional[str] = metadata

    @button(label="Raw Metadata", style=ButtonStyle.blurple, custom_id=f"{COG_UID}:raw_metadata")
    async def details(self, button: Button, ctx: MessageInteraction):
        await ctx.response.defer()
        try:
            button.disabled = True
            button.label = "✅ Done"
            button.style = ButtonStyle.green

            if len(self.metadata) > 1980:
                for i in range(0, len(self.metadata), 1980):
                    await ctx.send(f"```csv\n{self.metadata[i:i+1980]}```")
            else:
                await ctx.send(f"```csv\n{self.metadata}```")

        except Exception as e:
            await ctx.followup.send(f"Sending details failed: {e}")
            button.disabled = True
            button.label = "❌ Failed"
            button.style = ButtonStyle.red
            logger.error(e)
        finally:
            await ctx.edit_original_response(view=self)
            return


class PromptInspector(commands.Cog, name=COG_UID):
    def __init__(self, bot):
        self.bot: Owomatic = bot
        config_dict = json.loads(CONFIG_FILE.read_text())
        self.channel_ids: List[int] = config_dict.get("channel_ids", [])

    @commands.Cog.listener("on_message")
    async def on_message(self, message: Message):
        # ignore bots and self
        if message.author == self.bot.user:
            return
        # monitor only channels in the config
        if message.channel.id in self.channel_ids and message.attachments:
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
        ]
        logger.debug(f"Fetching metadata for {len(tasks)} attachments...")
        tasks = await gather(*tasks)
        if not metadata:
            logger.debug("No metadata found.")
            return

        dm_channel = await payload.member.create_dm()
        for attachment, data in [(message.attachments[i], data) for i, data in metadata.items()]:
            try:
                logger.debug(f"Parsing and sending metadata for attachment {attachment.filename}...")
                embed = dict2embed(get_params_from_string(data), message)
                embed.set_image(url=attachment.url)
                view = PromptView(metadata=metadata)
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
            await ctx.edit_original_response("This post contains no matching images.", ephemeral=True)
            return
        logger.debug(f"Found {len(attachments)} PNG attachments on message {message.id}")

        metadata = OrderedDict()
        tasks = [
            read_attachment_metadata(i, attachment, metadata)
            for i, attachment in enumerate(message.attachments)
        ]
        tasks = await gather(*tasks)
        if not metadata:
            logger.debug(f"No metadata found in attachments for message {message.id}")
            await ctx.edit_original_response(
                f"This post contains no image generation data.\n{message.author.mention} needs to install [this extension](<https://github.com/neggles/sd-webui-stealth-pnginfo>)",
                ephemeral=True,
            )
            return

        # Add the magnifying glass reaction if it's not there
        if TRIGGER_EMOJI not in [x.emoji for x in ctx.target.reactions]:
            await ctx.target.add_reaction(TRIGGER_EMOJI)

        dm_channel = await ctx.author.create_dm()
        first = True
        for attachment, data in [(attachments[i], data) for i, data in metadata.items()]:
            try:
                logger.debug(f"Parsing and sending metadata for attachment {attachment.filename}...")
                embed = dict2embed(get_params_from_string(data), message)
                embed.set_image(url=attachment.url)
                view = PromptView(metadata=metadata)
                if first is True:
                    await ctx.edit_original_response(embed=embed, view=view, ephemeral=True)
                    first = False
                await dm_channel.send(embed=embed, view=view, mention_author=False)
            except ValueError:
                pass


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
            return decoded_data
        except Exception as e:
            logger.exception(e)
            pass
    return None


@lru_cache(maxsize=128)
def get_params_from_string(param_str: str) -> dict:
    logger.debug(f"Parsing parameters from string: {param_str}")
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


@alru_cache(maxsize=128)
async def read_attachment_metadata(idx: int, attachment: Attachment, metadata: OrderedDict):
    """Allows downloading in bulk"""
    try:
        image_data = await attachment.read()
        with Image.open(BytesIO(image_data)) as img:
            try:
                info = img.info["parameters"]
            except Exception:
                info = read_info_from_image_stealth(img)
            if info and "Steps" in info:
                metadata[idx] = info
    except Exception as e:
        logger.error(f"{type(e).__name__}: {e}")


def setup(bot):
    bot.add_cog(PromptInspector(bot))
