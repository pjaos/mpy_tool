#!/usr/bin/env python3

import os
import argparse
import threading
import serial
import requests
import datetime
import shutil

from random import random
from subprocess import check_output
from pathlib import Path

from time import time, sleep
from queue import Queue, Empty
from p3lib.launcher import Launcher

from mpy_tool._lib.mcu_loader import LoaderBase, USBLoader, UpgradeManager, YDevScanner, MCUBase
from mpy_tool._lib.bluetooth import YDevBlueTooth

from p3lib.uio import UIO
from p3lib.helper import logTraceBack
from p3lib.pconfig import ConfigManager
from p3lib.helper import get_assets_dir, EnvArgs

from p3lib.ngt3 import TabbedNiceGui, YesNoDialog, FileAndFolderChooser, FileSaveChooser
from nicegui import ui, app
import plotly.graph_objects as go


class GUIServer(TabbedNiceGui):
    """@responsible for presenting a management GUI."""

    # We hard code the log path to ensure the user does not have the option to move them.
    LOG_PATH = "mcu_tool_logs"
    DEFAULT_SERVER_ADDRESS = "0.0.0.0"
    DEFAULT_SERVER_PORT = 11938
    PAGE_TITLE = "MPY Tool"
    CFG_FILENAME = ".mcu_tool_gui.cfg"
    WIFI_SSID = "WIFI_SSID"
    WIFI_PASSWORD = "WIFI_PASSWORD"
    DEVICE_ADDRESS = "DEVICE_ADDRESS"
    MCU_MAIN_PY = "MCU_MAIN_PY"
    MCU_TYPE = "MCU_TYPE"
    ERASE_MCU_FLASH = "ERASE_MCU_FLASH"
    LOAD_MICROPYTHON = "LOAD_MICROPYTHON"
    LOAD_APP = "LOAD_APP"
    MEM_MON_RUN_GC = "MEM_MON_RUN_GC"
    MEM_MON_POLL_SEC = "MEM_MON_POLL_SEC"
    SCAN_PORT_STR = "SCAN_PORT_STR"
    SCAN_SECONDS = "SCAN_SECONDS"
    SCAN_IP_ADDRESS = "SCAN_IP_ADDRESS"
    USB_WIFI_SETUP_IF = "USB_WIFI_SETUP_IF"
    SETUP_WIFI_IF = "SETUP_WIFI_IF"
    USB = "USB"
    BLUETOOTH = "Bluetooth"
    BT_MAC_ADDRESS = "BT_MAC_ADDRESS"
    SSID = "SSID"
    RSSI = "RSSI"
    YDEV_WIFI_SCAN_COMPLETE = "YDEV_WIFI_SCAN_COMPLETE"
    SET_YDEV_IP_ADDRESS = "SET_YDEV_IP_ADDRESS"
    DEFAULT_CODE_PATH = "DEFAULT_CODE_PATH"
    FILENAME1 = "FILENAME1"
    COPY_TO_EDITOR = "COPY_TO_EDITOR"
    RUN_MAIN_SW_STATE = "RUN_MAIN_SW_STATE"
    NEW_PROJECT_PATH = "NEW_PROJECT_PATH"

    DEFAULT_CONFIG = {WIFI_SSID: "",
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
                      SCAN_IP_ADDRESS: "",
                      USB_WIFI_SETUP_IF: USB,
                      SETUP_WIFI_IF: USB,
                      DEFAULT_CODE_PATH: os.path.expanduser("~"),
                      FILENAME1: "main.py",
                      COPY_TO_EDITOR: True,
                      RUN_MAIN_SW_STATE: True,
                      NEW_PROJECT_PATH: ""}

    DESCRIP_STYLE_1 = '<span style="font-size:1.5em;">'
    SERIAL_PORT_OPEN = 'SERIAL_PORT_OPEN'
    RAW_MESSAGE = "RAW"
    COMPLETE = "COMPLETE"
    SET_EDITOR_LINES = "SET_EDITOR_LINES"
    EXAMPLE_LIST = ['1',
                    '2',
                    '3',
                    '4',
                    '5',
                    '6',
                    '7']

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
        self._uio = uio
        self._options = options
        self._cfgMgr = ConfigManager(self._uio, GUIServer.CFG_FILENAME, GUIServer.DEFAULT_CONFIG)
        self._serialPortSelect1 = None
        self._serialPortSelect2 = None
        self._upgradeAppPathInput = None
        self._serialPortSelect1 = None
        self._serialPortSelect2 = None
        self._serialPortSelect3 = None
        self._app_main_py_input = None
        self._select_main_py_button = None
        self._installSWButton = None
        self._loadMicroPythonInput = None
        self._eraseMCUFlashInput = None
        self._serialTXQueue = Queue()
        self._serialRXQueue = None
        self._ser = None
        self._wifi_ssid = ""
        self._wifi_password = ""
        self._mu = None
        self._serialRXQueueLock = threading.Lock()
        self._filePath = os.path.expanduser("~")
        self._loadConfig()

    def start(self):
        """@brief Start the App server running."""
        self._uio.info("Starting GUI...")
        TabbedNiceGui.CheckPort(self._options.port)

        tabNameList = ('Install',
                       'WiFi',
                       'OTA (Over The Air)',
                       'Serial Port',
                       'Scan',
                       'Memory Monitor',
                       'Template Projects')

        # This must have the same number of elements as the above list
        tabMethodInitList = [self._initInstallTab,
                             self._initWiFiTab,
                             self._initUpgradeTab,
                             self._initSerialTab,
                             self._initScanTab,
                             self._initMemMonTab,
                             self._initTemplateProject]

        self.set_init_gui_args(tabNameList,
                                tabMethodInitList,
                                address=self._options.address,
                                port=self._options.port,
                                pageTitle=GUIServer.PAGE_TITLE,
                                reload=False)

        ui.sub_pages({
            '/': self.init_gui,  # Root page, followed by sub pages
            '/memory_usage': self._init_mem_usage_gui,
            '/project_examples': self.project_examples,
            '/project_template_1_README.md': self.example_1_page,
            '/project_template_2_README.md': self.example_2_page,
            '/project_template_3_README.md': self.example_3_page,
            '/project_template_4_README.md': self.example_4_page,
            '/project_template_5_README.md': self.example_5_page,
            '/project_template_6_README.md': self.example_6_page,
            '/project_template_7_README.md': self.example_7_page,
            '/WIFI_SETUP_GPIOS.md': self.wifi_setup_gpios_page,
            })

    def _initInstallTab(self):
        """@brief Create the install micropython tab contents."""
        markDownText = GUIServer.DESCRIP_STYLE_1+"""Install software on an MCU via a USB connection."""
        ui.markdown(markDownText)

        self._installPicoDialog = YesNoDialog("Power down the  RPi Pico W, hold it's button down and then power it back up. Then select the OK button below.",
                                              self._startInstallThread,
                                              successButtonText="OK",
                                              failureButtonText="Cancel")
        self._installEsp32Dialog = YesNoDialog("Hold the non ESP32 reset button down and then press and release the reset button. Then select the OK button below.",
                                               self._startInstallThread,
                                               successButtonText="OK",
                                               failureButtonText="Cancel")
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
            self._select_main_py_button = ui.button('select mcu main.py', on_click=self._select_main_py).tooltip("Select the main.py file to be loaded to the MCU.")
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
                if portInfo.device not in devNameList:
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
        file_and_folder_chooser = FileAndFolderChooser(selected_path)
        result = await file_and_folder_chooser.open()
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
            if self._setSerialPortClosed():
                ui.notify('The serial port was open in the SERIAL PORT tab. It has been closed in order to proceed with the install process.', type='warning')

        self._clearMessages()
        mcuType = self._mcuTypeSelect.value
        if mcuType:
            # If loading a MicroPython app and not loading MicroPython a serial port is required.
            if self._loadAppInput.value and not self._loadMicroPythonInput.value and not self._serialPortSelect1.value:
                ui.notify('No serial port is selected.', type='negative')
                return

            # For ESP32's you must erase the flash before loading it
            if mcuType in LoaderBase.VALID_ESP32_TYPES and self._loadMicroPythonInput.value:
                self._eraseMCUFlashInput.value = True

            # If you erase the flash and want to load a MicroPython app you must load MicroPython
            if self._eraseMCUFlashInput.value and not self._loadMicroPythonInput.value and self._loadAppInput.value:
                self._loadMicroPythonInput.value = True

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
        startMessage = "MCU: "
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

            t = threading.Thread(target=self._installSW)
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
                self._ser = serial.serial_for_url(serialPortDev, do_not_open=False, exclusive=True)
                self._ser.close()

            except serial.serialutil.SerialException:
                raise Exception(f"{serialPortDev} serial port is not available as it's in use.")
            self._ser = None

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

                fsStats = usbLoader.install(self._eraseMCUFlashInput.value,
                                            self._loadMicroPythonInput.value,
                                            self._loadAppInput.value,
                                            mcu_app_path,
                                            self._loadMpyInput.value,
                                            showInitialPrompt=False)

                if fsStats:
                    flashSize = fsStats[0]
                    freeSpace = fsStats[1]
                    usedSpace = flashSize-freeSpace
                    percentageUsed = 0
                    if usedSpace > 0:
                        percentageUsed = int((usedSpace/flashSize)*100.0)
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
        except Exception:
            pass
        self._wifi_ssid = self._cfgMgr.getAttr(GUIServerEXT1.WIFI_SSID)
        self._wifi_password = self._cfgMgr.getAttr(GUIServerEXT1.WIFI_PASSWORD)

    def _initWiFiTab(self):
        """@brief Create the Wifi tab contents."""
        pass

    def _setWiFiNetwork(self, wifiSSID, wifiPassword):
        """@brief Set the Wifi network on a YDev device over a USB interface.
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
        """@brief Create a tab used for over the air actions. Initially this ws just upgrading over the air, hence the name."""
        markDownText = f"{GUIServer.DESCRIP_STYLE_1}Update an MCU over your WiFi network."
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

        with ui.row():
            self._upgradeButton = ui.button('Upgrade App', on_click=self._upgradeButtonHandler)
            # Add to button list so that button is disabled while activity is in progress.
            self._appendButtonList(self._upgradeButton)
            self._upgradeAppPathInput.on('change', self._upgradeAppPathInputUpdated)

            self._resetWifiButton = ui.button('Reset WiFi configuration', on_click=self._resetWifiButtonHandler).tooltip('Reset the WiFi configuration and reboot the MCU.')
            self._appendButtonList(self._resetWifiButton)

    def _resetWifiButtonHandler(self):
        """@brief handle a user selecting the button to reset the WiFi config."""
        self._initTask()
        self._saveConfig()
        duration = 120
        self._startProgress(durationSeconds=duration)
        t = threading.Thread(target=self._resetWiFiConfigThread)
        t.daemon = True
        t.start()

    def _resetWiFiConfigThread(self):
        """@brief The thread responsible to resetting the MCU WiFi config."""
        try:
            try:
                address = self._deviceIPAddressInput1.value
                if len(address) == 0:
                    self.error("A device address is required.")

                else:
                    self.info(f"Reset the WiFi config for the MCU at {address}.")

                    upgradeManager = UpgradeManager(self._mcuTypeSelect.value, uio=self)
                    upgradeManager.resetWifiConfig(address)
                    self.infoDialog("WiFi config has been reset and the MCU is rebooting.")

            except Exception as ex:
                self.reportException(ex)

        finally:
            self._sendEnableAllButtons(True)

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
        t = threading.Thread(target=self._appUpgrade)
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

    def _serialCheckRepl(self, reportError = True):
        """@brief Check for the python REPL (>>> ) prompt on the open serial port.
           @param reportError If True and the REPL prompt is not found the error is reported in he message log.
           @return True if the REPL prompt is found."""
        found = False
        try:
            self._serialRXQueueLock.acquire()
            self._serialRXQueue = Queue()
            self._serialRXQueueLock.release()
            self._serialTXQueue.put('\r')
            timeout = time() + 0.25
            while True:
                if not self._serialRXQueue.empty():
                    data = self._serialRXQueue.get(block=False)
                    if data.find(">>> ") != -1:
                        found = True
                        break
                if time() >= timeout:
                    break
                sleep(0.05)

            if not found and reportError:
                self.error("Python REPL prompt (>>> ) not found on serial port.")
        finally:
            self._flush_queue(self._serialTXQueue)
            self._flush_queue(self._serialRXQueue)
            self._serialRXQueueLock.acquire()
            self._serialRXQueue = None
            self._serialRXQueueLock.release()

        return found

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

    def _initSerialSendDialog(self):
        """@brief A dialog displayed when the user wants to send a file to an MCU over a USB serial port."""
        # Create the dialog
        with ui.dialog() as self._serialSendDialog, ui.card():
            ui.label("Enter the name for the file to create on the MCU flash.")
            with ui.row():
                ser_send_file = self._cfgMgr.getAttr(GUIServer.FILENAME1)
                self._serialSendFileInput = ui.input('Filename', value=ser_send_file)
            with ui.row():
                ui.button("Ok", on_click=lambda: self._serialSendFile())
                ui.button("Cancel", on_click=lambda: (self._serialSendDialog.close()))

    def _initSerialGetFileDialog(self):
        """@brief A dialog displayed when the user wants to get a file from the MCU over a USB serial port."""
        # Create the dialog
        with ui.dialog() as self._serialDownloadFileDialog, ui.card():
            ui.label("Enter the name for the file to download from the MCU flash.")
            with ui.row():
                ser_get_file = self._cfgMgr.getAttr(GUIServer.FILENAME1)
                self._serialDownloadFileInput = ui.input('Filename', value=ser_get_file)
                cp_to_editor = self._cfgMgr.getAttr(GUIServer.COPY_TO_EDITOR)
                self._serialDownloadCoptToEditorSwitch = ui.switch("Copy to editor", value=cp_to_editor, on_change=self._copyToEditorSwitchChanged).style('width: 200px;')
            with ui.row():
                ui.button("Ok", on_click=lambda: self._getMCUFile())
                ui.button("Cancel", on_click=lambda: (self._serialDownloadFileDialog.close()))

    def _copyToEditorSwitchChanged(self):
        self._cfgMgr.addAttr(GUIServer.COPY_TO_EDITOR, self._serialDownloadCoptToEditorSwitch.value)
        self._saveConfig()

    def _initRunFileDialog(self):
        """@brief A dialog displayed when the user wants to run a python file that is sitting in the MCU flash over a serial port connection."""
        # Create the dialog
        with ui.dialog() as self._serialRunFileDialog, ui.card():
            ui.label("Enter the name for the file on the MCU flash to execute.")
            with ui.row():
                ser_get_file = self._cfgMgr.getAttr(GUIServer.FILENAME1)
                self._serialRunFileInput = ui.input('Filename', value=ser_get_file).tooltip("This python file must have a main() method.")
                run_man_sw_state = self._cfgMgr.getAttr(GUIServer.RUN_MAIN_SW_STATE)
                self._serialRunMainSwitch = ui.switch("Run main.py", value=run_man_sw_state, on_change=self._serialRunMainSwitchChanged).style('width: 200px;').tooltip("If selected 'CTRL D' is sent on the serial port which causes main.py to be executed.")
            with ui.row():
                ui.button("Ok", on_click=lambda: self._runMCUFile())
                ui.button("Cancel", on_click=lambda: (self._serialRunFileDialog.close()))

    def _serialRunMainSwitchChanged(self):
        if self._serialRunMainSwitch.value:
            self._serialRunFileInput.value = 'main.py'
            self._serialRunFileInput.disable()
        else:
            self._serialRunFileInput.enable()

    def _runMCUFile(self):
        # Save the state of the 'Run main.py' switch.
        self._cfgMgr.addAttr(GUIServer.RUN_MAIN_SW_STATE, self._serialRunMainSwitch.value)
        self._saveConfig()
        self._serialRunFileDialog.close()
        self._updateFilename1(self._serialRunFileInput.value)
        if self._serialCheckRepl():
            if self._serialRunMainSwitch.value:
                self._sendCtrlD()
            else:
                self._runMCUFileMain()

    def _runMCUFileMain(self):
        code_lines = []
        module_name = self._serialRunFileInput.value.replace(".py", "")
        code_lines.append(f'import {module_name}')
        code_lines.append(f'{module_name}.main()')
        code_lines.append(f'print("{GUIServer.COMPLETE}")')
        code_lines.append('')
        self._runPythonCodeFromREPL(code_lines)

    def _runPythonCodeFromREPL(self, code_lines, log_prefix=None):
        """@brief Run python code from the REPL prompt.
           @return A list of lines of text received."""
        rx_lines = []
        self._sendEnableAllButtons(False)
        try:

            self._serialRXQueueLock.acquire()
            self._serialRXQueue = Queue()
            self._serialRXQueueLock.release()

            # Send python code on serial port to
            for line in code_lines:
                self._serialTXQueue.put(line + '\r')

            timeout = time() + 3
            running = True
            while running:
                if not self._serialRXQueue.empty():
                    rxStr = self._serialRXQueue.get()
                    lines = rxStr.split('\n')
                    for line in lines:
                        line = line.rstrip('\r\n')
                        if line.startswith(GUIServer.COMPLETE) or line.find(f'print("{GUIServer.COMPLETE}")') >= 0:
                            running = False
                            break

                        if log_prefix and line.startswith(log_prefix):
                            prefix_len = len(log_prefix)
                            line = line[prefix_len:]
                            self.msg(line)
                            rx_lines.append(line)

                        if not log_prefix:
                            self.msg(line)
                            rx_lines.append(line)

                if time() > timeout:
                    self.error("Timeout waiting for response on serial port.")
                    self._flush_queue(self._serialTXQueue)
                    self._flush_queue(self._serialRXQueue)
                    break

        finally:
            self._serialRXQueueLock.acquire()
            self._serialRXQueue = None
            self._serialRXQueueLock.release()

            self._sendEnableAllButtons(True)

        return rx_lines

    def _initSerialTab(self):
        """@brief Show the serial port output."""
        self._initSerialSendDialog()
        self._initSerialGetFileDialog()
        self._initRunFileDialog()

        with ui.row():
            self._serialPortSelect3 = ui.select(options=[], label='MCU serial port', on_change=self._serialPortSelect3Changed).style('width: 200px;')
            self._serialPortSelect3.tooltip("The serial port to which the MCU is connected.")
            updateSerialPortButton = ui.button('update serial port list', on_click=self._updateSerialPortList)
            updateSerialPortButton.tooltip("Update the list of available serial ports.")

            self._openSerialPortButton = ui.button('Open', on_click=self._openSerialPortHandler)
            self._closeSerialPortButton = ui.button('Close', on_click=self._closeSerialPortHandler)
            self._hwResetESP32 = ui.switch("HW Reset ESP32", value=False).tooltip('Perform a reset using DTR/RTS if an ESP32 MCU is connected when the serial port is opened.')

        with ui.card().classes('w-full'):
            self._code_editor = ui.textarea(placeholder='MicroPython code', )
            self._code_editor.props('rows=15')
            self._code_editor.classes('w-full').style('font-family: monospace;')

        with ui.row():
            self._sendCtrlCButton = ui.button(icon='stop', on_click=self._sendCtrlC).tooltip("Send CTRL C to stop any program and get REPL (>>>) prompt. This should be selected before selecting other buttons.")
            self._sendCtrlBButton = ui.button(icon='info', on_click=self._sendCtrlB).tooltip("Send CTRL B to get MicroPython version from REPL prompt.")
            self._sendTextButton = ui.button(icon='play_arrow', on_click=self._sendText).tooltip("Run the python code above on the MCU.")
            self._sendCtrlDButton = ui.button(icon='run_circle', on_click=self._openSerialRunFileDialog).tooltip("Send CTRL D to start running the main.py file (if it exists) from REPL prompt.")

            self._listMCUFoldersButton = ui.button(icon='folder', on_click=self._listMCUFolders).tooltip("List files on MCU flash memory.")
            self._uploadButton = ui.button(icon='upload', on_click=self._serialSendDialog.open).tooltip("Upload a file to the MCU with the above contents.")
            self._downloadButton = ui.button(icon='download', on_click=self._serialDownloadFileDialog.open).tooltip("Download a file from the MCU.")
            self._saveCodeButton = ui.button(icon='arrow_circle_down', on_click=self._serialSaveLocalFile).tooltip("Save to a local file.")
            self._loadCodeButton = ui.button(icon='arrow_circle_up', on_click=self._serialLoadLocalFile).tooltip("Load from a local file.")

        self._setSerialPortClosed()

        # Populate the list of available serial ports if possible.
        self._updateSerialPortList()

    def _openSerialRunFileDialog(self):
        self._serialRunFileDialog.open()

    def _updateFilename1(self, filename):
        self._serialSendFileInput.value = filename
        self._serialDownloadFileInput.value = filename
        self._serialRunFileInput.value = filename
        self._cfgMgr.addAttr(GUIServer.FILENAME1, filename)
        self._saveConfig()

    def _serialSendFile(self):
        """@brief Send to a file on the MCU."""
        self._serialSendDialog.close()
        if self._serialSendFileInput.value:
            self._updateFilename1(self._serialSendFileInput.value)
            threading.Thread(target=self._serial_send_thread, args=(self._serialPortSelect3.value, self._code_editor.value, self._serialSendFileInput.value)).start()
        else:
            ui.notify('No filename entered.', type='warning')

    def _serial_send_thread(self, device, data_str, remote_file):
        tmp_file = None
        try:
            # We need to close the serial port so that we can use mpremote to send the file
            self._closeSerialPortHandler()
            sleep(.25)

            tmp_file = os.path.join(MCUBase.GetTempFolder(), f"editor_file_{str(int(random()*1E9))}.py")
            with open(tmp_file, 'w') as fd:
                fd.write(data_str)
            self.info(f"Created {tmp_file}")

            cmd_list = ['mpy_tool_mpremote', 'connect', f'{device}', 'cp', tmp_file, f':{remote_file}']
            cmd = ' '.join(cmd_list)
            self.debug(f"Executing cmd: {cmd}")
            result = check_output(cmd, shell=True).decode("utf-8", errors="ignore")
            self.debug(f"cmd result: {result}")

            self.info(f"Copied {tmp_file} to {remote_file}")

        finally:
            sleep(0.25)
            # Originally we cleaned up the temp file but it can be useful to leave it.
            # Open the serial port again
            self._openSerialPortHandler()

    def _listMCUFolders(self):
        if self._serialCheckRepl():
            threading.Thread(target=self._listMCUFoldersThread).start()

    def _listMCUFoldersThread(self):
        code_lines = []
        code_lines.append('import uos')
        code_lines.append('')
        code_lines.append('def is_dir(path):')
        code_lines.append('    try:')
        code_lines.append('        return uos.stat(path)[0] & 0o170000 == 0o040000')
        code_lines.append('    except:')
        code_lines.append('        return False')
        code_lines.append('')
        code_lines.append('def list_dirs_recursive(path):')
        code_lines.append('    dirs = []')
        code_lines.append('    try:')
        code_lines.append('        for entry in uos.listdir(path):')
        code_lines.append('            full_path = path.rstrip("/") + "/" + entry')
        code_lines.append('            dirs.append(full_path)')
        code_lines.append('            if is_dir(full_path):')
        code_lines.append('                dirs.extend(list_dirs_recursive(full_path))')
        code_lines.append('    except:')
        code_lines.append('        pass')
        code_lines.append('    return dirs')
        code_lines.append('')
        code_lines.append('entries = list_dirs_recursive("/")')
        code_lines.append('for e in entries:')
        code_lines.append('    print(f"MCU File:{e}")')
        code_lines.append('')
        code_lines.append(f'print("{GUIServer.COMPLETE}")')
        code_lines.append('')
        self._runPythonCodeFromREPL(code_lines, log_prefix="MCU File:")

    def _getMCUFile(self):
        self._serialDownloadFileDialog.close()
        if self._serialDownloadFileInput.value:
            self._updateFilename1(self._serialDownloadFileInput.value)
            if self._serialCheckRepl():
                threading.Thread(target=self._getMCUFileThread, args = (self._serialDownloadFileInput.value,)).start()

    def _getMCUFileThread(self, filename):
        code_lines = []
        code_lines.append(f"with open('{filename}', 'r') as fd:")
        code_lines.append('    lines = fd.readlines()')
        code_lines.append('')
        code_lines.append('for line in lines:')
        code_lines.append("    print('LINE:' + line)")
        code_lines.append('')
        code_lines.append(f'print("{GUIServer.COMPLETE}")')
        code_lines.append('')
        lines = self._runPythonCodeFromREPL(code_lines, log_prefix="LINE:")
        if lines and self._serialDownloadCoptToEditorSwitch.value:
            self.update_editor(lines)

    def _flush_queue(self, q: Queue):
        """@brief flush the queue"""
        if q:
            while not q.empty():
                try:
                    q.get_nowait()
                except Empty:
                    break

    async def _load_python_file(self):
        """@brief Select the MCU main.py micropython file."""
        selected_path = self._get_currently_selected_path()
        file_and_folder_chooser = FileAndFolderChooser(selected_path)
        result = await file_and_folder_chooser.open()
        if result:
            selected_file = result[0]
            if selected_file.endswith('.py'):
                if os.path.isfile(selected_file):
                    contents = None
                    with open(selected_file, 'r') as fd:
                        contents = fd.readlines()
                    if contents:
                        self._code_editor.value = contents

            else:
                self.error(f"{selected_file} selected. You must select a *.py file.")

    async def _serialSaveLocalFile(self):
        _path = self._cfgMgr.getAttr(GUIServerEXT1.DEFAULT_CODE_PATH)
        ffc = FileSaveChooser(_path)
        text_files = await ffc.open()
        if text_files:
            try:
                with open(str(text_files[0]), 'w') as fd:
                    fd.write(self._code_editor.value)
                self.info(f"Saved {text_files}")

            except OSError as ex:
                ui.notify(str(ex), type='negative')

        if text_files:
            _file = Path(text_files[0])
            if text_files and _file.is_dir():
                self._cfgMgr.addAttr(GUIServerEXT1.DEFAULT_CODE_PATH, str(_file))
            else:
                folder = str(_file.parent)
                self._cfgMgr.addAttr(GUIServerEXT1.DEFAULT_CODE_PATH, folder)

            _path = self._cfgMgr.getAttr(GUIServerEXT1.DEFAULT_CODE_PATH)
            self._saveConfig()

    async def _serialLoadLocalFile(self):
        _path = self._cfgMgr.getAttr(GUIServerEXT1.DEFAULT_CODE_PATH)
        ffc = FileAndFolderChooser(_path)
        text_files = await ffc.open()
        if text_files:
            with open(text_files[0], 'r') as fd:
                contents = fd.read()
                if contents:
                    self._code_editor.value = contents
                    self.info(f"Loaded from {text_files}")

        if text_files:
            _file = Path(text_files[0])
            if text_files and _file.is_dir():
                self._cfgMgr.addAttr(GUIServerEXT1.DEFAULT_CODE_PATH, str(_file))
            else:
                folder = str(_file.parent)
                self._cfgMgr.addAttr(GUIServerEXT1.DEFAULT_CODE_PATH, folder)

            _path = self._cfgMgr.getAttr(GUIServerEXT1.DEFAULT_CODE_PATH)
            self._saveConfig()

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
        self._uploadButton.enabled = open
        self._downloadButton.enabled = open
        self._listMCUFoldersButton.enabled = open

    def _openSerialPortHandler(self):
        # Enable the close serial port button so that the user can close the serial port when they are finished.
        if not self._serialPortSelect1.value:
            ui.notify('No serial port is selected.', type='negative')
        else:
            t = threading.Thread(target=self._viewSerialPortData, args=(self._hwResetESP32.value,))
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

    def _ensure_serial_port_is_closed(self):
        """@brief Ensure the serial port is closed.
           @return True if the serial port was closed."""
        closed = False
        if self._ser:
            try:
                self._ser.close()
                closed = True
            except Exception:
                pass
        return closed

    def _viewSerialPortData(self, resetESP32):
        """@brief Read data from the available serial port and display it.
           @param resetESP32 If True The perform a hardware reset using the RTS/DTR control signals."""
        try:
            self._ensure_serial_port_is_closed()

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
                        if resetESP32:
                            self._ser = usbLoader.esp32HWReset(closeSer=False)
                        else:
                            self._ser = usbLoader.openFirstSerialPort()

                    except serial.serialutil.SerialException as ex:
                        if str(ex).find('Could not exclusively lock port'):
                            self.error("It appears the serial port is in use.")
                        else:
                            self.error(str(ex))
                        return
                    self._sendSerialPortOpen(True)
                    try:
                        try:
                            while self._viewSerialRunning:
                                while self._ser.in_waiting > 0:
                                    bytesRead = self._ser.read(self._ser.in_waiting)
                                    sRead = bytesRead.decode("utf-8", errors="ignore")
                                    if len(sRead) > 0:
                                        self._serialRXQueueLock.acquire()
                                        # If we have an queue to put RX data into, do so
                                        if self._serialRXQueue:
                                            self._serialRXQueue.put(sRead)

                                        #If not then send it to the message log.
                                        else:
                                            sRead = sRead.rstrip('\r\n')
                                            self.msg(sRead)
                                        self._serialRXQueueLock.release()

                                while not self._serialTXQueue.empty():
                                    txStr = self._serialTXQueue.get()
                                    self._ser.write(txStr.encode())

                                # Ensure we don't spinlock
                                sleep(0.1)

                        except Exception as ex:
                            self.error(str(ex))
                            pass

                    finally:
                        if self._ser:
                            self._ser.close()
                            if usbLoader:
                                self.info(f"Closed {usbLoader._serialPort}")
                            usbLoader = None

                # Ensure we don't spinlock
                sleep(0.1)

        finally:
            self._ensure_serial_port_is_closed()
            if usbLoader:
                self.info(f"Closed {usbLoader._serialPort}")
            usbLoader = None
            self._sendSerialPortOpen(False)
            self._sendEnableAllButtons(True)

    def _sendCtrlB(self):
        if self._serialCheckRepl():
            self._serialTXQueue.put('\02')

    def _sendCtrlC(self):
        self._serialTXQueue.put('\03')

    def _sendCtrlD(self):
        if self._serialCheckRepl():
            self._serialTXQueue.put('\04')

    def _sendText(self):
        if self._serialCheckRepl():
            text = self._code_editor.value
            lines = text.split('\n')
            if len(lines) > 0:
                for line in lines:
                    line = line.rstrip('\r\n')
                    self._serialTXQueue.put(line + '\r')
            self._serialTXQueue.put('\r')

    def _closeSerialPortHandler(self):
        """@brief Shut down the running view serial port task."""
        self.info("Shutting down...")
        self._setSerialPortClosed()

    def _setSerialPortClosed(self):
        """@brief Set the serial port to the closed state.
           @return True if the serial port was closed."""
        self._update_serial_port_open_buttons(False)
        self._viewSerialRunning = False
        return self._ensure_serial_port_is_closed()

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

    def _init_mem_usage_gui(self):
        arg_list = MemoryUsageEnvArgs().get()
        ip_address = arg_list[0]
        run_gc = arg_list[1]
        poll_seconds = arg_list[2]
        debug = arg_list[3]
        self._mu = MemoryUsage(self._options,
                               ip_address,
                               run_gc,
                               poll_seconds,
                               debug)
        self._mu.init_gui()
        self._mu.start()

    def _startMemMon(self):
        """@brief Start monitoring MCU device memory usage."""
        # Set min value if not set
        if not self._memMonSecondsInput.value:
            self._memMonSecondsInput.value = 1

        self.info("Started memory monitor.")
        # Pass args to GUIServer instance through the env
        arg_list = []
        arg_list.append(self._deviceIPAddressInput2.value)
        arg_list.append(self._runGCInput.value)
        arg_list.append(self._memMonSecondsInput.value)
        arg_list.append(self._uio.isDebugEnabled())
        MemoryUsageEnvArgs().set(arg_list)
        # This will open the new page in a new browser window
        ui.run_javascript("window.open('/memory_usage', '_blank')")

    def close(self):
        """@brief Close down the app server."""
        ui.notify("Shutting down application...")
        ui.timer(interval=2, callback=self._shutdownApp)

    def _shutdownApp(self):
        """@brief Shutdown the app"""
        app.shutdown()

    def _rawGT(self, msg):
        """@brief Update a a raw message. This must be called from the GUI thread.
           @param msg The message to display."""
        self._handleMsg(msg)

    def msg(self, msg):
        """@brief Send a info message to be displayed in the GUI.
                  This can be called from outside the GUI thread.
           @param msg The message to be displayed."""
        msgDict = {GUIServer.RAW_MESSAGE: str(msg)}
        self.updateGUI(msgDict)

    def update_editor(self, lines):
        """@brief Send lines of text to be loaded into the editor.
           @param lines A list of text lines to be set in the editor."""
        msgDict = {GUIServer.SET_EDITOR_LINES: lines}
        self.updateGUI(msgDict)


    def _initTemplateProject(self):
        markDownText = GUIServer.DESCRIP_STYLE_1+"""Template/Example MCU code that provide a starting point for implementing your chosen projects functionality. """
        ui.markdown(markDownText)

        with ui.row():
            ui.markdown('Source Example Project')
            self._example_select = ui.select(options=GUIServer.EXAMPLE_LIST, value=GUIServer.EXAMPLE_LIST[4]).tooltip('The installed MCU code examples are listed here.')
            self._show_examples_button = ui.button('Example Project Descriptions', on_click=self._open_project_examples_page).tooltip('Show the descriptions of all the MCU template examples.')

        with ui.row():
            self._new_project_path_input = ui.input(label='New project path').style('width: 800px;')
            self._new_project_path_input.value = self._cfgMgr.getAttr(GUIServerEXT1.NEW_PROJECT_PATH)
            self._select_example_project_dir_button = ui.button('Select folder', on_click=self._select_example_project_dir).tooltip("Select the folder to copy the example project into.")
            self._appendButtonList(self._select_example_project_dir_button)

        with ui.row():
            self._copy_example_button = ui.button('Copy Example Project', on_click=self._copy_example_project).tooltip('Copy MCU example code to a new folder to start your new project.')

    async def _select_example_project_dir(self):
        """@brief Select the folder to copy the project template example intoMCU main.py micropython file."""
        selected_path = self._new_project_path_input.value
        if not selected_path:
            selected_path = os.getcwd()
        file_and_folder_chooser = FileAndFolderChooser(selected_path)
        result = await file_and_folder_chooser.open()
        if result:
            selected_folder = result[0]
            if os.path.isdir(selected_folder):
                default_filename = f'project_template_{self._example_select.value}'
                self._new_project_path_input.value = os.path.join(selected_folder, default_filename)
                self._saveConfig()
                ui.notify(f"{default_filename} is the default project folder name. You may change this in 'New project path' field if required.", type='positive', position='top')

            else:
                self.error(f"{selected_folder} selected. You must select a folder.")

    def _open_project_examples_page(self):
        """@brief open the top level mcu code examples page in a separate browser window."""
        # This will open in a separate browser window
        ui.run_javascript("window.open('/project_examples', '_blank')")

    def copy_ignore(self, directory, contents):
        # directory: the current folder being copied
        # contents: list of names in that folder
        return {name for name in contents if name in ["__pycache__"]}

    def _copy_example_project(self):
        """@brief Copy the selected example project to a new project folder so that the user can make changes for the required project functionality."""
        try:
            project_path = self._new_project_path_input.value
            if not project_path:
                raise Exception("The 'New project path' must be entered.")

            p = Path(project_path)
            parent = p.parent
            if not os.path.isdir(parent):
                raise Exception(f"{parent} folder not found.")

            if os.path.isfile(project_path):
                raise Exception(f"Failed to create a new folder as {project_path} is an existing file.")

            if os.path.isdir(project_path):
                raise Exception(f"Failed to create a new folder as {project_path} is an existing folder.")

            selected_example = self._example_select.value
            example_folder = GUIServer.GetExample()
            selected_example_folder = os.path.join(example_folder, f'project_template_{selected_example}')
            if not os.path.isdir(selected_example_folder):
                raise Exception("{selected_example_folder} folder not found.")

            main_py_file = os.path.join(selected_example_folder, 'main.py')
            if not os.path.isfile(main_py_file):
                raise Exception(f"{main_py_file} file not found.")

            dest_folder = project_path
            self.info(f"Copying {selected_example_folder} to {dest_folder}")
            shutil.copytree(selected_example_folder, dest_folder, ignore=self.copy_ignore)

            dest_main_py_file = os.path.join(dest_folder, 'main.py')
            if not os.path.isfile(dest_main_py_file):
                raise Exception(f"{dest_main_py_file} file not found.")

            self._app_main_py_input.value = dest_main_py_file

            self.info('All files copied successfully')

        except Exception as ex:
            self.error(str(ex))

    @staticmethod
    def GetExample(filename=None):
        """@Get the example folder of file in the examples folder."""
        assetsFolder = get_assets_dir('mpy_tool')
        if not assetsFolder:
            raise Exception("assets folder not found.")

        example = os.path.join(assetsFolder, 'examples')
        if not os.path.isdir(example):
            raise Exception(f"{example} folder not found.")

        if filename:
            example = os.path.join(example, filename)
            if not os.path.isfile(example):
                raise Exception(f"{example} file not found.")

        return example

    # Serve the mcu examples pages.
    def project_examples(self):
        example = GUIServer.GetExample(filename = 'project_examples.md')
        ui.page_title('MPY Tool Example doc')
        ui.markdown(Path(example).read_text())

    def example_1_page(self):
        example = GUIServer.GetExample(filename = 'project_template_1_README.md')
        ui.page_title('MPY Tool Example 1 doc')
        ui.markdown(Path(example).read_text())

    def example_2_page(self):
        example = GUIServer.GetExample(filename = 'project_template_2_README.md')
        ui.page_title('MPY Tool Example 2 doc')
        ui.markdown(Path(example).read_text())

    def example_3_page(self):
        example = GUIServer.GetExample(filename = 'project_template_3_README.md')
        ui.page_title('MPY Tool Example 3 doc')
        ui.markdown(Path(example).read_text())

    def example_4_page(self):
        example = GUIServer.GetExample(filename = 'project_template_4_README.md')
        ui.page_title('MPY Tool Example 4 doc')
        ui.markdown(Path(example).read_text())

    def example_5_page(self):
        example = GUIServer.GetExample(filename = 'project_template_5_README.md')
        ui.page_title('MPY Tool Example 5 doc')
        ui.markdown(Path(example).read_text())

    def example_6_page(self):
        example = GUIServer.GetExample(filename = 'project_template_6_README.md')
        ui.page_title('MPY Tool Example 6 doc')
        ui.markdown(Path(example).read_text())

    def example_7_page(self):
        example = GUIServer.GetExample(filename = 'project_template_7_README.md')
        ui.page_title('MPY Tool Example 7 doc')
        ui.markdown(Path(example).read_text())

    # This page is referenced inside examples 4 and 5
    def wifi_setup_gpios_page(self):
        example = GUIServer.GetExample(filename = 'project_template_1_README.md')
        ui.markdown(Path(example).read_text())


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

    def init_gui(self):
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
        self.debug(f"CMD RESPONSE: {str(obj)}")
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


class MemoryUsageEnvArgs(EnvArgs):
    ENV_REF = MemoryUsage.__name__

class GUIServerEXT1(GUIServer):
    """@brief Add WiFi configuration to the GUIServer.
       This class integrates the WiFi setup with bluetooth (rather than just USB) that
       was not present in the parent class."""

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
        self._new_project_path_input = None
        self._cfgMgr = ConfigManager(self._uio, GUIServerEXT1.CFG_FILENAME, GUIServerEXT1.DEFAULT_CONFIG)
        self._loadConfig()
        self._saveConfig()

    def _saveConfig(self):
        """@brief Save some parameters to a local config file."""
        if self._app_main_py_input:
            self._cfgMgr.addAttr(GUIServer.MCU_MAIN_PY, self._app_main_py_input.value)

        self._cfgMgr.addAttr(GUIServerEXT1.WIFI_SSID, self._wifi_ssid)
        self._cfgMgr.addAttr(GUIServerEXT1.WIFI_PASSWORD, self._wifi_password)

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
        if self._new_project_path_input:
            self._cfgMgr.addAttr(GUIServerEXT1.NEW_PROJECT_PATH, self._new_project_path_input.value)

        self._cfgMgr.store()

    def _openUSBWifiDialog(self):
        """@brief Open the first dialog to configure WiFi over a USB connection.
                  The code to setup WiFi over a USB connection is encapsulated in this method."""

        def saveEnteredUSBWiFiDialogValues(self):
            self._copyWifiParams(self._wifiSSIDUSBInput.value, self._wifiPasswordUSBInput.value)
            self._saveConfig()

        def usbSetWiFiNetwork(self, wifiSSID, wifiPassword):
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

        def startUsbWifiSetupThread(self):
            """@brief Called to start the worker thread to setup the MCU WiFi over a USB connection.
            @param event The button event."""
            err_msg = self._get_wifi_ssid_passwd_err(self._wifiSSIDUSBInput.value, self._wifiPasswordUSBInput.value)
            if err_msg:
                ui.notify(err_msg, type='negative')

            else:
                self._initTask()
                duration = 300
                self._startProgress(durationSeconds=duration)
                threading.Thread(target=usbSetWiFiNetwork, args=(self, self._wifiSSIDUSBInput.value, self._wifiPasswordUSBInput.value)).start()

        with ui.dialog() as usbWiFiDialog2, ui.card():
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
                ui.button("Ok", on_click=lambda: (saveEnteredUSBWiFiDialogValues(self), usbWiFiDialog2.close(), startUsbWifiSetupThread(self),))
                ui.button("Cancel", on_click=lambda: (saveEnteredUSBWiFiDialogValues(self), usbWiFiDialog2.close(), self._sendEnableAllButtons(True)))

        # Create the dialog
        with ui.dialog() as usbWiFiDialog1, ui.card():
            ui.label("A USB cable must be connected between this PC and the MCU device to setup it's WiFi.\n\nContinue ?").style('white-space: pre-wrap;')
            with ui.row():
                ui.button("Ok", on_click=lambda: (usbWiFiDialog1.close(), usbWiFiDialog2.open(),))
                ui.button("Cancel", on_click=lambda: (usbWiFiDialog1.close(), self._sendEnableAllButtons(True)))

        usbWiFiDialog1.open()

    # This method is reused when checking the ssid and password for setting up WiFi via bluetooth.
    def _get_wifi_ssid_passwd_err(self, ssid, passwd):
        """@brief Get a user error message for ssid and password.
           @param ssid The WiFi ssid.
           @param passwd The WiFi password.
           @return The user error message or None if the ssid and password are set."""
        err_msg = None
        if not ssid and not passwd:
            err_msg = "A WiFi SSID and password must be entered."
        elif not ssid:
            err_msg = "A WiFi SSID must be entered."
        elif not passwd:
            err_msg = "A WiFi password must be entered."
        return err_msg

    # This method is reused when checking the ssid and password for setting up WiFi via bluetooth.
    def _copyWifiParams(self, ssid, password):
        """@brief Copy same ssid and password to all UI elements used to enter these parameters.
           @param ssid The WiFi network/SSID.
           @param password The WiFi password."""
        self._wifi_ssid = ssid
        self._wifi_password = password

    def _openBTWifiDialog(self):
        """@brief Open the first dialog to configure WiFi over a bluetooth connection.
                  The code to setup WiFi over a bluetooth connection is encapsulated in this method."""

        def saveEnteredBTWiFiDialogValues(self):
            self._copyWifiParams(self._wifiSSIDBTInput.value, self._wifiPasswordBTInput.value)
            self._saveConfig()

        def btSetWiFiNetworkThread(self, ssid, password):
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
                if ct6Address:
                    waitingForIP = False
                    self.info(f"YDev device IP address = {ipAddress}")
                    # Send a message to set the YDev device IP address in the GUI
                    self._setYDevIPAddress(ipAddress)
                    self.info("Turning off bluetooth interface on YDev device.")
                    yDevBlueTooth.disable_bluetooth(ct6Address)
                    self.info("Device now restarting...")
                    sleep(2)
                    self._waitForPingSuccess(ipAddress)
                    self.infoDialog("Device WiFi setup complete.")

            except Exception as ex:
                error = str(ex)
                if error:
                    self.error(error)

            finally:
                self._sendEnableAllButtons(True)

            # Report a more useful user msg
            if waitingForIP:
                self.error(f"YDev device failed to connect to WiFi network ({ssid}). Check the ssid and password.")

        def startBTWifiSetupThread(self):
            """@brief Called to start the worker thread to setup the YDev WiFi over a Bluetooth connection.
            @param event The button event."""
            err_msg = self._get_wifi_ssid_passwd_err(self._wifiSSIDBTInput.value, self._wifiPasswordBTInput.value)
            if err_msg:
                ui.notify(err_msg, type='negative')

            else:
                self._setExpectedProgressMsgCount(9, 20)
                threading.Thread(target=btSetWiFiNetworkThread, args=(self, self._wifiSSIDBTInput.value, self._wifiPasswordBTInput.value)).start()

        def startBluetoothWifiSetup(self):
            """@brief Start attempting to setup the YDev WiFi settings using a bluetooth connection to the YDev device."""
            self._initTask()
            self._saveConfig()
            duration = 300
            self._startProgress(durationSeconds=duration)
            threading.Thread(target=startBluetoothWifiSetupThread, args=(self,)).start()

        def startBluetoothWifiSetupThread(self):
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

        def ssidDropDownSelected(self, value):
            """@bried Update the selected WiFi SSID."""
            self._wifiSSIDBTInput.value = value

        # Create the dialog
        with ui.dialog() as bluetoothWiFiDialog1, ui.card():
            ui.label("Hold the WiFi button down on the MCU device until it restarts and the LED/s flash.\n\nContinue ?").style('white-space: pre-wrap;')
            with ui.row():
                ui.button("Ok", on_click=lambda: (bluetoothWiFiDialog1.close(), startBluetoothWifiSetup(self),))
                ui.button("Cancel", on_click=lambda: (bluetoothWiFiDialog1.close(), self._sendEnableAllButtons(True)))

        with ui.dialog() as btWiFiDialog2, ui.card():
            with ui.column():
                self._ssidDropDown = ui.select([], label="WiFi SSID's Found.").style('width: 200px;')
                self._ssidDropDown.on('popup-hide', lambda: ssidDropDownSelected(self, self._ssidDropDown.value))
                self._wifiSSIDBTInput = ui.input(label='WiFi SSID').style('width: 200px;')
                ssid = self._cfgMgr.getAttr(GUIServerEXT1.WIFI_SSID)
                if ssid:
                    self._wifiSSIDBTInput.value = ssid

                self._wifiPasswordBTInput = ui.input(label='WiFi Password', password=True, password_toggle_button=True).style('width: 200px;')
                passwd = self._cfgMgr.getAttr(GUIServerEXT1.WIFI_PASSWORD)
                if passwd:
                    self._wifiPasswordBTInput.value = passwd

            with ui.row():
                ui.button("Ok", on_click=lambda: (saveEnteredBTWiFiDialogValues(self), btWiFiDialog2.close(), startBTWifiSetupThread(self),))
                ui.button("Cancel", on_click=lambda: (saveEnteredBTWiFiDialogValues(self), btWiFiDialog2.close(), self._sendEnableAllButtons(True)))
            self._btWiFiDialog2 = btWiFiDialog2

        bluetoothWiFiDialog1.open()

    def _initWiFiTab(self):
        """@brief Create the Wifi tab contents."""
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

    def _startWifiSetup(self):
        """@brief Called to start the process of setting up the WiFi network."""
        if self._wifi_setup_radio.value == GUIServerEXT1.USB:
            if self._setSerialPortClosed():
                ui.notify('The serial port was open in the SERIAL PORT tab. It has been closed in order to proceed with the WiFi setup process.', type='warning')

            self._openUSBWifiDialog()

        elif self._wifi_setup_radio.value == GUIServerEXT1.BLUETOOTH:
            self._openBTWifiDialog()

    def _setExpectedProgressMsgCount(self, nonDebugModeCount, debugModeCount):
        """@brief Set the number of log messages expected to complete a tasks progress.
           @param nonDebugModeCount The number of expected messages in non debug mode.
           @param nonDebugModeCount The number of expected messages in debug mode."""
        if self._uio.isDebugEnabled():
            self._startProgress(expectedMsgCount=debugModeCount)
        else:
            self._startProgress(expectedMsgCount=nonDebugModeCount)

    def _wifiPasswordBTInputTogglePassword(self):
        self._wifiPasswordBTInput.password = not self._wifiPasswordBTInput.password
        self._wifiPasswordBTInput.update()

    def _waitForPingSuccess(self, address):
        upgradeManager = UpgradeManager(self._mcuTypeSelect.value, uio=self)
        upgradeManager._waitForPingSuccess(address)

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

        if GUIServer.RAW_MESSAGE in rxDict:
            msg = rxDict[GUIServer.RAW_MESSAGE]
            self._rawGT(msg)

        if GUIServer.SET_EDITOR_LINES in rxDict:
            lines = rxDict[GUIServer.SET_EDITOR_LINES]
            self._set_editor(lines)

    def _set_editor(self, lines):
        self._code_editor.value = "\n".join(lines)

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
        """@brief Setup the YDev WiFi interface over a USB interface. This must be called outside the GUI thread.
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

    # If the program throws a system exit exception
    except SystemExit:
        pass
    # Don't print error information if CTRL C pressed
    except KeyboardInterrupt:
        pass
    except Exception as ex:
        logTraceBack(uio)

        if options.debug:
            raise
        else:
            uio.error(str(ex))


if __name__ in {"__main__", "__mp_main__"}:
    main()


