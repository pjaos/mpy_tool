## Details of WiFi setup functionality

The example code includes the allocation of two GPIO pins on the MCU, one connected to an LED and one connected to a button. 

You do not have to have these connected to use the project but without the LED you will have to look at the output on the serial port to know if the WiFi is connected. 
If the switch is not conected it cannot be held down to reset the WiFi config. However you can re install the software onto the MCU, reloading MicroPython using the INSTALL tab (mpy_tool_gui) or use the 'RESET WIFI CONFIGURATION' button of the 'OTA (OVER THE AIR) tab (mpy_tool_gui) if the MCU is pingable over it's WiFi interface.

- WiFi LED GPIO

This LED will indicate the state of the WiFi. The LED should be connected between the GPIO pin and GND through a sutable resistor (E.G 330 ohm). 

```
  - ON                          = LED connected to a WiFi network
  - Flashing ON/OFF evenly      = WiFi network is unset, waiting to be setup via a bluetooth or USB connection.
  - Brief ON every 2 seconds    = Attempting to connect to a WiFi network.
```

The GPIO pin used can be set in the _sta_connect_wifi() method call of the mcu_template_software/examples/project_template_4/app1/app.py file. 
The wifi_led_gpio argument to the _sta_connect_wifi() method sets the GPIO pin and is, by default, set to -1. 
If this argument is left at -1 then the _get_wifi_led_gpio() method, in the mpy_tool/mcu_template_software/examples/project_template_4/app1/lib/base_machine.py file is called to determine the GPIO pin to use. Check the mpy_tool/mcu_template_software/examples/project_template_4/app1/lib/base_machine.py file (_get_wifi_led_gpio() method) if you wish to know the GPIO pin that will be selected for your MCU.


- WiFi button GPIO

This button can be used as a factory reset button to reset the WiFi configuration (and any other configuration parameters you choose) to defaults by holding the button down for > 5 seconds. This button should connect the GPIO pin to GND.

If you hold the button down for longer than 5 seconds the WiFi LED button will start flashin ON/OFF when it the WiFi is wating to be setup. If you do not have an LED connected you can view the output on the serial port (SERIAL PORT tab in mpy_too_gui) as shown below.

```
INFO:  /dev/ttyACM0: app_task(): count = 4
INFO:  /dev/ttyACM0: app_task(): count = 5
INFO:  /dev/ttyACM0: DEBUG: Factory reset button pressed for 1 seconds.
app_task(): count = 6
INFO:  /dev/ttyACM0: DEBUG: Factory reset button pressed for 2 seconds.
app_task(): count = 7
INFO:  /dev/ttyACM0: DEBUG: Factory reset button pressed for 3 seconds.
app_task(): count = 8
INFO:  /dev/ttyACM0: DEBUG: Factory reset button pressed for 4 seconds.
app_task(): count = 9
INFO:  /dev/ttyACM0: DEBUG: Factory reset button pressed for 5 seconds.
DEBUG: Reset to factory defaults.
WARN:  Resetting to factory defaults.
DEBUG: Rebooting in 0.25 seconds.
ERROR: [Errno 5] Input/output error
INFO:  Closed /dev/ttyACM0
INFO:  RPi Pico 2 W on /dev/ttyACM0
INFO:  /dev/ttyACM0: 2
INFO:  Total RAM (bytes) 205440, Free 158080, Used 47360, uptime 0
DEBUG: MCU: Raspberry Pi Pico W with RP2040
DEBUG: MCU: Raspberry Pi Pico W with RP2040
INFO:  WiFi LED GPIO:      16
INFO:  WiFi RESET GPIO:    14
INFO:  Bluetooth LED GPIO: None
```

The GPIO pin used can be set in the _sta_connect_wifi() method call of the mcu_template_software/examples/project_template_4/app1/app.py file. 
The wifi_setup_gpio argument to the _sta_connect_wifi() method sets the GPIO pin and is, by default, set to -1. 
If this argument is left at -1 then the _get_wifi_setup_gpio() method, in the mpy_tool/mcu_template_software/examples/project_template_4/app1/lib/base_machine.py file is called to determine the GPIO pin to use. Check the mpy_tool/mcu_template_software/examples/project_template_4/app1/lib/base_machine.py file (_get_wifi_setup_gpio() method) if you wish to know the GPIO pin that will be selected for your MCU.