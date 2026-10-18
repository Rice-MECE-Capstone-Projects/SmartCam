import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from auto_collect import parse_topics, validate_name

class CollectorPureTests(unittest.TestCase):
    def test_topic_types(self):
        d = parse_topics('  /clock [rosgraph_msgs/msg/Clock]\n/cmd_vel [geometry_msgs/msg/Twist]\nnot-topic')
        self.assertEqual(d['/cmd_vel'], 'geometry_msgs/msg/Twist')
        self.assertNotIn('not-topic', d)

    def test_valid_ids(self):
        self.assertEqual(validate_name('B_blue_20261016_001'), 'B_blue_20261016_001')

    def test_unsafe_names(self):
        for text in ('hi', '../oops', 'two words', 'a'*81):
            with self.assertRaises(ValueError):validate_name(text)

if __name__=='__main__':unittest.main()
