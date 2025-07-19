import os
import shutil
import string
import serial
import getpass
import traceback
import mpy_cross
import json
import tempfile
import requests
import hashlib
import socket
import ping3
import esptool
import io
import sys

from   p3lib.helper import get_assets_folder

from pyflakes.reporter import Reporter
from pyflakes.api import checkRecursive
from lib.general import MCUBase
from time import sleep, time
from retry import retry
from copy import copy
from subprocess import check_call, PIPE, check_output
from threading import Thread
from random import random

class LoaderBase(MCUBase):

    PYTHON_FILE_EXTENSION       = ".py"
    MICROPYTHON_FILE_EXTENSION  = ".mpy"
    MACHINE_CONFIG_FILE         = "this.machine.cfg"
    BLUETOOTH_ON_KEY            = 'BLUETOOTH_ON_KEY'
    WIFI_KEY                    = "WIFI"
    AP_CHANNEL_KEY              = "AP_CHANNEL"
    MODE_KEY                    = "MODE"
    PASSWORD_KEY                = "PASSWORD"
    WIFI_CONFIGURED_KEY         = "WIFI_CONFIGURED"
    SSID_KEY                    = "SSID"

    MAIN_PYTHON_FILE            = "main.py"
    MAIN_MICROPYTHON_FILE       = "main.mpy"

    RPI_PICOW_MCU_TYPE          = 'RPi Pico W'
    RPI_PICO2W_MCU_TYPE         = 'RPi Pico 2 W'
    VALID_PICOW_TYPES           = [RPI_PICOW_MCU_TYPE, RPI_PICO2W_MCU_TYPE]
    ESP32_MCU_TYPE              = "esp32"
    ESP32C3_MCU_TYPE            = "esp32c3"
    ESP32C6_MCU_TYPE            = "esp32c6"
    VALID_ESP32_TYPES           = [ESP32_MCU_TYPE, ESP32C3_MCU_TYPE, ESP32C6_MCU_TYPE]
    VALID_MCU_TYPES             = VALID_PICOW_TYPES + VALID_ESP32_TYPES

    PICOW_BRD_ID                = 'RPI-RP2'
    PICO2W_BRD_ID               = 'RP2350'

    @staticmethod
    def IsPicoW(mcuType):
        return mcuType in LoaderBase.VALID_PICOW_TYPES

    @staticmethod
    def IsEsp32(mcuType):
        return mcuType in LoaderBase.VALID_ESP32_TYPES

    @staticmethod
    def GetFiles(fileList, searchPath):
        """@brief Recursively search for files in a folder.
           @param fileList The list of files to add to.
           @param searchPath The path to search for files."""
        entries = os.listdir(searchPath)
        for entry in entries:
            fullPath = os.path.join(searchPath, entry)
            if os.path.isfile(fullPath):
                fileList.append(fullPath)

            elif os.path.isdir(fullPath):
                LoaderBase.GetFiles(fileList, fullPath)

    @staticmethod
    def GetSubFileList(inputFileList, extension, include=True):
        """@brief Get a lis of files with the given extension.
           @brief inputFileList The input file list to search.
           @param extension The file extension to search for.
           @param include If True include only files with the given extension
                          in the returned file list. If False then exclude
                          files with the given extension from the returned file list.
           @return A list containing a subset or identical list of fileList
                   containing only files with the given extension."""
        if not extension.startswith("."):
            extension = "."+extension
        outputFileList = []
        for f in inputFileList:
            if f.endswith(extension):
                if include:
                    outputFileList.append(f)
            else:
                if not include:
                    outputFileList.append(f)

        return outputFileList

    @staticmethod
    def ResetESP32(uio, ser):
        """@brief Perform a reset on an ESP32 device.
                  The ESP32 MCU reset is connected to the RTS control signal. We use this to assert the reset and release it.
                  The serial port connected to an ESP32 device must be connected and openFirstSerialPort() must have been
                  called prior to calling this method leaving the serial port open.
           @param uio A UIO instance.
           @param ser n open serial port connected to an ESP32 device."""
        # Reset ESP32
        ser.setDTR(False)  # IO0 high
        ser.setRTS(True)   # EN low (reset)
        uio.info("Asserting esp32 hardware reset.")
        sleep(0.25)
        ser.setRTS(False)  # EN high
        uio.info("Released esp32 hardware reset.")
        sleep(0.25)

    @staticmethod
    def REPLGetFileContents(ser, filename):
        """@brief Get the contents of a text file when the serial port is connected to an MCU running MicroPython
                  presenting the interactive python REPL prompt.
           @param ser The open serial port connected to the MCU.
           @param filename The filename of the file to read.
           @return The file contents of None if we failed to read the file."""
        line = None
        fileContents = None
        startTime = time()
        while fileContents is None and time() < startTime+2:
            cmdLine = f'fd = open("{filename}") ; lines = fd.readlines() ; fd.close() ; print(lines[0])\r'
            ser.write(cmdLine.encode())
            sleep(0.25) # Give the MCU time to respond
            bytesAvailable = ser.in_waiting
            if bytesAvailable > 0:
                data = ser.read(bytesAvailable)
                if len(data) > 0:
                    data=data.decode("utf-8", errors="ignore")
                    lines = data.split("\n")
                    for line in lines:
                        if line.startswith('{"'):
                            fileContents = line
                            break
        return line

    @staticmethod
    def REPLGetFlashStats(ser):
        """@brief Get flash size and used space info when the serial port is connected to an MCU running MicroPython
                  presenting the interactive python REPL prompt.
           @param ser The open serial port connected to the MCU.
           @return A tuple containing
                   0 = Total Space in bytes.
                   1 = Free space in bytes."""
        totalBytes = -1
        freeBytes  = -1
        fileContents = None
        startTime = time()
        while fileContents is None and time() < startTime+2:
            cmdLine = "import uos ; uos.statvfs('/')\r"
            ser.write(cmdLine.encode())
            sleep(0.25) # Give the MCU time to respond
            bytesAvailable = ser.in_waiting
            if bytesAvailable > 0:
                data = ser.read(bytesAvailable)
                if len(data) > 0:
                    data=data.decode("utf-8", errors="ignore")
                    lines = data.split("\n")
                    for line in lines:
                        line=line.rstrip("\n\r")
                        if line.startswith('(') and line.endswith(')'):
                            line = line[1:-1]
                            elems = line.split(", ")
                            values = list(map(int, elems))
                            if len(values) > 4:
                                totalBytes = values[0] * values[2]
                                freeBytes = values[0] * values[3]
                            break
        return [totalBytes, freeBytes]

    @staticmethod
    def GetTempFolder():
        """@return The temp storage folder."""
        tempFolder = tempfile.gettempdir()
        if LoaderBase.IsWindowsPlatform():
            # On Windows we use the install folder as it should be writable
            tempFolder = os.path.dirname(__file__)
        return tempFolder

    @staticmethod
    def SaveDictToJSONFile(theDict, filename, uio):
        """@brief Save a dict to a file (JSON format).
           @param theDict The python dictionary to save.
           @param filename The filename to save the dict (in JSON format) to.
           @param uio An optional UIO instance to add debug message."""
        if uio:
            uio.debug(f"Saving to {filename}")
        with open(filename, 'w') as fd:
            json.dump(theDict, fd, ensure_ascii=False)

    @staticmethod
    def CheckPythonCode(rootPath):
        """@brief Check the python code using pyflakes
           @param rootPAth The root path of the python code to check."""
        # Custom reporter to capture messages
        class CaptureReporter(Reporter):
            def __init__(self):
                self.output = io.StringIO()
                super().__init__(self.output, self.output)

            def get_messages(self):
                return self.output.getvalue()
        reporter = CaptureReporter()
        checkRecursive((rootPath,), reporter)
        return reporter.get_messages()

    @staticmethod
    def GenByteCode(pythonFile):
        """@brief Create a python byte code file from the python file.
           @param pythonFile The python file to be converted.
           @return The python bytecode file after conversion."""
        outputFile = pythonFile.replace(".py",".mpy")
        process = mpy_cross.run(f"{pythonFile}", stdout=PIPE)
        # Wait for conversion to complete
        process.wait()
        if process.returncode != 0:
            raise Exception(f"Process to convert {pythonFile} to bytecode failed (return code = {process.returncode}).")
        if not os.path.isfile(outputFile):
            raise Exception("Failed to create {} python bytecode file.".format(outputFile))
        return outputFile

    @staticmethod
    def GetRShellPath(aPath):
        """@brief Convert a path to a path that can be used by rshell.
                  This will convert '\' characters into '/' characters and remove the drive letter as rshell requires this."""
            # rshell uses / as the file separator characters regardless of the platform its running on.
            # Therefore replace \ characters with / characters (needed on a Windows platforms).
        # On Windows platforms rshell will be unable to find the file if it starts with a drive letter.
        if LoaderBase.IsWindowsPlatform():
            # Therefore if the path starts c: then remove it. If the file is on another drive rshell will not support copying it.
            if aPath.upper().startswith("C:"):
                # Remove the drive from the path
                aPath = aPath[2:]

            # Allow the rshell /pyboard folder.
            elif aPath.startswith('/pyboard'):
                pass

            else:
                raise Exception(f"Currently rshell can only reference files on the C: drive on Windows platform: {aPath}")

        return  aPath.replace('\\','/')

    def __init__(self, mcu, uio=None):
        """@brief Constructor."""
        super().__init__(uio)
        self._mcu = mcu
        self._ser = None
        self._tempFolder = LoaderBase.GetTempFolder()
        self._appRootFolder = None

    def _isPico(self):
        pico=False
        if self._mcu and self._mcu.lower().find('pico') != -1:
            pico = True
        return pico

    def openFirstSerialPort(self, baud=115200):
        """@brief Wait for a serial port to appear on this machine.
           @param baud The baud rate of the serial port in bps.
           @return A reference to the open serial port obj."""
        dtr=True
        rts=True
        return self._openFirstSerialPort(baud=baud, dtr=dtr, rts=rts)

    def _deleteFiles(self, fileList, showMsg=True):
        """@brief Delete files details in the file list.
           @param showMsg If True then show the message detailing each file deleted."""
        for aFile in fileList:
            if os.path.isfile(aFile):
                os.remove(aFile)
                if showMsg:
                    self.debug("Deleted local {}".format(aFile))

    def _getRShellCmd(self, port, cmdFile):
        """@brief Get the RSHell command line.
           @param port The serial port to use.
           @param cmdFile The rshell command to execute."""
        dtr=1
        rts=1
        cmd = f'mpy_tool_rshell --rts {rts} --dtr {dtr} --timing -p {port} --buffer-size 128 -f "{cmdFile}"'
        return cmd

    def _runRshellCmdFile(self, port, cmdFile, allowFailure=False):
        """@brief Run an rshell command file.
           @param port The serial port to run the command over.
           @param cmdFile The rshell command file to execute.
           @param allowFailure If True then allow the command to fail. If False then an exception is thrown if the command fails.
           @return the output from the command executed as a string."""
        rshellCmd = self._getRShellCmd(port, cmdFile)
        self.debug(f"EXECUTING: {rshellCmd}")
        if allowFailure:
            try:
                return check_output(rshellCmd, shell=True).decode("utf-8", errors="ignore")
            except Exception as ex:
                self.error( str(ex) )
        else:
            return check_output(rshellCmd, shell=True).decode("utf-8", errors="ignore")

    def _runRShell(self, cmdList):
        """@brief Run an rshell command file.
           @param cmdList A list of commands to execute."""
        cmdFile = MCULoader.RSHELL_CMD_LIST_FILE
        self.debug(f"Creating {cmdFile}")
        # Create the rshell cmd file.
        fd = open(cmdFile, 'w')
        for line in cmdList:
            fd.write(f"{line}\n")
        fd.close()
        self._runRshellCmdFile(self._serialPort, MCULoader.RSHELL_CMD_LIST_FILE)

    def _checkMCUCorrect(self, line, checkIDLine=False):
        """@brief Check that the configured MCU is set correctly given the response to CTRL B @ REPL prompt or
                  the response from a esptool check_id command.
           @param line The line of text received in response to CTRL B on the serial port.
           @param If True the line is an esptool check_id command response. The esptool check_id command
                  returns different text to identify the device."""
        correct = False
        mcu = self._mcu
        if mcu == LoaderBase.ESP32_MCU_TYPE:
            if checkIDLine and "ESP32" in line:
                    correct = True

            elif "ESP32 " in line: # Space required to ensure it's not a later esp32 variant.
                correct = True

        elif mcu == LoaderBase.ESP32C3_MCU_TYPE:
            if checkIDLine and "ESP32-C3" in line:
                    correct = True

            elif "ESP32C3" in line:
                correct = True

        elif mcu == LoaderBase.ESP32C6_MCU_TYPE:
            if checkIDLine and "ESP32-C6" in line:
                    correct = True
            # At the current time esp32c6 MicroPython support is in progress.
            # The current version of MicroPython reports ESP32 rather than ESP32C6.
            elif "ESP32" in line or "ESP32C6" in line:
                    correct = True

        elif mcu == LoaderBase.RPI_PICOW_MCU_TYPE:
            if "RP2040" in line:
                correct = True

        elif mcu == LoaderBase.RPI_PICO2W_MCU_TYPE:
            if "RP2350" in line:
                correct = True

        if not correct:
            raise Exception(f"Incorrect MCU type. A {self._mcu} MCU is not connected via a USB cable.")

    def _checkMicroPython(self, closeSerialPort=True, timeoutSeconds=30, checkMCUCorrect=False):
        """@brief Check micropython is loaded onto the MCU connected vis USB.
           @param closeSerialPort If True then close the serial port on exit.
           @param timeoutSeconds Seconds to wait before timeout.
           @param checkMCUCorrect If True ensure the configured MCU type is correct.
           @return The MicroPython description line returned in response to CTRL sent on the serial port or None."""
        mpDescripLine = None
        self.debug("_checkMicroPython(): START")
        timeoutS = time()+timeoutSeconds
        replPromptFound = False
        try:
            try:
                self.openFirstSerialPort()
                if self._serialPort:
                    self.info(f"Found USB port: {self._serialPort}")
                timeToSend = time()+1
                self.info(f"Checking for MCU MicroPython prompt ({timeoutSeconds} second timeout)...")
                while True:
                    self.debug(".")
                    now = time()
                    # Send CTRL C periodically
                    if now >= timeToSend:
                        if replPromptFound:
                            self._ser.write(b"\02")
                            self.debug("Sent CTRL B")
                        else:
                            self._ser.write(b"\03")
                            self.debug("Sent CTRL C")
                        # Send every 2 seconds
                        timeToSend = now+2

                    elif self._ser.in_waiting > 0:
                        # Read the data that's arrived so
                        data = self._ser.read(self._ser.in_waiting)
                        if len(data) > 0:
                            data=data.decode("utf-8", errors="ignore")
                            self.debug(f"Serial data = {data}")
                            if replPromptFound:
                                pos = data.find("MicroPython")
                                if pos >= 0:
                                    _data = data[pos:]
                                    lines = _data.split("\r\n")
                                    if len(lines) > 0:
                                        line = lines[0]
                                        self.info(line)
                                        mpDescripLine = line
                                        if checkMCUCorrect:
                                            self._checkMCUCorrect(line)
                                        break
                            else:
                                pos = data.find(">>>")
                                if pos >= 0:
                                    replPromptFound = True

                    # Delay so we don't spinlock and to allow serial data to arrive
                    sleep(0.25)

                    if time() > timeoutS:
                        raise Exception(f"{timeoutSeconds} second timeout waiting for MCU MicroPython prompt.")

            except serial.SerialException:
                self.debug(f"SerialException: {traceback.format_exc()}")
                raise

            except OSError:
                self.debug(f"SerialException: {traceback.format_exc()}")
                raise

        finally:
            if closeSerialPort:
                self._closeSerialPort()

        self.debug("_checkMicroPython(): STOP")
        return mpDescripLine

    def esp32HWReset(self, ser=None):
        """@brief Perform a reset on an ESP32 device.
           @param ser A ref to an open serial port. If None then the first available serial port is used.
                  The ESP32 MCU reset is connected to the RTs control signal. We use this to assert the reset and release it."""
        try:
            if ser is None:
                ser = self.openFirstSerialPort()
            USBLoader.ResetESP32(self._uio, ser)
            # Wait for MCU to come out of reset
            sleep(1)

        finally:
            if ser:
                ser.close()
                ser = None

    def _closeSerialPort(self):
        """@brief Close the serial port if it's open."""
        if self._ser:
            self._ser.close()
            self._ser = None
            self.debug(f"{self._serialPort}: Closed.")

    def rebootUnit(self, esp32HWReboot=False):
        """@brief reboot a MCU device.
           @param esp32HWReboot If True and the HW is a type of esp32 MCU then the HW reset pin is used to reset it."""
        self.info(f"Rebooting the MCU ({self._mcu})")

        self._closeSerialPort()

        if esp32HWReboot and self._mcu in USBLoader.VALID_ESP32_TYPES:
            self.esp32HWReset()

        else:
            try:
                # Attempt to connect to the board under test python prompt
                self._checkMicroPython(closeSerialPort=False)
                try:
                    # Send the python code to reboot the MCU, three times.
                    count = 0
                    while count < 3:
                        self._ser.write(b"import machine ; machine.reset()\r")
                        sleep(0.1)
                        count += 1

                except serial.SerialException:
                    pass
            finally:
                self._closeSerialPort()

        # We need a short delay or subsequent serial port use throws errors
        # possibly because the serial port disappears and then reappears as observed on Linux.
        # 1 second fails sometimes, 1.5 seconds seems ok but this may be machine dependant !!!
        sleep(2)

    def _getWiFiDict(self, ssid, password):
        """@brief Get a dict containing the Wifi configuration.
           @param ssid The Wifi SSID/network.
           @param password The WiFi password.
           @return The WiFi configuration dict."""
        return {LoaderBase.MODE_KEY: 1,
                LoaderBase.SSID_KEY: ssid,
                LoaderBase.PASSWORD_KEY: password,
                LoaderBase.AP_CHANNEL_KEY: 3,
                LoaderBase.WIFI_CONFIGURED_KEY: 1}

    def _convertToMPY(self, pyFileList):
        """@brief Generate *.mpy files for all files in app1 and app1/lib
           @param pyFileList Python file list."""
        mpyFileList = []
        for pyFile in pyFileList:
            mpyFile = LoaderBase.GenByteCode(pyFile)
            mpyFileList.append(mpyFile)

        return mpyFileList

    def getAppFileList(self, loadMPYFiles=True):
        """@brief Get the list of files to load for the given app root path.
           @param loadMPYFiles If True (default) we compile the .py files to .mpy files and
                               load these. This saves significant MCU flash memory space.
                               If False then the python files are loaded."""

        if loadMPYFiles:
            fileList = []
            LoaderBase.GetFiles(fileList, self._appRootFolder)
            pyFileList = LoaderBase.GetSubFileList(fileList, LoaderBase.PYTHON_FILE_EXTENSION)
            mainPy = os.path.join(self._appRootFolder, LoaderBase.MAIN_PYTHON_FILE)
            # Ensure we have the main python file
            if mainPy not in pyFileList:
                raise Exception(f"{LoaderBase.MAIN_PYTHON_FILE} file not found in {self._appRootFolder}")
            mpyFileList = self._convertToMPY(pyFileList)
            # Do Not load the .py files onto the MCU only the .mpy and other files
            filesToLoad = LoaderBase.GetSubFileList(fileList, LoaderBase.PYTHON_FILE_EXTENSION, include=False)
            filesToLoad = filesToLoad + mpyFileList
            # Ensure we load the main python file
            filesToLoad.insert(0, mainPy)
            # Remove the main.mpy file from the list
            mainMpyFile = os.path.join(self._appRootFolder, LoaderBase.MAIN_MICROPYTHON_FILE)
            if mainMpyFile in filesToLoad:
                index = filesToLoad.index(mainMpyFile)
                if index >= 0:
                    del filesToLoad[index]
        else:
            # Ensure we don't have any mpy files at or below the app root folder.
            self.deleteLocalMPYFiles()
            filesToLoad = []
            # Load all files in and under the app root folder to the MCU
            LoaderBase.GetFiles(filesToLoad, self._appRootFolder)
        return filesToLoad

    def deleteLocalMPYFiles(self, showMsg=True):
        """@brief Delete existing *.mpy files,
           @param showMsg If True then show the message detailing each file deleted."""
        fileList = []
        LoaderBase.GetFiles(fileList, self._appRootFolder)
        # !!! Be careful with this code !!!
        # Don't change .mpy to .py or you could your python source code before checking it in to git.
        mpyFileList = LoaderBase.GetSubFileList(fileList, LoaderBase.MICROPYTHON_FILE_EXTENSION)
        self._deleteFiles(mpyFileList, showMsg=showMsg)

    def doPing(self, address):
        """@brief Attempt to ping the address.
           @return The time number of seconds it took for the ping packet to be returned or None if no ping packet returned."""
        pingSec = None
        if self._windowsPlatform:
            # On windows we can use the python ping3 module
            pingSec = ping3.ping(address)
        else:
            # On Linux the ping3 module gives 'Permission denied' errors for non root users
            # so we use the command line ping instead.
            try:
                startT = time()
                cmd = f"ping -W 1 -c 1 {address} 2>&1 > /dev/null"
                check_call(cmd, shell=True)
                pingSec = time()-startT
            except:
                pass
        return pingSec

    def checkMCUCode(self):
        """@brief Run pyflakes3 on the app1 folder code to check for errors before loading it."""
        self.info("Checking python code in the app1 folder using pyflakes")
        messages = USBLoader.CheckPythonCode(self._appRootFolder)
        if len(messages) > 0:
            self.error(messages)
            raise Exception("Errors were found in the Python MCU code. Fix these and try again.")
        self.info("Python MCU code passed the code check.")


