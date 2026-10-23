import os
import sys
import struct
from pathlib import Path
from types import SimpleNamespace
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from common import parse_ros_topics,pack_png_rgb,command_from_ros_msg,odom_from_ros_msg,ensure_id,is_motion,newest_not_after

class TestCommon(unittest.TestCase):
    def test_topic_parsing(self):
        self.assertEqual(parse_ros_topics('/camera/image_raw [sensor_msgs/msg/Image]\n/model/vehicle_blue/cmd_vel [geometry_msgs/msg/Twist]\n'),
                         {'/camera/image_raw':'sensor_msgs/msg/Image','/model/vehicle_blue/cmd_vel':'geometry_msgs/msg/Twist'})
    def test_message_shapes(self):
        xyz=lambda x: SimpleNamespace(x=x,z=x)
        t=SimpleNamespace(linear=xyz(0.08),angular=xyz(.2))
        self.assertEqual(command_from_ros_msg(t),(.08,.2))
        self.assertEqual(command_from_ros_msg(SimpleNamespace(twist=t)),(.08,.2))
        self.assertEqual(odom_from_ros_msg(SimpleNamespace(twist=SimpleNamespace(twist=t))),(.08,.2))
    def test_png_rgb(self):
        from PIL import Image
        import io
        for enc,data in [('rgb8',bytes([200,0,10,50,70,90])),('bgr8',bytes([10,0,200,90,70,50]))]:
            msg=SimpleNamespace(width=2,height=1,encoding=enc,step=6,data=data)
            im=Image.open(io.BytesIO(pack_png_rgb(msg)))
            self.assertEqual(im.size,(2,1))
            self.assertEqual(im.getpixel((0,0)),(200,0,10))
            self.assertEqual(im.getpixel((1,0)),(50,70,90))
    def test_rgb_padding(self):
        from PIL import Image
        import io
        msg=SimpleNamespace(width=1,height=2,encoding='bgr8',step=4,data=b'\x01\x02\x03\x00\x04\x05\x06\x00')
        im=Image.open(io.BytesIO(pack_png_rgb(msg)))
        self.assertEqual(im.getpixel((0,0)),(3,2,1))
        self.assertEqual(im.getpixel((0,1)),(6,5,4))
    def test_mono(self):
        from PIL import Image
        import io
        msg=SimpleNamespace(width=1,height=1,encoding='mono8',step=1,data=b'\x7b')
        im=Image.open(io.BytesIO(pack_png_rgb(msg)))
        self.assertEqual(im.getpixel((0,0)),(123,123,123))
    def test_encoding_reject(self):
        msg=SimpleNamespace(width=1,height=1,encoding='16UC1',step=2,data=b'\x00\x00')
        with self.assertRaises(ValueError):pack_png_rgb(msg)
    def test_no_late(self):
        events=[(100,(1,0)),(200,(2,0)),(300,(3,0))]
        self.assertEqual(newest_not_after(events,250),(200,(2,0)))
        self.assertIsNone(newest_not_after(events,50))
    def test_motion(self):
        self.assertFalse(is_motion(0.,0.))
        self.assertTrue(is_motion(.08,0.))
    def test_safe_episode_id(self):
        for bad in ('../abc','x','bad space','A/B'):
            with self.assertRaises(ValueError):ensure_id(bad)
        self.assertEqual(ensure_id('B_blue_001'),'B_blue_001')

if __name__=='__main__':unittest.main()
