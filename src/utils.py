"""Utils functions copied from charmhelpers library."""

import os
import subprocess

SYSTEMD_SYSTEM = '/run/systemd/system'
UPSTART_CONTAINER_TYPE = '/run/container_type'


def is_container():
    """Determine whether unit is running in a container.

    @return: boolean indicating if unit is in a container
    """
    if init_is_systemd():
        # Detect using systemd-detect-virt
        return subprocess.call(['systemd-detect-virt',
                                '--container']) == 0
    else:
        # Detect using upstart container file marker
        return os.path.exists(UPSTART_CONTAINER_TYPE)


def init_is_systemd(service_name=None):
    """Return whether the host uses systemd for the specified service.

    @param Optional[str] service_name: specific name of service
    """
    if str(service_name).startswith("snap."):
        return True
    if lsb_release()['DISTRIB_CODENAME'] == 'trusty':
        return False
    return os.path.isdir(SYSTEMD_SYSTEM)


def lsb_release():
    """Return /etc/os-release in a dict."""
    d = {}
    with open('/etc/os-release', 'r') as lsb:
        for line in lsb:
            s = line.split('=')
            if len(s) != 2:
                continue
            d[s[0].strip()] = s[1].strip()
    return d
