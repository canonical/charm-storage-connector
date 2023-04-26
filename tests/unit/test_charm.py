"""Unit tests for ISCSI Connector charm."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import PropertyMock, call, mock_open, patch

import charmhelpers.contrib.openstack.deferred_events as deferred_events
from ops.framework import EventBase
from ops.model import ActiveStatus
from ops.testing import Harness

import charm


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

    @patch("storage_connector.nrpe_utils.update_nrpe_config")
    @patch("charm.subprocess.check_call")
    @patch("charm.subprocess.check_output")
    @patch("charm.subprocess.getoutput")
    @patch("charm.utils.is_container")
    @patch("charm.StorageConnectorCharm.MULTIPATH_CONF_PATH", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.MULTIPATH_CONF_DIR", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.ISCSI_INITIATOR_NAME", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.ISCSI_CONF", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.ISCSI_CONF_PATH", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm._configure_deferred_restarts")
    def test_on_iscsi_install(
        self,
        m_configure_deferred_restarts,
        m_iscsi_conf_path,
        m_iscsi_conf,
        m_iscsi_initiator_name,
        m_multipath_conf_dir,
        m_multipath_conf_path,
        m_is_container,
        m_getoutput,
        m_check_output,
        m_check_call,
        _,
    ):
        """Test installation."""
        m_is_container.return_value = False
        m_iscsi_conf_path.return_value = self.tmp_iscsi_conf_path
        m_iscsi_conf.return_value = self.tmp_iscsi_conf_path / "iscsid.conf"
        m_iscsi_initiator_name.return_value = self.tmp_iscsi_conf_path / "initiatorname.iscsi"
        m_multipath_conf_dir.return_value = self.tmp_multipath_conf_dir
        m_multipath_conf_path.return_value = self.tmp_multipath_conf_dir / "conf.d"
        m_getoutput.return_value = "iqn.2020-07.canonical.com:lun1"

        self.harness.update_config(
            {
                "storage-type": "iscsi",
                "iscsi-target": "abc",
                "iscsi-port": "443",
                "multipath-devices": "{'a': 'b'}",
            }
        )

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
            ],
            any_order=False,
        )
        m_check_output.assert_has_calls(
            [call("iscsiadm -m node --login".split(), stderr=-2)], any_order=False
        )
        m_configure_deferred_restarts.assert_called_once()
        self.assertTrue(self.harness.charm._stored.installed)

    @patch("storage_connector.nrpe_utils.update_nrpe_config")
    @patch("charm.subprocess.getoutput")
    @patch("builtins.open", new_callable=mock_open)
    @patch("charm.utils.is_container")
    @patch("charm.StorageConnectorCharm.MULTIPATH_CONF_PATH", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.MULTIPATH_CONF_DIR", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.ISCSI_CONF", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm.ISCSI_CONF_PATH", new_callable=PropertyMock)
    @patch("charm.StorageConnectorCharm._configure_deferred_restarts")
    def test_on_fiberchannel_install(
        self,
        m_configure_deferred_restarts,
        m_iscsi_conf_path,
        m_iscsi_conf,
        m_multipath_conf_dir,
        m_multipath_conf_path,
        m_is_container,
        m_open,
        m_getoutput,
        _,
    ):
        """Test installation."""
        m_is_container.return_value = False
        m_iscsi_conf_path.return_value = self.tmp_iscsi_conf_path
        m_iscsi_conf.return_value = self.tmp_iscsi_conf_path / "fc-iscsid.conf"
        m_multipath_conf_dir.return_value = self.tmp_multipath_conf_dir
        m_multipath_conf_path.return_value = self.tmp_multipath_conf_dir / "conf.d"
        m_getoutput.return_value = "host0"
        self.harness.update_config(
            {"storage-type": "fc", "fc-lun-alias": "data1", "multipath-devices": "{'a': 'b'}"}
        )

        self.assertFalse(self.harness.charm._stored.installed)
        self.harness.charm.on.install.emit()
        self.assertFalse(os.path.exists(self.harness.charm.ISCSI_CONF))
        self.assertTrue(os.path.exists(self.harness.charm.MULTIPATH_CONF_PATH))
        self.assertTrue(self.harness.charm._stored.installed)
        m_open.assert_called_once_with("/sys/class/scsi_host/host0/scan", "w", encoding="utf-8")
        m_configure_deferred_restarts.assert_called_once()
        self.assertTrue(call(self.harness.charm.ISCSI_CONF, "w") not in m_open.mock_calls)

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

    def test_on_restart_services_action_mutually_exclusive_params(self):
        """Test on restart servcices action with both deferred-only and services."""
        action_event = FakeActionEvent(params={"deferred-only": True, "services": "test_service"})
        self.harness.charm._on_restart_services_action(action_event)
        self.assertEqual(
            action_event.results["failed"], "deferred-only and services are mutually exclusive"
        )

    def test_on_restart_services_action_no_params(self):
        """Test on restart servcices action with no param."""
        action_event = FakeActionEvent(params={"deferred-only": False, "services": ""})
        self.harness.charm._on_restart_services_action(action_event)
        self.assertEqual(
            action_event.results["failed"], "Please specify either deferred-only or services"
        )

    @patch("charm.subprocess.check_call")
    @patch("charm.deferred_events.get_deferred_restarts")
    @patch("charm.deferred_events.check_restart_timestamps")
    def test_on_restart_services_action_deferred_only_failed(
        self, m_check_rtimestamps, m_get_deferred_restarts, m_check_call
    ):
        """Test on restart servcices action empty list of deferred restarts."""
        m_get_deferred_restarts.return_value = []
        action_event = FakeActionEvent(params={"deferred-only": True, "services": ""})
        self.harness.charm._on_restart_services_action(action_event)
        self.assertEqual(action_event.results["failed"], "No deferred services to restart")

    @patch("charm.subprocess.check_call")
    @patch("charm.deferred_events.get_deferred_restarts")
    @patch("charm.deferred_events.check_restart_timestamps")
    def test_on_restart_services_action_deferred_only_success(
        self, m_check_rtimestamps, m_get_deferred_restarts, m_check_call
    ):
        """Test on restart servcices action with deferred only param."""
        m_get_deferred_restarts.return_value = [
            deferred_events.ServiceEvent(
                timestamp=123456,
                service="svc",
                reason="Reason",
                action="restart",
                policy_requestor_name="myapp",
                policy_requestor_type="charm",
            )
        ]
        action_event = FakeActionEvent(params={"deferred-only": True, "services": ""})
        self.harness.charm._on_restart_services_action(action_event)
        m_check_call.assert_has_calls([call(["systemctl", "restart", "svc"])], any_order=False)
        self.assertEqual(action_event.results["success"], "True")

    def test_on_restart_services_action_services_failed(self):
        """Test on restart servcices action failed with invalid service input."""
        action_event = FakeActionEvent(
            params={"deferred-only": False, "services": "non_valid_service"}
        )
        self.harness.charm._on_restart_services_action(action_event)
        self.assertEqual(action_event.results["failed"], "No valid services are specified.")

    @patch("charm.subprocess.check_call")
    @patch("charm.StorageConnectorCharm._iscsi_discovery_and_login")
    def test_on_restart_services_action_services_success(
        self, m_iscsi_discovery_and_login, m_check_call
    ):
        """Test on restart servcices action successfully run with services param."""
        action_event = FakeActionEvent(
            params={"deferred-only": False, "services": "iscsid open-iscsi multipathd"}
        )
        self.harness.charm._on_restart_services_action(action_event)
        m_check_call.assert_has_calls(
            [
                call(["systemctl", "restart", "iscsid"]),
                call(["systemctl", "restart", "open-iscsi"]),
                call(["systemctl", "restart", "multipathd"]),
            ],
            any_order=True,
        )
        self.assertEqual(action_event.results["success"], "True")
        m_iscsi_discovery_and_login.assert_called_once()

    @patch("charm.deferred_events.get_deferred_restarts")
    def test_on_show_deferred_restarts_action(self, m_get_deferred_restarts):
        """Test on show deferred restarts action."""
        m_get_deferred_restarts.return_value = [
            deferred_events.ServiceEvent(
                timestamp=123456,
                service="svc",
                reason="Reason",
                action="restart",
                policy_requestor_name="myapp",
                policy_requestor_type="charm",
            )
        ]

        action_event = FakeActionEvent()
        self.harness.charm._on_show_deferred_restarts_action(action_event)
        self.assertEqual(
            action_event.results["deferred-restarts"],
            "- 1970-01-02 10:17:36 +0000 UTC svc"
            + "                                      Reason\n",
        )

    @patch("charm.subprocess.check_call")
    def test_on_reload_multipathd_service_action(self, m_check_call):
        """Test on reload multipathd action."""
        action_event = FakeActionEvent()
        self.harness.charm._on_reload_multipathd_service_action(action_event)
        m_check_call.assert_called_once_with(["systemctl", "reload", "multipathd"])
        self.assertEqual(action_event.results["success"], "True")

    @patch("charm.subprocess.check_call")
    @patch("charm.subprocess.check_output")
    def test_on_iscsi_discovery_and_login_action(self, m_check_output, m_check_call):
        """Test on iscsi discovery and login action."""
        self.harness.update_config({"iscsi-target": "abc", "iscsi-port": "443"})
        action_event = FakeActionEvent()
        self.harness.charm._on_iscsi_discovery_and_login_action(action_event)

        m_check_call.assert_has_calls(
            [
                call(
                    ["iscsiadm", "-m", "discovery", "-t", "sendtargets", "-p", "abc" + ":" + "443"]
                ),
            ],
            any_order=False,
        )
        m_check_output.assert_has_calls(
            [call(["iscsiadm", "-m", "node", "--login"], stderr=-2)], any_order=False
        )
        self.assertEqual(action_event.results["success"], "True")

    @patch("charm.deferred_events.get_deferred_restarts")
    def test_get_status_message(self, m_get_deferred_restarts):
        """Test on setting active status with correct status message."""
        m_get_deferred_restarts.return_value = []
        self.assertEqual(self.harness.charm.get_status_message(), "Unit is ready")

        m_get_deferred_restarts.return_value = [
            deferred_events.ServiceEvent(
                timestamp=123456,
                service="svc1",
                reason="Reason1",
                action="restart",
                policy_requestor_name="other_app",
                policy_requestor_type="charm",
            ),
            deferred_events.ServiceEvent(
                timestamp=234567,
                service="svc2",
                reason="Reason2",
                action="restart",
                policy_requestor_name="storage-connector",
                policy_requestor_type="charm",
            ),
        ]
        self.assertEqual(
            self.harness.charm.get_status_message(),
            "Unit is ready. Services queued for restart: svc2",
        )

    @patch("charm.deferred_events.check_restart_timestamps")
    @patch("charm.deferred_events.get_deferred_restarts")
    def test_check_deferred_restarts_queue(
        self, m_get_deferred_restarts, m_check_restart_timestamps
    ):
        """Test check_deferred_restarts_queue decorator function."""
        self.harness.charm.unit.status = ActiveStatus("Unit is ready")
        m_get_deferred_restarts.return_value = [
            deferred_events.ServiceEvent(
                timestamp=234567,
                service="svc",
                reason="Reason",
                action="restart",
                policy_requestor_name="storage-connector",
                policy_requestor_type="charm",
            )
        ]

        # Trigger decorator function by emitting update_status event
        self.harness.charm.on.update_status.emit()

        m_check_restart_timestamps.assert_called_once()
        self.assertEqual(
            self.harness.charm.unit.status,
            ActiveStatus("Unit is ready. Services queued for restart: svc"),
        )

    @patch("charm.policy_rcd.install_policy_rcd")
    @patch("charm.policy_rcd.remove_policy_file")
    @patch("charm.policy_rcd.add_policy_block")
    @patch("charm.os.chmod")
    def test_configure_deferred_restarts(
        self, m_chmod, m_add_policy_block, m_remove_policy_file, install_policy_rcd
    ):
        """Test on setting up deferred restarts in policy-rc.d."""
        self.harness.update_config({"enable-auto-restarts": True})
        self.harness.charm._configure_deferred_restarts()
        install_policy_rcd.assert_called_once()
        m_remove_policy_file.assert_called_once()
        m_chmod.assert_called_once()

        self.harness.update_config({"enable-auto-restarts": False})
        self.harness.charm._configure_deferred_restarts()
        m_add_policy_block.assert_has_calls(
            [
                call("iscsid", ["stop", "restart", "try-restart"]),
                call("open-iscsi", ["stop", "restart", "try-restart"]),
            ],
            any_order=False,
        )

    @patch("charm.subprocess.check_call")
    @patch("charm.StorageConnectorCharm._iscsi_discovery_and_login")
    def test_on_restart_non_iscsi_services(self, m_iscsi_discovery_and_login, m_check_call):
        """Test on restarting non-iscsi services."""
        self.harness.charm._restart_services(services=["multipathd"])
        m_check_call.assert_has_calls(
            [call(["systemctl", "restart", "multipathd"])], any_order=True
        )
        m_iscsi_discovery_and_login.assert_not_called()

    @patch("charm.subprocess.check_call")
    @patch("charm.StorageConnectorCharm._iscsi_discovery_and_login")
    def test_on_restart_iscsi_services_with_discovery_login(
        self, m_iscsi_discovery_and_login, m_check_call
    ):
        """Test on restarting a iscsi service with discovery and login."""
        self.harness.update_config({"iscsi-discovery-and-login": True})
        self.harness.charm._restart_services(services=["iscsid"])
        m_check_call.assert_has_calls([call(["systemctl", "restart", "iscsid"])], any_order=True)
        m_iscsi_discovery_and_login.assert_called_once()

    @patch("charm.subprocess.check_call")
    @patch("charm.StorageConnectorCharm._iscsi_discovery_and_login")
    def test_on_restart_iscsi_services_without_discovery_login(
        self, m_iscsi_discovery_and_login, m_check_call
    ):
        """Test on restarting a iscsi service without running discovery and login."""
        self.harness.update_config({"iscsi-discovery-and-login": False})
        self.harness.charm._restart_services(services=["iscsid"])
        m_check_call.assert_has_calls([call(["systemctl", "restart", "iscsid"])], any_order=True)
        m_iscsi_discovery_and_login.assert_not_called()

    @patch("charm.subprocess.check_output")
    @patch("charm.subprocess.check_call")
    @patch("charm.logging.exception")
    def test_iscsiadm_discovery_failed(self, m_log_exception, m_check_call, m_check_output):
        """Test response to iscsiadm discovery failure."""
        self.harness.update_config(
            {"storage-type": "iscsi", "iscsi-target": "abc", "iscsi-port": "443"}
        )
        self.harness.charm.unit.status = ActiveStatus("Unit is ready")
        m_check_call.side_effect = charm.subprocess.CalledProcessError(
            returncode=15,
            cmd=["iscsiadm", "-m", "discovery", "-t", "sendtargets", "-p", "abc" + ":" + "443"],
        )
        self.harness.charm._iscsi_discovery_and_login()
        m_log_exception.assert_called_once()

    @patch("charm.subprocess.check_output")
    @patch("charm.subprocess.check_call")
    @patch("charm.logging.exception")
    def test_iscsiadm_login_failed(self, m_log_exception, m_check_call, m_check_output):
        """Test response to iscsiadm login failure."""
        self.harness.update_config(
            {"storage-type": "iscsi", "iscsi-target": "abc", "iscsi-port": "443"}
        )
        self.harness.charm.unit.status = ActiveStatus("Unit is ready")
        m_check_output.side_effect = charm.subprocess.CalledProcessError(
            returncode=15,
            cmd=["iscsiadm", "-m", "node", "--login"],
            output=b"iscsiadm: Could not log into all portals",
        )
        self.harness.charm._iscsi_discovery_and_login()
        m_log_exception.assert_called_once()

    @patch("storage_connector.metrics_utils.uninstall_exporter")
    @patch("storage_connector.metrics_utils.install_exporter")
    def test_on_metrics_endpoint_handlers(self, m_install_exporter, m_uninstall_exporter):
        """Test the relation event handlers for metrics-endpoint."""
        rel_id = self.harness.add_relation("metrics-endpoint", "prometheus-k8s")
        m_install_exporter.assert_called_once_with(self.harness.charm.model.resources)

        self.harness.remove_relation(rel_id)
        m_uninstall_exporter.assert_called_once()

    @patch("storage_connector.metrics_utils.uninstall_exporter")
    @patch("storage_connector.metrics_utils.install_exporter")
    @patch("storage_connector.nrpe_utils.unsync_nrpe_files")
    def test_on_nrpe_external_master_handlers(
        self,
        m_unsync_nrpe_files,
        m_install_exporter,
        m_uninstall_exporter,
    ):
        """Test the relation event handlers for nrpe-external-master."""
        rel_id = self.harness.add_relation("nrpe-external-master", "nrpe")
        m_install_exporter.assert_called_once_with(self.harness.charm.model.resources)

        self.harness.remove_relation(rel_id)
        m_uninstall_exporter.assert_called_once()
        m_unsync_nrpe_files.assert_called_once()


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
