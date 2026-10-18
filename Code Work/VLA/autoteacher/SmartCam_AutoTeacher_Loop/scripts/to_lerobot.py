#!/usr/bin/env python3
"""Converted synchronized SmartCam RGB+2D velocity dataset -> LeRobot v0.6.1, offline only.
Run in Conda Python 3.12 with `lerobot[dataset]==0.6.1`, NOT system ROS2 Python.
"""
import argparse
import csv
from importlib.metadata import version
import json
from pathlib import Path
import sys


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--raw-root',type=Path,default=Path.home()/'smartcam_vla_r9000p/datasets/raw')
    ap.add_argument('--output',type=Path,default=Path.home()/'smartcam_vla_r9000p/datasets/lerobot/smartcam_velocity_v1')
    ap.add_argument('--repo-id',default='smartcam/smartcam_velocity_v1')
    ap.add_argument('--include-partial',action='store_true',help='EXPLICITLY include incomplete demonstrations for interface smoke test only, NOT task-success evaluation')
    ap.add_argument('--min-frames',type=int,default=8)
    ap.add_argument('--width',type=int,default=320)
    ap.add_argument('--height',type=int,default=240)
    args=ap.parse_args()
    if version('lerobot')!='0.6.1':raise SystemExit('Expected exact lerobot==0.6.1')
    import numpy as np
    from PIL import Image
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    raw=args.raw_root.expanduser();out=args.output.expanduser()
    if out.exists():raise SystemExit('Refusing overwrite of dataset: '+str(out))
    if args.min_frames<3 or args.width<16 or args.height<16:raise SystemExit('Invalid frame count / image dimensions')
    episodes=[];excluded=[];fps=None
    for folder in sorted(raw.iterdir()) if raw.exists() else []:
        meta_path=folder/'metadata.json';csv_path=folder/'samples.csv'
        if not meta_path.is_file() or not csv_path.is_file():continue
        meta=json.loads(meta_path.read_text());outcome=meta.get('outcome','unknown')
        if meta.get('split')!='train' or outcome not in (['success','partial'] if args.include_partial else ['success']):
            excluded.append(folder.name);continue
        f=int(meta.get('fps',0))
        if f<=0:raise SystemExit('Invalid FPS in '+str(meta_path))
        if fps is None:fps=f
        if f!=fps:raise SystemExit('Mixed dataset FPS. Normalize all first.')
        with csv_path.open(newline='',encoding='utf8') as file: rows=list(csv.DictReader(file))
        groups={}
        for row in rows:groups.setdefault(row['segment'],[]).append(row)
        for segment,chunk in groups.items():
            if len(chunk)<args.min_frames:continue
            episodes.append((folder,meta,segment,chunk))
    if not episodes:raise SystemExit('No eligible train segment: verify split/outcome; partial samples require --include-partial')
    if len(episodes)<8:print('WARNING: small number of trajectories; suitable for pipeline check, NOT model generalization evidence')
    features={
        'observation.images.front':{'dtype':'image','shape':(args.height,args.width,3),'names':['height','width','channels']},
        'observation.state':{'dtype':'float32','shape':(2,),'names':['v_current_m_s','omega_current_rad_s']},
        'action':{'dtype':'float32','shape':(2,),'names':['v_command_m_s','omega_command_rad_s']},
    }
    dataset=LeRobotDataset.create(repo_id=args.repo_id,root=out,fps=fps,features=features,
                                   robot_type='smartcam_diff_drive_sim',use_videos=False,
                                   image_writer_processes=0,image_writer_threads=0)
    total=0
    try:
        for folder,meta,segment,rows in episodes:
            for row in rows:
                p=(folder/row['image']).resolve()
                if not p.is_relative_to(folder.resolve()) or not p.is_file():
                    raise RuntimeError('Image missing or outside episode root: '+str(p))
                with Image.open(p) as pic:
                    img=np.asarray(pic.convert('RGB').resize((args.width,args.height),Image.Resampling.BILINEAR),dtype=np.uint8)
                state=np.array([float(row['v_current_m_s']),float(row['omega_current_rad_s'])],dtype=np.float32)
                action=np.array([float(row['v_command_m_s']),float(row['omega_command_rad_s'])],dtype=np.float32)
                if not np.all(np.isfinite(state)) or not np.all(np.isfinite(action)):
                    raise RuntimeError('Non-finite state/action in '+str(p))
                dataset.add_frame({'observation.images.front':img,'observation.state':state,
                                   'action':action,'task':meta['task']})
                total+=1
            dataset.save_episode();print('Saved:',folder.name,'segment',segment,'frames',len(rows),'outcome',meta['outcome'])
    finally:
        dataset.finalize()
    print('LOCAL LEROBOT DATASET:',out,'episodes:',len(episodes),'frames:',total,'fps:',fps)
    print('Excluded (val/test/unknown/failure):',excluded)
    print('NOT trained model / NOT autonomous success. Verify dataset images/actions manually before training.')
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print('CONVERSION ERROR:',type(exc).__name__,exc,file=sys.stderr)
        sys.exit(2)
