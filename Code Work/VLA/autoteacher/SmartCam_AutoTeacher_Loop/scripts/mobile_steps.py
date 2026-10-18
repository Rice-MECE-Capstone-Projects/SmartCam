#!/usr/bin/env python3
"""Offline SmolVLA mobile-action preparation for LeRobot 0.6.1.
No ROS imports, publishers, Gazebo mutations, package installation or dataset generation.
"""
from __future__ import annotations
import argparse
import dataclasses
import datetime as dt
import importlib.metadata as md
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

VERSION = "0.6.1"
BASE = "lerobot/smolvla_base"
CAM = "observation.images.front"
STATE = "observation.state"
ACTION = "action"


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def flatten(value):
    if isinstance(value, (list, tuple)):
        for part in value:
            yield from flatten(part)
    else:
        yield float(value)


def validate_metadata(info: dict, stats: dict) -> list[str]:
    """Checks metadata only; does not assert timing correctness or label quality."""
    features = info.get("features", {})
    semantic_names = {STATE: ["v_current_m_s", "omega_current_rad_s"],
                      ACTION: ["v_command_m_s", "omega_command_rad_s"]}
    for name in (STATE, ACTION):
        if features.get(name, {}).get("names") != semantic_names[name]:
            raise ValueError(f"{name} names must declare velocity semantics and units: {semantic_names[name]}")
        if features.get(name, {}).get("shape") != [2]:
            raise ValueError(f"{name} must have shape [2]")
        if features[name].get("dtype") != "float32":
            raise ValueError(f"{name} must be float32")
        for field in ("mean", "std"):
            values = list(flatten(stats.get(name, {}).get(field, [])))
            if len(values) != 2 or not all(math.isfinite(v) for v in values):
                raise ValueError(f"{name}.{field}: need two finite training-set statistics")
        if any(v < 0 for v in flatten(stats[name]["std"])):
            raise ValueError(f"{name}.std must not be negative")
    camera = features.get(CAM, {})
    if camera.get("dtype") not in ("image", "video"):
        raise ValueError(f"Missing RGB feature {CAM} with image/video dtype")
    shape = camera.get("shape", [])
    names = camera.get("names", [])
    if len(shape) != 3 or names != ["height", "width", "channels"] or shape[-1] != 3:
        raise ValueError("Dataset image metadata must be HWC with 3 channels and matching names")
    if any(not isinstance(x, int) or x <= 0 for x in shape):
        raise ValueError("Image dimensions must be positive integers")
    visual_keys = [k for k, f in features.items() if f.get("dtype") in ("image", "video")]
    if visual_keys != [CAM]:
        raise ValueError("Stage 1 expects exactly one visual input, observation.images.front")
    observation_keys = {k for k in features if k.startswith("observation.")}
    if observation_keys != {CAM, STATE}:
        raise ValueError(f"Unexpected observation keys: {sorted(observation_keys)}")
    if not math.isclose(float(info.get("fps", 0)), 10.0, abs_tol=1e-6):
        raise ValueError("This first-stage recipe expects an audited 10 Hz dataset")
    if int(info.get("total_frames", 0)) < 2 or int(info.get("total_episodes", 0)) < 1:
        raise ValueError("Dataset is empty")
    warnings = []
    for name in (STATE, ACTION):
        if any(v <= 1e-8 for v in flatten(stats[name]["std"])):
            warnings.append(f"{name} contains an almost-constant component; this is not useful coverage")
    return warnings


def require_version() -> None:
    if sys.version_info < (3, 12):
        raise RuntimeError("Use the independent Python 3.12+ model environment, not ROS/OpenVLA Python 3.10")
    if md.version("lerobot") != VERSION:
        raise RuntimeError(f"Recipe checked against LeRobot {VERSION}; inspect your version before adapting")


