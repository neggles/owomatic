import json
import logging
import os
import platform
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import partial as partial_func
from pathlib import Path
from traceback import print_exception
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
    Member,
    Status,
)
from disnake import __version__ as DISNAKE_VERSION
from disnake.ext import commands, tasks
from humanize import naturaldelta as fuzzydelta

import exceptions
from owomatic import COGDIR_PATH, DATADIR_PATH, USERDATA_PATH
from owomatic.embeds import CooldownEmbed, MissingPermissionsEmbed
from owomatic.helpers.misc import get_package_root

PACKAGE_ROOT = get_package_root()

BOT_INTENTS = Intents.default()
BOT_INTENTS.typing = False
BOT_INTENTS.members = False
BOT_INTENTS.presences = False
BOT_INTENTS.message_content = True


logger = logging.getLogger(__package__)


class Owomatic(commands.Bot):
    def __init__(self, *args, **kwargs):
        command_prefix = kwargs.pop("command_prefix", commands.when_mentioned)
        intents = kwargs.pop("intents", BOT_INTENTS)

        super().__init__(*args, command_prefix=command_prefix, intents=intents, **kwargs)

        # attributes set up in cli.py. this is a dumb way to do this but it works
        self.config: dict = None
        self.timezone: ZoneInfo = None
        self.datadir_path: Path = DATADIR_PATH
        self.userdata_path: Path = USERDATA_PATH
        self.userdata: dict = None
        self.cogdir_path: Path = COGDIR_PATH
        self.start_time: datetime = datetime.now(tz=ZoneInfo("UTC"))
        self.home_guild: Guild = None  # set in on_ready
        self.hide: bool = False

    @property
    def uptime(self) -> timedelta:
        return datetime.now(tz=ZoneInfo("UTC")) - self.start_time

    @property
    def fuzzyuptime(self) -> str:
        return fuzzydelta(self.uptime)

    def available_cogs(self):
        cogs = [
            f.stem
            for f in self.cogdir_path.glob("*.py")
            if f.stem != "template" and not f.stem.endswith("_wip")
        ]
        if isinstance(self.config.get("disable_cogs", None), list):
            cogs = [x for x in cogs if x not in self.config["disable_cogs"]]
        return cogs

    def load_cogs(self):
        cogs = self.available_cogs()
        if cogs:
            for cog in cogs:
                try:
                    self.load_extension(f"cogs.{cog}")
                    logger.info(f"Loaded cog '{cog}'")
                except Exception:
                    etype, exc, tb = sys.exc_info()
                    exception = f"{etype}: {exc}"
                    logger.error(f"Failed to load cog {cog}:\n{exception}")
                    print_exception(etype, exc, tb)
        else:
            logger.info("No cogs found")

    @tasks.loop(minutes=1.0)
    async def status_task(self) -> None:
        """
        Set up the bot's status task
        """
        statuses = self.config["statuses"]
        activity = Activity(name=random.choice(statuses), type=ActivityType.playing)
        await self.change_presence(activity=activity)

    @status_task.before_loop
    async def before_status_task(self):
        if self.hide is True:
            # no status task if we're hiding
            await self.change_presence(status=Status.invisible)
            self.status_task.cancel()
        else:
            print("waiting...")
            await self.wait_until_ready()

    async def on_ready(self) -> None:
        """
        The code in this even is executed when the bot is ready
        """
        logger.info(f"Logged in as {self.user.name}")
        logger.info(f"disnake API version: {DISNAKE_VERSION}")
        logger.info(f"Python version: {platform.python_version()}")
        logger.info(f"Running on: {platform.system()} {platform.release()} ({os.name})")
        logger.info("-------------------")
        if self.home_guild is None:
            if self.config.get("home_guild_id", None) is None:
                logger.error("No home guild found, please specify one in config.json")
            else:
                logger.info("Saving home guild metadata to disk")
                self.home_guild = self.get_guild(self.config.get("home_guild_id", None))
                self.save_guild_metadata(self.home_guild.id)

        if self.hide is False:
            if not self.status_task.is_running():
                self.status_task.start()
        else:
            await self.change_presence(status=Status.invisible)

    async def on_message(self, message: Message) -> None:
        if message.author == self.user or message.author.bot:
            return
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

        embed = Embed(
            title="Error!",
            description="An unknown error occurred while executing this command. Please try again later or contact the bot owner if the problem persists.",
            color=0xE02B2B,
        )
        await ctx.send(embed=embed, ephemeral=ctx_ephemeral)

        logger.warn(f"Unhandled error in slash command {ctx}: {error}")
        raise error
