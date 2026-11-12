# 考前練習：使用 `ros2` CLI 觀察 ROS 2 系統

這份練習的目的，是讓你在考試前熟悉 ROS 2 的基本操作，以及如何使用 `ros2` CLI（Command-Line Interface） 觀察系統中的 node、topic 與訊息傳輸情形。

完成本練習後，你應該能在不查看程式內部實作的情況下，使用 `ros2` 指令：

1. 查看目前有哪些 node 正在執行。
2. 查看 node 發佈（publish）與訂閱（subscribe）了哪些 topic。
3. 查詢 topic 使用的訊息型別，以及訊息中包含哪些欄位。
4. 觀察 topic 上實際傳輸的資料與發佈頻率。
5. 使用指令自行發佈測試訊息。
6. 在資料未正常傳輸時，利用上述資訊進行基本的問題排查。

本練習可直接在自己的電腦上完成，不需要使用開發板；練習內容也不會直接涉及考題中的演算法。

---

## 0. ROS 2 基本概念

ROS 2（Robot Operating System 2）是一套用於開發機器人軟體的開源框架。

在 ROS 2 系統中，執行特定功能並參與 ROS 通訊的單位稱為 **node**。一個系統通常由多個 node 組成，各 node 之間透過 ROS 2 提供的通訊機制交換資料。

本練習中的兩支 Python 程式都各自建立一個 node。

ROS 2 常見的通訊方式包括：

| 方式 | 用途 | 例子 |
|---|---|---|
| **Topic** | 持續、非同步地傳送資料 | 感測器持續發布量測值 |
| Service | 一次 request / response | 查詢或修改某項設定 |
| Action | 執行需要一段時間完成的工作，並可回報進度或取消 | 要求機器人移動到指定位置 |

本練習只會使用 **Topic**。

Topic 可以理解成 node 之間傳遞資料的通道。每個 topic 都有自己的名稱與固定的 message type：

```text
publisher node ──> /topic（message type）──> subscriber node
```

發布資料的一方稱為 **publisher**，接收資料的一方稱為 **subscriber**。

本練習會使用下列指令：

| 指令 | 功能 |
|---|---|
| `ros2 node list` | 列出目前正在執行的 node |
| `ros2 node info <node>` | 查看某個 node 發佈與訂閱的 topic |
| `ros2 topic list` | 列出目前存在的 topic |
| `ros2 topic info <topic>` | 查看 topic 的 message type ，以及 publisher / subscriber 數量 |
| `ros2 interface show <type>` | 查看某種 message type 包含哪些欄位 |
| `ros2 topic echo <topic>` | 顯示 topic 上收到的資料 |
| `ros2 topic hz <topic>` | 顯示 topic 的發布頻率 |
| `ros2 topic pub <topic> <type> <data>` | 由 CLI 自行發布特定 message |

若想進一步了解 ROS 2，可參考官方文件：

<https://docs.ros.org/en/jazzy/>

---

## 1. 準備環境

本練習使用考前練習共用的 Docker image，裡面已經裝好 ROS 2 Jazzy，因此不需要另外安裝 ROS 2。

請先依照 [`demo/README.md`](../README.md) 安裝 Docker、建置 image 並啟動 container，接著在 container 內進入本練習的資料夾：

```bash
cd section2-1
```

ROS 2 系統中通常會同時執行多個 node，而 `ros2 topic echo`、Python node 等程式執行後也會持續佔用目前的 terminal，因此本練習會同時使用數個終端機視窗。

若要開啟另一個 shell，請另外開一個終端機視窗，執行：

```bash
docker exec -it srecruit-demo bash
cd section2-1
```

`docker exec` 會進入同一個 container，開啟另一個 shell。

因此，在不同終端機中啟動的 ROS 2 node 都位於同一個 ROS 2 系統中，可以互相發現並通訊。

以下使用 **終端機 A、B、C** 來區分不同視窗：

```text
終端機 A             終端機 B            終端機 C

publisher.py        processor.py        ros2 topic echo ...
     │                   │                    │
     └────────────── 同一個 ROS 2 系統 ────────┘
```

---

## 2. 觀察尚未啟動 node 的系統

在還沒有執行任何練習程式之前，先在終端機 A 執行：

```bash
ros2 node list
```

此時應該不會看到本練習的 node。

再執行：

```bash
ros2 topic list
```

依環境狀況，你可能會看到：

```text
/parameter_events
/rosout
```

也可能沒有任何輸出。

`/parameter_events`、`/rosout` 等 topic 是 ROS 2 系統本身可能使用的 topic，與本練習無關，可以先忽略。

這時的重點是先觀察：**目前還沒有任何本練習使用的 node 或 topic。**

