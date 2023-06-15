import logging

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from owomatic import BLACKLIST_PATH
from owomatic.helpers import checks

logger = logging.getLogger(__package__)


class Owner(commands.Cog, name="owner"):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot
        self.blacklist_file = BLACKLIST_PATH

    @commands.slash_command(
        name="shutdown",
        description="Make the bot shutdown.",
    )
    @checks.is_owner()
    async def shutdown(self, inter: ApplicationCommandInteraction) -> None:
        """
        Makes the bot shutdown.
        :param interaction: The application command interaction.
        """
        embed = disnake.Embed(description="Shutting down. Bye! :wave:", color=0x9C84EF)
        await inter.send(embed=embed)
        await self.bot.close()


def setup(bot):
    bot.add_cog(Owner(bot))
