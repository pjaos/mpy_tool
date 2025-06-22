import socket
import json
import uasyncio as asyncio

from lib.uo import UOBase
from lib.wifi import WiFi

from constants import Constants


class YDev(UOBase):
    """brief A Yview device implementation using micro python.
             See https://github.com/pjaos/yview for more information on the YView IoT architecture."""

    UDP_RX_BUFFER_SIZE = 2048   # The maximum AYT message size.
    AYT_KEY = "AYT"             # The key in the received JSON message.
    # The AYT key in the RX'ed JSON message must hold this value in
    # order to send a response to let the YView gateway know the device details.
    ID_STRING = "-!#8[dk_g^v\'s!d_rzn_e}6}8sP9}QoIR#?O&pg)Qra"

    # These are the attributes for the AYT response message
    IP_ADDRESS_KEY = "IP_ADDRESS"      # The IP address of this device
    OS_KEY = "OS"                      # The operating system running on this device
    UNIT_NAME_KEY = "UNIT_NAME"        # The name of this device.
    DEVICE_TYPE_KEY = "DEVICE_TYPE"    # The type of this device.
    PRODUCT_ID_KEY = "PRODUCT_ID"      # The product name for this device.
    # Details of the services provided by this device (E.G WEB:80)
    SERVICE_LIST_KEY = "SERVICE_LIST"
    # The group name for the device. Left unset if not restricted access is
    # needed.
    GROUP_NAME_KEY = "GROUP_NAME"

    YDEV_AYT_TCP_PORT_KEY       = "YDEV_AYT_TCP_PORT_KEY"
    YDEV_OS_KEY                 = "YDEV_OS"
    YDEV_UNIT_NAME_KEY          = "YDEV_UNIT_NAME"      # The name the user wishes to give the unit
    YDEV_PRODUCT_ID_KEY         = "YDEV_PRODUCT_ID"     # The product ID. E.G the model number. This is not writable as not write code is present in cmd_handler.
    YDEV_DEVICE_TYPE_KEY        = "YDEV_DEVICE_TYPE"    # The type of device of the unit. This is not writable as not write code is present in cmd_handler.
    YDEV_SERVICE_LIST_KEY       = "YDEV_SERVICE_LIST"   # A comma separated list of <service name>:<TCPIP port> that denote the service supported (E.G WEB:80). This is not writable as not write code is present in cmd_handler.
    YDEV_GROUP_NAME_KEY         = "YDEV_GROUP_NAME"

    def __init__(self, machine_config, uo=None):
        """@brief Constructor.
           @param machine_config The machine config that has details of the data to be returned in AYT response messages.
           @param uo A UO instance or None if no user output messages are needed."""
        super().__init__(uo=uo)
        self._machineConfig = machine_config
        self._yDevAYTPort = self._machineConfig.get(YDev.YDEV_AYT_TCP_PORT_KEY)
        self._running = False
        self._getParamsMethod = None
        self.listen()

    def _send_response(self, sock, remote_address_port):
        """@brief sock The UDP socket to send the response on.
           @param remote_address_port A tuple containing the address and port to send the response to."""
        # Ge the current WiFi interface IP address (if we have one) to send in the AYT response.
        address = WiFi.GetWifiAddress()
        json_dict = {}
        json_dict[YDev.IP_ADDRESS_KEY] = address
        json_dict[YDev.OS_KEY] = self._machineConfig.get(YDev.YDEV_OS_KEY)
        json_dict[YDev.UNIT_NAME_KEY] = self._machineConfig.get(YDev.YDEV_UNIT_NAME_KEY)
        json_dict[YDev.PRODUCT_ID_KEY] = self._machineConfig.get(YDev.YDEV_PRODUCT_ID_KEY)
        json_dict[YDev.DEVICE_TYPE_KEY] = self._machineConfig.get(YDev.YDEV_DEVICE_TYPE_KEY)
        json_dict[YDev.SERVICE_LIST_KEY] = self._machineConfig.get(YDev.YDEV_SERVICE_LIST_KEY)
        json_dict[YDev.GROUP_NAME_KEY] = self._machineConfig.get(YDev.YDEV_GROUP_NAME_KEY)
        if self._getParamsMethod is not None:
            # !!! If this method blocks it will delay the AYT message response
            params_dict = self._getParamsMethod()
            for key in params_dict.keys():
                json_dict[key] = params_dict[key]

        active = True
        if Constants.ACTIVE in json_dict:
            active = json_dict[Constants.ACTIVE]
        if active:
            json_dict_str = json.dumps(json_dict)
            self._debug("AYT response message: {}".format(json_dict_str))
            sock.sendto(json_dict_str.encode(), remote_address_port)
            self._debug(
                "Sent above message to {}:{}".format(
                    remote_address_port[0],
                    remote_address_port[1]))

    def set_get_params_method(self, get_params_method):
        """@brief Set reference to a method that will retrieve parameters to be included in the AYT response message."""
        self._getParamsMethod = get_params_method

    async def listen(self):
        """@brief Listen for YVIEW AYT messages and send responses when received."""
        # Open UDP socket to be used for discovering devices
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', self._yDevAYTPort))
        sock.setblocking(False)
        self._running = True
        while self._running:
            try:
                rx_data, address_port = sock.recvfrom(YDev.UDP_RX_BUFFER_SIZE)
                rx_dict = json.loads(rx_data)
                if YDev.AYT_KEY in rx_dict:
                    id_str = rx_dict[YDev.AYT_KEY]
                    if id_str == YDev.ID_STRING:
                        self._send_response(sock, address_port)
            except Exception:
                # We get here primarily when no data is present on the socket
                # when recvfrom is called.
                await asyncio.sleep(0.1)
