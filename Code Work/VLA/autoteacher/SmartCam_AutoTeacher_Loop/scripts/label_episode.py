#!/usr/bin/env python3
"""Manually annotate episode outcome after reviewing actual Gazebo footage/logs."""
import argparse
import json
from pathlib import Path
from common import json_write,manifest_for

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bag',type=Path,required=True)
    ap.add_argument('--outcome',choices=['success','partial','failure','unknown'],required=True)
    ap.add_argument('--notes',required=True)
    args=ap.parse_args()
    bag=args.bag.expanduser();p=manifest_for(bag)
    if not p.is_file():raise SystemExit('No session manifest; cannot safely infer task: '+str(p))
    m=json.loads(p.read_text())
    if len(args.notes.strip())<10:raise SystemExit('Provide descriptive notes (minimum 10 chars) documenting outcome evidence.')
    print('Episode:',m['episode_id'],'Task:',m['task'])
    print('Marking:',args.outcome,'Notes:',args.notes)
    if args.outcome=='success':
        print('WARNING: only mark SUCCESS if goal reached AND stopped by goal condition; TIME LIMIT does NOT count.')
        if input('Type VERIFIED to confirm visual/log evidence: ').strip()!='VERIFIED':
            raise SystemExit('Aborted; outcome unchanged.')
    m['outcome']=args.outcome;m['notes']=args.notes
    json_write(p,m);print('Updated',p)

if __name__=='__main__':main()
