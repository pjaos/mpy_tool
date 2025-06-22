# from machine import WDT

from time import time, sleep

from lib.uo import UO, UOBase
from lib.config import MachineConfig

# Turning this off will stop messages being sent on the serial port
SHOW_MESSAGES_ON_STDOUT = True
# and will reduce CPU usage.
# Note that 8388 is the max WD timeout value on pico W hardware.
WDT_TIMEOUT_MSECS = 8300


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

    this_machine = ThisMachine(uo)
    this_machine.start()


class BaseMachine(UOBase):
    def __init__(self, uo):
        super().__init__(uo)


class ThisMachineConfig(MachineConfig):
    """@brief Defines the config specific to required for this machine."""

    # Note that
    # MachineConfig.RUNNING_APP_KEY and
    # MachineConfig.WIFI_KEY will added automatically so we only need
    # to define keys that are specific to this machine type.

    ACTIVE = "ACTIVE"
    DEFAULT_CONFIG = {ACTIVE: True}

    def __init__(self):
        super().__init__(ThisMachineConfig.DEFAULT_CONFIG)


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
        self._machine_config = ThisMachineConfig()

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
