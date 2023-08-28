#! /usr/bin/env python3

"""Iscsi Connector Charm."""


import json
import logging
import os
import re
import socket
import subprocess
import time
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, List, Optional, cast

import apt  # pylint: disable=import-error
import yaml
from charmhelpers.contrib.openstack import deferred_events, policy_rcd
from charms.grafana_agent.v0.cos_agent import COSAgentProvider  # noqa
from jinja2 import Environment, FileSystemLoader
from ops.charm import (
    ActionEvent,
    CharmBase,
    ConfigChangedEvent,
    HookEvent,
    InstallEvent,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationCreatedEvent,
    RelationJoinedEvent,
    RelationDepartedEvent
    StartEvent,
    UpdateStatusEvent,
)
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from storage_connector import metrics_utils, nrpe_utils

import utils  # noqa

logger = logging.getLogger(__name__)


def check_deferred_restarts_queue(func: Callable) -> Callable:
    """Check the queue of deferred restarts and set correct status message.

    This wrapper can be used to decorate a method (primarily an event handler) from
    `StorageConnectorCharm` class. After decorated function is executed, this
    wrapper will clear the expired deferred restarts and attach correct status
    message if the unit is active.
    """

    @wraps(func)
    def wrapper(self: "StorageConnectorCharm", *args: Any, **kwargs: Any) -> Any:
        """Execute wrapped method and perform status assessment."""
        result = func(self, *args, **kwargs)

        # Handle manual service restarts outside the charm (e.g. run
        # `systemctl restart {service}` in the unit). It compares
        # each service's start time with its deferred events timestamp
        # and clears any deferred events which happened prior to this time
        try:
            deferred_events.check_restart_timestamps()
        except ValueError as err:
            logging.error("Cannot retrieve services' start time: %s", err)

        if isinstance(self.unit.status, ActiveStatus):
            self.unit.status = ActiveStatus(self.get_status_message())

        return result

    return wrapper


