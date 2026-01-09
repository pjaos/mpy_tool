import sys
import os
import platform
import getpass
import tempfile
import serial

from   retry import retry
from   time import time, sleep
from   serial.tools.list_ports import comports

class MCUBase(object):
    """@brief A base class that holds generally used methods.
              In part it implements methods used to display user."""

    @staticmethod
    def IsWindowsPlatform():
        """@return True if running on a Windows machine."""
        return any(platform.win32_ver())

    @staticmethod
    def IsMacOSPlatform():
        """@return True if running on a MacOS machine."""
        macos = False
        _platform = platform.system()
        if _platform == 'Darwin':
            macos = True
        return macos

    @staticmethod
    def GetAssetsFolder():
        """@return The assets folder."""
        # Get currently executing file
        exeFile = sys.argv[0]
        # Get it's path.
        pathname = os.path.dirname(os.path.dirname(exeFile))
        # Get the git_hash.txt file created when build.sh was executed to create the deb file.
        assetsPath = os.path.join(pathname, "assets")
        if not os.path.isdir(assetsPath):
            # Now we check the parent folder for the assets folder as the working dir may be server_lib
            parentAssetsPath = os.path.join("..", "assets")
            if os.path.isdir(parentAssetsPath):
                assetsPath = parentAssetsPath
            else:
                raise Exception(f"{assetsPath} path not found.")

        return assetsPath

    @staticmethod
    def GetSerialPortList():
        """@brief Get a list of the available serial ports.
           @return A list of serial.tools.list_ports.ListPortInfo instances.
                   Each instance has the following attributes.

                    - device
                    Full device name/path, e.g. /dev/ttyUSB0. This is also the information returned as first element when accessed by index.

                    - name
                    Short device name, e.g. ttyUSB0.

                    - description
                    Human readable description or n/a. This is also the information returned as second element when accessed by index.

                    - hwid
                    Technical description or n/a. This is also the information returned as third element when accessed by index.

                    USB specific data, these are all None if it is not an USB device (or the platform does not support extended info).

                    - vid
                    USB Vendor ID (integer, 0…65535).

                    - pid
                    USB product ID (integer, 0…65535).

                    - serial_number
                    USB serial number as a string.

                    - location
                    USB device location string (“<bus>-<port>[-<port>]…”)

                    - manufacturer
                    USB manufacturer string, as reported by device.

                    - product
                    USB product string, as reported by device.

                    - interface
                    Interface specific description, e.g. used in compound USB devices.
                    """
        portList = []
        comPortList = comports()
        for port in comPortList:
            if port.vid is not None:
                portList.append(port)
        return portList

    @staticmethod
    def ShowAvailableSerialPortDetails(uio, portInfoList=None):
        """@brief Show the serial port details of all available serial ports.
                  This method is really only for debug purposes.
           @param uio A UIO instance.
           @param portInfoList As returned from MCUBase.GetSerialPortList()."""
        if not portInfoList:
            portInfoList = MCUBase.GetSerialPortList()
        if uio:
            for portInfo in portInfoList:
                uio.info("Serial Port")
                uio.info(f"device:         {portInfo.device}")
                uio.info(f"name:           {portInfo.name}")
                uio.info(f"description:    {portInfo.description}")
                uio.info(f"hwid:           {portInfo.hwid}")
                uio.info(f"vid:            {portInfo.vid}")
                uio.info(f"pid:            {portInfo.pid}")
                uio.info(f"serial_number:  {portInfo.serial_number}")
                uio.info(f"location:       {portInfo.location}")
                uio.info(f"manufacturer:   {portInfo.manufacturer}")
                uio.info(f"product:        {portInfo.product}")
                uio.info(f"interface:      {portInfo.interface}")

    @staticmethod
    def GetTempFolder():
        """@return The temp storage folder. We could not have this method and use  tempfile.gettempdir() throughout the code
                   but this makes it easy to move the temp flder if required as the code only has to be changed here."""
        tempFolder = tempfile.gettempdir()
        return tempFolder

    def __init__(self, uio=None):
        """@brief Contructor.
           @param uio A UIO class instance."""
        self._uio               = uio
        self._windowsPlatform   = MCUBase.IsWindowsPlatform()
        self._username          = getpass.getuser()
        self._time1             = None
        self._ser               = None
        self.initTime()

    def info(self, msg):
        """@brief Display an info level message to the user.
           @param msg The message to be displayed."""
        if self._uio:
            self._uio.info(msg)

    def warn(self, msg):
        """@brief Display a warning level message to the user.
           @param msg The message to be displayed."""
        if self._uio:
            self._uio.warn(msg)

    def error(self, msg):
        """@brief Display an error level message to the user.
           @param msg The message to be displayed."""
        if self._uio:
            self._uio.error(msg)

    def debug(self, msg):
        """@brief Display an debug level message to the user.
           @param msg The message to be displayed."""
        if self._uio:
            self._uio.debug(msg)

    def waitForFirstAvailableSerialPort(self, timeoutSeconds=3):
        """@brief Wait for a serial port to appear on this machine.
           @return The device name of the first available serial port."""
        timeoutS = time()+timeoutSeconds
        while True:
            portInfoList = MCUBase.GetSerialPortList()
            if len(portInfoList) > 0:
                break
            if time() > timeoutS:
                raise Exception(f"{timeoutSeconds} second timeout waiting for a serial port to appear on this machine.")
            # Don't spinlock if no serial port is available
            sleep(0.25)

        return portInfoList[0].device

    # We retry this method as it has been found that this sometimes fails if a RPi Pico has just started.
    # When it fails a permission error is generated which is not the case on the next attempt.
    @retry(Exception, tries=3, delay=0.5)
    def _openFirstSerialPort(self, baud=115200, dtr=True, rts=True):
        """@brief Wait for a serial port to appear on this machine.
           @param baud The baud rate of the serial port in bps.
           @param dtr The State of the DTR control signal.
           @param rts The State of the RTS control signal.
           @return A reference to the open serial port obj."""
        self._serialPort = self.waitForFirstAvailableSerialPort()
        self.debug(f"Opening serial port {self._serialPort}")
        self._ser = serial.serial_for_url(self._serialPort, do_not_open=True, exclusive=True)
        self._ser.baudrate = baud
        self._ser.bytesize = 8
        self._ser.parity = 'N'
        self._ser.stopbits = 1
        self._ser.rtscts = False
        self._ser.xonxoff = False
        self._ser.open()
        self._ser.dtr=dtr
        self._ser.rts=rts
        self.debug(f"Opened serial port {self._serialPort}, DTR={dtr}, RTS={rts}")
        return self._ser

    def initTime(self):
        """@brief Save the current time."""
        self._time1 = time()

    def getElapsedSeconds(self):
        """@brief Get the elapsed seconds since initTime() was called."""
        return time()-self._time1

