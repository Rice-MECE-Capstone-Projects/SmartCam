# SmartCam ELEC 594 Midterm LIVE Demo

## Honest scope
This package provides a **language-conditioned rule-based visual navigation baseline**, NOT a fine-tuned or pretrained neural VLA policy. It exercises the SAME ROS2 sensing / velocity-command interfaces intended for the future VLA. Use the exact label **VLA-ready robot platform + vision-language control baseline** in the presentation.

## Prerequisites
School ROG Ubuntu 22.04, ROS2 Humble, Gazebo Classic 11, existing `~/Autonomous-RC-Car/farah_ws` with `articubot_one`, camera/scan/odom topics, `diff_cont` active. Uses built-in Python3 and ROS2 packages: no pip/apt installs.

## Installation on ROG
Assuming the archive is downloaded to `~/Downloads`:

```bash
mkdir -p ~/smartcam_vla
unzip ~/Downloads/SmartCam_Midterm_Demo.zip -d ~/smartcam_vla
cd ~/smartcam_vla/SmartCam_Midterm_Demo
chmod +x demo.sh
```

## Runbook (3 terminals)

**Terminal A (Gazebo):**
```bash
cd ~/smartcam_vla/SmartCam_Midterm_Demo
./demo.sh gazebo
```
Keep open. If Gazebo is already running, skip this step.

**Terminal B (scene and camera):**
```bash
cd ~/smartcam_vla/SmartCam_Midterm_Demo
./demo.sh check
./demo.sh scene A
./demo.sh camera
```
In rqt_image_view choose `/camera/image_raw`. You should see red box left and blue box right.

**Terminal C (safe preview; no motor command):**
```bash
cd ~/smartcam_vla/SmartCam_Midterm_Demo
./demo.sh red-preview
```
Expected log examples: `TURN TO CENTER ... v=0 omega=+... [PREVIEW ONLY]`.

**Optional live Gazebo driving after a successful preview:**
```bash
./demo.sh red-drive
```
Type `DRIVE` to enable simulated motion. A 20-second maximum, 0.08m/s linear limit, 0.20rad/s turn limit, stop within 0.72m of a front LiDAR return. Ctrl+C sends zero commands. Gazebo PAUSE is the fallback if movement is unexpectedly unsafe. Do NOT deploy directly to a physical MentorPi.

**Demonstrate visual/language grounding:**
```bash
./demo.sh scene B
./demo.sh blue-preview
```
This swaps the red/blue target positions without changing the robot. It is a *baseline demonstration*, not a trained policy. `./demo.sh blue-drive` is optional if preview confirms correct detections. The preview target selection is performed through a predefined `red`/`blue` instruction parser.

**Software stop command:**
```bash
./demo.sh stop
```
This is not a separate, certified E-stop. If joystick or tracker sends commands to higher-priority twist_mux inputs, stop them before the demo.

## Emergency / fallback
If camera or ROS topics are unavailable, show slides with real recorded Gazebo and rqt_image_view screenshots. If movement is unstable, only use `red-preview` / `blue-preview`; those commands never publish motor commands. The existing ROS Bag `teleop_validation_01` is ground-truth evidence of sensor and action data; this script does not overwrite it.

## Existing verified evidence as of 2026-10-10
- Camera `/camera/image_raw`: ~9.995 Hz measured.
- Robot controller `diff_cont`: active. `/scan`, `/diff_cont/odom`: available.
- `teleop_validation_01`: 425.783 s, 29,876 messages, 3.6 GiB; camera 4,175, scan 4,175, odom 12,279, `/cmd_vel` 2,536, controller input 2,536.
- 12 left turn messages in both `/cmd_vel` and `/diff_cont/cmd_vel_unstamped`, maximum angular speed 0.20 rad/s.
- Need to resolve previous slow uncommanded robot pose drift (~1 mm/s measured in a later quiet interval) and test the demo before presenting.
- The previous automatic collector `red_A_001` was interrupted with an `rcl_shutdown already called` error; do not claim a successful demonstration dataset from it.

## Talking point
> The midterm milestone is a simulation-first VLA-ready mobile robot. RGB, LiDAR, odometry and ROS2 control are integrated; we validated sensing at 10Hz and synchronized sensor/action logging. For the live demo, a lightweight vision-language baseline takes the spoken/text goal 'Go to the red object,' detects the visual target, produces bounded velocity commands and stops on LiDAR proximity. The learned VLA action head and robust fine-tuning are next steps, not yet completed.
