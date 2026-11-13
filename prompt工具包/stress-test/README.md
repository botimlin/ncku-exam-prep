# 提示詞卡壓力測試

用真的小模型測 `../cards/` 的提示詞卡：每個案例 = 一張卡 + 填好的資料 + 自動檢查（格式、有沒有亂引用、有沒有選對答案）。

## 檔案
| 檔案 | 用途 |
|---|---|
| `run.py` | 主程式：解析卡片 → 組提示詞 → 呼叫 OpenAI 相容 API（Ollama / vLLM / llama.cpp）→ 評分 → 報告 |
| `analyze.py` | 把一輪的結果整理成「案例 × 模型」通過矩陣，`--show <id>` 看各模型原始回答 |
| `cases/*.yaml` | 測試案例（每個都有 `golden` 標準答案；`--validate-cases` 確認標準答案會過、亂答會不過） |
| `mock_server.py` | 假的 API 伺服器，不用 GPU 也能測整條流程 |

## 常用指令
```bash
python3 run.py --validate-cases                 # 改案例後一定要跑：0 problems 才算數
python3 run.py --list-cards                     # 卡片解析狀況、字數（每張 ≤ 1200）
python3 run.py --dry-run --only t5 --out /tmp/d # 看組出來的提示詞長什麼樣
python3 run.py --base-url http://127.0.0.1:11434/v1 --model qwen3:8b \
  --temperature 0,0.7 --repeat 2 --concurrency 4 --out out/r2/qwen3_8b
python3 analyze.py out/r2                       # 通過矩陣 + 每個案例最常失敗的檢查
python3 run.py --cards-dir ../cards/_舊版 ...    # 舊版卡片 A/B 對照
```

## GPU 機器（vast.ai，RTX 4090 24GB）
- Ollama v0.40.16 從 GitHub release 安裝在 `/opt/ollama`，模型在 `/workspace/ollama-models`。
- `start_ollama.sh`：`OLLAMA_CONTEXT_LENGTH=8192`、`OLLAMA_NUM_PARALLEL=4`（OpenAI 相容 API 不能傳 num_ctx，context 要在伺服器端設）。
- `run_round.sh <label> [run.py 參數]`：依序跑 10 個模型（qwen2.5:3b/7b/14b、llama3.2:3b、llama3.1:8b、qwen3:8b、gemma3:12b、mistral-nemo:12b、phi4:14b、gpt-oss:20b，都是 Ollama 預設 4-bit 量化）。

## 改卡流程
1. 跑一輪 → `analyze.py` 找通過率低的案例
2. `--show` 看原始回答，分清楚是「卡片寫不好」還是「檢查太嚴」（檢查太嚴就修案例或 run.py，不要遷就分數改卡片）
3. 改卡片 → `--list-cards` 確認 ≤ 1200 字 → `git commit`（prompt工具包 有本地 git，可隨時退回）
4. 再跑一輪比較

## 從測試學到的小模型規則（已套用到卡片）
- 小模型**不會數 byte、不會對齊欄位** → 交給程式做（`frame.py diff`），模型只選原因。
- 表格要**先把列名填好**，模型只填格子；讓它自己生列會亂編。
- 範例裡的數值會被**照抄**（檔名、行號）→ 範例標「只示範格式，內容不要照抄」。
- 改建置檔時，「修改後 = 原本那行 + 在 `)` 前加新名稱，其他字不動」比「照原本寫法」有效。
- 引用常用反引號 `` `…` `` 而不是「」→ 評分時兩種都算。

## 主流程實測（`flow.py`，2026-11-14）
模擬考場操作者照 `考場SOP.md` 做，多輪對話；照模型寫的「原本 → 改成」手動套用到檔案，再用 gcc / pico-sdk 2.2.0 實際編譯、跑測資（`flow_apply.py`）。題目在 `flow_cases.py`（5 個假考題：serial 批次、DMA、ROS 2 topic/QoS、位元欄位、雙核 race）。
```bash
python3 flow.py --model gemma4:12b --ctx 4096,8192 --fix-only --plain \
  --check-card <G04-01 全文檔> --fix-card <G05-01 全文檔> --feedback 3 --build --out out/flow/x
python3 flow.py --report out/flow
```
結果（gemma4:12b，關 thinking）：舊流程（模型自己一直要卡）照著改完能用 0/5 → 修 bug 專用對話（SOP §5.2）4/5（4k、8k 相同）。gemma4:e4b 最好 1/5。serial 批次（兩端大改寫）兩個模型都沒成功。
