# Kaggriculture

GitHub：https://github.com/lhzwb2008/kaggriculture  
本地目录：`/Users/Wezhang/workspace/kaggriculture`  
Kaggle 比赛：https://www.kaggle.com/competitions/kaggriculture

这不是 `arc-prize-2026` 的一部分。ARC 仍在那个仓库；本题单独开仓，避免两套环境和目标搅在一起。

---

## 比赛

Google × Kaggle 的**对战模拟赛**：各管一块农场，30 天 / 720 回合，赛季结束谁银行里金币多谁赢。每天最多交 **5** 个 agent，只有最近 **2** 份参与匹配和最终榜。

截止（UTC）：报名/组队 2026-09-23，交卷 2026-09-30。之后约两周继续打局，再用 Bradley-Terry 定最终名次。

交卷必须是根目录带 `agent(obs)` 的 `main.py`（或 `tar.gz` 里根目录有它）。不是 notebook 写出 `submission.json` 那种 Code Competition。

当前 `main.py` 是可跑的小麦循环（买种 → 种 → 浇 → 收 → 卖），只当真实起点。

## 仓库结构

```
main.py                 提交用 agent（stdlib）
scripts/run_local.py    本地对 random / pass / starter
scripts/submit.py       Kaggle CLI 交卷 / 查提交 / 查榜
```

## 本地

```bash
cd /Users/Wezhang/workspace/kaggriculture
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/run_local.py --opponent random
python3 scripts/run_local.py --opponent starter --games 3
```

## 提交 Kaggle

整条链路走 CLI。

```bash
kaggle auth login
kaggle competitions list --group entered   # 确认已 Join
python3 scripts/submit.py -m "wheat loop v1"
python3 scripts/submit.py --status
python3 scripts/submit.py --leaderboard
```

多文件时打包后再交：

```bash
tar -czf submission.tar.gz main.py
python3 scripts/submit.py -f submission.tar.gz -m "multi-file v1"
```
