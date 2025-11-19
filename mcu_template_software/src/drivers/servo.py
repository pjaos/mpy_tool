from machine import Pin, PWM

class ServoBase:
    """@brief A class that allows control of servos that use a PWM signal to control them.
              This has been tested on esp32 and RPi Pico W MCU's"""
    # These parameters must be set in subclasses for specific Servo types.
    PWM_FREQ_HZ = None
    MIN_PULE_WIDTH_MS = None # This sets the servo to one extreeme of it's movement.
    MAX_PULSE_WIDTH_MS = None # This sets the servo to the other extreeme of it's movement.
    MAX_ANGULAR_ROTATION = None  # This sets the angular rotation that the servo is capable of

    # The required parameter names
    REQUIRED_PARAMS = [
        "PWM_FREQ_HZ",
        "MIN_PULE_WIDTH_MS",
        "MAX_PULSE_WIDTH_MS",
        "MAX_ANGULAR_ROTATION",
    ]

    def __init__(self, gpio_pin, center_ref=True):
        """@brief Initialise this instance.
           @param gpio_pin The GPIO pin to use to control the servo."""
        self._center_ref = center_ref
        for name in self.REQUIRED_PARAMS:
            value = getattr(self.__class__, name)
            if value is None:
                raise Exception(f"{self.__class__.__name__}.{name} must be set in a subclass of ServoBase.")

        self._init_pin(gpio_pin)

    def _init_pin(self, gpio_pin):
        """@brief Initialise the gpio pin.
           @param gpio_pin The GPIO pin to use to control the servo."""
        self._pwm_pin = PWM(Pin(gpio_pin))
        cls = self.__class__
        # Extract parameters from the class
        pwm_freq = cls.PWM_FREQ_HZ
        self._pwm_pin.freq(pwm_freq)

    def _get_duty_reg(self, angle):
        """@brief Get the value of the duty cycle register to set.
        @param angle This is the angle to set the servo to.
                        This can be 0° +/- half the MAX_ANGULAR_ROTATION.
        @return The register value 0 - 1023 to achieve the required angle."""

        cls = self.__class__

        # Extract parameters from the class
        pwm_freq = cls.PWM_FREQ_HZ
        min_ms = cls.MIN_PULE_WIDTH_MS
        max_ms = cls.MAX_PULSE_WIDTH_MS
        max_angle = cls.MAX_ANGULAR_ROTATION

        if self._center_ref:
            # ---- 0) Compute allowed angle range ----
            half_range = max_angle / 2
            min_angle = -half_range
            max_angle = +half_range

            # ---- 1) Validate input angle ----
            if not (min_angle <= angle <= max_angle):
                raise ValueError(
                    f"Angle {angle}° is outside valid range "
                    f"{min_angle}° to {max_angle}° for {cls.__name__}."
                )
            # ---- 2) Normalise angle to -1..+1 ----
            normalised = angle / half_range  # exactly -1..+1 now

            # ---- 3) Map to pulse width (ms) ----
            pulse_ms = min_ms + (normalised + 1) * (max_ms - min_ms) / 2

        else:
            if angle < 0.0 or angle > max_angle:
                raise ValueError(
                    f"Angle {angle}° is outside valid range "
                    f"0° to {max_angle}° for {cls.__name__}."
                )
            else:
                if angle <= 0.0:
                    pulse_ms = min_ms
                else:
                    # ---- 1) Map to pulse width (ms) ----
                    pulse_ms = min_ms + ( (max_ms - min_ms) * ( angle / max_angle ) )

        # ---- 4) Convert pulse width → duty register ----
        period_ms = 1000.0 / pwm_freq             # e.g. 50 Hz → 20 ms period
        duty_fraction = pulse_ms / period_ms      # 0.0 → 1.0
        duty_value = int(duty_fraction * 1023)    # convert to register units

        # Clamp final result (theoretically unnecessary for valid input)
        if duty_value < 0:
            duty_value = 0
        elif duty_value > 1023:
            duty_value = 1023

        return duty_value

    def move(self, angle):
        """@brief Move the Servo to the correct position.
           @param This is the angle to set the servo to.
                  This can be 0° +/- half the MAX_ANGULAR_ROTATION."""
        duty_reg = self._get_duty_reg(angle)
        self._set_duty(duty_reg)

    def _set_duty(self, duty_reg):
        """@brief Set the duty cycle register.
           @param duty_reg The duty cycle register (0 - 1023)."""
        if hasattr(self._pwm_pin, "duty"):
            self._pwm_pin.duty(duty_reg)

        elif hasattr(self._pwm_pin, "duty_u16"):
            # On RPi Pico the PWM interface is different and accepts a 16 bit value (0 - 65535)
            # so needs scaling.
            u16_scale = duty_reg * 64
            self._pwm_pin.duty_u16(u16_scale)

        else:
            raise Exception("Unable to set PWM pin duty cycle.")

    def off(self):
        """@brief Set the servo motor off by setting the duty to 0 (no +ve pule on the gpio pin)"""
        self._set_duty(0)


class GS3630BBServo(ServoBase):
    """@brief Define the parameters for a Gotech GS-3630BB servo.
       To add a servo, the ServoBase class must be sub classed and the following
       parameters must be set, as shown below for this servo."""
    PWM_FREQ_HZ = 50
    MIN_PULE_WIDTH_MS = 0.5
    MAX_PULSE_WIDTH_MS = 2.5
    MAX_ANGULAR_ROTATION = 180

"""

# Example code

from time import sleep

# Move center +/- 90°
servo_1 = GS3630BBServo(21)
servo_1.move(-90)
sleep(2)
servo_1.move(90)

# Move 0° - 180°
#servo_1 = GS3630BBServo(21, center_ref=False)
#servo_1.move(0)
#sleep(2)
#servo_1.move(90)

sleep(2)
servo_1.off()

"""




