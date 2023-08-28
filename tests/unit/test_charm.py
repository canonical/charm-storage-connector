"""Unit tests for the storage-connector charm."""
import subprocess
import sys
from textwrap import dedent
from unittest.mock import call, mock_open

import charmhelpers.contrib.openstack.deferred_events as deferred_events
from ops.framework import EventBase
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

import charm


def test_on_install_aborts_if_host_is_container(harness, mocker):
    """Test if charm stops when deployed on a container."""
    mocker.patch("charm.utils.is_container", return_value=True)
    harness.charm.on.install.emit()
    assert not harness.charm._stored.installed


def test_on_install(harness, mocker, iscsi_config):
    """Test install event handler."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    harness.disable_hooks()
    harness.update_config(iscsi_config)
    harness.enable_hooks()
    harness.charm.on.install.emit()
    mock_check_call.assert_has_calls(
        [call("systemctl enable iscsid".split()), call("systemctl enable open-iscsi".split())],
        any_order=False,
    )
    assert harness.charm._stored.installed
    assert harness.charm._stored.storage_type == "iscsi"
    assert harness.charm.unit.status == MaintenanceStatus("Install complete")


def test_on_install_apt_marks_missing_packages_for_install(harness, mocker, iscsi_config):
    """Test if apt marks missing packages for installation during install handler."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mocker.patch("charm.subprocess.check_call")
    mock_pkg = sys.modules["apt"].cache.Cache.return_value.__getitem__.return_value
    mock_pkg.is_installed = False

    harness.disable_hooks()
    harness.update_config(iscsi_config)
    harness.enable_hooks()
    harness.charm.on.install.emit()

    mock_pkg.mark_install.assert_called_once()


def test_on_config_changes_aborts_if_host_is_container(harness, mocker):
    """Test if charm stops when deployed on a container."""
    mocker.patch("charm.utils.is_container", return_value=True)
    harness.charm.on.config_changed.emit()
    assert not harness.charm._stored.configured
    assert not harness.charm._stored.started


