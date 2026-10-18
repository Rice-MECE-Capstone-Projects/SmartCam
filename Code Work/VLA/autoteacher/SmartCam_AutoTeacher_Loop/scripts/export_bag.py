#!/usr/bin/env python3
"""ROS2 SQLite -> timestamp-reviewed PNG+CSV, no model and no motor commands."""
import argparse
import bisect
import csv
import json
import math
from pathlib import Path
import sqlite3
import sys
from common import (command_from_ros_msg, odom_from_ros_msg, pack_png_rgb, is_motion,
                    json_write,manifest_for)


def bag_rows(bag,required_types):
    dbs=sorted(bag.glob('*.db3'))
    if not dbs:raise RuntimeError('No sqlite3 .db3 files in bag')
    for db in dbs:
        conn=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
        mapping={int(i):(n,t) for i,n,t in conn.execute('SELECT id,name,type FROM topics')}
        for i,ts,data in conn.execute('SELECT topic_id,timestamp,data FROM messages ORDER BY timestamp'):
            name,typ=mapping[i]
            if name in required_types:
                if typ not in required_types[name]:
                    raise RuntimeError(f'{name}: expected {required_types[name]}, got {typ}')
                yield name,typ,int(ts),data
        conn.close()


def unpack_events(bag,camera,odom,action):
    from rclpy.serialization import deserialize_message
    from geometry_msgs.msg import Twist, TwistStamped
    from nav_msgs.msg import Odometry
    req={camera:{'sensor_msgs/msg/Image'},odom:{'nav_msgs/msg/Odometry'},
         action:{'geometry_msgs/msg/Twist','geometry_msgs/msg/TwistStamped'}}
    acts=[];states=[]
    for name,typ,t,packet in bag_rows(bag,req):
        if name==action:
            msg=deserialize_message(packet,TwistStamped if typ.endswith('TwistStamped') else Twist)
            acts.append((t,command_from_ros_msg(msg)))
        elif name==odom:
            states.append((t,odom_from_ros_msg(deserialize_message(packet,Odometry))))
    acts.sort(key=lambda x:x[0]);states.sort(key=lambda x:x[0])
    return acts,states


