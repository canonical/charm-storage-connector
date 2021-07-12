#! /usr/bin/env python3

"""Iscsi Connector Charm."""

import json
import logging
import socket
import subprocess
from pathlib import Path

import apt

from jinja2 import Environment, FileSystemLoader

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

import utils


logger = logging.getLogger(__name__)


class StorageConnectorCharm(CharmBase):
    """Class representing this Operator charm."""

    _stored = StoredState()
    PACKAGES = ['multipath-tools']
    # FC_PACKAGES = ['sysfsutils']

    ISCSI_CONF_PATH = Path('/etc/iscsi')
    ISCSI_CONF = ISCSI_CONF_PATH / 'iscsid.conf'
    ISCSI_INITIATOR_NAME = ISCSI_CONF_PATH / 'initiatorname.iscsi'
    MULTIPATH_CONF_DIR = Path('/etc/multipath')
    MULTIPATH_CONF_PATH = MULTIPATH_CONF_DIR / 'conf.d'
    MULTIPATH_CONF = MULTIPATH_CONF_PATH / 'multipath.conf'

    ISCSI_SERVICES = ['iscsid', 'open-iscsi']
    MULTIPATHD_SERVICE = 'multipathd'

    ISCSI_MANDATORY_CONFIG = ['target', 'port']
    FC_MANDATORY_CONFIG = ['fc-lun-names']

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
        self._stored.set_default(installed=False)
        self._stored.set_default(configured=False)
        self._stored.set_default(started=False)
        # -- base values --
        self._stored.set_default(
            storage_type=self.framework.model.config.get('storage-type').lower()
        )

    def on_install(self, event):
        """Handle install state."""
        self.unit.status = MaintenanceStatus("Installing charm software")
        if self.check_if_container():
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
        if self._stored.storage_type == 'iscsi':
            for service in self.ISCSI_SERVICES:
                try:
                    logging.info('Enabling %s service', service)
                    subprocess.check_call(['systemctl', 'enable', service])
                except subprocess.CalledProcessError:
                    logging.exception('Unable to enable %s.', service)
        elif self._stored.storage_type == 'fc':
            # TODO: is there any service to install for FC
            print('to complete')

        self.unit.status = MaintenanceStatus("Install complete")
        logging.info("Install of software complete")
        self._stored.installed = True

    def render_config(self, event):
        """Render configuration templates upon config change."""
        if self.check_if_container():
            return

        if not self._check_mandatory_config():
            return

        self.unit.status = MaintenanceStatus("Rendering charm configuration")
        self._create_directories()

        charm_config = self.framework.model.config
        tenv = Environment(loader=FileSystemLoader('templates'))

        self._multipath_configuration(tenv, charm_config)
        if self._stored.storage_type == 'iscsi':
            self._iscsi_initiator(tenv, charm_config)
            self._iscsid_configuration(tenv, charm_config)
            logging.info('Restarting iscsi services')
            for service in self.ISCSI_SERVICES:
                try:
                    logging.info('Restarting %s service', service)
                    subprocess.check_call(['systemctl', 'restart', service])
                except subprocess.CalledProcessError:
                    logging.exception('An error occured while restarting %s.', service)

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
        self._stored.started = True
        self._stored.configured = True
        self.unit.status = ActiveStatus("Unit is ready")

    def on_start(self, event):
        """Handle start state."""
        if not self._stored.configured:
            logging.warning("Start called before configuration complete, " +
                            "deferring event: %s", event.handle)
            self._defer_once(event)
            return
        self.unit.status = MaintenanceStatus("Starting charm software")
        # Start software
        self.unit.status = ActiveStatus("Unit is ready")
        self._stored.started = True
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
        if self._stored.storage_type == "fc":
            if charm_config.get('fc-wwnn') and not charm_config.get('fc-wwpn'):
                self.FC_MANDATORY_CONFIG.append('fc-wwnn')
            elif not charm_config.get('fc-wwnn') and charm_config.get('fc-wwpn'):
                self.FC_MANDATORY_CONFIG.append('fc-wwpn')
            else:
                self.unit.status = BlockedStatus("For FC storage type, either fc-wwpn \
                                   or fc-wwnn must be provided, but not both.")
                return False
            mandatory_config = self.FC_MANDATORY_CONFIG
        elif self._stored.storage_type == "iscsi":
            mandatory_config = self.ISCSI_MANDATORY_CONFIG
        else:
            self.unit.status = BlockedStatus("Missing or incorrect storage type")
            return False

        missing_config = []
        for config in mandatory_config:
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

    def _create_directories(self):
        self.MULTIPATH_CONF_DIR.mkdir(
            exist_ok=True,
            mode=0o750)
        self.MULTIPATH_CONF_PATH.mkdir(
            exist_ok=True,
            mode=0o750)
        if self._stored.storage_type == 'iscsi':
            self.ISCSI_CONF_PATH.mkdir(
                exist_ok=True,
                mode=0o750)

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
        multipath_blacklist = charm_config.get('multipath-blacklist')
        if multipath_conf_devices:
            conf_devices = json.loads(multipath_conf_devices)
            ctxt['conf_devices'] = conf_devices
        if multipath_blacklist:
            conf_blacklist = json.loads(multipath_blacklist)
            ctxt['conf_blacklist'] = conf_blacklist
        template = tenv.get_template('multipath.conf.j2')
        rendered_content = template.render(ctxt)
        self.MULTIPATH_CONF.write_text(rendered_content)
        self.MULTIPATH_CONF.chmod(0o644)

    def _iscsiadm_discovery(self, charm_config):
        target = charm_config.get('iscsi-target')
        port = charm_config.get('iscsi-port')
        logging.info('Launching iscsiadm discovery against target')
        try:
            subprocess.check_call(['iscsiadm', '-m', 'discovery', '-t', 'sendtargets',
                                  '-p', target + ':' + port])
        except subprocess.CalledProcessError:
            logging.exception('Iscsi discovery failed.')
            self.unit.status = BlockedStatus(
                'Iscsi discovery failed against target'
            )

    def _iscsiadm_login(self):
        # add check if already logged in, no error if it is.
        try:
            subprocess.check_call(['iscsiadm', '-m', 'node', '--login'])
        except subprocess.CalledProcessError:
            logging.exception('Iscsi login failed.')
            self.unit.status = BlockedStatus(
                'Iscsi login failed against target'
            )

    def _fc_scan_host(self):
        hba_adapters = subprocess.getoutput('ls /sys/class/fc_host').split('\n')
        # number_hba_adapters = len(hba_adapters)
        for adapter in hba_adapters:
            try:
                logging.info('Running scan of the host to discover LUN devices.')
                subprocess.check_call(['echo', '"1"', '>',
                                       '/sys/class/fc_host/' + adapter + '/issue_lip'])
                subprocess.check_call(['echo', '"- - -"', '>',
                                       '/sys/class/scsi_host/' + adapter + '/scan'])
            except subprocess.CalledProcessError:
                logging.exception('An error occured during the scan of the hosts.')
                self.unit.status = BlockedStatus(
                    'Scan of the HBA adapters failed on the host.'
                )

    def _retrieve_multipath_status(self):
        result = subprocess.getoutput(['multipath', '-ll'])
        logging.info('Retrive multipath status')
        logging.info(result)

    def _create_partition_for_alias(self):
        print('tbc')

    def check_if_container(self):
        """Check if the charm is being deployed on a container host."""
        if utils.is_container():
            self.unit.status = BlockedStatus(
                'This charm is not supported on containers.'
            )
            logging.debug(
                'This charm is not supported on containers. Stopping execution.'
            )
            return True
        return False


if __name__ == "__main__":
    main(StorageConnectorCharm)
