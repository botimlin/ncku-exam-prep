#!/usr/bin/env python3
"""filter_node.py — 移動平均：訂閱 /sensor/raw，發布 /sensor/filtered

輸入：Int32MultiArray [seq, value]
輸出：Int32MultiArray [seq, avg]
  avg = 最近 4 筆 value 的平均，無條件捨去（整數除法）；剛開始不到 4 筆時，用目前有的幾筆平均。
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray

WINDOW = 4


class Filter(Node):
    def __init__(self):
        super().__init__("filter")
        self.window = []
        self.sub = self.create_subscription(Int32MultiArray, "/sensor/raw", self.on_raw, 10)
        self.pub = self.create_publisher(Int32MultiArray, "/sensor/filterd", 10)
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
