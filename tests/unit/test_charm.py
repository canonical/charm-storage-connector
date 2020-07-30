import unittest
from unittest.mock import Mock, patch, create_autospec, MagicMock
import subprocess

from ops.framework import EventBase
from ops.testing import Harness
from charm import CharmIscsiConnectorCharm



# list of tests to run
# - test if install triggers installed state
# - test if config_changed triggers render_config
# - test if the actions trigger actions
# - 


class TestCharm(unittest.TestCase):

    subprocess_mock = create_autospec(subprocess.check_call, return_value='True')
    subprocess.check_call = subprocess_mock

    def setUp(self):
        # Setup
        self.harness = Harness(CharmIscsiConnectorCharm)
        self.harness.begin()

    def test__init__works_without_a_hitch(self):
        # Setup
        harness = Harness(CharmIscsiConnectorCharm)

        # Exercise
        harness.begin()

    def test_on_install(self):
        harness = Harness(CharmIscsiConnectorCharm)
        harness.begin()
        self.assertFalse(harness.charm.state.installed)
        harness.charm.on.install.emit()
        self.assertTrue(harness.charm.state.installed)

    def test_on_start(self):
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
        harness = Harness(CharmIscsiConnectorCharm)
        harness.begin()
        action_event = FakeActionEvent()
        harness.charm.on_restart_iscsi_services_action(action_event)
        self.assertEqual(action_event.results['success'], 'True')

    def test_on_reload_multipathd_service_action(self):
        harness = Harness(CharmIscsiConnectorCharm)
        harness.begin()
        action_event = FakeActionEvent()
        harness.charm.on_reload_multipathd_service_action(action_event)
        self.assertEqual(action_event.results['success'], 'True')


class FakeActionEvent(EventBase):
    def __init__(self, params=None):
        super().__init__(None)
        if params is None:
            params = {}
        self.params = params

    def set_results(self, results):
        self.results = results
    
    def log(self, log):
        self.log = log


if __name__ == "__main__":
    unittest.main()
