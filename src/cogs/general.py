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

    @commands.slash_command(
        name="serverinfo",
        description="Get some useful (or not) information about the server.",
    )
    @checks.not_blacklisted()
    async def serverinfo(self, interaction: ApplicationCommandInteraction) -> None:
        """
        Get some useful (or not) information about the server.
        :param interaction: The application command interaction.
        """
        roles = [role.name for role in interaction.guild.roles]
        if len(roles) > 50:
            roles = roles[:50]
            roles.append(f">>>> Displaying[50/{len(roles)}] Roles")
        roles = ", ".join(roles)

        embed = disnake.Embed(title="**Server Name:**", description=f"{interaction.guild}", color=0x9C84EF)
        embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.add_field(name="Server ID", value=interaction.guild.id)
        embed.add_field(name="Member Count", value=interaction.guild.member_count)
        embed.add_field(name="Text/Voice Channels", value=f"{len(interaction.guild.channels)}")
        embed.add_field(name=f"Roles ({len(interaction.guild.roles)})", value=roles)
        embed.set_footer(text=f"Created at: {interaction.guild.created_at}")
        await interaction.send(embed=embed)


def setup(bot):
    bot.add_cog(General(bot))