def test_on_config_changed_iscsi(harness, mocker, iscsi_config):
    """Test config changed handler for iscsi configuration."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mocker.patch("charm.subprocess.getoutput", return_value="iqn.2020-07.canonical.com:lun1")
    mocker.patch("charm.socket.getfqdn", return_value="testhost.testdomain")
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    mock_check_output = mocker.patch("charm.subprocess.check_output")
    mock_configure_deferred_restarts = mocker.patch(
        "charm.StorageConnectorCharm._configure_deferred_restarts"
    )
    mock_write_text = mocker.patch("charm.Path.write_text")
    mock_chmod = mocker.patch("charm.Path.chmod")
    expected_iscsi_conf_content = dedent(
        """\
        ###############################################################################
        # [ WARNING ]
        # configuration file maintained by Juju
        # local changes will be overwritten.
        ###############################################################################
        iscsid.startup = /bin/systemctl start iscsid.socket
        node.startup = automatic
        node.leading_login = No
        node.session.timeo.replacement_timeout = 120
        node.conn[0].timeo.login_timeout = 15
        node.conn[0].timeo.logout_timeout = 15
        node.conn[0].timeo.noop_out_interval = 5
        node.conn[0].timeo.noop_out_timeout = 5
        node.session.err_timeo.abort_timeout = 15
        node.session.err_timeo.lu_reset_timeout = 30
        node.session.err_timeo.tgt_reset_timeout = 30
        node.session.initial_login_retry_max = 8
        node.session.cmds_max = 128
        node.session.queue_depth = 32
        node.session.xmit_thread_priority = -20
        node.session.iscsi.InitialR2T = No
        node.session.iscsi.ImmediateData = Yes
        node.session.iscsi.FirstBurstLength = 262144
        node.session.iscsi.MaxBurstLength = 16776192
        node.conn[0].iscsi.MaxRecvDataSegmentLength = 262144
        node.conn[0].iscsi.MaxXmitDataSegmentLength = 0
        discovery.sendtargets.iscsi.MaxRecvDataSegmentLength = 32768
        node.session.nr_sessions = 1
        node.session.iscsi.FastAbort = Yes
        node.session.scan = auto
        """
    )
    expected_initiator_content = dedent(
        """\
        ###############################################################################
        # [ WARNING ]
        # configuration file maintained by Juju
        # local changes will be overwritten.
        #
        # DO NOT EDIT OR REMOVE THIS FILE!
        # If you remove this file, the iSCSI daemon will not start.
        # If you change the InitiatorName, existing access control lists
        # may reject this initiator.  The InitiatorName must be unique
        # for each iSCSI initiator.  Do NOT duplicate iSCSI InitiatorNames.
        ###############################################################################
        InitiatorName=iqn.2020-07.canonical.com:lun1"""
    )
    expected_multipath_content = (
        "###############################################################################\n"
        "# [ WARNING ]\n"
        "# configuration file maintained by Juju\n"
        "# local changes will be overwritten.\n"
        "###############################################################################\n"
        "defaults {\n"
        '     user_friendly_names "yes"\n'
        "    \n"
        "}\n"
        "blacklist {\n"
        "    device {\n"
        '         vendor "QEMU"\n'
        '         product "*"\n'
        "        \n"
        "    }\n"
        "}\n"
        "devices {\n"
        "    device {\n"
        '         vendor "PURE"\n'
        '         product "FlashArray"\n'
        '         fast_io_fail_tmo "10"\n'
        '         path_grouping_policy "group_by_prio"\n'
        "        \n"
        "    }\n"
        "}\n"
    )

    harness.charm._stored.installed = True
    harness.update_config(iscsi_config)

    assert harness.charm.ISCSI_CONF_PATH.is_dir()
    assert harness.charm.MULTIPATH_CONF_PATH.is_dir()
    assert harness.charm.MULTIPATH_CONF_DIR.is_dir()
    mock_check_call.assert_has_calls(
        [
            call("systemctl restart iscsid".split()),
            call("systemctl restart open-iscsi".split()),
            call("iscsiadm -m discovery -t sendtargets -p abc:443".split()),
            call("systemctl reload multipathd".split()),
        ],
        any_order=False,
    )
    mock_check_output.assert_has_calls(
        [call("iscsiadm -m node --login".split(), stderr=-2)], any_order=False
    )
    mock_configure_deferred_restarts.assert_called_once()
    mock_write_text.assert_has_calls(
        [
            call(expected_initiator_content),
            call(expected_iscsi_conf_content),
            call(expected_multipath_content),
        ]
    )
    mock_chmod.assert_has_calls([call(0o600), call(0o600)])
    assert harness.charm._stored.installed
    assert harness.charm._stored.configured
    assert harness.charm._stored.started
    assert harness.charm._stored.storage_type == "iscsi"
    assert isinstance(harness.charm.unit.status, ActiveStatus)


def test_on_config_changed_iscsi_defers_restart(harness, mocker, iscsi_config):
    """Test config changed handler defers restart."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mocker.patch("charm.subprocess.getoutput", return_value="iqn.2020-07.canonical.com:lun1")
    mocker.patch("charm.socket.getfqdn", return_value="testhost.testdomain")
    mocker.patch("charm.subprocess.check_call")
    mocker.patch("charm.subprocess.check_output")
    mocker.patch("charm.StorageConnectorCharm._configure_deferred_restarts")
    mocker.patch("charm.Path.write_text")
    mocker.patch("charm.Path.chmod")

    mocker.patch("charm.time.time", return_value=1234)
    mocker.patch("charm.deferred_events.save_event")
    mock_service_event = mocker.patch("charm.deferred_events.ServiceEvent")

    harness.charm._stored.installed = True
    harness.update_config(iscsi_config)
    harness.update_config({"enable-auto-restarts": False})

    assert harness.charm._stored.installed
    assert harness.charm._stored.configured
    assert harness.charm._stored.started
    assert harness.charm._stored.storage_type == "iscsi"
    assert isinstance(harness.charm.unit.status, ActiveStatus)

    mock_service_event.assert_has_calls(
        [
            call(
                timestamp=1234,
                service="iscsid",
                reason="Charm event: config changed",
                action="restart",
            ),
            call(
                timestamp=1234,
                service="open-iscsi",
                reason="Charm event: config changed",
                action="restart",
            ),
        ]
    )


