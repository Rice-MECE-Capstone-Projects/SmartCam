import pigpio
import time
import sys
import serial
from collections import deque

ESC_PIN = 18
STEERING_PIN = 13

CENTER = 1500
LEFT = 1100
RIGHT = 1800

pi = pigpio.pi()
if not pi.connected:
    print("Unable to connect to pigpiod")
    sys.exit(1)

try:
    ser = serial.Serial('/dev/serial0', 115200, timeout=0)
    print("UART connected")
except Exception as e:
    print(f"UART initialization failed: {e}")
    ser = None

# We originally used maxlen=4 at startup,
# but now allow it to temporarily grow to 20 to avoid overflow.
z_history = deque(maxlen=20)

def setup():
    pi.set_servo_pulsewidth(ESC_PIN, CENTER)
    pi.set_servo_pulsewidth(STEERING_PIN, CENTER)
    print("Initialization complete\n")

def read_latest_line(ser):
    line = None
    while True:
        chunk = ser.readline().decode('utf-8', errors='ignore').strip()
        if not chunk:
            break
        line = chunk
    return line

def handle_command(cmd):
    if cmd == 'w':
        pi.set_servo_pulsewidth(ESC_PIN, 1650)
    elif cmd == 'x':
        pi.set_servo_pulsewidth(ESC_PIN, 1200)
        time.sleep(0.02)
        pi.set_servo_pulsewidth(ESC_PIN, 1340)
    elif cmd == 'h':
        pi.set_servo_pulsewidth(ESC_PIN, CENTER)
    elif cmd == 'a':
        pi.set_servo_pulsewidth(STEERING_PIN, LEFT)
    elif cmd == 'd':
        pi.set_servo_pulsewidth(STEERING_PIN, RIGHT)
    elif cmd == 's':
        pi.set_servo_pulsewidth(STEERING_PIN, CENTER)

def loop():
    try:
        while True:
            line = read_latest_line(ser)

            if not line:
                time.sleep(0.002)
                continue

            print("Latest command:", line)

            try:
                x_str, z_str = line.split(',')
                x = float(x_str)
                z = float(z_str)
            except:
                continue

            # STOP has the highest priority
            if z < 0.3:
                print("z < 0.3 → STOP")
                z_history.clear()
                handle_command('h')
                continue

            # Record z
            z_history.append(z)

            # If z_history exceeds 5 entries → clear (to avoid backlog)
            if len(z_history) > 5:
                print("z_history exceeded 5 entries → All discarded (prevent backlog)")
                z_history.clear()
                continue

            # Steering control
            if x > 120:
                handle_command('d')
            elif x < -120:
                handle_command('a')
            else:
                handle_command('s')

            # Forward condition
            if any(v > 0.5 for v in z_history):
                handle_command('w')

            time.sleep(0.002)

    except KeyboardInterrupt:
        pi.set_servo_pulsewidth(ESC_PIN, 0)
        pi.set_servo_pulsewidth(STEERING_PIN, 0)
        pi.stop()
        if ser:
            ser.close()
        print("EXIT CLEAN")

if _name_ == "_main_":
    setup()
    loop()