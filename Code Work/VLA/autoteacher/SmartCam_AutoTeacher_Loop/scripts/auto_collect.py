#!/usr/bin/env python3
"""One-terminal Gazebo Classic teacher-rollout + ROS bag capture.

This drives SIMULATION only, via the EXISTING school color_demo.py after
explicit operator authorization, and DOES NOT train any neural model.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

CAM = '/camera/image_raw'
ODOM = '/diff_cont/odom'
SCAN = '/scan'
CLOCK = '/clock'
ACTION = '/cmd_vel'
CTRL = '/diff_cont/cmd_vel_unstamped'
TYPE_EXPECT = {
    CAM: 'sensor_msgs/msg/Image',
    ODOM: 'nav_msgs/msg/Odometry',
    SCAN: 'sensor_msgs/msg/LaserScan',
    CLOCK: 'rosgraph_msgs/msg/Clock',
    ACTION: 'geometry_msgs/msg/Twist',
    CTRL: 'geometry_msgs/msg/Twist',
}
ROOT = Path.home() / 'smartcam_vla' / 'SmartCam_Midterm_Demo'
DEFAULT_BAGS = Path.home() / 'smartcam_vla' / 'datasets' / 'rosbags'


def run_checked(command: list[str], timeout: int=20) -> str:
    p = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=timeout, check=False)
    if p.returncode:
        raise RuntimeError(f'Command failed (exit={p.returncode}): {command}\n{p.stdout[-1200:]}')
    return p.stdout.strip()


def parse_topics(lines: str) -> dict[str, str]:
    result = {}
    for line in lines.splitlines():
        m = re.match(r'^\s*(/\S+)\s+\[([^\]]+)\]\s*$', line)
        if m:
            result[m.group(1)] = m.group(2)
    return result


def validate_name(name: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,80}', name):
        raise ValueError('Episode ID: 3-80 ASCII letters/digits/_/- only')
    return name


def get_gazebo_pose(name: str) -> str:
    pose = run_checked(['gz', 'model', '-m', name, '-p'], timeout=8).splitlines()
    found = next((line.strip() for line in pose if len(line.strip().split()) == 6), None)
    if not found:
        raise RuntimeError(f'No valid Gazebo Classic model pose for {name}; check model names')
    try:
        [float(x) for x in found.split()]
    except ValueError as e:
        raise RuntimeError('Non-numeric Gazebo pose: ' + found) from e
    return found


def preflight() -> dict:
    if not (ROOT / 'demo.sh').is_file() or not (ROOT / 'scripts' / 'color_demo.py').is_file():
        raise RuntimeError(f'Existing school demo package not found under {ROOT}; this kit does not install Gazebo')
    if not Path('/opt/ros/humble/setup.bash').is_file():
        raise RuntimeError('ROS 2 Humble not installed at /opt/ros/humble')
    run_checked(['pgrep', '-x', 'gzserver'], 5)
    pose = get_gazebo_pose('my_bot')
    topics = parse_topics(run_checked(['ros2', 'topic', 'list', '-t'], 18))
    errors = [f'{k}: expected {v}, found {topics.get(k)}'
              for k, v in TYPE_EXPECT.items() if k != CTRL and topics.get(k) != v]
    if errors:
        raise RuntimeError('Missing/incorrect ROS topics:\n' + '\n'.join(errors))
    # Controller output topic may be remapped by a twist_mux installation. Keep
    # requested /cmd_vel as teacher labels, record effective controller when present.
    has_ctrl = topics.get(CTRL) == TYPE_EXPECT[CTRL]
    try:
        run_checked(['ros2', 'topic', 'echo', CLOCK, '--once'], 9)
    except (subprocess.TimeoutExpired, RuntimeError) as e:
        raise RuntimeError('No live /clock, or Gazebo is paused / domain mismatch') from e
    nodes = run_checked(['ros2', 'node', 'list'], 15).splitlines()
    conflicts = {'/smartcam_midterm_color_baseline', '/smartcam_advanced_ablation',
                 '/smartcam_keyboard_teleop', '/smartcam_auto_teleop'}
    active = sorted(conflicts.intersection(set(nodes)))
    if active:
        raise RuntimeError(f'Another active teacher/teleop is running; stop it before resetting: {active}')
    return {'pose': pose, 'controller_topic_available': has_ctrl,
            'ros_domain_id': os.environ.get('ROS_DOMAIN_ID', '0'),
            'topic_count': len(topics)}


def stop_process(proc: subprocess.Popen | None, grace: int=35) -> int | None:
    if proc is None:
        return None
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        try:
            return proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            print('WARNING: process delayed after SIGINT; requesting SIGTERM (bag may need reindex)', flush=True)
            try: os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: return proc.wait(timeout=12)
            except subprocess.TimeoutExpired:
                print('ERROR: process still alive. Investigate before new run.', flush=True)
                return None
    return proc.returncode


def send_zero_twist() -> None:
    cmd = ['ros2', 'topic', 'pub', '--once', ACTION,
           'geometry_msgs/msg/Twist', '{linear: {x: 0.0}, angular: {z: 0.0}}']
    for _ in range(2):
        try: subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=6)
        except Exception: pass


def replay_log(stream, log_path: Path):
    with log_path.open('w', encoding='utf8') as f:
        for line in stream:
            print(line, end='', flush=True)
            f.write(line)
            f.flush()


def collect(args) -> int:
    validate_name(args.episode)
    if args.duration <= 2 or args.duration > 90:
        raise ValueError('Teacher duration must be in range (2, 90] seconds; color_demo limits to 90')
    bag_root = args.root.expanduser().resolve()
    if not bag_root.exists():bag_root.mkdir(parents=True)
    if shutil.disk_usage(bag_root).free < 2 * 1024**3:
        raise RuntimeError('At least 2GiB free disk is recommended for camera bag capture')
    bag = bag_root / args.episode
    meta = bag_root / f'{args.episode}.manifest.json'
    teacher_log = bag_root / f'{args.episode}.teacher.log'
    recorder_log = bag_root / f'{args.episode}.recorder.log'
    if any(p.exists() for p in (bag, meta, teacher_log, recorder_log)):
        raise RuntimeError('Refusing to overwrite an existing episode or logs: ' + args.episode)
    info = preflight()
    print('ROS domain:', info['ros_domain_id'])
    print('Resetting ONLY Gazebo SIMULATION. No robot hardware must share this ROS_DOMAIN_ID.')
    print(run_checked([str(ROOT / 'demo.sh'), 'scene', args.scene], 65))
    robot_before = get_gazebo_pose('my_bot')
    target_pose = get_gazebo_pose(f'{args.target}_target')
    task = f'Go to the {args.target} object.'
    print('Task:', task, 'Robot:', robot_before, 'Target:', target_pose)
    print('Check Gazebo and RGB view, and verify no other velocity command publishers.')
    print('Leave Gazebo visible. PAUSE simulation if unsafe; Ctrl+C aborts and sends stop.')
    if input('Type DRIVE to authorize ONE simulated teacher rollout: ').strip() != 'DRIVE':
        print('Canceled: no movement or bag was recorded.')
        return 0

    topics = [CAM, ODOM, ACTION, SCAN, CLOCK]
    if info['controller_topic_available']:
        topics.append(CTRL)
    # Do not silently re-use episode IDs; keep unknown outcome until reviewed.
    data = {
        'schema_version': 1, 'episode_id': args.episode, 'scene': args.scene,
        'target': args.target, 'task': task, 'split': args.split,
        'outcome': 'unknown', 'status': 'preparing',
        'recording_is_simulation_only': True,
        'source': 'School Gazebo Classic / SmartCam rule-based teacher',
        'teacher': 'SmartCam_Midterm_Demo/scripts/color_demo.py --drive',
        'teacher_duration_seconds': args.duration,
        'ros_domain_id': info['ros_domain_id'],
        'topics': {'camera': CAM, 'odom': ODOM, 'action': ACTION,
                   'scan': SCAN, 'clock': CLOCK,
                   'controller_action': CTRL if info['controller_topic_available'] else ''},
        'start_robot_pose': robot_before,
        'target_pose': target_pose,
        'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'notes': 'UNREVIEWED: time-limit or LiDAR stopping is not proof of task arrival.',
    }
    meta.write_text(json.dumps(data, indent=2), encoding='utf8')
    teacher = None
    recorder = None
    bag_log = None
    rc_teacher = None
    rc_rec = None
    interrupted = False
    try:
        bag_log = recorder_log.open('w', encoding='utf8')
        recorder = subprocess.Popen(['ros2', 'bag', 'record', '--use-sim-time', '-o', str(bag), *topics],
                                    stdin=subprocess.DEVNULL, stdout=bag_log,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(3.0)
        if recorder.poll() is not None:
            raise RuntimeError('Recorder exited at startup; inspect recorder log: '+str(recorder_log))
        data['status'] = 'recording';meta.write_text(json.dumps(data, indent=2), encoding='utf8')
        print('RECORDING:', bag, flush=True)
        command = ['/usr/bin/python3', str(ROOT/'scripts'/'color_demo.py'),
                   '--target', args.target, '--drive', '--duration', str(args.duration)]
        teacher = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, bufsize=1,
                                   start_new_session=True)
        assert teacher.stdin is not None and teacher.stdout is not None
        teacher.stdin.write('DRIVE\n');teacher.stdin.flush();teacher.stdin.close()
        worker = threading.Thread(target=replay_log, args=(teacher.stdout, teacher_log), daemon=True)
        worker.start()
        try:
            rc_teacher = teacher.wait(timeout=args.duration + 35.0)
        except subprocess.TimeoutExpired:
            print('Teacher exceeded watchdog time: stopping.', flush=True)
            rc_teacher = stop_process(teacher, grace=12)
        worker.join(timeout=5)
    except KeyboardInterrupt:
        interrupted = True
        print('\nInterrupted: stopping teacher, robot and recorder.', flush=True)
    except Exception as exc:
        print('COLLECTION ERROR:', str(exc), file=sys.stderr, flush=True)
        interrupted = True
    finally:
        if teacher is not None and teacher.poll() is None:
            rc_teacher = stop_process(teacher, grace=12)
        send_zero_twist()
        time.sleep(0.7)
        if recorder is not None:
            rc_rec = stop_process(recorder, grace=40)
        if bag_log is not None: bag_log.close()
        data['teacher_exit_code'] = rc_teacher
        data['recorder_exit_code'] = rc_rec
        data['status'] = ('recorded_unreviewed' if (bag / 'metadata.yaml').exists()
                          and rc_teacher == 0 and not interrupted else 'incomplete_or_aborted')
        data['ended_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        try: data['end_robot_pose'] = get_gazebo_pose('my_bot')
        except Exception: data['end_robot_pose'] = None
        data['notes'] = ('Unreviewed. Review recorded video/robot distance and stop reason. '
                         'Only label SUCCESS after verifying target reached and stopped by goal condition.')
        meta.write_text(json.dumps(data, indent=2), encoding='utf8')
    print('BAG:', bag)
    print('MANIFEST:', meta)
    print('RECORD STATUS:', data['status'], 'TEACHER EXIT:', rc_teacher, 'RECORDER EXIT:', rc_rec)
    if not (bag / 'metadata.yaml').is_file():
        print('No bag metadata.yaml; check recorder log. Do NOT train from this episode.')
        return 2
    print('AUDIT (may report legitimate single-direction warning for one goal):')
    audit = subprocess.run(['/usr/bin/python3', str(Path(__file__).parent / 'audit_bag.py'),
                            '--bag', str(bag)], check=False)
    print('AUDIT EXIT:', audit.returncode)
    print('NEXT: manually review outcome, then label and export only valid data.')
    return 0 if data['status']=='recorded_unreviewed' and audit.returncode==0 else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='operation', required=True)
    sub.add_parser('check', help='Read-only check of school Gazebo/ROS + robot/sensors')
    c = sub.add_parser('collect', help='Auto-drive simulation with existing teacher and record synchronized bag')
    c.add_argument('--scene', choices=['A','B'], required=True)
    c.add_argument('--target', choices=['red','blue'], required=True)
    c.add_argument('--episode', required=True)
    c.add_argument('--split', choices=['train','val','test'], default='train')
    c.add_argument('--duration', type=float, default=55.0)
    c.add_argument('--root', type=Path, default=DEFAULT_BAGS)
    args = ap.parse_args()
    try:
        if args.operation == 'check':
            info = preflight()
            print('SIMULATOR CHECK PASS:', json.dumps(info, indent=2))
            print('No robot movement and no data recording performed.')
            return 0
        return collect(args)
    except KeyboardInterrupt:
        print('Stopped by operator.')
        return 130
    except Exception as exc:
        print('ERROR:', type(exc).__name__, str(exc), file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
