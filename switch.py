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

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    #dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
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

def create_vlan_tag(vlan_id):
    # 0x8200 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def send_bdpu_every_sec():
    while True:
        # TODO Send BDPU every second if necessary
        time.sleep(1)

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
                link = interface(name_str, "A", vlan_id, count)
                interfaces[count] = link
            elif name_str.startswith("rr-"):    # trunk link then
                link = interface(name_str, "T", 0, count)   
                interfaces[count] = link
            count += 1

def is_broadcast(mac):
    if mac == "ff:ff:ff:ff:ff:ff":
        return True
    else:
        return False


def handle_unicast(recv_interface_id, data, length, dest_mac, src_mac, ethertype, vlan_id):
    recv_interface_type = interfaces[recv_interface_id].type
    if (cam.entry_exists(dest_mac)):
        sent_interface = cam.table[dest_mac]
        if sent_interface.type == "A":    # access port, send frame without the 802.1q header
            if recv_interface_type == "T":      # remove the existing 802.1q header
                # Reconstruct the header and remove the 4 bytes length of the 802.1q header
                data = remove_tagged_header(data)
                length -= 4
                send_to_link(sent_interface.id, length, data)
            elif recv_interface_type == "A":    # there is no existing 802.1q header, just send the frame
                send_to_link(sent_interface.id, length, data)
        elif sent_interface.type == "T":        # trunk port, send frame with 802.1q header
            if recv_interface_type == "T":      # 802.1q header already added, just send the frame
                send_to_link(sent_interface.id, length, data)
            elif recv_interface_type == "A":     # there is no existing 802.1q header, add it
                data = data[0:12] + create_vlan_tag(sent_interface.vlan) + data[12:]
                send_to_link(sent_interface.id, length, data)
    else:
        handle_broadcast(recv_interface_id, data, length, dest_mac, src_mac, ethertype, vlan_id)

def handle_broadcast(recv_interface_id, data, length, dest_mac, src_mac, ethertype, recv_vlan_id):
    # store the receving interface type, so we can know if there is an existing
    # 802.1q header since it needs to be removed because we're sending to an 
    # access port or added if we're sending to a trunk port
    recv_interface_type = interfaces[recv_interface_id].type

    for sent_interface in interfaces.values():
        # ignore the port form which we got the frame and the ports that dont belong in the same vlan as the recv port
        if sent_interface.id != recv_interface_id and (sent_interface.type == "T" or recv_vlan_id == sent_interface.vlan): 
            if sent_interface.type == "A":    # access port, send frame without the 802.1q header
                if recv_interface_type == "T":      # remove the existing 802.1q header
                    # Reconstruct the header and remove the 4 bytes length of the 802.1q header
                    data = remove_tagged_header(data)
                    length -= 4
                    send_to_link(sent_interface.id, length, data)
                elif recv_interface_type == "A":    # there is no existing 802.1q header, just send the frame
                    send_to_link(sent_interface.id, length, data)
            elif sent_interface.type == "T":        # trunk port, send frame with 802.1q header
                if recv_interface_type == "T":      # 802.1q header already added, just send the frame
                    send_to_link(sent_interface.id, length, data)
                elif recv_interface_type == "A":     # there is no existing 802.1q header, add it
                    data = data[0:12] + create_vlan_tag(sent_interface.vlan) + data[12:]
                    send_to_link(sent_interface.id, length, data)

def remove_tagged_header(old_frame):
    new_frame = old_frame[0:12] + old_frame[16:]
    return new_frame

def handle_frame_forward(recv_interface_id, data, length, dest_mac, src_mac, ethertype, vlan_id):
    if is_broadcast(dest_mac):
        handle_broadcast(recv_interface_id, data, length, dest_mac, src_mac, ethertype, vlan_id)
    else:
        handle_unicast(recv_interface_id, data, length, dest_mac, src_mac, ethertype, vlan_id)
    
def main():
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    switch_id = sys.argv[1]

    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces_count = range(0, num_interfaces)
    switch_mac = get_switch_mac()

    print("# Starting switch with id {}".format(switch_id), flush=True)
    print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in switch_mac))

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec)
    t.start()
    
    parse_switch_info(switch_id)

    #debug print interfaces info
    for i in interfaces_count:
        print(interfaces[i])


    while True:
        # Note that data is of type bytes([...]).
        # b1 = bytes([72, 101, 108, 108, 111])  # "Hello"
        # b2 = bytes([32, 87, 111, 114, 108, 100])  # " World"
        # b3 = b1[0:2] + b[3:4].
        interface, data, length = recv_from_any_link()

        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

        # Print the MAC src and MAC dst in human readable format
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        # Note. Adding a VLAN tag can be as easy as
        # tagged_frame = data[0:12] + create_vlan_tag(10) + data[12:]

        print(f'Destination MAC: {dest_mac}')
        print(f'Source MAC: {src_mac}')
        print(f'EtherType: {ethertype}')

        print("Received frame of size {} on interface {}".format(length, interface), flush=True)

        # TODO: Implement forwarding with learning

        # Update the CAM Table with the new entry
        cam.table[src_mac] = interface

        handle_frame_forward(interface, data, length, dest_mac, src_mac, ethertype, vlan_id)

        # TODO: Implement STP support

        # data is of type bytes.
        # send_to_link(i, length, data)

if __name__ == "__main__":
    main()
