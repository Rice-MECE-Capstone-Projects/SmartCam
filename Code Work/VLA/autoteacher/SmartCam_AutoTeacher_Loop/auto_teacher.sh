#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-help}"
if [ "$#" -ge 1 ]; then shift; fi
case "$ACTION" in
  help|-h|--help)
    cat <<'HELP'
SmartCam AutoTeacher (School Gazebo Classic + ROS2 Humble, SIMULATION ONLY)
  ./auto_teacher.sh check
  ./auto_teacher.sh collect --scene B --target blue --episode B_blue_auto_001 --duration 55
  ./auto_teacher.sh audit --bag ~/smartcam_vla/datasets/rosbags/B_blue_auto_001
  ./auto_teacher.sh label --bag ~/smartcam_vla/datasets/rosbags/B_blue_auto_001 --outcome partial --notes 'Reached time limit without verified goal stopping'
  ./auto_teacher.sh export --bag ~/smartcam_vla/datasets/rosbags/B_blue_auto_001 --fps 10

Separate Conda terminal (no ROS setup; activate smartcam_smolvla):
  ./auto_teacher.sh convert --raw-root ~/smartcam_vla/datasets/raw --output ~/smartcam_vla/datasets/lerobot/velocity_train_v1 --repo-id smartcam/velocity_train_v1
  ./auto_teacher.sh model env|prepare|train|verify [additional args]
Note: model training NEVER starts automatically after a new collection.
HELP
    ;;
  check|collect|audit|export|label)
    [ -f /opt/ros/humble/setup.bash ] || { echo 'Missing ROS 2 Humble' >&2; exit 2; }
    # ROS environment scripts sometimes reference unset variables; avoid nounset.
    set +u
    source /opt/ros/humble/setup.bash
    [ ! -f "$HOME/Autonomous-RC-Car/farah_ws/install/setup.bash" ] || source "$HOME/Autonomous-RC-Car/farah_ws/install/setup.bash"
    case "$ACTION" in
      check|collect) SCRIPT=auto_collect.py; set -- "$ACTION" "$@" ;;
      audit) SCRIPT=audit_bag.py ;;
      export) SCRIPT=export_bag.py ;;
      label) SCRIPT=label_episode.py ;;
    esac
    exec /usr/bin/python3 "$ROOT/scripts/$SCRIPT" "$@"
    ;;
  convert)
    [ -n "${CONDA_PREFIX:-}" ] || { echo 'Activate smartcam_smolvla Conda environment first' >&2; exit 2; }
    unset PYTHONPATH
    export PYTHONNOUSERSITE=1
    exec "$CONDA_PREFIX/bin/python" "$ROOT/scripts/to_lerobot.py" "$@"
    ;;
  model)
    [ -n "${CONDA_PREFIX:-}" ] || { echo 'Activate smartcam_smolvla Conda environment first' >&2; exit 2; }
    unset PYTHONPATH
    export PYTHONNOUSERSITE=1
    exec "$CONDA_PREFIX/bin/python" "$ROOT/scripts/mobile_steps.py" "$@"
    ;;
  *) echo "Unknown command: $ACTION (run ./auto_teacher.sh help)" >&2; exit 2;;
esac
