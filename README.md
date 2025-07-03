# MPY Tool project

This project provides a GUI tool with the following functionality

- Load MicroPython (MicroPython firmware and MicrPython program) onto RPi Pico W, RPi Pico 2 W, esp32, esp32c3 and esp32c6 MCU's.
- Setup the WiFi SSID and password on the above MCU's either using a USB port or via bluetooth connections.
- Upgrade a running MicroPython app on an MCU via a WiFi connection.
- Provide serial port debugging assistance.
- Scan function to read JSON data from MCU's running example code.
- Live plots of memory and disk usage while apps are running.

For more information on how to use the mp3_tool_gui for the above functionality click [here](desktop_software/README.md)

# Example MCU MicroPython code is included

The GUI tool requires that template code is executed on the MCU to allow setting up the WiFi over Bluetooth, Upgrades over the air (OTA) and running a webserver.
The following example applications are provided as the starting point for implementing your chosen project functionality. The example code can be found in the
/home/pja/git-repos/mpy_tool/mcu_template_software/examples folder of the git repo.

- Example 1
Minimal example. Click [here](mcu_template_software/examples/project_template_1/README.md) for more info.

- Example 2
As above but with the ability to setup the WiFi over USB or Bluetooth interface. Click [here](mcu_template_software/examples/project_template_2/README.md) for more info.

- Example 3
As above but with a webserver. Click [here](mcu_template_software/examples/project_template_3/README.md) for more info.

- Example 4
As above but with the ability to respond to are you there broadcast messages with stats in JSON format. Click [here](mcu_template_software/examples/project_template_4/README.md) for more info.

## Installation

The GUI tool has been tested on Linux and Windows platforms.

### Linux

The software is supplied as a python wheel file. This can be found in the desktop_software/linux folder


### Windows

The software is supplied as a python wheel file. This can be found in the desktop_software/windows folder

