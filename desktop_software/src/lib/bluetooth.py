import asyncio
import inspect
import json
from time import time
from bleak import BleakClient, BleakScanner, BleakError
from lib.general import MCUBase

class BlueTooth(object):
    """@brief Responsible for communication with a device via bluetooth.
              Bluetooth has to be enabled on the local machine and the device
              for this to work."""

    # An issue exists when running on MacOS in that
    # When an ESP32 (original or newer, E.G esp32c3 etc) device is used the
    # bluetooth device name set by the MicroPython code may not be what the
    # MacOS bluetooth stack detects. In this case MACOS may detect this
    # device name instead.
    MACOS_ESP32_BT_DEV_NAME = "MPY ESP32"

    @staticmethod
    async def _IsBluetoothEnabled():
        """@brief Check if Bluetooth is available on the local machine.
           @return True is bluetooth is enabled/available."""
        try:
            await BlueTooth._Scan(0.1)
            return True
        except BleakError as ex:
            if 'No Bluetooth adapters found.' in str(ex):
                return False

        except OSError as ex:
            if 'The device is not ready for use' in str(ex):
                return False

        except Exception as ex:
            raise ex  # Re-raise if it's a different error

    @staticmethod
    def IsBluetoothEnabled():
        """@brief Check if Bluetooth is available on the local machine.
           @return True is bluetooth is enabled/available."""
        return asyncio.run(BlueTooth._IsBluetoothEnabled())

    @staticmethod
    async def _Scan(seconds):
        """@brief Scan for bluetooth devices.
           @param seconds The number of seconds to scan for.
           @return A list of bluetooth devices found."""
        return await BleakScanner.discover(timeout=seconds)

    @staticmethod
    def Scan(seconds=5, dev_filter_string=None):
        """@brief Scan for bluetooth devices.
           @param dev_filter_string If True then only bluetooth devices that
                  start with this string are included in the bluetooth device list.
           @param seconds The number of seconds to scan for.
           @return A list of bluetooth devices."""
        device_list = []
        dev_list = asyncio.run(BlueTooth._Scan(seconds))
        if dev_filter_string:
            for device in dev_list:
                if device.name and device.name.startswith(dev_filter_string):
                    device_list.append(device)
                elif MCUBase.IsMacOSPlatform() and device.name == BlueTooth.MACOS_ESP32_BT_DEV_NAME:
                    device_list.append(device)

        else:
            device_list = dev_list
        return device_list

    STORED_EXCEPTION = None
    @staticmethod
    def SetException(exception):
        """@brief Set an error instance.
           @param exception The error instance."""
        BlueTooth.STORED_EXCEPTION = exception

    def __init__(self, uio=None, rx_timeout_seconds=10, rx_finished_timeout_seconds=0.2):
        self._uio = uio
        self._rx_list = []
        # If we received no data over bluetooth we wait this long.
        self._rx_timeout_seconds = rx_timeout_seconds
        # Once we start receiving data over bluetooth this timeout must occur before we stop listening.
        self._rx_finished_timeout_seconds = rx_finished_timeout_seconds
        # For recording an exception generated in the async env to be reported in the sync env
        self.exception = None

    def debug(self, msg):
        """@brief display a debug message if a UIO instance was passed in the constructor.
           @param msg The text message to be displayed."""
        if self._uio:
            self._uio.debug(msg)

    async def _notification_handler(self, sender, data):
        """@brief Called when data is received over a bluetooth connection in order to record it."""
        self._rx_list.append(data.decode())

    def _raise_exception_on_error(self):
        """@brief If an error/exception has occurred in the async env raise it in the sync env."""
        if BlueTooth.STORED_EXCEPTION:
            raise BlueTooth.STORED_EXCEPTION

    def _set_exception(self, exception):
        """@brief Set an error instance.
           @param exception The error instance."""
        BlueTooth.SetException(exception)

    def get_exception(self):
        """@return An exception instance if an error has occurred. If no error has occurred then None is returned."""
        return self.exception

    def clear_exception(self):
        """@brief May be called to clear an exception if one has occurred."""
        self.exception = None

    def _clear_rx_list(self):
        """@brief Clear the list that holds messages received over the bluetooth interface."""
        # Clear the RX data buffer
        self._rx_list.clear()

    async def _waitfor_response(self, client, clear_rx_list= True):
        """@brief Waitfor a response to a previously command previously sent over the bluetooth interface.
           @param client A connected BleakClient.
           @param clear_rx_list If True the self._rx_list is cleared before we start listening for bluetooth data."""
        if clear_rx_list:
            self._clear_rx_list()

        try:
            self.debug(f"{inspect.currentframe().f_code.co_name}: Waiting for RX data.")
            start_time = time()
            while True:
                await asyncio.sleep(0.25)
                # We have started receiving some data
                if self._rx_list:
                    self.debug(f"{inspect.currentframe().f_code.co_name}: Some data received.")
                    break

                if time() >= start_time + self._rx_timeout_seconds:
                    raise Exception(f"No data received for {self._rx_timeout_seconds} seconds.")

            self.debug(f"{inspect.currentframe().f_code.co_name}: Waiting for RX data.")
            msg_count = len(self._rx_list)
            last_msg_count = msg_count
            last_rx_time = time()
            while True:
                await asyncio.sleep(0.25)
                # We have started receiving some data
                if self._rx_list:
                    self.debug(f"{inspect.currentframe().f_code.co_name}: Some data received.")
                    break

                msg_count = len(self._rx_list)
                if msg_count > last_msg_count:
                    last_msg_count = msg_count
                    last_rx_time = time()

                # We've stopped receiving bluetooth data so exit
                elif time() > last_rx_time + self._rx_timeout_seconds:
                    break

                if time() >= start_time + self._rx_timeout_seconds:
                    raise Exception("Timeout waiting for bluetooth data reception to cease.")

        except Exception as ex:
            self.debug(f"{inspect.currentframe().f_code.co_name}: Error: {str(ex)}")
            self.exception = ex

        finally:
            await client.stop_notify(YDevBlueTooth.NOTIFY_UUID)

        return self._rx_list