def test_on_config_changed_blocks_upon_invalid_multipath_config(harness, mocker, iscsi_config):
    """Test config changed handler blocks the charm in case of invalid mp config."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mocker.patch("charm.socket.getfqdn", return_value="testhost.testdomain")
    mocker.patch("charm.subprocess.check_call")
    mocker.patch("charm.subprocess.check_output")
    mocker.patch("charm.StorageConnectorCharm._configure_deferred_restarts")
    mocker.patch(
        "charm.subprocess.getoutput",
        return_value="multipath.conf line 18, invalid keyword: user_friendly_name",
    )
    harness.update_config(iscsi_config)
    harness.charm._stored.installed = True
    harness.charm.on.config_changed.emit()
    assert harness.charm.unit.status == BlockedStatus(
        "Multipath conf error: ['invalid keyword: user_friendly_name']"
    )


def test_on_config_changed_exception_logged_upon_iscsi_login_failure(
    harness, mocker, iscsi_config
):
    """Test config changed handler logs exception upon iscsi login failure."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mocker.patch("charm.subprocess.getoutput", return_value="")
    mocker.patch("charm.socket.getfqdn", return_value="testhost.testdomain")
    mocker.patch("charm.subprocess.check_call")
    mock_exception = mocker.patch("charm.logging.exception")
    mock_check_output = mocker.patch(
        "charm.subprocess.check_output",
        side_effect=subprocess.CalledProcessError(returncode=1, cmd=[""], output=b"testoutput"),
    )
    mocker.patch("charm.StorageConnectorCharm._configure_deferred_restarts")
    harness.charm._stored.installed = True
    harness.update_config(iscsi_config)
    mock_check_output.assert_called_once_with(
        ["iscsiadm", "-m", "node", "--login"], stderr=subprocess.STDOUT
    )
    mock_exception.assert_called_once_with("Iscsi login failed. \n%s", "testoutput")


def test_on_config_changed_random_iqn(harness, mocker, iscsi_config):
    """Test config changed handler creates random iqn."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mocker.patch("charm.socket.getfqdn", return_value="foo")
    mocker.patch("charm.subprocess.check_call")
    mocker.patch("charm.subprocess.check_output")
    mocker.patch("charm.StorageConnectorCharm._configure_deferred_restarts")
    mock_getoutput = mocker.patch("charm.subprocess.getoutput", return_value="somehost")
    harness.charm._stored.installed = True
    harness.update_config(iscsi_config)
    assert call("/sbin/iscsi-iname") in mock_getoutput.mock_calls


def test_on_config_changed_blocks_upon_missing_config(harness, mocker, iscsi_config):
    """Test if config changed handler blocks the charm upon missing mandatory config."""
    mocker.patch("charm.utils.is_container", return_value=False)
    harness.charm._stored.installed = True
    del iscsi_config["multipath-devices"]
    harness.update_config(iscsi_config)
    assert harness.charm.unit.status == BlockedStatus(
        "Missing mandatory configuration option(s) ['multipath-devices']"
    )


def test_on_config_changed_blocks_upon_storage_type_change_after_deployment(
    harness, mocker, iscsi_config
):
    """Test config changed handler blocks the charm upon storage type change after deployment."""
    mocker.patch("charm.utils.is_container", return_value=False)
    harness.charm._stored.installed = True
    harness.charm._stored.storage_type = "fc"
    harness.update_config(iscsi_config)
    assert harness.charm.unit.status == BlockedStatus(
        "Storage type cannot be changed after deployment."
    )


def test_on_config_changed_logs_exception_upon_reload_multipathd_service_fails(
    harness, mocker, iscsi_config
):
    """Test config changed handler logs exception upon mp service reload failure."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mocker.patch("charm.subprocess.getoutput", return_value="")
    mocker.patch("charm.socket.getfqdn", return_value="testhost.testdomain")
    mocker.patch("charm.subprocess.check_output")
    mocker.patch("charm.StorageConnectorCharm._configure_deferred_restarts")
    mocker.patch(
        "charm.subprocess.check_call",
        side_effect=[
            None,
            None,
            None,
            subprocess.CalledProcessError(returncode=1, cmd=["systemctl", "reload", "multipathd"]),
        ],
    )
    mock_exception = mocker.patch("charm.logging.exception")
    harness.charm._stored.installed = True
    harness.update_config(iscsi_config)
    mock_exception.assert_called_once_with(
        "%s", "An error occured while reloading the multipathd service."
    )