class USBLoader(LoaderBase):
    PICO_IMAGE_FOLDER_NAME          = os.path.join("picow_flash_images", "pico1w")
    PICO2W_IMAGE_FOLDER_NAME        = os.path.join("picow_flash_images", "pico2w")
    PICO_ERASE_IMAGE                = "flash_nuke.uf2"
    PICO_MICROPYTHON_IMAGE          = "firmware.uf2"
    ESP32_IMAGE_FOLDER_NAME         = "esp32_flash_images"
    ESP32_MICROPYTHON_IMAGE         = "firmware.bin"
    ESP32C3_BOOTLOADER_IMAGE        = "bootloader.bin"
    ESP32C3_MICROPYTHON_IMAGE       = "micropython.bin"
    ESP32C3_PARTITION_TABLE_IMAGE   = "partition-table.bin"
    ESP32C6_BOOTLOADER_IMAGE        = ESP32C3_BOOTLOADER_IMAGE
    ESP32C6_PARTITION_TABLE_IMAGE   = ESP32C3_PARTITION_TABLE_IMAGE
    ESP32C6_MICROPYTHON_IMAGE       = ESP32C3_MICROPYTHON_IMAGE
    ESPTOOL_DETECTING_CHIP_TYPE     = "Detecting chip type..."
    INFO_UF2_TXT_FILE               = "info_uf2.txt"
    RPI_BOOT_BTN_DWN_FILE_LIST      = ["index.htm", INFO_UF2_TXT_FILE]
    ERASE_PCIO_FLASH                = 1
    LOAD_MICROPYTHON_TO_PICO_FLASH  = 2
    PICO_USB_PRODUCT_PARAM          = "Board in FS mode"
    PICO_USB_INTERFACE_PARAM        = "Board CDC"
    RPI_PICO_VENDOR_ID              = 11914
    RPI_PICO_PRODUCT_ID             = 5
    ESP32_VENDOR_ID                 = 4292
    ESP32_PRODUCT_ID                = 60000

    @staticmethod
    def GetPicoImagesFolder():
        """@return The Pico image file folder."""
        imageFolder = os.path.join(get_assets_folder(), USBLoader.PICO_IMAGE_FOLDER_NAME)
        if not os.path.isdir(imageFolder):
            raise Exception(f"{imageFolder} path not found.")
        return imageFolder

    @staticmethod
    def GetErasePicoFile():
        """@return The image that will erase the flash on the RPi Pico W MCU."""
        erasePicoImageFile = os.path.join(USBLoader.GetPicoImagesFolder(), USBLoader.PICO_ERASE_IMAGE)
        if not os.path.isfile(erasePicoImageFile):
            raise Exception(f"{erasePicoImageFile} file not found.")
        return erasePicoImageFile

    @staticmethod
    def GetPicoMicroPythonFile():
        """@return The Pico image file."""
        microPythonFile = os.path.join(USBLoader.GetPicoImagesFolder(), USBLoader.PICO_MICROPYTHON_IMAGE)
        if not os.path.isfile(microPythonFile):
            raise Exception(f"{microPythonFile} file not found.")
        return microPythonFile

    @staticmethod
    def GetPico2WImagesFolder():
        """@return The Pico 2 W image file folder."""
        imageFolder = os.path.join(get_assets_folder(), USBLoader.PICO2W_IMAGE_FOLDER_NAME)
        if not os.path.isdir(imageFolder):
            raise Exception(f"{imageFolder} path not found.")
        return imageFolder

    @staticmethod
    def GetErasePico2WFile():
        """@return The image that will erase the flash on the RPi PicoW MCU."""
        erasePicoImageFile = os.path.join(USBLoader.GetPico2WImagesFolder(), USBLoader.PICO_ERASE_IMAGE)
        if not os.path.isfile(erasePicoImageFile):
            raise Exception(f"{erasePicoImageFile} file not found.")
        return erasePicoImageFile

    @staticmethod
    def GetPico2WMicroPythonFile():
        """@return The Pico image file."""
        microPythonFile = os.path.join(USBLoader.GetPico2WImagesFolder(), USBLoader.PICO_MICROPYTHON_IMAGE)
        if not os.path.isfile(microPythonFile):
            raise Exception(f"{microPythonFile} file not found.")
        return microPythonFile

    @staticmethod
    def GetESP32ImagesFolder():
        """@return The esp32 image file folder."""
        imageFolder = os.path.join(get_assets_folder(), USBLoader.ESP32_IMAGE_FOLDER_NAME)
        if not os.path.isdir(imageFolder):
            raise Exception(f"{imageFolder} path not found.")
        return imageFolder

    @staticmethod
    def GetESP32MicroPythonFile():
        """@return The esp32 image file."""
        folder = os.path.join(USBLoader.GetESP32ImagesFolder(), 'esp32')
        microPythonFile = os.path.join(folder, USBLoader.ESP32_MICROPYTHON_IMAGE)
        if not os.path.isfile(microPythonFile):
            raise Exception(f"{microPythonFile} file not found.")
        return microPythonFile

    @staticmethod
    def GetESP32C3MicroPythonFiles():
        """@return A Tuple containing the files to load to an ESP32 C3."""
        folder = os.path.join(USBLoader.GetESP32ImagesFolder(), 'esp32c3')
        bootLoaderFile = os.path.join(folder, USBLoader.ESP32C3_BOOTLOADER_IMAGE)
        partionTableFile = os.path.join(folder, USBLoader.ESP32C3_PARTITION_TABLE_IMAGE)
        microPythonFile = os.path.join(folder, USBLoader.ESP32C3_MICROPYTHON_IMAGE)
        fileList = (bootLoaderFile, partionTableFile, microPythonFile)
        for _file in fileList:
            if not os.path.isfile(_file):
                raise Exception(f"{_file} file not found.")
        return fileList

    @staticmethod
    def GetESP32C6MicroPythonFiles():
        """@return A Tuple containing the files to load to an ESP32 C6."""
        folder = os.path.join(USBLoader.GetESP32ImagesFolder(), 'esp32c6')
        bootLoaderFile = os.path.join(folder, USBLoader.ESP32C6_BOOTLOADER_IMAGE)
        partionTableFile = os.path.join(folder, USBLoader.ESP32C6_PARTITION_TABLE_IMAGE)
        microPythonFile = os.path.join(folder, USBLoader.ESP32C6_MICROPYTHON_IMAGE)
        fileList = (bootLoaderFile, partionTableFile, microPythonFile)
        for _file in fileList:
            if not os.path.isfile(_file):
                raise Exception(f"{_file} file not found.")
        return fileList

    @staticmethod
    def GetAllPicoPaths():
        """@brief Get the path of the RPi Pico W device when mounted (powered up with button down).
           @return A list of all the valid paths any type of RPi Pico May be mounted at."""
        srcPathList = []
        windowsPlatform = USBLoader.IsWindowsPlatform()
        if windowsPlatform:
            # We try all Windows drive names except A:/B: (org floppy drives) and C: (hdd/ssd drive)
            srcPathList = ['%s:' % d for d in string.ascii_uppercase if d not in ('A', 'B' , 'C')]

        elif USBLoader.IsMacOSPlatform():
            srcPathList = ["/Volumes/RPI-RP2","/Volumes/RP2350"]

        else:
            srcPathList = [f"/media/{getpass.getuser()}/RPI-RP2",f"/media/{getpass.getuser()}/RP2350"]

        srcPathList = [s for s in srcPathList if not s.startswith("C:")]

        return srcPathList

    @staticmethod
    def WaitForPicoPath(mcuType, timeout=30):
        """@brief Wait for the path to exist when a RPi Pico W flash is mounted.
           @param mcuType The expected MCU type.
           @return The pico path found or an Exception is thrown if a timeout occurs."""
        picoPathFound = None
        picoPaths = USBLoader.GetAllPicoPaths()
        found = False
        timeoutTime = time()+timeout
        while not found:
            # Get a list of files in this location.
            try:
                for picoPath in picoPaths:
                    # If this folder exists
                    if os.path.isdir(picoPath):
                        _fileList = os.listdir(picoPath)
                        fileList = [s.lower() for s in _fileList]
                        foundCount = 0
                        for expectedFile in USBLoader.RPI_BOOT_BTN_DWN_FILE_LIST:
                            if expectedFile in fileList:
                                foundCount += 1
                            else:
                                break

                        if foundCount == len(USBLoader.RPI_BOOT_BTN_DWN_FILE_LIST):
                            infoFile = os.path.join(picoPath, USBLoader.INFO_UF2_TXT_FILE)
                            with open(infoFile, 'r') as fd:
                                lines = fd.readlines()
                                brdID = None
                                for line in lines:
                                    line = line.rstrip('\r\n')
                                    if line.startswith('Board-ID:'):
                                        elems = line.split(':')
                                        if len(elems) == 2:
                                            brdID = elems[1].strip()

                                if brdID:
                                    if brdID == USBLoader.PICOW_BRD_ID:
                                        if mcuType != USBLoader.RPI_PICOW_MCU_TYPE:
                                            raise Exception(f'Incorrect MCU type detected (board ID = {brdID}). Please select the correct MCU type.')

                                    elif brdID == USBLoader.PICO2W_BRD_ID:
                                        if mcuType != USBLoader.RPI_PICO2W_MCU_TYPE:
                                            raise Exception(f'Incorrect MCU type detected (board ID = {brdID}). Please select the correct MCU type.')

                                    else:
                                        raise Exception(f"{brdID} is an unsupported Pico board ID")

                                else:
                                    raise Exception(f"Failed to read RPi Pico board ID from {infoFile}")


                            found = 1
                            picoPathFound = picoPath

                    if not found and time() > timeoutTime:
                        raise Exception(f"{timeout} timeout waiting for {" or ".join(picoPaths)} path to be found.")

            except PermissionError:
                # As the drive mounts we may get this error for a short while
                pass

            if not picoPathFound:
                # If we have not fund the path don't spinlock.
                sleep(0.25)

        return picoPathFound

    def __init__(self, mcuType, uio=None):
        """@brief Constructor.
           @param mcuType Defines the type of MCU connected."""
        super().__init__(mcuType, uio=uio)
        self._mcuType = mcuType
        self._checkArgs()
        self._picoPathTimeout = 45
        self._serialPort = None

    def setSerialPort(self, serialPort):
        """@brief Set the serial port to use.
           @param serialPort hte serial port device to use."""
        self._serialPort = serialPort

    def _getSerialPort(self):
        """@brief Get the serial port connected to the MCU."""
        if self._serialPort is None:
            self._serialPort = self.waitForFirstAvailableSerialPort()
        return self._serialPort

    def setPicoPathTimeout(self, picoPathTimeout):
        """@brief Set the timeout period to wait for the Pico path/drive to appear.
           @param timeoutSeconds The timeout period while waiting for the Pico drive path to appear."""
        self._picoPathTimeout = picoPathTimeout

    def _checkArgs(self):
        """@brief Check the arguments are valid."""
        if self._mcuType not in USBLoader.VALID_MCU_TYPES:
            raise Exception(f"{self._mcuType} is an invalid MCU type. Valid MCU types = {",".join(USBLoader.VALID_MCU_TYPES)}")

    def install(self, eraseMCUFlash,
                      loadMicroPython,
                      loadApp,
                      appRootFolder,
                      loadMpyInput,
                      showInitialPrompt=True):
        """@brief Install MicroPython onto the MCU.
           @param eraseMCUFlash If True erase the MCU flash.
           @param loadMicroPython If True erase load MicroPython to the MCU flash.
           @param loadApp If True load the App to the MCU flash.
           @param appRootFolder The root folder of the MCU app.
           @param loadMpyInput If True load (*.mpy) files to MCU flash. If False load *.py files to MCU flash.
           @param showInitialPrompt If True prompt the user to hold down the button and then power up a PCIO MCU.
           @param serialPort The serial port to which the MCU is connected.
                             If only one serial port present on the machine then serialPort does not need to be set as the serial port found is be used.
                             If more than one serial port is found then the serial port must be set.
           @return If the MCU app is loaded return a tuple containing
                   0 = Total Space in bytes.
                   1 = Free space in bytes.
                   If MCU App is not loaded then None is returned.
           """
        if not eraseMCUFlash and not loadMicroPython and not loadApp:
            raise Exception("No install action selected.")
        fsStats = None
        if USBLoader.IsPicoW(self._mcuType):
            self.initTime()
            if eraseMCUFlash:
                startT1 = time()
                self.copyToPicoFlash(USBLoader.ERASE_PCIO_FLASH, showInitialPrompt=showInitialPrompt)
                sleep(1)
                elapseSeconds = time()-startT1
                self.info(f"Took {elapseSeconds:.1f} seconds to erase flash.")
            if loadMicroPython:
                startT2 = time()
                self.copyToPicoFlash(USBLoader.LOAD_MICROPYTHON_TO_PICO_FLASH, showInitialPrompt=False)
                elapseSeconds = time()-startT2
                self.info(f"Took {elapseSeconds:.1f} seconds to load MicroPython.")
            if loadApp:
                startT3 = time()
                fsStats = self._loadMCUApp(appRootFolder, loadMpyInput)
                elapseSeconds = time()-startT3
                self.info(f"Took {elapseSeconds:.1f} seconds to load App.")
            self.info(f"Took {self.getElapsedSeconds():.1f} seconds in total.")

        elif  USBLoader.IsEsp32(self._mcuType):
            self.initTime()
            if eraseMCUFlash:
                startT1 = time()
                self.eraseESP32Flash()
                elapseSeconds = time()-startT1
                self.info(f"Took {elapseSeconds:.1f} seconds to erase flash.")
            if loadMicroPython:
                startT2 = time()
                self.loadESP32()
                elapseSeconds = time()-startT2
                self.info(f"Took {elapseSeconds:.1f} seconds to load MicroPython.")
            if loadApp:
                startT3 = time()
                fsStats = self._loadMCUApp(appRootFolder, loadMpyInput)
                elapseSeconds = time()-startT3
                self.info(f"Took {elapseSeconds:.1f} seconds to load App.")
            self.info(f"Took {self.getElapsedSeconds():.1f} seconds in total.")

        # Be a bit defensive, we should never get here.
        else:
            raise Exception(f"{self._mcuType} is an invalid MCU type. Valid MCU types = {",".join(USBLoader.VALID_MCU_TYPES)}")
        return fsStats

    def _getPicoPath(self):
        """@brief Get the path of the RPi Pico W device. The method will block until the path to the RPi pico W.
           @return The path on this machine where RPi Pico W images can be copied to load them into flash."""
        picoPath = None
        timeoutT = time()+self._picoPathTimeout
        # Wait for the drive mounted from the RPi over the serial interface.
        while not picoPath:
            picoPath = USBLoader.WaitForPicoPath(self._mcuType)
            if picoPath:
                break
            if time() >= timeoutT:
                raise Exception(f"{self._picoPathTimeout} second timeout waiting for RPi Pico drive to mount.")

            # Sleep between checks of the drive so we don't spin lock
            sleep(0.1)

        return picoPath

    # We retry this method as it has been found that sometimes the copy fails
    @retry(Exception, tries=3, delay=1)
    def copyToPicoFlash(self, fileType, showInitialPrompt=True):
        """@brief Erase flash on the Pico MCU.
           @param fileType The type of file (either ERASE_PCIO_FLASH or LOAD_MICROPYTHON_TO_PICO_FLASH) to copy to the Pico flash
           @param showInitialPrompt If True show the initial user prompt instructing the user to hold down the Pico SW and power up the MCU."""
        if showInitialPrompt:
            self.info("The RPi Pico must be connected to a USB port on this machine.")
            self.info(f"Checking for a mounted {self._mcu} drive...")
            self.info(f"Hold the button down on the {self._mcuType} and then power it up.")
        sourcePath = None
        if self._mcuType == LoaderBase.RPI_PICOW_MCU_TYPE:
            if fileType == USBLoader.ERASE_PCIO_FLASH:
                sourcePath = USBLoader.GetErasePicoFile()

            elif fileType == USBLoader.LOAD_MICROPYTHON_TO_PICO_FLASH:
                sourcePath = USBLoader.GetPicoMicroPythonFile()

        elif self._mcuType == LoaderBase.RPI_PICO2W_MCU_TYPE:
            if fileType == USBLoader.ERASE_PCIO_FLASH:
                sourcePath = USBLoader.GetErasePico2WFile()

            elif fileType == USBLoader.LOAD_MICROPYTHON_TO_PICO_FLASH:
                sourcePath = USBLoader.GetPico2WMicroPythonFile()

        else:
            raise Exception(f"{self._mcuType} is an unknown MCU type.")

        if sourcePath is None:
            raise Exception(f"BUG: fileType is invalid: {fileType} for {self._mcuType} MCU.")

        picoPath = self._getPicoPath()
        # We don't get here unless the pico path exists
        destinationPath = picoPath

        if showInitialPrompt:
            self.info("")
            self.info("You may now release the button.")
            self.info("")

        self.info(f"Waiting for {picoPath} to mount...")
        while True:
            if os.path.isdir(picoPath):
                self.info(f'{picoPath} is mounted.')
                break
        # We wait a short while before copying to the drive after it mounted.
        sleep(0.5)

        self.info(f"Copying {sourcePath} to {destinationPath}")
        shutil.copy(sourcePath, destinationPath)

        picoPath = self._getPicoPath()

        if fileType == USBLoader.ERASE_PCIO_FLASH:
            self.info("Erased the RPi Pico flash.")
            while True:
                if not os.path.isdir(picoPath):
                    self.info(f'{self._mcuType} restarted after erasing the flash memory.')
                    break

        else:
            self.info("Copied the MicroPython image file to the RPi Pico flash.")

        self.info(f"Waiting for {picoPath} to unmount...")
        while True:
            if not os.path.isdir(picoPath):
                self.info(f'{picoPath} is unmounted.')
                break

        sleep(0.5)

    def _run_esptool_capture(self, args):
        """@brief run the esptool to execute command/s on attached esp32 devices.
           @param args The argument list for the esptool command."""
        error = True
        try:
            self.debug(f"EXECUTING: {str(args)}")
            # Save original argv to restore later
            original_argv = sys.argv
            sys.argv = args
            # Capture output
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            sys_stdout = sys.stdout
            sys_stderr = sys.stderr
            sys.stdout = stdout_buffer
            sys.stderr = stderr_buffer

            try:
                esptool._main()
                error = False

            except SystemExit:
                # Normal esptool._main() execution gets us here.
                error = False

            except Exception:
                pass

            finally:
                # Restore org stderr and stdout
                sys.stderr = sys_stderr
                sys.stdout = sys_stdout
            stderr_str = stderr_buffer.getvalue()
            stdout_str = stdout_buffer.getvalue()
            # Combine stdout and stderr
            response = stdout_str + "\n" + stderr_str
            self.debug(f"RESPONSE: {response}")
            if error:
                raise Exception(f"Command Execution Failed: {" ".join((args))}")
            return response

        finally:
            sys.argv = original_argv  # Restore original argv

    def _get_esp32_type(self):
        """@brief Get the esp32 argument for the esptool command."""
        sp = self._getSerialPort()
        # Dummy first argument, esptool
        args = [
            'esptool',
            '-p',
            f'{sp}',
            'chip_id'
        ]
        response = self._run_esptool_capture(args)
        lines = response.split("\n")
        esp_type = None
        for line in lines:
            if line.startswith(USBLoader.ESPTOOL_DETECTING_CHIP_TYPE):
                self.info(line)
                esp_type = line[len(USBLoader.ESPTOOL_DETECTING_CHIP_TYPE):]
                esp_type = esp_type.rstrip("\r\n")
                esp_type = esp_type.strip(" \t")
                esp_type = esp_type.replace("-", "")
                esp_type = esp_type.lower()
                if esp_type in USBLoader.VALID_ESP32_TYPES:
                    break

        if esp_type is None:
            raise Exception("Failed to determine ESP32 type.")

        # Check the correct type of MCU is connected.
        self._checkMCUCorrect(line, checkIDLine=True)

        return esp_type

    def eraseESP32Flash(self, showInitialPrompt=True):
        """@brief Erase the ESP32 flash.
           @param showInitialPrompt If True show the initial user prompt instructing the user to hold down the Pico SW and power up the MCU."""
        if showInitialPrompt:
            self.info("Hold the non esp32 reset button down while releasing the reset button")
        sp = self._getSerialPort()
        esp32_type = self._get_esp32_type()
        self.info("Erasing esp32 flash memory...")
        args = [
            'esptool', '--chip', f'{esp32_type}', '-p', f'{sp}', 'erase_flash'
        ]
        self._run_esptool_capture(args)
        self.info("Flash erase complete.")

    def loadESP32(self):
        """@brief Load MicroPython onto an esp32 MCU."""
        self.info("Loading MicroPython onto an esp32 MCU.")
        serialPortDevice = self._getSerialPort()
        esp32_type = self._get_esp32_type()
        if esp32_type == USBLoader.ESP32C3_MCU_TYPE:
            bootloader_file, partitiontable_file, micropython_file = USBLoader.GetESP32C3MicroPythonFiles()
            # Dummy first argument, esptool
            args = ['esptool',
                    '--chip', 'esp32c3',
                    '-p', f'{serialPortDevice}',
                    '-b', '460800',
                    '--before', 'default_reset',
                    '--after', 'hard_reset',
                    'write_flash',
                    '--flash_mode', 'dio',
                    '--flash_freq', '80m',
                    '--flash_size', '4MB',
                    '0x0', f'{bootloader_file}',
                    '0x8000', f'{partitiontable_file}',
                    '0x10000', f'{micropython_file}']

        elif esp32_type == USBLoader.ESP32C6_MCU_TYPE:
            bootloader_file, partitiontable_file, micropython_file = USBLoader.GetESP32C6MicroPythonFiles()
            # Dummy first argument, esptool
            args = ['esptool',
                    '--chip', 'esp32c6',
                    '-p', f'{serialPortDevice}',
                    '-b', '460800',
                    '--before', 'default_reset',
                    '--after', 'hard_reset',
                    'write_flash',
                    '--flash_mode', 'dio',
                    '--flash_freq', '80m',
                    '--flash_size', '4MB',
                    '0x0', f'{bootloader_file}',
                    '0x8000', f'{partitiontable_file}',
                    '0x10000', f'{micropython_file}']

        else:
            microPythonImageFile = USBLoader.GetESP32MicroPythonFile()
            # Dummy first argument, esptool
            args = ['esptool.py',
                    '-p', f'{serialPortDevice}',
                    'write_flash', '0x1000',
                    f'{microPythonImageFile}'
            ]

        self._run_esptool_capture(args)

        self.info("Loaded MicroPython.")

    def _loadMCUApp(self, appPath, loadMPYFiles):
        """@brief Load the App onto the MCU.
           @param appPath The root path of the MCU app.
           @param loadMPYFiles If True (default) we compile the .py files to .mpy files and
                               load these. This saves significant MCU flash memory space.
                               If False then the python files are loaded.
           @return A tuple containing
                   0 = Total Space in bytes.
                   1 = Free space in bytes."""
        if appPath is None or len(appPath) == 0:
            raise Exception("No main.py has been set. This is needed to load the program onto the MCU.")
        # This will clean all the files including all config from the MCU flash memory
        mcuLoader = MCULoader(self._uio, self._mcuType, appPath)
        vfsStats = mcuLoader.load(loadMPYFiles=loadMPYFiles)
        self.info(f"Loaded App to MCU ({self._mcuType})")
        return vfsStats

    def resetEsp32(self):
        """@brief Perform a reset on an ESP32 device.
                  The ESP32 MCU reset is connected to the RTs control signal. We use this to assert the reset and release it.
                  The serial port connected to an ESP32 device must be connected and openFirstSerialPort() must have been
                  called prior to calling this method leaving the serial port open."""
        USBLoader.ResetESP32(self._uio, self._ser)

    def viewSerialOut(self):
        """@brief View serial port output. This is useful on a RPi Pico W as when the Pico
         is reset the serial port is lost. This will show the output as the port re appears.
                  This is useful when debugging Pico W firmware issues."""
        running = True
        while running:
            self._ser = self.openFirstSerialPort()
            try:
                try:
                    while running:
                        bytesRead = self._ser.read_until()
                        sRead = bytesRead.decode("utf-8", errors="ignore")
                        sRead = sRead.rstrip('\r\n')
                        if len(sRead) > 0:
                            self.info(sRead)

                except KeyboardInterrupt:
                    running = False
                except:
                    sleep(0.1)

            finally:
                self._closeSerialPort()

    def _isEsp32Connected(self, line):
        """@brief Determine if an esp32 (any type) is connected.
           @param line The line of text returned from _checkMicroPython().
           @return True if an esp32 is connected."""
        esp32 = False
        if line.find('ESP32') != -1:
            esp32 = True
        return esp32

    def setupWiFi(self, ssid, password):
        """@brief Update the WiFi config on the MCU device using the USB port to ensure it will connect to the wiFi
                  network when the software is started.
           @param ssid The Wifi SSID/network.
           @param password The WiFi password.
           @return the configured SSID"""
        try:
            # Attempt to connect to the board under test python prompt
            mpLine = self._checkMicroPython(closeSerialPort=False)
            esp32 = self._isEsp32Connected(mpLine)
            thisMachineFileContents = LoaderBase.REPLGetFileContents(self._ser, LoaderBase.MACHINE_CONFIG_FILE)
            if thisMachineFileContents is None or thisMachineFileContents == '>>> ':
                raise Exception(f"The MCU device does not have a {LoaderBase.MACHINE_CONFIG_FILE} file. This should be created when the MCU boots the first time running example Project 3 or later.")
            thisMachineDict = json.loads(thisMachineFileContents)
            orgConfigStr = json.dumps(thisMachineDict, indent=4)
            self.debug(f"ORG CONFIG: <{orgConfigStr}>")
            # Set the house WiFi configuration in the machine config dict
            # WiFi key is -2 for Ydev devices
            thisMachineDict[USBLoader.WIFI_KEY] = self._getWiFiDict(ssid, password)
            newConfigStr = json.dumps(thisMachineDict, indent=4)
            self.debug(f"NEW CONFIG: <{newConfigStr}>")
            # Ensure bluetooth is turned off now we have configured the WiFi.
            # bluetooth enabled key is -1 for Ydev devices
            thisMachineDict["-1"] = 1
            # The machine config file sitting the the local temp folder.
            localMachineCfgFile = os.path.join(self._tempFolder, LoaderBase.MACHINE_CONFIG_FILE)
            LoaderBase.SaveDictToJSONFile(thisMachineDict, localMachineCfgFile, uio=self._uio)

        finally:
            self._closeSerialPort()
        localMachineCfgFile = USBLoader.GetRShellPath(localMachineCfgFile)
        # Copy the machine config file back to the MCU flash
        self._runRShell((f'cp "{localMachineCfgFile}" /pyboard/',) )
        return self._runApp(esp32)

    def _runApp(self, esp32, waitForIPAddress=True, timeoutSec=60):
        """@brief Run the firmware on the MCU.
           @param esp32 True if any type of esp32 is connected.
           @param waitForIPAddress If True wait for an IP address to be allocated to the unit.
           @return The IP address that the MCU obtains when registered on the WiFi if waitForIPAddress == True or None if not."""
        ipAddress = None
        self.info("Running App on the MCU device. Waiting for WiFi connection...")
        timeoutT = time()+timeoutSec
        try:
            try:
                self.rebootUnit(esp32HWReboot=esp32)

                self.openFirstSerialPort()

                while True:
                    availableByteCount = self._ser.in_waiting
                    if availableByteCount == 0:
                        sleep(0.05)
                        if time() >= timeoutT:
                            raise Exception(f"{timeoutSec} second timeout waiting to connect to WiFi network.")
                        continue
                    data = self._ser.read(availableByteCount)
                    if len(data) > 0:
                        data=data.decode("utf-8", errors="ignore")
                        if len(data) > 0:
                            lines = data.split("\n")
                            for line in lines:
                                line=line.rstrip("\r\n")
                                self.debug(line)

                        if waitForIPAddress:
                            pos = data.find("IP Address=")
                            if pos != -1:
                                elems = data.split("=")
                                if len(elems) > 0:
                                    ipAddress = elems[-1].rstrip("\r\n")
                                    self.info(f"MCU IP address = {ipAddress}")
                                    break

                        else:
                            # Wait for the app to get to a running state.
                            # It will get to this state regardless of whether the Wifi is configured.
                            pos = data.find("Activating WiFi")
                            if pos != -1:
                                break

            except serial.SerialException:
                self.debug(f"SerialException: {traceback.format_exc()}")

            except OSError:
                self.debug(f"SerialException: {traceback.format_exc()}")

        finally:
            self._closeSerialPort()

        return ipAddress


