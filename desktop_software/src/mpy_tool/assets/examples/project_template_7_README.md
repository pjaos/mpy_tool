# Example Project 7

This example has less features than project example 6. It's functionality is summarised
below.

- Allow the user to setup the WiFi interface either over a USB or Bluetooth connection.
  You can use the WIFI tab in mpy_tool_gui.py to do this.
- Setup the WebREPL server to allow connections to via a web browser.
- Once the WiFi has been setup the main() method (main.py file) exits.
  The user can then connect via the WebREPL interface.

This project is aimed at allowing the user to try out code by loading and running it via
the WebREPL interface. As such, it is really aimed at being a testing platform to allow
users to try out different solutions using the WebREPL interface.

You can use the mpy_tool_gui tool to setup the WiFi interface (WIFI tab) after using
the INSTALL tab to install MicroPython and this example onto the MCU.

# Connecting to the WebREPL interface

To connect to the web repl prompt enter 'http://MCUIPADDRESS:8266 (replace MCUIPADDRESS with the IP address of your MCU) into the address bar of your web browser.

When you connect you will need to enter the password. The default webrepl password is 12345678.


You may change this password by editing the webrepl_cfg.py file.

E.G

```
PASS = '12345678'

```

Note that this file must have a line feed character at the end of the line.
