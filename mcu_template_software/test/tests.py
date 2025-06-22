#!/usr/bin/env python3

import os
import unittest
from unittest.mock import patch
from io import StringIO

from src.config import MachineConfig
from src.uo import UO, UOBase

class TestConfig(unittest.TestCase):
    PARAM1 = 1
    PARAM1_VALUE = 12.34

    DEFAULT_CONFIG = {
        PARAM1: PARAM1_VALUE
    }

    def _del_config_files(self):
        if os.path.isfile(MachineConfig.CONFIG_FILENAME):
            os.remove(MachineConfig.CONFIG_FILENAME)
            #print(f"Removed {MachineConfig.CONFIG_FILENAME}")

        if os.path.isfile(MachineConfig.FACTORY_CONFIG_FILENAME):
            os.remove(MachineConfig.FACTORY_CONFIG_FILENAME)
            #print(f"Removed {MachineConfig.FACTORY_CONFIG_FILENAME}")

    def setUp(self):
        self._del_config_files()
        # runs before each test method
        self._machine_config = MachineConfig(TestConfig.DEFAULT_CONFIG)

    def tearDown(self):
        self._del_config_files()

    def test1_param1(self):
        # Check we can get a value from the dict
        value = self._machine_config.get(TestConfig.PARAM1)
        assert(value==TestConfig.PARAM1_VALUE)

    def test2_int_key_fails(self):
        try:
            self._machine_config.set(12, 1.0)
        except Exception as e:
            self.fail(f"Unexpected exception raised: {e}")

    def test3_string_key_fails(self):
        with self.assertRaises(Exception):
            self._machine_config.set("ASTRING", 1.0)

    def test4_check_read_default_wifi_cfg_dict(self):
        self._machine_config.store()
        wifi_cfg_dict = self._machine_config.get(MachineConfig.WIFI_KEY)
        self.assertEqual( wifi_cfg_dict[MachineConfig.WIFI_CONFIGURED_KEY], 0)
        self.assertEqual( wifi_cfg_dict[MachineConfig.MODE_KEY], MachineConfig.AP_MODE)
        self.assertEqual( wifi_cfg_dict[MachineConfig.AP_CHANNEL_KEY], MachineConfig.DEFAULT_AP_CHANNEL)
        self.assertEqual( wifi_cfg_dict[MachineConfig.SSID_KEY], MachineConfig.DEFAULT_SSID)
        self.assertEqual( wifi_cfg_dict[MachineConfig.PASSWORD_KEY], MachineConfig.DEFAULT_AP_PASSWORD)

    def test5_check_is_parameter(self):
        value = self._machine_config.is_parameter(TestConfig.PARAM1)
        assert(value==True)
        value = self._machine_config.is_parameter(100)
        assert(value==False)

    def test6_non_default_keys_removed(self):
        non_default_key = 100
        self._machine_config.set(non_default_key, "astr")
        found = self._machine_config.is_parameter(non_default_key)
        assert(found==True)
        self._machine_config.load()
        found = self._machine_config.is_parameter(non_default_key)
        assert(found==False)

        self._machine_config = MachineConfig( {TestConfig.PARAM1: TestConfig.PARAM1_VALUE, non_default_key: "astr"} )
        found = self._machine_config.is_parameter(non_default_key)
        assert(found==True)
        self._machine_config.load()
        found = self._machine_config.is_parameter(non_default_key)
        assert(found==True)

    def test7_merge_factory_dict(self):
        assy_text = "ASM0123V09.1_SN00000198"
        assy_key = 200
        self._machine_config = MachineConfig( {assy_key: assy_text} )
        self._machine_config.save_factory_config([assy_key,])
        # Del this.machine.cfg
        if os.path.isfile(MachineConfig.CONFIG_FILENAME):
            os.remove(MachineConfig.CONFIG_FILENAME)
            # print(f"Removed {MachineConfig.CONFIG_FILENAME}")
        # Load config this.machine.cfg
        self._machine_config = MachineConfig( {assy_key: ""} )
        loaded_assy_text = self._machine_config.get(assy_key)
        assert(loaded_assy_text==assy_text)

    def test_reset_wifi_config(self):
        wifi_cfg_dict = self._machine_config.get(MachineConfig.WIFI_KEY)
        wifi_cfg_dict[MachineConfig.MODE_KEY] = MachineConfig.STA_MODE
        self._machine_config.set(MachineConfig.WIFI_KEY, wifi_cfg_dict)
        self._machine_config.load()
        wifi_cfg_dict = self._machine_config.get(MachineConfig.WIFI_KEY)
        assert(wifi_cfg_dict[MachineConfig.MODE_KEY] == MachineConfig.STA_MODE)


class MyUO(UOBase):

    def __init__(self, uo):
        super().__init__(uo)

class TestUO(unittest.TestCase):

    def setUp(self):
        self.uo = UO()

    def test_info(self):
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.uo.info("Hello")
            self.assertEqual(fake_out.getvalue().strip(), "INFO:  Hello")

    def test_warn(self):
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.uo.warn("Hello")
            self.assertEqual(fake_out.getvalue().strip(), "WARN:  Hello")

    def test_error(self):
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.uo.error("Hello")
            self.assertEqual(fake_out.getvalue().strip(), "ERROR: Hello")

    def test_debug(self):
        with patch('sys.stdout', new=StringIO()) as fake_out:
            self.uo.debug("Hello")
            self.assertEqual(fake_out.getvalue().strip(), "DEBUG: Hello")

    def test_extended_uo_base_info(self):
        with patch('sys.stdout', new=StringIO()) as fake_out:
            muo = MyUO(self.uo)
            muo.info("Hello")
            self.assertEqual(fake_out.getvalue().strip(), "INFO:  Hello")

    def test_extended_uo_base_warn(self):
        with patch('sys.stdout', new=StringIO()) as fake_out:
            muo = MyUO(self.uo)
            muo.warn("Hello")
            self.assertEqual(fake_out.getvalue().strip(), "WARN:  Hello")

    def test_extended_uo_base_error(self):
        with patch('sys.stdout', new=StringIO()) as fake_out:
            muo = MyUO(self.uo)
            muo.error("Hello")
            self.assertEqual(fake_out.getvalue().strip(), "ERROR: Hello")

    def test_extended_uo_base_debug(self):
        with patch('sys.stdout', new=StringIO()) as fake_out:
            muo = MyUO(self.uo)
            muo.debug("Hello")
            self.assertEqual(fake_out.getvalue().strip(), "DEBUG: Hello")

if __name__ == '__main__':
    unittest.main()
