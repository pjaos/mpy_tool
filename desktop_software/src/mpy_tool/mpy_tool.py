#!/usr/bin/env python3

import argparse

from   lib.general import MCUBase
from   lib.mcu_loader import USBLoader, UpgradeManager, LoaderBase

from   p3lib.uio import UIO
from   p3lib.helper import logTraceBack

from p3lib.pconfig import ConfigManager, ConfigAttrDetails

class WiFiConfig(object):
    """@brief responsible for holding the WiFi config when setting up a devices WiFi."""
    CONFIG_FILENAME = "mcu_tool_wifi.cfg"
    SSID_STR = "SSID_STR"
    PASSWORD_STR = "PASSWORD_STR"

    DEFAULT_CONFIG = {
        SSID_STR: "",
        PASSWORD_STR: ""
    }

    CONFIG_ATTR_DETAILS_DICT = {
        SSID_STR: ConfigAttrDetails("Enter the WiFi network/ssid"),
        PASSWORD_STR: ConfigAttrDetails("Enter the WiFi password")
    }

    def __init__(self, uio):
        self._configManager = ConfigManager(uio, WiFiConfig.CONFIG_FILENAME, WiFiConfig.DEFAULT_CONFIG)

    def edit(self):
        self._configManager.edit(WiFiConfig.CONFIG_ATTR_DETAILS_DICT)

    def getSSID(self):
        return self._configManager.getAttr(WiFiConfig.SSID_STR)

    def getPassword(self):
        return self._configManager.getAttr(WiFiConfig.PASSWORD_STR)


class MCU_Tool(MCUBase):

    @staticmethod
    def GetCmdOpts():
        """@brief Get a reference to the command line options.
        @return The options instance."""
        parser = argparse.ArgumentParser(description="A tool to manage MCU devices.",
                                        formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument("--picow",            action='store_true', help="The original Pico W MCU.")
        parser.add_argument("--pico2w",           action='store_true', help="The Pico 2 W (second generation) MCU.")
        parser.add_argument("--esp32",            action='store_true', help="The original esp32 MCU.")
        parser.add_argument("--esp32c3",          action='store_true', help="The esp32c3 MCU.")
        parser.add_argument("--esp32c6",          action='store_true', help="The esp32c6 MCU.")
        parser.add_argument("-f", "--folder",     help="Folder containing the MCU micropython app to be loaded.")
        parser.add_argument("-a", "--address",    help="The IP address of the MCU on the WiFi network if upgrading.")
        parser.add_argument("-u", "--upgrade",    action='store_true', help="Upgrade the device app. If -a/--address defined the upgrade is performed over the WiFi network, if not use a USB port.")

        parser.add_argument("-p", "--port",       help="The serial port connected to the MCU if installing or upgrading. If not defined then the first serial port found is used.")
        parser.add_argument("-i", "--init",       action='store_true', help="Init the MCU (Pico W or esp32). Erases flash memory, loads MicroPython and then loads the app via a USB interface.")
        parser.add_argument("-l", "--load",       action='store_true', help="Load app onto MCU (Pico W or esp32). This is similar to the --init option but does not load MicroPython.")

        parser.add_argument("-w", "--setup_wifi", action='store_true', help="Setup the device WiFi interface.")
        parser.add_argument("-s", "--scan",       action='store_true', help="Scan for devices on the LAN/WiFi.")
        parser.add_argument("-v", "--view",       action='store_true', help="View received data on first /dev/ttyUSB* or /dev/ttyACM* serial port.")
        parser.add_argument("-d", "--debug",      action='store_true', help="Enable debugging.")
        parser.add_argument("-c", "--copy_example",    type=int, help="Copy example code to a new project folder.")
        options = parser.parse_args()
        return options

def main():
    """@brief Program entry point"""
    uio = UIO()

    try:
        options = MCU_Tool.GetCmdOpts()
        uio.enableDebug(options.debug)
        mcuType = "unknown"

        loadMPY = True

        if options.copy_example:
            LoaderBase.CopyExample(uio, options.copy_example)
            return

        elif options.picow:
            mcuType = USBLoader.RPI_PICOW_MCU_TYPE

        elif options.pico2w:
            mcuType = USBLoader.RPI_PICO2W_MCU_TYPE

        elif options.esp32:
            mcuType = USBLoader.ESP32_MCU_TYPE

        elif options.esp32c3:
            mcuType = USBLoader.ESP32C3_MCU_TYPE

        elif options.esp32c6:
            mcuType = USBLoader.ESP32C6_MCU_TYPE

        else:
            raise Exception("Please provide the MCU type on the command line.")

        usbLoader = USBLoader(mcuType, uio=uio)
        if options.init:
            usbLoader.setSerialPort(options.port)
            usbLoader.install(True, True, True, options.folder, loadMPY)

        if options.upgrade:
            upgradeManager = UpgradeManager(mcuType, uio=uio)
            upgradeManager.upgrade(options.address, options.folder, loadMPY)

        elif options.load:
            usbLoader.setSerialPort(options.port)
            usbLoader.install(False, False, True, options.folder, loadMPY)

        elif options.view:
            usbLoader.viewSerialOut()

        elif options.setup_wifi:
            wiFiConfig = WiFiConfig(uio)
            wiFiConfig.edit()
            usbLoader.setupWiFi(wiFiConfig.getSSID(), wiFiConfig.getPassword())

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
