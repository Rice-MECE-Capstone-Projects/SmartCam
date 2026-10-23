#!/usr/bin/env python3
"""Read-only offline bag counts and accepted-action diagnostics."""

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path


def inspect(bag):
    from geometry_msgs.msg import Twist
    from rclpy.serialization import deserialize_message

    files = sorted(bag.glob("*.db3"))
    if not files:
        raise RuntimeError(f"No db3 file in {bag}")
    counts = Counter()
    action_stats = {}
    for db in files:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as con:
            topics = {t[0]: (t[1], t[2]) for t in con.execute(
                "SELECT name,id,type FROM topics")}
            for topic, (tid, _type) in topics.items():
                counts[topic] += con.execute(
                    "SELECT COUNT(*) FROM messages WHERE topic_id=?", (tid,)
                ).fetchone()[0]
            for topic in ("/cmd_vel", "/diff_cont/cmd_vel_unstamped"):
                if topic not in topics:
                    continue
                stats = action_stats.setdefault(topic, {"left": 0, "right": 0,
                                                       "forward": 0, "backward": 0,
                                                       "max_abs_v": 0.0, "max_abs_w": 0.0})
                tid = topics[topic][0]
                for (blob,) in con.execute("SELECT data FROM messages WHERE topic_id=?", (tid,)):
                    msg = deserialize_message(blob, Twist)
                    v, w = msg.linear.x, msg.angular.z
                    stats["left"] += w > 0.05
                    stats["right"] += w < -0.05
                    stats["forward"] += v > 0.02
                    stats["backward"] += v < -0.02
                    stats["max_abs_v"] = max(stats["max_abs_v"], abs(v))
                    stats["max_abs_w"] = max(stats["max_abs_w"], abs(w))
    print("BAG:", bag)
    for topic, count in sorted(counts.items()):
        print(f"  {topic}: {count:,} messages")
    print("ACCEPTED ACTION STATS:", json.dumps(action_stats, indent=2))
    critical = ("/camera/image_raw", "/diff_cont/odom", "/scan",
                "/cmd_vel", "/diff_cont/cmd_vel_unstamped")
    missing = [t for t in critical if counts[t] <= 0]
    if missing:
        print("FAIL: Missing data on:", ", ".join(missing))
        return 2
    accepted = action_stats.get("/diff_cont/cmd_vel_unstamped", {})
    num_nonzero = sum(accepted.get(k, 0) for k in ("left", "right", "forward", "backward"))
    if num_nonzero == 0:
        print("WARNING: no nonzero accepted actions recorded")
        return 3
    print("BAG CHECK PASS: multimodal messages and nonzero accepted control recorded")
    print("NOTE: passing this check does not establish safe/successful navigation")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True, help="Episode ID or complete bag directory")
    args = parser.parse_args()
    path = Path(args.episode).expanduser()
    if not path.is_dir():
        path = Path.home() / "smartcam_data" / "bags" / args.episode
    if not path.is_dir():
        parser.error(f"No episode directory: {path}")
    try:
        return inspect(path)
    except Exception as exc:
        print("INSPECT ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
