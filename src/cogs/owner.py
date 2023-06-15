import logging

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from owomatic.helpers import checks

logger = logging.getLogger(__package__)


class Owner(commands.Cog, name="owner"):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(
        name="shutdown",
        description="Shut down the bot.",
    )
    @checks.is_admin()
    async def shutdown(self, ctx: ApplicationCommandInteraction) -> None:
        """
        Makes the bot shutdown.
        :param interaction: The application command interaction.
        """
        embed = disnake.Embed(description="Shutting down. Bye! :wave:", color=0x9C84EF)
        await ctx.send(embed=embed, ephemeral=True)
        await self.bot.close()


def setup(bot):
    bot.add_cog(Owner(bot))