class StorageConnectorCharm(CharmBase):
    """Class representing this Operator charm."""

    _stored = StoredState()
    PACKAGES = ["multipath-tools"]

    ISCSI_CONF_PATH = Path("/etc/iscsi")
    ISCSI_CONF = ISCSI_CONF_PATH / "iscsid.conf"
    ISCSI_INITIATOR_NAME = ISCSI_CONF_PATH / "initiatorname.iscsi"
    MULTIPATH_CONF_DIR = Path("/etc/multipath")
    MULTIPATH_CONF_PATH = MULTIPATH_CONF_DIR / "conf.d"
    MULTIPATH_CONF_TEMPLATE = "storage-connector-multipath.conf.j2"

    ISCSI_SERVICES = ["iscsid", "open-iscsi"]
    MULTIPATHD_SERVICE = "multipathd"
    DEFERRED_SERVICES = ISCSI_SERVICES + [MULTIPATHD_SERVICE]

    VALID_STORAGE_TYPES = ["fc", "iscsi"]
    MANDATORY_CONFIG = {
        "iscsi": ["storage-type", "iscsi-target", "iscsi-port", "multipath-devices"],
        "fc": ["storage-type", "fc-lun-alias", "multipath-devices"],
    }
    EXPORTER_PORT = 9090

    def __init__(self, *args: Any) -> None:
        """Initialize charm and configure states and events to observe."""
        super().__init__(*args)

        # -- standard hook observation
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.config_changed, self._render_config)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.restart_services_action, self._on_restart_services_action)
        self.framework.observe(
            self.on.show_deferred_restarts_action, self._on_show_deferred_restarts_action
        )
        self.framework.observe(
            self.on.reload_multipathd_service_action, self._on_reload_multipathd_service_action
        )
        self.framework.observe(
            self.on.iscsi_discovery_and_login_action, self._on_iscsi_discovery_and_login_action
        )
        self.framework.observe(
            self.on.cos_agent_relation_joined, self._on_cos_agent_relation_joined
        )
        self.framework.observe(
            self.on.cos_agent_relation_departed, self._on_cos_agent_relation_departed
        )
        self.framework.observe(
            self.on.nrpe_external_master_relation_created,
            self._on_nrpe_external_master_relation_created,
        )
        self.framework.observe(
            self.on.nrpe_external_master_relation_changed,
            self._on_nrpe_external_master_relation_changed,
        )
        self.framework.observe(
            self.on.nrpe_external_master_relation_broken,
            self._on_nrpe_external_master_relation_broken,
        )
        self.cos_agent_provider = COSAgentProvider(
            self,
            metrics_endpoints=[{"path": "/", "port": self.EXPORTER_PORT}],
        )

        # -- initialize states --
        self._stored.set_default(
            installed=False,
            configured=False,
            started=False,
            fc_scan_ran_once=False,
            storage_type=self.model.config.get("storage-type"),
            mp_conf_name="juju-" + self.app.name + "-multipath.conf",
            grafana_agent_related=False,
            nrpe_related=False,
        )
        self.mp_path: Path = self.MULTIPATH_CONF_PATH / cast(str, self._stored.mp_conf_name)

    def _on_install(self, _: InstallEvent) -> None:
        """Handle install state."""
        self.unit.status = MaintenanceStatus("Installing charm software")
        if self._check_if_container():
            return

        self._check_mandatory_config()
        if isinstance(self.unit.status, BlockedStatus):  # type: ignore
            return  # type: ignore

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
        if self._stored.storage_type == "iscsi":
            for service in self.ISCSI_SERVICES:
                try:
                    logging.info("Enabling %s service", service)
                    subprocess.check_call(["systemctl", "enable", service])
                except subprocess.CalledProcessError:
                    logging.exception("Failed to enable %s.", service)

        self.unit.status = MaintenanceStatus("Install complete")
        logging.info("Install of software complete")
        self._stored.installed = True

    def _on_config_changed(self, _: ConfigChangedEvent) -> None:
        """Config-changed event handler."""
        if self._stored.nrpe_related is True:
            nrpe_utils.update_nrpe_config(self.model.config)  # type: ignore

    def _render_config(self, _: ConfigChangedEvent) -> None:
        """Render configuration templates upon config change."""
        if self._check_if_container():
            return

        self.unit.status = MaintenanceStatus("Validating charm configuration")
        self._check_mandatory_config()
        if isinstance(self.unit.status, BlockedStatus):  # type: ignore
            return  # type: ignore

        if self._stored.storage_type == "fc" and self._stored.fc_scan_ran_once is False:
            self._fc_scan_host()  # type: ignore
            if isinstance(self.unit.status, BlockedStatus):
                return

        self.unit.status = MaintenanceStatus("Rendering charm configuration")
        self._create_directories()

        tenv = Environment(loader=FileSystemLoader("templates"))

        self._configure_deferred_restarts()

        if self._stored.storage_type == "iscsi":
            self._configure_iscsi(tenv=tenv, event_name="config changed")
            if isinstance(self.unit.status, BlockedStatus):  # type: ignore
                return  # type: ignore  # pragma: nocover

        self._multipath_configuration(tenv)
        if isinstance(self.unit.status, BlockedStatus):  # type: ignore
            return  # type: ignore

        self._validate_multipath_config()
        if isinstance(self.unit.status, BlockedStatus):  # type: ignore
            return  # type: ignore

        self._reload_multipathd_service()

        logging.info("Setting started state")
        self._stored.started = True
        self._stored.configured = True
        self.unit.status = ActiveStatus(self.get_status_message())

    def _on_start(self, event: StartEvent) -> None:
        """Handle start state."""
        if self._stored.configured is False:
            logging.warning(  # type: ignore
                "Start called before configuration complete, deferring event: %s",
                event.handle,
            )
            self._defer_once(event)
            return
        self.unit.status = MaintenanceStatus("Starting charm software")
        # Start software
        self.unit.status = ActiveStatus(self.get_status_message())
        self._stored.started = True
        logging.info("Started")

    @check_deferred_restarts_queue
    def _on_update_status(self, _: UpdateStatusEvent) -> None:
        """Assess unit's status."""

    # Actions
    @check_deferred_restarts_queue
    def _on_restart_services_action(self, event: ActionEvent) -> None:
        """Restart charm managed services."""
        deferred_only = event.params["deferred-only"]
        services = event.params["services"].split()
        if deferred_only and services:
            event.set_results({"failed": "deferred-only and services are mutually exclusive"})
            return
        if not (deferred_only or services):
            event.set_results({"failed": "Please specify either deferred-only or services"})
            return
        if deferred_only:
            deferred_services = list(
                {
                    deferred_event.service
                    for deferred_event in deferred_events.get_deferred_restarts()
                }
            )
            if not deferred_services:
                event.set_results({"failed": "No deferred services to restart"})
                return
            event.log(
                "Restarting the following deferred services: {}".format(
                    ", ".join(deferred_services)
                )
            )
            self._restart_services(services=deferred_services)
        else:
            specified_services = list(
                {service for service in services if service in self.DEFERRED_SERVICES}
            )
            if not specified_services:
                event.set_results({"failed": "No valid services are specified."})
                return
            event.log(
                "Restarting the following services: {}".format(", ".join(specified_services))
            )
            self._restart_services(services=specified_services)

        event.set_results({"success": "True"})

    def _on_show_deferred_restarts_action(self, event: ActionEvent) -> None:
        """Get and display the list of service multipathd service."""
        output = []
        for deferred_event in deferred_events.get_deferred_restarts():
            output.append(
                "{} {} {} {}".format(
                    str(datetime.utcfromtimestamp(deferred_event.timestamp)),
                    "+0000 UTC",
                    deferred_event.service.ljust(40),
                    deferred_event.reason,
                )
            )
        output.sort()
        event.set_results(
            {"deferred-restarts": "{}".format(yaml.dump(output, default_flow_style=False))}
        )

    def _on_reload_multipathd_service_action(self, event: ActionEvent) -> None:
        """Reload multipathd service."""
        event.log("Reloading multipathd service")
        self._reload_multipathd_service()
        event.set_results({"success": "True"})

    def _on_iscsi_discovery_and_login_action(self, event: ActionEvent) -> None:
        """Run discovery and login against iscsi target(s)."""
        self._iscsi_discovery_and_login()
        event.set_results({"success": "True"})

    # Additional functions
    def get_status_message(self) -> str:
        """Set unit status to active with correct status message.

        Check if any services need restarts. If yes, append the queue of
        such services to the status message.
        """
        status_message = "Unit is ready"
        if not self.model.config.get("enable-auto-restarts"):
            deferred_restarts = list(
                {
                    event.service
                    for event in deferred_events.get_deferred_restarts()
                    if event.policy_requestor_name == self.app.name
                }
            )
            if deferred_restarts:
                svc_msg = "Services queued for restart: {}".format(
                    ", ".join(sorted(deferred_restarts))
                )
                status_message = "{}. {}".format(status_message, svc_msg)

        return status_message

    def _defer_service_restart(self, services: List[str], reason: Optional[str] = None) -> None:
        """Defer service restarts and record this event."""
        for service in services:
            deferred_events.save_event(
                deferred_events.ServiceEvent(
                    timestamp=round(time.time()),
                    service=service,
                    reason="Charm event: {}".format(reason),
                    action="restart",
                )
            )

    def _restart_services(self, services: Optional[List[str]] = None) -> None:
        """Restart iscsid and open-iscsi services."""
        if services:
            for service in services:
                logging.info("Restarting %s service", service)
                try:
                    subprocess.check_call(["systemctl", "restart", service])
                except subprocess.CalledProcessError:
                    logging.exception("An error occured while restarting %s.", service)

            # Clear deferred restart events
            deferred_events.clear_deferred_restarts(services)

            # If any iscsi services restarted and iscsi-discovery-and-login config is
            # set to true, run iscsiadm discovery and login.
            if any(svc in self.ISCSI_SERVICES for svc in services) and self.model.config.get(
                "iscsi-discovery-and-login"
            ):
                self._iscsi_discovery_and_login()

    def _reload_multipathd_service(self) -> None:
        """Reload multipathd service."""
        logging.info("Reloading multipathd service")
        try:
            subprocess.check_call(["systemctl", "reload", self.MULTIPATHD_SERVICE])
        except subprocess.CalledProcessError:
            logging.exception("%s", "An error occured while reloading the multipathd service.")

    def _configure_iscsi(self, tenv: Environment, event_name: str) -> None:
        self._iscsi_initiator(tenv)
        self._iscsid_configuration(tenv)

        charm_config = self.model.config
        if charm_config.get("enable-auto-restarts") or self._stored.started is False:
            self._restart_services(services=self.ISCSI_SERVICES)
        else:
            self._defer_service_restart(services=self.ISCSI_SERVICES, reason=event_name)

    def _check_mandatory_config(self) -> None:
        """Check whether mandatory configs are provided."""
        charm_config = self.model.config

        if charm_config["storage-type"] in self.VALID_STORAGE_TYPES:
            if (
                self._stored.storage_type == "None"
                or self._stored.storage_type not in self.VALID_STORAGE_TYPES
            ):
                # allow user to change storage type only if initial entry was incorrect
                self._stored.storage_type = charm_config["storage-type"].lower()
                logging.debug("Storage type updated to %s", self._stored.storage_type)
            elif charm_config["storage-type"] != self._stored.storage_type:
                self.unit.status = BlockedStatus(
                    "Storage type cannot be changed after deployment."
                )
                return
        else:
            self.unit.status = BlockedStatus(
                "Missing/Invalid storage type. Valid options are 'iscsi' or 'fc'."
            )
            return

        mandatory_config = self.MANDATORY_CONFIG[cast(str, self._stored.storage_type)]
        missing_config = []
        for config in mandatory_config:
            if charm_config.get(config) is None:
                missing_config.append(config)
        if missing_config:
            self.unit.status = BlockedStatus(
                "Missing mandatory configuration " + "option(s) {}".format(missing_config)
            )

    def _defer_once(self, event: HookEvent) -> None:
        """Defer the given event, but only once."""
        notice_count = 0
        handle = str(event.handle)

        for event_path, _, _ in self.framework._storage.notices(None):  # pylint: disable=W0212
            if event_path.startswith(handle.split("[", maxsplit=1)[0]):
                notice_count += 1
                logging.debug("Found event: %s x %d", event_path, notice_count)

        if notice_count > 1:
            logging.debug(  # pragma: nocover
                "Not deferring %s notice count of %d", handle, notice_count
            )
        else:
            logging.debug("Deferring %s notice count of %d", handle, notice_count)
            event.defer()

    def _create_directories(self) -> None:
        self.MULTIPATH_CONF_DIR.mkdir(exist_ok=True, mode=0o750)
        self.MULTIPATH_CONF_PATH.mkdir(exist_ok=True, mode=0o750)
        if self._stored.storage_type == "iscsi":
            self.ISCSI_CONF_PATH.mkdir(exist_ok=True, mode=0o750)

    def _iscsi_initiator(self, tenv: Environment) -> None:
        charm_config = self.model.config
        initiator_name = None
        hostname = socket.getfqdn()
        initiators = charm_config.get("initiator-dictionary")
        if initiators:
            # search for hostname and create context
            initiators_dict = json.loads(initiators)
            if hostname in initiators_dict.keys():
                initiator_name = initiators_dict[hostname]

        if not initiator_name:
            initiator_name = subprocess.getoutput("/sbin/iscsi-iname")
            logging.warning(
                "The hostname was not found in the initiator dictionary! "
                "The random iqn %s will be used for %s",
                initiator_name,
                hostname,
            )

        logging.info("Rendering initiatorname.iscsi")
        ctxt = {"initiator_name": initiator_name}
        template = tenv.get_template("initiatorname.iscsi.j2")
        rendered_content = template.render(ctxt)
        self.ISCSI_INITIATOR_NAME.write_text(rendered_content)

    def _iscsid_configuration(self, tenv: Environment) -> None:
        charm_config = self.model.config
        ctxt = {
            "node_startup": charm_config.get("iscsi-node-startup"),
            "node_fastabort": charm_config.get("iscsi-node-session-iscsi-fastabort"),
            "node_session_scan": charm_config.get("iscsi-node-session-scan"),
            "auth_authmethod": charm_config.get("iscsi-node-session-auth-authmethod"),
            "auth_username": charm_config.get("iscsi-node-session-auth-username"),
            "auth_password": charm_config.get("iscsi-node-session-auth-password"),
            "auth_username_in": charm_config.get("iscsi-node-session-auth-username-in"),
            "auth_password_in": charm_config.get("iscsi-node-session-auth-password-in"),
        }
        logging.info("Rendering iscsid.conf template.")
        template = tenv.get_template("iscsid.conf.j2")
        rendered_content = template.render(ctxt)
        self.ISCSI_CONF.write_text(rendered_content)
        self.ISCSI_CONF.chmod(0o600)

    def _multipath_configuration(self, tenv: Environment) -> None:
        charm_config = self.model.config
        ctxt = {}
        multipath_sections = ["defaults", "devices", "blacklist"]
        for section in multipath_sections:
            config = charm_config.get("multipath-" + section)
            if config:
                logging.info("Gather information for the multipaths section %s", section)
                logging.debug("multipath-%s data: %s", section, config)
                try:
                    ctxt[section] = json.loads(config)
                except json.JSONDecodeError as exception:
                    logging.info(
                        "An exception has occured. Please verify the format \
                                  of the multipath config option %s. \
                                  Traceback: %s",
                        section,
                        exception,
                    )
                    self.unit.status = BlockedStatus(
                        "Exception occured during the multipath \
                        configuration. Please check logs."
                    )
                    return
            else:
                logging.debug("multipath-%s is empty.", section)  # pragma: nocover

        if self._stored.storage_type == "fc":
            wwid = self._retrieve_multipath_wwid()
            if not wwid:
                self.unit.status = BlockedStatus(
                    "No WWID was found. Please check multipath status and logs."
                )
                return
            alias = charm_config.get("fc-lun-alias")
            ctxt["multipaths"] = {"wwid": wwid, "alias": alias}

        logging.debug("Rendering multipath json template")
        template = tenv.get_template(self.MULTIPATH_CONF_TEMPLATE)
        rendered_content = template.render(ctxt)
        self.mp_path.write_text(rendered_content)
        self.mp_path.chmod(0o600)

    def _iscsi_discovery_and_login(self) -> None:
        """Run iscsiadm discovery and login against targets."""
        charm_config = self.model.config
        target = str(charm_config.get("iscsi-target"))
        port = str(charm_config.get("iscsi-port"))
        logging.info("Launching iscsiadm discovery and login against targets")

        try:
            subprocess.check_call(
                ["iscsiadm", "-m", "discovery", "-t", "sendtargets", "-p", target + ":" + port]
            )
        except subprocess.CalledProcessError:
            logging.exception("Iscsi discovery failed.")
            return

        try:
            subprocess.check_output(
                ["iscsiadm", "-m", "node", "--login"], stderr=subprocess.STDOUT
            )
        except subprocess.CalledProcessError as err:
            logging.exception("Iscsi login failed. \n%s", err.output.decode("utf-8"))

    def _fc_scan_host(self) -> None:
        hba_adapters = subprocess.getoutput("ls /sys/class/scsi_host")
        logging.debug("hba_adapters: %s", hba_adapters)
        if not hba_adapters:
            logging.info("No scsi devices were found. Scan aborted")
            self.unit.status = BlockedStatus("No scsi devices were found. Scan aborted")
            return

        for adapter in hba_adapters.split("\n"):
            try:
                logging.info("Running scan of the host to discover LUN devices.")
                file_name = "/sys/class/scsi_host/" + adapter + "/scan"
                with open(file_name, "w", encoding="utf-8") as file:
                    file.write("- - -")
            except OSError:
                logging.exception("An error occured during the scan of the hosts.")
                self.unit.status = BlockedStatus("Scan of the HBA adapters failed on the host.")
                return
        self._stored.fc_scan_ran_once = True

    def _retrieve_multipath_wwid(self) -> Optional[str]:
        logging.info("Retrive device WWID via multipath -ll")
        result = subprocess.getoutput("multipath -ll")
        wwid = re.findall(r"\(([\d\w]+)\)", result)
        logging.info("WWID is %s", wwid)
        return wwid[0] if wwid else None

    def _validate_multipath_config(self) -> None:
        result = subprocess.getoutput("multipath -ll")
        error = re.findall(r"(invalid\skeyword:\s\w+)", result)
        if error:
            logging.info("Configuration is probably malformed. See output below %s", result)
            self.unit.status = BlockedStatus("Multipath conf error: {}".format(error))

    def _check_if_container(self) -> bool:
        """Check if the charm is being deployed on a container host."""
        if utils.is_container():
            self.unit.status = BlockedStatus("This charm is not supported on containers.")
            logging.error("This charm is not supported on containers. Stopping execution.")
            return True
        return False

    def _configure_deferred_restarts(self) -> None:
        """Set up deferred restarts in policy-rc.d."""
        policy_rcd.install_policy_rcd()
        os.chmod("/var/lib/charm/{}/policy-rc.d".format(self.app.name), 0o755)

        charm_config = self.model.config
        if charm_config.get("enable-auto-restarts"):
            policy_rcd.remove_policy_file()
        else:
            blocked_actions = ["stop", "restart", "try-restart"]
            for svc in self.DEFERRED_SERVICES:
                policy_rcd.add_policy_block(svc, blocked_actions)

    def _on_cos_agent_relation_joined(
        self, event: RelationJoinedEvent
    ) -> None:
        """Install and start exporter when joining cos-agent relation."""
        self.unit.status = MaintenanceStatus("Installing exporter")
        metrics_utils.install_exporter(self.model.resources)

        self._stored.grafana_agent_related = True
        self.unit.status = ActiveStatus(self.get_status_message())

    def _on_cos_agent_relation_departed(
        self, event: RelationDepartedEvent
    ) -> None:
        """Uninstall exporter when departing from cos-agent relation."""
        if self._stored.nrpe_related is False:
            self.unit.status = MaintenanceStatus("Removing exporter")  # type: ignore
            metrics_utils.uninstall_exporter()

        self._stored.grafana_agent_related = False
        self.unit.status = ActiveStatus(self.get_status_message())

    def _on_nrpe_external_master_relation_created(
        self, event: RelationCreatedEvent  # pylint: disable=unused-argument
    ) -> None:
        """Relation-created event handler for nrpe-external-master."""
        self.unit.status = MaintenanceStatus("Installing exporter")
        metrics_utils.install_exporter(self.model.resources)

        self._stored.nrpe_related = True
        self.unit.status = ActiveStatus(self.get_status_message())

    def _on_nrpe_external_master_relation_changed(
        self, event: RelationChangedEvent  # pylint: disable=unused-argument
    ) -> None:
        """Relation-changed event handler for nrpe-external-master."""
        nrpe_utils.update_nrpe_config(self.model.config)

    def _on_nrpe_external_master_relation_broken(
        self, event: RelationBrokenEvent  # pylint: disable=unused-argument
    ) -> None:
        """Relation-broken event handler for nrpe-external-master."""
        if self._stored.grafana_agent_related is False:
            self.unit.status = MaintenanceStatus("Removing exporter software")  # type: ignore
            metrics_utils.uninstall_exporter()

        self.unit.status = MaintenanceStatus("Uninstalling nrpe scripts")
        nrpe_utils.unsync_nrpe_files()

        self._stored.nrpe_related = False
        self.unit.status = ActiveStatus(self.get_status_message())


if __name__ == "__main__":  # pragma: nocover
    main(StorageConnectorCharm)
