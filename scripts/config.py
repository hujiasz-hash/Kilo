"""统一配置管理 — 环境变量优先，默认值兼容 OpenClaw"""

import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPTS_DIR)

DATA_DIR = os.environ.get(
    "CALORIE_TRACKER_DATA_DIR",
    os.path.expanduser("~/.openclaw/data/calorie-tracker"),
)
DB_PATH = os.environ.get(
    "CALORIE_TRACKER_DB_PATH",
    os.path.join(DATA_DIR, "calories.db"),
)
FOODS_CSV = os.path.join(PROJECT_DIR, "data", "foods.csv")
