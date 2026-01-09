# Example Project 2

This has the ability to switch between app1 and app2 when upgraded. 
However it does not include the code to setup WiFi via bluetooth.

The message log from mpy_tool_gui (SERIAL PORT tab) when starting the app is shown below.

```
INFO:  Running app1
INFO:  Total RAM (bytes) 178688, Free 158288, Used 20400, uptime 0
INFO:  /dev/ttyACM0: INFO:  Total RAM (bytes) 178688, Free 165536, Used 13152, uptime 5
INFO:  /dev/ttyACM0: INFO:  Total RAM (bytes) 178688, Free 165520, Used 13168, uptime 10
INFO:  /dev/ttyACM0: INFO:  Total RAM (bytes) 178688, Free 165520, Used 13168, uptime 15
INFO:  /dev/ttyACM0: INFO:  Total RAM (bytes) 178688, Free 165520, Used 13168, uptime 20
```

## Supported mpy_tool_gui functionality.
- The INSTALL tab can be used to load code onto an MCU.
- The WiFi tab can be used to setup the WiFi interface via a USB connection.
- SERIAL PORT tab can be used to view and send data on the serial port.

If you wish to add code for your project you should update the ThisMachine class start() method in the app1/app.py. This method is shown below.

```
class ThisMachine(BaseMachine):
...
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
```

