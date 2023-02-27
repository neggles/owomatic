import logging

from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from owomatic.helpers import checks

logger = logging.getLogger(__package__)


class Template(commands.Cog, name="template-slash"):
    def __init__(self, bot):
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


def setup(bot):
    bot.add_cog(Template(bot))
