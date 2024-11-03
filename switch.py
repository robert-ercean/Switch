#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name
from data_structs import interface
from data_structs import CAM_table

cam = CAM_table()
switch_mac = None
switch_priority = None
# Each switch has a list of interfaces that holds each interface's information
# like the name, type (trunk or access, and eventually the vlan_id)
interfaces = {}

def print_frame(dest_mac, src_mac, ethertype, vlan_id, interface, length):
    print("-----------------------------------")
    print("Received frame of size {} on interface {}".format(length, interface), flush=True)
    p_dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
    p_src_mac = ':'.join(f'{b:02x}' for b in src_mac)
    print(f'Destination MAC: {p_dest_mac}')
    print(f'Source MAC: {p_src_mac}')
    print(f'EtherType: {hex(ethertype)}')
    print('VLAN_ID: ', vlan_id)

# Parses the switch's information from the config file
def parse_switch_info(switch_id):
    path = "configs/switch" + str(switch_id) + ".cfg"
   
    with open(path, "r") as file:
        # Read the first line before the parsing loop, to get the switches' priority
        line = file.readline().strip()
        switch_priority = int(line)
        count = 0
        # Parse the interfaces' info
        for line in file:
            line = line.strip()
            parts = line.split()
            name_str = parts[0]
            if name_str.startswith("r-"):   # not a trunk link then
                vlan_id = parts[1]
                link = interface(name_str, "A", int(vlan_id), count)
                interfaces[count] = link
            elif name_str.startswith("rr-"):    # trunk link then
                link = interface(name_str, "T", 0, count)   
                interfaces[count] = link
            count += 1

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    # dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8200 in network byte order is b'\x82\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id


def create_vlan_tag(data, vlan_id):
    # 0x8200 for the Ethertype for 802.1Q (mock value)
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    tag_data = struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)
    return data[0:12] + tag_data + data[12:]

def send_bdpu_every_sec():
    while True:
        # TODO Send BDPU every second if necessary
        time.sleep(1)

def send_from_tagged_frame(send_interface, recv_interface, data, length, recv_vlan_id):
    if (send_interface.id != recv_interface.id):
            if (send_interface.type == "A" and send_interface.vlan == recv_vlan_id):
                # remove the 802.1q header and send frame
                print(f"Sending on interface {send_interface!r} with removed 802.1q header")
                new_data = remove_tagged_header(data)
                new_length = length - 4
                send_to_link(send_interface.id, new_length, new_data)
            elif (send_interface.type == "T"):
                # keep the 802.1q header and send the frame
                print(f"sending in handle tagged on {send_interface!r} with kept 802.1q heeader")
                send_to_link(send_interface.id, length, data)


def send_from_untagged_frame (send_interface, recv_interface, data, length):
    if (send_interface.id != recv_interface.id):
        if (send_interface.type == "A" and send_interface.vlan == recv_interface.vlan):
            print(f"Sending on interface {send_interface!r}")
            send_to_link(send_interface.id, length, data)
        elif (send_interface.type == "T"):
            new_data = create_vlan_tag(data, recv_interface.vlan)
            new_length = length + 4
            print(f"Sending on interface {send_interface!r} with added 802.1q header")
            send_to_link(send_interface.id, new_length, new_data)

def handle_untagged_frame(recv_interface_id, data, length, dest_mac):
    recv_interface = interfaces[recv_interface_id]
    if (cam.entry_exists(dest_mac)):
        send_interface = cam.table[dest_mac]
        send_from_untagged_frame(send_interface, recv_interface, data, length)
    else:   # send broadcast
        print(f"(UNTAGGED BROADCAST)")
        for send_interface in interfaces.values():
            send_from_untagged_frame(send_interface, recv_interface, data, length)

def handle_tagged_frame(recv_interface_id, data, length, dest_mac, recv_vlan_id):
    recv_interface = interfaces[recv_interface_id]
    if (cam.entry_exists(dest_mac)):
        send_interface = cam.table[dest_mac]
        send_from_tagged_frame(send_interface, recv_interface, data, length, recv_vlan_id)
    else:   # send broadcast
        print(f"(TAGGED BROADCAST)")
        for send_interface in interfaces.values():
            send_from_tagged_frame(send_interface, recv_interface, data, length, recv_vlan_id)


def remove_tagged_header(old_frame):
    new_frame = old_frame[0:12] + old_frame[16:]
    return new_frame

def forward_frame(recv_interface_id, data, length, dest_mac, recv_vlan_id):
    tpid = int.from_bytes(data[12:14], byteorder='big')
    if tpid == 0x8200:
        # tagged frame
        handle_tagged_frame(recv_interface_id, data, length, dest_mac, recv_vlan_id)
    else:
        # untagged frame
        handle_untagged_frame(recv_interface_id, data, length, dest_mac)

def main():
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    switch_id = sys.argv[1]

    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces_count = range(0, num_interfaces)
    switch_mac = get_switch_mac()

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec)
    t.start()
    
    parse_switch_info(switch_id)

    while True:
        # Note that data is of type bytes([...]).
        # b1 = bytes([72, 101, 108, 108, 111])  # "Hello"
        # b2 = bytes([32, 87, 111, 114, 108, 100])  # " World"
        # b3 = b1[0:2] + b[3:4].
        interface_id, data, length = recv_from_any_link()

        dest_mac, src_mac, ethertype, recv_vlan_id = parse_ethernet_header(data)

        print_frame(dest_mac, src_mac, ethertype, recv_vlan_id, interface_id, length)
        cam.table[src_mac] = interfaces[interface_id]
        forward_frame(interface_id, data, length, dest_mac, recv_vlan_id)

if __name__ == "__main__":
    main()
