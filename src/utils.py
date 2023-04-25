"""Utils functions copied from charmhelpers library."""

import os
import subprocess
from typing import Optional

SYSTEMD_SYSTEM = '/run/systemd/system'
UPSTART_CONTAINER_TYPE = '/run/container_type'


def is_container() -> bool:
    """Determine whether unit is running in a container.

    @return: boolean indicating if unit is in a container
    """
    if init_is_systemd():
        # Detect using systemd-detect-virt
        return subprocess.call(['systemd-detect-virt',
                                '--container']) == 0
    # Detect using upstart container file marker
    return os.path.exists(UPSTART_CONTAINER_TYPE)


def init_is_systemd(service_name: Optional[str] = None) -> bool:
    """Return whether the host uses systemd for the specified service.

    @param Optional[str] service_name: specific name of service
    """
    if str(service_name).startswith("snap."):
        return True
    return os.path.isdir(SYSTEMD_SYSTEM)
