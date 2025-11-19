# servo.py
# Complete, feature-rich servo control module for ESP32 and Raspberry Pi Pico.
# Includes:
#   - Async sweeping
#   - Smooth motion with easing
#   - Per-servo calibration offset
#   - Range checking
#   - Auto PWM resolution detection (duty vs duty_u16)
#   - Logging callback
#   - Cleanup and safe shutdown

from machine import Pin, PWM
import uasyncio as asyncio
from time import sleep_ms


# ================================================================
# Exceptions
# ================================================================
class ServoRangeError(ValueError):
    """Raised when the requested angle exceeds real-world limits."""
    pass


# ================================================================
# Easing Functions
# ================================================================
def ease_linear(t):
    return t


def ease_in_out_quad(t):
    if t < 0.5:
        return 2 * t * t
    return 1 - pow(-2 * t + 2, 2) / 2


EASING = {
    "linear": ease_linear,
    "ease_in_out": ease_in_out_quad,
}


# ================================================================
# Base class
# ================================================================
class ServoBase:
    """
    Base class for PWM-based hobby servos.

    Subclasses must define:
        PWM_FREQ_HZ
        MIN_PULSE_US
        MAX_PULSE_US
        MAX_ANGLE_DEG

    Optional:
        REAL_MIN_ANGLE
        REAL_MAX_ANGLE
    """

    PWM_FREQ_HZ = None
    MIN_PULSE_US = None
    MAX_PULSE_US = None
    MAX_ANGLE_DEG = None

    REAL_MIN_ANGLE = None
    REAL_MAX_ANGLE = None

    REQUIRED_PARAMS = [
        "PWM_FREQ_HZ",
        "MIN_PULSE_US",
        "MAX_PULSE_US",
        "MAX_ANGLE_DEG",
    ]

    # --------------------------------------------------------------
    # Constructor
    # --------------------------------------------------------------
    def __init__(self, gpio_pin, *,
                 freq=None,
                 pulse_offset_us=0,
                 safe=True):
        # Validate subclass
        for name in self.REQUIRED_PARAMS:
            if getattr(self.__class__, name) is None:
                raise Exception(f"{self.__class__.__name__}.{name} must be defined.")

        # Store calibration offset
        self._offset_us = int(pulse_offset_us)

        # Create PWM
        self._pwm = PWM(Pin(gpio_pin))
        self.pwm_freq = freq if freq is not None else self.__class__.PWM_FREQ_HZ
        self._pwm.freq(self.pwm_freq)

        # Precompute
        self.min_us = int(self.__class__.MIN_PULSE_US)
        self.max_us = int(self.__class__.MAX_PULSE_US)
        self.max_angle = float(self.__class__.MAX_ANGLE_DEG)
        self._period_us = int(1_000_000 // self.pwm_freq)

        # Detect PWM resolution
        self._has_duty = hasattr(self._pwm, "duty")
        self._has_duty_u16 = hasattr(self._pwm, "duty_u16")
        self._duty_max = 1023 if self._has_duty else 65535

        self.angle = 0
        self._last_fraction = 0.0
        self._safe = safe

        # async sweep task
        self._sweep_task = None

        # Optional movement logging callback
        self.on_move = None

    # --------------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------------
    def close(self):
        """Detach PWM and stop sweeping."""
        self.cancel_sweep()
        try:
            self._pwm.deinit()
        except:
            pass

    def __del__(self):
        """Automatic cleanup when collected."""
        try:
            self.close()
        except:
            pass

    # --------------------------------------------------------------
    # Offset control
    # --------------------------------------------------------------
    def set_offset(self, offset_us):
        self._offset_us = int(offset_us)

    def get_offset(self):
        return self._offset_us

    # --------------------------------------------------------------
    # Calibration tool
    # --------------------------------------------------------------
    def calibrate_center(self, *, step=5):
        """
        Moves the servo to logical center (0° or 90° depending on mode),
        and lets the user adjust using the offset.

        Usage:
            servo.calibrate_center()
        """
        print("Starting interactive calibration.")
        print("Press Ctrl+C to exit calibration.\n")

        try:
            angle = 0 if self.max_angle == 180 else self.max_angle / 2
            self.move(angle, center_ref=True)

            while True:
                print(f"Current offset: {self._offset_us} us")
                print("Adjust offset: (+/- integer, or 'q' to quit): ", end="")
                s = input()

                if s.lower() == "q":
                    print("Calibration finished.")
                    break

                try:
                    d = int(s)
                except:
                    print("Invalid input")
                    continue

                self._offset_us += d
                self.move(angle, center_ref=True)

        except KeyboardInterrupt:
            print("Calibration cancelled.")

    # --------------------------------------------------------------
    # Validation
    # --------------------------------------------------------------
    def _validate_real_limits(self, angle):
        lo = self.__class__.REAL_MIN_ANGLE
        hi = self.__class__.REAL_MAX_ANGLE
        if lo is not None and angle < lo:
            raise ServoRangeError(f"{angle}° < real min {lo}°")
        if hi is not None and angle > hi:
            raise ServoRangeError(f"{angle}° > real max {hi}°")

    # --------------------------------------------------------------
    # Angle → pulse
    # --------------------------------------------------------------
    def _pulse_us_from_angle(self, angle, center_ref):
        if center_ref:
            half = self.max_angle / 2
            if not (-half <= angle <= half):
                raise ValueError(f"{angle} outside {-half} .. {half}")
            normalised = (angle + half) / (2 * half)
        else:
            if not (0 <= angle <= self.max_angle):
                raise ValueError(f"{angle} outside 0 .. {self.max_angle}")
            normalised = angle / self.max_angle

        return int(self.min_us + normalised * (self.max_us - self.min_us))

    def _apply_offset(self, pulse_us):
        return pulse_us + self._offset_us

    def _pulse_to_fraction(self, pulse_us):
        frac = pulse_us / self._period_us
        return max(0.0, min(1.0, frac))

    def _set_by_fraction(self, fraction):
        if self._has_duty_u16:
            self._pwm.duty_u16(int(fraction * 65535))
        else:
            self._pwm.duty(int(fraction * 1023))

        self._last_fraction = fraction

    # --------------------------------------------------------------
    # Public movement API
    # --------------------------------------------------------------
    def move(self, angle, *, center_ref=True, clamp=False, safe=True):
        if safe and self._safe:
            self._validate_real_limits(angle)

        # get pulse
        try:
            pulse = self._pulse_us_from_angle(angle, center_ref)
        except ValueError:
            if not clamp:
                raise
            # clamp
            if center_ref:
                half = self.max_angle / 2
                angle = max(min(angle, half), -half)
            else:
                angle = max(min(angle, self.max_angle), 0)
            pulse = self._pulse_us_from_angle(angle, center_ref)

        # apply calibration
        pulse = self._apply_offset(pulse)
        fraction = self._pulse_to_fraction(pulse)
        self._set_by_fraction(fraction)

        self.angle = angle

        # logging hook
        if self.on_move:
            try:
                self.on_move(angle, pulse)
            except:
                pass

    def move_us(self, pulse_us):
        """Raw microsecond pulse (offset applied automatically)."""
        pulse = self._apply_offset(int(pulse_us))
        fraction = self._pulse_to_fraction(pulse)
        self._set_by_fraction(fraction)

    def off(self):
        self._set_by_fraction(0)

    def hold(self):
        self._set_by_fraction(self._last_fraction)

    # --------------------------------------------------------------
    # Async sweep
    # --------------------------------------------------------------
    async def _async_sweep(self, start, end, duration, *,
                           center_ref=True, steps=60, loop=False,
                           easing="linear"):
        if steps < 2:
            steps = 2

        ease_fn = EASING.get(easing, ease_linear)

        while True:
            # forward
            for i in range(steps + 1):
                t = i / steps
                t = ease_fn(t)
                a = start + (end - start) * t
                self.move(a, center_ref=center_ref, clamp=True)
                await asyncio.sleep(duration / steps)

            if not loop:
                break

            # reverse
            for i in range(steps + 1):
                t = i / steps
                t = ease_fn(t)
                a = end + (start - end) * t
                self.move(a, center_ref=center_ref, clamp=True)
                await asyncio.sleep(duration / steps)

    def sweep_async(self, start, end, duration, *,
                    center_ref=True, steps=60, loop=False,
                    easing="linear"):
        if self._sweep_task:
            try:
                self._sweep_task.cancel()
            except:
                pass

        loop_obj = asyncio.get_event_loop()
        self._sweep_task = loop_obj.create_task(
            self._async_sweep(start, end, duration,
                              center_ref=center_ref,
                              steps=steps,
                              loop=loop,
                              easing=easing)
        )
        return self._sweep_task

    def cancel_sweep(self):
        if self._sweep_task:
            try:
                self._sweep_task.cancel()
            except:
                pass
            self._sweep_task = None

    def sweep_blocking(self, start, end, duration, *,
                       center_ref=True, steps=60, easing="linear"):
        async def _run():
            await self._async_sweep(start, end, duration,
                                    center_ref=center_ref,
                                    steps=steps,
                                    loop=False,
                                    easing=easing)
        asyncio.run(_run())

    # --------------------------------------------------------------
    # Smooth async motion
    # --------------------------------------------------------------
    async def move_smooth(self, target_angle, speed_deg_s=60, *,
                          center_ref=True, clamp=True, safe=True,
                          steps=50, easing="ease_in_out"):

        current = self.angle
        diff = target_angle - current

        duration = abs(diff) / speed_deg_s
        if duration <= 0:
            return

        ease_fn = EASING.get(easing, ease_in_out_quad)

        for i in range(steps):
            t = (i + 1) / steps
            t = ease_fn(t)
            a = current + diff * t
            self.move(a, center_ref=center_ref, clamp=clamp, safe=safe)
            await asyncio.sleep(duration / steps)

        self.angle = target_angle


# ================================================================
# Example subclasses
# ================================================================
class GS3630BBServo(ServoBase):
    PWM_FREQ_HZ = 50
    MIN_PULSE_US = 500
    MAX_PULSE_US = 2500
    MAX_ANGLE_DEG = 180


class SG90Servo(ServoBase):
    PWM_FREQ_HZ = 50
    MIN_PULSE_US = 500
    MAX_PULSE_US = 2400
    MAX_ANGLE_DEG = 180


"""

# ================================================================
# Example usage (non-blocking and async)
# ================================================================
async def sweep_demo():
    servo = GS3630BBServo(21)
    servo.sweep_async(-90, 90, 4.0, steps=80, loop=True, easing="ease_in_out")
    await asyncio.sleep(20)
    servo.cancel_sweep()
    servo.off()


async def demo_smooth_move():
    servo = GS3630BBServo(21)
    print("Start smooth move")
    await servo.move_smooth(70, speed_deg_s=10)
    servo.off()
    print("Finished")

def sync_demo():
    try:
        s = GS3630BBServo(21, pulse_offset_us=0)   # change pin number as needed
        # Uncomment to run sweep asynchronously.
        #s.sweep_blocking(-90, 100, 4.0, center_ref=True, steps=10)

        # Uncomment to calibrate set the offset
        # s.calibrate_center()

        print("Center")
        s.move(0, center_ref=True)
        sleep_ms(1000)
        print("Left")
        s.move(-90, center_ref=True)
        sleep_ms(1000)
        print("Right")
        s.move(90, center_ref=True)
        sleep_ms(1000)
        s.off()

    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    # Uncomment to run demos
    #sync_demo()
    #asyncio.run(sweep_demo())
    #asyncio.run(demo_smooth_move())
    pass

"""