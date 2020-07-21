# charm-iscsi-connector Charm

Overview
--------

This charm configures a unit to connect to an iscsi endpoint. It act as a subordinate charm, which can be
deployed on any baremetal or virtual machine, alongside a main charm.

This charm will:
- Generate an iscsi initiator name and put it in /etc/iscsi/initiatorname.iscsi
- Install the package multipath-tools
- Configure /etc/multipath.conf for the correct array
- Restart the services iscsid, open-iscsi
- Perform an iscsi discovery against a target
- Login to the target
- Restart the service multipathd

The user can input a initiator name dictionary in config.yaml if he wishes to use a specific iqn for a specific
unit. Also, the target IP and port are needed to perform the discovery and login with iscsiadm. 


Quickstart
----------

To build the charm, one needs to use the charmcraft tool. 
`charmcraft build`
Alternatively, use a virtual environment to build this charm. Here is an example with `fades`:
`fades -r requirements.txt -x python -m charmcraft build --from <CHARM_PATH>`

This generates a file called iscsi-connector.charm

To deploy it on a ubuntu unit, deploy cs:ubuntu first.
`juju add-model my-test-model`
`juju deploy cs:ubuntu --series bionic`
`juju deploy ./iscsi-connector.charm`
`juju relate ubuntu iscsi-connector`

To edit the config of the target or the port:
`juju config iscsi-connector target=<TARGET_IP> port=<PORT>`

To restart services manually, two actions exist:
`juju run-action --unit ubuntu/0 restart-iscsi-services`
`juju run-action --unit ubuntu/0 restart-multipathd-service`

Scaling
-------

Provide instructions for scaling this charm.

Contact
-------
 - Author: Camille Rodriguez <camille.rodriguez@canonical.com>
 - Bug Tracker: [here](https://discourse.juju.is/c/charming)
 