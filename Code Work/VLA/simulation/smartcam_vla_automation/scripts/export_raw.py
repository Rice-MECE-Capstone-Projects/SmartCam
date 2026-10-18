#!/usr/bin/env python3
"""ROS bag SQLite -> time-aligned episode frames/actions for model training.

Uses ROS2 /usr/bin/python3. No PIL or LeRobot needed. Image payloads saved as
binary PPM to avoid changing packages in the ROS2 system environment.
Time alignment is based on sqlite ROS2 receipt timestamps, never row indices.
"""

import argparse
import bisect
import csv
import json
import math
import sqlite3
import sys
from pathlib import Path


def latest_before(stamps, values, stamp, max_age_ns):
    pos = bisect.bisect_right(stamps, stamp) - 1
    if pos < 0 or (stamp - stamps[pos]) > max_age_ns:
        return None
    return values[pos]


def image_as_ppm(image_msg):
    import numpy as np
    encoding = image_msg.encoding.lower()
    height, width, stride = image_msg.height, image_msg.width, image_msg.step
    if encoding in ("rgb8", "bgr8"):
        channels = 3
    elif encoding in ("rgba8", "bgra8"):
        channels = 4
    elif encoding in ("mono8", "8uc1"):
        channels = 1
    else:
        raise RuntimeError(f"Unsupported ROS Image encoding: {image_msg.encoding}")
    if stride < width * channels:
        raise RuntimeError("Malformed ROS image step")
    data = np.frombuffer(image_msg.data, dtype=np.uint8)
    if len(data) != height * stride:
        raise RuntimeError("Image size does not match height * step")
    pix = data.reshape(height, stride)[:, :width*channels].reshape(height, width, channels)
    if encoding.startswith("bgr"):
        pix = pix[:, :, [2, 1, 0]]
    elif encoding == "bgra8":
        pix = pix[:, :, [2, 1, 0]]
    elif channels == 4:
        pix = pix[:, :, :3]
    elif channels == 1:
        pix = np.repeat(pix, 3, axis=2)
    return f"P6\n{width} {height}\n255\n".encode("ascii") + pix.tobytes()


def load_stamped(con, topic_map, name, extractor):
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    if name not in topic_map:
        raise RuntimeError(f"Bag missing: {name}")
    tid, msg_type = topic_map[name]
    message_cls = get_message(msg_type)
    stamps, values = [], []
    for ns, blob in con.execute(
        "SELECT timestamp, data FROM messages WHERE topic_id=? ORDER BY timestamp", (tid,)
    ):
        val = extractor(deserialize_message(blob, message_cls))
        stamps.append(ns)
        values.append(val)
    return stamps, values


def valid_lidar_distance(scan):
    valid = [float(x) for x in scan.ranges if math.isfinite(x)
             and scan.range_min <= x <= scan.range_max]
    return min(valid) if valid else None


def convert_one(bag, out, fps=10, max_age_ms=180, allow_failed=False):
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import Image

    metadata_path = bag / "task.json"
    if not metadata_path.is_file():
        metadata_path = bag.parent / f"{bag.name}.task.json"
    if not metadata_path.is_file():
        raise RuntimeError(f"Missing task.json for {bag.name}; task labels must not be guessed")
    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    if meta.get("success") is not True and not allow_failed:
        raise RuntimeError(f"Episode {bag.name} not marked successful; refusing training export")
    if out.exists():
        raise RuntimeError(f"Refusing to overwrite: {out}")
    dbfiles = sorted(bag.glob("*.db3"))
    if len(dbfiles) != 1:
        raise RuntimeError("Exporter requires one db3 per short episode; split bags are not supported")

    out.mkdir(parents=True)
    frames = out / "frames"
    frames.mkdir()
    completed = False
    try:
        with sqlite3.connect(f"file:{dbfiles[0]}?mode=ro", uri=True) as con:
            topic_map = {r[0]: (r[1], r[2]) for r in con.execute(
                "SELECT name, id, type FROM topics")}
            action_t, action_v = load_stamped(
                con, topic_map, "/diff_cont/cmd_vel_unstamped",
                lambda m: (float(m.linear.x), float(m.angular.z)))
            odom_t, odom_v = load_stamped(
                con, topic_map, "/diff_cont/odom",
                lambda m: (float(m.twist.twist.linear.x), float(m.twist.twist.angular.z)))
            laser_t, laser_v = load_stamped(
                con, topic_map, "/scan", valid_lidar_distance)
            if not action_t or not odom_t:
                raise RuntimeError("No odometry or actual controller command messages")
            if "/camera/image_raw" not in topic_map:
                raise RuntimeError("No RGB Camera messages")
            image_tid = topic_map["/camera/image_raw"][0]
            age_ns = int(max_age_ms * 1e6)
            step_ns = int(1e9 / fps)
            last_saved = None
            first_saved = None
            rows = []
            for stamp, blob in con.execute(
                "SELECT timestamp, data FROM messages WHERE topic_id=? ORDER BY timestamp",
                (image_tid,)
            ):
                if last_saved is not None and stamp - last_saved < step_ns * 0.92:
                    continue
                action = latest_before(action_t, action_v, stamp, age_ns)
                state = latest_before(odom_t, odom_v, stamp, age_ns)
                if action is None or state is None:
                    continue
                lidar = latest_before(laser_t, laser_v, stamp, 350_000_000)
                image = deserialize_message(blob, Image)
                filename = f"{len(rows):06d}.ppm"
                (frames / filename).write_bytes(image_as_ppm(image))
                if first_saved is None:
                    first_saved = stamp
                rows.append({"frame": filename, "timestamp_ns": stamp,
                             "time_s": (stamp-first_saved)/1e9,
                             "v_current": state[0], "omega_current": state[1],
                             "v_target": action[0], "omega_target": action[1],
                             "lidar_min_m": "" if lidar is None else lidar})
                last_saved = stamp
        if len(rows) < 10:
            raise RuntimeError(f"Only {len(rows)} time-aligned frames (need >=10)")
        with (out / "actions.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        export_meta = {**meta, "fps": fps, "exported_frames": len(rows),
                       "max_alignment_age_ms": max_age_ms,
                       "image_format": "binary PPM RGB",
                       "sync_basis": "ROS bag receipt timestamp (not header stamps)",
                       "action_definition": "most recent accepted command at/before image receipt time"}
        (out / "metadata.json").write_text(json.dumps(export_meta, indent=2), encoding="utf-8")
        completed = True
        print(f"EXPORT PASS: {bag.name} -> {out} ({len(rows)} frames, task={meta['task']})")
    finally:
        if not completed:
            # Keep partial data for debugging; never overwrite it implicitly.
            print(f"WARNING: partial folder may exist: {out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--max-age-ms", type=int, default=180)
    parser.add_argument("--allow-failed", action="store_true")
    args = parser.parse_args()
    if args.fps < 1 or args.fps > 30:
        parser.error("fps must be in [1,30]")
    bag = Path(args.episode).expanduser()
    if not bag.is_dir():
        bag = Path.home() / "smartcam_data" / "bags" / args.episode
    if not bag.is_dir():
        parser.error(f"Cannot find bag: {bag}")
    out = Path.home() / "smartcam_data" / "raw" / bag.name
    try:
        convert_one(bag, out, args.fps, args.max_age_ms, args.allow_failed)
        return 0
    except Exception as exc:
        print("EXPORT ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
