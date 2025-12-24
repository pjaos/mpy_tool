# Example Project 3

This is the first example that includes the ability to setup WiFi over bluetooth.
However it does not allow upgrading or resetting the configuration over a WiFi network interface.

The message log from mpy_tool_gui (SERIAL PORT tab) when starting the app when it's connected to a WiFi network.

```
MPY: soft reboot
DEBUG: active_app=1
INFO:  /dev/ttyACM0: INFO:  Started app
INFO:  Running app1
INFO:  /dev/ttyACM0: INFO:  Total RAM (bytes) 205440, Free 158240, Used 47200, uptime 0
DEBUG: MCU: Raspberry Pi Pico W with RP2040
DEBUG: MCU: Raspberry Pi Pico W with RP2040
INFO:  WiFi LED GPIO:      16
INFO:  WiFi RESET GPIO:    14
INFO:  Bluetooth LED GPIO: None
DEBUG: wifi_status=3
DEBUG: connected
INFO:  IP Address=X.X.X.X
INFO:  Total RAM (bytes) 205440, Free 178304, Used 27136, uptime 0
INFO:  /dev/ttyACM0: INFO:  Total RAM (bytes) 205440, Free 179712, Used 25728, uptime 1
INFO:  /dev/ttyACM0: INFO:  Total RAM (bytes) 205440, Free 179696, Used 25744, uptime 1
INFO:  /dev/ttyACM0: INFO:  Total RAM (bytes) 205440, Free 179696, Used 25744, uptime 1
INFO:  /dev/ttyACM0: INFO:  Total RAM (bytes) 205440, Free 179696, Used 25744, uptime 1
INFO:  /dev/ttyACM0: INFO:  Total RAM (bytes) 205440, Free 179696, Used 25744, uptime 1
```

## Supported mpy_tool_gui functionality.
- The INSTALL tab can be used to load code onto an MCU.
- The WiFi tab can be used to setup the WiFi interface via USB or bluetooth connections.
- SERIAL PORT tab can be used to view and send data on the serial port.

If you wish to add code for your project you should update the ThisMachine class start() method in the app1/app.py. This method is shown below.


```
class ThisMachine(BaseMachine):
...
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
```
