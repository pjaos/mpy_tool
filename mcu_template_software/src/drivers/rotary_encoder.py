# MIT License (MIT)
# Copyright (c) 2022 Mike Teachman
# Copyright (c) 2021 Eric Moyer
# Copyright (c) 2023 Paul Austen
# https://opensource.org/licenses/MIT

# Platform-independent MicroPython code for the rotary encoder module

# Documentation:
#   https://github.com/MikeTeachman/micropython-rotary

from machine import Pin, Timer
import utime

_DIR_CW = 0x10  # Clockwise step
_DIR_CCW = 0x20  # Counter-clockwise step

# Rotary Encoder States
_R_START = 0x0
_R_CW_1 = 0x1
_R_CW_2 = 0x2
_R_CW_3 = 0x3
_R_CCW_1 = 0x4
_R_CCW_2 = 0x5
_R_CCW_3 = 0x6
_R_ILLEGAL = 0x7

_transition_table = [

    # |------------- NEXT STATE -------------|            |CURRENT STATE|
    # CLK/DT    CLK/DT     CLK/DT    CLK/DT
    #   00        01         10        11
    [_R_START, _R_CCW_1, _R_CW_1, _R_START],             # _R_START
    [_R_CW_2, _R_START, _R_CW_1, _R_START],             # _R_CW_1
    [_R_CW_2, _R_CW_3, _R_CW_1, _R_START],             # _R_CW_2
    [_R_CW_2, _R_CW_3, _R_START, _R_START | _DIR_CW],   # _R_CW_3
    [_R_CCW_2, _R_CCW_1, _R_START, _R_START],             # _R_CCW_1
    [_R_CCW_2, _R_CCW_1, _R_CCW_3, _R_START],             # _R_CCW_2
    [_R_CCW_2, _R_START, _R_CCW_3, _R_START | _DIR_CCW],  # _R_CCW_3
    [_R_START, _R_START, _R_START, _R_START]]             # _R_ILLEGAL

_transition_table_half_step = [
    [_R_CW_3, _R_CW_2, _R_CW_1, _R_START],
    [_R_CW_3 | _DIR_CCW, _R_START, _R_CW_1, _R_START],
    [_R_CW_3 | _DIR_CW, _R_CW_2, _R_START, _R_START],
    [_R_CW_3, _R_CCW_2, _R_CCW_1, _R_START],
    [_R_CW_3, _R_CW_2, _R_CCW_1, _R_START | _DIR_CW],
    [_R_CW_3, _R_CCW_2, _R_CW_3, _R_START | _DIR_CCW],
    [_R_START, _R_START, _R_START, _R_START],
    [_R_START, _R_START, _R_START, _R_START]]

_STATE_MASK = 0x07
_DIR_MASK = 0x30


