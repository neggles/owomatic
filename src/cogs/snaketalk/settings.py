from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseSettings, Field

from owomatic import DATADIR_PATH
from owomatic.settings import GuildSettingsList, JsonConfig

SNAKETALK_CFG_PATH = DATADIR_PATH.joinpath("snaketalk.json")


class VoiceSettings(BaseSettings):
    enabled: bool = Field(False)
    guilds: GuildSettingsList = Field([])
    volume: int = Field(50)
    libname: str = Field(None)

    class Config(JsonConfig):
        json_config_path = SNAKETALK_CFG_PATH


@lru_cache(maxsize=2)
def get_snaketalk_settings(config_path: Optional[Path] = None) -> VoiceSettings:
    if config_path is None:
        config_path = SNAKETALK_CFG_PATH
    settings = VoiceSettings(json_config_path=config_path)
    return settings
