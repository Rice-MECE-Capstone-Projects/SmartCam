#!/usr/bin/env python3
"""Successful SmartCam raw episodes -> local LeRobotDataset v0.6.1 (train only).

Run under a separate Conda env containing lerobot==0.6.1; do NOT source ROS2.
"""

import argparse
import csv
import importlib.metadata
import json
import sys
from pathlib import Path


def convert(raw_root, dest, repo_id, limit=None):
    version = importlib.metadata.version("lerobot")
    if version != "0.6.1":
        raise RuntimeError(f"This converter was checked against lerobot 0.6.1, found {version}")
    import numpy as np
    from PIL import Image
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    if dest.exists():
        raise RuntimeError(f"Destination exists, refusing overwrite: {dest}")
    episodes = []
    skipped = []
    for ep in sorted(raw_root.glob("*")):
        if not ep.is_dir() or not (ep / "metadata.json").is_file():
            continue
        meta = json.loads((ep / "metadata.json").read_text())
        if meta.get("split") != "train" or meta.get("success") is not True:
            skipped.append(ep.name)
            continue
        episodes.append(ep)
    if limit:
        episodes = episodes[:limit]
    if not episodes:
        raise RuntimeError("No successful train episodes to convert")
    if len(episodes) < 5:
        print(f"WARNING: only {len(episodes)} training episode(s); suitable for smoke test, not a trained policy evaluation")

    features = {
        "observation.images.front": {
            "dtype": "image", "shape": (240, 320, 3),
            "names": ["height", "width", "channels"],
        },
        "observation.state": {
            "dtype": "float32", "shape": (2,), "names": ["v_current", "omega_current"],
        },
        "action": {
            "dtype": "float32", "shape": (2,), "names": ["v_target", "omega_target"],
        },
    }
    dataset = LeRobotDataset.create(
        repo_id=repo_id, root=dest, fps=10, robot_type="articubot_one",
        features=features, use_videos=False,
    )
    frames_added = 0
    for ep in episodes:
        meta = json.loads((ep / "metadata.json").read_text())
        with (ep / "actions.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
        if len(rows) < 10:
            raise RuntimeError(f"Not enough frames in {ep.name}")
        for row in rows:
            path = ep / "frames" / row["frame"]
            with Image.open(path) as im:
                image = np.asarray(im.convert("RGB").resize((320, 240), Image.Resampling.BILINEAR), dtype=np.uint8)
            state = np.asarray([float(row["v_current"]), float(row["omega_current"])], dtype=np.float32)
            action = np.asarray([float(row["v_target"]), float(row["omega_target"])], dtype=np.float32)
            if not np.all(np.isfinite(state)) or not np.all(np.isfinite(action)):
                raise RuntimeError(f"Invalid state or action values in {ep.name}: {row['frame']}")
            dataset.add_frame({
                "observation.images.front": image,
                "observation.state": state,
                "action": action,
                "task": meta["task"],
            })
            frames_added += 1
        dataset.save_episode()
        print(f"Saved episode: {ep.name}, frames={len(rows)}, task={meta['task']}")
    dataset.finalize()
    print(f"LEROBOT PASS: episodes={len(episodes)}, frames={frames_added}, path={dest}")
    if skipped:
        print("Excluded test/failed episodes:", ", ".join(skipped))
    print("Training readiness is not the same as VLA success. Use a held-out test set.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path,
                        default=Path.home() / "smartcam_data" / "raw")
    parser.add_argument("--output", type=Path,
                        default=Path.home() / "smartcam_data" / "lerobot" / "mentorpi_gazebo_v1")
    parser.add_argument("--repo-id", default="smartcam/mentorpi_gazebo_v1")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    try:
        convert(args.raw_root.expanduser(), args.output.expanduser(), args.repo_id, args.limit)
        return 0
    except Exception as exc:
        print("CONVERT ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