def test_on_config_changed_logs_exception_upon_service_restart_fails(
    harness, mocker, iscsi_config
):
    """Test config changed handler logs exception upon service restart failure."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mocker.patch("charm.subprocess.getoutput", return_value="")
    mocker.patch("charm.socket.getfqdn", return_value="testhost.testdomain")
    mocker.patch("charm.subprocess.check_output")
    mocker.patch("charm.StorageConnectorCharm._configure_deferred_restarts")
    mocker.patch(
        "charm.subprocess.check_call",
        side_effect=[
            subprocess.CalledProcessError(returncode=1, cmd=["systemctl", "restart", "iscsid"]),
            None,
            None,
            None,
        ],
    )
    mock_exception = mocker.patch("charm.logging.exception")
    harness.charm._stored.installed = True
    harness.update_config(iscsi_config)
    mock_exception.assert_called_once_with("An error occured while restarting %s.", "iscsid")


def test_on_config_changed_fc(harness, mocker, fc_config, multipath_topology):
    """Test config changed handler for fibrechannel configuration."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mock_configure_deferred_restarts = mocker.patch(
        "charm.StorageConnectorCharm._configure_deferred_restarts"
    )
    mock_builtin_open = mocker.patch("charm.open", new_callable=mock_open)
    mock_write_text = mocker.patch("charm.Path.write_text")
    mock_chmod = mocker.patch("charm.Path.chmod")
    mocker.patch(
        "charm.subprocess.getoutput",
        side_effect=[
            "host0",
            multipath_topology,
            multipath_topology,
        ],
    )
    expected_multipath_conf = (
        "###############################################################################\n"
        "# [ WARNING ]\n"
        "# configuration file maintained by Juju\n"
        "# local changes will be overwritten.\n"
        "###############################################################################\n"
        "defaults {\n"
        '     user_friendly_names "yes"\n'
        "    \n"
        "}\n"
        "blacklist {\n"
        "    device {\n"
        '         vendor "QEMU"\n'
        '         product "*"\n'
        "        \n"
        "    }\n"
        "}\n"
        "devices {\n"
        "    device {\n"
        '         vendor "PURE"\n'
        '         product "FlashArray"\n'
        '         fast_io_fail_tmo "10"\n'
        '         path_grouping_policy "group_by_prio"\n'
        "        \n"
        "    }\n"
        "}\n"
        "multipaths {\n"
        "    multipath {\n"
        '         wwid "360014380056efd060000d00000510000"\n'
        '         alias "data1"\n'
        "        \n"
        "    }\n"
        "}\n"
    )
    harness.charm._stored.installed = True
    harness.update_config(fc_config)

    assert harness.charm._stored.installed
    assert harness.charm._stored.configured
    assert harness.charm._stored.fc_scan_ran_once
    assert harness.charm._stored.storage_type == "fc"
    assert isinstance(harness.charm.unit.status, ActiveStatus)
    mock_write_text.assert_called_once_with(expected_multipath_conf)
    mock_chmod.assert_called_once_with(0o600)
    mock_configure_deferred_restarts.assert_called_once()
    mock_builtin_open.assert_called_once_with(
        "/sys/class/scsi_host/host0/scan", "w", encoding="utf-8"
    )


