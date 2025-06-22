# from machine import WDT

import os
from time import time, sleep

from lib.uo import UO, UOBase
from lib.config import MachineConfig
from lib.wifi import WiFi
from lib.hardware import Hardware

SHOW_MESSAGES_ON_STDOUT = True  # Turning this off will stop messages being sent on the serial port and will reduce CPU usage.
WDT_TIMEOUT_MSECS = 8300        # Note that 8388 is the max WD timeout value on pico W hardware.


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
        self._wdt = None

    def _init(self):
        self._machine_config = MachineConfig(ThisMachine.DEFAULT_CONFIG)

    def pat_wdt(self):
        if self._wdt:
            self._wdt.feed()

    def _sta_connect_wifi(self):
        """@brief Connect to a WiFi network in STA mode."""
        # Init the WiFi interface
        self._wifi = WiFi(self._uo,
                          ThisMachine.WIFI_LED_PIN,
                          ThisMachine.WIFI_SETUP_BUTTON_PIN,
                          self._wdt,
                          self._machine_config,
                          max_reg_wait_secs=ThisMachine.MAX_STA_WAIT_REG_SECONDS)
        self._wifi.sta_connect()

    def set_factory_defaults(self):
        """@brief reset the config to factory defaults."""
        self._machine_config.set_defaults()
        self._machine_config.store()
        self.warn("Resetting to factory defaults.")
        # Ensure the file system is synced before we reboot.
        os.sync()
        Hardware.Reboot(uo=self._uo)
        while True:
            sleep(1)


class ThisMachine(BaseMachine):
    """@brief Implement functionality required by this project."""

    # This value must be less than the WDT_TIMEOUT_MSECS if the WDT is enabled.
    SERVICE_LOOP_MILLISECONDS = 200

    # The MAX time to wait for an STA to register.
    # After this time has elapsed the unit will either reboot
    # or if the hardware has the capability, power cycle itself.
    MAX_STA_WAIT_REG_SECONDS = 60

    # A button pulls this GPIO pin low to reset the WiFi parameters.
    # The PC or android app should be used to setup the WiFi.
    # Typically GPIO 0 on an esp32 MCU.
    # Typically GPIO 9 on an esp32-c3 MCU.
    # Typically GPIO 14 on a RPi pico W MCU.
    WIFI_SETUP_BUTTON_PIN = 9

    # The GPIO pin connected to the WiFi indicator LED (-1 = not used).
    # This flashes when not connected and turns solid on when connected to a WiFi network.
    # Typically GPIO 2 on an esp32 MCU.
    # Typically GPIO 16 on a RPi pico W MCU.
    WIFI_LED_PIN = 2

    ACTIVE = "ACTIVE"
    DEFAULT_CONFIG = {ACTIVE: True}

    def __init__(self, uo):
        super().__init__(uo)
        self._startTime = time()

        # Initialise this machine
        self._init()

    def _init(self):
        super()._init()

        # Enable watchdog timer here if required.
        # If the WiFi goes down then we can
        # drop out to the REPL prompt.
        # The WDT will then trigger a reboot.
    #        self._wdt = WDT(timeout=WDT_TIMEOUT_MSECS)

    def start(self):
        self.show_ram_info()

        # Connect this machine to a WiFi network.
        self._sta_connect_wifi()

        from lib.webserver import WebServer
        web_server = WebServer(self._machine_config,
                               self._startTime,
                               uo=self._uo)
        web_server.run()
