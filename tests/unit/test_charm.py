
"""Unit tests for ISCSI Connector charm."""

import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import create_autospec, Mock
from pathlib import Path

from charm import CharmIscsiConnectorCharm
from src import charm

from ops.framework import EventBase
from ops.testing import Harness

import src.utils as utils

class TestCharm(unittest.TestCase):
    """Charm Unit Tests."""

    subprocess_mock = create_autospec(subprocess.check_call, return_value='True')
    subprocess.check_call = subprocess_mock

    

    def setUp(self):
        """Test setup."""
        self.tempdir = tempfile.mkdtemp()
        self.harness = Harness(CharmIscsiConnectorCharm)
        self.harness.set_leader(is_leader=True)
    
    def tearDown(self):
        """Remove testing artifacts."""
        shutil.rmtree(self.tempdir)

    def test__init__works_without_a_hitch(self):
        """Test init."""
        self.harness.begin()

    def test_abort_if_host_is_container(self):
        self.harness.begin()
        charm.utils.is_container = Mock(return_value = True)
        self.assertFalse(self.harness.charm.store.installed)

    def test_on_install(self):
        """Test installation."""
        charm.utils.is_container = Mock(return_value = False)
        # self.harness.charm.ISCSI_CONF_PATH = tempfile.mkdtemp()
        # with self.tempdir as td: Mock('src.charm.Path', lambda: return td)
        charm.Path = Mock(return_value = tempfile.mkdtemp())
        charm.CharmIscsiConnectorCharm.ISCSI_CONF_PATH = tempfile.mkdtemp()
        print(charm.CharmIscsiConnectorCharm.ISCSI_CONF_PATH)
        
        # self.harness.charm.ISCSI_CONF_DIR = self.tempdir

        self.harness.begin()
        self.harness.charm.ISCSI_CONF_PATH = Path(tempfile.mkdtemp())

        self.assertFalse(self.harness.charm.store.installed)
        self.harness.charm.on.install.emit()

        
        self.assertTrue(self.harness.charm.store.installed)

    def test_on_start(self):
        """Test on start hook."""
        self.harness.begin()
        self.assertFalse(self.harness.charm.store.started)
        self.harness.charm.on.start.emit()
        # event deferred as charm not configured yet
        self.assertFalse(self.harness.charm.store.started)
        # mock charm as configured
        self.harness.charm.store.configured = True
        self.harness.charm.on.start.emit()
        self.assertTrue(self.harness.charm.store.started)

    def test_on_restart_iscsi_services_action(self):
        """Test on restart action."""
        self.harness.begin()
        action_event = FakeActionEvent()
        self.harness.charm.on_restart_iscsi_services_action(action_event)
        self.assertEqual(action_event.results['success'], 'True')

    def test_on_reload_multipathd_service_action(self):
        """Test on reload action."""
        self.harness.begin()
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
