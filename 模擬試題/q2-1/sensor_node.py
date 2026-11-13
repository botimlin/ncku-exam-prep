#!/usr/bin/env python3
"""sensor_node.py — 模擬感測器：發布 /sensor/raw

訊息：std_msgs/msg/Int32MultiArray，data = [seq, value]
  seq   從 0 開始，每筆 +1
  value = (seq * 37) % 101
規格：20 Hz；QoS 用 sensor data（best effort）。
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Int32MultiArray


class Sensor(Node):
    def __init__(self):
        super().__init__("sensor")
        self.pub = self.create_publisher(Int32MultiArray, "/sensor/raw", qos_profile_sensor_data)
        self.seq = 0
        self.timer = self.create_timer(0.5, self.tick)
        self.get_logger().info("sensor 已啟動")

    def tick(self):
        msg = Int32MultiArray()
        msg.data = [self.seq, (self.seq * 37) % 101]
        self.pub.publish(msg)
        self.seq += 1


def main():
    rclpy.init()
    node = Sensor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
