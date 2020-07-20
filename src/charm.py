#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
# Copyright © 2020 Camille Rodriguez camille.rodriguez@canonical.com

import apt
from jinja2 import Environment, FileSystemLoader
import json
import logging
import os
from pathlib import Path
import socket
import subprocess

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, ModelError
from adapters.framework import FrameworkAdapter

logger = logging.getLogger(__name__)


class CharmIscsiConnectorCharm(CharmBase):
    """Class reprisenting this Operator charm."""

    state = StoredState()
    PACKAGES = ['multipath-tools']

    ISCSI_CONF_PATH = Path('/etc/iscsi')
    ISCSI_CONF = ISCSI_CONF_PATH / 'iscsid.conf'
    ISCSI_INITIATOR_NAME = ISCSI_CONF_PATH / 'initiatorname.iscsi'
    MULTIPATH_CONF_PATH = Path('/etc')
    MULTIPATH_CONF = MULTIPATH_CONF_PATH / 'multipath.conf'

    ISCSI_SERVICES = ['iscsid', 'open-iscsi']
    MULTIPATH_SERVICE = ['multipathd']

    def __init__(self, *args):
        """Initialize charm and configure states and events to observe."""
        super().__init__(*args)
        self.fw_adapter = FrameworkAdapter(self.framework)
        # -- standard hook observation
        self.framework.observe(self.on.install, self.on_install)
        self.framework.observe(self.on.start, self.on_start)
        self.framework.observe(self.on.config_changed, self.render_config)
        # -- initialize states --
        self.state.set_default(installed=False)
        self.state.set_default(configured=False)
        self.state.set_default(started=False)

    def on_install(self, event):
        """Handle install state."""
        self.unit.status = MaintenanceStatus("Installing charm software")

        # install packages
        cache = apt.cache.Cache()
        cache.update()
        cache.open()
        for package in self.PACKAGES:
            pkg = cache[package]
            if not pkg.is_installed:
                pkg.mark_install()
                cache.commit()

        self.unit.status = MaintenanceStatus("Install complete")
        logging.info("Install of software complete")
        self.state.installed = True

    def render_config(self, event):
        self.ISCSI_CONF_PATH.mkdir(
            exist_ok=True,
            mode=0o750)
        
        charm_config = self.fw_adapter.get_config()
        tenv = Environment(loader=FileSystemLoader('templates'))
        
        def _iscsi_initiator():
            initiator_name = None
            hostname = socket.getfqdn()
            initiators = charm_config.get('initiator-dictionary')
            if initiators:
                # search for hostname and create context
                initiators_dict = json.loads(initiators)
                if hostname in initiators_dict.keys():
                    # TO-DO (maybe): add a regex check to make sure the initiator name provided respects the correct format. 
                    initiator_name = initiators_dict[hostname]

            if not initiator_name:
                logging.warning('The hostname was not found in the initiator' +
                ' dictionary! A random name will be generated for ' +
                '{}'.format(hostname))
                initiator_name = subprocess.getoutput('/sbin/iscsi-iname')

            ctxt = {'initiator_name': initiator_name}
            template = tenv.get_template('initiatorname.iscsi.j2')
            rendered_content = template.render(ctxt)
            self.ISCSI_INITIATOR_NAME.write_text(rendered_content)
            logging.info('Rendering initiatorname.iscsi')

        def _iscsid_configuration():
            iscsi_resource = None
            try:
                iscsi_resource = self.framework.model.resources.fetch('iscsid-conf')
            except ModelError:
                # The resource is optional, the charm should not error without it. 
                pass
            if iscsi_resource:
                logging.info('Resource iscsi.conf found, rendering.')
                rendered_content = iscsi_resource.read_text()
            else:
                logging.info('Rendering default iscsid.conf template.')
                template = tenv.get_template('iscsid.conf.j2')
                rendered_content = template.render(ctxt)

            self.ISCSI_CONF.write_text(rendered_content)
            self.ISCSI_CONF.chmod(0o600)
            
        def _multipath_configuration():
            multipath_resource = None
            try:
                multipath_resource = self.framework.model.resources.fetch('multipath-conf')
            except ModelError:
                # The resource is optional, the charm should not error without it. 
                pass
            if multipath_resource:
                logging.info('Resource multipath.conf found, rendering.')
                rendered_content = multipath_resource.read_text()
            else:
                logging.info('Rendering default multipath.conf template.')
                template = tenv.get_template('multipath.conf.j2')
                rendered_content = template.render(ctxt)

            self.MULTIPATH_CONF.write_text(rendered_content)
            self.MULTIPATH_CONF.chmod(0o644)

        def _iscsiadm_discovery():
            target = charm_config.get('target')
            port = charm_config.get('port')
            logging.info('Launching iscsiadm discovery against target')
            subprocess.check_call(['iscsiadm', '-m', 'discovery', '-t', 'sendtargets', '-p', target + ':' + port])

        def _iscsiadm_login():
            subprocess.check_call(['iscsiadm', '-m', 'node', '--login'])


        _iscsi_initiator()
        _iscsid_configuration()
        _multipath_configuration()

        logging.info('Enabling iscsid')
        # Enabling the service ensure it start on reboots. 
        subprocess.check_call(['systemctl', 'enable', self.ISCSI_SERVICES[0]])

        logging.info('Restarting iscsi services')
        for service in self.ISCSI_SERVICES:
            subprocess.check_call(['systemctl', 'restart', service])
        
        logging.info('Launch iscsiadm discovery and login')
        _iscsiadm_discovery
        _iscsiadm_login

        logging.info('Restarting multipathd service')
        subprocess.check_call(['systemctl', 'restart', self.MULTIPATH_SERVICE])

        logging.info("Setting started state")
        self.state.started = True
        self.state.configured = True

    def on_start(self, event):
        """Handle start state."""

        if not self.state.configured:
            logging.warning("Start called before configuration complete, deferring event: {}".format(event.handle))
            self._defer_once(event)

            return
        self.unit.status = MaintenanceStatus("Starting charm software")
        # Start software
        self.unit.status = ActiveStatus("Unit is ready")
        self.state.started = True
        logging.info("Started")

    def _defer_once(self, event):
        """Defer the given event, but only once."""
        notice_count = 0
        handle = str(event.handle)

        for event_path, _, _ in self.framework._storage.notices(None):
            if event_path.startswith(handle.split('[')[0]):
                notice_count += 1
                logging.debug("Found event: {} x {}".format(event_path, notice_count))

        if notice_count > 1:
            logging.debug("Not deferring {} notice count of {}".format(handle, notice_count))
        else:
            logging.debug("Deferring {} notice count of {}".format(handle, notice_count))
            event.defer()


if __name__ == "__main__":
    from ops.main import main
    main(CharmIscsiConnectorCharm)
