import json
import logging
from asyncio import gather, sleep
from enum import IntEnum
from io import BytesIO, StringIO
from typing import Optional, List
from collections import OrderedDict

from disnake import (
    ApplicationCommandInteraction,
    Embed,
    File,
    Message,
    MessageCommandInteraction,
    ButtonStyle,
    Attachment,
    RawReactionActionEvent,
)
from disnake.ext import commands
from disnake.ui import View, Button, button
from PIL import Image

import logsnake
from owomatic import DATADIR_PATH, LOG_FORMAT, LOGDIR_PATH
from owomatic.bot import Owomatic
from owomatic.helpers import checks

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
    fileLoglevel=logging.INFO,
    maxBytes=2 * (2**20),
    backupCount=2,
)


class PromptView(View):
    def __init__(self, metadata: str, timeout: float = 3600.0):
        super().__init__(timeout=timeout)
        self.metadata: Optional[str] = None

    @button(label="Raw Metadata", style=ButtonStyle.secondary)
    async def details(self, button: Button, ctx: ApplicationCommandInteraction):
        button.disabled = True
        await ctx.edit_original_response(view=self)

        if len(self.metadata) > 1980:
            for i in range(0, len(self.metadata), 1980):
                await ctx.send(f"```csv\n{self.metadata[i:i+1980]}```")
        else:
            await ctx.send(f"```csv\n{self.metadata}```")

        self.stop()


class PromptInspector(commands.Cog, name=COG_UID):
    def __init__(self, bot):
        self.bot: Owomatic = bot
        config_dict = json.loads(CONFIG_FILE.read_text())
        self.channel_ids: List[int] = config_dict.get("channel_ids", [])

    @commands.Cog.listener("on_message")
    async def on_message(self, message: Message):
        # ignore bots and self
        if (message.author.bot is True) or (message.author == self.bot.user):
            return
        # monitor only channels in the config
        if message.channel.id not in self.channel_ids:
            return

        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename.endswith(".png"):
                    image_data = await attachment.read()
                    with Image.open(BytesIO(image_data)) as image:
                        try:
                            metadata = decode_stealth_metadata(image)
                            if metadata and "Steps" in metadata:
                                logger.debug("Found metadata: %s", metadata)
                                await message.add_reaction(TRIGGER_EMOJI)
                        except Exception as e:
                            pass

    @commands.Cog.listener("on_raw_reaction_add")
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        if payload.member.bot or payload.member.id == self.bot.user.id:
            return
        if payload.emoji.name != TRIGGER_EMOJI or payload.channel_id not in self.channel_ids:
            return

        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        if message is None or len(message.attachments) == 0:
            return

        metadata = OrderedDict()
        tasks = [
            read_attachment_metadata(i, attachment, metadata)
            for i, attachment in enumerate(message.attachments)
        ]
        await gather(*tasks)
        if not metadata:
            return

        for attachment, data in [(message.attachments[i], data) for i, data in metadata.items()]:
            try:
                embed = dict2embed(get_params_from_string(data), message)
                embed.set_image(url=attachment.url)
                view = PromptView(metadata=metadata)
                await payload.member.send(embed=embed, view=view, mention_author=False)
            except ValueError:
                pass

    @commands.message_command(name="Inspect Prompt", dm_permission=True)
    async def inspect_message(self, ctx: MessageCommandInteraction, message: Message):
        """Get raw list of parameters for every image in this post."""
        attachments = [a for a in message.attachments if a.filename.lower().endswith(".png")]
        if not attachments:
            await ctx.respond("This post contains no matching images.", ephemeral=True)
            return
        await ctx.defer(ephemeral=True)

        metadata = OrderedDict()
        tasks = [
            read_attachment_metadata(i, attachment, metadata)
            for i, attachment in enumerate(message.attachments)
        ]
        await gather(*tasks)
        if not metadata:
            await ctx.respond(
                f"This post contains no image generation data.\n{message.author.mention} needs to install [this extension](<https://github.com/ashen-sensored/sd_webui_stealth_pnginfo>).",
                ephemeral=True,
            )
            return
        response = "\n\n".join(metadata.values())
        if len(response) < 1980:
            await ctx.respond(f"```yaml\n{response}```", ephemeral=True)
        else:
            with StringIO() as f:
                f.write(response)
                f.seek(0)
                await ctx.respond(file=File(f, "parameters.yaml"), ephemeral=True)


def get_params_from_string(param_str):
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
    return output_dict


def dict2embed(data: dict, context: Message) -> Embed:
    embed = Embed(color=context.author.accent_color)
    for key, val in data.items():
        embed.add_field(name=key, value=val, inline="Prompt" not in key)
    embed.set_footer(text=f"Posted by {context.author}", icon_url=context.author.display_avatar.url)


class DecodeState(IntEnum):
    ERROR = -1
    SIG_SCAN = 0
    PARAM_LEN = 1
    PARAM_DATA = 2
    PARAM_END = 3
    END = 4


def decode_stealth_metadata(image: Image.Image) -> Optional[str]:
    STEALTH_MAGIC = "".join(format(byte, "08b") for byte in "stealth_pnginfo".encode())

    if image.mode != "RGBA":
        logger.debug("Got image with no alpha channel, skipping...")
        return None

    # do some setup
    width, height = image.size
    pixels = image.load()

    sig_found = False
    decode_state = DecodeState(0)
    buffer = ""
    bindata = ""
    index = 0

    for x in range(width):
        for y in range(height):
            _, _, _, a = pixels[x, y]
            buffer += str(a & 1)
            if decode_state == DecodeState.SIG_SCAN:
                if index == len("stealth_pnginfo") * 8 - 1:
                    if buffer == STEALTH_MAGIC:
                        sig_found = True
                        decode_state = DecodeState.PARAM_LEN
                        buffer = ""
                        index = 0
                    else:
                        decode_state = DecodeState.ERROR
                        break

            elif decode_state == DecodeState.PARAM_LEN:
                if index == 32:
                    param_len = int(buffer, 2)
                    decode_state = DecodeState.PARAM_DATA
                    buffer = ""
                    index = 0

            elif decode_state == DecodeState.PARAM_DATA:
                if index == param_len:
                    bindata = buffer
                    decode_state = DecodeState.PARAM_END
            else:
                # should never make it here
                decode_state = DecodeState.ERROR
                break
        if decode_state == DecodeState.ERROR or decode_state == DecodeState.PARAM_END:
            break

    if sig_found:
        return bytearray(int(bindata[i : i + 8], 2) for i in range(0, len(bindata), 8)).decode(
            "utf-8", errors="ignore"
        )
    return None


async def read_attachment_metadata(idx: int, attachment: Attachment, metadata: OrderedDict):
    """Allows downloading in bulk"""
    try:
        image_data = await attachment.read()
        with Image.open(BytesIO(image_data)) as img:
            info = decode_stealth_metadata(img)
            if info and "Steps" in info:
                metadata[idx] = info
    except Exception as error:
        print(f"{type(error).__name__}: {error}")


def setup(bot):
    bot.add_cog(PromptInspector(bot))