class MCULoader(LoaderBase):
    """@brief Responsible for converting .py files in app1 and app1/lib
              to .mpy files and loading them onto the MCU."""
    DEL_ALL_FILES_CMD_LIST = ["rm -r /pyboard/*"]
    MCU_MP_CACHE_FOLDER = "mcu_app.cache"
    RSHELL_CMD_LIST_FILE = os.path.join( MCUBase.GetTempFolder(), f"cmd_list_{str( int(random()*1E6) )}.cmd")

    @staticmethod
    def GetAppRootPath(appRootFolder):
        """@brief Get the app root path.
           @param appRootFolder This may be the app root folder or the main.py file in the app root folder.
           @return The app root path. This is the location where the main.py file sits."""
        if os.path.isdir(appRootFolder):
            mainFile = os.path.join(appRootFolder, LoaderBase.MAIN_PYTHON_FILE)
            if not os.path.isfile(mainFile):
                raise Exception(f"{mainFile} file not found.")
        else:
            # If appRootFolder points to the main.py python file
            if appRootFolder.endswith(LoaderBase.MAIN_PYTHON_FILE) and os.path.isfile(appRootFolder):
                # Get the dir it's sitting in
                appRootFolder = os.path.dirname(appRootFolder)
            else:
                raise Exception(f"{appRootFolder} file not found.")
        return appRootFolder

    def __init__(self, uio, mcu, appRootFolder):
        """@brief Constructor
           @param uio A UIO instance handling user input and output (E.G stdin/stdout or a GUI)
           @param mcu The MCU type. Either 'picow' or 'esp32'. esp32 is not supported on the MCU HW.
                      However this class supports loading code onto an esp32.
           @param appRootFolder This may be the app root folder or the main.py file in the app root folder."""
        super().__init__(mcu, uio=uio)
        appRootFolder = MCULoader.GetAppRootPath(appRootFolder)
        self._appRootFolder = appRootFolder
        self._check_for_main()
        if mcu not in USBLoader.VALID_MCU_TYPES:
            raise Exception(f"{mcu} is an unsupported MCU ({','.join(USBLoader.VALID_MCU_TYPES)} are valid).")
        self._mcu = mcu

    def _check_for_main(self):
        """@brief Check for the main.py file in the appRootFolder folder."""
        if os.path.isdir(self._appRootFolder):
            main_file = os.path.join(self._appRootFolder, 'main.py')
            if not os.path.isfile(main_file):
                raise Exception(f'{main_file} file not found.')

        else:
            raise Exception(f'{self._appRootFolder} folder not found.')

    def _getFolderList(self, fileList):
        """@param fileList A list of local files to be loaded to the MCU flash.
           @return Get a list of folders to be created on the MCU flash."""
        folderList=[]
        for _file in fileList:
            folder=os.path.dirname(_file)
            folder = folder.replace(self._appRootFolder, "")
            folder=folder.strip()
            if folder not in folderList:
                if len(folder) > 0:
                    folderList.append(folder)
        app1FolderList = copy(folderList)
        for _folder in app1FolderList:
            if _folder.find('/app1') != -1:
                folderList.append(_folder.replace('/app1', '/app2'))
        # The folder list will be created on the MCU and must have / rather
        # than \ separator chars.
        finalFolderList = []
        for folder in folderList:
            finalFolderList.append(folder.replace("\\", "/"))
        return finalFolderList

    def _getMakeFolderCmdList(self, fileList):
        """@param fileList A list of local files to be loaded to the MCU flash.
           @return A list of commands to create the required folders in the MCU flash."""
        cmdList = []
        folderList = self._getFolderList(fileList)
        # Sort folders shortest to longest as rshell does not have a mkdirs command
        # to create folder if parent does not exist.
        folderList = sorted(folderList, key=len)
        for folder in folderList:
            cmdList.append(f"mkdir /pyboard{folder}")
        return cmdList

    def _loadFiles(self, fileList, port):
        """@brief Load files onto the micro controller device.
           @param fileList The list of files to load.
           @param port The serial port to use."""
        cmdList = self._getMakeFolderCmdList(fileList)
        totalSizeAllFiles = 0
        srcFileList = []
        for srcFile in fileList:
            destFile = "/pyboard" + srcFile
            # rshell uses / as the file separator characters regardless of the platform its running on.
            # Therefore replace \ characters with / characters (needed on a Windows platforms).
            srcFile = USBLoader.GetRShellPath(srcFile)
            destFile = USBLoader.GetRShellPath(destFile)
            # The dest path must use / path separator chars rather than
            # \ chars which will be present if running on a windows platform.
            rootPath = self._appRootFolder.replace("\\", "/")
            # Remove the local app root from the dest path
            destFile = destFile.replace(rootPath, "")
            srcFileList.append(srcFile)
            cpCmd = f'cp "{srcFile}" {destFile}'
            cmdList.append(cpCmd)
            fSize = os.path.getsize(srcFile)
            self.info(f"Loading {srcFile} to {destFile} (size={fSize} bytes).")
            totalSizeAllFiles += fSize

        fd = open(MCULoader.RSHELL_CMD_LIST_FILE, 'w')
        for l in cmdList:
            fd.write("{}\n".format(l))
        fd.close()
        self.info(f"Size of all files to be loaded = {totalSizeAllFiles} bytes.")
        self.info("Loading MCU firmware. This may take several minutes...")
        cmdOutput = self._runRshellCmdFile(port, MCULoader.RSHELL_CMD_LIST_FILE)
        lines = cmdOutput.split("\n")
        for l in lines:
            self.debug(l)
        for _file in srcFileList:
            if cmdOutput.find(_file) == -1:
                raise Exception(f"Failed to load the {_file} file onto the MCU device.")
        self.info(f"Loaded all {len(fileList)} files.")
        return totalSizeAllFiles

    def _deleteAllMCUFiles(self, port):
        """@brief Delete all files from the MCU device.
           @param port The serial port to use."""
        self.info("Deleting all files from MCU flash...")
        cmdList = MCULoader.DEL_ALL_FILES_CMD_LIST
        fd = open(MCULoader.RSHELL_CMD_LIST_FILE, 'w')
        for l in cmdList:
            fd.write("{}\n".format(l))
        fd.close()
        # If no files are present to be deleted this command will fail, hence allowFailure=True.
        self._runRshellCmdFile(port, MCULoader.RSHELL_CMD_LIST_FILE, allowFailure=True)
        self.info("Deleted all files from MCU flash.")

    def load(self, loadMPYFiles=True):
        """@brief Load the python code onto the micro controller device.
           @param loadMPYFiles If True (default) we compile the .py files to .mpy files and
                               load these. This saves significant MCU flash memory space.
                               If False then the python files are loaded.
           @return A tuple containing
                   0 = Total Space in bytes.
                   1 = Free space in bytes."""
        self.checkMCUCode()

        # An esp32 may be locked up waiting for a bootloader due to previous control signal states or button presses
        # so we reset it at the start of the load process to attempt to ensure it's running normally.
        if self._mcu in USBLoader.VALID_ESP32_TYPES:
            self.esp32HWReset()

        self._checkMicroPython(checkMCUCorrect=True)
        self.deleteLocalMPYFiles()
        # Delete all files from the MCU device
        self._deleteAllMCUFiles(self._serialPort)

        # We now need to reboot the device in order to ensure the WDT is disabled
        # as there is no way to disable the WDT once enabled and the WDT runs
        # on a MCU device. We don't want the WDT firing part way through the installation
        # process.
        self.rebootUnit()

        # Regain the python prompt from the MCU unit.
        self._checkMicroPython(closeSerialPort=False)
        self.info("Reading MCU flash stats")
        fsStats = LoaderBase.REPLGetFlashStats(self._ser)
        self.info("Read MCU flash stats")
        self._closeSerialPort()

        filesToLoad = self.getAppFileList(loadMPYFiles)
        sizeOfAllLoadedFiles = self._loadFiles(filesToLoad, self._serialPort)
        self.deleteLocalMPYFiles()
        # Reduce the free space by the total size of the files loaded.
        freeSpace = fsStats[1]
        fsStats[1] = freeSpace - sizeOfAllLoadedFiles
        self.rebootUnit(esp32HWReboot=True)
        return fsStats

