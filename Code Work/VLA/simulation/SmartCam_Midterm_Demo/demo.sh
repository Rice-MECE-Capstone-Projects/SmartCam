#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f /opt/ros/humble/setup.bash ]; then
  echo 'ERROR: ROS2 Humble is not installed at /opt/ros/humble'
  exit 2
fi
# ROS2 setup sometimes uses initially-unset AMENT_* variables.
set +u
source /opt/ros/humble/setup.bash
if [ -f "$HOME/Autonomous-RC-Car/farah_ws/install/setup.bash" ]; then
  source "$HOME/Autonomous-RC-Car/farah_ws/install/setup.bash"
fi
set -u
usage() {
  cat <<'HELP'
SmartCam ELEC 594 — Midterm LIVE Demo

Run these in separate terminals:
  ./demo.sh gazebo             Start the existing articubot_one Gazebo Classic simulation
  ./demo.sh scene A            Set red LEFT and blue RIGHT, reset robot
  ./demo.sh camera             View the robot's actual ROS camera
  ./demo.sh red-preview        Print instructions, detections and [v, omega] without driving
  ./demo.sh red-drive          Drive robot toward RED for up to 20 seconds (explicit confirmation)
  ./demo.sh scene B            Swap positions: red RIGHT and blue LEFT; reset robot
  ./demo.sh blue-preview
  ./demo.sh blue-drive
  ./demo.sh stop               Publish zeros to /cmd_vel several times
  ./demo.sh check              Check required live ROS2 topics and controller

This is a rule-based, language-conditioned visual baseline, NOT a trained VLA.
This package does not change existing workspaces, model weights or older ROS bags.
HELP
}
cmd="${1:-help}"
case "$cmd" in
  gazebo)
    if pgrep -x gzserver >/dev/null; then echo 'Gazebo already running. Do not launch a duplicate.'; exit 0; fi
    exec ros2 launch articubot_one launch_sim.launch.py use_sim_time:=true ;;
  check)
    if ! pgrep -x gzserver >/dev/null; then echo 'FAIL: Gazebo gzserver not running'; exit 3; fi
    for topic in /camera/image_raw /scan /diff_cont/odom /diff_cont/cmd_vel_unstamped /clock; do
      if timeout 8s ros2 topic list | grep -Fx "$topic" >/dev/null; then echo "PASS: $topic"; else echo "FAIL: $topic"; exit 4; fi
    done
    echo '===== CONTROLLERS ====='
    timeout 10s ros2 control list_controllers
    echo '===== ROBOT POSE ====='
    timeout 6s gz model -m my_bot -p ;;
  scene)
    /usr/bin/python3 "$ROOT/scripts/scene.py" "${2:-A}" ;;
  camera)
    exec ros2 run rqt_image_view rqt_image_view ;;
  red-preview|blue-preview|red-drive|blue-drive)
    color="${cmd%%-*}"
    if [[ "$cmd" == *-drive ]]; then
      /usr/bin/python3 "$ROOT/scripts/color_demo.py" --target "$color" --drive --duration 20
    else
      /usr/bin/python3 "$ROOT/scripts/color_demo.py" --target "$color" --duration 20
    fi ;;
  stop)
    for i in 1 2 3; do
      timeout 5s ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.0}, angular: {z: 0.0}}' || true
    done ;;
  help|-h|--help)
    usage ;;
  *)
    echo "Unknown command: $cmd"
    usage
    exit 2 ;;
esac
