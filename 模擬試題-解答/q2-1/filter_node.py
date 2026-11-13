#!/usr/bin/env python3
"""filter_node.py — 移動平均：訂閱 /sensor/raw，發布 /sensor/filtered

輸入：Int32MultiArray [seq, value]
輸出：Int32MultiArray [seq, avg]
  avg = 最近 4 筆 value 的平均，無條件捨去（整數除法）；剛開始不到 4 筆時，用目前有的幾筆平均。
"""
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Int32MultiArray

WINDOW = 4


class Filter(Node):
    def __init__(self):
        super().__init__("filter")
        self.window = deque(maxlen=WINDOW)          # 解答 bug 3：原本 list 一直變長 → 變成「全部的平均」
        self.sub = self.create_subscription(Int32MultiArray, "/sensor/raw", self.on_raw,
                                            qos_profile_sensor_data)   # 解答 bug 2：publisher 是 best effort，訂閱端預設 reliable → QoS 不相容，一筆都收不到
        self.pub = self.create_publisher(Int32MultiArray, "/sensor/filtered", 10)   # 解答 bug 1：原本拼成 /sensor/filterd
        self.get_logger().info("filter 已啟動")

    def on_raw(self, msg):
        seq, value = msg.data[0], msg.data[1]
        self.window.append(value)
        avg = sum(self.window) // len(self.window)
        out = Int32MultiArray()
        out.data = [seq, avg]
        self.pub.publish(out)


def main():
    rclpy.init()
    node = Filter()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