def env_check(args) -> int:
    print("Python:", sys.version.split()[0], sys.executable)
    print("Conda prefix:", os.environ.get("CONDA_PREFIX", "not active"))
    for name in ("lerobot", "torch", "torchvision", "transformers", "numpy", "accelerate", "datasets", "huggingface-hub"):
        try:
            print(name + ":", md.version(name))
        except md.PackageNotFoundError:
            print(name + ": NOT INSTALLED")
    require_version()
    import torch
    from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
    from lerobot.policies.factory import make_pre_post_processors
    from lerobot.datasets import LeRobotDataset
    fields = {f.name for f in dataclasses.fields(SmolVLAConfig)}
    required = {"input_features", "output_features", "max_action_dim", "max_state_dim",
                "train_expert_only", "train_state_proj", "freeze_vision_encoder"}
    if not required <= fields:
        raise RuntimeError("Installed configuration API differs from the verified recipe")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available; fix the model environment before training")
    print("GPU:", torch.cuda.get_device_name(0))
    print("VRAM GiB:", round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2))
    torch.cuda.synchronize()
    print("ENV PASS: imports and CUDA visibility only; no weights loaded and no training performed")
    return 0


def plan_training(args) -> int:
    require_version()
    root = Path(args.dataset_root).expanduser().resolve()
    info_path, stats_path = root / "meta/info.json", root / "meta/stats.json"
    if not info_path.is_file() or not stats_path.is_file():
        raise FileNotFoundError("A real converted LeRobot TRAIN dataset is required: meta/info.json + meta/stats.json")
    info = json.loads(info_path.read_text())
    stats = json.loads(stats_path.read_text())
    warnings = validate_metadata(info, stats)
    if not args.training_only:
        raise ValueError("Confirm this root contains TRAIN episodes only and train-only stats with --training-only")
    if args.steps < 20:
        raise ValueError("Use at least 20 steps in this recipe")
    from lerobot.configs import PreTrainedConfig
    from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig
    from lerobot.utils.feature_utils import dataset_to_policy_features
    from huggingface_hub import hf_hub_download
    base_path = Path(args.base).expanduser()
    if base_path.is_dir():
        policy_source = str(base_path.resolve())
        config_file = base_path / "config.json"
        if not config_file.is_file():
            raise FileNotFoundError(str(config_file))
        revision = None
    else:
        config_file = Path(hf_hub_download(args.base, "config.json", revision=args.revision,
                                         local_files_only=args.local_only))
        policy_source = args.base
        # Standard HF cache layout: snapshots/<commit>/config.json
        revision = config_file.parent.name if config_file.parent.parent.name == "snapshots" else args.revision
        if not revision:
            raise ValueError("Could not resolve a model commit; provide --revision")
    cfg = PreTrainedConfig.from_pretrained(str(config_file.parent), cli_overrides=[])
    if not isinstance(cfg, SmolVLAConfig):
        raise ValueError("Base config is not SmolVLA")
    if cfg.max_action_dim < 2 or cfg.max_state_dim < 2:
        raise ValueError("Base internal dimensions do not support 2D data")
    internal = {"max_action_dim": cfg.max_action_dim, "max_state_dim": cfg.max_state_dim,
                "chunk_size": cfg.chunk_size}
    features = dataset_to_policy_features(info["features"])
    cfg.input_features = {CAM: features[CAM], STATE: features[STATE]}
    cfg.output_features = {ACTION: features[ACTION]}
    cfg.n_action_steps = 1
    cfg.device = "cuda"
    cfg.use_amp = True
    cfg.freeze_vision_encoder = True
    cfg.train_expert_only = True
    cfg.train_state_proj = True
    cfg.adapt_to_pi_aloha = False
    cfg.use_delta_joint_actions_aloha = False
    cfg.push_to_hub = False
    cfg.pretrained_path = Path(policy_source)
    cfg.pretrained_revision = revision
    cfg.optimizer_lr = 1e-4
    cfg.scheduler_warmup_steps = min(10, args.steps // 5)
    cfg.scheduler_decay_steps = args.steps
    cfg.validate_features()
    out = Path(args.output).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=False)
    cfg.save_pretrained(out / "config_only_NOT_A_CHECKPOINT")
    run = out / "training_run"
    cmd = [sys.executable, "-m", "lerobot.scripts.lerobot_train",
           f"--policy.path={policy_source}", "--policy.input_features=null", "--policy.output_features=null",
           "--policy.device=cuda", "--policy.use_amp=true", "--policy.push_to_hub=false",
           "--policy.freeze_vision_encoder=true", "--policy.train_expert_only=true", "--policy.train_state_proj=true",
           "--policy.adapt_to_pi_aloha=false", "--policy.use_delta_joint_actions_aloha=false",
           "--policy.n_action_steps=1", f"--policy.chunk_size={cfg.chunk_size}",
           "--policy.optimizer_lr=0.0001", f"--policy.scheduler_warmup_steps={cfg.scheduler_warmup_steps}",
           f"--policy.scheduler_decay_steps={args.steps}",
           f"--dataset.repo_id={args.repo_id}", f"--dataset.root={root}",
           "--dataset.image_transforms.enable=false", "--dataset.eval_split=0.0",
           "--batch_size=1", "--num_workers=0", f"--steps={args.steps}", "--log_freq=10",
           f"--save_freq={args.steps}", "--save_checkpoint=true", "--save_checkpoint_to_hub=false",
           "--wandb.enable=false", "--env_eval_freq=0", "--eval_steps=0",
           f"--output_dir={run}", "--job_name=smartcam_velocity_smoke", "--seed=42"]
    if revision:
        cmd.append(f"--policy.pretrained_revision={revision}")
    plan = {"recipe_version": VERSION, "schema": "smartcam_velocity_v1",
            "status": "CONFIG_PREPARED_NOT_TRAINED", "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "training_only_confirmed_by_user": True, "timing_alignment_verified_by_this_tool": False,
            "all_dataset_rows_checked_by_this_tool": False, "dataset_root": str(root), "repo_id": args.repo_id,
            "base": policy_source, "resolved_model_revision": revision, "internal_dimensions_preserved": internal,
            "expected_state_shape": [2], "expected_action_shape": [2],
            "state_names": ["v_current_m_s", "omega_current_rad_s"],
            "action_names": ["v_command_m_s", "omega_command_rad_s"],
            "warnings": warnings, "training_run": str(run), "command": cmd}
    save_json(out / "plan.json", plan)
    (out / "command.txt").write_text(shlex.join(cmd) + "\n")
    print("PLAN SAVED:", out / "plan.json")
    print("External state/action dimensions: 2/2. Internal dimensions preserved:", internal)
    for warning in warnings:
        print("WARNING:", warning)
    print("No weights trained. Config-only folder is NOT an inference checkpoint.")
    print("DRY RUN COMMAND:\n" + shlex.join(cmd))
    return 0


