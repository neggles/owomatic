import logging
import os
import platform
import random
import sys
from pathlib import Path
from traceback import print_exception
from zoneinfo import ZoneInfo

import disnake
from disnake import ApplicationCommandInteraction, Intents
from disnake.ext import commands, tasks

import exceptions
from owomatic.helpers.misc import get_package_root

PACKAGE_ROOT = get_package_root()

BOT_INTENTS = Intents.all()
BOT_INTENTS.members = True
BOT_INTENTS.presences = False
BOT_INTENTS.typing = False
BOT_INTENTS.message_content = False


logger = logging.getLogger(__package__)


class Owomatic(commands.Bot):
    def __init__(self, *args, **kwargs):
        command_prefix = kwargs.pop("command_prefix", commands.when_mentioned)
        intents = kwargs.pop("intents", BOT_INTENTS)

        super().__init__(*args, command_prefix=command_prefix, intents=intents, **kwargs)

        # attributes set up in cli.py. this is a dumb way to do this but it works
        self.config: dict = None
        self.timezone: ZoneInfo = None
        self.datadir_path: Path = None
        self.userdata_path: Path = None
        self.userdata: dict = None
        self.cogdir_path: Path = None
        self.extdir_path: Path = None

    def available_cogs(self):
        return [
            f.stem
            for f in self.cogdir_path.glob("*.py")
            if f.stem != "template" and not f.stem.endswith("_wip")
        ]

    def load_cogs(self, override: bool = False):
        cogs = self.available_cogs()
        if cogs:
            for cog in cogs:
                try:
                    self.load_extension(f"cogs.{cog}")
                    logger.info(f"Loaded cog '{cog}'")
                except Exception:
                    etype, exc, tb = sys.exc_info()
                    exception = f"{etype}: {exc}"
                    logger.error(f"Failed to load extension {cog}:\n{exception}")
                    print_exception(etype, exc, tb)
        else:
            logger.info("No cogs found")

    @tasks.loop(minutes=1.0)
    async def status_task(self) -> None:
        """
        Set up the bot's status task
        """
        statuses = self.config["statuses"]
        activity = disnake.Activity(name=random.choice(statuses), type=disnake.ActivityType.playing)
        await self.change_presence(activity=activity)

    @status_task.before_loop
    async def before_status_task(self):
        print("waiting...")
        await self.wait_until_ready()

    async def on_ready(self) -> None:
        """
        The code in this even is executed when the bot is ready
        """
        logger.info(f"Logged in as {self.user.name}")
        logger.info(f"disnake API version: {disnake.__version__}")
        logger.info(f"Python version: {platform.python_version()}")
        logger.info(f"Running on: {platform.system()} {platform.release()} ({os.name})")
        logger.info("-------------------")
        if not self.status_task.is_running():
            self.status_task.start()

    async def on_message(self, message: disnake.Message) -> None:
        """
        The code in this event is executed every time someone sends a message, with or without the prefix
        :param message: The message that was sent.
        """
        if message.author == self.user or message.author.bot:
            return

        await self.process_commands(message)

    async def on_slash_command(self, interaction: ApplicationCommandInteraction) -> None:
        """
        The code in this event is executed every time a slash command has been *successfully* executed
        :param interaction: The slash command that has been executed.
        """
        logger.info(
            f"Executed {interaction.data.name} command in {interaction.guild.name} (ID: {interaction.guild.id}) by {interaction.author} (ID: {interaction.author.id})"
        )

    async def on_slash_command_error(interaction: ApplicationCommandInteraction, error: Exception) -> None:
        """
        The code in this event is executed every time a valid slash command catches an error
        :param interaction: The slash command that failed executing.
        :param error: The error that has been faced.
        """
        if isinstance(error, exceptions.UserBlacklisted):
            """
            The code here will only execute if the error is an instance of 'UserBlacklisted', which can occur when using
            the @checks.is_owner() check in your command, or you can raise the error by yourself.

            'hidden=True' will make so that only the user who execute the command can see the message
            """
            embed = disnake.Embed(
                title="Error!", description="You are blacklisted from using the bot.", color=0xE02B2B
            )
            logger.info("A blacklisted user tried to execute a command.")
            return await interaction.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.errors.MissingPermissions):
            embed = disnake.Embed(
                title="Error!",
                description="You are missing the permission(s) `"
                + ", ".join(error.missing_permissions)
                + "` to execute this command!",
                color=0xE02B2B,
            )
            logger.info("A blacklisted user tried to execute a command.")
            return await interaction.send(embed=embed, ephemeral=True)
        else:
            logger.error(f"An error occurred while executing a slash command: {error}")
            embed = disnake.Embed(
                title="Error!",
                description=f"An error occurred while executing the command: {str(error).capitalize()}",
                color=0xE02B2B,
            )
            await interaction.send(embed=embed, ephemeral=True)
        raise error

    async def on_command_completion(context: commands.Context) -> None:
        """
        The code in this event is executed every time a normal command has been *successfully* executed
        :param context: The context of the command that has been executed.
        """
        full_command_name = context.command.qualified_name
        split = full_command_name.split(" ")
        executed_command = str(split[0])
        logger.info(
            f"Executed {executed_command} command in {context.guild.name} (ID: {context.message.guild.id}) by {context.message.author} (ID: {context.message.author.id})"
        )

    async def on_command_error(context: commands.Context, error) -> None:
        """
        The code in this event is executed every time a normal valid command catches an error
        :param context: The normal command that failed executing.
        :param error: The error that has been faced.
        """
        if isinstance(error, commands.CommandOnCooldown):
            minutes, seconds = divmod(error.retry_after, 60)
            hours, minutes = divmod(minutes, 60)
            hours = hours % 24
            embed = disnake.Embed(
                title="Hey, please slow down!",
                description=f"You can use this command again in {f'{round(hours)} hours' if round(hours) > 0 else ''} {f'{round(minutes)} minutes' if round(minutes) > 0 else ''} {f'{round(seconds)} seconds' if round(seconds) > 0 else ''}.",
                color=0xE02B2B,
            )
            await context.send(embed=embed, delete_after=5.0)
        elif isinstance(error, commands.MissingPermissions):
            embed = disnake.Embed(
                title="Error!",
                description="You are missing the permission(s) `"
                + ", ".join(error.missing_permissions)
                + "` to execute this command!",
                color=0xE02B2B,
            )
            await context.send(embed=embed, delete_after=5.0)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = disnake.Embed(
                title="Error!",
                # We need to capitalize because the command arguments have no capital letter in the code.
                description=str(error).capitalize(),
                color=0xE02B2B,
            )
            await context.send(embed=embed, delete_after=5.0)
        elif isinstance(error, commands.CommandNotFound):
            # This is actually fine so lets just pretend everything is okay.
            return
        else:
            logger.warn(f"An error occurred while executing a command: {error}")
            raise error