def test_on_config_changed_fc_blocks_upon_io_error(harness, mocker, fc_config, multipath_topology):
    """Test config changed handler blocks the charm upon io error during fc scan."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mocker.patch("charm.open", side_effect=OSError)
    mocker.patch(
        "charm.subprocess.getoutput",
        side_effect=["host0", multipath_topology, multipath_topology],
    )

    harness.charm._stored.installed = True
    harness.update_config(fc_config)

    assert harness.charm._stored.installed
    assert not harness.charm._stored.configured
    assert not harness.charm._stored.fc_scan_ran_once
    assert harness.charm.unit.status == BlockedStatus(
        "Scan of the HBA adapters failed on the host."
    )


def test_on_config_changed_fc_blocks_upon_no_scsi_hosts(harness, mocker, fc_config):
    """Test config changed handler blocks the charm if there are no scsi hosts."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mock_getoutput = mocker.patch("charm.subprocess.getoutput", return_value="")

    harness.charm._stored.installed = True
    harness.update_config(fc_config)

    assert harness.charm._stored.installed
    assert not harness.charm._stored.configured
    assert not harness.charm._stored.fc_scan_ran_once
    assert harness.charm.unit.status == BlockedStatus("No scsi devices were found. Scan aborted")
    mock_getoutput.assert_called_once_with("ls /sys/class/scsi_host")


def test_on_config_changed_fc_blocks_upon_no_wwid(harness, mocker, fc_config):
    """Test config changed handler blocks the charm upon no wwid is found."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mocker.patch("charm.open", new_callable=mock_open)
    mocker.patch("charm.StorageConnectorCharm._configure_deferred_restarts")
    mock_getoutput = mocker.patch("charm.subprocess.getoutput", return_value="host0")

    harness.charm._stored.installed = True
    harness.update_config(fc_config)

    assert harness.charm._stored.installed
    assert not harness.charm._stored.configured
    assert not harness.charm._stored.started
    assert harness.charm._stored.fc_scan_ran_once
    assert harness.charm.unit.status == BlockedStatus(
        "No WWID was found. Please check multipath status and logs."
    )
    assert call("multipath -ll") in mock_getoutput.mock_calls


def test_on_config_change_blocks_upon_bad_multipath_config(
    harness, mocker, fc_config, multipath_topology
):
    """Test config changed handler blocks the charm upon bad multipath configuration."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mocker.patch("charm.open", new_callable=mock_open)
    mocker.patch("charm.StorageConnectorCharm._configure_deferred_restarts")
    mocker.patch(
        "charm.subprocess.getoutput",
        side_effect=["host0", multipath_topology, multipath_topology],
    )
    fc_config["multipath-devices"] = "}}}"
    harness.charm._stored.installed = True
    harness.update_config(fc_config)

    assert harness.charm._stored.installed
    assert not harness.charm._stored.configured
    assert not harness.charm._stored.started
    assert harness.charm._stored.fc_scan_ran_once
    assert harness.charm.unit.status == BlockedStatus(
        "Exception occured during the multipath                         "
        "configuration. Please check logs."
    )


def test_on_install_blocks_for_invalid_storage_types(harness, mocker):
    """Test installation gets blocked for invalid storage types."""
    mocker.patch("charm.utils.is_container", return_value=False)
    harness.update_config({"storage-type": "foo"})
    harness.charm.on.install.emit()
    assert not harness.charm._stored.installed


def test_on_install_logs_exception_upon_service_enable_fails(harness, mocker, iscsi_config):
    """Test exception is logged during install if service enable fails."""
    mocker.patch("charm.utils.is_container", return_value=False)
    mock_log_exception = mocker.patch("charm.logging.exception")
    mocker.patch(
        "charm.subprocess.check_call",
        side_effect=subprocess.CalledProcessError(returncode=-1, cmd=[""]),
    )
    harness.disable_hooks()
    harness.update_config(iscsi_config)
    harness.enable_hooks()
    harness.charm.on.install.emit()
    mock_log_exception.assert_has_calls(
        [
            call("Failed to enable %s.", "iscsid"),
            call("Failed to enable %s.", "open-iscsi"),
        ],
        any_order=False,
    )


