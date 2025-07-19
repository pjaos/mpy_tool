#!/usr/bin/env python3

import os
import argparse
import threading
import serial
import requests
import datetime

from   time import time, sleep
from queue import Queue
from p3lib.launcher import Launcher

from   lib.mcu_loader import LoaderBase, USBLoader, UpgradeManager, YDevScanner, MCUBase
from   lib.bluetooth import YDevBlueTooth

from   p3lib.uio import UIO
from   p3lib.helper import logTraceBack
from   p3lib.pconfig import ConfigManager

from   p3lib.ngt import TabbedNiceGui, YesNoDialog, local_file_picker
from   nicegui import ui, app
import plotly.graph_objects as go


class GUIServer(TabbedNiceGui):
    """@responsible for presenting a management GUI."""

    # We hard code the log path to ensure the user does not have the option to move them.
    LOG_PATH                    = "mcu_tool_logs"
    DEFAULT_SERVER_ADDRESS      = "0.0.0.0"
    DEFAULT_SERVER_PORT         = 11938
    PAGE_TITLE                  = "MPY Tool"
    CFG_FILENAME                = ".mcu_tool_gui.cfg"
    WIFI_SSID                   = "WIFI_SSID"
    WIFI_PASSWORD               = "WIFI_PASSWORD"
    DEVICE_ADDRESS              = "DEVICE_ADDRESS"
    MCU_MAIN_PY                 = "MCU_MAIN_PY"
    MCU_TYPE                    = "MCU_TYPE"
    ERASE_MCU_FLASH             = "ERASE_MCU_FLASH"
    LOAD_MICROPYTHON            = "LOAD_MICROPYTHON"
    LOAD_APP                    = "LOAD_APP"
    MEM_MON_RUN_GC              = "MEM_MON_RUN_GC"
    MEM_MON_POLL_SEC            = "MEM_MON_POLL_SEC"
    SCAN_PORT_STR               = "SCAN_PORT_STR"
    SCAN_SECONDS                = "SCAN_SECONDS"
    SCAN_IP_ADDRESS             = "SCAN_IP_ADDRESS"
    DEFAULT_CONFIG              = {WIFI_SSID: "",
                                   WIFI_PASSWORD: "",
                                   DEVICE_ADDRESS: "",
                                   MCU_MAIN_PY: "",
                                   MCU_TYPE: LoaderBase.RPI_PICOW_MCU_TYPE,
                                   ERASE_MCU_FLASH: True,
                                   LOAD_MICROPYTHON: True,
                                   LOAD_APP: True,
                                   MEM_MON_RUN_GC: True,
                                   MEM_MON_POLL_SEC: 5,
                                   SCAN_PORT_STR: YDevScanner.YDEV_DISCOVERY_PORT,
                                   SCAN_SECONDS: 5,
                                   SCAN_IP_ADDRESS: ""}
    DESCRIP_STYLE_1             = '<span style="font-size:1.5em;">'
    SERIAL_PORT_OPEN            = 'SERIAL_PORT_OPEN'

    @staticmethod
    def GetCmdOpts():
        """@brief Get a reference to the command line options.
        @return A tuple containing
                0 - The options instance.
                1 - A Launcher instance."""
        parser = argparse.ArgumentParser(description="A tool to manage MCU devices using a GUI interface.",
                                        formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument("--address",  help=f"Address that the GUI server is bound to (default={GUIServer.DEFAULT_SERVER_ADDRESS}).", default=GUIServer.DEFAULT_SERVER_ADDRESS)
        parser.add_argument("-p", "--port",     type=int, help=f"The TCP server port to which the GUI server is bound to (default={GUIServer.DEFAULT_SERVER_PORT}).", default=GUIServer.DEFAULT_SERVER_PORT)
        parser.add_argument("-d", "--debug",    action='store_true', help="Enable debugging.")
        launcher = Launcher("icon.png", app_name="MPY_Tool")
        launcher.addLauncherArgs(parser)
        options = parser.parse_args()
        return (options, launcher)

    def __init__(self, uio, options):
        """@brief Constructor
           @param uio A UIO instance
           @param options The command line options instance."""
        super().__init__(uio.isDebugEnabled(), GUIServer.LOG_PATH)
        self._uio                       = uio
        self._options                   = options
        self._cfgMgr                    = ConfigManager(self._uio, GUIServer.CFG_FILENAME, GUIServer.DEFAULT_CONFIG)
        self._serialPortSelect1         = None
        self._serialPortSelect2         = None
        self._upgradeAppPathInput       = None
        self._serialPortSelect1         = None
        self._serialPortSelect2         = None
        self._serialPortSelect3         = None
        self._app_main_py_input         = None
        self._select_main_py_button     = None
        self._installSWButton           = None
        self._loadMicroPythonInput      = None
        self._eraseMCUFlashInput        = None
        self._serialTXQueue             = Queue()
        self._loadConfig()

    def start(self):
        """@brief Start the App server running."""
        self._uio.info("Starting GUI...")
        TabbedNiceGui.CheckPort(self._options.port)
        try:
            tabNameList = ('Install',
                           'WiFi',
                           'Upgrade',
                           'Serial Port',
                           'Scan',
                           'Memory Monitor')
            # This must have the same number of elements as the above list
            tabMethodInitList = [self._initInstallTab,
                                 self._initWiFiTab,
                                 self._initUpgradeTab,
                                 self._initSerialTab,
                                 self._initScanTab,
                                 self._initMemMonTab]

            self.initGUI(tabNameList,
                          tabMethodInitList,
                          address=self._options.address,
                          port=self._options.port,
                          pageTitle=GUIServer.PAGE_TITLE,
                          reload=False)

        finally:
            self.close()

    def _initInstallTab(self):
        """@brief Create the install micropython tab contents."""
        markDownText = GUIServer.DESCRIP_STYLE_1+"""Install software on an MCU via a USB connection."""
        ui.markdown(markDownText)

        self._installPicoDialog = YesNoDialog("Power down the  RPi Pico W, hold it's button down and then power it back up. Then select the OK button below.",
                                              self._startInstallThread,
                                              successButtonText = "OK",
                                              failureButtonText = "Cancel")
        self._installEsp32Dialog = YesNoDialog("Hold the non ESP32 reset button down and then press and release the reset button. Then select the OK button below.",
                                               self._startInstallThread,
                                               successButtonText = "OK",
                                               failureButtonText = "Cancel")
        with ui.row():
            self._mcuTypeSelect = ui.select(options=[LoaderBase.RPI_PICOW_MCU_TYPE,
                                                     LoaderBase.RPI_PICO2W_MCU_TYPE,
                                                     LoaderBase.ESP32_MCU_TYPE,
                                                     LoaderBase.ESP32C3_MCU_TYPE,
                                                     LoaderBase.ESP32C6_MCU_TYPE],
                                                     value=LoaderBase.RPI_PICOW_MCU_TYPE,
                                                     label='MCU Type').style('width: 200px;')

            self._mcuTypeSelect.tooltip("The type of microcontroller (MCU) to load.")
            self._mcuTypeSelect.value = self._cfgMgr.getAttr(GUIServer.MCU_TYPE)
            self._serialPortSelect1 = ui.select(options=[], label='MCU serial port', on_change=self._serialPortSelect1Changed).style('width: 200px;')
            self._serialPortSelect1.tooltip("The serial port to which the MCU is connected.")
            updateSerialPortButton = ui.button('update serial port list', on_click=self._updateSerialPortList)
            updateSerialPortButton.tooltip("Update the list of available serial ports.")

        with ui.row():
            self._eraseMCUFlashInput = ui.switch("Erase MCU flash", value=True, on_change=self._checkSWStates).style('width: 200px;')
            self._eraseMCUFlashInput.value = self._cfgMgr.getAttr(GUIServer.ERASE_MCU_FLASH)
            self._eraseMCUFlashInput.tooltip("Turn this on if you want to erase the contents of the MCU flash before loading it.")

            self._loadMicroPythonInput = ui.switch("Load MicroPython to MCU flash", value=True, on_change=self._checkSWStates).style('width: 200px;')
            self._loadMicroPythonInput.value = self._cfgMgr.getAttr(GUIServer.LOAD_MICROPYTHON)
            self._loadMicroPythonInput.tooltip("Turn this on if you want to load MicroPython onto the MCU flash memory.")

            self._loadAppInput = ui.switch("Load App to MCU flash", value=True, on_change=self._updateAppField).style('width: 200px;')
            self._loadAppInput.value = self._cfgMgr.getAttr(GUIServer.LOAD_APP)
            self._loadAppInput.tooltip("Turn this on if you want to load the App onto the MCU flash memory")

            self._loadMpyInput = ui.switch("Load *.mpy files to MCU flash", value=True, on_change=self._updateAppField).style('width: 200px;')
            self._loadMpyInput.value = True
            self._loadMpyInput.tooltip("Load *.mpy files rather than *.py files as they use less flash memory.")

        with ui.row():
            self._app_main_py_input = ui.input(label='MCU micropython main.py').style('width: 800px;')
            self._app_main_py_input.value = self._cfgMgr.getAttr(GUIServer.MCU_MAIN_PY)
            self._select_main_py_button = ui.button('select mcu main.py', on_click=self._select_main_py)
            self._appendButtonList(self._select_main_py_button)

        self._installSWButton = ui.button('Install SW', on_click=self._installMicroPythonButtonHandler)
        # Add to button list so that button is disabled while activity is in progress.
        self._appendButtonList(self._installSWButton)
        # Populate the list of available serial ports if possible.
        self._updateSerialPortList()

        self._app_main_py_input.on('change', self._mcu_main_py_updated)
        self._mcuTypeSelect.on('update:modelValue', self._mcu_type_updated)

    def _serialPortSelect1Changed(self):
        if self._serialPortSelect2:
            self._serialPortSelect2.value = self._serialPortSelect1.value
        if self._serialPortSelect3:
            self._serialPortSelect3.value = self._serialPortSelect1.value

    def _get_mcu_app_path(self):
        """@return the path to the MCU micropython app."""
        return os.path.dirname(self._app_main_py_input.value)

    def _mcu_type_updated(self, event):
        """@brief Called when the mcu app path is updated."""
        self._cfgMgr.addAttr(GUIServer.MCU_TYPE, self._mcuTypeSelect.value)
        self._saveConfig()

    def _mcu_main_py_updated(self, event):
        """@brief Called when the mcu app path is updated in the install tab."""
        self._cfgMgr.addAttr(GUIServer.MCU_MAIN_PY, self._app_main_py_input.value)
        self._saveConfig()
        if self._upgradeAppPathInput:
            self._upgradeAppPathInput.value = self._app_main_py_input.value

    def _upgradeAppPathInputUpdated(self, event):
        """@brief Called when the mcu app path is updated in the upgrade tab."""
        self._cfgMgr.addAttr(GUIServer.MCU_MAIN_PY, self._upgradeAppPathInput.value)
        self._saveConfig()
        self._app_main_py_input.value = self._upgradeAppPathInput.value

    def _updateSerialPortList(self):
        """@brief Update the available serial port list for the install tab."""
        serialPortWidgetList = []
        if self._serialPortSelect1:
            serialPortWidgetList.append(self._serialPortSelect1)

        if self._serialPortSelect2:
            serialPortWidgetList.append(self._serialPortSelect2)

        if self._serialPortSelect3:
            serialPortWidgetList.append(self._serialPortSelect3)

        devNameList = []
        portInfoList = MCUBase.GetSerialPortList()

        for serialPortWidget in serialPortWidgetList:
            for portInfo in portInfoList:
                devNameList.append(portInfo.device)
            if len(devNameList) > 0:
                serialPortWidget.options = devNameList
                # Default to the first in the list
                serialPortWidget.value = devNameList[0]
            else:
                serialPortWidget.options = []
            serialPortWidget.update()

    def _get_currently_selected_path(self):
        """@return the path currently selected holding the main.py file."""
        selected_path = '/'
        currently_selected = self._app_main_py_input.value
        if os.path.isfile(currently_selected):
            selected_path = os.path.dirname(currently_selected)
        elif os.path.isdir(currently_selected):
            selected_path = currently_selected
        return selected_path

    async def _select_main_py(self):
        """@brief Select the MCU main.py micropython file."""
        selected_path = self._get_currently_selected_path()
        result = await local_file_picker(selected_path)
        if result:
            selected_file = result[0]
            if selected_file.endswith('main.py'):
                self._app_main_py_input.value = selected_file
                self._upgradeAppPathInput.value = selected_file
                self._saveConfig()
            else:
                self.error(f"{selected_file} selected. You must select a main.py file.")

    def _checkSWStates(self):
        """@brief Check the switch states and disable the Install SW button if no actions are selected."""
        if self._loadMicroPythonInput and self._eraseMCUFlashInput:
            self._cfgMgr.addAttr(GUIServer.ERASE_MCU_FLASH, self._eraseMCUFlashInput.value)
            self._cfgMgr.addAttr(GUIServer.LOAD_MICROPYTHON, self._loadMicroPythonInput.value)
            self._saveConfig()

        if self._installSWButton:
            if not self._eraseMCUFlashInput.value and not self._loadMicroPythonInput.value and not self._loadAppInput.value:
                self._installSWButton.disable()
            else:
                self._installSWButton.enable()

    def _updateAppField(self):
        """@brief Update the App field."""
        self._cfgMgr.addAttr(GUIServer.LOAD_APP, self._loadAppInput.value)
        self._saveConfig()

        if self._app_main_py_input and self._select_main_py_button:
            if self._loadAppInput.value:
                self._app_main_py_input.enable()
                self._select_main_py_button.enable()
            else:
                self._app_main_py_input.disable()
                self._select_main_py_button.disable()
        self._checkSWStates()

    def _installMicroPythonButtonHandler(self, event):
        """@brief Process button click.
           @param event The button event."""
        if self._is_serial_port_open():
            ui.notify('The serial port is open in the SERIAL PORT tab. Close it and try again.', type='negative')
            return

        self._clearMessages()
        mcuType = self._mcuTypeSelect.value
        if mcuType:
            # For ESP32's you must erase the flash before loading it
            if mcuType in LoaderBase.VALID_ESP32_TYPES and self._loadMicroPythonInput.value:
                self._eraseMCUFlashInput.value = True

            # If you erase the flash and want to load a MicroPython app you must load MicroPython
            if self._eraseMCUFlashInput.value and not self._loadMicroPythonInput.value and self._loadAppInput.value:
                self._loadMicroPythonInput.value = True

            if self._loadMicroPythonInput.value and self._mcuTypeSelect.value == LoaderBase.ESP32C6_MCU_TYPE:
                ui.notify("Note that ESP32C6 MicroPython is still under development. Some features don't work, E.G machine.Timer in the version to be loaded.", type='warning')

            # In this case we expect MicroPython to have been loaded to the MCU previously.
            if not self._eraseMCUFlashInput.value and not self._loadMicroPythonInput.value:
                self._startInstallThread()

            else:

                if LoaderBase.IsPicoW(mcuType):
                    self._installPicoDialog.show()

                elif LoaderBase.IsEsp32(mcuType):
                    self._installEsp32Dialog.show()

        else:
            self.error("No MCU detected connected to a USB port")

    def _startInstallThread(self):
        """@brief Start the SW installation thread."""
        self._initTask()
        self._saveConfig()
        mcuType = self._mcuTypeSelect.value
        startMessage="MCU: "
        duration = 0
        try:
            # We just set a long progress bar duration seconds here that should cover most installs.
            # We used to try and guess the time but it wasn't very accurate for various reasons.
            # Considered removing the progress bar but it's useful to know that the thread
            # is still active.
            duration = 600
            if LoaderBase.IsPicoW(mcuType):
                self.info(f"Checking for a mounted {mcuType} drive...")
                self._startProgress(durationSeconds=duration, startMessage=startMessage)
            else:
                self._checkSerialPortAvailable(self._serialPortSelect1.value)
                self._startProgress(durationSeconds=duration, startMessage=startMessage)

            t = threading.Thread( target=self._installSW)
            t.daemon = True
            t.start()

        except Exception as ex:
            self.reportException(ex)
            self._sendEnableAllButtons(True)

    def _checkSerialPortAvailable(self, serialPortDev):
        """@brief Check that the selected serial port is present and available for use.
                  An Exception is thrown if not available."""
        if serialPortDev is None or len(serialPortDev) == 0:
            raise Exception("No serial port selected. Connect MCU via a USB cable and select the 'UPDATE SERIAL PORT LIST' button.")

        portInfoList = MCUBase.GetSerialPortList()
        found = False
        for portInfo in portInfoList:
            if portInfo.device == serialPortDev:
                found = True
                break

        # If the selected serial port is not available, report to user
        if not found:
            raise Exception(f"{serialPortDev} was not found.")

        if found:
            try:
                ser = serial.serial_for_url(serialPortDev, do_not_open=False, exclusive=True)
                ser.close()

            except serial.serialutil.SerialException:
                raise Exception(f"{serialPortDev} serial port is not available as it's in use.")

        else:
            raise Exception(f"{serialPortDev} appears to be in use.")

    def _installSW(self):
        """@brief Called to do the work of wiping flash and installing MicroPython onto the MCU."""
        try:
            try:
                mcuType = self._mcuTypeSelect.value
                self.info(f"MCU: {mcuType}.")
                # Wait for Pico path if we need it.
                if LoaderBase.IsPicoW(mcuType) and (self._eraseMCUFlashInput.value or self._loadMicroPythonInput.value):
                    USBLoader.WaitForPicoPath(mcuType)

                usbLoader = USBLoader(mcuType, uio=self)
                usbLoader.setSerialPort(self._serialPortSelect1.value)
                mcu_app_path = self._get_mcu_app_path()
                # If we will load the MCU app check it first so
                # as erase and load MicroPython can take some time.
                if self._loadAppInput.value:
                    USBLoader.CheckPythonCode(mcu_app_path)

                fsStats = usbLoader.install(self._eraseMCUFlashInput.value, \
                                  self._loadMicroPythonInput.value, \
                                  self._loadAppInput.value, \
                                  mcu_app_path, \
                                  self._loadMpyInput.value, \
                                  showInitialPrompt=False)

                if fsStats:
                    flashSize = fsStats[0]
                    freeSpace = fsStats[1]
                    usedSpace = flashSize-freeSpace
                    percentageUsed = 0
                    if usedSpace > 0:
                        percentageUsed = int( (usedSpace/flashSize)*100.0 )
                    self.info(f"Flash partition size (MB): {flashSize/1E6:.3f}")
                    self.info(f"Used space(MB):            {usedSpace/1E6:.3f}")
                    self.info(f"Free space(MB):            {freeSpace/1E6:.3f}")
                    self.info(f"% partition used:          {percentageUsed}")
                    self.infoDialog("Software installation complete.")

            except Exception as ex:
                self.reportException(ex)

        finally:
            self._sendEnableAllButtons(True)

    def _saveConfig(self):
        """@brief Save some parameters to a local config file."""
        raise Exception("PJA GUIServerEXT1 used instead.")

    def _loadConfig(self):
        """@brief Load the config from a config file."""
        try:
            self._cfgMgr.load()
        except:
            pass

    def _initWiFiTab(self):
        """@brief Create the Wifi tab contents."""
        pass

    def _setWiFiNetwork(self, wifiSSID, wifiPassword):
        """@brief Set the Wifi network on a YDev device..
           @param wifiSSID The WiFi SSID to set.
           @param wifiPassword The WiFi password to set."""
        startT = time()
        try:
            try:
                if len(wifiSSID) == 0:
                    self.error("A WiFi SSID is required.")

                elif len(wifiPassword) == 0:
                    self.error("A WiFi password is required.")

                else:
                    self.info("Checking for a USB connected MCU.")
                    mcuType = self._mcuTypeSelect.value
                    self.info(f"MCU: {mcuType}.")
                    usbLoader = USBLoader(mcuType, uio=self)
                    self._deviceIPAddressInput1.value = usbLoader.setupWiFi(wifiSSID, wifiPassword)
                    self.info("WiFi is now configured on MCU.")
                    self._saveConfig()
                    elapsedT = time()-startT
                    self.info(f"Took {elapsedT:.1f} seconds.")
                    self.infoDialog("WiFi setup complete.")

            except Exception as ex:
                self.reportException(ex)

        finally:
            self._sendEnableAllButtons(True)

    def _deviceIPAddressInput1Change(self):
        # Update all IP address fields if this one changes
        self._copyYDevAddress(self._deviceIPAddressInput1.value)

    def _initUpgradeTab(self):
        """@brief Create the Wifi tab contents."""
        markDownText = f"{GUIServer.DESCRIP_STYLE_1}Upgrade the device App over your WiFi network."
        ui.markdown(markDownText)
        with ui.row():
            self._deviceIPAddressInput1 = ui.input(label='Device address', on_change=self._deviceIPAddressInput1Change)
            self._upgradeMpyInput = ui.switch("Load *.mpy files to MCU flash", value=True, on_change=self._updateAppField).style('width: 200px;')
            self._upgradeMpyInput.value = True
            self._upgradeMpyInput.tooltip("Load *.mpy files rather than *.py files as they use less flash memory.")

        ipAddress = self._cfgMgr.getAttr(GUIServer.DEVICE_ADDRESS)
        if ipAddress:
            self._deviceIPAddressInput1.value = ipAddress

        with ui.row():
            self._upgradeAppPathInput = ui.input(label='App Path').style('width: 800px;')
            self._upgradeAppPathInput.value = self._cfgMgr.getAttr(GUIServer.MCU_MAIN_PY)
            self._defaultUpgradeAppButton = ui.button('select mcu main.py', on_click=self._select_main_py)

        self._upgradeButton = ui.button('Upgrade App', on_click=self._upgradeButtonHandler)
        # Add to button list so that button is disabled while activity is in progress.
        self._appendButtonList(self._upgradeButton)

        self._upgradeAppPathInput.on('change', self._upgradeAppPathInputUpdated)

    def _upgradeButtonHandler(self, event):
        """@brief Process button click.
           @param event The button event."""
        self._initTask()
        self._saveConfig()
        # We just set a long progress bar duration seconds here that should cover most installs.
        # We used to try and guess the time but it wasn't very accurate for various reasons.
        # Considered removing the progress bar but it's useful to know that the thread
        # is still active.
        duration = 240
        self._startProgress(durationSeconds=duration)
        t = threading.Thread( target=self._appUpgrade)
        t.daemon = True
        t.start()

    def _appUpgrade(self):
        """@brief Upgrade the MCU app."""
        startT = time()
        try:
            try:
                address = self._deviceIPAddressInput1.value
                appPath = self._upgradeAppPathInput.value
                if len(address) == 0:
                    self.error("A device address is required.")

                else:
                    self.info(f"Upgrading MCU at {address}.")

                    upgradeManager = UpgradeManager(self._mcuTypeSelect.value, uio=self)
                    upgradeManager.upgrade(address, appPath, loadMpyFiles=self._upgradeMpyInput.value)

                    elapsedT = time()-startT
                    self.info(f"Took {elapsedT:.1f} seconds.")
                    self.infoDialog("Upgrade complete.")

            except Exception as ex:
                self.reportException(ex)

        finally:
            self._sendEnableAllButtons(True)

    def _initScanTab(self):
        """@brief Create the scan tab contents."""
        markDownText = GUIServer.DESCRIP_STYLE_1+"""Scan for active devices on the LAN/WiFi."""
        ui.markdown(markDownText)
        portOptions = [f'YDEV: {YDevScanner.YDEV_DISCOVERY_PORT}',
                       f'CT6:   {YDevScanner.CT6_DISCOVERY_PORT}']
        with ui.row():
            self._scanPortSelect = ui.select(options=portOptions,
                                            label="Scan Port",
                                            value=portOptions[0]).style('width: 300px;')
            self._scanPortSelect.tooltip("The UDP port to which are you there (AYT) broadcast messages are sent.")
            self._scanSecondsInput = ui.number(label='Scan Period (Seconds)', value=3, format='%d', min=1, max=60)
            self._scanSecondsInput.style('width: 150px')
            self._scanIPAddressInput = ui.input(label='IP Address')
            self._scanIPAddressInput.tooltip("Set an IP address if you wish to limit scan to a single device.")
        with ui.row():
            self._scanButton = ui.button('Scan', on_click=self._scanButtonHandler)
        # Add to button list so that button is disabled while activity is in progress.
        self._appendButtonList(self._scanButton)

        self._scanPortSelect.value = self._cfgMgr.getAttr(GUIServer.SCAN_PORT_STR)
        self._scanSecondsInput.value = self._cfgMgr.getAttr(GUIServer.SCAN_SECONDS)
        self._scanIPAddressInput.value = self._cfgMgr.getAttr(GUIServer.SCAN_IP_ADDRESS)

        # If no port has been set select the first in the list
        if not self._scanPortSelect.value:
            self._scanPortSelect.value = portOptions[0]

        # Enable events once we've set the initial state from stored cfg
        self._scanPortSelect.on('update:modelValue', self._saveConfig)
        self._scanSecondsInput.on('change', self._saveConfig)
        self._scanIPAddressInput.on('change', self._saveConfig)

    def _scanButtonHandler(self, event):
        """@brief Process button click.
           @param event The button event."""
        self._initTask()
        self._saveConfig()
        self._startProgress(durationSeconds=self._scanSecondsInput.value)
        t = threading.Thread(target=self._scanForDevices)
        t.daemon = True
        t.start()

    def _getSelectedPort(self):
        """@brief Get the selected UDP broadcast port.
           @return The selected port as an integer value or None if not found."""
        port = None
        elems = self._scanPortSelect.value.split(":")
        if len(elems) == 2:
            try:
                port = int(elems[1])
            except ValueError:
                pass
        if port is None:
            self.info("Failed to read the scan port.")
        return port

    def _scanForDevices(self):
        """@brief Scan for YDev devices."""
        try:
            try:
                port = self._getSelectedPort()
                if port is not None:
                    yDevScanner = YDevScanner(self)
                    yDevScanner.scan(runSeconds=self._scanSecondsInput.value,
                                     addressOfInterest=self._scanIPAddressInput.value,
                                     port=port)
                    self.infoDialog("Scan complete.")

            except Exception as ex:
                self.reportException(ex)

        finally:
            self._sendEnableAllButtons(True)

    def _initSerialTab(self):
        """@brief Show the serial port output."""
        with ui.row():
            self._serialPortSelect3 = ui.select(options=[], label='MCU serial port', on_change=self._serialPortSelect3Changed).style('width: 200px;')
            self._serialPortSelect3.tooltip("The serial port to which the MCU is connected.")
            updateSerialPortButton = ui.button('update serial port list', on_click=self._updateSerialPortList)
            updateSerialPortButton.tooltip("Update the list of available serial ports.")

        with ui.row():
            self._openSerialPortButton  = ui.button('Open', on_click=self._openSerialPortHandler)
            self._closeSerialPortButton = ui.button('Close', on_click=self._closeSerialPortHandler)

        with ui.row():
            self._sendCtrlCButton  = ui.button('CTRL C', on_click=self._sendCtrlC).tooltip("Stop program and get REPL (>>>) prompt.")
            self._sendCtrlBButton  = ui.button('CTRL B', on_click=self._sendCtrlB).tooltip("Get MicroPython version from REPL prompt.")
            self._sendCtrlDButton  = ui.button('CTRL D', on_click=self._sendCtrlD).tooltip("Start running the main.py file (if it exists) from REPL prompt.")
            self._sendTextButton  = ui.button('SEND', on_click=self._sendText)
            self._sendTextInput = ui.input(label='Text to send').style('width: 400px;')
            self._sendTextInput.on('keydown.enter', lambda _: self._sendText())

        self._setSerialPortClosed()

        # Populate the list of available serial ports if possible.
        self._updateSerialPortList()

    def _serialPortSelect3Changed(self):
        if self._serialPortSelect1:
            self._serialPortSelect1.value = self._serialPortSelect3.value
        if self._serialPortSelect2:
            self._serialPortSelect2.value = self._serialPortSelect3.value

    def _update_serial_port_open_buttons(self, open):
        self._openSerialPortButton.enabled = not open
        self._closeSerialPortButton.enabled = open
        self._sendCtrlBButton.enabled = open
        self._sendCtrlCButton.enabled = open
        self._sendCtrlDButton.enabled = open
        self._sendTextButton.enabled = open

    def _openSerialPortHandler(self):
        # Enable the close serial port button so that the user can close the serial port when they are finished.
        if not self._serialPortSelect1.value:
            ui.notify('No serial port is selected.', type='negative')
        else:
            t = threading.Thread(target=self._viewSerialPortData)
            t.daemon = True
            t.start()

    def _is_serial_port_open(self):
        """@brief Determine if the user has opened the serial port in the SERIAL PORT tab.
           @return True if the serial port is open."""
        open = False
        if self._closeSerialPortButton.enabled:
            open = True
        return open

    def _sendSerialPortOpen(self, open):
        """@brief Send a message to the GUI to tell it that the serial port is open.
           @param open If True the serial port has been opened."""
        msgDict = {GUIServer.SERIAL_PORT_OPEN: open}
        self.updateGUI(msgDict)

    def _viewSerialPortData(self):
        """@brief Read data from the available serial port and display it."""
        try:
            ser = None
            usbLoader = None
            self._viewSerialRunning = True
            self.info("Checking for connected MCU's...")
            while self._viewSerialRunning:
                mcuType = self._mcuTypeSelect.value
                serialPort = self._serialPortSelect1.value
                # If we have an MCU type
                if mcuType:
                    self.info(f"{mcuType} on {serialPort}")
                    usbLoader = USBLoader(mcuType, uio=self)
                    try:
                        ser = usbLoader.openFirstSerialPort()
                    except serial.serialutil.SerialException as ex:
                        if str(ex).find('Could not exclusively lock port'):
                            self.error("It appears the serial port is in use by another program.")
                        else:
                            self.error(str(ex))
                        return
                    self._sendSerialPortOpen(True)
                    try:
                        try:
                            while self._viewSerialRunning:
                                while ser.in_waiting > 0:
                                    bytesRead = ser.read(ser.in_waiting)
                                    sRead = bytesRead.decode("utf-8", errors="ignore")
                                    sRead = sRead.rstrip('\r\n')
                                    if len(sRead) > 0:
                                        self.info(serialPort + ": " + sRead)

                                while not self._serialTXQueue.empty():
                                    txStr = self._serialTXQueue.get()
                                    ser.write(txStr.encode())

                                # Ensure we don't spinlock
                                sleep(0.1)

                        except:
                            pass

                    finally:
                        if ser:
                            ser.close()
                            ser = None
                            if usbLoader:
                                self.info(f"Closed {usbLoader._serialPort}")
                            usbLoader = None

                # Ensure we don't spinlock
                sleep(0.1)

        finally:
            if ser:
                ser.close()
                ser = None
                if usbLoader:
                    self.info(f"Closed {usbLoader._serialPort}")
                usbLoader = None
            self._sendSerialPortOpen(False)
            self._sendEnableAllButtons(True)

    def _sendCtrlB(self):
        self._serialTXQueue.put('\02')

    def _sendCtrlC(self):
        self._serialTXQueue.put('\03')

    def _sendCtrlD(self):
        self._serialTXQueue.put('\04')

    def _sendText(self):
        text = self._sendTextInput.value
        if text:
            self._serialTXQueue.put(text + '\r')

    def _closeSerialPortHandler(self):
        """@brief Shut down the running view serial port task."""
        self.info("Shutting down...")
        self._setSerialPortClosed()

    def _setSerialPortClosed(self):
        self._closeSerialPortButton.disable()
        self._sendCtrlBButton.disable()
        self._sendCtrlCButton.disable()
        self._sendCtrlDButton.disable()
        self._sendTextButton.disable()
        self._viewSerialRunning = False

    def _initMemMonTab(self):
        """@initialise the memory monitor tab."""
        markDownText = f"{GUIServer.DESCRIP_STYLE_1}Monitor the RAM/Disk usage along with the uptime of a device."
        ui.markdown(markDownText)
        with ui.row():
            self._deviceIPAddressInput2 = ui.input(label='Device address')
            self._deviceIPAddressInput2.tooltip("The IP address of the MCU device to be monitored.")
            self._runGCInput = ui.switch("Run Python GC", value=True, on_change=self._runGCInputUpdated).style('width: 200px;')
            self._runGCInput.tooltip("Run the python garbage collector just before reading the memory usage.")
            self._runGCInput.value = self._cfgMgr.getAttr(GUIServer.MEM_MON_RUN_GC)

        self._memMonSecondsInput = ui.number(label='Poll Period (Seconds)', value=5, format='%d', min=1, max=3600).style('width: 300px')
        self._memMonSecondsInput.tooltip("The time in seconds between attempts to read the stats from the device.")
        self._memMonSecondsInput.value = self._cfgMgr.getAttr(GUIServer.MEM_MON_POLL_SEC)

        with ui.row():
            self._startMemMonButton = ui.button('Start', on_click=self._startMemMon)
            self._startMemMonButton.tooltip("Start monitoring memory usage.")
            self._appendButtonList(self._startMemMonButton)

        ipAddress = self._cfgMgr.getAttr(GUIServer.DEVICE_ADDRESS)
        if ipAddress:
            self._deviceIPAddressInput2.value = ipAddress

        self._deviceIPAddressInput2.on('change', self._deviceIPAddressInput2Change)
        self._memMonSecondsInput.on('change', self._memMonSecondsInputUpdated)

    def _deviceIPAddressInput2Change(self):
        # Update all IP address fields if this one changes
        self._copyYDevAddress(self._deviceIPAddressInput2.value)
        self._saveConfig()

    def _runGCInputUpdated(self):
        """@brief Update GC selected state in config."""
        self._saveConfig()

    def _memMonSecondsInputUpdated(self):
        """@brief Update the memory monitor poll time."""
        self._saveConfig()

    def _startMemMon(self):
        """@brief Start monitoring MCU device memory usage."""
        # Set min value if not set
        if not self._memMonSecondsInput.value:
            self._memMonSecondsInput.value = 1

        self.info("Started memory monitor.")
        # Open another browser window to show the memory usage.
        @ui.page('/memory_usage')
        def memory_usage():
            mu = MemoryUsage(self._options,
                        self._deviceIPAddressInput2.value,
                        self._runGCInput.value,
                        self._memMonSecondsInput.value,
                        self._uio.isDebugEnabled())
            mu.start()
         # This will open the new page in a new browser window
        ui.run_javascript("window.open('/memory_usage', '_blank')")

    def close(self):
            """@brief Close down the app server."""
            ui.notify("Shutting down application...")
            ui.timer(interval=2, callback=self._shutdownApp)

    def _shutdownApp(self):
        """@brief Shutdown the app"""
        app.shutdown()

class MemoryUsage(TabbedNiceGui):

    RAM_TOTAL_BYTES = "RAM_TOTAL_BYTES"
    RAM_USED_BYTES = "RAM_USED_BYTES"
    RAM_FREE_BYTES = "RAM_FREE_BYTES"
    DISK_TOTAL_BYTES = "DISK_TOTAL_BYTES"
    DISK_USED_BYTES = "DISK_USED_BYTES"
    UPTIME_SECONDS = "UPTIME_SECONDS"

    # Allow for 1 day at second resolution.
    # !!! This may be too large. It may be useful to give the user control of this.
    MAX_PLOT_POINT_COUNT = 3600*24

    def __init__(self, options, address, runGC, pollTime, debugEnabled):
        super().__init__(debugEnabled)
        self._options = options
        self._address = address
        self._runGC = runGC
        self._pollTime = pollTime
        self._init_gui()

    def _init_gui(self):
        self._time_data = []
        self._ram_used_data = []
        self._ram_free_data = []
        self._ram_total_data = []
        self._disk_used_data = []
        self._disk_free_data = []
        self._disk_total_data = []
        self._uptime_seconds_data = []
        self._memMonRunning = False
        self._toGUIQueue = Queue()
        self._initMemMonTab()

    def _initMemMonTab(self):
        """@brief Initialise the memory monitor tab."""

        with ui.row():
            ui.label("MCU Memory Monitor").style('font-size: 32px; font-weight: bold;')

        with ui.row():
            self._stopMemMonButton = ui.button('Stop', on_click=self._stop)
            self._stopMemMonButton.tooltip("Stop a monitoring memory usage.")

        with ui.column().style('width: 100%; margin: 0 auto;'):
            self._ramPlot = ui.plotly(self._createRamPlot()).style('width: 100%; margin: 0 auto;')
            self._ramPlot.update()

        with ui.row().style('width: 100%; margin: 0 auto;'):
            self._diskPlot = ui.plotly(self._createDiskPlot()).style('width: 100%; margin: 0 auto;')
            self._diskPlot.update()

        with ui.row().style('width: 100%; margin: 0 auto;'):
            self._upTimePlot = ui.plotly(self._createUpTimePlot()).style('width: 100%; margin: 0 auto;')
            self._upTimePlot.update()

        ui.timer(interval=TabbedNiceGui.GUI_TIMER_SECONDS, callback=self.guiTimerCallback)

    def _createRamPlot(self):
        with ui.row():
            layout = go.Layout(title="Ram Usage",
                               showlegend=True,
                               plot_bgcolor="black",
                               paper_bgcolor="black",
                               xaxis=dict(title='Time'),
                               yaxis=dict(title='Bytes'))
            fig = go.Figure(layout=layout)
            ram_used_trace = go.Scatter(x=self._time_data, y=self._ram_used_data, mode='lines+markers', name='Used')
            ram_free_trace = go.Scatter(x=self._time_data, y=self._ram_free_data, mode='lines+markers', name='Free')
            ram_total_trace = go.Scatter(x=self._time_data, y=self._ram_total_data, mode='lines+markers', name='Total')
            fig.add_trace(ram_used_trace)
            fig.add_trace(ram_free_trace)
            fig.add_trace(ram_total_trace)

        return fig

    def _createDiskPlot(self):
        with ui.row():
            layout = go.Layout(title="Disk Usage",
                               showlegend=True,
                               plot_bgcolor="black",
                               paper_bgcolor="black",
                               xaxis=dict(title='Time'),
                               yaxis=dict(title='Bytes'))
            fig = go.Figure(layout=layout)
            disk_used_trace = go.Scatter(x=self._time_data, y=self._disk_used_data, mode='lines+markers', name='Used')
            disk_free_trace = go.Scatter(x=self._time_data, y=self._disk_free_data, mode='lines+markers', name='Free')
            disk_total_trace = go.Scatter(x=self._time_data, y=self._disk_total_data, mode='lines+markers', name='Total')
            fig.add_trace(disk_used_trace)
            fig.add_trace(disk_free_trace)
            fig.add_trace(disk_total_trace)

        return fig

    def _createUpTimePlot(self):
        with ui.row():
            layout = go.Layout(title="Uptime",
                               showlegend=True,
                               plot_bgcolor="black",
                               paper_bgcolor="black",
                               xaxis=dict(title='Time'),
                               yaxis=dict(title='Seconds'))
            fig = go.Figure(layout=layout)
            uptime_seconds_trace = go.Scatter(x=self._time_data, y=self._uptime_seconds_data, mode='lines+markers', name='Uptime')
            fig.add_trace(uptime_seconds_trace)
        return fig

    def _stop(self):
        """@brief Stop monitoring memory."""
        self._memMonRunning = False
        self._stopMemMonButton.disable()

    def start(self):
        t = threading.Thread(target=self._memMonThread)
        t.daemon = True
        t.start()

    def _getStats(self, address, runGC):
        """@brief Get the memory/disk usage and uptime stats.
           @param address The address of the device to get the stats from.
           @param runGC If True an attempt will be made to run the python garbage collector before reading the stats.
           @return A dict containing the stats."""
        url = f'http://{address}:{UpgradeManager.DEVICE_REST_INTERFACE_TCP_PORT}{UpgradeManager.GET_SYS_STATS}?gc={runGC}'
        self.debug(f"CMD: {url}")
        r = requests.get(url)
        obj = r.json()
        self.debug(f"CMD RESPONSE: { str(obj) }")
        return obj

    def _memMonThread(self):
        """@brief The thread that reads the memory usage data."""
        try:
            nextReadStatsTime = time()
            self._memMonRunning = True
            while self._memMonRunning:
                if time() >= nextReadStatsTime:
                    statsDict = self._getStats(self._address, self._runGC)
                    self._toGUIQueue.put(statsDict)
                    nextReadStatsTime = time() + self._pollTime
                sleep(0.5)

        except Exception as ex:
            self.error(str(ex))

    def guiTimerCallback(self):
        """@called periodically (quickly) to allow updates of the GUI."""
        while not self._toGUIQueue.empty():
            rxMessage = self._toGUIQueue.get()
            if isinstance(rxMessage, dict):
                self._processRXDict(rxMessage)

    def _processRXDict(self, rxDict):
        """@brief Process the dicts received from the GUI message queue.
           @param rxDict The dict received from the GUI message queue."""
        self._plot_stats(rxDict)

    def _plot_stats(self, statDict):
        """@brief Plot the stats from the PSU
           @param stats A tuple (volts, amps, watts)"""

        if MemoryUsage.RAM_TOTAL_BYTES in statDict and \
           MemoryUsage.RAM_USED_BYTES in statDict and \
           MemoryUsage.RAM_FREE_BYTES in statDict and \
           MemoryUsage.DISK_TOTAL_BYTES in statDict and \
           MemoryUsage.DISK_USED_BYTES in statDict and \
           MemoryUsage.UPTIME_SECONDS in statDict:
            self._time_data.append(datetime.datetime.now())
            self._ram_total_data.append(statDict[MemoryUsage.RAM_TOTAL_BYTES])
            self._ram_used_data.append(statDict[MemoryUsage.RAM_USED_BYTES])
            self._ram_free_data.append(statDict[MemoryUsage.RAM_FREE_BYTES])

            diskTotal = statDict[MemoryUsage.DISK_TOTAL_BYTES]
            diskUsed = statDict[MemoryUsage.DISK_USED_BYTES]
            diskFree = diskTotal - diskUsed
            self._disk_total_data.append(diskTotal)
            self._disk_used_data.append(diskUsed)
            self._disk_free_data.append(diskFree)
            self._uptime_seconds_data.append(statDict[MemoryUsage.UPTIME_SECONDS])

            # Limit the max size of the plot by removing the oldest points
            max_plot_points = MemoryUsage.MAX_PLOT_POINT_COUNT
            if self._time_data and max_plot_points:
                # Ensure the number of points is limited
                while len(self._time_data) > max_plot_points:
                    del self._time_data[0]
                    del self._ram_used_data[0]
                    del self._ram_free_data[0]
                    del self._ram_total_data[0]
                    del self._disk_used_data[0]
                    del self._disk_free_data[0]
                    del self._disk_total_data[0]
                    del self._uptime_seconds_data[0]

            # Update the plots and refresh them
            self._ramPlot.figure = self._createRamPlot()
            self._ramPlot.update()  # Ensure the display is refreshed

            self._diskPlot.figure = self._createDiskPlot()
            self._diskPlot.update()  # Ensure the display is refreshed

            self._upTimePlot.figure = self._createUpTimePlot()
            self._upTimePlot.update()  # Ensure the display is refreshed


class GUIServerEXT1(GUIServer):
    """@brief Add WiFi configuration to the GUIServer.
       This class integrates the WiFi setup with bluetooth (rather than just USB) that
       was not present in the parent class."""
    CFG_FILENAME                = ".mcu_tool_gui_ext1.cfg"
    USB_WIFI_SETUP_IF           = "USB_WIFI_SETUP_IF"
    USB                         = "USB"
    BLUETOOTH                   = "Bluetooth"
    BT_MAC_ADDRESS              = "BT_MAC_ADDRESS"
    SSID                        = "SSID"
    RSSI                        = "RSSI"
    YDEV_WIFI_SCAN_COMPLETE     = "YDEV_WIFI_SCAN_COMPLETE"
    SET_YDEV_IP_ADDRESS         = "SET_YDEV_IP_ADDRESS"
    SETUP_WIFI_IF               = "SETUP_WIFI_IF"
    DEFAULT_CONFIG              = {GUIServer.WIFI_SSID: "",
                                   GUIServer.WIFI_PASSWORD: "",
                                   GUIServer.DEVICE_ADDRESS: "",
                                   GUIServer.MCU_MAIN_PY: "",
                                   GUIServer.MCU_TYPE: LoaderBase.RPI_PICOW_MCU_TYPE,
                                   GUIServer.ERASE_MCU_FLASH: True,
                                   GUIServer.LOAD_MICROPYTHON: True,
                                   GUIServer.LOAD_APP: True,
                                   USB_WIFI_SETUP_IF: USB,
                                   GUIServer.MEM_MON_RUN_GC: True,
                                   GUIServer.MEM_MON_POLL_SEC: 5,
                                   SETUP_WIFI_IF: USB,
                                   GUIServer.SCAN_PORT_STR: YDevScanner.YDEV_DISCOVERY_PORT,
                                   GUIServer.SCAN_SECONDS: 5,
                                   GUIServer.SCAN_IP_ADDRESS: ""}

    def __init__(self, uio, options):
        """@brief Constructor
           @param uio A UIO instance
           @param options The command line options instance."""
        super().__init__(uio, options)
        self._wifiSSIDUSBInput = None
        self._wifiPasswordUSBInput = None
        self._deviceIPAddressInput1 = None
        self._deviceIPAddressInput2 = None
        self._wifi_setup_radio = None
        self._runGCInput = None
        self._memMonSecondsInput = None
        self._wifi_setup_radio = None
        self._scanPortSelect = None
        self._scanSecondsInput = None
        self._scanIPAddressInput = None
        self._cfgMgr = ConfigManager(self._uio, GUIServerEXT1.CFG_FILENAME, GUIServerEXT1.DEFAULT_CONFIG)
        self._loadConfig()

    def _saveConfig(self):
        """@brief Save some parameters to a local config file."""
        if self._app_main_py_input:
            self._cfgMgr.addAttr(GUIServer.MCU_MAIN_PY, self._app_main_py_input.value)
        if self._wifiSSIDUSBInput:
            self._cfgMgr.addAttr(GUIServerEXT1.WIFI_SSID, self._wifiSSIDUSBInput.value)
        if self._wifiPasswordUSBInput:
            self._cfgMgr.addAttr(GUIServerEXT1.WIFI_PASSWORD, self._wifiPasswordUSBInput.value)
        if self._deviceIPAddressInput1:
            self._cfgMgr.addAttr(GUIServerEXT1.DEVICE_ADDRESS, self._deviceIPAddressInput1.value)
        if self._wifi_setup_radio:
            self._cfgMgr.addAttr(GUIServerEXT1.USB_WIFI_SETUP_IF, self._wifi_setup_radio.value)
        if self._runGCInput:
            self._cfgMgr.addAttr(GUIServerEXT1.MEM_MON_RUN_GC, self._runGCInput.value)
        if self._memMonSecondsInput:
            self._cfgMgr.addAttr(GUIServerEXT1.MEM_MON_POLL_SEC, self._memMonSecondsInput.value)
        if self._wifi_setup_radio:
            self._cfgMgr.addAttr(GUIServerEXT1.SETUP_WIFI_IF, self._wifi_setup_radio.value)
        if self._scanPortSelect:
            self._cfgMgr.addAttr(GUIServerEXT1.SCAN_PORT_STR, self._scanPortSelect.value)
        if self._scanSecondsInput:
            self._cfgMgr.addAttr(GUIServerEXT1.SCAN_SECONDS, self._scanSecondsInput.value)
        if self._scanIPAddressInput:
            self._cfgMgr.addAttr(GUIServerEXT1.SCAN_IP_ADDRESS, self._scanIPAddressInput.value)

        self._cfgMgr.store()

    def _initWiFiTab(self):
        """@brief Create the Wifi tab contents."""
        # Init all the dialogs used in the WiFi setup process.
        self._initUsbWiFiDialog1()
        self._initUsbWiFiDialog2()
        self._initBluetoothWiFiDialog1()
        self._initBluetoothWiFiDialog2()

        markDownText = """
        <span style="font-size:1.5em;">Set the WiFi ssid and password to connect your MCU to a WiFi network via either a USB or Bluetooth connection.
        """
        ui.markdown(markDownText)
        wifiSetupIF = self._cfgMgr.getAttr(GUIServerEXT1.USB_WIFI_SETUP_IF)
        with ui.column():
            self._wifi_setup_radio = ui.radio([GUIServerEXT1.USB, GUIServerEXT1.BLUETOOTH], value=wifiSetupIF, on_change=self._wsrChanged).props('inline')

            with ui.row():
                self._serialPortSelect2 = ui.select(options=[], label='MCU serial port', on_change=self._serialPortSelect2Changed).style('width: 200px;')
                self._serialPortSelect2.tooltip("The serial port to which the MCU is connected.")
                self._updateSerialPortButton = ui.button('update serial port list', on_click=self._updateSerialPortList)
                self._updateSerialPortButton.tooltip("Update the list of available serial ports.")

            self._setWiFiButton = ui.button('Setup WiFi', on_click=self._startWifiSetup)

            self._appendButtonList(self._setWiFiButton)

        # Populate the list of available serial ports if possible.
        self._updateSerialPortList()
        self._setInitWiFiState()

    def _serialPortSelect2Changed(self):
        if self._serialPortSelect1:
            self._serialPortSelect1.value = self._serialPortSelect2.value
        if self._serialPortSelect3:
            self._serialPortSelect3.value = self._serialPortSelect2.value

    def _setInitWiFiState(self):
        if self._wifi_setup_radio.value != GUIServerEXT1.USB:
            self._serialPortSelect2.disable()
            self._updateSerialPortButton.disable()
        else:
            self._serialPortSelect2.enable()
            self._updateSerialPortButton.enable()

    def _wsrChanged(self):
        self._setInitWiFiState()
        self._saveConfig()

    def _initUsbWiFiDialog1(self):
        """@brief A dialog displayed as step 1 in the WiFi setup process when using a USB interface to talk to the MCU device."""
        # Create the dialog
        with ui.dialog() as self._usbWiFiDialog1, ui.card():
            ui.label("A USB cable must be connected between this PC and the MCU device to setup it's WiFi.\n\nContinue ?").style('white-space: pre-wrap;')
            with ui.row():
                ui.button("Ok", on_click=lambda: (self._usbWiFiDialog1.close(), self._usbWiFiDialog2.open(),))
                ui.button("Cancel", on_click=lambda: (self._usbWiFiDialog1.close(), self._sendEnableAllButtons(True)))

    def _initUsbWiFiDialog2(self):
        """@brief A dialog displayed as step 2 in the WiFi setup process when using a USB interface to talk to the MCU device."""
        with ui.dialog() as self._usbWiFiDialog2, ui.card():
            with ui.column():

                self._wifiSSIDUSBInput = ui.input(label='WiFi SSID')
                ssid = self._cfgMgr.getAttr(GUIServerEXT1.WIFI_SSID)
                if ssid:
                    self._wifiSSIDUSBInput.value = ssid

                self._wifiPasswordUSBInput = ui.input(label='WiFi Password', password=True, password_toggle_button=True)
                passwd = self._cfgMgr.getAttr(GUIServerEXT1.WIFI_PASSWORD)
                if passwd:
                    self._wifiPasswordUSBInput.value = passwd

            with ui.row():
                ui.button("Ok", on_click=lambda: (self._usbWiFiDialog2.close(), self._startUsbWifiSetupThread(),))
                ui.button("Cancel", on_click=lambda: (self._usbWiFiDialog2.close(), self._sendEnableAllButtons(True)))

    def _initBluetoothWiFiDialog1(self):
        """@brief A dialog displayed as step 1 in the WiFi setup process when using a bluetooth interface to talk to the MCU device."""
        # Create the dialog
        with ui.dialog() as self._bluetoothWiFiDialog1, ui.card():
            ui.label("Hold the WiFi button down on the MCU device until it restarts and the LED/s flash.\n\nContinue ?").style('white-space: pre-wrap;')
            with ui.row():
                ui.button("Ok", on_click=lambda: (self._bluetoothWiFiDialog1.close(), self._startBluetoothWifiSetup(),))
                ui.button("Cancel", on_click=lambda: (self._bluetoothWiFiDialog1.close(), self._sendEnableAllButtons(True)))

    def _initBluetoothWiFiDialog2(self):
        """@brief A dialog displayed as step 2 in the WiFi setup process when using a bluetooth interface to talk to the MCU device."""
        with ui.dialog() as self._btWiFiDialog2, ui.card():
            with ui.column():
                self._ssidDropDown = ui.select([], label="WiFi SSID's Found.", on_change=lambda e: self._ssidDropDownSelected(e.value)).style('width: 200px;')

                self._wifiSSIDBTInput = ui.input(label='WiFi SSID').style('width: 200px;')
                ssid = self._cfgMgr.getAttr(GUIServerEXT1.WIFI_SSID)
                if ssid:
                    self._wifiSSIDBTInput.value = ssid

                self._wifiPasswordBTInput = ui.input(label='WiFi Password', password=True, password_toggle_button=True).style('width: 200px;')
                passwd = self._cfgMgr.getAttr(GUIServerEXT1.WIFI_PASSWORD)
                if passwd:
                    self._wifiPasswordBTInput.value = passwd

            with ui.row():
                ui.button("Ok", on_click=lambda: (self._btWiFiDialog2.close(), self._startBTWifiSetupThread(),))
                ui.button("Cancel", on_click=lambda: (self._btWiFiDialog2.close(), self._sendEnableAllButtons(True)))

    def _startWifiSetup(self):
        """@brief Called to start the process of setting up the WiFi network."""
        if self._wifi_setup_radio.value == GUIServerEXT1.USB:
            self._usbWiFiDialog1.open()

        elif self._wifi_setup_radio.value == GUIServerEXT1.BLUETOOTH:
            self._bluetoothWiFiDialog1.open()

    def _usbSetWiFiNetwork(self, wifiSSID, wifiPassword):
        """@brief Set the Wifi network on a YDev device over a USB connection to the YDev unit.
           @param wifiSSID The WiFi SSID to set.
           @param wifiPassword The WiFi password to set."""
        try:
            try:
                if len(wifiSSID) == 0:
                    self.error("A WiFi SSID is required.")

                elif len(wifiPassword) == 0:
                    self.error("A WiFi password is required.")

                else:
                    self._setupWiFi(wifiSSID, wifiPassword)

            except Exception as ex:
                self.error(str(ex))

        finally:
            self._sendEnableAllButtons(True)

    def _startUsbWifiSetupThread(self):
        """@brief Called to start the worker thread to setup the MCU WiFi over a USB connection.
           @param event The button event."""
        self._initTask()
        self._copyWifiParams(self._wifiSSIDUSBInput.value, self._wifiPasswordUSBInput.value)
        self._saveConfig()
        self._setExpectedProgressMsgCount(22,86)
        threading.Thread( target=self._usbSetWiFiNetwork, args=(self._wifiSSIDUSBInput.value, self._wifiPasswordUSBInput.value)).start()

    def _startBluetoothWifiSetup(self):
        """@brief Start attempting to setup the YDev WiFi settings using a bluetooth connection to the YDev device."""
        self._initTask()
        self._saveConfig()
        self._setExpectedProgressMsgCount(5, 10)
        threading.Thread(target=self._startBluetoothWifiSetupThread).start()

    def _startBluetoothWifiSetupThread(self):
        """@brief A worker thread that sets up the WiFi interface over a bluetooth connection to the YDev device."""
        try:
            if YDevBlueTooth.IsBluetoothEnabled():
                self.info("Scanning for YDev devices via bluetooth...")
                ct6DevList = YDevBlueTooth.ScanYDev()
                if ct6DevList:
                    if len(ct6DevList) == 1:
                        bluetoothDev = ct6DevList[0]
                        self.info(f"Detected YDev unit (address = {bluetoothDev.address}).")
                        self.info("YDev unit is now performing a WiFi network scan...")
                        yDevBlueTooth = YDevBlueTooth(uio=self)
                        networkDicts = yDevBlueTooth.wifi_scan(bluetoothDev.address)
                        # This should open a dialog to allow the user to setup the WiFi
                        msgDict = {GUIServerEXT1.BT_MAC_ADDRESS: bluetoothDev.address,
                                GUIServerEXT1.YDEV_WIFI_SCAN_COMPLETE: networkDicts}
                        self.updateGUI(msgDict)

                    else:
                        self.errorDialog("More than one YDev device found. Turn off other devices to leave one powered on and try again.")

                else:
                    self.errorDialog("Failed to detect a YDev device via bluetooth.")

            else:
                self.errorDialog("Bluetooth is not available on this computer. Please enable bluetooth and try again.")

        except Exception as ex:
            self.error(str(ex))

        finally:
            self._sendEnableAllButtons(True)

    def _setExpectedProgressMsgCount(self, nonDebugModeCount, debugModeCount):
        """@brief Set the number of log messages expected to complete a tasks progress.
           @param nonDebugModeCount The number of expected messages in non debug mode.
           @param nonDebugModeCount The number of expected messages in debug mode."""
        if self._uio.isDebugEnabled():
            self._startProgress(expectedMsgCount=debugModeCount)
        else:
            self._startProgress(expectedMsgCount=nonDebugModeCount)

    def _copyWifiParams(self, ssid, password):
        """@brief Copy same ssid and password to all UI elements used to enter these parameters.
           @param ssid The WiFi network/SSID.
           @param password The WiFi password."""
        if self._wifiSSIDUSBInput:
            self._wifiSSIDUSBInput.value = ssid

        if self._wifiPasswordUSBInput:
            self._wifiPasswordUSBInput.value = password

        if self._wifiSSIDBTInput:
            self._wifiSSIDBTInput.value = ssid

        if self._wifiPasswordBTInput:
            self._wifiPasswordBTInput.value = password

    def _ssidDropDownSelected(self, value):
        """@bried Update the selected WiFi SSID."""
        self._wifiSSIDBTInput.value = value

    def _wifiPasswordBTInputTogglePassword(self):
        self._wifiPasswordBTInput.password = not self._wifiPasswordBTInput.password
        self._wifiPasswordBTInput.update()

    def _startBTWifiSetupThread(self):
        """@brief Called to start the worker thread to setup the YDev WiFi over a Bluetooth connection.
           @param event The button event."""
        self._copyWifiParams(self._wifiSSIDBTInput.value, self._wifiPasswordBTInput.value)
        self._saveConfig()
        self._setExpectedProgressMsgCount(9,20)
        threading.Thread( target=self._btSetWiFiNetworkThread, args=(self._wifiSSIDBTInput.value, self._wifiPasswordBTInput.value)).start()

    def _btSetWiFiNetworkThread(self, ssid, password):
        """@brief A worker thread responsible for configuring the YDev Wifi SSID and password over bluetooth.
           @param ssid The WiFi SSID.
           @param password The WiFi password."""
        waitingForIP = False
        try:
            ct6Address = self._btMacAddress
            yDevBlueTooth = YDevBlueTooth(uio=self)
            self.info("Setting up YDev WiFi...")
            yDevBlueTooth.setup_wifi(ct6Address, ssid, password)
            self.info("Waiting for YDev device to restart...")
            waitingForIP = True
            yDevBlueTooth.waitfor_device(ct6Address)
            self.info("Waiting for YDev device WiFi to be served an IP address by the DHCP server...")
            ipAddress = yDevBlueTooth.get_ip(ct6Address)
            waitingForIP = False
            self.info(f"YDev device IP address = {ipAddress}")
            # Send a message to set the YDev device IP address in the GUI
            self._setYDevIPAddress(ipAddress)
            self.info("Turning off bluetooth interface on YDev device.")
            yDevBlueTooth.disable_bluetooth(ct6Address)
            self.infoDialog("Device WiFi setup complete.")

        except Exception as ex:
            # Report a more useful user msg
            if waitingForIP:
                self.error(f"YDev device failed to connect to WiFi network ({ssid}). Check the ssid and password.")
            else:
                error = str(ex)
                if error:
                    self.error(error)

        finally:
            self._sendEnableAllButtons(True)

    def _copyYDevAddress(self, ipAddress):
        """@brief Copy same address to YDEV address on all tabs.
           @param ipAddress The IP address to copy to all tabs."""
        if self._deviceIPAddressInput1:
            self._deviceIPAddressInput1.value = ipAddress

        if self._deviceIPAddressInput2:
            self._deviceIPAddressInput2.value = ipAddress

    def _handleGUIUpdate(self, rxDict):
        """@brief Process the dicts received from the GUI message queue that were not
                  handled by the parent class instance.
           @param rxDict The dict received from the GUI message queue."""
        if GUIServerEXT1.YDEV_WIFI_SCAN_COMPLETE in rxDict and \
           GUIServerEXT1.BT_MAC_ADDRESS in rxDict:
            btMacAddress = rxDict[GUIServerEXT1.BT_MAC_ADDRESS]
            scanResultsDicts = rxDict[GUIServerEXT1.YDEV_WIFI_SCAN_COMPLETE]
            self._continueYDevWifiBTSetup(btMacAddress, scanResultsDicts)

        if GUIServerEXT1.SET_YDEV_IP_ADDRESS in rxDict:
            address = rxDict[GUIServerEXT1.SET_YDEV_IP_ADDRESS]
            # Set the IP address field to the CT6 address
            self._copyYDevAddress(address)
            self._saveConfig()

        if GUIServer.SERIAL_PORT_OPEN in rxDict:
            open = rxDict[GUIServerEXT1.SERIAL_PORT_OPEN]
            self._update_serial_port_open_buttons(open)

    def _continueYDevWifiBTSetup(self, btMacAddress, wifiNetworkDicts):
        self._btMacAddress = btMacAddress
        # Build a list of the ssid's found.
        ssidList = []
        self.info("WiFi Network                             RSSI (dBm)")
        for wifiNetworkDict in wifiNetworkDicts:
            if GUIServerEXT1.SSID in wifiNetworkDict:
                ssid = wifiNetworkDict[GUIServerEXT1.SSID]
                if ssid and ssid not in ssidList:
                    ssidList.append(ssid)

                if ssid and GUIServerEXT1.RSSI in wifiNetworkDict:
                    rssi = wifiNetworkDict[GUIServerEXT1.RSSI]
                    if rssi < -10:
                        self.info(f"{ssid:<40s} {rssi:.0f}")

        # Set list in GUI field and update
        self._ssidDropDown.options = ssidList
        if self._wifiSSIDBTInput.value in ssidList:
            self._ssidDropDown.value = self._wifiSSIDBTInput.value

        self._ssidDropDown.update()
        # Open the dialog to allow the user to enter the wifi ssid and password.
        self._btWiFiDialog2.open()

    def _setYDevIPAddress(self, address):
        """@brief Set the YDEV IP address.
                  This can be called from outside the GUI thread.
           @param msg The message to be displayed."""
        if address:
            msgDict = {GUIServerEXT1.SET_YDEV_IP_ADDRESS: address}
        else:
            msgDict = {GUIServerEXT1.ERROR_MESSAGE: "YDEV device failed to connect to WiFi network."}
        self.updateGUI(msgDict)

    def _setupWiFi(self, wifiSSID, wifiPassword):
        """@brief Setup the YDev WiFi interface. This must be called outside the GUI thread.
           @param wifiSSID The WiFi SSID to set.
           @param wifiPassword The WiFi password to set."""
        try:
            self._checkSerialPortAvailable(self._serialPortSelect2.value)
            self._setWiFiNetwork(wifiSSID, wifiPassword)

        except Exception as ex:
            self.reportException(ex)


def main():
    """@brief Program entry point"""
    uio = UIO()

    try:
        options, launcher = GUIServerEXT1.GetCmdOpts()
        uio.enableDebug(options.debug)
        handled = launcher.handleLauncherArgs(options, uio=uio)
        if not handled:
            guiServer = GUIServerEXT1(uio, options)
            guiServer.start()

    #If the program throws a system exit exception
    except SystemExit:
        pass
    #Don't print error information if CTRL C pressed
    except KeyboardInterrupt:
        pass
    except Exception as ex:
        logTraceBack(uio)

        if options.debug:
            raise
        else:
            uio.error(str(ex))

if __name__== '__main__':
    main()


# TODO
# Just load App and progress bar does not work, FIX
# Add ability for MCU path not to end in mcu
# Add ability to upgrade SW
# Add log files for UIO output
# Add web sever , move REST server to a different port
# Add Scan and reboot/Powercycle
# Add all GUI features to CMD line tool
