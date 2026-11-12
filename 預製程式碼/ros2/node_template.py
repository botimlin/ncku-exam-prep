#!/usr/bin/env python3
"""node_template.py — 最小 rclpy 節點: 訂閱 -> 處理 -> 發布 (+ 參數 + QoS + 計時器)

對應官方 demo: /number (Int32) --[乘 2]--> /double (Int32)
執行:
  source /opt/ros/jazzy/setup.bash
  python3 node_template.py                                  # 用預設參數
  python3 node_template.py --ros-args -p in_topic:=/number -p out_topic:=/double -p factor:=3
測試 (另一個終端機):
  ros2 topic echo /double
  ros2 topic pub --once /number std_msgs/msg/Int32 "{data: 21}"     # 應該看到 data: 42
「修 bug 題」先檢查: topic 名字拼錯? 型別對不對? QoS 一不一致? callback 有沒有真的 publish?
"""
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32  # TODO(改這裡) 換訊息型別，例如 Int32MultiArray / String / UInt8MultiArray

# QoS: 發布端和訂閱端要「相容」，不然連得上卻收不到 (ros2 topic info -v 可以看)
#   RELIABLE 訂閱端 + BEST_EFFORT 發布端 → 收不到!  (感測器 topic 常是 BEST_EFFORT)
#   直接寫數字 10 = 預設 (RELIABLE, VOLATILE, depth 10)，大部分情況用 10 就好
QOS = QoSProfile(
    depth=10,
    history=HistoryPolicy.KEEP_LAST,
    reliability=ReliabilityPolicy.RELIABLE,   # TODO(改這裡) 收不到感測器資料時改 BEST_EFFORT
    durability=DurabilityPolicy.VOLATILE,     # TRANSIENT_LOCAL = 晚加入的訂閱者也拿得到最後一筆
)


class Processor(Node):
    def __init__(self):
        super().__init__("processor")  # TODO(改這裡) 節點名字 (題目可能指定，ros2 node list 會看到)

        # ---- 參數: 用 --ros-args -p 名字:=值 覆蓋，不用改程式 ----
        self.declare_parameter("in_topic", "/number")    # TODO(改這裡) 輸入 topic
        self.declare_parameter("out_topic", "/double")   # TODO(改這裡) 輸出 topic
        self.declare_parameter("factor", 2)
        self.declare_parameter("tick_period", 0.0)       # >0 才開計時器 (秒)
        in_topic = self.get_parameter("in_topic").value
        out_topic = self.get_parameter("out_topic").value
        self.factor = self.get_parameter("factor").value

        # ---- 發布者 / 訂閱者 ----
        self.pub = self.create_publisher(Int32, out_topic, QOS)
        self.sub = self.create_subscription(Int32, in_topic, self.on_msg, QOS)
        self.count = 0
        self.get_logger().info(f"訂閱 {in_topic} -> 發布 {out_topic} (factor={self.factor})")

        # ---- 計時器: 每 tick_period 秒發一個遞增的數字到 /tick (官方 demo 的 publisher 寫法) ----
        period = float(self.get_parameter("tick_period").value)
        if period > 0:
            self.tick_pub = self.create_publisher(Int32, "/tick", QOS)
            self.tick = 0
            self.timer = self.create_timer(period, self.on_timer)

    def on_msg(self, msg):
        """收到一筆 → 處理 → 發布。題目的運算寫在這裡"""
        out = Int32()
        out.data = msg.data * self.factor     # TODO(改這裡) 你的處理邏輯
        self.pub.publish(out)                 # 常見 bug: 忘了 publish、或 publish 到錯的 publisher
        self.count += 1
        self.get_logger().info(f"#{self.count}: {msg.data} -> {out.data}")

    def on_timer(self):
        msg = Int32()
        msg.data = self.tick
        self.tick_pub.publish(msg)
        self.tick += 1


def main():
    rclpy.init()
    node = Processor()
    try:
        rclpy.spin(node)          # 一直等 callback；沒有 spin 的話 callback 永遠不會被呼叫!
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