def run_training(args) -> int:
    require_version()
    plan_file = Path(args.plan).expanduser().resolve()
    plan = json.loads(plan_file.read_text())
    if plan.get("recipe_version") != VERSION or plan.get("schema") != "smartcam_velocity_v1":
        raise ValueError("Unexpected plan format")
    cmd = list(plan["command"])
    if len(cmd) < 3 or cmd[1:3] != ["-m", "lerobot.scripts.lerobot_train"]:
        raise ValueError("Unexpected training module in plan")
    cmd[0] = sys.executable
    print(shlex.join(cmd))
    if not args.execute:
        print("PREVIEW ONLY. Add --execute after checking the dataset and plan.")
        return 0
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    if Path(plan["training_run"]).exists():
        raise FileExistsError("Training directory exists. Create a NEW plan, do not overwrite.")
    log_path = plan_file.parent / "training_console.log"
    with log_path.open("x", encoding="utf-8") as log:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        try:
            assert process.stdout is not None
            for line in process.stdout:
                sys.stdout.write(line)
                log.write(line)
                log.flush()
            rc = process.wait()
        except KeyboardInterrupt:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
    print("TRAIN EXIT:", rc, "; verify checkpoint reload and predictions separately")
    return rc


def verify_checkpoint(args) -> int:
    require_version()
    ckpt = Path(args.checkpoint).expanduser().resolve()
    if not (ckpt / "model.safetensors").is_file():
        raise FileNotFoundError("Need a real locally trained checkpoint with model.safetensors, not config-only output")
    out = Path(args.output).expanduser().resolve()
    if out.exists():
        raise FileExistsError("Verification output exists; choose a new JSON filename")
    import torch
    from lerobot.datasets import LeRobotDataset
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
    from lerobot.policies.factory import make_pre_post_processors
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    dataset = LeRobotDataset(args.repo_id, root=Path(args.dataset_root).expanduser())
    sample = dataset[args.index]
    policy = SmolVLAPolicy.from_pretrained(str(ckpt)).to("cuda").eval()
    if tuple(policy.config.action_feature.shape) != (2,) or tuple(policy.config.input_features[STATE].shape) != (2,):
        raise ValueError("Checkpoint is not a 2D state / 2D action policy")
    preprocess, postprocess = make_pre_post_processors(
        policy.config, str(ckpt), preprocessor_overrides={"device_processor": {"device": "cuda"}})
    obs = {}
    for key in policy.config.input_features:
        if key not in sample:
            raise KeyError(f"Dataset sample is missing {key}")
        value = sample[key]
        if key in policy.config.image_features and value.dtype == torch.uint8:
            value = value.float() / 255.0
        obs[key] = value
    task = args.task if args.task is not None else sample.get("task")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("Sample task must be a non-empty string")
    obs["task"] = task
    batch = preprocess(obs)
    policy.reset()
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.inference_mode():
        action = postprocess(policy.select_action(batch))
    torch.cuda.synchronize()
    latency = time.perf_counter() - t0
    if not isinstance(action, torch.Tensor) or action.numel() != 2 or not bool(torch.isfinite(action).all()):
        raise ValueError("Invalid 2D policy output")
    values = action.detach().cpu().reshape(-1).tolist()
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {"status": "OFFLINE_2D_CHECKPOINT_RELOAD_PASS", "checkpoint": str(ckpt),
              "task": task, "dataset_index": args.index, "state_source": "dataset_not_zero_placeholder",
              "action_m_s_rad_s": values, "inference_seconds": latency,
              "measurement_scope": "single cold inference, not a steady-state benchmark",
              "robot_commands_sent": 0, "navigation_quality_verified": False,
              "warning": "Finite 2D output does not establish learned navigation or safety"}
    save_json(out, record)
    print(json.dumps(record, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    env = sub.add_parser("env", help="Read-only environment/import check")
    env.set_defaults(fn=env_check)
    prepare = sub.add_parser("prepare", help="Inspect converted train metadata, download base config only, create training plan")
    prepare.add_argument("--dataset-root", required=True)
    prepare.add_argument("--repo-id", required=True)
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--base", default=BASE)
    prepare.add_argument("--revision")
    prepare.add_argument("--local-only", action="store_true")
    prepare.add_argument("--training-only", action="store_true")
    prepare.add_argument("--steps", type=int, default=100)
    prepare.set_defaults(fn=plan_training)
    train = sub.add_parser("train", help="Print command by default; explicit --execute launches training")
    train.add_argument("--plan", required=True)
    train.add_argument("--execute", action="store_true")
    train.set_defaults(fn=run_training)
    verify = sub.add_parser("verify", help="Reload locally trained 2D checkpoint and infer one actual dataset sample; NO ROS")
    verify.add_argument("--checkpoint", required=True)
    verify.add_argument("--dataset-root", required=True)
    verify.add_argument("--repo-id", required=True)
    verify.add_argument("--index", type=int, default=0)
    verify.add_argument("--task")
    verify.add_argument("--output", required=True)
    verify.set_defaults(fn=verify_checkpoint)
    args = p.parse_args()
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        print("Interrupted; no robot interface is present in this tool", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
