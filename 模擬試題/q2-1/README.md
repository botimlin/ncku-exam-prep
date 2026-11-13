# 2-1：ROS 2 資料管線除錯（20 分）

> 需要 ROS 2 Jazzy：在 `srecruit-demo` 容器裡做（見 `../README.md` 的「環境」）。

## 1. 系統

```text
sensor_node ──> /sensor/raw ──> filter_node ──> /sensor/filtered ──> monitor_node
  20 Hz           [seq, value]     移動平均         [seq, avg]           評分用
```

| node | 檔案 | 能不能改 | 規格 |
|---|---|---|---|
| `/sensor` | `sensor_node.py` | ✅ | 發布 `/sensor/raw`，`std_msgs/msg/Int32MultiArray`，`data = [seq, value]`；seq 從 0 開始每筆 +1，`value = (seq * 37) % 101`；**20 Hz**；QoS 用 `qos_profile_sensor_data`（best effort）—— QoS 這點是規格，不能改 |
| `/filter` | `filter_node.py` | ✅ | 訂閱 `/sensor/raw`，發布 `/sensor/filtered`，`data = [seq, avg]`；`avg` = **最近 4 筆** value 的平均，整數除法無條件捨去；剛啟動不到 4 筆時，用已經收到的幾筆平均 |
| `/monitor` | `monitor_node.py` | ❌ | 訂閱 `/sensor/filtered`（reliable），收滿 40 筆寫進 `monitor.log` 後結束 |

現在的狀況：三個都跑起來、沒有任何 exception，但 monitor **一筆都收不到**。

## 2. 任務

1. 讓 monitor 收得到資料，而且 avg 和頻率都符合規格。
2. 回答 `ANSWERS.md` 的 3 題（寫你實際用了什麼指令、看到什麼）。

**規定：先用 `ros2` CLI 找問題，不要一開始就讀程式碼。** 這題練的就是考前練習 section2-1 的那套排查流程：

```text
node 在不在 → topic 在不在 → 兩邊是不是同一個 topic → publisher / subscriber 數量 → QoS → 實際有沒有資料 → 頻率
```

## 3. 自己跑（三個終端機，都先 `cd /demo/q2-1`）

```bash
python3 filter_node.py
```

```bash
python3 monitor_node.py --timeout 60
```

```bash
python3 sensor_node.py
```

再開一個終端機觀察：

```bash
ros2 node list
```

```bash
ros2 topic list
```

```bash
ros2 topic info -v /sensor/raw
```

```bash
ros2 topic hz /sensor/raw
```

> `ros2 topic echo` 預設的 QoS 會跟著 publisher 調整；要模擬某一種 QoS 可以加 `--qos-reliability reliable` 或 `best_effort`。

## 4. 評分（`python3 judge.py q2-1`）

judge 會先啟動 filter 和 monitor，等 3 秒，再啟動 sensor。

| 項目 | 分數 |
|---|---|
| monitor 在 30 秒內收到 40 筆 | 8 |
| avg 正確（seq ≥ 3 的筆數，至少 90% 正確） | 6 |
| 頻率 15～25 Hz | 3 |
| `ANSWERS.md` 3 題（自評，每題 1 分） | 3 |
