"""每秒發佈一個 1～100 的隨機整數。"""
import random

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32


class Publisher(Node):
    def __init__(self):
        super().__init__('publisher')
        self.pub = self.create_publisher(Int32, '/number', 10)
        self.timer = self.create_timer(1.0, self.tick)

    def tick(self):
        msg = Int32()
        msg.data = random.randint(1, 100)
        self.pub.publish(msg)


def main():
    rclpy.init()
    node = Publisher()
    print('publisher 已啟動，按 Ctrl-C 停止', flush=True)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