---

## 3. 啟動 publisher，使用 CLI 觀察它

在終端機 A 執行：

```bash
python3 publisher.py
```

畫面會顯示：

```text
publisher 已啟動，按 Ctrl-C 停止
```

接下來使用 `ros2` CLI 觀察這個 node。

### 3.1 查看目前的 node

到終端機 B 執行：

```bash
ros2 node list
```

應該可以看到：

```text
/publisher
```

表示目前有一個名為 `/publisher` 的 node 正在執行。

### 3.2 查看目前的 topic

執行：

```bash
ros2 topic list
```

你會看到一個新的 topic - `/number`：

```text
/number
/parameter_events
/rosout
```

### 3.3 查看 `/publisher` 的通訊介面

執行：

```bash
ros2 node info /publisher
```

其中會看到類似：

```text
/publisher

  Subscribers:

  Publishers:
    /number: std_msgs/msg/Int32
    /parameter_events: rcl_interfaces/msg/ParameterEvent
    /rosout: rcl_interfaces/msg/Log
```

可以看出 `/publisher` 正在發布 `/number`。

`/number` 後面的：

```text
std_msgs/msg/Int32
```

是這個 topic 使用的 message type 。

### 3.4 從 topic 的角度查看資訊

執行：

```bash
ros2 topic info /number
```

應該會看到：

```text
Type: std_msgs/msg/Int32
Publisher count: 1
Subscription count: 0
```

目前有 1 個 publisher 發布 `/number`，但還沒有任何 subscriber 訂閱它。

### 3.5 查看訊息型別的內容

執行：

```bash
ros2 interface show std_msgs/msg/Int32
```

你會看到類似：

```text
int32 data
```

代表 `std_msgs/msg/Int32` 這個訊息型別包含一個名為 `data` 的 `int32` 欄位。

### 3.6 查看實際資料

執行：

```bash
ros2 topic echo /number
```

你會持續看到 `/number` 上收到的訊息，例如：

```text
data: 82
---
data: 58
---
```

按 `Ctrl-C` 可以停止 `echo`。

接著查看發布頻率：

```bash
ros2 topic hz /number
```

應該會看到接近：

```text
average rate: 1.000
```

表示 publisher 約每秒發布一筆資料。

同樣按 `Ctrl-C` 結束。

### 3.7 停止 publisher

回到終端機 A，按 `Ctrl-C` 停止 `publisher.py`。

接著在終端機 B 再執行：

```bash
ros2 node list
```

此時 `/publisher` 應該已經消失。

也就是說，建立 node 的程式停止後，該 node 也會從 ROS 2 系統中消失。

---

## 4. 加入 processor

接下來加入第二個 node：`processor.py`。

這支程式已經寫好，不需要修改。它會作為 `/number` 的 **subscriber**，接收 publisher 發出的整數；收到資料後，將數值乘以 2，再把結果發佈到 `/double`。

因此 `processor.py` 雖然是 `/number` 的 subscriber，同時也會作為 `/double` 的 publisher：

```text
/publisher ──> /number ──> /processor ──> /double
```

先在終端機 A 重新啟動：

```bash
python3 publisher.py
```

接著在終端機 B 執行：

```bash
python3 processor.py
```

你會看到類似這樣的畫面：

```text
received: 51
received: 34
...
```

此時到終端機 C 觀察系統。

### 4.1 查看 node 與 topic

先執行：

```bash
ros2 node list
```

應該會看到：

```text
/processor
/publisher
```

再執行：

```bash
ros2 topic list
```

應該會看到：

```text
/double
/number
/parameter_events
/rosout
```

和第 3 節相比多了 `/double`，表示加入 `processor.py` 後，系統中多了一個 node，也多了一個 topic。

### 4.2 查看 processor 的連線

執行：

```bash
ros2 node info /processor
```

可以看到類似：

```text
/processor

  Subscribers:
    /number: std_msgs/msg/Int32

  Publishers:
    /double: std_msgs/msg/Int32
    /parameter_events: rcl_interfaces/msg/ParameterEvent
    /rosout: rcl_interfaces/msg/Log
```

因此可以推得：

- `/processor` 訂閱 `/number`
- `/processor` 發布 `/double`

目前的資料流為：

```text
/publisher ──> /number ──> /processor ──> /double
```

### 4.3 再查看 `/number`

執行：

```bash
ros2 topic info /number
```

這次會看到：

```text
Type: std_msgs/msg/Int32
Publisher count: 1
Subscription count: 1
```

與前一節相比，`Subscription count` 從 0 變成了 1。

這個 subscriber 就是剛才啟動的 `/processor`。

### 4.4 查看 processor 的輸出

在終端機 C 執行：

