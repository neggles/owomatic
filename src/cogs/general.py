import platform
import random

import aiohttp
import disnake
from disnake import ApplicationCommandInteraction, Option, OptionType
from disnake.ext import commands

from owomatic.helpers import checks


class General(commands.Cog, name="general"):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="botinfo",
        description="Get some theoretically useful information about the bot.",
    )
    @checks.not_blacklisted()
    async def botinfo(self, interaction: ApplicationCommandInteraction) -> None:
        """
        Get some useful (or not) information about the bot.
        :param interaction: The application command interaction.
        """
        embed = disnake.Embed(description="a bot for WWF role management", color=0x9C84EF)
        embed.set_author(name="Bot Info", icon_url=self.bot.user.avatar.url)
        embed.add_field(name="Owner:", value=self.bot.config["owner"], inline=True)
        embed.add_field(name="Running on:", value=f"Python {platform.python_version()}", inline=True)
        embed.add_field(name="Repo:", value=self.bot.config["repo_url"], inline=False)
        embed.add_field(name="Prefix:", value="/ (Slash Commands)", inline=False)
        embed.set_footer(text=f"Requested by {interaction.author}", icon_url=interaction.author.avatar.url)
        await interaction.send(embed=embed)


def setup(bot):
    bot.add_cog(General(bot))
