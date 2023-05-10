import logging
from pathlib import Path

from disnake import ApplicationCommandInteraction
from disnake.ext import commands

import logsnake
from owomatic import LOGDIR_PATH, LOG_FORMAT
from owomatic.bot import Owomatic
from owomatic.helpers import checks

COG_UID = "cmd-auth"

# setup cog logger
logger = logsnake.setup_logger(
    level=logging.DEBUG,
    isRootLogger=False,
    name=COG_UID,
    formatter=logsnake.LogFormatter(fmt=LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"),
    logfile=LOGDIR_PATH.joinpath(f"{COG_UID}.log"),
    fileLoglevel=logging.INFO,
    maxBytes=2 * (2**20),
    backupCount=2,
)


class CommandAuth(commands.Cog, name=COG_UID):
    def __init__(self, bot: Owomatic):
        self.bot: Owomatic = bot

    @commands.slash_command(
        name="testcommand",
        description="This is a testing command that does nothing.",
    )
    @checks.not_blacklisted()
    @checks.is_owner()
    async def testcommand(self, inter: ApplicationCommandInteraction):
        """
        This is a testing command that does nothing.
        Note: This is a SLASH command
        :param inter: The application command interaction.
        """
        pass


def setup(bot):
    bot.add_cog(CommandAuth(bot))
