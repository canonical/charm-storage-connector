"""Utility functions related to metrics-endpoint relation.

These functions are intended to help exposing the metrics gathered from
the system via the help of the prometheus-iscsi-exporter snap package.

The snap package is expecting the output of the "multipath -ll" command
that is run against the live system, in the $SNAP_DATA/multipath path.
Which is expanded to /var/snap/prometheus-iscsi-exporter/current/multipath.

The snap package is not running the command itself since it is installed in
a confined environment by design and will need to install its own copy of
the multipath-tools package but work it against the system directories which
is outide of it confinement. To overcome this, we are installing a cronjob
that will run on the system and redirect the output to $SNAP_DATA/multipath
for the exporter to consume/export.

There is one caveat with this design though. The cronjob is set to run every
minute, which coincidentally the default scrape interval for prometheus unless
specified otherwise. This means that scrape interval shorter than 1 min will
have no effect since the cronjob is running every minute.
"""
import logging
from pathlib import Path

from ops.model import ModelError

from charms.operator_libs_linux.v1 import snap  # noqa

logger = logging.getLogger(__name__)


EXPORTER_SNAP_NAME = "prometheus-iscsi-exporter"
CRON_SCRIPT_PATH = Path("/etc/cron.d/multipath")
CRON_SCRIPT_OUTPUT_PATH = Path(
    f"/var/snap/{EXPORTER_SNAP_NAME}/current/multipath"
)


def install_multipath_status_cronjob():
    """Install the cronjob to run multipath -ll every minute."""
    # crond expects newline before EOF or else it ignores the script
    CRON_SCRIPT_PATH.write_text(
        f"* * * * * root multipath -ll > {str(CRON_SCRIPT_OUTPUT_PATH)}\n"
    )
    CRON_SCRIPT_PATH.chmod(mode=0o644)


def uninstall_multipath_status_cronjob():
    """Uninstall the cronjob."""
    CRON_SCRIPT_PATH.unlink(missing_ok=True)
    CRON_SCRIPT_OUTPUT_PATH.unlink(missing_ok=True)


def install_exporter_snap(resources):
    """Install the prometheus-iscsi-exporter snap."""
    try:
        snap_resource = resources.fetch(EXPORTER_SNAP_NAME)
    except ModelError:
        snap_resource = None

    if snap_resource and Path(snap_resource).stat().st_size != 0:
        logger.info("Installing snap from local resource")
        snap.install_local(snap_resource, dangerous=True)
    else:
        logger.info("Installing snap from snap store")
        snap.add(EXPORTER_SNAP_NAME)

    logger.info("Installed snap successfully")


def uninstall_exporter_snap():
    """Uninstall the prometheus-iscsi-exporter snap."""
    logger.info("Removing snap")
    snap.remove(EXPORTER_SNAP_NAME)


def install_exporter(resources):
    """Install exporter and cronjob."""
    install_exporter_snap(resources)
    install_multipath_status_cronjob()


def uninstall_exporter():
    """Uninstall exporter and cronjob."""
    uninstall_exporter_snap()
    uninstall_multipath_status_cronjob()