class YDevBlueTooth(BlueTooth):
    """@brief Responsible for communication with a YDev device via bluetooth.
              Bluetooth has to be enabled on the local machine and YDev device
              for this to work. To enable Bluetooth on a YDev device hold the
              Wifi button down until the YDev unit reboots and the blue and
              green led's flash."""

    WRITE_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Replace with actual UUID
    NOTIFY_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"      # Notification UUID

    WIFI_SCAN_CMD = b'{"CMD": "WIFI_SCAN"}'
    GET_IP_CMD = b'{"CMD": "GET_IP"}'
    DISABLE_BLUETOOTH = b'{"CMD": "DISABLE_BT"}'

    SSID = 'SSID'
    PASSWORD = 'PASSWD'
    SETUP_WIFI_CMD_DICT = {'CMD': 'BT_CMD_STA_CONNECT', f'{SSID}': '', f'{PASSWORD}': ''}

    IP_ADDRESS = "IP_ADDRESS"

    YDEV = "YDEV"

    @staticmethod
    def ScanYDev(seconds=5):
        """@brief Scan for bluetooth devices.
           @param dev_filter_string If True then only bluetooth devices that
                  start with this string are included in the bluetooth device list.
           @param seconds The number of seconds to scan for.
           @return A list of bluetooth devices."""
        return YDevBlueTooth.Scan(seconds=seconds, dev_filter_string=YDevBlueTooth.YDEV)

    def __init__(self, uio=None):
        super().__init__(uio=uio)

    async def _wifi_scan(self, address):
        """@brief Send a cmd to the YDev unit to get it to scan for WiFi networks that it can see.
           @param address The bluetooth address of the device.
           @return A list of strings detailing the network parameters."""
        try:
            async with BleakClient(address) as client:
                self.debug(f"{inspect.currentframe().f_code.co_name}: Connected to {address}")

                await client.start_notify(YDevBlueTooth.NOTIFY_UUID, self._notification_handler)
                self.debug(f"{inspect.currentframe().f_code.co_name}: started RX data notifier.")

                data = YDevBlueTooth.WIFI_SCAN_CMD
                await client.write_gatt_char(YDevBlueTooth.WRITE_CHAR_UUID, data, response=True)
                self.debug(f"{inspect.currentframe().f_code.co_name}: Data written: {data}")

                await self._waitfor_response(client)

        except Exception as e:
            self._set_exception(e)

        return self._rx_list

    def wifi_scan(self, address):
        """@brief Send a cmd to the YDev unit to get it to scan for WiFi networks that
                  it can see.
           @param address The bluetooth address of the device.
           @return A list of dicts. Each dict contains the following keys.
                  RSSI,
                  HIDDEN,
                  SSID,
                  CHANNEL,
                  BSSID
                  SECURITY
        """
        line_list = asyncio.run(self._wifi_scan(address))
        # This sometimes generates an error even though the scan worked.
        # Therefore we ignore the error, rather than calling self._raise_exception_on_error().
        self._set_exception(None)
        dict_list = []
        for line in line_list:
            try:
                dict_list.append(json.loads(line))
            except json.decoder.JSONDecodeError:
                pass
        return dict_list

    async def _setup_wifi(self, address, ssid, password):
        """@brief Set the WiFi SSID and password for the YDev device.
           @param address The bluetooth address of the device.
           @param ssid The WiFi SSID.
           @param password The WiFi password."""
        try:
            async with BleakClient(address) as client:
                self.debug(f"{inspect.currentframe().f_code.co_name}: Connected to {address}")

                YDevBlueTooth.SETUP_WIFI_CMD_DICT[YDevBlueTooth.SSID] = ssid
                YDevBlueTooth.SETUP_WIFI_CMD_DICT[YDevBlueTooth.PASSWORD] = password
                cmd_str = json.dumps(YDevBlueTooth.SETUP_WIFI_CMD_DICT)

                data = cmd_str.encode()
                await client.write_gatt_char(YDevBlueTooth.WRITE_CHAR_UUID, data, response=True)
                self.debug(f"{inspect.currentframe().f_code.co_name}: Data written: {data}")

        except Exception as e:
            self._set_exception(e)

        return self._rx_list

    def setup_wifi(self, address, ssid, password):
        """@brief Set the WiFi SSID and password for the YDev device.
           @param address The bluetooth address of the device.
           @param ssid The WiFi SSID.
           @param password The WiFi password."""
        response = asyncio.run(self._setup_wifi(address, ssid, password))
        self._raise_exception_on_error()
        return response

    def waitfor_device(self, address, timeout=30):
        """@brief Waitfor a YDev device to appear.
           @param timeout The number of seconds before we give up looking.
           @return The Bluetooth device found or None if not found."""
        dev_found = None
        start_time = time()
        waiting = True
        while waiting:
            dev_list = YDevBlueTooth.Scan(seconds=3)
            for dev in dev_list:
                if dev.address == address:
                    dev_found = dev
                    waiting = False
                    break

            # Quit on timeout
            if time() >= start_time + timeout:
                break

        return dev_found

    async def _get_ip(self, address, timeout=60):
        """@brief Get the IP address of the YDev device. This is only useful after setup_wifi() has been called.
           @param address The bluetooth address of the device.
           @param timeout The number of seconds to wait for the IP address to be received.
           @return The IP address of the device."""
        ip_address = None
        try:
            async with BleakClient(address) as client:
                self.debug(f"{inspect.currentframe().f_code.co_name}: Connected to {address}")

                await client.start_notify(YDevBlueTooth.NOTIFY_UUID, self._notification_handler)
                self.debug(f"{inspect.currentframe().f_code.co_name}: started RX data notifier.")

                # Wait for an IP address of the device over a bluetooth connection.
                timeout = time() + timeout
                while True:
                    try:
                        data = YDevBlueTooth.GET_IP_CMD
                        await client.write_gatt_char(YDevBlueTooth.WRITE_CHAR_UUID, data, response=True)
                        self.debug(f"{inspect.currentframe().f_code.co_name}: Data written: {data}")

                        await self._waitfor_response(client)

                        if self._rx_list:
                            line = self._rx_list[0].rstrip('\r\n')
                            rx_dict = json.loads(line)
                            if YDevBlueTooth.IP_ADDRESS in rx_dict:
                                ip_address = rx_dict[YDevBlueTooth.IP_ADDRESS]
                                break

                        if time() >= timeout:
                            raise Exception("Failed to get IP address over bluetooth.")

                    except Exception as ex:
                        print(str(ex))

        except Exception as e:
            self._set_exception(e)

        return ip_address

    def get_ip(self, address):
        """@brief Get the IP address of the YDev device. This is only useful after setup_wifi() has been called.
           @param address The bluetooth address of the device.
           @return The IP address of the device."""
        response = asyncio.run(self._get_ip(address))
        self._raise_exception_on_error()
        return response

    async def _disable_bluetooth(self, address):
        """@brief Disable the bluetooth interface on the YDev device.
                  To enable bluetooth on the YDev device the WiFi switch
                  must be held down until the device restarts."""
        try:
            async with BleakClient(address) as client:
                self.debug(f"{inspect.currentframe().f_code.co_name}: Connected to {address}")

                data = YDevBlueTooth.DISABLE_BLUETOOTH
                await client.write_gatt_char(YDevBlueTooth.WRITE_CHAR_UUID, data, response=True)
                self.debug(f"{inspect.currentframe().f_code.co_name}: Data written: {data}")

        except Exception as e:
            e_str = str(e)
            # Ignore this error as it appears the command completes successfully when it occurs
            if e_str.find("Unlikely Error") == -1:
                # Raise all other errors
                self._set_exception(e)

        return self._rx_list

    def disable_bluetooth(self, address):
        """@brief Disable the bluetooth interface on the YDev device.
                  To enable bluetooth on the YDev device the WiFi switch
                  must be held down until the device restarts."""
        asyncio.run(self._disable_bluetooth(address))
        self._raise_exception_on_error()


