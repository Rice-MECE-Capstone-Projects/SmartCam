#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMAND="${1:-help}"
if [[ $# -gt 0 ]]; then shift; fi
case "$COMMAND" in
  help|-h|--help)
    cat <<'HELP'
SmartCam VLA automation (Gazebo Classic / ROS2 Humble, simulation only)

  ./smartcam.sh check
  ./smartcam.sh scene --scene A
  ./smartcam.sh collect --scene A --target red --task 'Go to the red object.' --episode red_A_001
  ./smartcam.sh inspect --episode red_A_001
  ./smartcam.sh export --episode red_A_001

In a SEPARATE Conda terminal with lerobot==0.6.1 (NO ROS setup):
  ./smartcam.sh convert
  ./smartcam.sh train
  ./smartcam.sh train --execute

Use --help after collect/inspect/export/convert/train for detailed options.
The scripts do NOT perform automatic target navigation or autonomous VLA deployment.
HELP
    ;;
  check|scene|collect|inspect|export)
    if [[ ! -f /opt/ros/humble/setup.bash ]]; then
      echo "ROS2 Humble not found under /opt/ros/humble" >&2
      exit 1
    fi
    source /opt/ros/humble/setup.bash
    if [[ -f "$HOME/Autonomous-RC-Car/farah_ws/install/setup.bash" ]]; then
      source "$HOME/Autonomous-RC-Car/farah_ws/install/setup.bash"
    fi
    case "$COMMAND" in
      check) script="doctor.py" ;;
      scene) script="scene.py" ;;
      collect) script="collect.py" ;;
      inspect) script="inspect_bag.py" ;;
      export) script="export_raw.py" ;;
    esac
    exec /usr/bin/python3 "$ROOT/scripts/$script" "$@"
    ;;
  convert|train)
    if [[ -z "${CONDA_PREFIX:-}" ]]; then
      echo "Activate a Conda environment with lerobot 0.6.1 before $COMMAND" >&2
      exit 1
    fi
    unset PYTHONPATH
    if [[ "$COMMAND" == "convert" ]]; then
      exec "$CONDA_PREFIX/bin/python" "$ROOT/scripts/convert_lerobot.py" "$@"
    else
      exec "$CONDA_PREFIX/bin/python" "$ROOT/scripts/train_smolvla.py" "$@"
    fi
    ;;
  *) echo "Unknown command: $COMMAND" >&2; exit 2 ;;
esac
