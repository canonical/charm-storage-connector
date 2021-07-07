
"""Unit tests for ISCSI Connector charm."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, create_autospec, patch

from charm import CharmStorageConnectorCharm

from ops.framework import EventBase
from ops.testing import Harness

from src import charm


class TestCharm(unittest.TestCase):
    """Charm Unit Tests."""

    subprocess_mock = create_autospec(subprocess.check_call, return_value='True')
    subprocess.check_call = subprocess_mock

    def setUp(self):
        """Test setup."""
        self.tempdir = tempfile.mkdtemp()
        self.harness = Harness(CharmStorageConnectorCharm)
        self.harness.set_leader(is_leader=True)
        self.harness.begin()

    def tearDown(self):
        """Remove testing artifacts."""
        shutil.rmtree(self.tempdir)

    def test__init__works_without_a_hitch(self):
        """Test init."""

    def test_abort_if_host_is_container(self):
        """Test if charm stops when deployed on a container."""
        charm.utils.is_container = Mock(return_value=True)
        self.assertFalse(self.harness.charm._stored.installed)

    @patch("charm.CharmStorageConnectorCharm._iscsi_initiator")
    @patch("charm.utils.is_container")
    @patch("charm.CharmStorageConnectorCharm.MULTIPATH_CONF")
    @patch("charm.CharmStorageConnectorCharm.MULTIPATH_CONF_PATH")
    @patch("charm.CharmStorageConnectorCharm.MULTIPATH_CONF_DIR")
    @patch("charm.CharmStorageConnectorCharm.ISCSI_INITIATOR_NAME")
    @patch("charm.CharmStorageConnectorCharm.ISCSI_CONF")
    @patch("charm.CharmStorageConnectorCharm.ISCSI_CONF_PATH")
    def test_on_install(self, iscsi_conf_path, iscsi_conf, iscsi_initiator_name,
                        multipath_conf_dir, multipath_conf_path, multipath_conf,
                        is_container, iscsi_initiator):
        """Test installation."""
        is_container.return_value = False
        iscsi_conf_path.return_value = Path(tempfile.mkdtemp())
        iscsi_conf.return_value = iscsi_conf_path / 'iscsid.conf'
        iscsi_initiator_name.return_value = iscsi_conf / 'initiatorname.iscsi'
        multipath_conf_dir.return_value = Path(tempfile.mkdtemp())
        multipath_conf_path.return_value = multipath_conf_dir / 'conf.d'
        multipath_conf.return_value = multipath_conf_path / 'multipath.conf'
        iscsi_initiator.return_value = None

        self.assertFalse(self.harness.charm._stored.installed)
        self.harness.charm.on.install.emit()

        self.assertTrue(os.path.exists(self.harness.charm.ISCSI_CONF))
        self.assertTrue(os.path.exists(self.harness.charm.MULTIPATH_CONF))
        self.assertTrue(self.harness.charm._stored.installed)

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

    def test_on_restart_iscsi_services_action(self):
        """Test on restart action."""
        action_event = FakeActionEvent()
        self.harness.charm.on_restart_iscsi_services_action(action_event)
        self.assertEqual(action_event.results['success'], 'True')

    def test_on_reload_multipathd_service_action(self):
        """Test on reload action."""
        action_event = FakeActionEvent()
        self.harness.charm.on_reload_multipathd_service_action(action_event)
        self.assertEqual(action_event.results['success'], 'True')


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
