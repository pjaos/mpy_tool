# from machine import WDT

import asyncio
from time import time

from lib.uo import UO
from lib.config import MachineConfig
from lib.base_machine import BaseMachine
from lib.webserver import WebServer
from lib.microdot.microdot import send_file, Response
from lib.io import IO

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


class MyWebServer(WebServer):
    """@brief The webserver for this project."""

    def __init__(self,
                 machine_config,
                 startTime,
                 uo=None,
                 port=WebServer.DEFAULT_PORT):
        super().__init__(machine_config,
                         startTime,
                         uo=uo,
                         port=port)

        self._dark_mode = True

        # --- Parameters stored on the MCU ---
        self._params = { "charge_current": 500, # mA
                       }
        self._battery_voltage = 36
        self._charging = True

        # Used for plotting data in the web browser.
        self._reading_history = []  # list of (voltage, current)
        self._max_points = 50

        self._load_routes()

    def add_reading(self, volts, amps):
        self._reading_history.append((volts, amps))
        if len(self._reading_history) > self._max_points:
            self._reading_history.pop(0)

        print(f"PJA: len(self._reading_history)={len(self._reading_history)}")

    # --- Simulated battery logic ---
    def _read_battery_voltage(self):
        if self._charging:
            battery_voltage = min(4.2, self._battery_voltage + 0.01)
        else:
            battery_voltage = max(3.0, self._battery_voltage - 0.005)
        return battery_voltage

    def _load_routes(self):

        @self._app.route('assets/<path>')
        def static_files(request, path):
            # The file should be found inside the assets folder of the running app
            running_app = self._machine_config.get(MachineConfig.RUNNING_APP_KEY)
            file_to_send = f"/app{running_app}" + '/assets/' + path
            file_exists = IO.FileExists(file_to_send)
            if file_exists:
                return send_file(file_to_send)

        @self._app.route('/status')
        def status(request):
            v = self._read_battery_voltage()
            html = f"""
                <p>Voltage: {v:.2f} V</p>
                <p>Charging: {"Yes" if self._charging else "No"}</p>
            """
            return html

        @self._app.route('/toggle', methods=['POST'])
        def toggle(request):
            charging = not self._charging
            v = self._read_battery_voltage()
            html = f"""
                <p>Voltage: {v:.2f} V</p>
                <p>Charging: {"Yes" if charging else "No"}</p>
            """
            return html

        # --- GET parameters ---
        @self._app.route('/get_param')
        def get_param(request):
            html = f"""
                <p>Charge Current: {self._params['charge_current']} mA</p>
            """
            return html

        # --- SET parameters ---
        @self._app.route('/set_param', methods=['POST'])
        def set_param(request):
            if 'charge_current' in request.form:
                try:
                    self._params['charge_current'] = int(request.form['charge_current'])
                except:
                    return "<p>Error: invalid number</p>"

            html = f"""
                <p>Updated Charge Current: {self._params['charge_current']} mA</p>
            """
            return html

        @self._app.post('/toggle-dark')
        def toggle_dark(request):
            self._dark_mode = not self._dark_mode
            print(f"PJA: self._dark_mode={self._dark_mode}")
            return Response('', 204)  # no content

        @self._app.route('/plot_data')
        def plot_data(request):
            # Ensure you are recording samples somewhere
            data = {
                "labels": list(range(len(self._reading_history))),
                "voltage": [v for v, c in self._reading_history],
                "current": [c for v, c in self._reading_history]
            }
            return data






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

    def start(self):
        self.show_ram_info()

        # Connect this machine to a WiFi network.
        # Note that the WiFi setup claims two GPIO pins. See _sta_connect_wifi doc for more info.
        self._sta_connect_wifi()

        # Start task that looks for user press of the reset to defaults button press
        asyncio.create_task(self._check_factory_Defaults_task())

        # Run the web server. This is used for upgrades and also to present
        # a local webserver to allow users to interact with the device.
        # In this case it displays dummy temperatures.
        self._web_server = MyWebServer(self._machine_config,
                                       self._startTime,
                                       uo=self._uo)

        # Call the app task to execute your projects functionality.
        asyncio.create_task(self.app_task())

        self._web_server.run()

    async def read(self):
        import random
        volts = random.random()*12
        amps = random.random()
        return (volts, amps)

    async def app_task(self):
        """@brief Add your project code here.
                  Make sure await asyncio.sleep(1) is called frequently to ensure other tasks get CPU time."""
        count = 0
        while True:
            volts, amps = await self.read()
            self._web_server.add_reading(volts, amps)
            print(f"app_task(): count = {count}")
            await asyncio.sleep(1)
            count += 1

