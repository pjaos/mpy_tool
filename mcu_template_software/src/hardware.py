import sys
import os

from machine import Timer, reset_cause, deepsleep, reset
try:
    from micropython import const
except ImportError:
    def const(x): return x  # fallback for CPython


class Hardware(object):
    """@brief Provide functionality to ease cross platform use."""

    RPI_PICO_PLATFORM = const("rp2")
    ESP32_PLATFORM = const("esp32")

    @staticmethod
    def is_pico():
        """@return True if running on a RPi pico platform."""
        pico = False
        if sys.platform == Hardware.RPI_PICO_PLATFORM:
            pico = True
        return pico

    @staticmethod
    def is_esp32():
        """@return True if running on an ESP32 platform."""
        esp32 = False
        if sys.platform == Hardware.ESP32_PLATFORM:
            esp32 = True
        return esp32

    @staticmethod
    def get_timer():
        """@brief Get a machine.Timer instance.
           @return a Timer instance."""
        timer = None
        if Hardware.is_pico():
            timer = Timer(-1)
        else:
            timer = Timer(0)
        return timer

    @staticmethod
    def get_last_reset_cause(self):
        """@brief Get the reset cause.
                  See, https://docs.micropython.org/en/latest/library/machine.html#machine-constants."""
        return reset_cause()

    @staticmethod
    def deep_sleep(micro_seconds):
        """@brief Put the microcontroller to sleep for a period of time.
           @param micro_seconds The period of time to put the micro controller to sleep."""
        if micro_seconds > 0:
            deepsleep(micro_seconds)

    @staticmethod
    def reboot():
        """@brief Reboot this device."""
        # Ensure the file system is synced before we reboot.
        os.sync()
        # Issue
        # The following won't work on ESP32C6 as Timer support is yet to be added on
        # image provided by the mpy_tool_gui install tab.
        timer = Hardware.get_timer()
        # Reboot in 500 ms
        timer.init(mode=Timer.ONE_SHOT, period=500, callback=Hardware._do_reboot )

    def _do_reboot(_):
        """@brief Perform a device restart. The argument is the timer instance that called this method."""
        print("Rebooting MCU...")
        # !!! This does not always work
        reset()