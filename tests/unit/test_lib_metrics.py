"""Metrics module related tests."""
from unittest import TestCase
from unittest.mock import MagicMock, patch

from ops.model import ModelError

import metrics  # noqa


class TestMetrics(TestCase):
    """Metrics module related tests."""

    @patch("metrics.stat")
    @patch("charms.operator_libs_linux.v1.snap.install_local")
    def test_install_exporter_snap_resource(self, mock_install_local, mock_stat):
        """Test the install_exporter_snap function with resources."""
        snap_resource_path = "/prometheus-iscsi-exporter.snap"
        mock_resources = MagicMock()
        mock_resources.fetch.return_value = snap_resource_path
        mock_stat.st_size.return_value = 1

        metrics.install_exporter_snap(mock_resources)
        mock_install_local.assert_called_once_with(snap_resource_path, dangerous=True)

    @patch("charms.operator_libs_linux.v1.snap.add")
    def test_install_exporter_snap_snapstore(self, mock_add):
        """Test the install_exporter_snap function without resources."""
        mock_resources = MagicMock()
        mock_resources.fetch.side_effect = ModelError

        metrics.install_exporter_snap(mock_resources)
        mock_add.assert_called_once_with("prometheus-iscsi-exporter")

    @patch("charms.operator_libs_linux.v1.snap.remove")
    def test_uninstall_exporter_snap(self, mock_remove):
        """Test the uninstall_exporter_snap function."""
        metrics.uninstall_exporter_snap()
        mock_remove.assert_called_once_with("prometheus-iscsi-exporter")

    @patch("metrics.Configuration")
    def test_install_multipath_status_cronjob(self, mock_configuration):
        """Test the install_multipath_status_cronjob function."""
        mock_configuration.cron_script_output_path = "/test"
        mock_configuration.cron_script_path = MagicMock()

        metrics.install_multipath_status_cronjob()
        mock_configuration.cron_script_path.write_text.assert_called_once_with(
            "* * * * * root multipath -ll > /test\n"
        )
        mock_configuration.cron_script_path.chmod.assert_called_once_with(
            mode=0o644
        )

    @patch("metrics.Configuration")
    def test_uninstall_multipath_status_cronjob(self, mock_configuration):
        """Test the uninstall_multipath_status_cronjob function."""
        mock_configuration.cron_script_output_path = MagicMock()
        mock_configuration.cron_script_path = MagicMock()

        metrics.uninstall_multipath_status_cronjob()
        mock_configuration.cron_script_path.unlink.assert_called_once_with(
            missing_ok=True
        )
        mock_configuration.cron_script_output_path.unlink.assert_called_once_with(
            missing_ok=True
        )
