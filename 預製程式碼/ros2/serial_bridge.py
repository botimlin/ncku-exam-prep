#!/usr/bin/env python3
"""serial_bridge.py — ROS 2 <-> Pico 序列埠橋接節點

  /numbers (std_msgs/Int32MultiArray) --SUM_U32--> Pico --> /sum (std_msgs/UInt32)
  /bytes   (std_msgs/UInt8MultiArray) --CRC32----> Pico --> /crc (std_msgs/UInt32)

參數 batch_size: 一包塞幾個數字
  1  = 一次一個 (每個數字一來一回，最慢，但最好除錯)
  0  = 批次: 一包塞滿 CHUNK_BYTES (見 frame.py)，數字多時快非常多
為什麼「二進位 + 批次」比「一行一行文字 (print("123\\n"))」快?
  1. 每次來回都有固定開銷 (USB 約 1ms 輪詢 + Python/系統呼叫)，包數越少越好
  2. 文字 "4294967295\\n" 要 11 bytes，二進位 u32 只要 4 bytes；Pico 也不用 atoi 慢慢解析
執行 (配假 Pico):
  python3 fake_pico.py                         # 會印出 /dev/pts/N
  python3 serial_bridge.py --ros-args -p port:=/dev/pts/N -p batch_size:=0
  ros2 topic echo /sum
  ros2 topic pub --once /numbers std_msgs/msg/Int32MultiArray "{data: [1, 2, 3]}"   # -> 6
"""
import array
import time

import rclpy
import serial
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray, UInt8MultiArray, UInt32

from frame import CHUNK_BYTES, CMD_CRC32, CMD_SUM_U32, MAX_LEN, transact, unpack_u32


class SerialBridge(Node):
    def __init__(self):
        super().__init__("serial_bridge")
        self.declare_parameter("port", "/dev/ttyACM0")   # TODO(改這裡) ls /dev/ttyACM* 看是哪個
        self.declare_parameter("batch_size", 0)          # TODO(改這裡) 1=一次一個, 0=塞滿一包
        self.declare_parameter("timeout", 1.0)           # 等回覆幾秒算逾時
        self.declare_parameter("retries", 3)             # 逾時重送幾次
        g = lambda n: self.get_parameter(n).value        # noqa: E731  縮短寫法
        self.batch, self.timeout, self.retries = g("batch_size"), g("timeout"), g("retries")
        if self.batch * 4 > MAX_LEN:       # 一包超過 Pico 的 FRAME_MAX_PAYLOAD，Pico 會直接丟掉、不回覆
            self.get_logger().warning(f"batch_size={self.batch} 太大，改成 {MAX_LEN // 4}（Pico 一包最多 {MAX_LEN} bytes）")
            self.batch = MAX_LEN // 4

        # timeout 要小 (0.05)，transact() 會自己算總逾時；USB CDC 的 baudrate 沒差
        self.ser = serial.Serial(g("port"), timeout=0.05)
        self.seq = 0

        self.pub_sum = self.create_publisher(UInt32, "/sum", 10)   # TODO(改這裡) 輸出 topic/型別
        self.pub_crc = self.create_publisher(UInt32, "/crc", 10)
        self.create_subscription(Int32MultiArray, "/numbers", self.on_numbers, 10)
        self.create_subscription(UInt8MultiArray, "/bytes", self.on_bytes, 10)
        self.get_logger().info(f"開啟 {g('port')}，batch_size={self.batch}")

    def send(self, cmd, payload):
        """送一包給 Pico 並等回覆 (含逾時重試)。seq 每次 +1，用來對應是哪一包的回覆"""
        self.seq = (self.seq + 1) & 0xFF
        return transact(self.ser, cmd, payload, self.seq, self.timeout, self.retries)

    def on_numbers(self, msg):
        t0 = time.perf_counter()
        # Int32MultiArray.data 是 array('i')；.tobytes() 直接得到小端 int32 = u32 的位元，超快
        data = array.array("i", msg.data).tobytes()
        step = 4 * self.batch if self.batch > 0 else CHUNK_BYTES // 4 * 4
        total = 0
        try:
            for i in range(0, len(data), step):          # 切成好幾包，每包一來一回
                reply = self.send(CMD_SUM_U32, data[i:i + step])
                total = (total + unpack_u32(reply)[0]) & 0xFFFFFFFF   # TODO(改這裡) 合併方式
        except TimeoutError as e:
            self.get_logger().error(str(e))
            return
        self.pub_sum.publish(UInt32(data=total))
        ms = (time.perf_counter() - t0) * 1000
        self.get_logger().info(f"{len(msg.data)} 個數字, {-(-len(data) // step)} 包, 總和={total}, {ms:.1f} ms")

    def on_bytes(self, msg):
        # 注意: CRC32 不能像 SUM 一樣切塊再加起來 —— Pico 每一包都從頭算 CRC。
        # 所以資料一定要塞得進「一包」，太大就先擋下來，免得 Pico 丟包、這邊白等 3 次 timeout。
        # TODO(改這裡) 真的要算大資料: (a) 把 Pico 的 FRAME_MAX_PAYLOAD 加大
        #   或 (b) 協定多加一個「起始 crc 值」欄位，讓 Pico 接著上一包算 (zlib.crc32(data, prev) 同概念)
        if len(msg.data) > CHUNK_BYTES:
            self.get_logger().error(f"{len(msg.data)} bytes 超過一包上限 {CHUNK_BYTES}，CRC 不能分包算")
            return
        try:
            reply = self.send(CMD_CRC32, bytes(msg.data))   # UInt8MultiArray.data -> bytes
        except TimeoutError as e:
            self.get_logger().error(str(e))
            return
        crc = unpack_u32(reply)[0]
        self.pub_crc.publish(UInt32(data=crc))
        self.get_logger().info(f"{len(msg.data)} bytes, crc32={crc:#010x}")


def main():
    rclpy.init()
    node = SerialBridge()
    try:
        rclpy.spin(node)   # 單執行緒: callback 一個一個跑，序列埠不會被兩個 callback 同時用
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.ser.close()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
