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
from os import stat
from pathlib import Path

from ops.model import ModelError

from charms.operator_libs_linux.v1 import snap  # noqa

logger = logging.getLogger(__name__)


class Configuration:
    """Module level configuration."""

    exporter_snap_name = "prometheus-iscsi-exporter"
    cron_script_path = Path("/etc/cron.d/multipath")
    cron_script_output_path = Path(
        f"/var/snap/{exporter_snap_name}/current/multipath"
    )


def install_multipath_status_cronjob():
    """Install the cronjob to run multipath -ll every minute."""
    # crond expects newline before EOF or else it ignores the script
    Configuration.cron_script_path.write_text(
        f"* * * * * root multipath -ll > {str(Configuration.cron_script_output_path)}\n"
    )
    Configuration.cron_script_path.chmod(mode=0o644)


def uninstall_multipath_status_cronjob():
    """Uninstall the cronjob."""
    Configuration.cron_script_path.unlink(missing_ok=True)
    Configuration.cron_script_output_path.unlink(missing_ok=True)


def install_exporter_snap(resources):
    """Install the prometheus-iscsi-exporter snap."""
    try:
        snap_resource = resources.fetch(Configuration.exporter_snap_name)
    except ModelError:
        snap_resource = None

    if snap_resource and stat(snap_resource).st_size != 0:
        logger.info("Installing snap from local resource")
        snap.install_local(snap_resource, dangerous=True)
    else:
        logger.info("Installing snap from snap store")
        snap.add(Configuration.exporter_snap_name)

    logger.info("Installed snap successfully")


def uninstall_exporter_snap():
    """Uninstall the prometheus-iscsi-exporter snap."""
    logger.info("Removing snap")
    snap.remove(Configuration.exporter_snap_name)
