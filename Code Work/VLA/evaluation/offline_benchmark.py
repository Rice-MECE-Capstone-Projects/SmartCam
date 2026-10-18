#!/usr/bin/env python3
"""Offline benchmark: SmolVLA vs. rule-based teacher."""

import argparse
import csv
from pathlib import Path

import torch
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies.factory import make_pre_post_processors
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument(
        "--repo-id",
        default="smartcam/velocity_partial_smoke_v1"
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    ckpt = Path(args.checkpoint).expanduser().resolve()
    root = Path(args.dataset_root).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()

    assert (ckpt / "model.safetensors").is_file()
    assert torch.cuda.is_available()

    dataset = LeRobotDataset(
        repo_id=args.repo_id,
        root=root
    )

    policy = SmolVLAPolicy.from_pretrained(
        str(ckpt),
        local_files_only=True,
        strict=True
    ).to("cuda").eval()

    pre, post = make_pre_post_processors(
        policy.config,
        pretrained_path=str(ckpt),
        preprocessor_overrides={
            "device_processor": {"device": "cuda"}
        },
    )

    indices = [0, 20, 50, 100, 150, 200, 250, 300, 339]
    rows = []

    print("\nFrame | Teacher [v, omega] | SmolVLA [v, omega]")

    for idx in indices:
        sample = dataset[idx]

        obs = {
            "observation.images.front": sample[
                "observation.images.front"
            ],
            "observation.state": sample["observation.state"],
            "task": sample["task"],
        }

        policy.reset()
        torch.manual_seed(42 + idx)

        with torch.inference_mode():
            with torch.autocast("cuda", dtype=torch.bfloat16):
                batch = pre(obs)
                prediction = post(policy.select_action(batch))

        pred = prediction.detach().float().cpu().flatten()
        teacher = sample["action"].detach().float().cpu().flatten()

        assert pred.numel() == 2
        assert torch.isfinite(pred).all()

        error = (pred - teacher).abs()

        rows.append({
            "frame": idx,
            "teacher_v": teacher[0].item(),
            "teacher_omega": teacher[1].item(),
            "pred_v": pred[0].item(),
            "pred_omega": pred[1].item(),
            "error_v": error[0].item(),
            "error_omega": error[1].item(),
        })

        print(
            f"{idx:3d} | "
            f"{teacher.tolist()} | "
            f"{pred.tolist()}"
        )

    mae_v = sum(r["error_v"] for r in rows) / len(rows)
    mae_w = sum(r["error_omega"] for r in rows) / len(rows)

    print(f"\nLinear MAE:  {mae_v:.6f} m/s")
    print(f"Angular MAE: {mae_w:.6f} rad/s")

    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print("Saved:", output)
    print("BENCHMARK PASS")


if __name__ == "__main__":
    main()