def test_on_start(harness):
    """Test on start hook."""
    assert not harness.charm._stored.started
    harness.charm.on.start.emit()
    # event deferred as charm not configured yet
    assert not harness.charm._stored.started
    # mock charm as configured
    harness.charm._stored.configured = True
    harness.charm.on.start.emit()
    assert harness.charm._stored.started


def test_retrieve_multipath_wwid(harness, mocker, multipath_topology):
    mock_getoutput = mocker.patch(
        "charm.subprocess.getoutput",
        return_value=multipath_topology,
    )
    wwid = harness.charm._retrieve_multipath_wwid()
    mock_getoutput.assert_called_once_with("multipath -ll")
    assert wwid == "360014380056efd060000d00000510000"


def test_defer_service_restart(harness, mocker):
    mocker.patch("charm.time.time", return_value=1234)
    mock_service_event = mocker.patch("charm.deferred_events.ServiceEvent")
    mock_save_event = mocker.patch("charm.deferred_events.save_event")
    harness.charm._defer_service_restart(services=["testservice"], reason="testreason")
    mock_save_event.assert_called_once_with(mock_service_event.return_value)
    mock_service_event.assert_called_once_with(
        timestamp=1234, service="testservice", reason="Charm event: testreason", action="restart"
    )


def test_on_restart_services_action_mutually_exclusive_params(harness):
    """Test on restart servcices action with both deferred-only and services."""
    action_event = FakeActionEvent(params={"deferred-only": True, "services": "test_service"})
    harness.charm._on_restart_services_action(action_event)
    assert action_event.results["failed"] == "deferred-only and services are mutually exclusive"


def test_on_restart_services_action_no_params(harness):
    """Test on restart servcices action with no param."""
    action_event = FakeActionEvent(params={"deferred-only": False, "services": ""})
    harness.charm._on_restart_services_action(action_event)
    assert action_event.results["failed"] == "Please specify either deferred-only or services"


def test_on_restart_services_action_deferred_only_failed(harness, mocker):
    """Test on restart servcices action empty list of deferred restarts."""
    mocker.patch("charm.subprocess.check_call")
    mocker.patch("charm.deferred_events.get_deferred_restarts", return_value=[])
    action_event = FakeActionEvent(params={"deferred-only": True, "services": ""})
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
    harness.charm._on_restart_services_action(action_event)
    mock_check_call.assert_has_calls([call(["systemctl", "restart", "svc"])], any_order=False)
    assert action_event.results["success"] == "True"


def test_on_restart_services_action_services_failed(harness):
    """Test on restart servcices action failed with invalid service input."""
    action_event = FakeActionEvent(
        params={"deferred-only": False, "services": "non_valid_service"}
    )
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
    harness.charm._on_show_deferred_restarts_action(action_event)
    assert (
        action_event.results["deferred-restarts"]
        == "- 1970-01-02 10:17:36 +0000 UTC svc" + "                                      Reason\n"
    )


def test_on_reload_multipathd_service_action(harness, mocker):
    """Test on reload multipathd action."""
    action_event = FakeActionEvent()
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    harness.charm._on_reload_multipathd_service_action(action_event)
    mock_check_call.assert_called_once_with(["systemctl", "reload", "multipathd"])
    assert action_event.results["success"] == "True"


def test_on_iscsi_discovery_and_login_action(harness, mocker):
    """Test on iscsi discovery and login action."""
    mock_check_call = mocker.patch("charm.subprocess.check_call")
    mock_check_output = mocker.patch("charm.subprocess.check_output")
    action_event = FakeActionEvent()
    harness.update_config({"iscsi-target": "abc", "iscsi-port": "443"})
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
    harness.charm.unit.status = ActiveStatus("Unit is ready")

    # Trigger decorator function by emitting update_status event
    harness.charm.on.update_status.emit()

    mock_check_restart_timestamps.assert_called_once()
    assert harness.charm.unit.status == ActiveStatus(
        "Unit is ready. Services queued for restart: svc"
    )


