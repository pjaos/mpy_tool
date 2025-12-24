# Example Project 1

This is the most basic example.

It runs a loop that prints out an incrementing count.

When started it shows the incrementing count on the serial port as shown below.

```
INFO:  /dev/ttyUSB0: Running: 1
INFO:  /dev/ttyUSB0: Running: 2
INFO:  /dev/ttyUSB0: Running: 3
INFO:  /dev/ttyUSB0: Running: 4
INFO:  /dev/ttyUSB0: Running: 5
INFO:  /dev/ttyUSB0: Running: 6
INFO:  /dev/ttyUSB0: Running: 7
INFO:  /dev/ttyUSB0: Running: 8
INFO:  /dev/ttyUSB0: Running: 9
INFO:  /dev/ttyUSB0: Running: 10
INFO:  /dev/ttyUSB0: Running: 11
INFO:  /dev/ttyUSB0: Running: 12
INFO:  /dev/ttyUSB0: Running: 13
INFO:  /dev/ttyUSB0: Running: 14
INFO:  /dev/ttyUSB0: Running: 15
```

## Supported mpy_tool_gui functionality.
- The INSTALL tab can be used to load code onto an MCU.
- SERIAL PORT tab can be used to view and send data on the serial port.

If you wish to use this project the current main.py file can be changed from that detailed below.

```
import time

try:
    count = 0
    while True:
        print(f"Running: {count}")
        time.sleep(0.1)
        count+=1
except KeyboardInterrupt:
    print("Interrupted!")
```
