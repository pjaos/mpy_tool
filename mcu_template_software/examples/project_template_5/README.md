# Example Project 5

Template project

- With WiFi that can be setup via bluetooth
- Start the microdot webserver.
- A YDev broadcast message listener. This listens for YDev are you
  there (AYT) messages and responds with JSON stats data.

Add project code to app1/app.py file ThisMachine.start() method.

Once loaded the WIFI tab in mpy_tool_gui can be used to setup the WiFi.
The message log from mpy_tool_gui when setting up the WiFi over bluetooth is shown below

```
INFO:  Scanning for YDev devices via bluetooth...
INFO:  Detected YDev unit (address = 28:37:2F:54:28:B6).
INFO:  YDev unit is now performing a WiFi network scan...
INFO:  WiFi Network                             RSSI (dBm)
INFO:  airstorm11-Guest                         -85
INFO:  airstorm11                               -86
INFO:  Setting up YDev WiFi...
INFO:  Waiting for YDev device to restart...
INFO:  Waiting for YDev device WiFi to be served an IP address by the DHCP server...
INFO:  YDev device IP address = X.X.X.X
INFO:  Turning off bluetooth interface on YDev device.
INFO:  Device WiFi setup complete.
```

If you open a web browser and connect to http://<MCU IP ADDRESS>:80
you should receive.

'''
Microdot Example Page
Hello from Microdot!

Click to shutdown the server
'''

If the mpy_tool_gui SCAN tab is used to send YDEV broadcast messages when a device is running this example code it will respond with JSON messages as shown below in the messages window.

```
INFO:  Sending AYT messages every second.
INFO:  Listening on UDP port 2934
INFO:  {
    "OS": "MicroPython",
    "DEVICE_TYPE": "DEV_TYPE",
    "UNIT_NAME": "DEV_NAME",
    "PRODUCT_ID": "PRODUCT_ID",
    "SERVICE_LIST": "web:80",
    "IP_ADDRESS": "192.168.0.57",
    "GROUP_NAME": ""
}
INFO:  {
    "OS": "MicroPython",
    "DEVICE_TYPE": "DEV_TYPE",
    "UNIT_NAME": "DEV_NAME",
    "PRODUCT_ID": "PRODUCT_ID",
    "SERVICE_LIST": "web:80",
    "IP_ADDRESS": "192.168.0.57",
    "GROUP_NAME": ""
}
INFO:  {
    "OS": "MicroPython",
    "DEVICE_TYPE": "DEV_TYPE",
    "UNIT_NAME": "DEV_NAME",
    "PRODUCT_ID": "PRODUCT_ID",
    "SERVICE_LIST": "web:80",
    "IP_ADDRESS": "192.168.0.57",
    "GROUP_NAME": ""
}
INFO:  {
    "OS": "MicroPython",
    "DEVICE_TYPE": "DEV_TYPE",
    "UNIT_NAME": "DEV_NAME",
    "PRODUCT_ID": "PRODUCT_ID",
    "SERVICE_LIST": "web:80",
    "IP_ADDRESS": "192.168.0.57",
    "GROUP_NAME": ""
}
INFO:  {
    "OS": "MicroPython",
    "DEVICE_TYPE": "DEV_TYPE",
    "UNIT_NAME": "DEV_NAME",
    "PRODUCT_ID": "PRODUCT_ID",
    "SERVICE_LIST": "web:80",
    "IP_ADDRESS": "192.168.0.57",
    "GROUP_NAME": ""
}
INFO:  Scan complete.
```
