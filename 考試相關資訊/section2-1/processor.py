"""接收 publisher 的整數，乘以 2 後發佈到 /double。"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32


INPUT_TOPIC = '/number'
OUTPUT_TOPIC = '/double'


class Processor(Node):
    def __init__(self):
        super().__init__('processor')
        self.sub = self.create_subscription(Int32, INPUT_TOPIC, self.on_msg, 10)
        self.pub = self.create_publisher(Int32, OUTPUT_TOPIC, 10)

    def on_msg(self, received):
        print(f'received: {received.data}', flush=True)

        out = Int32()
        out.data = received.data * 2
        self.pub.publish(out)


def main():
    rclpy.init()
    node = Processor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
