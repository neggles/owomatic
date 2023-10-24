from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseSettings, Field

from owomatic import DATADIR_PATH
from owomatic.settings import GuildSettingsList, JsonConfig

INSPECTOR_CFG_PATH = DATADIR_PATH.joinpath("prompt-inspector.json")


class InspectorSettings(BaseSettings):
    enabled: bool = Field(True)
    guilds: GuildSettingsList = Field([])

    class Config(JsonConfig):
        json_config_path = INSPECTOR_CFG_PATH


@lru_cache(maxsize=2)
def get_inspector_settings(config_path: Optional[Path] = None) -> InspectorSettings:
    if config_path is None:
        config_path = INSPECTOR_CFG_PATH
    settings = InspectorSettings(json_config_path=config_path)
    return settings
