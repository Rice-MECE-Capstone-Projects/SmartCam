"""Shared helpers for SmartCam ROS2/Gazebo-only dataset workflow."""
from __future__ import annotations
import bisect
import json
import math
import re
import struct
import zlib
from pathlib import Path

VALID_TASKS = {"red": "Go to the red object.", "blue": "Go to the blue object."}


def parse_ros_topics(output: str) -> dict[str, str]:
    """Read `ros2 topic list -t` format, retaining exact topic names."""
    result = {}
    for line in output.splitlines():
        match = re.match(r"^\s*(/\S+)\s+\[([^\]]+)\]\s*$", line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def newest_not_after(events, t_ns: int, offset_ns: int = 0):
    """events sorted (timestamp_ns, object): causally past or same timestamp."""
    if not events:
        return None
    stamps = [x[0] for x in events]  # avoid for many frames: pass precomputed stamps in export
    i = bisect.bisect_right(stamps, t_ns + offset_ns) - 1
    return events[i] if i >= 0 else None


def is_motion(v: float, w: float, epsilon: float = 0.005) -> bool:
    return abs(v) > epsilon or abs(w) > epsilon


def command_from_ros_msg(msg):
    """Unpack geometry_msgs/Twist or geometry_msgs/TwistStamped."""
    twist = msg.twist if hasattr(msg, 'twist') else msg
    return float(twist.linear.x), float(twist.angular.z)


def odom_from_ros_msg(msg):
    twist = msg.twist.twist
    return float(twist.linear.x), float(twist.angular.z)


def pack_png_rgb(msg) -> bytes:
    """Pure stdlib ROS Image -> PNG, supports rgb8, bgr8, rgba8, bgra8, mono8."""
    w, h = int(msg.width), int(msg.height)
    enc = str(msg.encoding).lower()
    channels = {"rgb8":3, "bgr8":3, "rgba8":4, "bgra8":4, "mono8":1}.get(enc)
    if not channels:
        raise ValueError(f"Unsupported image encoding '{msg.encoding}'. Use rgb8/bgr8/rgba8/bgra8/mono8 or modify converter.")
    if w <= 0 or h <= 0 or w > 8192 or h > 8192:
        raise ValueError(f"Invalid image dimensions {w}x{h}")
    if msg.step < w * channels:
        raise ValueError("Image step smaller than width*channels")
    data = bytes(msg.data)
    if len(data) < h * msg.step:
        raise ValueError("Truncated ROS image")
    compressed = zlib.compressobj(level=4)
    payload = bytearray()
    for row in range(h):
        line = data[row * msg.step:row * msg.step + w*channels]
        if enc == "bgr8":
            rgb = bytearray(len(line))
            rgb[0::3], rgb[1::3], rgb[2::3] = line[2::3], line[1::3], line[0::3]
            line = bytes(rgb)
        elif enc == "bgra8":
            rgb = bytearray(w*3)
            rgb[0::3],rgb[1::3],rgb[2::3] = line[2::4],line[1::4],line[0::4]
            line = bytes(rgb)
        elif enc == "rgba8":
            rgb = bytearray(w*3)
            rgb[0::3],rgb[1::3],rgb[2::3] = line[0::4],line[1::4],line[2::4]
            line = bytes(rgb)
        elif enc == "mono8":
            rgb = bytearray(w*3)
            rgb[0::3] = line; rgb[1::3] = line; rgb[2::3] = line
            line = bytes(rgb)
        payload.extend(compressed.compress(b'\x00' + line))
    payload.extend(compressed.flush())
    def chunk(kind: bytes, data: bytes):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',w,h,8,2,0,0,0))+chunk(b'IDAT',bytes(payload))+chunk(b'IEND',b'')


def json_write(path: Path, obj: dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding='utf8')


def manifest_for(bag_dir: Path) -> Path:
    return bag_dir.parent / (bag_dir.name + '.manifest.json')


def ensure_id(name: str):
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,80}', name):
        raise ValueError('Episode ID must have 3-80 ASCII letters/digits/underscore/hyphen')
    return name


def finite_pair(v:float,w:float):
    return math.isfinite(v) and math.isfinite(w)
