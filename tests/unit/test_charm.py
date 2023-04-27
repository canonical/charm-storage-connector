"""Unit tests for ISCSI Connector charm."""
from unittest.mock import call, mock_open

import charmhelpers.contrib.openstack.deferred_events as deferred_events
from ops.framework import EventBase
from ops.model import ActiveStatus

import charm


def test_abort_if_host_is_container(harness, mocker):
    """Test if charm stops when deployed on a container."""
    mocker.patch("charm.utils.is_container", return_value=True)
    harness.begin_with_initial_hooks()
    assert not harness.charm._stored.installed


def test_on_iscsi_install(harness, mocker):
    """Test installation."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mock_getoutput = mocker.patch(
        "charm.subprocess.getoutput", return_value="iqn.2020-07.canonical.com:lun1"
    )
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    mock_check_output = mocker.patch("charm.subprocess.check_output")
    mock_configure_deferred_restarts = mocker.patch(
        "charm.StorageConnectorCharm._configure_deferred_restarts"
    )
    harness.update_config(
        {
            "storage-type": "iscsi",
            "iscsi-target": "abc",
            "iscsi-port": "443",
            "multipath-devices": "{'a': 'b'}",
        }
    )
    harness.begin_with_initial_hooks()

    assert harness.charm.ISCSI_CONF.is_file()
    assert harness.charm.MULTIPATH_CONF_PATH.is_dir()
    mock_getoutput.assert_any_call("/sbin/iscsi-iname")
    mock_check_call.assert_has_calls(
        [
            call("systemctl restart iscsid".split()),
            call("systemctl restart open-iscsi".split()),
            call("iscsiadm -m discovery -t sendtargets -p abc:443".split()),
        ],
        any_order=False,
    )
    mock_check_output.assert_has_calls(
        [call("iscsiadm -m node --login".split(), stderr=-2)], any_order=False
    )
    mock_configure_deferred_restarts.assert_called_once()
    assert harness.charm._stored.installed


def test_on_fiberchannel_install(harness, mocker):
    """Test installation."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mock_configure_deferred_restarts = mocker.patch(
        "charm.StorageConnectorCharm._configure_deferred_restarts"
    )
    mocker.patch("charm.subprocess.getoutput", return_value="host0")
    mock_builtin_open = mocker.patch("builtins.open", new_callable=mock_open)
    harness.update_config(
        {"storage-type": "fc", "fc-lun-alias": "data1", "multipath-devices": "{'a': 'b'}"}
    )
    harness.begin_with_initial_hooks()

    assert not harness.charm.ISCSI_CONF.exists()
    assert harness.charm.MULTIPATH_CONF_PATH.is_dir()
    assert harness.charm._stored.installed
    mock_builtin_open.assert_called_once_with(
        "/sys/class/scsi_host/host0/scan", "w", encoding="utf-8"
    )
    mock_configure_deferred_restarts.assert_called_once()
    assert call(harness.charm.ISCSI_CONF, "w") not in mock_builtin_open.mock_calls


def test_on_start(harness):
    """Test on start hook."""
    harness.begin()
    assert not harness.charm._stored.started
    harness.charm.on.start.emit()
    # event deferred as charm not configured yet
    assert not harness.charm._stored.started
    # mock charm as configured
    harness.charm._stored.configured = True
    harness.charm.on.start.emit()
    assert harness.charm._stored.started


def test_on_restart_services_action_mutually_exclusive_params(harness):
    """Test on restart servcices action with both deferred-only and services."""
    action_event = FakeActionEvent(params={"deferred-only": True, "services": "test_service"})
    harness.begin()
    harness.charm._on_restart_services_action(action_event)
    assert action_event.results["failed"] == "deferred-only and services are mutually exclusive"


