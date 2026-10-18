#!/usr/bin/env python3
"""Prepare Scene A/B in an already-running Gazebo Classic simulation."""
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def run(argv, timeout=20, check=True):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=check)


def get_pose(name):
    result = run(['gz', 'model', '-m', name, '-p'], check=False, timeout=8)
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    try:
        values = [float(x) for x in output.split()]
    except ValueError:
        return None
    return output if len(values) == 6 else None


def pose(name, x, y, z, yaw=0.0):
    run(['gz', 'model', '-m', name, '-x', str(x), '-y', str(y),
         '-z', str(z), '-R', '0', '-P', '0', '-Y', str(yaw)], timeout=8)


def place_target(name, x, y):
    if get_pose(name) is None:
        print(f'Spawning {name} ...', flush=True)
        argv = ['ros2', 'run', 'gazebo_ros', 'spawn_entity.py', '-entity', name,
                '-file', str(ROOT / 'scenes' / (name + '.sdf')),
                '-x', str(x), '-y', str(y), '-z', '0.35']
        result = run(argv, timeout=30)
        print(result.stdout.strip())
    else:
        pose(name, x, y, 0.35)
    print(f'{name}: {get_pose(name)}')


def main():
    scene = sys.argv[1].upper() if len(sys.argv) > 1 else 'A'
    if scene not in ('A', 'B'):
        raise SystemExit('Only scene A or B is supported.')
    if get_pose('my_bot') is None:
        raise SystemExit('Gazebo robot my_bot not found. Start ./demo.sh gazebo first.')
    # Stop any navigation input before teleporting the robot.
    for _ in range(3):
        run(['ros2', 'topic', 'pub', '--once', '/cmd_vel', 'geometry_msgs/msg/Twist',
             '{linear: {x: 0.0}, angular: {z: 0.0}}'], timeout=8)
    red_y, blue_y = (0.8, -0.8) if scene == 'A' else (-0.8, 0.8)
    place_target('red_target', 2.0, red_y)
    place_target('blue_target', 2.0, blue_y)
    pose('my_bot', -0.70, 0.0, 0.033)
    time.sleep(1)
    print(f'SCENE {scene} READY: my_bot {get_pose("my_bot")}')
    print('Open ./demo.sh camera, select /camera/image_raw and confirm targets visible.')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print('ERROR:', exc, getattr(exc, 'stderr', ''))
        raise SystemExit(1)
