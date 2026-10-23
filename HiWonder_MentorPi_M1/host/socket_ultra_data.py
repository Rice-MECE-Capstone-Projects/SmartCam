import socket
import time
from gpiozero import DistanceSensor

# Set up the UDP socket (The Walkie-Talkie)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
DOCKER_IP = "127.0.0.1" # Sending to local machine
PORT = 9090

# Set up the Sensor (Change pins to match your wiring)
sensor = DistanceSensor(echo=24, trigger=23, max_distance=2.0)
safe_distance = 0.20 # 20 centimeters

print("Host Sensor Active. Beaming data to Docker...")

try:
    while True:
        current_distance = sensor.distance
	
	# Grab the exact time right before we send
        current_time = time.time()
        
        if current_distance < safe_distance:
            message = f"STOP|{current_time}"
            # print(f"OBSTACLE! ({current_distance:.2f}m) -> Beaming STOP")
        else:
            message = f"SAFE|{current_time}"
            
        # Send the message to the Docker container
        sock.sendto(message.encode('utf-8'), (DOCKER_IP, PORT))
        
        # Check the sensor 20 times a second
        time.sleep(0.05)

except KeyboardInterrupt:
    print("Shutting down sensor.")
finally:
    sock.close()
