#!/usr/bin/env python3
"""Idempotent Gazebo Classic scene setup for SmartCam RGB target imitation."""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, *, check=True, timeout=25):
    return subprocess.run(args, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=timeout, check=check)


def pose(name):
    result = run(["gz", "model", "-m", name, "-p"], check=False, timeout=6)
    if result.returncode != 0:
        return None
    values = result.stdout.strip().split()
    if len(values) != 6:
        return None
    try:
        return [float(v) for v in values]
    except ValueError:
        return None


def set_pose(name, x, y, z, yaw=0.0):
    result = run(["gz", "model", "-m", name,
                  "-x", str(x), "-y", str(y), "-z", str(z),
                  "-R", "0", "-P", "0", "-Y", str(yaw)], timeout=10)
    if result.stdout.strip():
        print(result.stdout.strip())
    time.sleep(0.15)
    updated = pose(name)
    if updated is None:
        raise RuntimeError(f"Cannot read back pose of {name}")
    if abs(updated[0] - x) > 0.12 or abs(updated[1] - y) > 0.12:
        raise RuntimeError(f"Pose mismatch for {name}: expected ({x}, {y}), got {updated}")
    return updated


def ensure_target(name, x, y):
    existing = pose(name)
    if existing is not None:
        return set_pose(name, x, y, 0.35)
    sdf = ROOT / "scenes" / f"{name}.sdf"
    cmd = ["ros2", "run", "gazebo_ros", "spawn_entity.py", "-entity", name,
           "-file", str(sdf), "-x", str(x), "-y", str(y), "-z", "0.35"]
    created = run(cmd, timeout=35)
    print(created.stdout.strip())
    if pose(name) is None:
        raise RuntimeError(f"Target did not spawn: {name}")
    return pose(name)


def prepare(scene="A", reset=True):
    if not shutil.which("gz") or not shutil.which("ros2"):
        raise RuntimeError("Missing gz or ros2; source ROS2 Humble setup first")
    if pose("my_bot") is None:
        raise RuntimeError("Gazebo my_bot not found. Launch articubot_one before setup")

    if scene == "A":
        red_y, blue_y = 0.8, -0.8
    elif scene == "B":
        red_y, blue_y = -0.8, 0.8
    else:
        raise ValueError("Scene must be A or B")

    print(f"Configuring scene {scene} ...")
    print("red_target:", ensure_target("red_target", 2.0, red_y))
    print("blue_target:", ensure_target("blue_target", 2.0, blue_y))
    if reset:
        # Only intended for Gazebo simulation, never for a real robot.
        try:
            run(["ros2", "topic", "pub", "--once", "/cmd_vel",
                 "geometry_msgs/msg/Twist",
                 "{linear: {x: 0.0}, angular: {z: 0.0}}"], timeout=8)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print("WARNING: Could not send stop via /cmd_vel; inspect other teleop nodes")
        print("my_bot:", set_pose("my_bot", -0.7, 0.0, 0.033, 0.0))
        time.sleep(1.0)
    return {"scene": scene, "red_target": pose("red_target"),
            "blue_target": pose("blue_target"), "robot": pose("my_bot")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=["A", "B"], default="A")
    parser.add_argument("--no-reset", action="store_true")
    args = parser.parse_args()
    try:
        prepare(args.scene, reset=not args.no_reset)
        print("SCENE READY; inspect /camera/image_raw for visibility.")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
