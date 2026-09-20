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

当前提交 agent 是公开 notebook [Shop Router 0908](https://www.kaggle.com/code/yhay81/shop-router-0908)：4 条 mosaic tape，第 6 天按羊毛店分叉，第 27 天按鸡蛋库存选卖法。该 kernel 公开成绩 **rating 2611.5**。旧的 C95 单 tape 在 `agents/c95/main.py`。

## 仓库结构

```
main.py observation.py model.json actions.json   当前提交（Shop Router 0908）
agents/c95/main.py           旧 C95 单 tape（harvest 仍可换这条）
scripts/harvest_tapes.py     从公开对局抽出赢家 tape
scripts/assemble_tape.py     把选中的 tape 写进 C95 main.py
scripts/tournament.py        本地 tape 对 tape
scripts/run_local.py         本地对 random / pass / starter
scripts/submit.py            打包 tar.gz / 交卷 / 查榜
tapes/                       抽出的 tape（默认不入库）
```

## 方案 1：收最新公开对局，换更强 tape

公开 replay 里已经有每一步的 action。动作在 `steps[t + 1]`，回放用 `day * 24 + hour`。杂草修复、卖单重排、开局囤饲料这些包装不用动。

```bash
cd /Users/wenbozhang/workspace/kaggriculture
# 凭据放 kaggle.json 或 .env，见下方「提交 Kaggle」；不要 kaggle auth login

# 1. 把当前 C95 存成对照
python3 scripts/harvest_tapes.py --export-current

# 2. 直接侦察公开榜前 3 名的对局（推荐）
python3 scripts/harvest_tapes.py --scout-top 3 --top 8
# 或从排行榜对局页抄 episode id / 每日 dump 的 manifest.csv
python3 scripts/harvest_tapes.py --episode EPISODE_ID
# 或
python3 scripts/harvest_tapes.py --from-dir replays
# 或
python3 scripts/harvest_tapes.py --from-manifest data/episodes/manifest.csv --top 20

# 3. 看哪条 tape 和当前不是同一家族、终局金币更高
python3 scripts/harvest_tapes.py --rank

# 4. 有本地环境时再对打确认
python3 scripts/tournament.py tapes/current_c95.json tapes/epXXXX_seatY.json --games 4

# 5. 写进 main.py（只换 _TRACE，包装层保留）
python3 scripts/assemble_tape.py tapes/epXXXX_seatY.json

# 6. 提交
python3 scripts/submit.py -m "harvest epXXXX seatY"
```

每日公开对局：`kaggle/kaggriculture-episodes-YYYY-MM-DD`（整包约 20GB，优先只下 `manifest.csv` 或单个 `kaggle competitions replay <id>`）。旧 tape 被抄多了会掉分，这条流水线要反复跑。

## 本地

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest tests/test_tape_lib.py
python3 scripts/run_local.py --opponent starter --games 3
```

## 提交 Kaggle

交卷走 CLI，**不要**每次 `kaggle auth login`。本仓库 venv 是 Python 3.9 + kaggle 1.7，只认 legacy `username/key`，不认浏览器 OAuth，也不认新的 `KAGGLE_API_TOKEN`。

一次性把 [Legacy API Key](https://www.kaggle.com/settings/api) 放到下面任一处（均已 gitignore）：

```bash
# 推荐：仓库根目录
mv ~/Downloads/kaggle.json /Users/wenbozhang/workspace/kaggriculture/kaggle.json

# 或用户目录
mkdir -p ~/.kaggle
mv ~/Downloads/kaggle.json ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json

# 或 .env
# KAGGLE_USERNAME=yourname
# KAGGLE_KEY=xxxxxxxx
```

之后：

```bash
python3 scripts/submit.py -m "obs_step day*24+hour"
python3 scripts/submit.py --status
python3 scripts/submit.py --leaderboard
```

多文件时打包后再交：

```bash
tar -czf submission.tar.gz main.py
python3 scripts/submit.py -f submission.tar.gz -m "multi-file v1"
```
