"""统一配置管理 — 环境变量优先，默认值兼容 OpenClaw"""

import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPTS_DIR)

# ─── 个人记录库（不进 git）──────────────────────────────────
DATA_DIR = os.environ.get(
    "CALORIE_TRACKER_DATA_DIR",
    os.path.expanduser("~/.openclaw/data/calorie-tracker"),
)
RECORDS_DB = os.environ.get(
    "CALORIE_TRACKER_DB_PATH",
    os.path.join(DATA_DIR, "records.db"),
)

# ─── 食物参考库（git 跟踪）──────────────────────────────────
FOODS_SQL = os.path.join(PROJECT_DIR, "data", "foods.sql")
FOODS_DB = os.path.join(PROJECT_DIR, "data", "foods.db")

# 向后兼容
DB_PATH = RECORDS_DB