"""

# Example to setup YDev WiFi

def main():
    # Program entry point

    # Example to setup YDEV WiFi

    class UIO():
        # @brief Example UIO class.
        def info(self, msg):
            print(f"INFO:  {msg}")

        def debug(self, msg):
            print(f"DEBUG: {msg}")

    uio = UIO()

    ydevBlueTooth = YDevBlueTooth(uio=None)

    if YDevBlueTooth.IsBluetoothEnabled():

        dev_list = YDevBlueTooth.ScanYDev()
        if dev_list:
            dev = dev_list[0]
            print(f"Found: {dev}. WiFi scan in progress...")
            network_dicts = ydevBlueTooth.wifi_scan(dev.address)
            print("Setting up WiFi")
            ydevBlueTooth.setup_wifi(dev.address, 'YOURSSID', 'YOURPASSWORD')
            print(f"Waiting for YDev device ({dev.address}) to restart.")
            ydevBlueTooth.waitfor_device(dev.address)

            ip_address = ydevBlueTooth.get_ip(dev.address)
            print(f"ip_address={ip_address}")

            ydevBlueTooth.disable_bluetooth(dev.address)

        else:
            print("No YDev devices detected over bluetooth.")

    else:
        print("Bluetooth is not available. Please enable bluetooth.")

if __name__== '__main__':
    main()

"""

"""
# Example to detect all bluetooth devices.

def main():

    if BlueTooth.IsBluetoothEnabled():
        devices = BlueTooth.Scan(seconds=5)
        for device in devices:
            print(f"------------------------------------")
            print(f"device.name    = {device.name}")
            print(f"device.address = {device.address}")
            print(f"local_name     = {device.metadata.get('local_name')}")
            if 'path' in device.details:
                print(f'path           ={device.details['path']}')
            print('PROPERTIES')
            if 'props' in device.details:
                properties = device.details['props']
                for prop in properties:
                    print(f'{prop:<20s}: {properties[prop]}')


    else:
        print("Bluetooth is not available. Please enable bluetooth.")

if __name__== '__main__':
    main()
"""

