# Iscsi Connector Charm

## Overview

This charm configures a unit to connect to an iscsi endpoint. It acts as a subordinate
charm, which can be deployed on any baremetal or virtual machine, alongside a main
charm.

This charm will:
- Generate an iscsi initiator name and put it in /etc/iscsi/initiatorname.iscsi
- Install the package multipath-tools
- Configure /etc/multipath.conf for the correct array
- Restart the services iscsid, open-iscsi
- Perform an iscsi discovery against a target
- Login to the target
- Restart the service multipathd

The user can input a initiator name dictionary in config.yaml if he wishes to use a
specific iqn for a specific unit. Also, the target IP and port are needed to perform
the discovery and login with iscsiadm. 


## Quickstart

To build the charm, use the Make actions. These actions use the charmcraft tool, so make sure to install it beforehand:
```
snap install charmcraft
make build
```
This will create the `iscsi-connector.charm` file and place it in the `.build` directory.

To deploy this subordinate charm on a ubuntu unit, deploy `cs:ubuntu` first.
```
juju add-model my-test-model
juju deploy cs:ubuntu --series bionic
juju deploy cs:iscsi-connector
juju relate ubuntu iscsi-connector
```

To edit the config of the target or the port:
```
juju config iscsi-connector target=<TARGET_IP> 
juju config iscsi-connector port=<PORT>
```

To restart services manually, two actions exist:
```
juju run-action --unit ubuntu/0 restart-iscsi-services
juju run-action --unit ubuntu/0 reload-multipathd-service
```

## Scaling

This charm will scale with the units it is related to. For example, if you scale the ubuntu application, and that the iscsi-connector is related to it, it will be deployed on each ubuntu units. 
```
juju add-unit ubuntu
juju remove-unit ubuntu/1
```

## Troubleshooting

If the iscsi discovery or login fails, compare the exit status number with the
iscsiadm documentation at https://linux.die.net/man/8/iscsiadm to understand the
cause of the error.


## Contact
 - Author: Camille Rodriguez <camille.rodriguez@canonical.com>
 - Maintainers: BootStack Charmers <bootstack-charmers@lists.canonical.com>
 - Bug Tracker: [here](https://bugs.launchpad.net/charm-iscsi-connector)
 