def test_on_restart_services_action_no_params(harness):
    """Test on restart servcices action with no param."""
    action_event = FakeActionEvent(params={"deferred-only": False, "services": ""})
    harness.begin()
    harness.charm._on_restart_services_action(action_event)
    assert action_event.results["failed"] == "Please specify either deferred-only or services"


def test_on_restart_services_action_deferred_only_failed(harness, mocker):
    """Test on restart servcices action empty list of deferred restarts."""
    mocker.patch("charm.subprocess.check_call")
    mocker.patch("charm.deferred_events.get_deferred_restarts", return_value=[])
    action_event = FakeActionEvent(params={"deferred-only": True, "services": ""})
    harness.begin()
    harness.charm._on_restart_services_action(action_event)
    assert action_event.results["failed"] == "No deferred services to restart"


def test_on_restart_services_action_deferred_only_success(harness, mocker):
    """Test on restart servcices action with deferred only param."""
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    mocker.patch("charm.deferred_events.check_restart_timestamps")
    mocker.patch(
        "charm.deferred_events.get_deferred_restarts",
        return_value=[
            deferred_events.ServiceEvent(
                timestamp=123456,
                service="svc",
                reason="Reason",
                action="restart",
                policy_requestor_name="myapp",
                policy_requestor_type="charm",
            )
        ],
    )
    action_event = FakeActionEvent(params={"deferred-only": True, "services": ""})
    harness.begin()
    harness.charm._on_restart_services_action(action_event)
    mock_check_call.assert_has_calls([call(["systemctl", "restart", "svc"])], any_order=False)
    assert action_event.results["success"] == "True"


def test_on_restart_services_action_services_failed(harness):
    """Test on restart servcices action failed with invalid service input."""
    action_event = FakeActionEvent(
        params={"deferred-only": False, "services": "non_valid_service"}
    )
    harness.begin()
    harness.charm._on_restart_services_action(action_event)
    assert action_event.results["failed"] == "No valid services are specified."


def test_on_restart_services_action_services_success(harness, mocker):
    """Test on restart servcices action successfully run with services param."""
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    mock_iscsi_discovery_and_login = mocker.patch(
        "charm.StorageConnectorCharm._iscsi_discovery_and_login"
    )
    action_event = FakeActionEvent(
        params={"deferred-only": False, "services": "iscsid open-iscsi multipathd"}
    )
    harness.begin()
    harness.charm._on_restart_services_action(action_event)
    mock_check_call.assert_has_calls(
        [
            call(["systemctl", "restart", "iscsid"]),
            call(["systemctl", "restart", "open-iscsi"]),
            call(["systemctl", "restart", "multipathd"]),
        ],
        any_order=True,
    )
    assert action_event.results["success"] == "True"
    mock_iscsi_discovery_and_login.assert_called_once()


def test_on_show_deferred_restarts_action(harness, mocker):
    """Test on show deferred restarts action."""
    mocker.patch(
        "charm.deferred_events.get_deferred_restarts",
        return_value=[
            deferred_events.ServiceEvent(
                timestamp=123456,
                service="svc",
                reason="Reason",
                action="restart",
                policy_requestor_name="myapp",
                policy_requestor_type="charm",
            )
        ],
    )
    action_event = FakeActionEvent()
    harness.begin()
    harness.charm._on_show_deferred_restarts_action(action_event)
    assert (
        action_event.results["deferred-restarts"]
        == "- 1970-01-02 10:17:36 +0000 UTC svc" + "                                      Reason\n"
    )


def test_on_reload_multipathd_service_action(harness, mocker):
    """Test on reload multipathd action."""
    action_event = FakeActionEvent()
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    harness.begin()
    harness.charm._on_reload_multipathd_service_action(action_event)
    mock_check_call.assert_called_once_with(["systemctl", "reload", "multipathd"])
    assert action_event.results["success"] == "True"


