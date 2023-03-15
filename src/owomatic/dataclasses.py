import disnake
from dataclasses import InitVar, dataclass
from dataclasses_json import dataclass_json, LetterCase


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class RoleInfo:
    role: InitVar[disnake.Role] = None
    id: int = None
    name: str = None

    def __post_init__(self, role: disnake.Role):
        if role is not None:
            self.id = role.id
            self.name = role.name


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class MemberInfo:
    member: InitVar[disnake.Member] = None
    id: int = None
    bot: bool = None
    name: str = None
    display_name: str = None
    guild: int = None
    roles: list[RoleInfo] = None
    joined_at: str = None

    def __post_init__(self, member: disnake.Member):
        if member is not None:
            self.id = member.id
            self.bot = member.bot
            self.name = member.name
            self.display_name = member.display_name
            self.guild = member.guild.id
            self.roles = [RoleInfo(role=x) for x in member.roles]
            self.joined_at = member.joined_at.isoformat()