def export(args):
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import Image
    bag=args.bag.expanduser(); meta_file=manifest_for(bag)
    if not meta_file.is_file():raise RuntimeError('Missing episode manifest; do not invent language label. Use record_episode first.')
    meta=json.loads(meta_file.read_text())
    tt=meta['topics'];camera=args.camera or tt['camera'];odom=args.odom or tt['odom'];action=args.action or tt['action']
    dst=args.output.expanduser() if args.output else (bag.parent.parent/'raw'/bag.name)
    if dst.exists():raise RuntimeError('Refusing overwrite of existing exported episode: '+str(dst))
    acts,states=unpack_events(bag,camera,odom,action)
    if not acts or not states:raise RuntimeError('No action or odometry messages')
    meaningful=[ts for ts,(v,w) in acts if is_motion(v,w)]
    if len(meaningful)<5:raise RuntimeError('Insufficient moving commands (need >=5); do not train on empty/idle Bag')
    a_stamps=[x[0] for x in acts];s_stamps=[x[0] for x in states]
    start_ns=min(meaningful)-int(args.pre_roll*1e9)
    end_ns=max(meaningful)+int(args.post_roll*1e9)
    maxage_ns=int(args.max_age_ms*1e6); shift_ns=int(args.label_shift_ms*1e6)
    if shift_ns!=0:
        print('CAUTION: Nonzero label shift changes temporal correspondence; confirm teacher sensor->command latency before using these labels.')
    dst.mkdir(parents=True,exist_ok=False)
    images=dst/'rgb';images.mkdir()
    rows=[];last_sample=None;last_kept=None;seg=0
    skipped={'outside_motion_window':0,'rate':0,'stale_action':0,'stale_odom':0,'unsupported_image':0,'nonfinite':0}
    required={camera:{'sensor_msgs/msg/Image'},odom:{'nav_msgs/msg/Odometry'},action:{'geometry_msgs/msg/Twist','geometry_msgs/msg/TwistStamped'}}
    period_ns=int(1e9/args.fps)
    for name,typ,stamp,data in bag_rows(bag,required):
        if name!=camera:continue
        if stamp < start_ns or stamp > end_ns:
            skipped['outside_motion_window']+=1;continue
        if last_sample is not None and stamp - last_sample < int(period_ns*0.9):
            skipped['rate']+=1;continue
        last_sample=stamp
        aidx=bisect.bisect_right(a_stamps,stamp+shift_ns)-1
        sidx=bisect.bisect_right(s_stamps,stamp)-1
        if aidx<0 or stamp+shift_ns-a_stamps[aidx]>maxage_ns or stamp+shift_ns<a_stamps[aidx]:
            skipped['stale_action']+=1;continue
        if sidx<0 or stamp-s_stamps[sidx]>maxage_ns or stamp<s_stamps[sidx]:
            skipped['stale_odom']+=1;continue
        vcmd,wcmd=acts[aidx][1];vcur,wcur=states[sidx][1]
        if not all(math.isfinite(x) for x in [vcmd,wcmd,vcur,wcur]):
            skipped['nonfinite']+=1;continue
        msg=deserialize_message(data,Image)
        try:png=pack_png_rgb(msg)
        except ValueError as e:
            skipped['unsupported_image']+=1
            if skipped['unsupported_image']<=2:print('Image dropped:',e,file=sys.stderr)
            continue
        if last_kept is not None and stamp - last_kept > int(period_ns*1.8):seg+=1
        last_kept=stamp
        fn=f'{len(rows):06d}.png';(images/fn).write_bytes(png)
        header_ns=int(msg.header.stamp.sec)*1_000_000_000+int(msg.header.stamp.nanosec)
        rows.append({'index':len(rows),'segment':seg,'image':'rgb/'+fn,'bag_time_ns':stamp,
            'image_header_time_ns':header_ns,'cmd_time_ns':a_stamps[aidx],
            'odom_time_ns':s_stamps[sidx],
            'cmd_age_ms':round((stamp+shift_ns-a_stamps[aidx])/1e6,3),
            'odom_age_ms':round((stamp-s_stamps[sidx])/1e6,3),
            'v_current_m_s':vcur,'omega_current_rad_s':wcur,
            'v_command_m_s':vcmd,'omega_command_rad_s':wcmd,
            'task':meta['task'],'scene':meta['scene'],'target':meta['target']})
        if args.max_frames and len(rows)>=args.max_frames:break
    if not rows:
        raise RuntimeError('No synchronized frames exported; inspect data/clock/timestamps and do not treat as training data.')
    with (dst/'samples.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    header_offsets_ms=[(r['bag_time_ns']-r['image_header_time_ns'])/1e6 for r in rows if r['image_header_time_ns']!=0]
    hmed=sorted(header_offsets_ms)[len(header_offsets_ms)//2] if header_offsets_ms else None
    motion_rows=sum(is_motion(r['v_command_m_s'],r['omega_command_rad_s']) for r in rows)
    summary={'episode_id':meta['episode_id'],'task':meta['task'],'scene':meta['scene'],'target':meta['target'],
             'outcome':meta.get('outcome','unknown'),'split':meta.get('split','train'),
             'source_bag':str(bag),'frame_count':len(rows),'moving_frames':motion_rows,
             'segments':seg+1,'fps':args.fps,'max_age_ms':args.max_age_ms,'label_shift_ms':args.label_shift_ms,
             'median_image_header_minus_receipt_ms':None if hmed is None else -hmed,
             'skipped':skipped,'image_size':{'width':msg.width,'height':msg.height},
             'notes':'Teacher velocities are labels. Outcomes must be manually verified. Gaps segmented to avoid cross-reset action chunks. This is NOT trained VLA.'}
    json_write(dst/'metadata.json',summary)
    print('EXPORTED:',dst,'frames:',len(rows),'moving:',motion_rows,'segments:',seg+1)
    print('Rejected frames:',skipped)
    if hmed is not None and abs(hmed)>250:
        print('WARNING: RGB header timestamps differ >250ms from bag timestamps. Verify /clock and synchronization before training.')
    if motion_rows<5:print('WARNING: fewer than 5 aligned moving frames; not useful as training data')
    print('Next: inspect samples.csv and RGB manually; mark real episode outcome before conversion.')
    return 0


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bag',type=Path,required=True)
    ap.add_argument('--output',type=Path)
    ap.add_argument('--camera',type=str)
    ap.add_argument('--odom',type=str)
    ap.add_argument('--action',type=str)
    ap.add_argument('--fps',type=int,default=10)
    ap.add_argument('--max-age-ms',type=int,default=300)
    ap.add_argument('--label-shift-ms',type=float,default=0.0)
    ap.add_argument('--pre-roll',type=float,default=1.0)
    ap.add_argument('--post-roll',type=float,default=2.0)
    ap.add_argument('--max-frames',type=int,default=500)
    args=ap.parse_args()
    if args.fps<=0 or args.fps>60 or args.max_age_ms<=0:raise SystemExit('Invalid fps or age limit')
    try:return export(args)
    except Exception as e:
        print('EXPORT ERROR:',type(e).__name__,str(e),file=sys.stderr);return 2

if __name__=='__main__':sys.exit(main())
