# import  uasyncio as asyncio

# from machine import WDT

from time import time, sleep

from lib.uo import UO, UOBase
from lib.config import MachineConfig

# Turning this off will stop messages being sent on the serial port
SHOW_MESSAGES_ON_STDOUT = True
# and will reduce CPU usage.
# Note that 8388 is the max WD timeout value on pico W hardware.
WDT_TIMEOUT_MSECS = 8300


async def start(config_file, active_app_key, active_app):
    """@brief The app entry point
       @param config_file The config file that holds all machine config including the active application ID.
       @param active_app_key The key in the config dict that details which app (1 or 2) we are running from.
       @param active_app The active app. Either 1 or 2."""

    if SHOW_MESSAGES_ON_STDOUT:
        uo = UO(enabled=True, debug_enabled=True)
        uo.info("Started app")
        uo.info("Running app{}".format(active_app))
    else:
        uo = None

    this_machine = ThisMachine(uo)
    this_machine.start()


class BaseMachine(UOBase):
    def __init__(self, uo):
        super().__init__(uo)


class ThisMachine(BaseMachine):
    """@brief Implement functionality required by this project."""

    DEFAULT_CONFIG = {}

    # This value must be less than the WDT_TIMEOUT_MSECS if the WDT is enabled.
    SERVICE_LOOP_MILLISECONDS = 5000

    def __init__(self, uo):
        super().__init__(uo)

        self._wdt = None
#        self._wdt = WDT(timeout=WDT_TIMEOUT_MSECS)  # Enable watchdog timer here.
        # If the WiFi goes down then we can
        # drop out to the REPL prompt.
        # The WDT will then trigger a reboot.

        # Initialise this machine
        self._init()

    def _init(self):
        self._machine_config = MachineConfig(ThisMachine.DEFAULT_CONFIG)

    def pat_wdt(self):
        if self._wdt:
            self._wdt.feed()

    def start(self):

        while True:
            start_loop_time = time()
            self.show_ram_info()

            # Calc how long we need to delay to maintain the service loop time
            elapsed_seconds = time() - start_loop_time
            loop_seconds_left = (
                ThisMachine.SERVICE_LOOP_MILLISECONDS / 1000) - elapsed_seconds
            if loop_seconds_left > 0:
                self.pat_wdt()
                sleep(loop_seconds_left)

            else:
                self.debug(
                    f"Run out of service loop time by {loop_seconds_left} seconds.")