def test_on_iscsi_discovery_and_login_action(harness, mocker):
    """Test on iscsi discovery and login action."""
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    mock_check_output = mocker.patch("charm.subprocess.check_output")
    action_event = FakeActionEvent()
    harness.update_config({"iscsi-target": "abc", "iscsi-port": "443"})
    harness.begin()
    harness.charm._on_iscsi_discovery_and_login_action(action_event)

    mock_check_call.assert_has_calls(
        [
            call(["iscsiadm", "-m", "discovery", "-t", "sendtargets", "-p", "abc" + ":" + "443"]),
        ],
        any_order=False,
    )
    mock_check_output.assert_has_calls(
        [call(["iscsiadm", "-m", "node", "--login"], stderr=-2)], any_order=False
    )
    assert action_event.results["success"] == "True"


def test_get_status_message(harness, mocker):
    """Test on setting active status with correct status message."""
    mock_get_deferred_restarts = mocker.patch(
        "charm.deferred_events.get_deferred_restarts", return_value=[]
    )
    harness.begin()
    assert harness.charm.get_status_message() == "Unit is ready"

    mock_get_deferred_restarts.return_value = [
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

    assert harness.charm.get_status_message() == "Unit is ready. Services queued for restart: svc2"


def test_check_deferred_restarts_queue(harness, mocker):
    """Test check_deferred_restarts_queue decorator function."""
    mock_check_restart_timestamps = mocker.patch("charm.deferred_events.check_restart_timestamps")
    mocker.patch(
        "charm.deferred_events.get_deferred_restarts",
        return_value=[
            deferred_events.ServiceEvent(
                timestamp=234567,
                service="svc",
                reason="Reason",
                action="restart",
                policy_requestor_name="storage-connector",
                policy_requestor_type="charm",
            )
        ],
    )
    harness.begin()
    harness.charm.unit.status = ActiveStatus("Unit is ready")

    # Trigger decorator function by emitting update_status event
    harness.charm.on.update_status.emit()

    mock_check_restart_timestamps.assert_called_once()
    assert harness.charm.unit.status == ActiveStatus(
        "Unit is ready. Services queued for restart: svc"
    )


def test_configure_deferred_restarts(harness, mocker):
    """Test on setting up deferred restarts in policy-rc.d."""
    mock_install_policy_rcd = mocker.patch("charm.policy_rcd.install_policy_rcd")
    mock_remove_policy_file = mocker.patch("charm.policy_rcd.remove_policy_file")
    mock_add_policy_block = mocker.patch("charm.policy_rcd.add_policy_block")
    mock_chmod = mocker.patch("charm.os.chmod")

    harness.update_config({"enable-auto-restarts": True})
    harness.begin()
    harness.charm._configure_deferred_restarts()

    mock_install_policy_rcd.assert_called_once()
    mock_remove_policy_file.assert_called_once()
    mock_chmod.assert_called_once()

    harness.update_config({"enable-auto-restarts": False})
    harness.charm._configure_deferred_restarts()
    mock_add_policy_block.assert_has_calls(
        [
            call("iscsid", ["stop", "restart", "try-restart"]),
            call("open-iscsi", ["stop", "restart", "try-restart"]),
        ],
        any_order=False,
    )


def test_on_restart_non_iscsi_services(harness, mocker):
    """Test on restarting non-iscsi services."""
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    mock_iscsi_discovery_and_login = mocker.patch(
        "charm.StorageConnectorCharm._iscsi_discovery_and_login"
    )
    harness.begin()
    harness.charm._restart_services(services=["multipathd"])
    mock_check_call.assert_has_calls(
        [call(["systemctl", "restart", "multipathd"])], any_order=True
    )
    mock_iscsi_discovery_and_login.assert_not_called()


def test_on_restart_iscsi_services_with_discovery_login(harness, mocker):
    """Test on restarting a iscsi service with discovery and login."""
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    mock_iscsi_discovery_and_login = mocker.patch(
        "charm.StorageConnectorCharm._iscsi_discovery_and_login"
    )
    harness.update_config({"iscsi-discovery-and-login": True})
    harness.begin()
    harness.charm._restart_services(services=["iscsid"])
    mock_check_call.assert_has_calls([call(["systemctl", "restart", "iscsid"])], any_order=True)
    mock_iscsi_discovery_and_login.assert_called_once()


def test_on_restart_iscsi_services_without_discovery_login(harness, mocker):
    """Test on restarting a iscsi service without running discovery and login."""
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    mock_iscsi_discovery_and_login = mocker.patch(
        "charm.StorageConnectorCharm._iscsi_discovery_and_login"
    )
    harness.update_config({"iscsi-discovery-and-login": False})
    harness.begin()
    harness.charm._restart_services(services=["iscsid"])
    mock_check_call.assert_has_calls([call(["systemctl", "restart", "iscsid"])], any_order=True)
    mock_iscsi_discovery_and_login.assert_not_called()


def test_iscsiadm_discovery_failed(harness, mocker):
    """Test response to iscsiadm discovery failure."""
    mock_log_exception = mocker.patch("charm.logging.exception")
    mocker.patch("charm.subprocess.check_output")
    mocker.patch(
        "charm.subprocess.check_call",
        side_effect=charm.subprocess.CalledProcessError(
            returncode=15,
            cmd=["iscsiadm", "-m", "discovery", "-t", "sendtargets", "-p", "abc" + ":" + "443"],
        ),
    )

    harness.update_config({"storage-type": "iscsi", "iscsi-target": "abc", "iscsi-port": "443"})
    harness.begin()
    harness.charm.unit.status = ActiveStatus("Unit is ready")
    harness.charm._iscsi_discovery_and_login()
    mock_log_exception.assert_called_once()


def test_iscsiadm_login_failed(harness, mocker):
    """Test response to iscsiadm login failure."""
    mock_log_exception = mocker.patch("charm.logging.exception")
    mocker.patch("charm.subprocess.check_output")
    mocker.patch(
        "charm.subprocess.check_call",
        side_effect=charm.subprocess.CalledProcessError(
            returncode=15,
            cmd=["iscsiadm", "-m", "node", "--login"],
            output=b"iscsiadm: Could not log into all portals",
        ),
    )
    harness.update_config({"storage-type": "iscsi", "iscsi-target": "abc", "iscsi-port": "443"})
    harness.begin()
    harness.charm.unit.status = ActiveStatus("Unit is ready")
    harness.charm._iscsi_discovery_and_login()
    mock_log_exception.assert_called_once()


def test_on_metrics_endpoint_handlers(harness, mocker):
    """Test the relation event handlers for metrics-endpoint."""
    mock_install_exporter = mocker.patch("storage_connector.metrics_utils.install_exporter")
    mock_uninstall_exporter = mocker.patch("storage_connector.metrics_utils.uninstall_exporter")

    harness.begin()
    rel_id = harness.add_relation("metrics-endpoint", "prometheus-k8s")
    mock_install_exporter.assert_called_once_with(harness.charm.model.resources)

    harness.remove_relation(rel_id)
    mock_uninstall_exporter.assert_called_once()


def test_on_nrpe_external_master_handlers(harness, mocker):
    """Test the relation event handlers for nrpe-external-master."""
    mock_install_exporter = mocker.patch("storage_connector.metrics_utils.install_exporter")
    mock_uninstall_exporter = mocker.patch("storage_connector.metrics_utils.uninstall_exporter")
    mock_unsync_nrpe_files = mocker.patch("storage_connector.nrpe_utils.unsync_nrpe_files")

    harness.begin()
    rel_id = harness.add_relation("nrpe-external-master", "nrpe")
    mock_install_exporter.assert_called_once_with(harness.charm.model.resources)

    harness.remove_relation(rel_id)
    mock_uninstall_exporter.assert_called_once()
    mock_unsync_nrpe_files.assert_called_once()


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
