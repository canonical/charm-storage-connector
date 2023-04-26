"""Metrics_utils module related tests."""
from unittest import TestCase
from unittest.mock import MagicMock, patch

from ops.model import ModelError
from storage_connector import metrics_utils


class TestMetricsUtils(TestCase):
    """Metrics_utils module related tests."""

    @patch("pathlib.Path.stat")
    @patch("charms.operator_libs_linux.v1.snap.install_local")
    def test_install_exporter_snap_resource(self, mock_install_local, mock_stat):
        """Test the install_exporter_snap function with resources."""
        snap_resource_path = "/prometheus-iscsi-exporter.snap"
        mock_resources = MagicMock()
        mock_resources.fetch.return_value = snap_resource_path
        mock_stat.st_size.return_value = 1

        metrics_utils.install_exporter_snap(mock_resources)
        mock_install_local.assert_called_once_with(snap_resource_path, dangerous=True)

    @patch("charms.operator_libs_linux.v1.snap.add")
    def test_install_exporter_snap_snapstore(self, mock_add):
        """Test the install_exporter_snap function without resources."""
        mock_resources = MagicMock()
        mock_resources.fetch.side_effect = ModelError

        metrics_utils.install_exporter_snap(mock_resources)
        mock_add.assert_called_once_with("prometheus-iscsi-exporter")

    @patch("charms.operator_libs_linux.v1.snap.remove")
    def test_uninstall_exporter_snap(self, mock_remove):
        """Test the uninstall_exporter_snap function."""
        metrics_utils.uninstall_exporter_snap()
        mock_remove.assert_called_once_with("prometheus-iscsi-exporter")

    @patch("storage_connector.metrics_utils.CRON_SCRIPT_OUTPUT_PATH", "/test")
    @patch("storage_connector.metrics_utils.CRON_SCRIPT_PATH")
    def test_install_multipath_status_cronjob(self, mock_cron_script_path):
        """Test the install_multipath_status_cronjob function."""
        mock_cron_script_path.return_value = MagicMock()

        metrics_utils.install_multipath_status_cronjob()
        mock_cron_script_path.write_text.assert_called_once_with(
            "* * * * * root multipath -ll > /test\n"
        )
        mock_cron_script_path.chmod.assert_called_once_with(mode=0o644)

    @patch("storage_connector.metrics_utils.CRON_SCRIPT_OUTPUT_PATH")
    @patch("storage_connector.metrics_utils.CRON_SCRIPT_PATH")
    def test_uninstall_multipath_status_cronjob(
        self, mock_cron_script_path, mock_cron_script_output_path
    ):
        """Test the uninstall_multipath_status_cronjob function."""
        mock_cron_script_output_path.return_value = MagicMock()
        mock_cron_script_path.return_value = MagicMock()

        metrics_utils.uninstall_multipath_status_cronjob()
        mock_cron_script_path.unlink.assert_called_once_with(missing_ok=True)
        mock_cron_script_output_path.unlink.assert_called_once_with(missing_ok=True)

    @patch("storage_connector.metrics_utils.install_multipath_status_cronjob")
    @patch("storage_connector.metrics_utils.install_exporter_snap")
    def test_install_exporter(
        self, mock_install_exporter_snap, mock_install_multipath_status_cronjob
    ):
        """Test the install_exporter function."""
        mock_resources = MagicMock()
        metrics_utils.install_exporter(mock_resources)
        mock_install_exporter_snap.assert_called_once()
        mock_install_multipath_status_cronjob.assert_called_once()

    @patch("storage_connector.metrics_utils.uninstall_multipath_status_cronjob")
    @patch("storage_connector.metrics_utils.uninstall_exporter_snap")
    def test_uninstall_exporter(
        self, mock_uninstall_exporter_snap, mock_uninstall_multipath_status_cronjob
    ):
        """Test the uninstall_exporter function."""
        metrics_utils.uninstall_exporter()
        mock_uninstall_exporter_snap.assert_called_once()
        mock_uninstall_multipath_status_cronjob.assert_called_once()
