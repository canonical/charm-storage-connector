# Storage Connector Charm

## Overview

This charm configures a unit to connect to a storage endpoint, either iSCSI or Fibre Channel. 
It acts as a subordinate charm, which can be deployed on any bare metal or virtual machine, 
alongside a main charm. It is not supported in containers due to lack of ability for lxd 
containers to access iSCSI and Fibre Channel hardware of the underlying kernel. 

If you configure this charm for iSCSI, this charm will:
- Generate an iSCSI initiator name and put it in /etc/iscsi/initiatorname.iscsi
- Install the package multipath-tools
- Configure multipath under /etc/multipath/conf.d directory
- Restart the services iscsid, open-iscsi
- Perform an iSCSI discovery against a target
- Login to the target
- Reload and restart the service multipathd

If you configure it for Fibre Channel, this charm will:
- Install the package multipath-tools
- Scan the host for HBA adapters
- Retrieve the WWID for the Fibre Channel connection
- Configure multipath under /etc/multipath/conf.d directory
- Reload and restart multipathd.service

Please note that the Fiber Channel option currently supports only one device. 

If iSCSI, the user can input a initiator name dictionary in config.yaml if they wish to use a
specific IQN for a specific unit. Also, the target IP and port are needed to perform
the discovery and login with iscsiadm. 

For Fibre Channel, the user can choose the device alias to be used when mapping the disk.
See the option "fc-lun-alias" for further details.


## Quickstart

To build the charm, use the Make actions. These actions use the charmcraft tool, so make sure to install it beforehand:
```
snap install charmcraft
make build
```
This will create the `storage-connector.charm` file and place it in the `.build` directory.

To deploy this subordinate charm on an ubuntu unit, deploy `cs:ubuntu` first , or other principal
charm of your choosing (i.e nova-compute, mysql, etc.).
```
juju add-model my-test-model
juju deploy cs:ubuntu --series focal
juju deploy cs:storage-connector
```

### To configure this charm for iSCSI, do the following.

Edit the config of the target or the port:
```
juju config storage-connector \
    storage-type='iscsi' \
    iscsi-target=<TARGET_IP> \
    iscsi-port=<PORT>
```

To restart services manually, two actions exist:
```
juju run-action --unit ubuntu/0 restart-iscsi-services
juju run-action --unit ubuntu/0 reload-multipathd-service
```

### To configure this charm for Fibre Channel, do the following.

Set the storage type to FC and the various configuration parameters:
```
juju config storage-connector storage-type='fc' \
    fc-lun-alias='data1' \
    multipath-defaults='{"user_friendly_names":"yes", "find_multipaths":"yes", "polling_interval":"10"}' \
    multipath-devices='{"vendor":"PURE", "product":"FlashArray", "fast_io_fail_tmo":"10", "path_selector":"queue-length 0", "path_grouping_policy":"group_by_prio", "rr_min_io":"1", "path_checker":"tur", "fast_io_fail_tmo":"1", "dev_loss_tmo":"infinity", "no_path_retry":"5", "failback":"immediate", "prio":"alua", "hardware_handler":"1 alua", "max_sectors_kb":"4096"}'
```

### After the configuration is set, relate the charm to ubuntu

This will apply the configuration to hosts running the "ubuntu" application.
```
juju relate ubuntu storage-connector
```

## Scaling

This charm will scale with the units it is related to. For example, if you scale the 
ubuntu application, and the storage-connector is related to it, it will be deployed on each 
newly deployed ubuntu unit. 
```
juju add-unit ubuntu
juju remove-unit ubuntu/1
```

## Troubleshooting

If the iSCSI discovery or login fails, compare the exit status number with the
iscsiadm documentation at https://linux.die.net/man/8/iscsiadm to understand the
cause of the error.


## Contact
 - Author: Camille Rodriguez <camille.rodriguez@canonical.com>
 - Maintainers: BootStack Charmers <bootstack-charmers@lists.canonical.com>
 - Bug Tracker: [here](https://bugs.launchpad.net/charm-storage-connector)
 