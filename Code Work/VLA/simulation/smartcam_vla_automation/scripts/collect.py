#!/usr/bin/env python3
"""One-terminal simulation-only teleop + rosbag episode recording.

The operator MUST drive; this script never invents demonstration actions.
"""

import argparse
import csv
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import termios
import time
import tty
from datetime import datetime
from pathlib import Path

from doctor import check as doctor_check
from scene import prepare as prepare_scene, pose

MOVES = {
    "w": (0.10, 0.00, 0.90),
    "s": (-0.05, 0.00, 0.50),
    "a": (0.00, 0.20, 0.65),
    "d": (0.00, -0.20, 0.65),
}
TOPICS = [
    "/camera/image_raw", "/camera/camera_info", "/diff_cont/odom",
    "/scan", "/cmd_vel", "/diff_cont/cmd_vel_unstamped", "/clock",
]


def stop_recorder(rec):
    if rec.poll() is not None:
        return rec.returncode
    try:
        os.killpg(rec.pid, signal.SIGINT)
    except ProcessLookupError:
        return rec.poll()
    try:
        return rec.wait(timeout=35)
    except subprocess.TimeoutExpired:
        print("WARNING: recorder slow to stop; requesting graceful termination")
        os.killpg(rec.pid, signal.SIGTERM)
        try:
            return rec.wait(timeout=12)
        except subprocess.TimeoutExpired:
            print("ERROR: recorder still running; investigate before another run")
            return None


