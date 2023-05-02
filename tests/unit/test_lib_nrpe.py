"""Unit tests for the nrpe library."""
from storage_connector import nrpe_utils


def test_sync_nrpe_files(mocker):
    """Test sync_nrpe_files function."""
    mock_plugins_dir_path = mocker.patch("storage_connector.nrpe_utils.NAGIOS_PLUGINS_DIR_PATH")
    mock_check_script_dst_path = mocker.patch(
        "storage_connector.nrpe_utils.CHECK_SCRIPT_DST_ABSOLUTE_PATH"
    )
    mock_check_script_dst_path.__str__.return_value = "/mock/dst"
    mock_rsync = mocker.patch("storage_connector.nrpe_utils.rsync")
    mocker.patch("storage_connector.nrpe_utils.charm_dir", return_value="/mock")

    nrpe_utils.sync_nrpe_files()

    mock_plugins_dir_path.mkdir.assert_called_once_with(parents=True, exist_ok=True)
    mock_rsync.assert_called_once_with("/mock/files/check_iscsi_metric.py", "/mock/dst")
    mock_check_script_dst_path.chmod.assert_called_once_with(mode=0o755)


def test_unsync_nrpe_files(mocker):
    """Test unsync_nrpe_files function."""
    mock_check_script_dst_path = mocker.patch(
        "storage_connector.nrpe_utils.CHECK_SCRIPT_DST_ABSOLUTE_PATH"
    )
    nrpe_utils.unsync_nrpe_files()
    mock_check_script_dst_path.unlink.assert_called_once_with(missing_ok=True)


def test_update_nrpe_config(mocker):
    """Test update_nrpe_config function."""
    mock_sync_nrpe_files = mocker.patch("storage_connector.nrpe_utils.sync_nrpe_files")
    mock_nrpe_compat = mocker.patch("storage_connector.nrpe_utils.NRPE")
    mock_config = mocker.MagicMock()
    mock_config.get.return_value = 1
    nrpe_utils.update_nrpe_config(mock_config)
    mock_sync_nrpe_files.assert_called_once()
    mock_nrpe_compat.return_value.add_check.assert_called_once_with(
        shortname="multipath",
        description="Check multipath path count",
        check_cmd="/usr/local/lib/nagios/plugins/check_iscsi_metric.py -n 1",
    )
    mock_nrpe_compat.return_value.write.assert_called_once()
    mock_config.get.assert_called_once_with("nagios_multipath_paths_per_volume")
