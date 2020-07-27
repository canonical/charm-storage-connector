#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
# Copyright © 2020 Camille Rodriguez camille.rodriguez@canonical.com

"""Iscsi Connector Charm."""

import json
import logging
from pathlib import Path
import socket
import subprocess

import apt
from jinja2 import Environment, FileSystemLoader
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, BlockedStatus, ModelError


logger = logging.getLogger(__name__)


class CharmIscsiConnectorCharm(CharmBase):
    """Class reprisenting this Operator charm."""

    state = StoredState()
    PACKAGES = ['multipath-tools']

    ISCSI_CONF_PATH = Path('/etc/iscsi')
    ISCSI_CONF = ISCSI_CONF_PATH / 'iscsid.conf'
    ISCSI_INITIATOR_NAME = ISCSI_CONF_PATH / 'initiatorname.iscsi'
    MULTIPATH_CONF_DIR = Path('/etc/multipath')
    MULTIPATH_CONF_PATH = MULTIPATH_CONF_DIR / 'conf.d'
    MULTIPATH_CONF = MULTIPATH_CONF_PATH / 'multipath.conf'

    ISCSI_SERVICES = ['iscsid', 'open-iscsi']
    MULTIPATHD_SERVICE = 'multipathd'

    MANDATORY_CONFIG = ['target', 'port']

    def __init__(self, *args):
        """Initialize charm and configure states and events to observe."""
        super().__init__(*args)
        # -- standard hook observation
        self.framework.observe(self.on.install, self.on_install)
        self.framework.observe(self.on.start, self.on_start)
        self.framework.observe(self.on.config_changed, self.render_config)
        self.framework.observe(self.on.restart_iscsi_services_action, self.on_restart_iscsi_services_action)
        self.framework.observe(self.on.reload_multipathd_service_action, self.on_reload_multipathd_service_action)
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
        """Render configuration templates upon config change."""
        self.unit.status = MaintenanceStatus("Rendering charm configuration")
        self.ISCSI_CONF_PATH.mkdir(
            exist_ok=True,
            mode=0o750)
        self.MULTIPATH_CONF_DIR.mkdir(
            exist_ok=True,
            mode=0o750)
        self.MULTIPATH_CONF_PATH.mkdir(
            exist_ok=True,
            mode=0o750)

        charm_config = self.framework.model.config
        tenv = Environment(loader=FileSystemLoader('templates'))

        self._iscsi_initiator(tenv, charm_config)
        self._iscsid_configuration(tenv, charm_config)
        self._multipath_configuration(tenv, charm_config)

        logging.info('Enabling iscsid')
        # Enabling the service ensure it start on reboots.
        subprocess.check_call(['systemctl', 'enable', self.ISCSI_SERVICES[0]])

        logging.info('Restarting iscsi services')
        for service in self.ISCSI_SERVICES:
            subprocess.check_call(['systemctl', 'restart', service])

        if not self._check_mandatory_config():
            return
        logging.info('Launching iscsiadm discovery and login')
        try:
            self._iscsiadm_discovery(charm_config)
            self._iscsiadm_login()
        except subprocess.CalledProcessError as e:
            logging.error('Iscsi discovery and login failed. Traceback: {}'.format(e))
            self.unit.status = BlockedStatus('Iscsi discovery failed against given target')
            return
       
        logging.info('Reloading multipathd service')
        subprocess.check_call(['systemctl', 'reload', self.MULTIPATHD_SERVICE])

        logging.info("Setting started state")
        self.state.started = True
        self.state.configured = True
        self.unit.status = ActiveStatus("Unit is ready")

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

    # Actions
    def on_restart_iscsi_services_action(self, event):
        event.log('Restarting iscsi services')
        for service in self.ISCSI_SERVICES:
            subprocess.check_call(['systemctl', 'restart', service])
            event.set_results({"success": "true"})

    def on_reload_multipathd_service_action(self, event):
        event.log('Restarting multipathd service')
        subprocess.check_call(['systemctl', 'reload', self.MULTIPATHD_SERVICE])
        event.set_results({"success": "true"})

    # Additional functions
    def _check_mandatory_config(self):
        charm_config = self.framework.model.config
        missing_config = []
        for config in self.MANDATORY_CONFIG:
            if charm_config.get(config) is None:
                missing_config.append(config)
        if missing_config:
            self.unit.status = BlockedStatus("Missing mandatory configuration option {}".format(missing_config))
            return False
        return True
        
    # def _fetch_optional_resource(self, resource_name):
    #     resource = None
    #     try:
    #         resource = self.framework.model.resources.fetch(resource_name)
    #     except ModelError:
    #         # The resource is optional, the charm should not error without it.
    #         pass
    #     return resource

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

    def _iscsi_initiator(self, tenv, charm_config):
        initiator_name = None
        hostname = socket.getfqdn()
        initiators = charm_config.get('initiator-dictionary')
        if initiators:
            # search for hostname and create context
            initiators_dict = json.loads(initiators)
            if hostname in initiators_dict.keys():
                initiator_name = initiators_dict[hostname]

        if not initiator_name:
            logging.warning('The hostname was not found in the initiator dictionary! A random name will be ' +
                            'generated for {}'.format(hostname))
            initiator_name = subprocess.getoutput('/sbin/iscsi-iname')

        logging.info('Rendering initiatorname.iscsi')
        ctxt = {'initiator_name': initiator_name}
        template = tenv.get_template('initiatorname.iscsi.j2')
        rendered_content = template.render(ctxt)
        self.ISCSI_INITIATOR_NAME.write_text(rendered_content)

    def _iscsid_configuration(self, tenv, charm_config):
        ctxt = {
            'node_startup': charm_config.get('iscsi-node-startup'),
            'node_fastabort': charm_config.get('iscsi-node-session-iscsi-fastabort'),
            'node_session_scan': charm_config.get('iscsi-node-session-scan')
        }
        logging.info('Rendering iscsid.conf template.')
        template = tenv.get_template('iscsid.conf.j2')
        rendered_content = template.render(ctxt)
        self.ISCSI_CONF.write_text(rendered_content)
        self.ISCSI_CONF.chmod(0o600)

    def _multipath_configuration(self, tenv, charm_config):
        ctxt = {}
        multipath_conf_devices = charm_config.get('multipath-conf-devices')
        if multipath_conf_devices:
            conf_devices = json.loads(multipath_conf_devices)
            ctxt['conf_devices'] = conf_devices
        template = tenv.get_template('multipath.conf.j2')
        rendered_content = template.render(ctxt)
        self.MULTIPATH_CONF.write_text(rendered_content)
        self.MULTIPATH_CONF.chmod(0o644)

    def _iscsiadm_discovery(self, charm_config):
        target = charm_config.get('target')
        port = charm_config.get('port')
        logging.info('Launching iscsiadm discovery against target')
        subprocess.check_call(['iscsiadm', '-m', 'discovery', '-t', 'sendtargets', '-p', target + ':' + port])

    def _iscsiadm_login(self):
        # add check if already logged in, no error if it is.
        subprocess.check_call(['iscsiadm', '-m', 'node', '--login'])

if __name__ == "__main__":
    main(CharmIscsiConnectorCharm)
