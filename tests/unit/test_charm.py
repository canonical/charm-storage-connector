
"""Unit tests for ISCSI Connector charm."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import PropertyMock, call, mock_open, patch

import charm

from ops.framework import EventBase
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    """Charm Unit Tests."""

    def setUp(self):
        """Test setup."""
        self.tmp_iscsi_conf_path = Path(tempfile.mkdtemp())
        self.tmp_multipath_conf_dir = Path(tempfile.mkdtemp())
        self.harness = Harness(charm.StorageConnectorCharm)
        self.harness.set_leader(is_leader=True)
        self.harness.begin()

    def tearDown(self):
        """Remove testing artifacts."""
        shutil.rmtree(self.tmp_iscsi_conf_path)
        shutil.rmtree(self.tmp_multipath_conf_dir)

    @patch("charm.utils.is_container")
    def test_abort_if_host_is_container(self, m_is_container):
        """Test if charm stops when deployed on a container."""
        m_is_container.return_value = True
        self.assertFalse(self.harness.charm._stored.installed)
        self.harness.charm.on.install.emit()
        self.assertFalse(self.harness.charm._stored.installed)

    @patch("charm.subprocess.check_call")
    @patch("charm.subprocess.getoutput")
    @patch("charm.utils.is_container")
    @patch("charm.StorageConnectorCharm.MULTIPATH_CONF_PATH", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.MULTIPATH_CONF_DIR", new_callable=PropertyMock)
    @patch(
        "charm.StorageConnectorCharm.ISCSI_INITIATOR_NAME", new_callable=PropertyMock
    )
    @patch("charm.StorageConnectorCharm.ISCSI_CONF", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.ISCSI_CONF_PATH", new_callable=PropertyMock)
    def test_on_iscsi_install(self,
                              m_iscsi_conf_path,
                              m_iscsi_conf,
                              m_iscsi_initiator_name,
                              m_multipath_conf_dir,
                              m_multipath_conf_path,
                              m_is_container,
                              m_getoutput,
                              m_check_call):
        """Test installation."""
        m_is_container.return_value = False
        m_iscsi_conf_path.return_value = self.tmp_iscsi_conf_path
        m_iscsi_conf.return_value = self.tmp_iscsi_conf_path / 'iscsid.conf'
        m_iscsi_initiator_name.return_value = \
            self.tmp_iscsi_conf_path / 'initiatorname.iscsi'
        m_multipath_conf_dir.return_value = self.tmp_multipath_conf_dir
        m_multipath_conf_path.return_value = self.tmp_multipath_conf_dir / 'conf.d'
        m_getoutput.return_value = "iqn.2020-07.canonical.com:lun1"

        self.harness.update_config({
            "storage-type": "iscsi",
            "iscsi-target": "abc",
            "iscsi-port": "443",
            'multipath-devices': "{'a': 'b'}"
        })

        self.assertFalse(self.harness.charm._stored.installed)
        self.harness.charm.on.install.emit()

        self.assertTrue(os.path.exists(self.harness.charm.ISCSI_CONF))
        self.assertTrue(os.path.exists(self.harness.charm.MULTIPATH_CONF_PATH))
        m_getoutput.assert_called_with("/sbin/iscsi-iname")
        m_check_call.assert_has_calls(
            [
                call("systemctl restart iscsid".split()),
                call("systemctl restart open-iscsi".split()),
                call("iscsiadm -m discovery -t sendtargets -p abc:443".split()),
                call("iscsiadm -m node --login".split())
            ],
            any_order=False
        )
        self.assertTrue(self.harness.charm._stored.installed)

    @patch("charm.subprocess.getoutput")
    @patch("builtins.open", new_callable=mock_open)
    @patch("charm.utils.is_container")
    @patch("charm.StorageConnectorCharm.MULTIPATH_CONF_PATH", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.MULTIPATH_CONF_DIR", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.ISCSI_CONF", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.ISCSI_CONF_PATH", new_callable=PropertyMock)
    def test_on_fiberchannel_install(self,
                                     m_iscsi_conf_path,
                                     m_iscsi_conf,
                                     m_multipath_conf_dir,
                                     m_multipath_conf_path,
                                     m_is_container,
                                     m_open,
                                     m_getoutput):
        """Test installation."""
        m_is_container.return_value = False
        m_iscsi_conf_path.return_value = self.tmp_iscsi_conf_path
        m_iscsi_conf.return_value = self.tmp_iscsi_conf_path / "fc-iscsid.conf"
        m_multipath_conf_dir.return_value = self.tmp_multipath_conf_dir
        m_multipath_conf_path.return_value = self.tmp_multipath_conf_dir / "conf.d"
        m_getoutput.return_value = "host0"
        self.harness.update_config({
            "storage-type": "fc",
            "fc-lun-alias": "data1",
            'multipath-devices': "{'a': 'b'}"
        })

        self.assertFalse(self.harness.charm._stored.installed)
        self.harness.charm.on.install.emit()
        self.assertFalse(os.path.exists(self.harness.charm.ISCSI_CONF))
        self.assertTrue(os.path.exists(self.harness.charm.MULTIPATH_CONF_PATH))
        self.assertTrue(self.harness.charm._stored.installed)
        m_open.assert_called_once_with("/sys/class/scsi_host/host0/scan", "w")
        self.assertTrue(
            call(self.harness.charm.ISCSI_CONF, "w") not in m_open.mock_calls
        )

    def test_on_start(self):
        """Test on start hook."""
        self.assertFalse(self.harness.charm._stored.started)
        self.harness.charm.on.start.emit()
        # event deferred as charm not configured yet
        self.assertFalse(self.harness.charm._stored.started)
        # mock charm as configured
        self.harness.charm._stored.configured = True
        self.harness.charm.on.start.emit()
        self.assertTrue(self.harness.charm._stored.started)

    @patch("charm.subprocess.check_call")
    def test_on_restart_iscsi_services_action(self, m_check_call):
        """Test on restart action."""
        action_event = FakeActionEvent()
        m_check_call.return_value = True
        self.harness.charm.on_restart_iscsi_services_action(action_event)
        m_check_call.assert_has_calls(
            [
                call(["systemctl", "restart", "iscsid"]),
                call(["systemctl", "restart", "open-iscsi"])
            ],
            any_order=False
        )
        self.assertEqual(action_event.results['success'], 'True')

    @patch("charm.subprocess.check_call")
    def test_on_reload_multipathd_service_action(self, m_check_call):
        """Test on reload action."""
        action_event = FakeActionEvent()
        self.harness.charm.on_reload_multipathd_service_action(action_event)
        m_check_call.assert_called_once_with(["systemctl", "reload", "multipathd"])
        self.assertEqual(action_event.results['success'], 'True')

    @patch("metrics.uninstall_multipath_status_cronjob")
    @patch("metrics.install_multipath_status_cronjob")
    @patch("metrics.uninstall_exporter_snap")
    @patch("metrics.install_exporter_snap")
    def test_on_metrics_endpoint_handlers(
        self,
        m_install_exporter_snap,
        m_uninstall_exporter_snap,
        m_install_multipath_status_cronjob,
        m_uninstall_multipath_status_cronjob
    ):
        """Test the relation event handlers for metrics-endpoint."""
        rel_id = self.harness.add_relation("metrics-endpoint", "prometheus-k8s")
        m_install_exporter_snap.assert_called_once_with(
            self.harness.charm.model.resources
        )
        m_install_multipath_status_cronjob.assert_called_once()

        self.harness.remove_relation(rel_id)
        m_uninstall_exporter_snap.assert_called_once()
        m_uninstall_multipath_status_cronjob.assert_called_once()


class FakeActionEvent(EventBase):
    """Set a fake action class for unit tests mocking."""

    def __init__(self, params=None):
        """Class init."""
        super().__init__(None)
        if params is None:
            params = {}
        self.params = params

    def set_results(self, results):
        """Mock results."""
        self.results = results

    def log(self, log):
        """Mock logs."""
        self.log = log


if __name__ == "__main__":
    unittest.main()