```bash
ros2 topic echo /double
```

應該可以持續看到 `/double` 上的資料。

`processor.py` 會將從 `/number` 收到的數值乘以 2，再發布到 `/double`。

這個 `echo` 請先保持執行，下一節還會使用。

> **選讀**
>
> 若想進一步了解程式碼，可以打開 `processor.py`，對照剛才使用 CLI 看到的資訊：
>
> - `INPUT_TOPIC = '/number'` 對應 `/processor` 的 subscriber。
> - `Int32` 對應 `std_msgs/msg/Int32`。
> - `received.data` 對應 `ros2 interface show` 中看到的 `int32 data`。

---

## 5. 使用 CLI 取代 publisher

接下來不再使用 `publisher.py`，改成直接由 CLI 發布測試訊息。

回到終端機 A，按 `Ctrl-C` 停止 `publisher.py`。

此時：

- 終端機 B 的 `processor.py` 保持執行。
- 終端機 C 的 `ros2 topic echo /double` 也保持執行。

先在終端機 A 查看 `/number`：

```bash
ros2 topic info /number
```

你應該會看到：

```text
Type: std_msgs/msg/Int32
Publisher count: 0
Subscription count: 1
```

`/number` 仍然存在，而且 `/processor` 仍然訂閱它，但目前已經沒有 publisher。

這也表示：

**topic 存在，不代表目前一定有資料正在傳送。**

接著由 CLI 發布一筆訊息：

```bash
ros2 topic pub --once /number std_msgs/msg/Int32 "{data: 21}"
```

終端機 A 會顯示類似：

```text
publisher: beginning loop
publishing #1: std_msgs.msg.Int32(data=21)
```

而終端機 C 應該收到：

```text
data: 42
---
```

可以再自行測試其他數值，例如：

```bash
ros2 topic pub --once /number std_msgs/msg/Int32 "{data: -5}"
```

預期輸出：

```text
data: -10
---
```

也可以試：

```text
0
100
```

確認輸出分別為：

```text
0
200
```

這裡可以看到兩個常用 CLI 指令實際扮演的角色：

| 指令 | 在 ROS 2 系統中的角色 |
|---|---|
| `ros2 topic echo` | 暫時建立 subscriber，將收到的資料顯示在終端機 |
| `ros2 topic pub` | 暫時建立 publisher，將指定的資料送到 topic |

因此在除錯時，不一定需要另外撰寫測試程式，就可以直接使用 CLI 測試某個 node 的輸入或輸出。

---

## 6. 資料沒有正常傳輸時

如果程式沒有出現錯誤，但預期中的資料沒有出現，可以善用 ROS2 CLI 來做除錯。

常用的檢查方式如下：

| 想確認的事 | 指令 |
|---|---|
| 預期的 node 是否正在執行？ | `ros2 node list` |
| 預期的 topic 是否存在？ | `ros2 topic list` |
| node 實際訂閱與發布了哪些 topic？ | `ros2 node info <node>` |
| topic 的型別，以及 publisher / subscriber 數量是否正確？ | `ros2 topic info <topic>` |
| topic 上是否真的有資料？ | `ros2 topic echo <topic>` |
| topic 的發布頻率是否正常？ | `ros2 topic hz <topic>` |
| 想單獨測試某個 node 的輸入 | 使用 `ros2 topic pub` 發送已知資料，再用 `echo` 觀察輸出 |

例如，topic 名稱只要差一個字元，ROS 2 就會把它視為另一個不同的 topic。

這種情況下程式不一定會出現錯誤，但：

- `ros2 topic list` 可能會出現非預期的 topic 名稱。
- `ros2 topic info` 可能顯示某一側的 publisher 或 subscriber 數量為 0。

因此遇到資料沒有正常傳輸時，可以先從：

```text
node 是否存在
        ↓
topic 是否存在
        ↓
兩端是否連到相同的 topic
        ↓
publisher / subscriber 數量是否合理
        ↓
實際是否有資料傳輸
```

依序檢查。

---

## 7. 結束練習

完成後，請依序結束目前仍在執行的程式與 container。

1. 在仍執行 `processor.py`、`ros2 topic echo` 等程式的終端機按 `Ctrl-C`。
2. 由 `docker exec` 進入的終端機可輸入：

```bash
exit
```

3. 最後回到最一開始由 `docker run` 進入的 shell，輸入：

```bash
exit
```

container 會隨之停止並刪除。

如果先離開第一個 shell，其他透過 `docker exec` 進入的終端機可能會跟著中斷，這是正常現象。

本練習不需要修改任何檔案。之後若想重新操作，再次執行 [`demo/README.md`](../README.md) 中的 `docker run` 指令即可重新開始。