def test_check_deferred_restarts_queue_logs_error(harness, mocker):
    """Test check_deferred_restarts_queue logs error."""
    mock_error = mocker.patch("charm.logging.error")
    value_error = ValueError("test")
    mock_check_restart_timestamps = mocker.patch(
        "charm.deferred_events.check_restart_timestamps", side_effect=value_error
    )
    harness.charm.on.update_status.emit()
    mock_check_restart_timestamps.assert_called_once()
    mock_error.assert_called_once_with("Cannot retrieve services' start time: %s", value_error)


def test_configure_deferred_restarts(harness, mocker):
    """Test on setting up deferred restarts in policy-rc.d."""
    mock_install_policy_rcd = mocker.patch("charm.policy_rcd.install_policy_rcd")
    mock_remove_policy_file = mocker.patch("charm.policy_rcd.remove_policy_file")
    mock_add_policy_block = mocker.patch("charm.policy_rcd.add_policy_block")
    mock_chmod = mocker.patch("charm.os.chmod")

    harness.update_config({"enable-auto-restarts": True})
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
    harness.charm.unit.status = ActiveStatus("Unit is ready")
    harness.charm._iscsi_discovery_and_login()
    mock_log_exception.assert_called_once()


def test_on_cos_agent_relation_handlers(harness, mocker):
    """Test the relation event handlers for cos-agent."""
    mock_install_exporter = mocker.patch("storage_connector.metrics_utils.install_exporter")
    mock_uninstall_exporter = mocker.patch("storage_connector.metrics_utils.uninstall_exporter")

    rel_id = harness.add_relation("cos-agent", "grafana-agent")
    harness.add_relation_unit(rel_id, "grafana-agent/0")
    mock_install_exporter.assert_called_once_with(harness.charm.model.resources)

    harness.remove_relation(rel_id)
    mock_uninstall_exporter.assert_called_once()


def test_on_nrpe_external_master_handlers(harness, mocker):
    """Test the relation event handlers for nrpe-external-master."""
    mock_install_exporter = mocker.patch("storage_connector.metrics_utils.install_exporter")
    mock_uninstall_exporter = mocker.patch("storage_connector.metrics_utils.uninstall_exporter")
    mock_unsync_nrpe_files = mocker.patch("storage_connector.nrpe_utils.unsync_nrpe_files")

    rel_id = harness.add_relation("nrpe-external-master", "nrpe")
    mock_install_exporter.assert_called_once_with(harness.charm.model.resources)

    harness.remove_relation(rel_id)
    mock_uninstall_exporter.assert_called_once()
    mock_unsync_nrpe_files.assert_called_once()


def test_on_nrpe_external_master_changed(harness, mocker):
    """Test the relation event handlers for nrpe-external-master."""
    mocker.patch("storage_connector.metrics_utils.install_exporter")
    mocker.patch("storage_connector.metrics_utils.uninstall_exporter")
    mock_update_nrpe_config = mocker.patch("charm.nrpe_utils.update_nrpe_config")

    rel_id = harness.add_relation("nrpe-external-master", "nrpe")
    harness.add_relation_unit(rel_id, "nrpe/0")
    harness.update_relation_data(rel_id, "nrpe/0", {"foo": "bar"})
    mock_update_nrpe_config.assert_called_once_with(harness.charm.model.config)


def test_on_nrpe_external_master_handlers_config(harness, mocker):
    """Test the relation event handlers for nrpe-external-master."""
    mocker.patch("charm.metrics_utils.install_exporter")
    mocker.patch("charm.metrics_utils.uninstall_exporter")
    mock_update_nrpe_config = mocker.patch("charm.nrpe_utils.update_nrpe_config")

    harness.add_relation("nrpe-external-master", "nrpe")
    harness.charm.on.config_changed.emit()

    mock_update_nrpe_config.assert_called_once_with(harness.charm.model.config)


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
