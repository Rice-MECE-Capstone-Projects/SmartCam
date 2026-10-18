#!/usr/bin/env python3
"""Read-only ROS/Gazebo preflight checks."""

import shutil
import subprocess
import sys

NEEDED = {
    "/camera/image_raw": "sensor_msgs/msg/Image",
    "/scan": "sensor_msgs/msg/LaserScan",
    "/diff_cont/odom": "nav_msgs/msg/Odometry",
    "/diff_cont/cmd_vel_unstamped": "geometry_msgs/msg/Twist",
    "/clock": "rosgraph_msgs/msg/Clock",
}


def run(cmd, timeout=12):
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout)


def check():
    for exe in ("ros2", "gz", "/usr/bin/python3"):
        if not shutil.which(exe):
            raise RuntimeError(f"Missing {exe}. Source ROS2 Humble first.")
    p = run(["pgrep", "-x", "gzserver"])
    if p.returncode != 0:
        raise RuntimeError("Gazebo Classic gzserver not running")
    p = run(["gz", "model", "-m", "my_bot", "-p"])
    if p.returncode != 0 or len(p.stdout.strip().split()) != 6:
        raise RuntimeError("Gazebo entity my_bot not available")
    print("Gazebo my_bot:", p.stdout.strip())
    p = run(["ros2", "topic", "list", "-t"], timeout=15)
    if p.returncode != 0:
        raise RuntimeError(f"ROS2 topic list failed: {p.stderr.strip()}")
    missing = []
    for topic, msg_type in NEEDED.items():
        entry = f"{topic} [{msg_type}]"
        exists = entry in p.stdout.splitlines()
        print(("PASS" if exists else "MISSING") + " ", entry)
        if not exists:
            missing.append(topic)
    p = run(["ros2", "control", "list_controllers"], timeout=12)
    if p.returncode == 0:
        print("Controllers:\n" + p.stdout.strip())
        if not ("diff_cont" in p.stdout and "active" in p.stdout):
            missing.append("active diff_cont")
    else:
        missing.append("controller_manager")
    if missing:
        raise RuntimeError("Required checks failed: " + ", ".join(missing))
    print("DOCTOR PASS: ROS graph and Gazebo entity found")


if __name__ == "__main__":
    try:
        check()
    except Exception as exc:
        print("DOCTOR FAIL:", exc, file=sys.stderr)
        sys.exit(1)
