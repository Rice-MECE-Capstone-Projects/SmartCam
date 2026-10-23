# SmolVLA Offline Benchmark

## Experiment

- Project: SmartCam VLA
- Date: October 18, 2026
- Model: SmolVLA
- Training: 100 steps, BF16
- GPU: NVIDIA RTX 3070 8GB
- Framework: LeRobot 0.6.1
- Dataset: 340 frames, one partial episode
- Task: Go to the blue object.

## Evaluation

Nine frames sampled from the training trajectory:
0, 20, 50, 100, 150, 200, 250, 300, 339.

Action representation:
[v_linear (m/s), omega_angular (rad/s)]

## Results

| Metric | Result |
|---|---|
| Linear velocity MAE | 0.014123 m/s |
| Angular velocity MAE | 0.028108 rad/s |
| Offline inference | PASS |
| Repeated benchmark | Matching outputs |

Full per-frame results:
benchmark_100step.csv

## Observations

- Straight-motion predictions are relatively close to the teacher.
- Initial turning is poorly reproduced.
- Deceleration and stopping require improvement.

## Limitations

This is an in-sample smoke test on one partial
demonstration trajectory.

The results do not establish navigation success,
generalization, or physical robot safety.

No VLA closed-loop robot control was performed.
