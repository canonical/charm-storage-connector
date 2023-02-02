# Copyright 2020 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Encapsulate storage-connector testing."""

import logging

import zaza.model
import zaza.openstack.charm_tests.test_utils as test_utils


class StorageConnectorTest(test_utils.BaseCharmTest):
    """Class for storage-connector tests."""

    @classmethod
    def setUpClass(cls):
        """Run class setup for running glance tests."""
        super(StorageConnectorTest, cls).setUpClass()

    def test_iscsi_connector_config_changed(self):
        """Test iscsi configuration changes and wait for idle status."""
        conf = zaza.model.get_application_config('storage-connector')
        conf["storage-type"] = "null"
        zaza.model.set_application_config('storage-connector', conf)
        logging.info('Wait for block status...')
        zaza.model.wait_for_application_states(
            states={
                "storage-connector": {
                    "workload-status": "blocked",
                    "workload-status-message-prefix": "Missing"
                },
                "ubuntu": {
                    "workload-status": "active",
                    "workload-status-message-regex": "^$"
                },
                "ubuntu-target": {
                    "workload-status": "active",
                    "workload-status-message-regex": "^$"
                }
            }
        )

        conf["storage-type"] = "iscsi"
        zaza.model.set_application_config('storage-connector', conf)
        logging.info('Wait for idle/ready status...')
        zaza.model.wait_for_application_states(
            states={
                "storage-connector": {
                    "workload-status": "active",
                    "workload-status-message-prefix": ""
                },
                "ubuntu": {
                    "workload-status": "active",
                    "workload-status-message-regex": "^$"
                },
                "ubuntu-target": {
                    "workload-status": "active",
                    "workload-status-message-regex": "^$"
                }
            }
        )

    def test_validate_iscsi_session(self):
        """Validate that the iscsi session is active."""
        unit = zaza.model.get_units('storage-connector')[0]
        logging.info('Checking if iscsi session is active.')
        run = zaza.model.run_on_unit(unit.entity_id, 'iscsiadm -m session')
        logging.info("""iscsiadm -m session: Stdout: {}, Stderr: {}, """
                     """Code: {}""".format(run['Stdout'],
                                           run['Stderr'],
                                           run['Code']))
        assert run['Code'] == '0'

    def test_defer_service_restarts(self):
        """Validate that the iscsi services are deferred on config-changed."""
        unit = zaza.model.get_units('storage-connector')[0]

        active_time_pre_check = zaza.model.get_systemd_service_active_time(
            unit.entity_id, 'iscsid.service'
        )
        logging.info("""Service start time before config change: {}""".format(
            active_time_pre_check))

        # Modify the value of a random config option to trigger config-changed event
        conf = zaza.model.get_application_config('storage-connector')
        conf["iscsi-node-session-scan"] = "manual"
        zaza.model.set_application_config('storage-connector', conf)

        zaza.model.wait_for_application_states(
            states={
                "storage-connector": {
                    "workload-status": "active",
                    "workload-status-message-regex": ".*Services queued for restart.*"
                },
                "ubuntu": {
                    "workload-status": "active",
                    "workload-status-message-regex": "^$"
                },
                "ubuntu-target": {
                    "workload-status": "active",
                    "workload-status-message-regex": "^$"
                }
            }
        )

        active_time_post_check = zaza.model.get_systemd_service_active_time(
            unit.entity_id, 'iscsid.service'
        )
        logging.info("""Service start time after config change: {}""".format(
            active_time_post_check))

        # Check if service restart is blocked
        assert active_time_pre_check == active_time_post_check

        # Run restart-iscsi-services to restart the deferred services
        zaza.model.run_action(
            unit.entity_id,
            "restart-services",
            action_params={
                'deferred-only': True})
        zaza.model.wait_for_application_states(
            states={
                "storage-connector": {
                    "workload-status": "active",
                    "workload-status-message-prefix": "Unit is ready"
                },
                "ubuntu": {
                    "workload-status": "active",
                    "workload-status-message-regex": "^$"
                },
                "ubuntu-target": {
                    "workload-status": "active",
                    "workload-status-message-regex": "^$"
                }
            }
        )

        active_time_after_restart = zaza.model.get_systemd_service_active_time(
            unit.entity_id, 'iscsid.service'
        )
        logging.info("""Service start time after service restart action: {}""".format(
            active_time_after_restart))

        # Check if service restart was successful
        assert active_time_post_check != active_time_after_restart
