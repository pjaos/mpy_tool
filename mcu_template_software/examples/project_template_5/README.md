# Example Project 5

This example includes the ability to setup WiFi over bluetooth. It also includes a webserver (microdot)
that allows applications to be upgraded over the WiFi interface. It also supports device discovery over the 
WiFi network.

The message log from mpy_tool_gui (SERIAL PORT tab) when starting the app when it's connected to a WiFi network.
When connected to a WiFi network an incrementing count is printed.

```
MPY: soft reboot
DEBUG: active_app=1
INFO:  /dev/ttyACM0: INFO:  Started app
INFO:  Running app1
INFO:  Total RAM (bytes) 205440, Free 157968, Used 47472, uptime 0
DEBUG: MCU: Raspberry Pi Pico W with RP2040
DEBUG: MCU: Raspberry Pi Pico W with RP2040
INFO:  WiFi LED GPIO:      16
INFO:  WiFi RESET GPIO:    14
INFO:  Bluetooth LED GPIO: None
DEBUG: wifi_status=3
DEBUG: connected
INFO:  IP Address=X.X.X.X
INFO:  /dev/ttyACM0: app_task(): count = 0
Starting async server on 0.0.0.0:80...
INFO:  /dev/ttyACM0: app_task(): count = 1
INFO:  /dev/ttyACM0: app_task(): count = 2
```

You can update the html file in the assets folder 
to present the web page that you wish. Other files (css, javascript etc) 
can be added to the assets folder if required. The _updateContent()
method in the WebServer class (lib/webserver.py) updates the values on the 
web page/s after they are read from flash memory and before they are served 
to the clients web browser.

'''
Sensor Data

Temperature: 24.306 °C

Humidity: 60.344 %
'''


## Supported mpy_tool_gui functionality.

- The INSTALL tab can be used to load code onto an MCU.
- The WiFi tab can be used to setup the WiFi interface via USB or bluetooth connections.
- OTA (OVER THE AIR) tab UPGRADE and RESET WIFI CONFIGURATION buttons.
- SERIAL PORT tab can be used to view and send data on the serial port.
- SCAN tab can be used to discover connected devices on the network.
- MEMORY MONITOR tab can be used to monitor RAM and disk usage.

If you wish to add code for your project you should update the ThisMachine class app_task() method in the app1/app.py. This method is shown below.


```
class ThisMachine(BaseMachine):
...
    async def app_task(self):
        """@brief Add your project code here. 
                  Make sure await asyncio.sleep(1) is called frequently to ensure other tasks get CPU time."""
        count = 0
        while True:
            print(f"app_task(): count = {count}")
            await asyncio.sleep(1)
            count += 1
```

You may want to modify the above code for your projects functionality to read some values from sensors. These values can be used to update values in a dictionary.
The setParamDict() method on the WebServer class (lib/webserver.py) should be used to pass a reference to this dictionary which is 
then used by the WebServer class to update the values on the webpage served to the client.

## Scan tool
If the SCAN button is selected in the mpu_tool_gui SCAN tab the following can be produced.

```
INFO:  Sending AYT messages every second.
INFO:  Listening on UDP port 2934
INFO:  {
    "OS": "MicroPython",
    "DEVICE_TYPE": "DEV_TYPE",
    "UNIT_NAME": "DEV_NAME",
    "PRODUCT_ID": "PRODUCT_ID",
    "SERVICE_LIST": "web:80",
    "IP_ADDRESS": "192.168.0.16",
    "GROUP_NAME": ""
}
INFO:  {
    "OS": "MicroPython",
    "DEVICE_TYPE": "DEV_TYPE",
    "UNIT_NAME": "DEV_NAME",
    "PRODUCT_ID": "PRODUCT_ID",
    "SERVICE_LIST": "web:80",
    "IP_ADDRESS": "192.168.0.18",
    "GROUP_NAME": ""
}
```

These parameters can be set in your code for your product type.


## Details of WiFi setup functionality

The example code includes the allocation of two GPIO pins on the MCU, one connected to an LED and one connected to a button.

See [WIFI_SETUP_GPIOS.md](../project_template_4/WIFI_SETUP_GPIOS.md) for details of this.
