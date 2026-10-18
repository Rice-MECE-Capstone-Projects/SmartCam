#!/usr/bin/env python3
"""Read-only ROS2 bag action/sensor audit using ROS2 system Python + rclpy."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
from common import command_from_ros_msg, is_motion, json_write, manifest_for


def audit(bag:Path,action:str,camera:str,odom:str,output:Path|None=None):
    from rclpy.serialization import deserialize_message
    from geometry_msgs.msg import Twist, TwistStamped
    bag=bag.expanduser()
    dbs=sorted(bag.glob('*.db3'))
    if not dbs:raise RuntimeError('No ROS2 SQLite .db3 found. MCAP needs a separate converter.')
    counts=Counter(); changes=[];nonzero=0;forward=0;left=0;right=0;reverse=0;stops=0
    maxv=0.;maxw=0.;firstcmd=None;lastcmd=None;all_times=[];img_data=None
    other=[]
    for db in dbs:
        conn=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
        topic_rows=conn.execute('SELECT id,name,type FROM topics').fetchall()
        lookup={int(i):(name,typ) for i,name,typ in topic_rows}
        for name,typ in [(name,typ) for _,name,typ in topic_rows]:
            if name==action and typ not in ('geometry_msgs/msg/Twist','geometry_msgs/msg/TwistStamped'):
                raise RuntimeError(f'Unexpected control message type {typ}')
        for topic_id,stamp,data in conn.execute('SELECT topic_id,timestamp,data FROM messages ORDER BY timestamp'):
            name,typ=lookup[topic_id];counts[name]+=1
            if name==action:
                typ_cls = TwistStamped if typ=='geometry_msgs/msg/TwistStamped' else Twist
                msg=deserialize_message(data,typ_cls);v,w=command_from_ros_msg(msg)
                if not all(abs(x)<1e6 for x in [v,w]):raise RuntimeError('Non-finite or invalid velocities')
                if firstcmd is None:firstcmd=stamp
                lastcmd=stamp
                maxv=max(abs(v),maxv);maxw=max(abs(w),maxw)
                if is_motion(v,w):
                    nonzero+=1
                    if len(changes)<12: changes.append([round(v,4),round(w,4)])
                else:stops+=1
                if v>0.005:forward+=1
                if v < -0.005:reverse+=1
                if w>0.005:left+=1
                if w < -0.005:right+=1
            elif name==camera and img_data is None:
                from sensor_msgs.msg import Image
                img=deserialize_message(data,Image)
                img_data={'encoding':str(img.encoding),'width':img.width,'height':img.height,'step':img.step,
                          'header_stamp_sec':int(img.header.stamp.sec)+int(img.header.stamp.nanosec)*1e-9,
                          'bag_receive_time_sec':int(stamp)*1e-9}
        conn.close()
    length=sum(counts.values())
    summary={'bag':str(bag),'message_count':length,'topic_counts':dict(counts),'action_topic':action,
             'total_commands':counts[action],'nonzero_commands':nonzero,'forward':forward,'reverse':reverse,
             'left_turn':left,'right_turn':right,'stop_commands':stops,'max_abs_v_m_s':maxv,'max_abs_omega_rad_s':maxw,
             'first_cmd_time_sec':None if firstcmd is None else firstcmd/1e9,
             'last_cmd_time_sec':None if lastcmd is None else lastcmd/1e9,'sample_nonzero_actions':changes,
             'first_camera':img_data}
    problems=[]
    if counts[camera] < 10:problems.append('Fewer than 10 RGB frames')
    if counts[odom] < 10:problems.append('Fewer than 10 odometry samples')
    if counts[action] == 0:problems.append('No teacher velocity commands')
    if nonzero<10:problems.append('Fewer than 10 nonzero commands')
    if forward==0:problems.append('No forward motion commands')
    if left==0 or right==0:problems.append('One turning direction missing (OK for single scene, not sufficient for whole training set)')
    summary['warnings']=problems
    if output:json_write(output,summary)
    print('===== SmartCam BAG AUDIT =====')
    print('Bag:',bag)
    for k in [camera,odom,action]:print(k,'samples:',counts[k])
    print('Commands: total',counts[action],'nonzero',nonzero,'forward',forward,'reverse',reverse,'left',left,'right',right,'stop',stops)
    print('Max speeds: |v|=',round(maxv,4),'m/s; |omega|=',round(maxw,4),'rad/s')
    print('Sample nonzero actions:',changes[:8]);print('First RGB:',img_data)
    print('Warnings:',problems if problems else '(none detected)')
    print('Note: presence of messages cannot prove synchronized, correct task, collision-free or arrival.')
    if output:print('Report:',output)
    return summary


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bag',type=Path,required=True)
    ap.add_argument('--action',default=None)
    ap.add_argument('--camera',default=None)
    ap.add_argument('--odom',default=None)
    ap.add_argument('--report',type=Path,default=None)
    args=ap.parse_args()
    bag=args.bag.expanduser()
    meta_path=manifest_for(bag)
    meta=json.loads(meta_path.read_text()) if meta_path.is_file() else {}
    topics=meta.get('topics',{})
    dest=args.report or (bag.parent.parent / 'reports'/(bag.name+'_audit.json'))
    try:
        audit(bag,args.action or topics.get('action','/cmd_vel'),args.camera or topics.get('camera','/camera/image_raw'),
              args.odom or topics.get('odom','/diff_cont/odom'),dest.expanduser())
    except Exception as e:
        print('AUDIT ERROR:',type(e).__name__,str(e),file=sys.stderr);return 2
    return 0

if __name__=='__main__':sys.exit(main())
