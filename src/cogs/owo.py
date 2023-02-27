import logging
from random import choice as random_choice

from disnake import Message
from disnake.ext import commands

from owomatic.bot import Owomatic

logger = logging.getLogger(__package__)

TRIGGER_STRINGS = ["owo", "uwu"]
OWO_STRINGS = ["◕w◕", "σωσ", "◔w◔", "♥w♥", "𝓞𝔀𝓞", "𝙤𝙬𝙤", "uωu", "UωU", "OωO", "oωo", "OωO", "oωo"]


class Owo(commands.Cog, name="template-slash"):
    def __init__(self, bot: Owomatic):
        self.bot = bot
        self.owo_pool = OWO_STRINGS

    async def cog_load(self) -> None:
        logger.info("owo? what's this?")
        return await super().cog_load()

    async def cog_unload(self) -> None:
        return await super().cog_unload()

    def has_owo(self, message: Message) -> bool:
        return any(trigger in message.content.lower() for trigger in TRIGGER_STRINGS)

    def get_owo(self):
        # if we only have one option left, use that and reset the pool
        if len(self.owo_pool) == 1:
            owo = self.owo_pool[0]
            self.owo_pool = OWO_STRINGS
        else:  # get a random owo from the pool and remove it from the pool
            owo = random_choice(self.owo_pool)
            self.owo_pool.remove(owo)
        return owo

    @commands.Cog.listener("on_message")
    async def on_message(self, message: Message):
        if (message.author.bot is True) or (message.author == self.bot.user):
            return

        if self.has_owo(message):
            logger.info("owo!")
            await message.reply(self.get_owo())


def setup(bot):
    bot.add_cog(Owo(bot))
