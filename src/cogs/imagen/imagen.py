import json
import logging
import re
from asyncio import Lock
from base64 import b64decode
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional

from aiohttp import ClientSession
from disnake import ApplicationCommandInteraction, File
from disnake.ext import commands
from humanize import naturaldelta as fuzzydelta
from PIL import Image

from cogs.imagen.settings import (
    IMAGEN_DATA_DIR,
    ImageAspect,
    ImagenApiParams,
    ImagenModel,
    ImagenSettings,
    get_imagen_settings,
)
from cogs.imagen.ui import ImagenEmbed, ImagenView
from owomatic.bot import Owomatic

# setup cog logger
COG_UID = "imagen"
logger = logging.getLogger(__name__)


# for removing non-alphanumeric characters
re_clean_filename = re.compile(r"[^a-zA-Z0-9_\- ]+")
# for removing multiple consecutive dashes
re_single_dash = re.compile(r"-+")


def convert_model(ctx: ApplicationCommandInteraction, model_name: str) -> ImagenModel:
    cog: "Imagen" = ctx.bot.get_cog(COG_UID)
    if model_name is None:
        return cog.config.default_model
    model_name = model_name.lower()
    return next(
        iter([x for x in cog.config.models if model_name in [x.id.lower(), x.name.lower()]]),
        cog.config.default_model,
    )


def autocomp_models(ctx: ApplicationCommandInteraction, input: str) -> List[str]:
    cog: "Imagen" = ctx.bot.get_cog(COG_UID)
    input = input.lower()
    return [
        x.name
        for x in cog.config.models
        if (len(input) < 3) or (x.name.lower().startswith(input)) or (input in x.name.lower())
    ]


