import logging
from typing import Iterator, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class NamedSnowflake(BaseModel):
    id: int = Field(...)
    name: str = Field("")  # not actually used, just here so it can be in config
    note: Optional[str] = Field(None)


class SnowflakeList(BaseModel):
    __root__: list[NamedSnowflake] = []

    def __iter__(self) -> Iterator[NamedSnowflake]:
        return iter(self.__root__)

    def __getitem__(self, key) -> NamedSnowflake:
        return self.__root__[key]

    @property
    def ids(self) -> List[int]:
        return [x.id for x in self.__root__]

    def get_id(self, id: int) -> Optional[NamedSnowflake]:
        for item in self.__root__:
            if item.id == id:
                return item
        return None


class PermissionList(BaseModel):
    """A list of users and roles used for permission gating"""

    users: SnowflakeList = Field([])
    roles: SnowflakeList = Field([])

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
    channels: List[ChannelSettings] = Field([])

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


class GuildSettingsList(BaseModel):
    __root__: list[GuildSettings]

    def __iter__(self) -> Iterator[GuildSettings]:
        return iter(self.__root__)

    def __getitem__(self, key) -> GuildSettings:
        return self.__root__[key]

    @property
    def guild_ids(self) -> List[int]:
        return [x.id for x in self]

    @property
    def enabled_ids(self) -> list[int]:
        return [x.id for x in self if x.enabled is True]

    def get_id(self, guild_id: int) -> Optional[GuildSettings]:
        for guild in self.__root__:
            if guild.id == guild_id:
                return guild
        return None
