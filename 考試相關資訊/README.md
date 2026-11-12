# 考前練習

這裡有三份考前練習，讓你先熟悉考試會接觸到的背景知識。這些練習不是考題，不影響成績，也不需要開發板。

所有練習都在同一個 Docker container 裡操作，ROS 2、`gcc`、`make` 都已經裝好，你只需要自行安裝 Docker。

## 需求

請先自行安裝 Docker：

| 作業系統 | 安裝方式 |
|---|---|
| Linux | [Docker Engine](https://docs.docker.com/engine/install/) |
| Windows | [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)，並在 WSL 中操作 |
| macOS | [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) |

裝好後執行下面的指令確認，應該會看到 `Hello from Docker!`：

```bash
docker run --rm hello-world
```

在 Linux 上如果出現 `permission denied`，請參考 [Linux post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/) 設定權限。

建置 image 時需要連上網路，之後練習就不需要了。

## 專案結構

```text
demo/
├── Dockerfile      建立練習環境的 image
├── .dockerignore   不放進 image 的檔案
├── README.md       本文件
├── section2-1/     使用 ros2 CLI 觀察 node 與 topic
├── section2-2/     位元運算與 PIO 基礎
└── section2-3/     臨界區保護與資料搬運引擎
```

每個子資料夾都有自己的 `README.md`，裡面有該練習的詳細步驟。

| 資料夾 | 內容 | 開始方式 |
|---|---|---|
| `section2-1/` | 用 `ros2` CLI 觀察 node、topic 與訊息傳輸 | `python3 publisher.py`，需要同時開三個終端機 |
| `section2-2/` | C 語言位元運算，以及一支最小的 PIO 範例（閱讀即可） | `cc demo_asm.c -o demo_asm && ./demo_asm` |
| `section2-3/` | pthread 臨界區，以及模擬的資料搬運引擎 | `make run` |

## 使用方式

以下指令都在 `demo/` 資料夾下，於自己電腦的終端機執行。

### 1. 建置 image

只有第一次使用，或練習內容更新時才需要執行：

```bash
docker build -t srecruit-demo .
```

### 2. 啟動 container

```bash
docker run --rm -it --name srecruit-demo srecruit-demo
```

執行後會進入 container 內的 `/demo`，裡面就是三個練習資料夾。例如：

```bash
cd section2-3
make run
```

### 3. 開啟更多終端機

`section2-1` 需要同時開三個終端機。第一個終端機保持執行，再另開視窗執行：

```bash
docker exec -it srecruit-demo bash
```

需要幾個終端機就執行幾次。

### 4. 結束

在每個終端機輸入 `exit`。第一個終端機離開時，container 會停止並刪除，其他終端機也會一起中斷。

## 注意事項

**container 刪除後，裡面的修改會消失。** 想保留修改的話，請改用下面的指令啟動，把自己電腦上的 `demo/` 掛載進去：

```bash
docker run --rm -it --name srecruit-demo -v "$PWD:/demo" srecruit-demo
```

**如果出現 `The container name "/srecruit-demo" is already in use`，** 表示已經有一個練習用的 container。需要再開終端機時請用 `docker exec`；要重新開始則先執行：

```bash
docker rm -f srecruit-demo
```
