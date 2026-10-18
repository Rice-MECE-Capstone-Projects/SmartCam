#!/usr/bin/env python3
"""Reproduce SmolVLA BF16 training from an existing plan.json.

Dry run by default. Does not control ROS or any robot.
"""

import argparse
import json
import runpy
import shlex
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    plan_path = args.plan.expanduser().resolve()
    output = args.output.expanduser().resolve()

    if not plan_path.is_file():
        raise FileNotFoundError(plan_path)

    plan = json.loads(plan_path.read_text())

    if plan.get("recipe_version") != "0.6.1":
        raise ValueError("Expected LeRobot 0.6.1 plan")

    if plan.get("schema") != "smartcam_velocity_v1":
        raise ValueError("Unexpected dataset schema")

    command = list(plan["command"])

    if command[1:3] != [
        "-m", "lerobot.scripts.lerobot_train"
    ]:
        raise ValueError("Unexpected training module")

    if output.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing output: {output}"
        )

    train_args = [
        arg for arg in command[3:]
        if not arg.startswith("--output_dir=")
    ]

    train_args.append(f"--output_dir={output}")

    print("Training configuration:")
    print("  Plan:", plan_path)
    print("  Output:", output)
    print("  Precision: BF16")
    print(
        "  Command:",
        shlex.join([sys.executable, "-m",
                    "lerobot.scripts.lerobot_train",
                    *train_args])
    )

    if not args.execute:
        print("\nDRY RUN PASS - training not started")
        return

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")

    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("GPU does not support BF16")

    torch.set_autocast_dtype("cuda", torch.bfloat16)

    print("CUDA autocast dtype:",
          torch.get_autocast_dtype("cuda"), flush=True)

    sys.argv = ["lerobot_train", *train_args]
    runpy.run_module(
        "lerobot.scripts.lerobot_train",
        run_name="__main__"
    )


if __name__ == "__main__":
    main()
