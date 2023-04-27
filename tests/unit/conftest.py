from unittest.mock import PropertyMock

import ops.testing
import pytest

from charm import StorageConnectorCharm


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
    # harness.begin()

    yield harness

    harness.cleanup()
