import sys
import os
import gc
import hashlib
import binascii
import asyncio

import ujson as json
from time import time

from lib.microdot.microdot import Microdot, Response
from lib.config import MachineConfig
from lib.io import IO
from lib.hardware import const, Hardware
from lib.fs import VFS
from lib.wifi import WiFi

class WebServer():
    DEFAULT_PORT = 80

    RAM_USED_BYTES = const("RAM_USED_BYTES")
    RAM_FREE_BYTES = const("RAM_FREE_BYTES")
    RAM_TOTAL_BYTES = const("RAM_TOTAL_BYTES")
    DISK_TOTAL_BYTES = const("DISK_TOTAL_BYTES")
    DISK_USED_BYTES = const("DISK_USED_BYTES")
    DISK_PERCENTAGE_USED = const("DISK_PERCENTAGE_USED")

    OK_KEY = "OK"                                            # The key in the JSON response if no error occurs.
    ERROR_KEY = "ERROR"                                      # The key in the JSON response if an error occurs.
    UPTIME_SECONDS = "UPTIME_SECONDS"
    ACTIVE_APP_FOLDER_KEY = "ACTIVE_APP_FOLDER"
    INACTIVE_APP_FOLDER_KEY = "INACTIVE_APP_FOLDER"
    WIFI_SCAN_RESULTS = "WIFI_SCAN_RESULTS"

    WEBREPL_CFG_PY_FILE = "webrepl_cfg.py"

    @staticmethod
    def get_error_dict(msg):
        """@brief Get an error response dict.
           @param msg The message to include in the response.
           @return The dict containing the error response"""
        return {WebServer.ERROR_KEY: msg}

    @staticmethod
    def get_ok_dict():
        """@brief Get an OK dict response.
           @param msg The message to include in the response.
           @return The dict containing the error response"""
        return {WebServer.OK_KEY: True}

    def __init__(self,
                 machine_config,
                 startTime,
                 uo=None, port=DEFAULT_PORT):
        """@brief Constructor
           @param machine_config The MachineConfig instance for this machine.
           @param startTime The time that the machine started.
           @param uo A UIO instance if debug required."""
        self._machine_config = machine_config
        self._uo = uo
        self._port = port
        self._startTime = startTime
        self._param_dict = {}
        # PJA
        self.request_lock = asyncio.Lock()

        self._app = Microdot()

    def get_param_dict(self):
        """@return The webserver parameter dict."""
        return self._param_dict

    def _update_content(self, template_bytes, values_dict, start = b'{{ ', stop = b' }}'):
        """@brief Insert the values into an HTML page.
           @param template_bytes The html file contents read from flash.
           @param values_dict The dict containing the values. The key is the parameter text between start and stop bytes.
           @param start = The bytes (not string) that appears before the variable name in the html file.
           @param start = The bytes (not string) that appears after the variable name in the html file."""
        for key, val in values_dict.items():
            placeholder = start + key.encode() + stop
            value_bytes = str(val).encode()
            template_bytes = template_bytes.replace(placeholder, value_bytes)
        return template_bytes

    def _add_ram_stats(self, responseDict):
        """@brief Update the RAM usage stats.
           @param responseDict the dict to add the stats to."""
        usedBytes = gc.mem_alloc()
        freeBytes = gc.mem_free()
        responseDict[WebServer.RAM_USED_BYTES] = usedBytes
        responseDict[WebServer.RAM_FREE_BYTES] = freeBytes
        responseDict[WebServer.RAM_TOTAL_BYTES] = usedBytes + freeBytes

    def _add_disk_usage_stats(self, responseDict):
        """@brief Update the RAM usage stats.
           @param responseDict the dict to add the stats to."""
        totalBytes, usedSpace, percentageUsed = VFS.get_fs_info()
        responseDict[WebServer.DISK_TOTAL_BYTES] = totalBytes
        responseDict[WebServer.DISK_USED_BYTES] = usedSpace
        responseDict[WebServer.DISK_PERCENTAGE_USED] = percentageUsed

    def _add_up_time(self, responseDict):
        """@brief Get the uptime stats.
           @param responseDict A dict to add the uptime stats to."""
        responseDict[WebServer.UPTIME_SECONDS] = time()-self._startTime

    def _getSysStats(self, request):
        """@return A dict containing the system stats, ram, disk usage and uptime."""
        runGC = request.args.get("gc", False)
        if runGC:
            gc.collect()
        responseDict = {}
        self._add_ram_stats(responseDict)
        self._add_disk_usage_stats(responseDict)
        self._add_up_time(responseDict)
        return responseDict

    def _get_folder_entries(self, folder, fileList):
        """@brief List the entries in a folder.
           @brief folder The folder to look for files in.
           @brief fileList The list to add files to."""
        fsIterator = os.ilistdir(folder)
        for nodeList in fsIterator:
            if len(nodeList) >= 3:
                name = nodeList[0]
                type = nodeList[1]
                if len(name) > 0:
                    if folder == '/':
                        anEntry = folder + name
                    else:
                        anEntry = folder + "/" + name
                    if type == IO.TYPE_FILE:
                        fileList.append(anEntry)

                    elif type == IO.TYPE_DIR:
                        # All folders end in /
                        fileList.append(anEntry + '/')
                        # Recurse through dirs
                        self._get_folder_entries(anEntry, fileList)
        return fileList

    def _get_file_list(self, request):
        """@brief Get a list of the files and dirs on the system.
            @param request The http request.
            @return The response list."""
        path = request.args.get("path", "/")
        if ".." in path:
            return WebServer.get_error_dict(".. is an Invalid path")
        return self._get_folder_entries(path, [])

    def _remove_dir(self, theDirectory):
        """@brief Remove the directory an all of it's contents.
           @param theDirectory The directory to remove."""
        if IO.DirExists(theDirectory):
            entryList = []
            self._get_folder_entries(theDirectory, entryList)
            for entry in entryList:
                if IO.DirExists(entry):
                    self._remove_dir(entry)

                elif IO.FileExists(entry):
                    os.remove(entry)
            # All contents removed so remove the top level.
            os.remove(theDirectory)

    def _erase_offline_app(self):
        """@brief Erase the offline app folder and all of it's contents.
           @return The response dict."""
        runningApp = self._machine_config.get(MachineConfig.RUNNING_APP_KEY)
        if runningApp:
            offLineApp = 2
            if runningApp == 2:
                offLineApp = 1
            appRoot = "/app{}".format(offLineApp)
            self._remove_dir(appRoot)
            returnDict = WebServer.get_ok_dict()

        else:
            returnDict = WebServer.get_error_dict("The machine config does not detail the running app !!!")

        return returnDict

    def _make_dir(self, request):
        """@brief Create a dir on the devices file system.
           @param request The http request.
           @return The response dict."""
        path = request.args.get("path", None)
        if path:
            try:
                os.mkdir(path)
                responseDict = WebServer.get_ok_dict()
            except OSError:
                responseDict = WebServer.get_error_dict("Failed to create {}".format(path))
        return responseDict

    def _rm_dir(self, request):
        """@brief Remove a dir on the devices file system.
           @param request The http request.
           @return The response dict."""
        path = request.args.get("path", None)
        if path:
            try:
                os.rmdir(path)
                responseDict = WebServer.get_ok_dict()
            except OSError:
                responseDict = WebServer.get_error_dict("Failed to remove {}".format(path))
        else:
            responseDict = WebServer.get_error_dict("No dir passed to /rmdir")
        return responseDict

    def _rm_file(self, request):
        """@brief Remove a dir on the devices file system.
           @param request The http request.
           @return The response dict."""
        _file = request.args.get("file", None)
        if _file:
            try:
                os.remove(_file)
                responseDict = WebServer.get_ok_dict()
            except OSError:
                responseDict = WebServer.get_error_dict("Failed to delete {}".format(_file))
        else:
            responseDict = WebServer.get_error_dict("No file passed to /rmfile")
        return responseDict

    def _get_file(self, request):
        """@brief Get the contents of a file on the devices file system.
            @param request The http request.
           @return The response dict containing the file contents."""
        _file = request.args.get("file", None)
        if _file:
            try:
                fd = None
                try:
                    fd = open(_file)
                    fileContent = fd.read()
                    fd.close()
                    responseDict = WebServer.get_ok_dict()
                    responseDict[_file] = fileContent

                finally:
                    if fd:
                        fd.close()
                        fd = None

            except Exception as ex:
                WebServer.get_error_dict(str(ex))

        else:
            responseDict = WebServer.get_error_dict("No file passed to /get_file")

        return responseDict

    def reset_wifi_config(self):
        """@brief Reset the WiFi config to the default values (AP mode)"""
        self._machine_config.reset_wifi_config()
        return WebServer.get_ok_dict()

    def _get_app_folder(self, active):
        """@brief Get the app folder.
           @param active If True then get the active application folder.
           @param responseDict containing the active app folder."""
        runningApp = self._machine_config.get(MachineConfig.RUNNING_APP_KEY)

        if runningApp == 1:
            offLineApp = 2
        if runningApp == 2:
            offLineApp = 1

        if active:
            appRoot = "/app{}".format(runningApp)
            returnDict = {WebServer.ACTIVE_APP_FOLDER_KEY: appRoot}
        else:
            appRoot = "/app{}".format(offLineApp)
            returnDict = {WebServer.INACTIVE_APP_FOLDER_KEY: appRoot}

        return returnDict

    def get_active_app_folder(self):
        return self._get_app_folder(True)

    def get_inactive_app_folder(self):
        return self._get_app_folder(False)

    def swap_active_app_folder(self):
        """@brief Swap the active app folder.
           @return a dict containing the active app folder."""
        if self._machine_config.is_parameter(MachineConfig.RUNNING_APP_KEY):
            runningApp = self._machine_config.get(MachineConfig.RUNNING_APP_KEY)
            if runningApp == 1:
                newActiveApp = 2
            else:
                newActiveApp = 1
            self._machine_config.set(MachineConfig.RUNNING_APP_KEY, newActiveApp)
            self._machine_config.store()
        return {WebServer.ACTIVE_APP_FOLDER_KEY: newActiveApp}

    def reset_to_default_config(self):
        """@reset the configuration to defaults."""
        self._machine_config.set_defaults()
        self._machine_config.store()
        responseDict = WebServer.get_ok_dict()
        responseDict["INFO"] = "The unit has been reset to the default configuration."

    def wifi_scan(self):
        """@brief Scan for WiFi networks."""
        responseDict = WebServer.get_ok_dict()
        responseDict[WebServer.WIFI_SCAN_RESULTS] = WiFi.Get_Wifi_Networks()
        return responseDict

    def sha256_file(path, request):
        try:
            digest = ""
            _file = request.args.get("file", None)
            h = hashlib.sha256()
            with open(_file, 'rb') as f:
                while True:
                    chunk = f.read(1024)
                    if not chunk:
                        break
                    h.update(chunk)
            digest = binascii.hexlify(h.digest())
            responseDict = WebServer.get_ok_dict()
            responseDict["SHA256"] = digest

        except Exception as e:
            responseDict = WebServer.get_error_dict(str(e))

        return responseDict

    def collect_garbage(self):
        """@brief Force run the python garbage collector."""
        gc.collect()
        responseDict = WebServer.get_ok_dict()
        return responseDict

    def get_content_type(self, filename):
        if filename.endswith('.html'):
            return 'text/html'
        elif filename.endswith('.css'):
            return 'text/css'
        elif filename.endswith('.js'):
            return 'application/javascript'
        elif filename.endswith('.json'):
            return 'application/json'
        elif filename.endswith('.png'):
            return 'image/png'
        elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
            return 'image/jpeg'
        elif filename.endswith('.gif'):
            return 'image/gif'
        elif filename.endswith('.svg'):
            return 'image/svg+xml'
        elif filename.endswith('.ico'):
            return 'image/x-icon'
        else:
            return 'application/octet-stream'

    def _mkdirs(self, path):
        """@brief Recursively create directories like os.makedirs()
           @param path The path to create"""
        parts = path.split('/')
        current = ''
        for part in parts:
            if not part:
                continue  # Skip empty parts (e.g. from leading '/')
            current += '/' + part
            try:
                os.mkdir(current)
            except OSError as e:
                if e.args[0] == 17:
                    # EEXIST — already exists, so continue
                    continue
                else:
                    raise

    def _set_webrepl_password(self, request):
        """@brief Create a dir on the devices file system.
           @param request The http request.
           @return The response dict."""
        password = request.args.get("password", None)
        if password:
            if len(password) >= 4 and len(password) <= 9:
                try:
                    lines = ['# The password must be 4 to 9 characters long',
                            '# This file must have a new line after the password.',
                            f"PASS = '{password}'"]
                    with open(WebServer.WEBREPL_CFG_PY_FILE, 'w') as fd:
                        for line in lines:
                            fd.write(line + "\n")
                    responseDict = WebServer.get_ok_dict()
                    responseDict['WEBREPL_PASSWORD'] = f'{password}'
                    responseDict['INFO'] = 'Restart MCU to set new password.'
                except OSError:
                    responseDict = WebServer.get_error_dict(f"Failed to create {WebServer.WEBREPL_CFG_PY_FILE}")
            else:
                responseDict = WebServer.get_error_dict(f"{password} is an invalid WebREPL password. The password length must be >= 4 and <= 9 characters long.")
        else:
            responseDict = WebServer.get_error_dict("WebREPL password not defined.")

        return responseDict

    def get_app(self):
        return self._app

    def run(self):
        """@brief This is a blocking method that starts the web server.
                  All the routes will be added that are needed to support OTA upgrade."""

        def get_json(_dict):
            """@param _dict A python dictionary.
               @return Return a JSON representation of the _dict"""
            return json.dumps(_dict)

        def return_success():
            return get_json(WebServer.get_ok_dict())

        def return_error(msg):
            return get_json(WebServer.get_error_dict(msg))

        @self._app.post('/upload')
        def upload(req):
            filename = req.headers.get('X-File-Name')
            is_first_chunk = req.headers.get('X-Start', '0') == '1'
            chunk = req.body
            chunk_size = len(chunk)

            # Ensure containing directory exists
            dir_name = '/'.join(filename.split('/')[:-1])
            if dir_name and dir_name not in os.listdir():
                self._mkdirs(dir_name)

            mode = 'wb'  # truncate file if it exists
            if not is_first_chunk:
                mode = 'ab'

            # Write the file containing the received data
            with open(filename, mode) as f:
                if chunk_size > 0:
                    f.write(chunk)

            return get_json(WebServer.get_ok_dict())

        # ------- Start of protection from overload
        # We lock requests so we process them serially
        @self._app.before_request
        async def acquire_lock(request):
            try:
                await asyncio.wait_for(self.request_lock.acquire(), 2)
                request._has_lock = True
            except asyncio.TimeoutError:
                return Response('Server busy', status_code=503)

        @self._app.after_request
        async def release_lock(request, response):
            if getattr(request, '_has_lock', False):
                self.request_lock.release()
                request._has_lock = False
            return response

        @self._app.errorhandler(Exception)
        async def handle_exception(exc):
            # release lock if held
            if self.request_lock.locked():
                self.request_lock.release()

            sys.print_exception(exc)

            return 'Internal error', 500

            return Response('Internal error', status_code=500)

        # --------End of protection from overload

        @self._app.route('/get_sys_stats')
        async def get_sys_stats(request):
            return get_json(self._getSysStats(request))

        @self._app.route('/get_file_list')
        async def get_file_list(request):
            return get_json(self._get_file_list(request))

        @self._app.route('/get_machine_config')
        async def get_machine_config(request):
            return get_json(self._machine_config)

        @self._app.route('/erase_offline_app')
        async def erase_offline_app(request):
            return get_json(self._erase_offline_app())

        @self._app.route('/mkdir')
        async def mkdir(request):
            return get_json(self._make_dir(request))

        @self._app.route('/rmdir')
        async def rmdir(request):
            return get_json(self._rm_dir(request))

        @self._app.route('/rmfile')
        async def rmfile(request):
            return get_json(self._rm_file(request))

        @self._app.route('/get_file')
        async def getfile(request):
            return get_json(self._get_file(request))

        @self._app.route('/reset_wifi_config')
        async def reset_wifi_config(request):
            return get_json(self.reset_wifi_config())

        @self._app.route('/get_active_app_folder')
        async def get_active_app_folder(request):
            return get_json(self.get_active_app_folder())

        @self._app.route('/get_inactive_app_folder')
        async def get_inactive_app_folder(request):
            return get_json(self.get_inactive_app_folder())

        @self._app.route('/swap_active_app')
        async def swap_active_app(request):
            return get_json(self.swap_active_app_folder())

        @self._app.route('/reboot')
        async def reboot(request):
            Hardware.reboot()
            return get_json(WebServer.get_ok_dict())

        @self._app.route('/reset_to_default_config')
        async def reset_to_default_config(request):
            return get_json(self.reset_to_default_config())

        @self._app.route('/wifi_scan')
        async def wifi_scan(request):
            return get_json(self.wifi_scan())

        @self._app.route('/sha256')
        async def sha256(request):
            return get_json(self.sha256_file(request))

        @self._app.route('/gc')
        async def gc(request):
            return get_json(self.collect_garbage())

        @self._app.route('/shutdown')
        async def shutdown(request):
            request.app.shutdown()
            return get_json(WebServer.get_error_dict("The server is shutting down..."))

        # The ability to set the WebREPL password over the REST interface is a clear security hole.
        # This is why this is commented out by default. Remove the comment lines with care.
#        @app.route('/setwebreplpw')
#        async def set_webrepl_password(request):
#            return get_json(self._set_webrepl_password(request))

        # The default path. Do not place route definitions after this or they will
        # not be called.
        @self._app.route('/')
        @self._app.route('/<path:path>')
        def serve(request, path='index.html'):
            # Prevent directory traversal
            if '..' in path or path.startswith('/'):
                return '403 Forbidden', 403

            try:
                appFolder = self.get_active_app_folder()[WebServer.ACTIVE_APP_FOLDER_KEY]
                serverFile = f'{appFolder}/assets/{path}'
                with open(serverFile, 'rb') as f:
                    content = f.read()
                    if self._param_dict:
                        content = self._update_content(content, self._param_dict)
                    content_type = self.get_content_type(path)
                    return Response(body=content, headers={'Content-Type': content_type})

            except Exception:
                return '404 Not Found', 404

        self._app.run(debug=True, port=self._port)

