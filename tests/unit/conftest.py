from textwrap import dedent
from unittest.mock import PropertyMock

import ops.testing
import pytest

from charm import StorageConnectorCharm


@pytest.fixture
def multipath_topology():
    """Return an example output of the "multipath -ll" command."""
    return dedent(
        r"""diskname (360014380056efd060000d00000510000) dm-3 Vendor,StorageModel
            [size=1.0G][features=1 queue_if_no_path][hwhandler=0][rw]
            \_ round-robin 0 [prio=100][active]
            \_ 0:0:0:1 sda 8:0   [active][ready]
            \_ 1:0:1:1 sdd 8:48  [active][ready]
            \_ round-robin 0 [prio=20][enabled]
            \_ 0:0:1:1 sdb 8:16  [active][ready]
            \_ 1:0:0:1 sdc 8:32  [active][ready]"""
    )


@pytest.fixture
def iscsi_config():
    return {
        "storage-type": "iscsi",
        "iscsi-target": "abc",
        "iscsi-port": "443",
        "multipath-defaults": '{"user_friendly_names": "yes"}',
        "multipath-devices": '{"vendor":"PURE","product": "FlashArray","fast_io_fail_tmo": "10", "path_grouping_policy":"group_by_prio"}',  # noqa
        "multipath-blacklist": '{"vendor": "QEMU", "product": "*"}',
        "fc-lun-alias": "data1",
        "initiator-dictionary": '{"testhost.testdomain": "iqn.2020-07.canonical.com:lun1"}',
    }


@pytest.fixture
def fc_config():
    return {
        "storage-type": "fc",
        "multipath-defaults": '{"user_friendly_names": "yes"}',
        "multipath-devices": '{"vendor":"PURE","product": "FlashArray","fast_io_fail_tmo": "10", "path_grouping_policy":"group_by_prio"}',  # noqa
        "multipath-blacklist": '{"vendor": "QEMU", "product": "*"}',
        "fc-lun-alias": "data1",
    }


@pytest.fixture
def harness(mocker, tmp_path):
    multipath_conf_dir = tmp_path / "multipath"
    iscsi_conf_path = tmp_path / "iscsi"

    multipath_conf_dir.mkdir()
    iscsi_conf_path.mkdir()

    mocker.patch(
        "charm.StorageConnectorCharm.MULTIPATH_CONF_DIR",
        new_callable=PropertyMock,
        return_value=multipath_conf_dir,
    )
    mocker.patch(
        "charm.StorageConnectorCharm.MULTIPATH_CONF_PATH",
        new_callable=PropertyMock,
        return_value=multipath_conf_dir / "conf.d",
    )
    mocker.patch(
        "charm.StorageConnectorCharm.ISCSI_CONF_PATH",
        new_callable=PropertyMock,
        return_value=iscsi_conf_path,
    )
    mocker.patch(
        "charm.StorageConnectorCharm.ISCSI_CONF",
        new_callable=PropertyMock,
        return_value=iscsi_conf_path / "iscsid.conf",
    )
    mocker.patch(
        "charm.StorageConnectorCharm.ISCSI_INITIATOR_NAME",
        new_callable=PropertyMock,
        return_value=iscsi_conf_path / "initiatorname.iscsi",
    )

    ops.testing.SIMULATE_CAN_CONNECT = True
    harness = ops.testing.Harness(StorageConnectorCharm)
    harness.set_leader(is_leader=True)
    harness.begin()

    yield harness

    harness.cleanup()
