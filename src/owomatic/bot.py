import logging
import os
import platform
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import partial as partial_func
from pathlib import Path
from shlex import join
from traceback import format_exc, format_exception, print_exception
from zoneinfo import ZoneInfo

from disnake import (
    Activity,
    ActivityType,
    ApplicationCommandInteraction,
    Embed,
    Guild,
    Intents,
    InteractionResponseType,
    Message,
    Status,
    __version__ as DISNAKE_VERSION,
)
from disnake.ext import commands, tasks
from humanize import naturaldelta as fuzzydelta

import exceptions
from owomatic import COGDIR_PATH, DATADIR_PATH
from owomatic.embeds import CooldownEmbed, MissingPermissionsEmbed, MissingRequiredArgumentEmbed
from owomatic.helpers.misc import get_package_root
from owomatic.settings import get_settings

PACKAGE_ROOT = get_package_root()

BOT_INTENTS = Intents.all()
BOT_INTENTS.typing = False
BOT_INTENTS.presences = False
BOT_INTENTS.members = True
BOT_INTENTS.message_content = True

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.propagate = True


class Owomatic(commands.Bot):
    def __init__(self, config_path: Path, *args, **kwargs):
        intents = kwargs.pop("intents", BOT_INTENTS)
        super().__init__(*args, command_prefix=None, intents=intents, **kwargs)

        self.config = get_settings(config_path)
        self.datadir_path: Path = DATADIR_PATH
        self.cogdir_path: Path = COGDIR_PATH
        self.start_time: datetime = datetime.now(tz=ZoneInfo("UTC"))

        # thread pool for blocking code
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bot")

    @property
    def timezone(self) -> ZoneInfo:
        return self.config.timezone

    @property
    def uptime(self) -> timedelta:
        return datetime.now(tz=ZoneInfo("UTC")) - self.start_time

    @property
    def fuzzyuptime(self) -> str:
        return fuzzydelta(self.uptime)

    @property
    def owner_link(self):
        return f"[{self.owner}](https://discordapp.com/users/{self.owner_id})"

    @property
    def support_guild(self) -> Guild:
        return self.get_guild(self.config.support_guild)

    @property
    def home_guild(self) -> Guild:
        return self.get_guild(self.config.home_guild)

    @property
    def hide(self) -> bool:
        return self.config.hide

    async def do(self, func, *args, **kwargs):
        """Run a blocking function in a background thread."""
        funcname = getattr(func, "__name__", None)
        if funcname is None:
            funcname = getattr(func.__class__, "__name__", "unknown")
        logger.info(f"Running {funcname} in background thread...")
        return await self.loop.run_in_executor(self.executor, partial_func(func, *args, **kwargs))

    def available_cogs(self) -> list[str]:
        cogs = [
            p.stem
            for p in self.cogdir_path.iterdir()
            if (p.is_dir() or p.suffix == ".py") and not p.name.startswith("_")
        ]

        if len(self.config.disable_cogs) > 0:
            cogs = [x for x in cogs if x not in self.config.disable_cogs]
        return cogs

    def load_cogs(self) -> None:
        cogs = self.available_cogs()
        if cogs:
            for cog in cogs:
                try:
                    self.load_extension(f"cogs.{cog}")
                    logger.info(f"Loaded cog '{cog}'")
                except Exception as e:
                    etype, exc, tb = sys.exc_info()
                    exception = f"{etype}: {exc}"
                    logger.error(f"Failed to load cog {cog}:\n{exception}")
                    print_exception(etype, exc, tb)
        else:
            logger.info("No cogs found")

    async def on_ready(self) -> None:
        """
        The code in this even is executed when the bot is ready
        """
        logger.info(f"Logged in as {self.user.name}")
        logger.info(f"disnake API version: {DISNAKE_VERSION}")
        logger.info(f"Python version: {platform.python_version()}")
        logger.info(f"Running on: {platform.system()} {platform.release()} ({os.name})")
        logger.info("-------------------")
        if self.hide is False:
            if not self.status_task.is_running():
                logger.info("Starting status update task")
                self.status_task.start()
        else:
            logger.info("Hide is set to True, bot will not be visible")
            await self.change_presence(status=Status.invisible)

    async def on_message(self, message: Message) -> None:
        await self.process_commands(message)

    async def on_slash_command(self, ctx: ApplicationCommandInteraction) -> None:
        logger.info(
            f"Executed {ctx.data.name} command in {ctx.guild.name} (ID: {ctx.guild.id}) by {ctx.author} (ID: {ctx.author.id})"
        )

    async def on_slash_command_error(self, ctx: ApplicationCommandInteraction, error) -> None:
        if isinstance(error, commands.CommandOnCooldown):
            logger.info(
                f"User {ctx.author} attempted to use {ctx.application_command.qualified_name} on cooldown."
            )
            embed = CooldownEmbed(error.retry_after + 1, ctx.author)
            return await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, exceptions.UserBlacklisted):
            logger.info(
                f"User {ctx.author} attempted to use {ctx.application_command.qualified_name}, but is blacklisted."
            )
            embed = Embed(
                title="Error!",
                description="You have been blacklisted and cannot use this bot. If you think this is a mistake, please contact the bot owner.",
                color=0xE02B2B,
            )
            return await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, exceptions.UserNotOwner):
            embed = Embed(
                title="Error!",
                description="This command requires admin permissions. soz bb xoxo <3",
                color=0xE02B2B,
            )
            logger.warn(
                f"User {ctx.author} attempted to execute {ctx.application_command.qualified_name} without admin permissions."
            )
            return await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, commands.MissingPermissions):
            logger.warn(
                f"User {ctx.author} attempted to execute {ctx.application_command.qualified_name} without authorization."
            )
            embed = MissingPermissionsEmbed(ctx.author, error.missing_permissions)
            return await ctx.send(embed=embed, ephemeral=True)

        # that covers all the usual errors, so let's catch the rest
        # first work out if we've deferred the response so we can send an ephemeral message if we need to
        ctx_rtype = getattr(ctx.response, "_response_type", None)
        ctx_ephemeral = (
            True
            if (ctx_rtype == InteractionResponseType.deferred_channel_message)
            or (ctx_rtype == InteractionResponseType.deferred_message_update)
            else False
        )

        exc_text = "\n".join(format_exception(error, limit=2))
        exc_text = f"```\n{exc_text}\n```"
        embed = Embed(
            title="Error!",
            description=f"An unknown error occurred while executing this command.:\n{exc_text}",
            color=0xE02B2B,
        )
        embed.set_footer(text="sorry bb xoxo <3")
        await ctx.send(embed=embed, ephemeral=ctx_ephemeral, delete_after=30.0)

        logger.warn(f"Unhandled error in slash command {ctx}: {error}")
        raise error

    async def on_command_completion(self, ctx: commands.Context) -> None:
        """
        The code in this event is executed every time a normal command has been *successfully* executed
        :param ctx: The ctx of the command that has been executed.
        """
        full_command_name = ctx.command.qualified_name
        split = full_command_name.split(" ")
        executed_command = str(split[0])
        logger.info(
            f"Executed {executed_command} command in {ctx.guild.name} (ID: {ctx.message.guild.id}) by {ctx.message.author} (ID: {ctx.message.author.id})"
        )

    async def on_command_error(self, ctx: commands.Context, error) -> None:
        """
        The code in this event is executed every time a normal valid command catches an error
        :param ctx: The normal command that failed executing.
        :param error: The error that has been faced.
        """
        if isinstance(error, commands.CommandOnCooldown):
            logger.info(f"User {ctx.author} attempted to use {ctx.command.qualified_name} on cooldown.")
            embed = CooldownEmbed(error.retry_after + 1, ctx.author)
            return await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, exceptions.UserBlacklisted):
            logger.info(
                f"User {ctx.author} attempted to use {ctx.command.qualified_name}, but is blacklisted."
            )
            embed = Embed(
                title="Error!",
                description="You have been blacklisted and cannot use this bot. If you think this is a mistake, please contact the bot owner.",
                color=0xE02B2B,
            )
            return await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, exceptions.UserNotOwner):
            embed = Embed(
                title="Error!",
                description="This command requires admin permissions. soz bb xoxo <3",
                color=0xE02B2B,
            )
            logger.warn(
                f"User {ctx.author} attempted to execute {ctx.command.qualified_name} without authorization."
            )
            return await ctx.send(embed=embed, ephemeral=True)

        elif isinstance(error, commands.MissingPermissions):
            logger.warn(
                f"User {ctx.author} attempted to execute {ctx.command.qualified_name} without authorization."
            )
            embed = MissingPermissionsEmbed(ctx.author, error.missing_permissions)
            return await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.MissingRequiredArgument):
            logger.info(
                f"User {ctx.author} attempted to execute {ctx.command.qualified_name} without the required arguments"
            )
            embed = MissingRequiredArgumentEmbed(ctx.author, error.param.name)
            return await ctx.send(embed=embed)
        elif isinstance(error, commands.CommandNotFound):
            # This is actually fine so lets just pretend everything is okay.
            logger.info(
                f"User {ctx.author} attempted to execute a non-existent command: {ctx.message.content}"
            )
            return
        logger.warn(f"Unhandled error in command {ctx}: {error}")
        raise error

    @tasks.loop(minutes=1.5)
    async def status_task(self) -> None:
        """
        Set up the bot's status task
        """
        activity_type = getattr(ActivityType, self.config.status_type, ActivityType.playing)
        activity = Activity(name=random.choice(self.config.statuses), type=activity_type)
        await self.change_presence(activity=activity)

    @status_task.before_loop
    async def before_status_task(self) -> None:
        logger.info("waiting for ready... just to be sure")
        await self.wait_until_ready()
