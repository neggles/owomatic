import logging
from enum import Enum
from functools import lru_cache
from operator import neg
from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import BaseModel, BaseSettings, Field

from owomatic import DATADIR_PATH
from owomatic.settings import JsonConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IMAGEN_CFG_PATH = DATADIR_PATH.joinpath("imagen.json")
IMAGEN_DATA_DIR = DATADIR_PATH.joinpath("imagen")
IMAGEN_DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_PIXELS = 768 * 768  # clamp image size to this many pixels
HR_RATIO = 1.5  # ratio of high-res to low-res image size


class ImageAspect(int, Enum):
    Square = 0
    Landscape = 1
    Portrait = 2


def get_image_size(aspect: ImageAspect) -> Tuple[int, int]:
    """Y'all can have about a half a megapixel (pre-upscale)"""
    if aspect == ImageAspect.Square:
        return 768, 768
    elif aspect == ImageAspect.Landscape:
        return 896, 640
    elif aspect == ImageAspect.Portrait:
        return 640, 896
    else:
        raise ValueError(f"Invalid aspect ratio: {aspect}")


class NamedSnowflake(BaseModel):
    id: int = Field(...)
    name: str = Field("")  # not actually used, just here so it can be in config
    note: Optional[str] = Field(None)


class PermissionList(BaseModel):
    users: List[NamedSnowflake] = Field([])
    roles: List[NamedSnowflake] = Field([])

    @property
    def user_ids(self) -> List[int]:
        return [x.id for x in self.users]

    @property
    def role_ids(self) -> List[int]:
        return [x.id for x in self.roles]


class ChannelSettings(NamedSnowflake):
    enabled: bool = Field(True)


class GuildSettings(NamedSnowflake):
    enabled: bool = Field(True)
    channels: List[ChannelSettings] = Field(default_factory=list)

    def channel_enabled(self, channel_id: int) -> bool:
        """
        Returns whether the bot should respond to messages in this channel,
        based on the guild's default setting and the channel's settings.
        """
        if self.enabled is False:
            return False  # guild is disabled, don't respond
        if channel_id in [x.id for x in self.channels if x.enabled is True]:
            return True  # channel is explicitly enabled
        return self.enabled  # guild default


class ImagenModel(BaseModel):
    enabled: bool = Field(True)
    name: str = Field(...)
    id: str = Field(...)
    kind: str = Field("waifu")
    checkpoint: Optional[str] = Field(None)
    vae: Optional[str] = Field(None)
    tags: List[str] = Field([])
    tag_pos: str = Field("start")
    negative: List[str] = Field([])
    clip_skip: int = Field(2)
    overrides: Optional[dict] = None

    def get_negative(self, prompt: str):
        if len(self.negative) > 0:
            return ", ".join([*self.negative, prompt])
        return prompt

    def get_prompt(self, prompt: str):
        if len(self.tags) > 0:
            if self.tag_pos == "start":
                return ", ".join([*self.tags, prompt])
            elif self.tag_pos == "end":
                return ", ".join([prompt, *self.tags])
        return prompt


class ImagenApiParams(BaseModel):
    steps: int = 25
    cfg_scale: float = ...
    vae: str = ...
    sampler_name: str = "DPM++ 2M Karras"
    enable_hr: bool = False
    hr_steps: int = 6
    hr_denoise: float = 0.51
    hr_scale: float = 1.5
    hr_upscaler: str = "Latent"
    clip_skip: int = 2
    overrides: Optional[dict] = None

    def build_request(
        self,
        prompt: str,
        negative: str = "",
        steps: Optional[int] = None,
        cfg_scale: Optional[float] = None,
        seed: Optional[int] = None,
        denoise: Optional[float] = None,
        aspect: ImageAspect = ...,
        model: ImagenModel = ...,
    ):
        width, height = get_image_size(aspect)

        prompt = model.get_prompt(prompt)
        negative = model.get_negative(negative)

        request_obj = {
            "prompt": prompt,
            "negative_prompt": negative,
            "steps": steps,
            "cfg_scale": cfg_scale or self.cfg_scale,
            "seed": seed or -1,
            "seed_enable_extras": False,
            "subseed": -1,
            "seed_resize_from_h": 0,
            "seed_resize_from_w": 0,
            "width": width,
            "height": height,
            "batch_size": 1,
            "n_iter": 1,
            "send_images": True,
            "save_images": True,
            "sampler_name": self.sampler_name,
            "enable_hr": int(self.enable_hr),
            "hr_scale": 1.5,
            "hr_second_pass_steps": self.hr_steps,
            "denoising_strength": denoise or self.hr_denoise,
            "hr_upscaler": self.hr_upscaler,
        }
        # copy the overrides dict so we don't modify the original
        overrides = self.overrides.copy() if self.overrides is not None else {}

        # set the checkpoint, VAE, and CLIP skip from the model
        overrides["sd_model_checkpoint"] = model.checkpoint
        overrides["sd_vae"] = model.vae or self.vae
        overrides["CLIP_stop_at_last_layers"] = model.clip_skip or self.clip_skip

        # apply model overrides
        overrides.update(model.overrides or {})

        # if we have overrides, set them in the request object
        if len(overrides.keys()) > 0:
            request_obj["override_settings"] = overrides
            request_obj["override_settings_restore_afterwards"] = True

        # return the request object
        return request_obj


class ImagenSettings(BaseSettings):
    enabled: bool = Field(True)
    api_host: str = Field(...)
    api_params: ImagenApiParams = Field(...)
    models: List[ImagenModel] = Field(...)
    default_model_id: str = Field(...)

    @property
    def default_model(self):
        return next(iter([x for x in self.models if x.id == self.default_model_id]))

    def get_model(self, model_id: str) -> Optional[ImagenModel]:
        return next(iter([x for x in self.models if x.id == model_id]), None)

    class Config(JsonConfig):
        json_config_path = IMAGEN_CFG_PATH


@lru_cache(maxsize=2)
def get_imagen_settings(config_path: Optional[Path] = None) -> ImagenSettings:
    if config_path is None:
        config_path = IMAGEN_CFG_PATH
    settings = ImagenSettings(json_config_path=config_path)
    return settings
