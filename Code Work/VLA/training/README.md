# SmolVLA BF16 Training

## Environment

- Ubuntu 22.04
- NVIDIA RTX 3070 8GB
- LeRobot 0.6.1
- PyTorch with CUDA
- Conda environment: smartcam_smolvla

## Model

Base model: lerobot/smolvla_base

Training configuration:
- 100 steps
- Batch size: 1
- BF16 mixed precision
- Freeze vision encoder
- Train expert only
- Train state projection
- 2D velocity action output

## Training Script

train_bf16.py

The script reads an existing AutoTeacher plan.json.

A compatible plan can be generated using the
AutoTeacher model preparation command.

The script runs in dry-run mode by default.
Use --execute only when intentionally starting training.

The plan contains local dataset paths and must be
regenerated or adjusted on another machine.

## Verified Result

The original 100-step experiment completed successfully
and saved a reloadable checkpoint.

The standalone train_bf16.py script has passed
syntax validation and dry-run verification.

Its full training execution has not been independently
retested.

## Dataset

One partial Gazebo demonstration, 340 frames.

Raw datasets and model checkpoints are excluded
from GitHub.

## Checkpoint Verification

Verified on October 18, 2026.

The 100-step checkpoint was successfully reloaded
using the AutoTeacher model verification command.

- Dataset index: 20
- Task: Go to the blue object.
- Predicted linear velocity: 0.084456 m/s
- Predicted angular velocity: 0.047440 rad/s
- Single cold inference: 0.782 s
- ROS velocity commands sent: 0
- Status: OFFLINE_2D_CHECKPOINT_RELOAD_PASS

This verifies checkpoint loading and finite 2D
action prediction, not real-time performance,
navigation success, or deployment safety.

The local JSON verification record is stored
outside the Git repository.
