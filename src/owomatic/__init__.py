try:
    from ._version import (
        version as __version__,
        version_tuple,
    )
except ImportError:
    __version__ = "unknown (no version information available)"
    version_tuple = (0, 0, "unknown", "noinfo")

from owomatic.helpers.misc import get_package_root

LOG_FORMAT = "%(color)s[%(levelname)1.1s %(asctime)s][%(name)s][%(module)s:%(funcName)s:%(lineno)d]%(end_color)s %(message)s"

PACKAGE = __package__.replace("_", "-")
PACKAGE_ROOT = get_package_root()

COGDIR_PATH = PACKAGE_ROOT.joinpath("cogs")
LOGDIR_PATH = PACKAGE_ROOT.parent.joinpath("logs")
DATADIR_PATH = PACKAGE_ROOT.parent.joinpath("data")

CONFIG_PATH = DATADIR_PATH.joinpath("config.json")
BLACKLIST_PATH = DATADIR_PATH.joinpath("blacklist.json")
MISCDATA_PATH = DATADIR_PATH.joinpath("misc")
