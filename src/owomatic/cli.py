import json
import logging
import sys
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import click
import daemonocle
import uvloop
from daemonocle.cli import DaemonCLI, pass_daemon
from daemonocle.helpers import FHSDaemon
from rich.pretty import install as install_pretty
from rich.traceback import install as install_traceback

import logsnake
from owomatic import COGDIR_PATH, CONFIG_PATH, DATADIR_PATH, LOG_FORMAT, LOGDIR_PATH
from owomatic.bot import Owomatic
from owomatic.helpers.misc import parse_log_level

MBYTE = 2**20

logfmt = logsnake.LogFormatter(fmt=LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
# setup root logger
logging.root = logsnake.setup_logger(
    level=logging.INFO,
    isRootLogger=True,
    formatter=logfmt,
    logfile=LOGDIR_PATH.joinpath(f"{__name__.split('.')[0]}-debug.log".replace("_", "-")),
    fileLoglevel=logging.DEBUG,
    maxBytes=1 * MBYTE,
    backupCount=3,
)
# setup package logger
logger = logsnake.setup_logger(
    level=logging.INFO,
    isRootLogger=False,
    name=__package__,
    formatter=logfmt,
    logfile=LOGDIR_PATH.joinpath(f"{__name__.split('.')[0]}.log".replace("_", "-")),
    fileLoglevel=logging.DEBUG,
    maxBytes=1 * MBYTE,
    backupCount=3,
)

# install rich traceback handler
install_pretty()
install_traceback(show_locals=True)

noisy_loggers = [
    "httpx",
    "disnake.gateway",
    "disnake.http",
    "disnake.client",
    "PIL.Image",
    "httpcore.http11",
]


def cb_shutdown(message: str, code: int):
    logger.warning(f"owomatic shutdown: {message} (code {code})")
    return code


class BotDaemon(FHSDaemon):
    @daemonocle.expose_action
    @click.argument("name")
    @click.pass_context
    def reload_cog(self, ctx: click.Context, name: str):
        """**BROKEN!** Unload a cog (if loaded) then load it."""
        bot = ctx.obj.bot if hasattr(ctx.obj, "bot") else None
        if bot is None:
            logger.error("Could not find bot instance")
            return

        cog_module = f"cogs.{name}"
        if cog_module in bot.extensions.keys():
            logger.warning(f"Found extension {name}, unloading...")
            bot.unload_extension(cog_module)

        avail_cogs = bot.available_cogs()
        if name not in avail_cogs:
            logger.error(f"Could not find module {name} in cog dir")
        bot.load_extension(cog_module)


@click.command(
    cls=DaemonCLI,
    daemon_class=BotDaemon,
    daemon_params={
        "name": "owomatic",
        "shutdown_callback": cb_shutdown,
        "prefix": CONFIG_PATH.parent.joinpath("daemon"),
        "log_prefix": "owomatic-",
        "stop_timeout": 60,
    },
)
@click.version_option(package_name="owomatic")
@pass_daemon
def cli(daemon: BotDaemon):
    """
    owomatic discord bot CLI service controller.

    pass --config <name> to use a specific configuration file / data dir suffix.
    """

    logger.info(f"Config path: {CONFIG_PATH}")
    logger.info(f"DATADIR_PATH: {DATADIR_PATH}")
    logger.info(f"LOGDIR_PATH: {LOGDIR_PATH}")
    logger.info(f"Daemon data path: {CONFIG_PATH.parent.joinpath('daemon')}")
    return start_bot(daemon)


def start_bot(daemon: BotDaemon, config_path: Optional[Path] = None):
    if not hasattr(daemon, "bot"):
        daemon.bot = Owomatic(config_path=config_path)

    bot: Owomatic = daemon.bot

    # have to use a different method on python 3.11 and up because of a change to how asyncio works
    # not sure how to implement that with disnake, so for now, no uvloop on python 3.11 and up
    if sys.version_info < (3, 11):
        logger.info("installing uvloop...")
        uvloop.install()

    logger.info("Starting owomatic")

    config_log_level = parse_log_level(bot.config.log_level)
    logger.setLevel(config_log_level)
    logger.info(f"Effective log level: {logging.getLevelName(logger.getEffectiveLevel())}")

    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.INFO)

    # create log and data directories if they don't exist
    if not DATADIR_PATH.exists():
        DATADIR_PATH.mkdir(parents=True)
    if not LOGDIR_PATH.exists():
        LOGDIR_PATH.mkdir(parents=True)

    cfg_dict = bot.config.dict()
    for key in cfg_dict:
        logger.debug(f"    {key}: {json.dumps(cfg_dict[key], default=str)}")

    bot.load_cogs()
    return bot.run(token=bot.config.bot_token, reconnect=True)
