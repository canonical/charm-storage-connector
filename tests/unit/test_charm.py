
"""Unit tests for ISCSI Connector charm."""

import subprocess
import unittest
from unittest.mock import create_autospec

from charm import CharmIscsiConnectorCharm
from ops.framework import EventBase
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    """Charm Unit Tests."""

    subprocess_mock = create_autospec(subprocess.check_call, return_value='True')
    subprocess.check_call = subprocess_mock

    def setUp(self):
        """Test setup."""
        self.harness = Harness(CharmIscsiConnectorCharm)
        self.harness.begin()

    def test__init__works_without_a_hitch(self):
        """Test init."""
        harness = Harness(CharmIscsiConnectorCharm)
        harness.begin()

    def test_on_install(self):
        """Test installation."""
        harness = Harness(CharmIscsiConnectorCharm)
        harness.begin()
        self.assertFalse(harness.charm.state.installed)
        harness.charm.on.install.emit()
        self.assertTrue(harness.charm.state.installed)

    def test_on_start(self):
        """Test on start hook."""
        harness = Harness(CharmIscsiConnectorCharm)
        harness.begin()
        self.assertFalse(harness.charm.state.started)
        harness.charm.on.start.emit()
        # event deferred as charm not configured yet
        self.assertFalse(harness.charm.state.started)
        # mock charm as configured
        harness.charm.state.configured = True
        harness.charm.on.start.emit()
        self.assertTrue(harness.charm.state.started)

    def test_on_restart_iscsi_services_action(self):
        """Test on restart action."""
        harness = Harness(CharmIscsiConnectorCharm)
        harness.begin()
        action_event = FakeActionEvent()
        harness.charm.on_restart_iscsi_services_action(action_event)
        self.assertEqual(action_event.results['success'], 'True')

    def test_on_reload_multipathd_service_action(self):
        """Test on reload action."""
        harness = Harness(CharmIscsiConnectorCharm)
        harness.begin()
        action_event = FakeActionEvent()
        harness.charm.on_reload_multipathd_service_action(action_event)
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
