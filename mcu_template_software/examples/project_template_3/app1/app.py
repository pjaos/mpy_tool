# from machine import WDT

import os
from time import time, sleep

from lib.uo import UO, UOBase
from lib.config import MachineConfig
from lib.wifi import WiFi
from lib.hardware import Hardware

SHOW_MESSAGES_ON_STDOUT = True  # Turning this off will stop messages being sent on the serial port and will reduce CPU usage.
WDT_TIMEOUT_MSECS = 8300        # Note that 8388 is the max WD timeout value on pico W hardware.


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


class ThisMachineConfig(MachineConfig):
    """@brief Defines the config specific to this machine."""

    # Note that
    # MachineConfig.RUNNING_APP_KEY and
    # MachineConfig.WIFI_KEY will added automatically so we only need
    # to define keys that are specific to this machine type here.

    DEFAULT_CONFIG = {}

    def __init__(self):
        super().__init__(ThisMachineConfig.DEFAULT_CONFIG)


class BaseMachine(UOBase):

    def __init__(self, uo):
        super().__init__(uo)
        self._wdt = None

    def _init(self):
        self._machine_config = ThisMachineConfig()

    def pat_wdt(self):
        if self._wdt:
            self._wdt.feed()

    def _get_wifi_setup_gpio(self, override=-1):
        """@brief get the GPIO pin used to setup the WiFi GPIO.
           @param wifi_setup_gpio_override. By default this is set to -1 which sets the following defaults.
                  GPIO 0 on an esp32 (original) MCU.
                  GPIO 9 on an esp32-c3 or esp32-c6 MCU.
                  GPIO 14 on a RPi Pico W or RPi Pico 2 W MCU.
           @return The GPIO pin to use."""
        mcu = os.uname().machine
        self.debug(f"MCU: {mcu}")
        gpio_pin = -1
        if override >= 0:
            # TODO: Add checks here to check that it's a valid GPIO for the MCU
            gpio_pin = override

        else:
            # !!!
            # Currently MicroPython for the ESP32C6 is under development and the
            # image of MicroPython in this tool returns ESP32
            # rather than ESP32C6 for esp32c6 HW.
            if 'ESP32C6' in mcu:
                gpio_pin = 9

            elif 'ESP32C3' in mcu:
                gpio_pin = 9

            elif 'ESP32' in mcu:
                gpio_pin = 0

            elif 'RP2040' in mcu or 'RP2350' in mcu:
                gpio_pin = 14

            else:
                raise Exception(f"Unsupported MCU: {mcu}")

        return gpio_pin

    def _get_wifi_led_gpio(self, override=-1):
        """@brief get the GPIO pin connected connected to an LED that turns on when the WiFi
                  is connected to the WiFi network as an STA.
           @param wifi_setup_gpio_override. By default this is set to -1 which sets the following defaults.
                  GPIO 2 on an esp32 (original) MCU.
                  GPIO 8 on an esp32-c3 or esp32-c6 MCU.
                  GPIO 16 on a RPi Pico W or RPi Pico 2 W MCU.
           @return The GPIO pin to use."""
        mcu = os.uname().machine
        self.debug(f"MCU: {mcu}")
        gpio_pin = -1
        if override >= 0:
            # TODO: Add checks here to check that it's a valid GPIO for the MCU
            gpio_pin = override

        else:
            # !!!
            # Currently MicroPython for the ESP32C6 is under development and the
            # image of MicroPython in this tool returns ESP32
            # rather than ESP32C6 for esp32c6 HW.
            if 'ESP32C6' in mcu:
                gpio_pin = 8

            elif 'ESP32C3' in mcu:
                gpio_pin = 8

            elif 'ESP32' in mcu:
                gpio_pin = 2

            elif 'RP2040' in mcu or 'RP2350' in mcu:
                gpio_pin = 16

            else:
                raise Exception(f"Unsupported MCU: {mcu}")

        return gpio_pin

    def _sta_connect_wifi(self, wifi_setup_gpio=-1, wifi_led_gpio=-1):
        """@brief Connect to a WiFi network in STA mode.
           @param wifi_setup_gpio The GPIO pin, connected to a switch that when held low for some time resets WiFi setup.
                                  See _get_wifi_setup_gpio() for more info.
           @param wifi_led_gpio   The GPIO pin, connected to an LED that turns on when the WiFi is connected to the WiFi network as an STA.
                                  See _get_wifi_led_gpio() for more info.
           """
        wifi_led_gpio = self._get_wifi_led_gpio(override=wifi_led_gpio)
        wifi_setup_gpio = self._get_wifi_setup_gpio(override=wifi_setup_gpio)
        self.info(f"WiFi LED GPIO:   {wifi_led_gpio}")
        self.info(f"WiFi RESET GPIO: {wifi_setup_gpio}")
        # Init the WiFi interface
        self._wifi = WiFi(self._uo,
                          wifi_led_gpio,
                          wifi_setup_gpio,
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

    DEFAULT_CONFIG = {}

    # This value must be less than the WDT_TIMEOUT_MSECS if the WDT is enabled.
    SERVICE_LOOP_MILLISECONDS = 200
    # The MAX time to wait for an STA to register.
    # After this time has elapsed the unit will either reboot
    # or if the hardware has the capability, power cycle itself.
    MAX_STA_WAIT_REG_SECONDS = 60

    def __init__(self, uo):
        super().__init__(uo)

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

        while True:
            start_loop_time = time()
            self.show_ram_info()

            if self._wifi.is_factory_reset_required():
                self.set_factory_defaults()

            # Calc how long we need to delay to maintain the service loop time
            elapsed_seconds = time() - start_loop_time
            loop_seconds_left = (ThisMachine.SERVICE_LOOP_MILLISECONDS/1000) - elapsed_seconds
            if loop_seconds_left > 0:
                self.pat_wdt()
                sleep(loop_seconds_left)

            else:
                self.debug(f"Run out of service loop time by {loop_seconds_left} seconds.")
