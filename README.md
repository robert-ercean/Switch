# Overview

- **1 2 3** 

- This project implements a **Layer 2 Virtual Switch**  within a virtual topology created using *mininet* with support of core functionalities such as the **CAM Table**, **VLAN isolation** (*802.1q protocol*) and the **STP Protocol**.

## Topology
- As mentioned above, multiple switches share the same implementation within a virtual topology created using *mininet*. The switches are tested by running the *test scripts* inside the folder `checker`, or by manually sending `control packets` with `ICMP` or similar protocols. The topology used for testing the functionalities can be seen below. 

## CAM Table

- Each switch maintains a local `CAM Table` used to store associations between *MAC Addresses* and *physical interfaces*. Whenever a switch receives a frame through one of its interfaces, before any parsing and forwarding decisions of the frame being made, the switch updates the `CAM Table entry` of the respective interface.
### CAM Table structure
- The CAM Table is built using a class defined in `data_structs.py`. The table is a `hashmap` (the only field of this class) with associations between MAC Addreses(**keys**) and Interface ID (**values**).
- The class also exposes a method for checking the existence of a certain key (*MAC Address*) and *debug methods* such as printing the current CAM Table.


## VLAN Support

- The switches have VLAN support, providing a way to isolate traffic between different departments in the same LAN.
- VLAN's are identified by `VLAN ID's`, unique within each switch's configuration.
- Each interface is stored as an object of type class `Interface`, defined in `data_structs.py`, with fields:

| Field Name |  Data Type    |     Meaning |
| ----------- | --- |----------- |
| ID | int | The port's unique ID within the switch's config|
| VLAN ID | int | The port's VLAN ID|
| Name | str | The port's name (used for debugging purposes) |
| Type | str | Describes whether a port is of type `ACCESSS` or `TRUNK`|

- **This implementation has no support for Native VLANs**
- While parsing the config file, it is important to take notice that if an interface is detected of being of type `TRUNK`, its associated *Interface object* will have the VLAN ID field set to `0`.
- First and foremost, before being ready to receive / forward any frames, the switch's configuration is parsed within the function `parse_switch_info()` that populates the fields of each `Interface class object.`
- After parsing the critical info, the frame handling and forwarding process begins.

### Frame handling
- When a frame is received, and the `frame is not BPDU`:

    - If tagged: The frame’s VLAN ID is compared with the destination port's VLAN configuration.
    - If untagged: The VLAN ID is determined by the receiving port’s configuration.
    - The receiving port's information is parsed within the function `parse_ethernet_header()`

- For outgoing frames:
    - If destined for an access port: The VLAN tag is stripped if the port’s VLAN matches the frame’s VLAN.
    - If destined for a trunk port: The VLAN tag is kept to preserve VLAN information.
    - Forwarding decisions are being made within `send_from_tagged_frame()` or `send_from_untagged_frame()`
    - If we have a direct association between the `Dest MAC` and a certain interface, we sent it to that interface if the above criterias are matched, if not, `we broadcast the frame in the same VLAN`

### Custom 802.1Q Tagging Implementation
- Some changes are made to the standard 802.1q header to avoid issues.
- Use 0x8200 as the TPID to avoid conflicts with Linux’s default VLAN filtering.
- Set fields PCP and DEI to 0.

## Custom STP Protocol

- For easier handling of STP and because each switch within the testing vitual topology will have support of this, a custom header is created for easier maneuvering of the frames:
# MAC_MULTICAST(6 BYTES) | OWN_BID (8 BYTES) | ROOT_BRIDGE_ID (8 BYTES) | ROOT_PATH_COST(4 BYTES)

| Field Name |  Data Size    |  Meaning |
| ----------- | --- |-----------|
| MAC_MULTICAST | 6 BYTES | The port's unique ID within the switch's config|
| OWN_BID | 8 BYTES | The port's VLAN ID|
| ROOT_BRIDGE_ID | 8 BYTES | The port's name (used for debugging purposes) |
| ROOT_PATH_COST | 4 BYTES | Describes whether a port is of type `ACCESSS` or `TRUNK`|
