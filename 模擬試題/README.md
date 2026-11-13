# 模擬試題：116 學年度成大資工特選上機考（仿真版）

> 這是**猜題做的模擬考**，不是真的考題。題型照 `../預製程式碼/預測考題.md` 的推測出：
> ROS 2 + 一份寫到一半、埋了 bug 的專案 + 自動評分 + 越快越好。
> 不需要開發板：Pico 的部分用電腦上的模擬器代替（函式名稱照 pico-sdk 2.x）。
> **解答在 `../模擬試題-解答/`，做完之前不要打開。**

## 建議時間：3.5 小時（真的考試約 7 小時）

| 題目 | 配分 | 建議時間 | 內容 |
|---|---|---|---|
| 第一大題 `q1/` | 40 | 90 分鐘 | 電腦 ↔「Pico」序列埠協定：修 bug、改成批次傳輸、兩片板子平行 |
| 2-1 `q2-1/` | 20 | 30 分鐘 | ROS 2：三個 node 串起來，資料沒在傳，用 `ros2` CLI 找出原因 |
| 2-2 `q2-2/` | 20 | 60 分鐘 | 依規格打包 / 拆解位元欄位、PIO 位元流解析、RISC-V 立即值 |
| 2-3 `q2-3/` | 20 | 30 分鐘 | 雙核心 + spinlock + DMA：一跑就 panic、結果不對、而且很慢 |

每題的規格在該資料夾的 `README.md`。**先讀完全部題目再開始**，先拿容易的分。

## 規則（跟真的考試一樣）

1. 只能改題目說「可以改」的檔案。標了「不要改」的檔案 judge 會檢查，被改過那題 0 分。
2. 分數 = 正確性 + 效能。**先交一個能動的版本**，再回頭優化。
3. 可以查官方文件（pico-sdk、RP2350 datasheet、ROS 2 docs、RISC-V 手冊），可以用考場的小模型。
   練習時建議只用 `../prompt工具包/cards/` 的卡片問模型，順便練卡片。
4. 不要看 `judge/` 資料夾和 `judge.py` 的內容（真的考試看不到 judge）。看 judge 的**輸出**沒關係。

## 環境

第一大題、2-2、2-3 只需要 `gcc`、`make`、`python3`，任何 Linux / WSL / macOS 都可以。
**2-1 需要 ROS 2 Jazzy**：用考前練習的 `srecruit-demo` image（見 `../考試相關資訊/README.md`），把這個資料夾掛進去：

```bash
cd 模擬試題
docker run --rm -it --name srecruit-demo -v "$PWD:/demo" srecruit-demo
```

進去之後就在 `/demo`（= 這個資料夾），所有題目都可以在容器裡做。要開更多終端機：

```bash
docker exec -it srecruit-demo bash
```

## 評分

```bash
python3 judge.py            # 全部
python3 judge.py q1         # 只評一題：q1、q2-1、q2-2、q2-3
python3 judge.py q2-1 -v    # 多印一些細節
```

`.gitlab-ci.yml` 是「如果放到 GitLab 上」的 CI 設定，讀題練習用：真的考試開考後的第一件事，就是讀懂 CI 怎麼評分、
commit message 要寫什麼。這份的規則是 commit message 要含 `[Q1]`、`[Q2-1]`、`[Q2-2]`、`[Q2-3]`。
練習時用 git 走一次流程：

```bash
git add -A && git commit -m "[Q2-2] parse_header 修好"
```

## 資料夾

```text
模擬試題/
├── README.md            本文件（題目總說明）
├── .gitlab-ci.yml       讀題練習用的 CI 設定
├── judge.py             本地評分（不要看內容）
├── judge/               judge 用的檔案（不要看、不要改）
├── tools/
│   ├── pio_sim.py       PIO 模擬器（2-2 用）：python3 tools/pio_sim.py 檔案.pio 0x12345678 --trace
│   └── fake_link.py     把模擬 Pico 接到虛擬序列埠（第一大題用）
├── q1/                  第一大題
├── q2-1/                2-1
├── q2-2/                2-2
└── q2-3/                2-3
```

## 做完之後

1. 跑 `python3 judge.py`，記下分數和每題花的時間。
2. 打開 `../模擬試題-解答/README.md` 對答案：每個 bug 是什麼、怎麼找到的、考場上用哪張卡片問模型最快。
3. 想重做：`git checkout -- 模擬試題/`（或 `git stash`）把題目還原。
