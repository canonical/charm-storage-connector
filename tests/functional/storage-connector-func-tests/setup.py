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

"""Code for setting up storage-connector tests."""

import json
import logging

import zaza.model


def basic_target_setup():
    """Run basic setup for iscsi guest."""
    logging.info('Installing package tgt on ubuntu-target')
    unit = zaza.model.get_units('ubuntu-target')[0]
    setup_cmds = [
        "apt install --yes tgt",
        "systemctl start tgt",
        "open-port 3260"]
    for cmd in setup_cmds:
        zaza.model.run_on_unit(
            unit.entity_id,
            cmd)


def configure_iscsi_target():
    """Configure the iscsi target."""
    lun = 'iqn.2020-07.canonical.com:lun1'
    backing_store = 'dev/vdb'
    initiator_address = zaza.model.get_app_ips('ubuntu')[0]
    username = 'iscsi-user'
    password = 'password123'
    username_in = 'iscsi-target'
    password_in = 'secretpass'
    write_file = (
        """echo -e '<target {}>\n\tbacking-store {}\n\tinitiator-address """
        """{}\n\tincominguser {} {}\n\toutgoinguser {} {}\n</target>' """
        """ | sudo tee /etc/tgt/conf.d/iscsi.conf""".format(lun,
                                                            backing_store,
                                                            initiator_address,
                                                            username,
                                                            password,
                                                            username_in,
                                                            password_in)
    )
    logging.info('Writing target iscsi.conf')
    zaza.model.run_on_unit('ubuntu-target/0', write_file)
    # Restart tgt to load new config
    restart_tgt = "systemctl restart tgt"
    zaza.model.run_on_unit('ubuntu-target/0', restart_tgt)


def get_unit_full_hostname(unit_name):
    """Retrieve the full hostname of a unit."""
    for unit in zaza.model.get_units(unit_name):
        result = zaza.model.run_on_unit(unit.entity_id, 'hostname -f')
        hostname = result['Stdout'].rstrip()
    return hostname


def configure_iscsi_connector():
    """Configure iscsi connector."""
    iqn = 'iqn.2020-07.canonical.com:lun1'
    unit_fqdn = get_unit_full_hostname('ubuntu')
    iscsi_target = zaza.model.get_app_ips('ubuntu-target')[0]
    initiator_dictionary = json.dumps({unit_fqdn: iqn})
    conf = {
        'storage-type': 'iscsi',
        'initiator-dictionary': initiator_dictionary,
        'iscsi-target': iscsi_target,
        'iscsi-port': '3260',
        'iscsi-node-session-auth-authmethod': 'CHAP',
        'iscsi-node-session-auth-username': 'iscsi-user',
        'iscsi-node-session-auth-password': 'password123',
        'iscsi-node-session-auth-username-in': 'iscsi-target',
        'iscsi-node-session-auth-password-in': 'secretpass',
        'multipath-devices': '{}',
        'enable-auto-restarts': "false"
    }

    zaza.model.set_application_config('storage-connector', conf)
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
