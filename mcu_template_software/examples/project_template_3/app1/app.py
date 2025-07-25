# from machine import WDT

import asyncio
from time import time, sleep

from lib.uo import UO
from lib.config import MachineConfig
from lib.base_machine import BaseMachine

SHOW_MESSAGES_ON_STDOUT = True  # Turning this off will stop messages being sent on the serial port and will reduce CPU usage.
WDT_TIMEOUT_MSECS = 8300        # Note that 8388 is the max WD timeout value on pico W hardware.


class ThisMachineConfig(MachineConfig):
    """@brief Defines the config specific to this machine."""

    # Note that
    # MachineConfig.RUNNING_APP_KEY and
    # MachineConfig.WIFI_KEY will added automatically so we only need
    # to define keys that are specific to this machine type here.

    DEFAULT_CONFIG = {}

    def __init__(self):
        super().__init__(ThisMachineConfig.DEFAULT_CONFIG)


async def start(runningAppKey, configFilename):
    """@brief The app entry point.
       @param runningAppKey The KEY in the config dict that holds the current running app.
       @param configFilename The name of the config file. This sits in / on flash."""
    MachineConfig.RUNNING_APP_KEY = runningAppKey
    MachineConfig.CONFIG_FILENAME = configFilename
    file_path = __file__
    if file_path.startswith('app1'):
        active_app = 1

    elif file_path.startswith('app2'):
        active_app = 2

    else:
        raise Exception(f"App path not /app1 or /app2: {file_path}")

    if SHOW_MESSAGES_ON_STDOUT:
        uo = UO(enabled=True, debug_enabled=True)
        uo.info("Started app")
        uo.info("Running app{}".format(active_app))
    else:
        uo = None

    machine_config = ThisMachineConfig()
    this_machine = ThisMachine(uo, machine_config)
    this_machine.start()


class ThisMachine(BaseMachine):
    """@brief Implement functionality required by this project."""

    # This value must be less than the WDT_TIMEOUT_MSECS if the WDT is enabled.
    SERVICE_LOOP_MILLISECONDS = 200

    def __init__(self, uo, machine_config):
        super().__init__(uo, machine_config)
        self._startTime = time()

        # Enable watchdog timer here if required.
        # If the WiFi goes down then we can
        # drop out to the REPL prompt.
        # The WDT will then trigger a reboot.
        # self._wdt = WDT(timeout=WDT_TIMEOUT_MSECS)

    def start(self):
        self.show_ram_info()

        # Connect this machine to a WiFi network.
        # Note that the WiFi setup claims two GPIO pins. See _sta_connect_wifi doc for more info.
        self._sta_connect_wifi()

        # Start task that looks for user press of the reset to defaults button press
        asyncio.create_task(self._check_factory_Defaults_task())

        while True:
            start_loop_time = time()
            self.show_ram_info()

            if self._wifi.is_factory_reset_required():
                self.set_factory_defaults()

            # Calc how long we need to delay to maintain the service loop time
            elapsed_seconds = time() - start_loop_time
            loop_seconds_left = (ThisMachine.SERVICE_LOOP_MILLISECONDS/1000) - elapsed_seconds
            if loop_seconds_left > 0:
                sleep(loop_seconds_left)

            else:
                self.debug(f"Run out of service loop time by {loop_seconds_left} seconds.")
