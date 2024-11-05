# a VLAN ID of 0 is always associated with a trunk port since 
# there is no support of native VLANs in this project
class interface:
    def __init__(self, name: str, type: str, vlan: int, id: int, state: str):
        self.id = id
        self.name = name
        self.vlan = vlan
        if vlan != 0:
            self.type = "A"
        else:
            self.type = "T"
        self.state = state
    def __repr__(self):
        return f"interface(name = {self.name!r}, type = {self.type!r}, vlan = {self.vlan!r},id = {self.id!r}, state = {self.state!r})"
    
class CAM_table:
    def __init__(self):
        self.table = {}

    def add_entry(self, mac: bytes, interface_id: int):
        self.table[mac] = interface_id
    
    def entry_exists(self, mac: bytes):
        if mac in self.table:
            return True
        else:
            return False

    def __repr__(self):
        for mac, interface in self.table.items():
            print(f"MAC: {mac.hex(':')}, Interface: {interface}")