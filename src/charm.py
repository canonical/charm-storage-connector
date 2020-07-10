#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
# Copyright © 2020 Camille Rodriguez camille.rodriguez@canonical.com

"""Operator Charm main library."""
# Load modules from lib directory
import logging
import os
from pathlib import Path
import subprocess
from jinja2 import Environment, FileSystemLoader

import setuppath  # noqa:F401
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus
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

    ISCSI_SERVICES = ['iscsid', 'open-iscsi', 'multipathd']

    RESTART_MAP = {
        str(ISCSI_CONF): ISCSI_SERVICES,
        str(MULTIPATH_CONF): ISCSI_SERVICES
    }

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
        # Perform install tasks
        self.unit.status = MaintenanceStatus("Install complete")
        logging.info("Install of software complete")
        self.state.installed = True

    # def on_config_changed(self, event):
    #     """Handle config changed."""

    #     if not self.state.installed:
    #         logging.warning("Config changed called before install complete, deferring event: {}.".format(event.handle))
    #         self._defer_once(event)

    #         return

    #     if self.state.started:
    #         # Stop if necessary for reconfig
    #         logging.info("Stopping for configuration, event handle: {}".format(event.handle))
    #     # Configure the software
    #     logging.info("Configuring")
    #     self.state.configured = True


    def render_config(self, event):
        self.ISCSI_CONF_PATH.mkdir(
            exist_ok=True,
            mode=0o750)
        
        charm_config = self.fw_adapter.get_config()
        ctxt = {
            'target': charm_config.get('target', False),
        }
        tenv = Environment(loader=FileSystemLoader('templates'))
        template = tenv.get_template('iscsid.conf.j2')
        rendered_content = template.render(ctxt)
        self.ISCSI_CONF.write_text(rendered_content)
        logging.info('Rendering config')

        if self.state.started:
            logging.info('Restarting services')
            subprocess.check_call(['systemctl', 'restart', self.ISCSI_SERVICES[0]])

        logging.info("Setting started state")
        self.state.started = True
        self.unit.status = ActiveStatus()

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

    # -- Example relation interface for MySQL, not observed by default:
    def on_db_relation_changed(self, event):
        """Handle an example db relation's change event."""
        self.password = event.relation.data[event.unit].get("password")
        self.unit.status = MaintenanceStatus("Configuring database")
        if self.mysql.is_ready:
            event.log("Database relation complete")
        self.state._db_configured = True

    def on_example_action(self, event):
        """Handle the example_action action."""
        event.log("Hello from the example action.")
        event.set_results({"success": "true"})


if __name__ == "__main__":
    from ops.main import main
    main(CharmIscsiConnectorCharm)