class UpgradeManager(LoaderBase):
    """@brief Responsible for upgrading the MCU App over a WiFi network."""

    DEVICE_REST_INTERFACE_TCP_PORT  = 80
    ERASE_OFFLINE_APP               = "/erase_offline_app"
    GET_SYS_STATS                   = "/get_sys_stats"
    GET_INACTIVE_APP_FOLDER         = "/get_inactive_app_folder"
    GET_ACTIVE_APP_FOLDER           = "/get_active_app_folder"
    SWAP_ACTIVE_APP                 = "/swap_active_app"
    REBOOT_DEVICE                   = "/reboot"
    GET_SHA256                      = "/sha256"
    RESET_WIFI_CONFIG               = "/reset_wifi_config"

    DISK_TOTAL_BYTES                = "DISK_TOTAL_BYTES"
    DISK_USED_BYTES                 = "DISK_USED_BYTES"
    INACTIVE_APP_FOLDER_KEY         = "INACTIVE_APP_FOLDER"
    ACTIVE_APP_FOLDER_KEY           = "ACTIVE_APP_FOLDER"

    SHA256                          = "SHA256"
    MAX_CHUNK_SIZE                  = 4096 # This is limited by the ram available while transferring files.

    def __init__(self, mcu, uio=None):
        """@brief Constructor.
           @param mcu Either esp32 or pico
           @param uio A UIO instance."""
        super().__init__(mcu, uio=uio)
        self._appRootFolder      = None
        self._orgActiveAppFolder = None

    def _getSize(self, loadMpyFiles, byteCount=0):
        """@brief Get the size of all the files in and below the folder.
           @param loadMpyFiles True if loading .mpy rather than .py files to the MCU.
           @param byteCount The running byte count."""
        entries = self.getAppFileList(loadMpyFiles)
        for entry in entries:
            if os.path.isfile(entry):
                fileSize = os.path.getsize(entry)
                byteCount += fileSize

        return byteCount

    def _runCommand(self, address, cmd, returnDict = False):
        """@brief send a command to the device and get response.
           @param address The address of the MCU to upgrade.
           @param cmd The REST cmd to execute.
           @return A requests instance."""
        url = 'http://{}:{}{}'.format(address, UpgradeManager.DEVICE_REST_INTERFACE_TCP_PORT, cmd)
        self.debug(f"CMD: {url}")
        if returnDict:
            obj = requests.get(url).json()
            self.debug(f"CMD RESPONSE: { str(obj) }")
            if isinstance(obj, dict):
                return obj
            else:
                raise Exception("'{}' failed to return a dict.".format(cmd))
        else:
            return requests.get(url)

    def _checkDiskSpace(self, address, appSize):
        """@brief Check that there is sufficient space to store the new app. This should
                  take a maximum of 1/2 the available disk space so that there is space
                  for the same size app in the other app path (/app1 or /app2).
           @param address The address of the MCU to upgrade.
           @param appSize The size of all the files in the app to be loaded."""
        url = 'http://{}:{}{}'.format(address, UpgradeManager.DEVICE_REST_INTERFACE_TCP_PORT, UpgradeManager.GET_SYS_STATS)
        self.debug(f"CMD: {url}")
        r = requests.get(url)
        obj = r.json()
        self.debug(f"CMD RESPONSE: { str(obj) }")
        if isinstance(obj, dict):
             if UpgradeManager.DISK_TOTAL_BYTES in obj and UpgradeManager.DISK_USED_BYTES in obj:
                diskSize = obj[UpgradeManager.DISK_TOTAL_BYTES]
                used = obj[UpgradeManager.DISK_USED_BYTES]
                free = diskSize - used
                # App should not take more than 1/2 the available space so that we always have the ability
                # to upgrade.
                maxAppSize = int(diskSize/2)
                if appSize > maxAppSize:
                    raise Exception(f"The app is too large ({appSize} bytes, max {maxAppSize} bytes).")
                if appSize > free:
                    raise Exception(f"The app is too large ({appSize} bytes. There is only {free} bytes free).")
                self.info("App size (MB):        {}".format(appSize/1E6))
                self.info("Max app size (MB):    {}".format(maxAppSize/1E6))

        else:
            raise Exception("Unable to retrieve the disk space from the device.")

    def _showFreeDiskSpace(self, address):
        """@brief Show the current free disk space.
           @param address The address of the MCU to upgrade."""
        url = 'http://{}:{}{}'.format(address, UpgradeManager.DEVICE_REST_INTERFACE_TCP_PORT, UpgradeManager.GET_SYS_STATS)
        self.debug(f"CMD: {url}")
        r = requests.get(url)
        obj = r.json()
        self.debug(f"CMD RESPONSE: { str(obj) }")
        if isinstance(obj, dict):
            if UpgradeManager.DISK_TOTAL_BYTES in obj and UpgradeManager.DISK_USED_BYTES in obj:
                diskSize = obj[UpgradeManager.DISK_TOTAL_BYTES]/1E6
                used = obj[UpgradeManager.DISK_USED_BYTES]/1E6
                percentageLeft = ((1-(used/diskSize))*100.0)
                self.info(f"Flash size (MB):  {diskSize}")
                self.info(f"Used (MB):        {used}")
                self.info(f"% space left:     {percentageLeft:.1f}")

        else:
            raise Exception("Unable to retrieve the disk space from the device.")

    def _getSHA256(self, address, _file):
        """@Brief Get the sha256 hash of a file on the MCU.
           @param address The address of the MCU to upgrade.
           @param _file The file ni the MCU file system.
           @return The SHA256 string or None ."""
        url = 'http://{}:{}{}?file={}'.format(address, UpgradeManager.DEVICE_REST_INTERFACE_TCP_PORT, UpgradeManager.GET_SHA256, _file)
        self.debug(f"CMD: {url}")
        r = requests.get(url)
        obj = r.json()
        self.debug(f"CMD RESPONSE: { str(obj) }")
        sha256 = None
        if isinstance(obj, dict):
            if UpgradeManager.SHA256 in obj:
                sha256 = obj[UpgradeManager.SHA256]
        return sha256

    @retry(Exception, tries=3, delay=1)
    def _sendFileOverWiFi(self, address, localFile, destPath):
        """@brief Send a file to the device.
           @param address The IP address of the CT6 device.
           @param localFile The local file to be sent.
           @param destPath The path on the device to save the file into.
           @return The file size in bytes."""
        #If on a windows platform then we need to correct the destination file path
        if self._windowsPlatform and destPath.find("\\"):
            destPath=destPath.replace('\\','/')

        if not os.path.isfile(localFile):
            raise Exception(f"Local file not found: {localFile}")

        fSize = os.path.getsize(localFile)

        # Calc hash of local file for checking later
        with open(localFile, 'rb') as fd:
            encodedData = fd.read()
            localSHA256 = hashlib.sha256(encodedData).hexdigest()

        fileName = os.path.basename(localFile)
        destFile = os.path.join(destPath, fileName)

        self.debug(f"Sending {localFile} to {address}:{destFile} (size={fSize} bytes).")
        url = f"http://{address}:80/upload"

        with open(localFile, 'rb') as f:
            first = True
            if fSize == 0:
                headers = {'X-File-Name': destFile,
                           'X-Start': '1' if first else '0'}
                # Send an empty file, E.G __init__.py
                requests.post(url, data=b'', headers=headers)

            else:
                while chunk := f.read(UpgradeManager.MAX_CHUNK_SIZE):
                    headers = {'X-File-Name': destFile,
                               'X-Start': '1' if first else '0'}
                    response = requests.post(url, data=chunk, headers=headers)
                    if response.status_code != 200:
                        # We rely on the sha256 for checking file integrity so don't need to report error here.
                        break
                    first = False

        # Check that the sha256 hash of the local and remote files match.
        remoteSHA256 = self._getSHA256(address, destFile)
        if localSHA256 != remoteSHA256:
            raise Exception(f"{localFile}: Remote file SHA256 mismatch.")

        return fSize

    def sendFile(self, address, localFile, destPath):
        """@brief Send a file to the device.
           @param address The address of the MCU on the wiFi network.
           @param localFile The local file to be sent.
           @param destPath The path on the device to save the file into.
           @return The file size in bytes."""

        if not os.path.isfile(localFile):
            raise Exception("{} file not found.".format(localFile))

        if destPath is None or len(destPath) == 0:
            raise Exception("Send path not defined.")

        fSize = self._sendFileOverWiFi(address, localFile, destPath)
        self.info(f"Sent {localFile} to {address}:{destPath} (size={fSize} bytes)")
        return fSize

    def _sendFilesToInactiveAppFolder(self, address, loadMpyFiles):
        """@brief Send all the files in the app folder to the remote device.
           @param address The address of the MCU on the wiFi network.
           @param loadMpyFiles If True then .mpy files are loaded to the MCU.
                               If False then .py files are loaded to the MCU which will take up more flash space."""
        responseDict = self._runCommand(address, UpgradeManager.GET_INACTIVE_APP_FOLDER, returnDict=True)
        if UpgradeManager.INACTIVE_APP_FOLDER_KEY in responseDict:
            inactiveAppFolder = responseDict[UpgradeManager.INACTIVE_APP_FOLDER_KEY]
            self.info("Inactive App Folder: {}".format(inactiveAppFolder))
            localAppFolder = self._appRootFolder
            fileList = self.getAppFileList(loadMpyFiles)
            totalBytes = 0
            for localFile in fileList:
                # Ignore any *.pyc files
                if localFile.endswith(".pyc"):
                    continue
                # Final check to ensure the local file exists.
                if os.path.isfile(localFile):
                    destPath = localFile.replace(localAppFolder, "")
                    destPath = os.path.dirname(destPath)
                    # The the path includes the src /app1 folder
                    if len(destPath) >=4:
                        # Replace it with the inactive app folder.
                        destPath = inactiveAppFolder + destPath[5:]
                    fSize = self.sendFile(address, localFile, destPath)
                    totalBytes += fSize

            self.info(f"Total size of all files loaded to the MCU: {totalBytes} bytes.")
            self._checkDiskSpace(address, totalBytes)
        else:
            raise Exception("Failed to determine the devices inactive app folder.")

    def _switchActiveAppFolder(self, address):
        """@brief Switch the active app, /app1 -> /app2 or /app2 -> /app1 depending upon
                  which is the currently active app.
           @param address The address of the MCU on the wiFi network."""
        beforeDict = self._runCommand(address, UpgradeManager.GET_ACTIVE_APP_FOLDER, returnDict=True)
        self._runCommand(address, UpgradeManager.SWAP_ACTIVE_APP)
        afterDict = self._runCommand(address, UpgradeManager.GET_ACTIVE_APP_FOLDER, returnDict=True)
        if beforeDict[UpgradeManager.ACTIVE_APP_FOLDER_KEY] == afterDict[UpgradeManager.ACTIVE_APP_FOLDER_KEY]:
            raise Exception("Failed to switch active app folder from: {}".format(beforeDict[UpgradeManager.ACTIVE_APP_FOLDER_KEY]))
        self._orgActiveAppFolder = beforeDict[UpgradeManager.ACTIVE_APP_FOLDER_KEY]

    def _reboot(self, address, rebootTimeout=60):
        """@brief Issue a command to reboot the device.
           @param address The address of the MCU on the wiFi network.
           @param rebootTimeout The number of seconds to wait for the device reboot."""
        pingSec = self.doPing(address)
        if pingSec is None:
            raise Exception(f"Unable to reboot the MCU ({address}) as it's not reachable on the LAN.")

        timeoutT = time()+rebootTimeout
        rebootInProgress = True
        while rebootInProgress:
            self.info("Rebooting the device.")
            self._runCommand(address, UpgradeManager.REBOOT_DEVICE, returnDict = True)

            self.info(f"Waiting for the MCU ({address}) to reboot.")
            stopCheckT = time()+5
            while time() < stopCheckT:
                pingSec = self.doPing(address)
                # If we can no longer ping the device then it has rebooted
                if pingSec is None:
                    rebootInProgress = False
                    break
                sleep(0.25)

            if time() >= timeoutT:
                raise Exception(f"{rebootTimeout} second timeout waiting for MCU to reboot.")

        self.info("The MCU has rebooted.")

    def _waitForPingSuccess(self, address, restartTimeout=60, pingHoldSecs = 3):
        """@brief Wait for a reconnect to the WiFi network.
           @param address The address of the MCU on the wiFi network.
           @param restartTimeout The number of seconds before an exception is thrown if the WiFi does not reconnect.
           @param pingHoldSecs The number of seconds of constant pings before we determine the WiFi has reconnected.
                               This is required because the Pico W may ping and then stop pinging before pinging
                               again when reconnecting to the Wifi."""
        startT = time()
        pingRestartTime = None
        self.info("Waiting for the MCU to reconnect to the WiFi network.")
        while True:
            pingSec = self.doPing(address)
            if pingSec is not None:
                if pingRestartTime is None:
                    pingRestartTime = time()

                if time() > pingRestartTime+pingHoldSecs:
                    break

            else:
                pingRestartTime = None

            if time() >= startT+restartTimeout:
                raise Exception(f"Timeout waiting for {address} to become pingable.")

            sleep(0.25)

        self.info(f"{address} ping success.")

    def _checkRunningNewApp(self, address, restartTimeout=120):
        """@brief Check that the upgrade has been successful and the device is running the updated app.
           @param address The address of the MCU on the wiFi network.
           @param restartTimeout The timeout in seconds to check for the new running app."""
        self._waitForPingSuccess(address)

        retDict = self._runCommand(address, UpgradeManager.GET_ACTIVE_APP_FOLDER, returnDict=True)
        activeApp = retDict[UpgradeManager.ACTIVE_APP_FOLDER_KEY]
        if self._orgActiveAppFolder == activeApp:
            raise Exception(f"Failed to run the updated app. Still running from {self._orgActiveAppFolder}.")
        else:
            self.info(f"Upgrade successful. Switched from {self._orgActiveAppFolder} to {activeApp}")

    def upgrade(self, address, appRootPath, loadMpyFiles):
        """@brief Perform an MCU upgrade.
           @param address The address of the MCU on the wiFi network.
           @param appRootPath @param appRootFolder This may be the app root folder or the main.py file in the app root folder.
           @param loadMpyFiles If True then .mpy files are loaded to the MCU.
                               If False then .py files are loaded to the MCU which will take up more flash space."""
        if address is None or len(address) == 0:
            raise Exception("An IP address is required to upgrade a unit.")
        self.info(f"Checking {address} is reachable.")
        pingSec = self.doPing(address)
        if pingSec is None:
            raise Exception(f"{address} is not reachable on the network.")
        startTime = time()
        self._appRootFolder = MCULoader.GetAppRootPath(appRootPath)
        self.checkMCUCode()
        appSize = self._getSize(self._appRootFolder, loadMpyFiles)
        self.info(f"Performing an OTA upgrade of {address}")
        # We need to erase any data in the inactive partition to see if we have space for the new app
        self._runCommand(address, UpgradeManager.ERASE_OFFLINE_APP)
        self._checkDiskSpace(address, appSize)
        self._sendFilesToInactiveAppFolder(address, loadMpyFiles)
        self._switchActiveAppFolder(address)
        elapsedT = time()-startTime
        self.info(f"Took {elapsedT:.1f} seconds to upgrade device.")
        self._reboot(address)
        self._checkRunningNewApp(address)

        if loadMpyFiles:
            # Don't leave the byte code files around.
            # We don't want the deletion messages to appear in the log
            # as they detract from the upgrade success message.
            self.deleteLocalMPYFiles(showMsg=False)

        self._showFreeDiskSpace(address)

    def resetWifiConfig(self, address):
        """@brief Perform an MCU upgrade.
           @param address The address of the MCU on the wiFi network."""
        if not address:
            raise Exception("An IP address is required to reset the WiFi configuration.")

        self.info("Reset MCU WiFi configuration..")
        self._runCommand(address, UpgradeManager.RESET_WIFI_CONFIG, returnDict = True)

        self.info("Rebooting the device.")
        self._runCommand(address, UpgradeManager.REBOOT_DEVICE, returnDict = False)

