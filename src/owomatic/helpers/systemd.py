from enum import Enum
from os import getgid, getuid
from pathlib import Path
from sysconfig import get_path

from owomatic import DAEMON_PATH, PACKAGE_ROOT

UNIT_TEMPLATE = """
[Unit]
Description={package_name} discord bot
After=network.target network-online.target
Wants=network-online.target

[Service]
Restart={restart_policy}
Type=simple

User={exec_uid}
Group={exec_gid}
WorkingDirectory={work_dir}
PIDFile={daemon_path}/run/{package_name}.pid

Environment=VIRTUAL_ENV={env_root}
Environment=PATH={env_bin}:${{PATH}}
ExecStart={env_bin}/{package_name} start
ExecStop={env_bin}/{package_name} stop
ExecReload={env_bin}/{package_name} restart

[Install]
WantedBy=multi-user.target
"""


class RestartPolicy(str, Enum):
    Always = "always"
    OnSuccess = "on-success"
    OnFailure = "on-failure"
    OnAbnormal = "on-abnormal"
    OnAbort = "on-abort"
    OnWatchdog = "on-watchdog"


def service_unit(
    package_name: str = "owomatic",
    restart_policy: RestartPolicy = RestartPolicy.OnFailure,
) -> str:
    return UNIT_TEMPLATE.format(
        package_name=package_name,
        restart_policy=restart_policy,
        exec_uid=getuid(),
        exec_gid=getgid(),
        work_dir=PACKAGE_ROOT.parent,
        daemon_path=DAEMON_PATH,
        env_root=Path(get_path("data")),
        env_bin=Path(get_path("scripts")),
    ).lstrip()


__all__ = [
    "UNIT_TEMPLATE",
    "RestartPolicy",
    "service_unit",
]
