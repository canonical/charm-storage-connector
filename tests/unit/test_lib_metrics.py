"""Metrics_utils module related tests."""

from ops.model import ModelError
from storage_connector import metrics_utils


def test_install_exporter_snap_resource(mocker):
    """Test the install_exporter_snap function with resources."""
    mock_install_local = mocker.patch("charms.operator_libs_linux.v1.snap.install_local")
    mock_stat = mocker.patch("pathlib.Path.stat")
    snap_resource_path = "/prometheus-iscsi-exporter.snap"
    mock_resources = mocker.MagicMock()
    mock_resources.fetch.return_value = snap_resource_path
    mock_stat.st_size.return_value = 1

    metrics_utils.install_exporter_snap(mock_resources)
    mock_install_local.assert_called_once_with(snap_resource_path, dangerous=True)


def test_install_exporter_snap_snapstore(mocker):
    """Test the install_exporter_snap function without resources."""
    mock_add = mocker.patch("charms.operator_libs_linux.v1.snap.add")
    mock_resources = mocker.MagicMock()
    mock_resources.fetch.side_effect = ModelError

    metrics_utils.install_exporter_snap(mock_resources)
    mock_add.assert_called_once_with("prometheus-iscsi-exporter")


def test_uninstall_exporter_snap(mocker):
    """Test the uninstall_exporter_snap function."""
    mock_remove = mocker.patch("charms.operator_libs_linux.v1.snap.remove")
    metrics_utils.uninstall_exporter_snap()
    mock_remove.assert_called_once_with("prometheus-iscsi-exporter")


def test_install_multipath_status_cronjob(mocker):
    """Test the install_multipath_status_cronjob function."""
    mocker.patch("storage_connector.metrics_utils.CRON_SCRIPT_OUTPUT_PATH", "/test")
    mock_cron_script_path = mocker.patch("storage_connector.metrics_utils.CRON_SCRIPT_PATH")
    mock_cron_script_path.return_value = mocker.MagicMock()

    metrics_utils.install_multipath_status_cronjob()
    mock_cron_script_path.write_text.assert_called_once_with(
        "* * * * * root multipath -ll > /test\n"
    )
    mock_cron_script_path.chmod.assert_called_once_with(mode=0o644)


def test_uninstall_multipath_status_cronjob(mocker):
    """Test the uninstall_multipath_status_cronjob function."""
    mock_cron_script_path = mocker.patch("storage_connector.metrics_utils.CRON_SCRIPT_PATH")
    mock_cron_script_output_path = mocker.patch(
        "storage_connector.metrics_utils.CRON_SCRIPT_OUTPUT_PATH"
    )
    mock_cron_script_output_path.return_value = mocker.MagicMock()
    mock_cron_script_path.return_value = mocker.MagicMock()

    metrics_utils.uninstall_multipath_status_cronjob()
    mock_cron_script_path.unlink.assert_called_once_with(missing_ok=True)
    mock_cron_script_output_path.unlink.assert_called_once_with(missing_ok=True)


def test_install_exporter(mocker):
    """Test the install_exporter function."""
    mock_install_exporter_snap = mocker.patch(
        "storage_connector.metrics_utils.install_exporter_snap"
    )
    mock_install_multipath_status_cronjob = mocker.patch(
        "storage_connector.metrics_utils.install_multipath_status_cronjob"
    )
    mock_resources = mocker.MagicMock()
    metrics_utils.install_exporter(mock_resources)
    mock_install_exporter_snap.assert_called_once()
    mock_install_multipath_status_cronjob.assert_called_once()


def test_uninstall_exporter(mocker):
    """Test the uninstall_exporter function."""
    mock_uninstall_exporter_snap = mocker.patch(
        "storage_connector.metrics_utils.uninstall_exporter_snap"
    )
    mock_uninstall_multipath_status_cronjob = mocker.patch(
        "storage_connector.metrics_utils.uninstall_multipath_status_cronjob"
    )
    metrics_utils.uninstall_exporter()
    mock_uninstall_exporter_snap.assert_called_once()
    mock_uninstall_multipath_status_cronjob.assert_called_once()