def _wrap(value, incr, lower_bound, upper_bound):
    range = upper_bound - lower_bound + 1
    value = value + incr

    if value < lower_bound:
        value += range * ((lower_bound - value) // range + 1)

    return lower_bound + (value - lower_bound) % range


def _bound(value, incr, lower_bound, upper_bound):
    return min(upper_bound, max(lower_bound, value + incr))


def _trigger(rotary_instance):
    for listener in rotary_instance._listener:
        listener()


class Rotary(object):

    RANGE_UNBOUNDED = 1
    RANGE_WRAP = 2
    RANGE_BOUNDED = 3

    def __init__(self, min_val, max_val, incr, reverse,
                 range_mode, half_step, invert):
        self._min_val = min_val
        self._max_val = max_val
        self._incr = incr
        self._reverse = -1 if reverse else 1
        self._range_mode = range_mode
        self._value = min_val
        self._state = _R_START
        self._half_step = half_step
        self._invert = invert
        self._listener = []

    def set(self, value=None, min_val=None, incr=None,
            max_val=None, reverse=None, range_mode=None):
        # disable DT and CLK pin interrupts
        self._hal_disable_irq()

        if value is not None:
            self._value = value
        if min_val is not None:
            self._min_val = min_val
        if max_val is not None:
            self._max_val = max_val
        if incr is not None:
            self._incr = incr
        if reverse is not None:
            self._reverse = -1 if reverse else 1
        if range_mode is not None:
            self._range_mode = range_mode
        self._state = _R_START

        # enable DT and CLK pin interrupts
        self._hal_enable_irq()

    def value(self):
        return self._value

    def reset(self):
        self._value = 0

    def close(self):
        self._hal_close()

    def add_listener(self, _listener):
        self._listener.append(_listener)

    def remove_listener(self, _listener):
        if _listener not in self._listener:
            raise ValueError('{} is not an installed listener'.format(_listener))
        self._listener.remove(_listener)

    def _process_rotary_pins(self, pin):
        old_value = self._value
        clk_dt_pins = (self._hal_get_clk_value() <<
                       1) | self._hal_get_dt_value()

        if self._invert:
            clk_dt_pins = ~clk_dt_pins & 0x03

        # Determine next state
        if self._half_step:
            self._state = _transition_table_half_step[self._state &
                                                      _STATE_MASK][clk_dt_pins]
        else:
            self._state = _transition_table[self._state &
                                            _STATE_MASK][clk_dt_pins]
        direction = self._state & _DIR_MASK

        incr = 0
        if direction == _DIR_CW:
            incr = self._incr
        elif direction == _DIR_CCW:
            incr = -self._incr

        incr *= self._reverse

        if self._range_mode == self.RANGE_WRAP:
            self._value = _wrap(
                self._value,
                incr,
                self._min_val,
                self._max_val)
        elif self._range_mode == self.RANGE_BOUNDED:
            self._value = _bound(
                self._value,
                incr,
                self._min_val,
                self._max_val)
        else:
            self._value = self._value + incr

        try:
            if old_value != self._value and len(self._listener) != 0:
                _trigger(self)
        except BaseException:
            pass


IRQ_RISING_FALLING = Pin.IRQ_RISING | Pin.IRQ_FALLING


class RotaryIRQ(Rotary):
    def __init__(
        self,
        pin_num_clk,
        pin_num_dt,
        pin_sw=None,
        min_val=0,
        max_val=10,
        incr=1,
        reverse=False,
        range_mode=Rotary.RANGE_UNBOUNDED,
        pull_up=False,
        half_step=False,
        invert=False,
        sw_down_callback=None,
        sw_up_callback=None,
    ):
        super().__init__(min_val, max_val, incr, reverse, range_mode, half_step, invert)
        self._pin_sw = None
        self._sw_down_callback = sw_down_callback
        self._sw_up_callback = sw_up_callback
        self._swDebounceTimer = Timer(-1)

        if pull_up:
            self._pin_clk = Pin(pin_num_clk, Pin.IN, Pin.PULL_UP)
            self._pin_dt = Pin(pin_num_dt, Pin.IN, Pin.PULL_UP)
            # If we have the args to setup the SW pin callback
            if pin_sw is not None:
                self._pin_sw = Pin(pin_sw, Pin.IN, Pin.PULL_UP)

        else:
            self._pin_clk = Pin(pin_num_clk, Pin.IN)
            self._pin_dt = Pin(pin_num_dt, Pin.IN)
            # If we have the args to setup the SW pin callback
            if pin_sw is not None:
                self._pin_sw = Pin(pin_sw, Pin.IN, Pin.PULL_UP)

        self._hal_enable_irq()
        self._swDownTime = None
        self._swUpTime = None
        self._lastSWDownSec = None

    def _sw_callback(self, pin):
        self._disable_sw_irq()
        self._swDebounceTimer.init(
            mode=Timer.PERIODIC,
            period=10,
            callback=self._re_enable_sw_irq)
        if self._sw_down_callback:
            self._sw_down_callback()
        if self._swDownTime is None:
            self._swDownNS = utime.time_ns()

    def _re_enable_sw_irq(self, timer):
        if self._pin_sw.value():
            self._enable_sw_irq()
            self._swDebounceTimer.deinit()
            self._swUpTime = utime.time_ns()
            self._lastSWDownSec = float(self._swUpTime - self._swDownNS) / 1E9
            self._swDownTime = None
            self._swUpTime = None
            if self._sw_up_callback:
                self._sw_up_callback()

    def get_sw_down_sec(self):
        return self._lastSWDownSec

    def _enable_clk_irq(self):
        self._pin_clk.irq(self._process_rotary_pins, IRQ_RISING_FALLING)

    def _enable_dt_irq(self):
        self._pin_dt.irq(self._process_rotary_pins, IRQ_RISING_FALLING)

    def _enable_sw_irq(self):
        if self._pin_sw:
            self._pin_sw.irq(self._sw_callback, Pin.IRQ_FALLING)

    def _disable_clk_irq(self):
        self._pin_clk.irq(None, 0)

    def _disable_dt_irq(self):
        self._pin_dt.irq(None, 0)

    def _disable_sw_irq(self):
        if self._pin_sw:
            self._pin_sw.irq(None, 0)

    def _hal_get_clk_value(self):
        return self._pin_clk.value()

    def _hal_get_dt_value(self):
        return self._pin_dt.value()

    def _hal_enable_irq(self):
        self._enable_clk_irq()
        self._enable_dt_irq()
        self._enable_sw_irq()

    def _hal_disable_irq(self):
        self._disable_clk_irq()
        self._disable_dt_irq()
        self._disable_sw_irq()

    def _hal_close(self):
        self._hal_disable_irq()


"""
# Example code
import time

class RotarySWTest(object):

    CLK_GPIO = 25
    DT_GPIO = 26
    SW_GPIO = 27

    def __init__(self):
        self._rotaryIRQ = RotaryIRQ(pin_num_clk=RotarySWTest.CLK_GPIO,
                      pin_num_dt=RotarySWTest.DT_GPIO,
                      pin_sw=RotarySWTest.SW_GPIO,
                      min_val=0,
                      max_val=500,
                      reverse=True,
                      pull_up=True,
                      range_mode=RotaryIRQ.RANGE_WRAP,
                      sw_down_callback=self.sw_down,
                      sw_up_callback=self.sw_up,)

    def sw_down(self):
        print(f"PJA:
    def sw_up(self):
        print(f"SW released. Down for {self._rotaryIRQ.get_sw_down_sec()} seconds.")

    def run(self):
        val_old = self._rotaryIRQ.value()
        while True:
            val_new = self._rotaryIRQ.value()

            if val_old != val_new:
                val_old = val_new
                print('result =', val_new)

        time.sleep_ms(100)

rst = RotarySWTest()
rst.run()
"""