class YDevScanner(LoaderBase):
    """@brief Responsible for scanning for YDev devices."""
    IP_ADDRESS              = "IP_ADDRESS"
    YDEV_DISCOVERY_PORT     = 2934
    CT6_DISCOVERY_PORT      = 29340

    class AreYouThereThread(Thread):
        """An inner class to send are you there (AYT) messages to devices on the LAN."""

        AreYouThereMessage = "{\"AYT\":\"-!#8[dkG^v's!dRznE}6}8sP9}QoIR#?O&pg)Qra\"}"
        PERIODICITY_SECONDS = 1.0
        MULTICAST_ADDRESS   = "255.255.255.255"

        def __init__(self, sock, port):
            Thread.__init__(self)
            self._running = None
            self.daemon = True

            self._sock = sock
            self._port = port

        def run(self):
            self._running = True
            while self._running:
                self._sock.sendto(YDevScanner.AreYouThereThread.AreYouThereMessage.encode(), (YDevScanner.AreYouThereThread.MULTICAST_ADDRESS, self._port))
                sleep(YDevScanner.AreYouThereThread.PERIODICITY_SECONDS)

        def shutDown(self):
            """@brief Shutdown the are you there thread."""
            self._running = False

    def __init__(self, uio):
        """@brief Constructor
           @param uio A UIO instance handling user input and output (E.G stdin/stdout or a GUI)"""
        super().__init__(LoaderBase.RPI_PICOW_MCU_TYPE, uio=uio)

    def scan(self, callBack=None, runSeconds=None, addressOfInterest=None, port=YDEV_DISCOVERY_PORT):
        """@brief Perform a scan for CT6 devices on the LAN.
           @param callBack If defined then this method will be called passing the dict received from each unit that responds.
           @param runSeconds If defined then this is the number of seconds to scan for.
           @param addressOfInterest The IP address of the device of interest. If set then we only display
                                    responses from this address. If left at None (default) then all responses are shown.
           @port The UDP port to which are you there (SYT) broadcast messages are sent when scanning for devices."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(('', port))

        self.info('Sending AYT messages every second.')
        areYouThereThread = YDevScanner.AreYouThereThread(sock, port)
        areYouThereThread.start()

        self.info("Listening on UDP port %d" % (port) )
        stopTime = None
        if runSeconds:
            stopTime = time() + runSeconds
        running = True
        while running:
            #If we need to stop after a given time period.
            if stopTime and time() >= stopTime:
                areYouThereThread.shutDown()
                areYouThereThread.join()
                sock.close()
                break

            data = sock.recv(65536)
            #Ignore the messaage we sent
            if data != YDevScanner.AreYouThereThread.AreYouThereMessage:
                try:
                    dataStr = data.decode("utf-8", errors="ignore")
                    rx_dict = json.loads(dataStr)
                    # If the user is only interested in one device
                    if addressOfInterest:
                        if YDevScanner.IP_ADDRESS in rx_dict:
                            ipAddress = rx_dict[YDevScanner.IP_ADDRESS]
                            # And this is not the device of interest
                            if addressOfInterest != ipAddress:
                                # Ignore it
                                continue
                    # Ignore the reflected broadcast messages.
                    if 'AYT' in rx_dict:
                        continue

                    self.info(json.dumps(rx_dict, indent=4))

                    # If a callback has been defined
                    if callBack:
                        running = callBack(rx_dict)

                except:
                    pass

