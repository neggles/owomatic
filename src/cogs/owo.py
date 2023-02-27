import logging
from random import choice as random_choice

from disnake import Message
from disnake.ext import commands

from owomatic.bot import Owomatic

logger = logging.getLogger(__package__)

OWO_VAULT = ["◕w◕", "σωσ", "◔w◔", "♥w♥", "𝓞𝔀𝓞", "𝙤𝙬𝙤", "uωu", "UωU", "OωO", "oωo", "OωO", "oωo"]
OWO_SENSE = ["owo", "uwu"]


def has_owo(message: Message) -> bool:
    return any(owo in message.content.lower() for owo in OWO_SENSE)


class Owo(commands.Cog, name="template-slash"):
    def __init__(self, bot: Owomatic):
        self.bot = bot
        self.owo_pool = OWO_VAULT

    async def cog_load(self) -> None:
        logger.info("owo? what's this?")
        return await super().cog_load()

    async def cog_unload(self) -> None:
        return await super().cog_unload()

    def get_owo(self):
        # if we only have one option left, use that and reset the pool
        if len(self.owo_pool) == 1:
            owo = self.owo_pool[0]
            self.owo_pool = OWO_VAULT
        else:  # get a random owo from the pool and remove it from the pool
            owo = random_choice(self.owo_pool)
            self.owo_pool.remove(owo)
        return owo

    @commands.Cog.listener("on_message")
    async def on_message(self, message: Message):
        if (message.author.bot is True) or (message.author == self.bot.user):
            return

        if has_owo(message):
            logger.info("owo!")
            await message.reply(self.get_owo())


def setup(bot):
    bot.add_cog(Owo(bot))
