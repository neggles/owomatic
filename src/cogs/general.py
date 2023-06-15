import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from owomatic.bot import Owomatic
from owomatic.helpers import checks


class General(commands.Cog, name="general"):
    def __init__(self, bot) -> None:
        self.bot: Owomatic = bot

    @commands.slash_command(name="ping", description="ping the bot")
    @checks.not_blacklisted()
    async def ping(self, ctx: ApplicationCommandInteraction) -> None:
        """
        Check if the bot is alive.
        :param ctx: The application command ctx.
        """
        embed = disnake.Embed(
            title="🏓 Pong!",
            description=f"Current API latency is {round(self.bot.latency * 1000)}ms",
            color=0x9C84EF,
        )
        await ctx.send(embed=embed, ephemeral=True)


def setup(bot):
    bot.add_cog(General(bot))