class Imagen(commands.Cog, name=COG_UID):
    session: ClientSession

    def __init__(self, bot: Owomatic):
        self.bot: Owomatic = bot
        self.config: ImagenSettings = get_imagen_settings()

        self.api_base: str = self.config.api_host.rstrip("/")
        self.api: ImagenApiParams = self.config.api_params

        IMAGEN_DATA_DIR.mkdir(exist_ok=True, parents=True)

        self._lock = Lock()
        logger.info("Initialized Imagen.")

    async def cog_load(self):
        self.session = ClientSession(base_url=f"{self.api_base}")

    def cog_unload(self):
        self.bot.loop.run_until_complete(self.session.close())

    @commands.slash_command(name="imagen", description="Generate an image from text")
    @commands.cooldown(1, 15.0, commands.BucketType.user)
    async def imagen_generate(
        self,
        ctx: ApplicationCommandInteraction,
        prompt: str = commands.Param(description="what want", max_length=200),
        negative: Optional[str] = commands.Param(description="what NOT want", max_length=200, default=""),
        aspect: ImageAspect = commands.Param(description="wide, square, tall?", default=ImageAspect.Square),
        steps: int = commands.Param(description="how much think", ge=1, le=50, default=25),
        cfg: float = commands.Param(description="how hard think", ge=0.0, le=30.0, default=9.5),
        model: ImagenModel = commands.Param(
            description="which brain",
            converter=convert_model,
            autocomplete=autocomp_models,
            default=None,
            convert_defaults=True,
        ),
        denoise: float = commands.Param(description="do you like aliasing", ge=0.0, le=1.0, default=0.51),
        seed: int = commands.Param(description="roll a d2147483646", ge=-1, le=0x7FFFFFFF, default=-1),
    ):
        await ctx.response.defer()
        logger.debug(f"Imagen request: {ctx.filled_options}")
        request = self.api.build_request(prompt, negative, steps, cfg, seed, denoise, aspect, model)

        image_path, response = await self.submit_request(ctx, request)
        image_file = File(image_path)

        embed = ImagenEmbed(author=ctx.author, model_name=model.name, api_response=response)
        view = ImagenView(self.bot, ctx.author, model.name, request)

        response_message = await ctx.edit_original_response(embed=embed, view=view, file=image_file)
        if self.bot.get_cog("prompt-inspector") is not None:
            response_message.add_reaction("🔍")

    @commands.slash_command(name="journey", description="Generate an image with OpenJourney")
    @commands.cooldown(1, 15.0, commands.BucketType.user)
    async def imagen_journey(
        self,
        ctx: ApplicationCommandInteraction,
        prompt: str = commands.Param(description="what want", max_length=200),
        negative: Optional[str] = commands.Param(description="what NOT want", max_length=200, default=""),
        aspect: ImageAspect = commands.Param(description="wide, square, tall?", default=ImageAspect.Square),
        steps: int = commands.Param(description="how much think", ge=1, le=50, default=25),
        cfg: float = commands.Param(description="how hard think", ge=0.0, le=30.0, default=9.5),
        denoise: float = commands.Param(description="do you like aliasing", ge=0.0, le=1.0, default=0.51),
        seed: int = commands.Param(description="roll a d2147483646", ge=-1, le=0x7FFFFFFF, default=-1),
    ):
        return await self.imagen_generate(
            ctx, prompt, negative, aspect, steps, cfg, convert_model(ctx, "openjourney-v2"), denoise, seed
        )

    @commands.slash_command(name="waifu", description="Generate an image with Andromeda")
    @commands.cooldown(1, 15.0, commands.BucketType.user)
    async def imagen_waifu(
        self,
        ctx: ApplicationCommandInteraction,
        prompt: str = commands.Param(description="what want", max_length=200),
        negative: Optional[str] = commands.Param(description="what NOT want", max_length=200, default=""),
        aspect: ImageAspect = commands.Param(description="wide, square, tall?", default=ImageAspect.Square),
        steps: int = commands.Param(description="tick tock", ge=1, le=50, default=25),
        cfg: float = commands.Param(description="hmmm", ge=0.0, le=30.0, default=7.75),
        denoise: float = commands.Param(description="do you like aliasing", ge=0.0, le=1.0, default=0.51),
        seed: int = commands.Param(description="roll a d2147483646", ge=-1, le=0x7FFFFFFF, default=-1),
    ):
        return await self.imagen_generate(
            ctx, prompt, negative, aspect, steps, cfg, convert_model(ctx, "AndromedaDX"), denoise, seed
        )

    async def submit_request(
        self, ctx: ApplicationCommandInteraction = ..., request: Dict[str, Any] = ...
    ) -> Path:
        # make a tag for the filename
        req_string: str = request["prompt"][:50]
        req_string = req_string.replace(" ", "-").replace(",", "")  # remove spaces and commas
        req_string = re_clean_filename.sub("", req_string)  # trim fs-unfriendly characters
        req_string = re_single_dash.sub("-", req_string).rstrip("-")  # remove multiple consecutive dashes

        # submit the request and save the image
        async with self._lock:
            start_time = perf_counter()
            async with self.session.post("/sdapi/v1/txt2img", json=request) as r:
                if r.status == 200:
                    response: dict = await r.json(encoding="utf-8")
                    end_time = perf_counter()
                else:
                    r.raise_for_status()
                try:
                    # throw an exception if we got no image
                    if response["images"] is None or len(response["images"]) == 0:
                        raise ValueError("No image data returned from Imagen API", args=response)

                    # load and decode the image
                    image: Image.Image = Image.open(BytesIO(b64decode(response["images"][0])))
                    response.pop("images")  # don't need this anymore

                    # glue the JSON string onto the PNG
                    image.format = "PNG"
                    image.info.update({"parameters": response["info"]})
                    # then decode it for logging purposes
                    response["info"] = json.loads(response["info"])

                    # add the time taken to the response
                    response["gen_duration"] = fuzzydelta(int(end_time - start_time))

                    # work out the path to save the image to, then save it and the job info
                    imagefile_path = IMAGEN_DATA_DIR.joinpath(
                        f'{response["info"]["job_timestamp"]}_{response["info"]["seed"]}_{req_string}.png'
                    )
                    image.save(imagefile_path, format="PNG")

                    # save the job info
                    imagefile_path.with_suffix(".json").write_text(
                        json.dumps(
                            {"request": request, "response": response},
                            indent=2,
                            skipkeys=True,
                            default=str,
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    # this could return the image object, but we're saving it anyway and it's easier to
                    # load a disnake File() from a path, so, uh... memory leak prevention? :sweat_smile:

                    return imagefile_path, response
                except Exception as e:
                    logger.exception("Error saving image")
                    raise e


async def get_progress(ctx: ApplicationCommandInteraction, preview_setting) -> int:
    pass


def setup(bot: commands.Bot):
    bot.add_cog(Imagen(bot))
