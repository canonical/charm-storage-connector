"""Unit tests for the nrpe library."""
from unittest import TestCase
from unittest.mock import MagicMock, patch

from storage_connector import nrpe_utils


class TestNRPE(TestCase):
    """Nrpe module related tests."""

    @patch("storage_connector.nrpe_utils.charm_dir")
    @patch("storage_connector.nrpe_utils.rsync")
    @patch("storage_connector.nrpe_utils.CHECK_SCRIPT_DST_ABSOLUTE_PATH")
    @patch("storage_connector.nrpe_utils.NAGIOS_PLUGINS_DIR_PATH")
    def test_sync_nrpe_files(
        self,
        mock_plugins_dir_path,
        mock_check_script_dst_path,
        mock_rsync,
        mock_charm_dir
    ):
        """Test sync_nrpe_files function."""
        mock_check_script_dst_path.__str__ = MagicMock(
            return_value="/mock/dst"
        )
        mock_charm_dir.return_value = "/mock"

        nrpe_utils.sync_nrpe_files()

        mock_plugins_dir_path.mkdir.assert_called_once_with(
            parents=True, exist_ok=True
        )
        mock_rsync.assert_called_once_with(
            "/mock/files/check_iscsi_metric.py", "/mock/dst"
        )
        mock_check_script_dst_path.chmod.assert_called_once_with(
            mode=0o755
        )

    @patch("storage_connector.nrpe_utils.CHECK_SCRIPT_DST_ABSOLUTE_PATH")
    def test_unsync_nrpe_files(self, mock_check_script_dst_path):
        """Test unsync_nrpe_files function."""
        nrpe_utils.unsync_nrpe_files()
        mock_check_script_dst_path.unlink.assert_called_once_with(
            missing_ok=True
        )

    @patch("storage_connector.nrpe_utils.NRPE")
    @patch("storage_connector.nrpe_utils.sync_nrpe_files")
    def test_update_nrpe_config(
        self, mock_sync_nrpe_files, mock_nrpe_compat
    ):
        """Test update_nrpe_config function."""
        config = {"nagios_multipath_paths_per_volume": 4}
        nrpe_utils.update_nrpe_config(config)
        mock_sync_nrpe_files.assert_called_once()
        mock_nrpe_compat.return_value.add_check.assert_called_once()
        mock_nrpe_compat.return_value.write.assert_called_once()
