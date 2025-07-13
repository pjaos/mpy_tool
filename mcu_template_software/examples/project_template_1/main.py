import time

try:
    count = 0
    while True:
        print(f"Running: {count}")
        time.sleep(0.1)
        count+=1
except KeyboardInterrupt:
    print("Interrupted!")