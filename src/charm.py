#! /usr/bin/env python3

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
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

import utils

logger = logging.getLogger(__name__)


class CharmIscsiConnectorCharm(CharmBase):
    """Class representing this Operator charm."""

    store = StoredState()
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
        self.framework.observe(self.on.install, self.render_config)
        self.framework.observe(self.on.start, self.on_start)
        self.framework.observe(self.on.config_changed, self.render_config)
        self.framework.observe(self.on.restart_iscsi_services_action,
                               self.on_restart_iscsi_services_action)
        self.framework.observe(self.on.reload_multipathd_service_action,
                               self.on_reload_multipathd_service_action)
        # -- initialize states --
        self.store.set_default(installed=False)
        self.store.set_default(configured=False)
        self.store.set_default(started=False)

    def on_install(self, event):
        """Handle install state."""
        self.unit.status = MaintenanceStatus("Installing charm software")

        # check if container
        if utils.is_container:
            self.unit.status = BlockedStatus("This charm is not supported on containers.")
            return

        # install packages
        cache = apt.cache.Cache()
        cache.update()
        cache.open()
        for package in self.PACKAGES:
            pkg = cache[package]
            if not pkg.is_installed:
                pkg.mark_install()

        cache.commit()
        # enable services to ensure they start upon reboot
        for service in self.ISCSI_SERVICES:
            try:
                logging.info('Enabling %s service', service)
                subprocess.check_call(['systemctl', 'enable', service])
            except subprocess.CalledProcessError:
                logging.exception('Unable to enable %s.', service)

        self.unit.status = MaintenanceStatus("Install complete")
        logging.info("Install of software complete")
        self.store.installed = True

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

        logging.info('Restarting iscsi services')
        for service in self.ISCSI_SERVICES:
            try:
                logging.info('Restarting %s service', service)
                subprocess.check_call(['systemctl', 'restart', service])
            except subprocess.CalledProcessError:
                logging.exception('An error occured while restarting %s.', service)

        if not self._check_mandatory_config():
            return

        if charm_config.get('discovery-and-login'):
            logging.info('Launching iscsiadm discovery and login')
            self._iscsiadm_discovery(charm_config)
            self._iscsiadm_login()

        logging.info('Reloading multipathd service')
        try:
            subprocess.check_call(['systemctl', 'reload', self.MULTIPATHD_SERVICE])
        except subprocess.CalledProcessError:
            message = "An error occured while reloading the multipathd service."
            self.unit.status = BlockedStatus(message)
            logging.exception('%s', message)

        logging.info("Setting started state")
        self.store.started = True
        self.store.configured = True
        self.unit.status = ActiveStatus("Unit is ready")

    def on_start(self, event):
        """Handle start state."""
        if not self.store.configured:
            logging.warning("Start called before configuration complete, " +
                            "deferring event: %s", event.handle)
            self._defer_once(event)
            return
        self.unit.status = MaintenanceStatus("Starting charm software")
        # Start software
        self.unit.status = ActiveStatus("Unit is ready")
        self.store.started = True
        logging.info("Started")

    # Actions
    def on_restart_iscsi_services_action(self, event):
        """Restart iscsid and open-iscsi services."""
        event.log('Restarting iscsi services')
        for service in self.ISCSI_SERVICES:
            subprocess.check_call(['systemctl', 'restart', service])
            event.set_results({"success": "True"})

    def on_reload_multipathd_service_action(self, event):
        """Reload multipathd service."""
        event.log('Restarting multipathd service')
        subprocess.check_call(['systemctl', 'reload', self.MULTIPATHD_SERVICE])
        event.set_results({"success": "True"})

    # Additional functions
    def _check_mandatory_config(self):
        charm_config = self.framework.model.config
        missing_config = []
        for config in self.MANDATORY_CONFIG:
            if charm_config.get(config) is None:
                missing_config.append(config)
        if missing_config:
            self.unit.status = BlockedStatus("Missing mandatory configuration " +
                                             "option(s) {}".format(missing_config))
            return False
        return True

    def _defer_once(self, event):
        """Defer the given event, but only once."""
        notice_count = 0
        handle = str(event.handle)

        for event_path, _, _ in self.framework._storage.notices(None):
            if event_path.startswith(handle.split('[')[0]):
                notice_count += 1
                logging.debug("Found event: %s x %d", event_path, notice_count)

        if notice_count > 1:
            logging.debug("Not deferring %s notice count of %d", handle, notice_count)
        else:
            logging.debug("Deferring %s notice count of %d", handle, notice_count)
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
            initiator_name = subprocess.getoutput('/sbin/iscsi-iname')
            logging.warning('The hostname was not found in the initiator dictionary!' +
                            'The random iqn %s will be used for %s',
                            initiator_name, hostname)

        logging.info('Rendering initiatorname.iscsi')
        ctxt = {'initiator_name': initiator_name}
        template = tenv.get_template('initiatorname.iscsi.j2')
        rendered_content = template.render(ctxt)
        self.ISCSI_INITIATOR_NAME.write_text(rendered_content)

    def _iscsid_configuration(self, tenv, charm_config):
        ctxt = {
            'node_startup': charm_config.get('iscsi-node-startup'),
            'node_fastabort': charm_config.get('iscsi-node-session-iscsi-fastabort'),
            'node_session_scan': charm_config.get('iscsi-node-session-scan'),
            'auth_authmethod': charm_config.get('iscsi-node-session-auth-authmethod'),
            'auth_username': charm_config.get('iscsi-node-session-auth-username'),
            'auth_password': charm_config.get('iscsi-node-session-auth-password'),
            'auth_username_in': charm_config.get('iscsi-node-session-auth-username-in'),
            'auth_password_in': charm_config.get('iscsi-node-session-auth-password-in'),
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
        try:
            subprocess.check_call(['iscsiadm', '-m', 'discovery', '-t', 'sendtargets',
                                '-p', target + ':' + port])
        except subprocess.CalledProcessError:
            logging.exception('Iscsi discovery failed.')
            self.unit.status = BlockedStatus('Iscsi discovery failed against target')

    def _iscsiadm_login(self):
        # add check if already logged in, no error if it is.
        try:
            subprocess.check_call(['iscsiadm', '-m', 'node', '--login'])
        except subprocess.CalledProcessError:
            logging.exception('Iscsi login failed.')
            self.unit.status = BlockedStatus('Iscsi login failed against target')


if __name__ == "__main__":
    main(CharmIscsiConnectorCharm)
