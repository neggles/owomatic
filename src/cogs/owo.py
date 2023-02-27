import logging
from random import choice as random_choice

from disnake import ApplicationCommandInteraction, Message
from disnake.ext import commands

from owomatic.bot import Owomatic
from owomatic.helpers import checks

logger = logging.getLogger(__package__)

OWO = "owo"
OWO_STRINGS = ["◕w◕", "σωσ", "◔w◔", "♥w♥", "𝓞𝔀𝓞", "𝙤𝙬𝙤", "uωu", "UωU", "OωO", "oωo", "OωO", "oωo"]


def get_owo():
    return random_choice(OWO_STRINGS)


class Template(commands.Cog, name="template-slash"):
    def __init__(self, bot: Owomatic):
        self.bot = bot

    @commands.slash_command(
        name="testcommand",
        description="This is a testing command that does nothing.",
    )
    @checks.not_blacklisted()
    @checks.is_owner()
    async def testcommand(self, interaction: ApplicationCommandInteraction):
        """
        This is a testing command that does nothing.
        Note: This is a SLASH command
        :param interaction: The application command interaction.
        """
        pass

    @commands.Cog.listener("on_message")
    async def on_message(self, message: Message):
        if (message.author.bot is True) or (message.author == self.bot.user):
            return

        if OWO in message.content.lower():
            message.reply(get_owo())


def setup(bot):
    bot.add_cog(Template(bot))