def run(args):
    if not sys.stdin.isatty():
        raise RuntimeError("Use an interactive terminal with keyboard focus")
    if args.max_seconds < 5 or args.max_seconds > 300:
        raise RuntimeError("--max-seconds must be between 5 and 300")

    doctor_check()
    # Do not silently compete with a previous keyboard teleop node.
    other = subprocess.run(["ros2", "node", "list"], capture_output=True, text=True, timeout=12)
    if "/smartcam_keyboard_teleop" in other.stdout.splitlines():
        raise RuntimeError("Existing smartcam_keyboard_teleop node detected: stop it first")

    bag_root = Path.home() / "smartcam_data" / "bags"
    bag_root.mkdir(parents=True, exist_ok=True)
    name = args.episode or (f"{args.scene.lower()}_{args.target}_" +
                            datetime.now().strftime("%Y%m%d_%H%M%S"))
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
        raise RuntimeError("Episode ID must contain only letters, digits, '_' or '-'")
    bag_dir = bag_root / name
    meta_path = bag_root / f"{name}.task.json"
    log_path = bag_root / f"{name}.recorder.log"
    if any(p.exists() for p in (bag_dir, meta_path, log_path)):
        raise RuntimeError(f"Episode already exists; never overwriting: {name}")
    if shutil.disk_usage(str(bag_root)).free < 2 * 1024**3:
        raise RuntimeError("Less than 2 GiB free disk space")
    expected = "red" if "red" in args.task.lower() else ("blue" if "blue" in args.task.lower() else "unknown")
    if expected != "unknown" and expected != args.target:
        raise RuntimeError("Task and --target disagree")

    scene = prepare_scene(args.scene, reset=True)
    print("Review robot RGB view; make sure both targets are visible.")
    print("Scene setup complete. This is SIMULATION ONLY.")
    print("Task:", args.task)
    print("Controls: W forward | A left | D right | S backward | SPACE stop | Q end")
    print("For emergency halt, use Gazebo PAUSE (space is software stop only).")
    response = input("Press ENTER to start recording, or type NO to cancel: ").strip()
    if response.lower() == "no":
        print("Cancelled; no data written")
        return 0

    import rclpy
    from geometry_msgs.msg import Twist

    rclpy.init(args=None)
    node = rclpy.create_node("smartcam_auto_teleop")
    publisher = node.create_publisher(Twist, "/cmd_vel", 10)
    log_file = open(log_path, "w", encoding="utf-8")
    rec = None
    keys = []
    start_pose = pose("my_bot")
    start_wall = time.time_ns()
    pressed_q = False
    fd = sys.stdin.fileno()
    original = None
    try:
        # Start the recorder only after a live /cmd_vel publisher exists.
        rec = subprocess.Popen(
            ["ros2", "bag", "record", "-o", str(bag_dir), *TOPICS],
            stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        time.sleep(2.5)
        if rec.poll() is not None:
            raise RuntimeError("ros2 bag record stopped during startup; inspect recorder log")
        print("RECORDING:", bag_dir)
        print("Press W/A/S/D to drive. Press Q to finish.")
        t0 = time.monotonic()
        original = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        velocity, omega, deadline = 0.0, 0.0, 0.0
        while time.monotonic() - t0 < args.max_seconds:
            if rec.poll() is not None:
                raise RuntimeError("rosbag recorder exited unexpectedly")
            if select.select([sys.stdin], [], [], 0.02)[0]:
                key = sys.stdin.read(1).lower()
                if key in MOVES:
                    velocity, omega, duration = MOVES[key]
                    deadline = time.monotonic() + duration
                    keys.append((time.time_ns(), key, velocity, omega))
                    print(f"KEY={key.upper()} v={velocity:.2f} omega={omega:.2f}")
                elif key == " ":
                    velocity, omega, deadline = 0.0, 0.0, 0.0
                    keys.append((time.time_ns(), "space", 0.0, 0.0))
                    print("STOP")
                elif key == "q":
                    pressed_q = True
                    break
            if time.monotonic() >= deadline:
                velocity, omega = 0.0, 0.0
            msg = Twist()
            msg.linear.x = velocity
            msg.angular.z = omega
            publisher.publish(msg)
            time.sleep(0.03)
        if not pressed_q:
            print("MAX DURATION reached; stopping")
    finally:
        # Send zero commands even on Ctrl+C or recorder failure.
        for _ in range(15):
            try:
                publisher.publish(Twist())
                time.sleep(0.04)
            except Exception:
                break
        if original is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, original)
        # Give the recorder time to catch the final stop commands.
        time.sleep(0.7)
        rc = stop_recorder(rec) if rec else None
        log_file.close()
        node.destroy_node()
        rclpy.shutdown()

    end_wall = time.time_ns()
    final_pose = pose("my_bot")
    print("Rosbag recorder exit code:", rc)
    if rc not in (0, -signal.SIGINT):
        print("WARNING: nonzero recorder exit; verify bag with inspect")
    success_text = input("Was the task successfully completed? [y/N]: ").strip().lower()
    success = success_text in ("y", "yes")
    # Sidecar metadata is next to bag, and copied into bag when possible.
    metadata = {
        "episode_id": name, "task": args.task, "target": args.target,
        "scene": args.scene, "split": args.split, "success": success,
        "source": "Gazebo Classic 11 / ROS2 Humble",
        "camera_topic": "/camera/image_raw",
        "state_topic": "/diff_cont/odom",
        "action_topic": "/diff_cont/cmd_vel_unstamped",
        "label_policy": "latest accepted controller command before image receipt timestamp",
        "sim_only": True, "start_wall_ns": start_wall, "end_wall_ns": end_wall,
        "start_robot_pose": start_pose, "end_robot_pose": final_pose,
        "target_poses": {"red": scene["red_target"], "blue": scene["blue_target"]},
        "num_key_events": len(keys),
    }
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if bag_dir.is_dir():
        (bag_dir / "task.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        with (bag_dir / "key_events.csv").open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["wall_ns", "key", "v", "omega"])
            writer.writerows(keys)
    print("Metadata:", meta_path)
    print("Bag:", bag_dir)
    print("Key events:", len(keys), "success:", success)
    if not success:
        print("Not eligible for training by default; rerun the episode if needed")
    return 0 if rc in (0, -signal.SIGINT) else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=["A", "B"], default="A")
    parser.add_argument("--target", choices=["red", "blue"], required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--episode", default=None)
    parser.add_argument("--split", choices=["train", "test"], default="train")
    parser.add_argument("--max-seconds", type=int, default=60)
    args = parser.parse_args()
    try:
        return run(args)
    except KeyboardInterrupt:
        print("Interrupted")
        return 130
    except Exception as exc:
        print("COLLECT ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
