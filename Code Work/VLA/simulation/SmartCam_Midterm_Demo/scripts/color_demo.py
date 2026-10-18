#!/usr/bin/env python3
"""Live ROS2 color-goal navigation baseline. This is NOT a neural VLA.

No motion unless --drive and user types DRIVE.
Never use on physical hardware without a separate, tested safety controller.
"""
import argparse
import math
import sys
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image, LaserScan


def clamp(x, low, high):
    return max(low, min(high, x))


def detect_color(msg, target):
    """Sparse-pixel RGB/BGR target centroid; returns normalized horizontal error."""
    channels_by_encoding = {'rgb8': 3, 'bgr8': 3, 'rgba8': 4, 'bgra8': 4}
    enc = msg.encoding.lower()
    if enc not in channels_by_encoding:
        raise ValueError(f'Unsupported image encoding {msg.encoding!r}; expected rgb8/bgr8/rgba8/bgra8')
    chans = channels_by_encoding[enc]
    data = msg.data
    w, h, step = msg.width, msg.height, msg.step
    if not w or not h or len(data) < step * h:
        return None, 0
    if enc.startswith('rgb'):
        ro, go, bo = 0, 1, 2
    else:
        ro, go, bo = 2, 1, 0
    # Avoid the very top / bottom of image and reduce CPU overhead.
    sx = max(2, w // 120)
    sy = max(2, h // 90)
    count, xsum = 0, 0
    for y in range(h // 8, int(h * 0.86), sy):
        row = y * step
        for x in range(0, w, sx):
            idx = row + x * chans
            r, g, b = data[idx + ro], data[idx + go], data[idx + bo]
            if target == 'red':
                hit = r > 65 and r > g * 1.55 + 18 and r > b * 1.55 + 18
            else:
                hit = b > 65 and b > g * 1.5 + 18 and b > r * 1.5 + 18
            if hit:
                count += 1
                xsum += x
    if count < 12:
        return None, count
    # center error: -1 = left, +1 = right
    err = (2.0 * (xsum / count) / max(w - 1, 1)) - 1.0
    return err, count


class VisualNav(Node):
    def __init__(self, target, drive, duration):
        super().__init__('smartcam_midterm_color_baseline')
        self.target = target
        self.drive = drive
        self.duration = duration
        self.created = time.monotonic()
        self.last_image = None
        self.last_scan = None
        self.target_error = None
        self.target_pixels = 0
        self.min_front = None
        self.error_note = None
        self.last_print = 0.0
        self.done = False
        self.pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.create_subscription(Image, '/camera/image_raw', self.on_image, 10)
        self.create_subscription(LaserScan, '/scan', self.on_scan, 10)
        self.create_timer(0.1, self.control)

    def on_image(self, msg):
        self.last_image = time.monotonic()
        try:
            self.target_error, self.target_pixels = detect_color(msg, self.target)
            self.error_note = None
        except ValueError as exc:
            self.error_note = str(exc)
            self.target_error = None

    def on_scan(self, msg):
        self.last_scan = time.monotonic()
        vals = []
        for i, d in enumerate(msg.ranges):
            theta = msg.angle_min + i * msg.angle_increment
            if abs(theta) <= 0.42 and math.isfinite(d) and msg.range_min < d < msg.range_max:
                vals.append(d)
        self.min_front = min(vals) if vals else math.inf

    def control(self):
        now = time.monotonic()
        if now - self.created > self.duration:
            self.done = True
        state = 'TARGET LOST'
        v, omega = 0.0, 0.0
        if self.error_note:
            state = 'IMAGE ERROR: ' + self.error_note
        elif self.last_image is None or now - self.last_image > 0.8:
            state = 'WAITING /camera/image_raw'
        elif self.last_scan is None or now - self.last_scan > 0.8:
            state = 'WAITING /scan'
        elif self.target_error is None:
            state = 'TARGET NOT VISIBLE'
        elif self.min_front is not None and self.min_front <= 0.72:
            state = 'LIDAR STOP (<=0.72m)'
            self.done = True
        else:
            error = self.target_error
            omega = clamp(-0.35 * error, -0.20, 0.20)
            v = 0.0 if abs(error) > 0.23 else 0.08
            if self.min_front is not None and self.min_front < 1.15:
                v = min(v, 0.035)
            state = 'TURN TO CENTER' if v == 0 else 'APPROACH TARGET'

        if self.done:
            v, omega = 0.0, 0.0
        if self.drive:
            m = Twist()
            m.linear.x, m.angular.z = v, omega
            self.pub.publish(m)
        if now - self.last_print >= 0.8:
            dist = '?' if self.min_front is None else ('inf' if math.isinf(self.min_front) else f'{self.min_front:.2f}')
            err = '?' if self.target_error is None else f'{self.target_error:+.2f}'
            print(f'{state:23s} target={self.target:4s} err={err:6s} pixels={self.target_pixels:4d} '
                  f'LiDAR={dist:>5s}m -> v={v:+.3f} m/s omega={omega:+.3f} rad/s '
                  f'[{"DRIVE" if self.drive else "PREVIEW ONLY"}]', flush=True)
            self.last_print = now

    def stop(self):
        for _ in range(10):
            self.pub.publish(Twist())
            time.sleep(0.05)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=['red', 'blue'], required=True)
    parser.add_argument('--drive', action='store_true', help='Enable velocity publication (Gazebo simulation only)')
    parser.add_argument('--duration', type=float, default=20)
    args = parser.parse_args()
    if args.duration <= 0 or args.duration > 90:
        parser.error('duration must be between 0 and 90 seconds')
    print(f'Language instruction: Go to the {args.target} object.')
    print('RULE-BASED VISUAL BASELINE, NOT A TRAINED VLA MODEL')
    if args.drive:
        print('Simulation only. Keep Gazebo visible; stop via Ctrl+C, or PAUSE Gazebo if motion is unsafe.')
        if input('To enable movement, type DRIVE and press Enter: ').strip() != 'DRIVE':
            print('Canceled; no drive commands sent.')
            return
    else:
        print('PREVIEW ONLY: no velocity commands will be published.')
    rclpy.init()
    node = None
    try:
        node = VisualNav(args.target, args.drive, args.duration)
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.15)
    except KeyboardInterrupt:
        print('Interrupted. Stopping simulated robot.')
    finally:
        if node is not None:
            if args.drive and rclpy.ok():
                node.stop()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
