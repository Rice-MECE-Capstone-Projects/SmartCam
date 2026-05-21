#!/usr/bin/env python3
# encoding: utf-8
import time
import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

import sys, select, os
import tty, termios
import socket
import threading

settings = termios.tcgetattr(sys.stdin)
LIN_VEL = 0.21  # 0.5 gz
STEER = 0.36    # 0.8 gz
ANG_VEL = LIN_VEL/(0.145/math.tan(STEER))

msg = """
Control Your Robot!
---------------------------
Moving around:
        w
   a    s    d
CTRL-C to quit
"""

def getKey(settings):
    tty.setraw(sys.stdin.fileno())
    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
    if rlist:
        key = sys.stdin.read(1)
    else:
        key = ''

    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
    return key

class TeleopControl(Node):
    def __init__(self, name):
        rclpy.init()
        super().__init__(name)

        # Make sure this matches the topic your motor controller expects
        self.cmd_vel = self.create_publisher(Twist,"controller/cmd_vel", 1)

        # --- SAFETY STATE VARIABLE ---
        self.is_safe = True

        # --- START UDP LISTENER THREAD ---
        self.udp_thread = threading.Thread(target=self.listen_to_host)
        self.udp_thread.daemon = True
        self.udp_thread.start()

        control_linear_vel = 0.0
        control_angular_vel = 0.0
        last_x = 0
        last_z = 0
        count = 0

        try:
            print(msg)
            while rclpy.ok():
                key = getKey(settings)

                # --- SENSOR OVERRIDE LOGIC ---
                if not self.is_safe:
                    # Ignore the keyboard entirely, force velocities to 0
                    control_linear_vel = 0.0
                    control_angular_vel = 0.0
                    count = 0
                else:
                    # Normal teleop logic
                    if key == 'w':
                        count = 0
                        control_linear_vel = LIN_VEL
                    elif key == 'a':
                        count = 0
                        control_angular_vel = ANG_VEL
                    elif key == 'd':
                        count = 0
                        control_angular_vel = -ANG_VEL
                    elif key == 's':
                        count = 0
                        control_linear_vel = -LIN_VEL
                    elif key == '':
                        count += 1
                        if count > 5:
                            count = 0
                            if control_angular_vel != 0:
                                control_angular_vel = 0.0
                                control_linear_vel = 0.0
                    else:
                        count = 0
                        if (key == '\x03'):
                            break

                twist = Twist()

                twist.linear.x = control_linear_vel
                twist.linear.y = 0.0
                twist.linear.z = 0.0

                twist.angular.x = 0.0
                twist.angular.y = 0.0
                twist.angular.z = control_angular_vel

                if last_x != control_linear_vel or last_z != control_angular_vel or control_angular_vel != 0:
                    self.cmd_vel.publish(twist)

                last_x = control_linear_vel
                last_z = control_angular_vel
        except BaseException as e:
            print(e)

        finally:
            twist = Twist()
            twist.linear.x = 0.0
            twist.linear.y = 0.0
            twist.linear.z = 0.0
            twist.angular.x = 0.0
            twist.angular.y = 0.0
            twist.angular.z = 0.0
            self.cmd_vel.publish(twist)

            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)

    # --- UDP BACKGROUND FUNCTION ---
    def listen_to_host(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", 9090))
        
        while True:
            try:
                data, _ = sock.recvfrom(1024)
                # 1. Immediately stamp the arrival time
                arrival_time = time.time() 
                
                # 2. Decode and split the payload
                payload = data.decode('utf-8')
                command, sent_time_str = payload.split('|')
                
                # 3. Calculate latency in milliseconds
                latency_ms = (arrival_time - float(sent_time_str)) * 1000.0
                
                if command == "STOP":
                    if self.is_safe:
                        self.get_logger().warn(f"HOST SAYS STOP! Brakes applied. (Latency: {latency_ms:.3f} ms)")
                        # Print with \r\n to format correctly while in raw terminal mode
                        # print("\r\n[!] OBSTACLE DETECTED! Brakes engaged. Keyboard ignored.\r")
                    self.is_safe = False
                elif command == "SAFE":
                    if not self.is_safe:
                        print("\r\n[+] PATH CLEAR! Manual control restored.\r")
                    self.is_safe = True
            except Exception:
                pass

def main():
    node = TeleopControl('teleop_control')
    rclpy.spin(node)

if __name__ == "__main__":
    main()
