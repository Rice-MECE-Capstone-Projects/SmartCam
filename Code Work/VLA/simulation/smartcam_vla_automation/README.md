# SmartCam VLA Automation v1.0

Built for this specific verified environment:

- School ROG / Ubuntu 22.04 / Gazebo Classic 11 / ROS2 Humble
- `~/Autonomous-RC-Car/farah_ws` with `articubot_one` and a running `my_bot`
- `/camera/image_raw`, `/camera/camera_info`, `/diff_cont/odom`, `/scan`,
  `/cmd_vel`, `/diff_cont/cmd_vel_unstamped`, `/clock`
- Target names `red_target`, `blue_target`; Scene A: red Y=+0.8, blue Y=-0.8

This package intentionally does NOT modify the `articubot_one` source,
ROS2 installation, NVIDIA driver, existing bag files, or OpenVLA environment.
It does NOT operate a real robot. It does NOT autonomously drive to a target.

## 1. Unpack on the school computer

Keep the existing Gazebo simulation running in one terminal.

```bash
mkdir -p ~/smartcam_vla
unzip ~/Downloads/SmartCam_VLA_Automation_v1.zip -d ~/smartcam_vla/
cd ~/smartcam_vla/smartcam_vla_automation
./smartcam.sh check
```

If you saved the ZIP elsewhere, replace `~/Downloads` with its actual path.

## 2. Set up Scene A / B

```bash
./smartcam.sh scene --scene A
```

Or, for swapped red/blue positions:

```bash
./smartcam.sh scene --scene B
```

The `collect` command automatically calls `scene` and resets the robot to
(-0.70, 0, 0.033, yaw=0), so a separate scene command is optional.
Do not perform scene reset while a different teleop program is running.

## 3. Record a complete task episode in ONE terminal

```bash
./smartcam.sh collect --scene A --target red --task 'Go to the red object.' --episode red_A_001 --max-seconds 60 --split train
```

At the prompt, inspect the `/camera/image_raw` view and press ENTER.
Then press W/A/S/D on the terminal (not in Gazebo), SPACE to send zero
velocity, Q to stop the recording. Answer y only if the task succeeded.
Camera and state streams are recorded by ros2 bag while keys generate
velocity commands. The recorder is stopped automatically with SIGINT and
allowed to flush its data.

If you need more time, start a NEW ID with `--max-seconds 90`.
A failed episode is retained but excluded from the training dataset by default.
Do not repeatedly create only one fixed scene and one instruction.

Suggested balanced demonstration schedule:

```bash
./smartcam.sh collect --scene A --target red --task 'Go to the red object.' --episode red_A_001 --split train
./smartcam.sh collect --scene A --target blue --task 'Go to the blue object.' --episode blue_A_001 --split train
./smartcam.sh collect --scene B --target red --task 'Go to the red object.' --episode red_B_001 --split train
./smartcam.sh collect --scene B --target blue --task 'Go to the blue object.' --episode blue_B_001 --split test
```

Each command must be run after the previous one has ended. For actual
fine-tuning, collect MANY more train episodes with varying starts/poses.
The test set must be withheld at the episode/scene level to avoid leakage.

## 4. Inspect an episode and export time-aligned training records

```bash
./smartcam.sh inspect --episode red_A_001
./smartcam.sh export --episode red_A_001
```

The first command checks ROS bag message counts and reads the control labels.
The second converts ROS Image packets to binary PPM and writes an aligned
`actions.csv` with `v_current`, `omega_current`, `v_target`, `omega_target`,
and `lidar_min_m`. Alignment uses rosbag receipt timestamps and the most
recent accepted controller command at/before each RGB image. Frames whose
latest odom/action sample is older than 180 ms are discarded.

Exports live under:

```
~/smartcam_data/bags/<episode>/
~/smartcam_data/bags/<episode>.task.json
~/smartcam_data/raw/<episode>/metadata.json
~/smartcam_data/raw/<episode>/actions.csv
~/smartcam_data/raw/<episode>/frames/*.ppm
```

`export` refuses to overwrite an existing folder and skips unsuccessful tasks.
PPM is intentionally uncompressed; short episodes are encouraged. Old
`teleop_validation_01` is a diagnostics bag, not an automatically labeled task.

## 5. Convert to LeRobotDataset v0.6.1

Use a **separate** Conda terminal. Do not source ROS2 in this terminal.
The preexisting R9000P `smolvla` environment may already contain LeRobot 0.6.1.
The ROG `openvla` env is NOT the same as a LeRobot env; do not mix them.

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate smolvla
cd ~/smartcam_vla/smartcam_vla_automation
./smartcam.sh convert
```

If you choose to create a **new** environment on the ROG instead,
explicitly review dependencies and disk before running:

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda create -n smartcam-smolvla python=3.12 -y
conda activate smartcam-smolvla
python -m pip install 'lerobot[peft]==0.6.1'
python -c 'import torch; print(torch.cuda.is_available())'
```

Package installation is not automated by this project. Depending on the
platform, PyTorch/CUDA may need a matching wheel; check before training.

The converter creates the LeRobot dataset at:

```
~/smartcam_data/lerobot/mentorpi_gazebo_v1
```

Only successful `split=train` episodes are included. Dataset contains RGB
front image, 2D velocity state, language task and 2D target action. It does
not train on LiDAR; that remains a separate safety signal.

## 6. Attempt SmolVLA LoRA smoke test (GPU memory is NOT guaranteed)

```bash
./smartcam.sh train
```

The default is a DRY RUN, showing the exact command. When you have examined
it and confirmed an isolated LeRobot 0.6.1 environment:

```bash
./smartcam.sh train --execute --steps 100
```

ROG RTX3070 8GB and R9000P RTX3060 6GB may run out of GPU memory even with
LoRA, batch size 1, and 100 training steps. Do not alter NVIDIA drivers in
response to OOM. Stop, report the error, and consider a smaller Octo baseline
or a machine with more GPU VRAM.

Successful loss/backprop/checkpoint does not prove closed-loop visual-language
navigation. Before deploying a trained model, write and independently verify
an observation/action adapter and a separate LiDAR safety controller.

## Safety / troubleshooting

- Keep only one keyboard teleop publisher active; close prior teleop terminals.
- Focus the terminal before pressing W/A/S/D. Do NOT press Space in the
  rosbag terminal (rosbag uses it to pause/resume).
- The single terminal recorder handles stopping and flushes bag itself.
- If the robot moves unexpectedly, PAUSE Gazebo. SPACE is software stop,
  not a hardware emergency stop.
- Reject incorrect demos at the success prompt. Do not edit or overwrite
  the original bag; run a NEW episode ID for a retry.
- Model teleportation can change Gazebo world pose without resetting all
  controller/odometry states. Training input uses measured velocity only;
  do not assume odom absolute pose equals world coordinates after reset.
- If generated images are black/missing, check `/camera/image_raw` in
  rqt_image_view and verify simulation is not paused.
- This package has syntax and unit checks, but has NOT been executed on the
  user's ROG machine. First perform `check` and one smoke-test episode.

## Commands overview

```
./smartcam.sh help
./smartcam.sh check
./smartcam.sh scene --scene A
./smartcam.sh collect --help
./smartcam.sh inspect --episode EPISODE_ID
./smartcam.sh export --episode EPISODE_ID
./smartcam.sh convert
./smartcam.sh train
./smartcam.sh train --execute --steps 100
```
