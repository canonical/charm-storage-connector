"""Utility functions related to nrpe-external-master relation."""
import logging
import shutil
from pathlib import Path

from charmhelpers.contrib.charmsupport.nrpe import NRPE
from charmhelpers.core.hookenv import charm_dir
from charmhelpers.core.host import rsync

from charms.operator_libs_linux.v0 import passwd

logger = logging.getLogger(__name__)

NAGIOS_PLUGINS_DIR_PATH = Path(
    "/usr/local/lib/nagios/plugins"
)

CHECK_SCRIPT_SRC_RELATIVE_PATH = Path(
    "files/check_iscsi_metric.py"
)

CHECK_SCRIPT_DST_ABSOLUTE_PATH = \
    NAGIOS_PLUGINS_DIR_PATH / CHECK_SCRIPT_SRC_RELATIVE_PATH.name


def create_nagios_user():
    """Create nagios user."""
    nagios_home = Path("/var/lib/nagios")
    passwd.add_user(
        "nagios",
        home_dir=nagios_home,
        system_user=True,
        shell="/usr/sbin/nologin"
    )
    if not nagios_home.exists():
        nagios_home.mkdir(parents=True, exist_ok=True)
    shutil.chown(nagios_home, user="nagios", group="nagios")


def remove_nagios_user():
    """Remove nagios user."""
    return passwd.remove_user("nagios", remove_home=True)


def sync_nrpe_files():
    """Copy the nrpe check to the filesystem."""
    NAGIOS_PLUGINS_DIR_PATH.mkdir(parents=True, exist_ok=True)
    rsync(
        str(Path(charm_dir()) / CHECK_SCRIPT_SRC_RELATIVE_PATH),
        str(CHECK_SCRIPT_DST_ABSOLUTE_PATH)
    )
    CHECK_SCRIPT_DST_ABSOLUTE_PATH.chmod(mode=0o755)


def unsync_nrpe_files():
    """Remove the nrpe files from the filesystem."""
    CHECK_SCRIPT_DST_ABSOLUTE_PATH.unlink(missing_ok=True)


def update_nrpe_config(charm_config):
    """Update the nrpe configuration."""
    sync_nrpe_files()
    nrpe_compat = NRPE(primary=False)
    nrpe_compat.add_check(
        shortname="multipath",
        description="Check multipath path count",
        check_cmd="{} -n {}".format(
            CHECK_SCRIPT_DST_ABSOLUTE_PATH,
            charm_config.get("nagios_multipath_paths_per_volume")
        )
    )
    nrpe_compat.write()
