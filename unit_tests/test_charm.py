import unittest
from unittest.mock import Mock, patch

from ops.framework import EventBase
from ops.testing import Harness
from charm import CharmIscsiConnectorCharm



# list of tests to run
# - test if install triggers installed state
# - test if config_changed triggers render_config
# - test if the actions trigger actions
# - 


class TestCharm(unittest.TestCase):

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
        self.assertTrue(harness.charm.state.started)
        #maybe failing because it is defered when configuration is not done yet? 
    
    def test_on_config_changed(self):


    def mock_render_config(self):
        



    # def test_config_changed(self):
    #     harness = Harness(CharmIscsiConnectorCharm)
    #     # from 0.8 you should also do:
    #     # self.addCleanup(harness.cleanup)
    #     harness.begin()
    #     self.assertEqual(harness.charm.model.config.get('target'), None)
    #     harness.update_config({"target": "10.5.0.125"})
    #     self.assertEqual(list(harness.charm._config.get('target')), ["10.5.0.125"])

    # def test_restart_iscsi_services_action(self):
    #     harness = Harness(CharmIscsiConnectorCharm)
    #     harness.begin()
    #     action_event = Mock(params={"fail": ""})


    # def test_action(self):
    #     harness = Harness(CharmIscsiConnectorCharm)
    #     harness.begin()
    #     # the harness doesn't (yet!) help much with actions themselves
    #     action_event = Mock(params={"fail": ""})
    #     harness.charm.on_restart_iscsi_services_action(action_event)

    #     self.assertTrue(action_event.set_result.called)

    # def test_action_fail(self):
    #     harness = Harness(CharmIscsiConnectorCharm)
    #     harness.begin()
    #     action_event = Mock(params={"fail": "fail this"})
    #     harness.charm.on_restart_iscsi_services_action(action_event)

    #     self.assertEqual(action_event.fail.call_args, [("fail this",)])



if __name__ == "__main__":
    unittest.main()
