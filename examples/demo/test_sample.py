"""样例测试用于验证测试命令的原始结果采集。"""
import unittest
from sample import add


class SampleTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
