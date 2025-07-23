# from machine import WDT

import asyncio
from time import time

from lib.uo import UO
from lib.config import MachineConfig
from lib.ydev import YDev
from lib.base_machine import BaseMachine

SHOW_MESSAGES_ON_STDOUT = True  # Turning this off will stop messages being sent on the serial port and will reduce CPU usage.
WDT_TIMEOUT_MSECS = 8300        # Note that 8388 is the max WD timeout value on pico W hardware.


class ThisMachineConfig(MachineConfig):
    """@brief Defines the config specific to this machine."""

    # Note that
    # MachineConfig.RUNNING_APP_KEY and
    # MachineConfig.WIFI_KEY will added automatically so we only need
    # to define keys that are specific to this machine type here.

    DEFAULT_CONFIG = {YDev.ACTIVE: True,
                      YDev.AYT_TCP_PORT_KEY: 2934,               # The UDP port we expect to receive an AYT UDP broadcast message
                      YDev.OS_KEY: "MicroPython",
                      YDev.UNIT_NAME_KEY: "DEV_NAME",            # This can be used to identify device, probably user configurable.
                      YDev.PRODUCT_ID_KEY: "PRODUCT_ID",         # This is fixed for the product, probably during MFG.
                      YDev.DEVICE_TYPE_KEY: "DEV_TYPE",          # This is fixed for the product, probably during MFG.
                      YDev.SERVICE_LIST_KEY: "web:80",           # A service name followed by the TCPIP port number this device presents the service on.
                      YDev.GROUP_NAME_KEY: ""                    # Used put devices in a group for mild isolation purposes.
                      }

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

    def __init__(self, uo, machine_config):
        super().__init__(uo, machine_config)
        self._startTime = time()

        # Enable watchdog timer here if required.
        # If the WiFi goes down then we can
        # drop out to the REPL prompt.
        # The WDT will then trigger a reboot.
        # self._wdt = WDT(timeout=WDT_TIMEOUT_MSECS)

    async def _updateTemp(self, paramDict):
        """@brief Example code to update the temperature and humidity.
                  In reality you are likely to read values from sensor/s. """
        from math import floor
        from random import random
        #This task runs while the webserver is running.
        while True:
            # Move temp and humidity by small amounts so user can see
            # values changing
            temp = paramDict['temperature']
            value = floor(float(temp)) + random()
            paramDict['temperature'] = f"{value:.3f}"

            humidity = paramDict['humidity']
            value = floor(float(humidity)) + random()
            paramDict['humidity'] = f"{value:.3f}"

            await asyncio.sleep(1)

    def start(self):
        self.show_ram_info()

        # Connect this machine to a WiFi network.
        # Note that the WiFi setup claims two GPIO pins. See _sta_connect_wifi doc for more info.
        self._sta_connect_wifi()

        # Start task that looks for user press of the reset to defaults button press
        asyncio.create_task(self._check_factory_Defaults_task())

        # Call the app task to execute your projects functionality.
        asyncio.create_task(self.app_task())

        # Task that will return JSON messages to the YDev server.
        ydev = YDev(self._machine_config)
        asyncio.create_task(ydev.listen())

        # Run the web server. This is used for upgrades and also to present
        # a local webserver to allow users to interact with the device.
        # In this case it displays dummy temperatures.
        from lib.webserver import WebServer
        web_server = WebServer(self._machine_config,
                               self._startTime,
                               uo=self._uo)
        paramDict = {'temperature': 24.5, 'humidity': 60}
        asyncio.create_task(self._updateTemp(paramDict))
        web_server.setParamDict(paramDict)
        web_server.run()

    async def app_task(self):
        """@brief Add your project code here. 
                  Make sure await asyncio.sleep(1) is called frequently to ensure other tasks get CPU time."""
        count = 0
        while True:
            print(f"app_task(): count = {count}")
            await asyncio.sleep(1)
            count += 1

