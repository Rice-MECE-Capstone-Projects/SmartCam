#!/usr/bin/env python3
"""Prepare or explicitly launch the official SmolVLA LoRA smoke test.

Never silently installs dependencies or starts a GPU-consuming training job.
"""

import argparse
import importlib.metadata
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def train(args):
    if "/opt/ros/humble" in os.environ.get("PYTHONPATH", ""):
        raise RuntimeError("ROS2 PYTHONPATH detected. Use a separate Conda terminal; unset PYTHONPATH")
    if importlib.metadata.version("lerobot") != "0.6.1":
        raise RuntimeError("Requires lerobot==0.6.1 in an isolated environment")
    try:
        import peft
    except ImportError as exc:
        raise RuntimeError("PEFT missing. Install lerobot[peft]==0.6.1 in the chosen Conda env") from exc
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("torch.cuda.is_available() is false. Stop and check the GPU environment")
    props = torch.cuda.get_device_properties(0)
    memory_gib = props.total_memory / (1024 ** 3)
    print(f"GPU: {props.name}, VRAM={memory_gib:.2f} GiB")
    if memory_gib < 12:
        print("WARNING: 6-8 GB VRAM may be insufficient even with LoRA and batch_size=1")
    if not shutil.which("lerobot-train"):
        raise RuntimeError("lerobot-train executable not found in this Conda env")
    if not args.dataset.is_dir() or not (args.dataset / "meta" / "info.json").is_file():
        raise RuntimeError(f"No valid local LeRobotDataset at {args.dataset}")
    if args.output.exists():
        raise RuntimeError(f"Training output path exists; do not overwrite: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.steps < 1 or args.steps > 100000:
        raise RuntimeError("--steps out of range")

    command = [
        "lerobot-train", "--policy.path=lerobot/smolvla_base",
        "--policy.input_features=null", "--policy.output_features=null",
        "--policy.device=cuda", "--policy.push_to_hub=false",
        "--dataset.repo_id=smartcam/mentorpi_gazebo_v1",
        f"--dataset.root={args.dataset}",
        "--batch_size=1", f"--steps={args.steps}", "--num_workers=0",
        "--peft.method_type=LORA", "--peft.r=8", "--peft.lora_alpha=8",
        "--wandb.enable=false", f"--output_dir={args.output}",
        f"--job_name={args.output.name}",
    ]
    print("Command:", shlex.join(command))
    if not args.execute:
        print("DRY RUN only; pass --execute to start training")
        return 0
    print("STARTING SmolVLA LoRA; can fail on an 8GB GPU (OOM is not a software success)")
    return subprocess.call(command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path.home() / "smartcam_data" / "lerobot" / "mentorpi_gazebo_v1")
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path.home() / "smartcam_data" / "checkpoints" / "smolvla_test_01")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        args.dataset = args.dataset.expanduser()
        args.output = args.output.expanduser()
        return train(args)
    except Exception as exc:
        print("TRAIN PRECHECK FAILED:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
