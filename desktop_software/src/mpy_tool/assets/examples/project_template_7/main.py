from lib.uo import UO
from lib.config import MachineConfig
from lib.base_machine import BaseMachine

class ThisMachine(BaseMachine):
    """@brief Implement functionality required by this project."""

    def __init__(self, uo, machine_config):
        super().__init__(uo, machine_config)

    def sta_connect_wifi(self):
        """Connect this machine to a WiFi network.
           Note that the WiFi setup claims two GPIO pins. See _sta_connect_wifi doc for more info."""
        self._sta_connect_wifi()

uo = UO(enabled=True, debug_enabled=True)
uo.info("Starting")
MachineConfig.CONFIG_FILENAME = "this.machine.cfg"
config_dict = {}
machine_config = MachineConfig(config_dict)
this_machine = ThisMachine(uo, machine_config)
# This will block until the WiFi interface is setup.
this_machine.sta_connect_wifi()
# Once the Wifi is setup we exit