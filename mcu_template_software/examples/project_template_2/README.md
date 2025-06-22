# Example Project 2

Project template with WiFi that can be setup via bluetooth.

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
