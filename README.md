# MPY Tool project

This project provides a GUI (Graphical User Interface) tool with the following functionality

- Load MicroPython (MicroPython firmware and MicrPython program) onto Micro Controllers (MCU's).
  The currently supported list of MCU's is RPi Pico W, RPi Pico 2 W, esp32, esp32c3 and esp32c6.
- Setup the WiFi SSID and password on the above MCU's either using a USB port or via bluetooth connections.
- Upgrade a running MicroPython app on an MCU via a WiFi connection.
- Provide serial port debugging assistance.
- Scan function to read JSON data from MCU's running example code.
- Live plots of memory and disk usage while apps are running.

## Installation

The GUI tool has been tested on Linux, Windows and Mac platforms.

### Linux

The software is supplied as a python wheel file. This can be found in the desktop_software/linux folder of the git repo.

Python of at least version 3.12 should be installed on the Linux system.

pipx must also be installed. See https://pipx.pypa.io/latest/installation/ for details of how to install pipx.

Once python and pipx are installed the mpy_tool package can be installed as shown below by running a command from a terminal window.

```
pipx install desktop_software/linux/mpy_tool-0.12-py3-none-any.whl
  installed package mpy_tool 0.12, installed using Python 3.12.3
  These apps are now globally available
    - mpy_tool
    - mpy_tool_gui
    - mpy_tool_rshell
done! ✨ 🌟 ✨
```

The mpy_tool_gui command provides the functionality detailed above. The mpy_tool provides the similar functionality from the command line. The mpy_tool_rshell command can be ignored as it is used internally by the other two commands.


#### dialout group membership

On Linux platforms you may not have access (as local user) to serial ports which is required by this software.
To add access to serial ports run the following command from a terminal window.

```
sudo usermod -aG dialout $USER
[sudo] password for auser:
```

Follow this by to reload group membership. You may also logout and log back in to the system.

'''
newgrp dialout
'''

Checking that you are now a member of the dialout group

```
groups
dialout adm cdrom sudo dip plugdev users lpadmin auser
```


#### Create Gnome Application Launcher Icon

If you have a Linux distribution that supports gnome application launchers you can create a gnome desktop launcher by running the following command.

```
mpy_tool_gui -a
INFO:  Created gnome desktop application launcher
```

A gnome application launcher should now be available as shown below (press Windows key and enter mpy to view on Ubuntu) which can be used to start the mpy_tool_gui program.

![alt text](images/launcher_icon.png "Launcher Icon")


### Windows

Python of at least version 3.12 should be installed on the Windows system. Python installers for windows can be found at https://www.python.org/downloads/windows/

pipx must also be installed. See https://pipx.pypa.io/latest/installation/ for details of how to install pipx.


The software is supplied as a python wheel file. This can be found in the desktop_software/windows folder. To install the software run the following command from a power shell window.

```
pipx install desktop_software/windows/mpy_tool-0.12-py3-none-any.whl
  installed package mpy_tool 0.12, installed using Python 3.12.3
  These apps are now globally available
    - mpy_tool
    - mpy_tool_gui
    - mpy_tool_rshell
done! ✨ 🌟 ✨
```

#### Create Windows Shortcut Icon

Once installed you may create a Windows shortcut to launch the mpy_tool_gui program.

```
mpy_tool_gui.exe -a
INFO:  C:\Users\pja\pipx\venvs\mpy-tool\Lib\site-packages\assets\icon.ico icon file found.
INFO:  C:\Users\pja\Desktop\mpy_tool_gui.lnk shortcut created.
```

After executing the above command you should find the icon below on the Windows desktop. You should be able to double click this to start the mpy_tool_gui program.

![alt text](images/launcher_icon.png "Launcher Icon")



## MacOS

The software is supplied as a python wheel file. The MacOS installer is the same as the Linux installer and can be found in the desktop_software/linux folder of the git repo.

Python of at least version 3.12 should be installed on the MacOS system. Python installers for MacOS can be found at https://www.python.org/downloads/macos/

pipx must also be installed. See https://pipx.pypa.io/latest/installation/ for details of how to install pipx.

Once python and pipx are installed the mpy_tool package can be installed as shown below by running a command from a terminal window.

```
pipx install desktop_software/linux/mpy_tool-0.12-py3-none-any.whl
  installed package mpy_tool 0.12, installed using Python 3.12.3
  These apps are now globally available
    - mpy_tool
    - mpy_tool_gui
    - mpy_tool_rshell
done! ✨ 🌟 ✨
```

The mpy_tool_gui command provides the functionality detailed above. The mpy_tool provides the similar functionality from the command line. The mpy_tool_rshell command can be ignored as it is used internally by the other two commands.

#### Create a desktop launcher icon
Once installed you may create a desktop icon to launch the mpy_tool_gui program.

Run the following command from a terminal window to create the desktop launcher icon.

```
mpy_tool_gui -a
INFO:  Created /Users/pja/Desktop/MPY_Tool.app
```

After executing the above command you should find the icon below on the desktop. You should be able to double click this to start the mpy_tool_gui program.

![alt text](images/launcher_icon.png "Launcher Icon")

Note that the first time you start the mpy_tool_gui program it may take some time to start up.




# Starting the software
The mpy_tool_gui program may be started by wither of the options shown below

## Linux
- If you created the gnome application launcher icon you can double click it or
- Open a terminal window and enter 'mpy_tool_gui. You may use the -d argument to show debugging information in the Message Log window (-h gives command line help).


## Windows
- If you created the windows desktop launcher icon you can double click it or
- Open a powershell window and enter mpy_tool_gui.exe. You may use the -d argument to show debugging information in the Message Log window (-h gives command line help).

## MacOS
- If you created the desktop launcher icon you can double click it or
- Open a terminal window and enter mpy_tool_gui. You may use the -d argument to show debugging information in the Message Log window (-h gives command line help).


Once started a web browser window is opened as shown below

![alt text](images/initial_window.png "Initial Window")





# Installing onto an MCU

The example MicroPython applications can be installed onto an MCU as shown below. These example
applications can be modified to add the functionality required for your project.

## MicroPython MCU application code

The repo includes template/example code (mcu_template_software/examples git repo folder). The GUI tool requires that template code is executed on the MCU to allow setting up the WiFi over Bluetooth, Upgrades over the air (OTA), running a webserver and discovering devices on a network.

The following example applications are provided as the starting point for implementing your chosen project functionality. The example code can be found in mcu_template_software/examples folder of the git repo.

- Example 1
Minimal example. Click [here](mcu_template_software/examples/project_template_1/README.md) for more info.

- Example 2
As above but with the ability to setup the WiFi over USB or Bluetooth interface. Click [here](mcu_template_software/examples/project_template_2/README.md) for more info.

- Example 3
As above but with a webserver. Click [here](mcu_template_software/examples/project_template_3/README.md) for more info.

- Example 4
As above but with the ability to respond to are you there broadcast messages with stats in JSON format. Click [here](mcu_template_software/examples/project_template_4/README.md) for more info.




For the example below example 3 code is installed onto a RPi Pico 2 W (the latest Raspberry Pi Pico hardware).

- Select the MCU Type ('RPi Pico 2 W' in this case).
- Plug in a USB cable between the PC running the mpy_tool_gui software (GUI) and the RPi Pico 2 W.
- Select the 'UPDATE SERIAL PORT LIST' button in the GUI. If running on a Linux platform you should
  see the MCU Serial Port field updated as shown below.

![alt text](images/install_serial_port_set.png "Install Serial Port Updated")

- Then you need to select the MicroPython program that you wish to load. To do this the main.py file must
  be selected using the 'SELECT MCU MAIN.PY' button as shown below.

![alt text](images/install_main.py_selected.png "Example 3 main.py Selected")

- The four options (blue switch widgets) available should all be selected initially. Once MicroPython has
been loaded the first two (from the left) can be switch off unless you wish to Wipe the MCU flash and
reload MicroPython to it.
- Select the 'INSTALL SW' button to load the MCU. You are then prompted as shown below.

![alt text](images/install_2.png "")

- At this point remove the USB connected from the 'RPi Pico 2 W', hold the button down on the 'RPi Pico 2 W' and plug the USB connector back in (while holding the button down). This causes the 'RPi Pico 2 W' flash to be mounted as a drive.
- Select the OK button to continue.

The MCU installation process should now continue. An example of the text displayed in the Message Log window is shown below.

```

```

