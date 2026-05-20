"""卡路里追踪数据存储 — 拆分为 FoodsDB (食物库) + RecordsDB (个人记录)"""

import csv
import json
import os
import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

from rapidfuzz import fuzz, process as rf_process

from config import RECORDS_DB, FOODS_DB, FOODS_SQL

# ═══════════════════════════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════════════════════════

FOODS_SCHEMA = """
CREATE TABLE IF NOT EXISTS static_foods (
    id INTEGER PRIMARY KEY,
    category TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    calories_per_100g REAL DEFAULT 0,
    carbs_per_100g REAL DEFAULT 0,
    protein_per_100g REAL DEFAULT 0,
    fat_per_100g REAL DEFAULT 0,
    fiber_per_100g REAL DEFAULT 0,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS custom_foods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    barcode TEXT UNIQUE,
    brand TEXT DEFAULT '',
    serving_size_g REAL,
    serving_desc TEXT DEFAULT '',
    calories_per_100g REAL DEFAULT 0,
    carbs_per_100g REAL DEFAULT 0,
    protein_per_100g REAL DEFAULT 0,
    fat_per_100g REAL DEFAULT 0,
    fiber_per_100g REAL DEFAULT 0,
    added_date TEXT DEFAULT (datetime('now', 'localtime')),
    image_desc TEXT DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_foods_barcode ON custom_foods(barcode);
CREATE INDEX IF NOT EXISTS idx_custom_foods_name ON custom_foods(name);
CREATE INDEX IF NOT EXISTS idx_static_foods_name ON static_foods(name);
"""

RECORDS_SCHEMA = """
CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_time TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    meal_type TEXT DEFAULT '',
    foods_json TEXT NOT NULL,
    total_calories REAL DEFAULT 0,
    total_carbs REAL DEFAULT 0,
    total_protein REAL DEFAULT 0,
    total_fat REAL DEFAULT 0,
    total_fiber REAL DEFAULT 0,
    image_desc TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calorie_goal INTEGER NOT NULL DEFAULT 2000,
    set_date TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS macro_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calorie INTEGER DEFAULT 2000,
    protein_g REAL,
    carbs_g REAL,
    fat_g REAL,
    fiber_g REAL,
    set_date TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS weight_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    weight REAL NOT NULL,
    recorded_at TEXT DEFAULT (datetime('now', 'localtime')),
    note TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_weight_date ON weight_records(recorded_at);
"""


# ═══════════════════════════════════════════════════════════════
# FoodsDB — 食物参考库 (static_foods + custom_foods)
# ═══════════════════════════════════════════════════════════════

class FoodsDB:
    """管理食物参考库：static_foods (只读) + custom_foods (可读写)"""

    def __init__(self, db_path=None, sql_path=None):
        self.db_path = db_path or FOODS_DB
        self.sql_path = sql_path or FOODS_SQL
        self._ensure_db()

    def _ensure_db(self):
        """如果 foods.db 不存在，从 foods.sql 构建"""
        if os.path.exists(self.db_path):
            return
        if os.path.exists(self.sql_path):
            self._build_from_sql()

    def _build_from_sql(self):
        """从 foods.sql 文本文件构建 foods.db"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        with open(self.sql_path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(FOODS_SCHEMA)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ─── 查询（统一入口）──────────────────────────────────────

    def lookup(self, keyword):
        """统一食物查询：先 custom_foods，再 static_foods"""
        results = []

        with self._conn() as db:
            # 1. custom_foods（用户精确数据优先）
            custom_rows = db.execute(
                "SELECT * FROM custom_foods WHERE name LIKE ?",
                (f"%{keyword}%",),
            ).fetchall()
            for r in custom_rows:
                results.append({
                    "source": "custom",
                    "category": "自定义",
                    "name": r["name"],
                    "calories": round(r["calories_per_100g"] or 0, 1),
                    "carbs_g": round(r["carbs_per_100g"] or 0, 1),
                    "protein_g": round(r["protein_per_100g"] or 0, 1),
                    "fat_g": round(r["fat_per_100g"] or 0, 1),
                    "fiber_g": round(r["fiber_per_100g"] or 0, 1),
                    "note": "",
                })

            # 2. static_foods（参考数据）
            static_rows = db.execute(
                "SELECT * FROM static_foods WHERE name LIKE ?",
                (f"%{keyword}%",),
            ).fetchall()
            for r in static_rows:
                results.append({
                    "source": "static",
                    "category": r["category"],
                    "name": r["name"],
                    "calories": round(r["calories_per_100g"] or 0, 1),
                    "carbs_g": round(r["carbs_per_100g"] or 0, 1),
                    "protein_g": round(r["protein_per_100g"] or 0, 1),
                    "fat_g": round(r["fat_per_100g"] or 0, 1),
                    "fiber_g": round(r["fiber_per_100g"] or 0, 1),
                    "note": r["note"] or "",
                })

            # 3. 如果精确匹配不到，用模糊搜索
            if not results:
                all_static = db.execute("SELECT * FROM static_foods").fetchall()
                all_custom = db.execute("SELECT * FROM custom_foods").fetchall()

                static_names = {r["name"]: dict(r) for r in all_static}
                custom_names = {r["name"]: dict(r) for r in all_custom}
                all_names = list(static_names.keys()) + list(custom_names.keys())

                if all_names:
                    matches = rf_process.extract(keyword, all_names, scorer=fuzz.token_sort_ratio, limit=10)
                    for match_name, score, _ in matches:
                        if score < 50:
                            continue
                        if match_name in custom_names:
                            r = custom_names[match_name]
                            results.append({
                                "source": "custom",
                                "category": "自定义",
                                "name": r["name"],
                                "calories": round(r["calories_per_100g"] or 0, 1),
                                "carbs_g": round(r["carbs_per_100g"] or 0, 1),
                                "protein_g": round(r["protein_per_100g"] or 0, 1),
                                "fat_g": round(r["fat_per_100g"] or 0, 1),
                                "fiber_g": round(r["fiber_per_100g"] or 0, 1),
                                "note": "",
                            })
                        if match_name in static_names:
                            r = static_names[match_name]
                            results.append({
                                "source": "static",
                                "category": r["category"],
                                "name": r["name"],
                                "calories": round(r["calories_per_100g"] or 0, 1),
                                "carbs_g": round(r["carbs_per_100g"] or 0, 1),
                                "protein_g": round(r["protein_per_100g"] or 0, 1),
                                "fat_g": round(r["fat_per_100g"] or 0, 1),
                                "fiber_g": round(r["fiber_per_100g"] or 0, 1),
                                "note": r["note"] or "",
                            })

        return {"status": "ok", "keyword": keyword, "count": len(results), "foods": results}

    # ─── custom_foods 写操作 ──────────────────────────────────

    def food_search(self, keyword):
        """搜索自定义食物库"""
        with self._conn() as db:
            rows = db.execute(
                "SELECT * FROM custom_foods WHERE name LIKE ? OR brand LIKE ?",
                (f"%{keyword}%", f"%{keyword}%"),
            ).fetchall()
        foods = [self._format_custom_food(r) for r in rows]
        return {"status": "ok", "foods": foods} if foods else \
            {"status": "ok", "foods": [], "message": f"未找到与「{keyword}」匹配的食物"}

    def food_barcode(self, code):
        """按条码查询"""
        with self._conn() as db:
            row = db.execute("SELECT * FROM custom_foods WHERE barcode = ?", (code,)).fetchone()
        if row:
            return {"status": "ok", "food": self._format_custom_food(row)}
        return {"status": "not_found", "message": f"条码 {code} 未找到"}

    def food_add(self, data):
        """添加自定义食物，同时同步到 foods.sql"""
        with self._conn() as db:
            db.execute(
                """INSERT INTO custom_foods (name, barcode, brand, serving_size_g, serving_desc,
                   calories_per_100g, carbs_per_100g, protein_per_100g, fat_per_100g, fiber_per_100g, image_desc)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (data["name"], data.get("barcode"), data.get("brand", ""),
                 data.get("serving_size_g"), data.get("serving_desc", ""),
                 data.get("calories_per_100g", 0), data.get("carbs_per_100g", 0),
                 data.get("protein_per_100g", 0), data.get("fat_per_100g", 0),
                 data.get("fiber_per_100g", 0), data.get("image_desc", "")),
            )
            food_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            row = db.execute("SELECT * FROM custom_foods WHERE id = ?", (food_id,)).fetchone()

        # 同步到 foods.sql
        self._sync_sql()
        return {"status": "ok", "id": food_id, "food": self._format_custom_food(row)}

    def food_update(self, food_id, data):
        """更新自定义食物"""
        fields, vals = [], []
        for col in ["name", "barcode", "brand", "serving_size_g", "serving_desc",
                     "calories_per_100g", "carbs_per_100g", "protein_per_100g",
                     "fat_per_100g", "fiber_per_100g", "image_desc"]:
            if col in data:
                fields.append(f"{col} = ?")
                vals.append(data[col])
        if not fields:
            return {"status": "error", "message": "没有更新字段"}
        vals.append(int(food_id))
        with self._conn() as db:
            db.execute(f"UPDATE custom_foods SET {', '.join(fields)} WHERE id = ?", vals)
        self._sync_sql()
        return {"status": "ok", "updated_id": int(food_id)}

    def food_delete(self, food_id):
        """删除自定义食物"""
        with self._conn() as db:
            db.execute("DELETE FROM custom_foods WHERE id = ?", (int(food_id),))
            affected = db.execute("SELECT changes()").fetchone()[0]
        self._sync_sql()
        if affected:
            return {"status": "ok", "deleted_id": int(food_id)}
        return {"status": "error", "message": f"未找到 ID {food_id}"}

    def food_list(self):
        """列出所有自定义食物"""
        with self._conn() as db:
            rows = db.execute("SELECT * FROM custom_foods ORDER BY id DESC").fetchall()
        return {"status": "ok", "foods": [self._format_custom_food(r) for r in rows]}

    # ─── foods.sql 同步 ───────────────────────────────────────

    def _sync_sql(self):
        """将 foods.db 的全部内容导出到 foods.sql"""
        with self._conn() as db:
            static_rows = db.execute("SELECT * FROM static_foods ORDER BY id").fetchall()
            custom_rows = db.execute("SELECT * FROM custom_foods ORDER BY id").fetchall()

        with open(self.sql_path, "w", encoding="utf-8") as f:
            f.write("-- 食物参考库 (auto-generated, do not edit manually)\n")
            f.write("-- static_foods: 常见食物标准数据\n")
            f.write("-- custom_foods: 用户录入数据\n\n")
            f.write(FOODS_SCHEMA.strip())
            f.write("\n\n")

            f.write("-- ─── static_foods ────────────────────────────────────────\n\n")
            for r in static_rows:
                f.write(
                    f"INSERT INTO static_foods VALUES ({r['id']},"
                    f"'{r['category']}','{r['name']}',"
                    f"{r['calories_per_100g']},{r['carbs_per_100g']},"
                    f"{r['protein_per_100g']},{r['fat_per_100g']},"
                    f"{r['fiber_per_100g']},'{r['note']}');\n"
                )

            f.write("\n-- ─── custom_foods ────────────────────────────────────────\n\n")
            for r in custom_rows:
                f.write(
                    f"INSERT INTO custom_foods VALUES ({r['id']},"
                    f"'{r['name'].replace(chr(39), chr(39)+chr(39))}',"
                    f"'{(r['barcode'] or '').replace(chr(39), chr(39)+chr(39))}',"
                    f"'{(r['brand'] or '').replace(chr(39), chr(39)+chr(39))}',"
                    f"{r['serving_size_g'] or 'NULL'},"
                    f"'{(r['serving_desc'] or '').replace(chr(39), chr(39)+chr(39))}',"
                    f"{r['calories_per_100g'] or 0},{r['carbs_per_100g'] or 0},"
                    f"{r['protein_per_100g'] or 0},{r['fat_per_100g'] or 0},"
                    f"{r['fiber_per_100g'] or 0},"
                    f"'{(r['added_date'] or '').replace(chr(39), chr(39)+chr(39))}',"
                    f"'{(r['image_desc'] or '').replace(chr(39), chr(39)+chr(39))}');\n"
                )

    # ─── helper ───────────────────────────────────────────────

    @staticmethod
    def _format_custom_food(row):
        return {
            "id": row["id"],
            "name": row["name"],
            "barcode": row["barcode"],
            "brand": row["brand"],
            "serving_size_g": row["serving_size_g"],
            "serving_desc": row["serving_desc"],
            "calories_per_100g": round(row["calories_per_100g"] or 0, 1),
            "carbs_per_100g": round(row["carbs_per_100g"] or 0, 1),
            "protein_per_100g": round(row["protein_per_100g"] or 0, 1),
            "fat_per_100g": round(row["fat_per_100g"] or 0, 1),
            "fiber_per_100g": round(row["fiber_per_100g"] or 0, 1),
            "added_date": row["added_date"],
        }


# ═══════════════════════════════════════════════════════════════
# RecordsDB — 个人记录 (meals, goals, macro_goals, weight)
# ═══════════════════════════════════════════════════════════════

class RecordsDB:
    """管理个人餐食记录、目标、体重"""

    def __init__(self, db_path=None):
        self.db_path = db_path or RECORDS_DB
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(RECORDS_SCHEMA)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ─── helpers ────────────────────────────────────────────────

    def _today_str(self):
        return datetime.now().strftime("%Y-%m-%d")

    def _get_macro_goal(self, conn):
        row = conn.execute(
            "SELECT * FROM macro_goals ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return {
                "calorie": row["calorie"] or 2000,
                "protein_g": row["protein_g"] or 0,
                "carbs_g": row["carbs_g"] or 0,
                "fat_g": row["fat_g"] or 0,
                "fiber_g": row["fiber_g"] or 0,
            }
        cal_row = conn.execute(
            "SELECT calorie_goal FROM goals ORDER BY id DESC LIMIT 1"
        ).fetchone()
        default_cal = cal_row["calorie_goal"] if cal_row else 2000
        return {"calorie": default_cal, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0}

    def _today_totals(self, conn):
        today = self._today_str()
        row = conn.execute(
            """SELECT
                COALESCE(SUM(total_calories), 0) as calories,
                COALESCE(SUM(total_carbs), 0) as carbs_g,
                COALESCE(SUM(total_protein), 0) as protein_g,
                COALESCE(SUM(total_fat), 0) as fat_g,
                COALESCE(SUM(total_fiber), 0) as fiber_g
               FROM meals WHERE meal_time >= ?""",
            (today,),
        ).fetchone()
        return {
            "calories": round(row["calories"], 1),
            "carbs_g": round(row["carbs_g"], 1),
            "protein_g": round(row["protein_g"], 1),
            "fat_g": round(row["fat_g"], 1),
            "fiber_g": round(row["fiber_g"], 1),
        }

    @staticmethod
    def _calc_progress(totals, macro):
        return {
            "calories_pct": round(totals["calories"] / macro["calorie"] * 100, 1) if macro["calorie"] else 0,
            "carbs_pct": round(totals["carbs_g"] / macro["carbs_g"] * 100, 1) if macro.get("carbs_g") else 0,
            "protein_pct": round(totals["protein_g"] / macro["protein_g"] * 100, 1) if macro.get("protein_g") else 0,
            "fat_pct": round(totals["fat_g"] / macro["fat_g"] * 100, 1) if macro.get("fat_g") else 0,
            "fiber_pct": round(totals["fiber_g"] / macro["fiber_g"] * 100, 1) if macro.get("fiber_g") else 0,
        }

    # ─── 餐食记录 ───────────────────────────────────────────────

    def add_meal(self, foods, meal_type="", image_desc=""):
        if not foods:
            raise ValueError("没有食物数据")

        def _get(food, *keys):
            for k in keys:
                v = food.get(k)
                if v is not None:
                    return v
            return 0

        total_cal = sum(f.get("calories", 0) for f in foods)
        total_carbs = sum(_get(f, "carbs_g", "carbs") for f in foods)
        total_protein = sum(_get(f, "protein_g", "protein") for f in foods)
        total_fat = sum(_get(f, "fat_g", "fat") for f in foods)
        total_fiber = sum(_get(f, "fiber_g", "fiber") for f in foods)

        with self._conn() as db:
            db.execute(
                """INSERT INTO meals (meal_type, foods_json, total_calories,
                   total_carbs, total_protein, total_fat, total_fiber, image_desc)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (meal_type, json.dumps(foods, ensure_ascii=False),
                 total_cal, total_carbs, total_protein, total_fat, total_fiber, image_desc),
            )
            meal_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            macro = self._get_macro_goal(db)
            today = self._today_totals(db)

        return {
            "status": "ok",
            "meal_id": meal_id,
            "meal_type": meal_type,
            "foods": foods,
            "totals": {
                "calories": round(total_cal, 1),
                "carbs_g": round(total_carbs, 1),
                "protein_g": round(total_protein, 1),
                "fat_g": round(total_fat, 1),
                "fiber_g": round(total_fiber, 1),
            },
            "today": today,
            "macro_goal": macro,
            "remaining": round(macro["calorie"] - today["calories"], 1),
            "progress": self._calc_progress(today, macro),
        }

    def summary(self, period="today"):
        today = self._today_str()
        if period == "today":
            start, end_date = today, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        elif period == "week":
            now = datetime.now()
            start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
            end_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        elif period == "yesterday":
            start = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            end_date = today
        else:
            start = period
            end_date = (datetime.strptime(period, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

        with self._conn() as db:
            meals = db.execute(
                "SELECT * FROM meals WHERE meal_time >= ? AND meal_time < ? ORDER BY meal_time ASC",
                (start, end_date),
            ).fetchall()
            macro = self._get_macro_goal(db)

        totals = {"calories": 0, "carbs_g": 0, "protein_g": 0, "fat_g": 0, "fiber_g": 0}
        meal_list = []
        for m in meals:
            foods = json.loads(m["foods_json"])
            totals["calories"] += m["total_calories"] or 0
            totals["carbs_g"] += m["total_carbs"] or 0
            totals["protein_g"] += m["total_protein"] or 0
            totals["fat_g"] += m["total_fat"] or 0
            totals["fiber_g"] += m["total_fiber"] or 0
            meal_list.append({
                "id": m["id"], "time": m["meal_time"], "meal_type": m["meal_type"],
                "foods": foods,
                "totals": {
                    "calories": round(m["total_calories"] or 0, 1),
                    "carbs_g": round(m["total_carbs"] or 0, 1),
                    "protein_g": round(m["total_protein"] or 0, 1),
                    "fat_g": round(m["total_fat"] or 0, 1),
                    "fiber_g": round(m["total_fiber"] or 0, 1),
                },
            })

        totals_rounded = {k: round(v, 1) for k, v in totals.items()}
        return {
            "status": "ok",
            "period": period,
            "meals": meal_list,
            "totals": totals_rounded,
            "macro_goal": macro,
            "remaining": round(macro["calorie"] - totals["calories"], 1),
            "progress": self._calc_progress(totals_rounded, macro),
        }

    def meal_list(self, date_str="today"):
        today = self._today_str()
        if date_str == "today":
            start, end_date = today, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start = date_str
            end_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

        with self._conn() as db:
            rows = db.execute(
                "SELECT id, meal_time, meal_type, foods_json, total_calories FROM meals "
                "WHERE meal_time >= ? AND meal_time < ? ORDER BY meal_time ASC",
                (start, end_date),
            ).fetchall()

        meals = []
        for r in rows:
            meals.append({
                "id": r["id"], "time": r["meal_time"], "meal_type": r["meal_type"],
                "foods": json.loads(r["foods_json"]),
                "calories": round(r["total_calories"] or 0, 1),
            })
        return {"status": "ok", "period": date_str, "meals": meals}

    def meal_delete(self, meal_id):
        with self._conn() as db:
            db.execute("DELETE FROM meals WHERE id = ?", (int(meal_id),))
            affected = db.execute("SELECT changes()").fetchone()[0]
        if affected:
            return {"status": "ok", "deleted_id": int(meal_id), "message": f"已删除记录 #{meal_id}"}
        return {"status": "error", "message": f"未找到 ID 为 {meal_id} 的记录"}

    def meal_update(self, meal_id, data):
        fields, vals = [], []
        if "meal_type" in data:
            fields.append("meal_type = ?"); vals.append(data["meal_type"])
        if "foods" in data:
            foods = data["foods"]
            fields.append("foods_json = ?"); vals.append(json.dumps(foods, ensure_ascii=False))
            def _get(food, *keys):
                for k in keys:
                    v = food.get(k)
                    if v is not None:
                        return v
                return 0

            total_cal = sum(f.get("calories", 0) for f in foods)
            total_carbs = sum(_get(f, "carbs_g", "carbs") for f in foods)
            total_protein = sum(_get(f, "protein_g", "protein") for f in foods)
            total_fat = sum(_get(f, "fat_g", "fat") for f in foods)
            total_fiber = sum(_get(f, "fiber_g", "fiber") for f in foods)
            fields.extend([
                "total_calories = ?", "total_carbs = ?",
                "total_protein = ?", "total_fat = ?", "total_fiber = ?",
            ])
            vals.extend([total_cal, total_carbs, total_protein, total_fat, total_fiber])
        if not fields:
            return {"status": "error", "message": "没有更新字段"}
        vals.append(int(meal_id))
        with self._conn() as db:
            db.execute(f"UPDATE meals SET {', '.join(fields)} WHERE id = ?", vals)
        return {"status": "ok", "updated_id": int(meal_id)}

    def repeat(self, n=1):
        with self._conn() as db:
            row = db.execute(
                "SELECT * FROM meals ORDER BY id DESC LIMIT 1 OFFSET ?", (n - 1,)
            ).fetchone()
        if not row:
            return {"status": "error", "message": f"没有第{n}条记录"}
        foods = json.loads(row["foods_json"])
        return self.add_meal(foods, meal_type=row["meal_type"])

    def delete_last(self):
        with self._conn() as db:
            row = db.execute("SELECT id FROM meals ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return {"status": "error", "message": "没有记录可删除"}
            db.execute("DELETE FROM meals WHERE id = ?", (row["id"],))
        return {"status": "ok", "deleted_id": row["id"], "message": "已删除最后一条记录"}

    def recent_foods(self, limit=10):
        with self._conn() as db:
            rows = db.execute(
                "SELECT foods_json, meal_time FROM meals ORDER BY id DESC LIMIT ?", (limit * 3,)
            ).fetchall()
        food_counts = {}
        for r in rows:
            for f in json.loads(r["foods_json"]):
                name = f.get("name", "")
                if name:
                    food_counts[name] = food_counts.get(name, 0) + 1
        sorted_foods = sorted(food_counts.items(), key=lambda x: -x[1])[:limit]
        return {"status": "ok", "foods": [{"name": n, "count": c} for n, c in sorted_foods]}

    # ─── 目标 ───────────────────────────────────────────────────

    def goal_set(self, value):
        with self._conn() as db:
            db.execute("INSERT INTO goals (calorie_goal) VALUES (?)", (int(value),))
        return {"status": "ok", "goal": int(value)}

    def goal_get(self):
        with self._conn() as db:
            row = db.execute("SELECT calorie_goal FROM goals ORDER BY id DESC LIMIT 1").fetchone()
        return {"status": "ok", "goal": row["calorie_goal"] if row else 2000}

    def macro_set(self, **kwargs):
        with self._conn() as db:
            current = self._get_macro_goal(db)
            for k in ["protein_g", "carbs_g", "fat_g", "fiber_g", "calorie"]:
                if k in kwargs:
                    current[k] = float(kwargs[k])
            db.execute(
                "INSERT INTO macro_goals (calorie, protein_g, carbs_g, fat_g, fiber_g) VALUES (?,?,?,?,?)",
                (current["calorie"], current.get("protein_g"), current.get("carbs_g"),
                 current.get("fat_g"), current.get("fiber_g")),
            )
        return {"status": "ok", "macro": current, "message": f"宏量目标已更新"}

    def macro_get(self):
        with self._conn() as db:
            return {"status": "ok", "macro": self._get_macro_goal(db)}

    # ─── 体重 ───────────────────────────────────────────────────

    def weight_add(self, kg, note=""):
        with self._conn() as db:
            db.execute("INSERT INTO weight_records (weight, note) VALUES (?, ?)", (float(kg), note))
        return {"status": "ok", "weight": float(kg)}

    def weight_list(self, days=30):
        with self._conn() as db:
            rows = db.execute(
                "SELECT * FROM weight_records ORDER BY id DESC LIMIT ?", (int(days),)
            ).fetchall()
        return {"status": "ok", "records": [dict(r) for r in rows]}

    def weight_latest(self):
        with self._conn() as db:
            row = db.execute(
                "SELECT * FROM weight_records ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row:
            return {"status": "ok", "weight": row["weight"],
                    "recorded_at": row["recorded_at"], "note": row["note"]}
        return {"status": "ok", "weight": None, "message": "还没有体重记录"}

    # ─── 健康数据导出 ──────────────────────────────────────────

    def health_export(self, period="today", date_str=None):
        today = self._today_str()
        if period == "today":
            start, end_date = today, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        elif period == "week":
            now = datetime.now()
            start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
            end_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        elif period == "date" and date_str:
            start = date_str
            end_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start, end_date = today, (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        with self._conn() as db:
            rows = db.execute(
                "SELECT * FROM meals WHERE meal_time >= ? AND meal_time < ? ORDER BY meal_time ASC",
                (start, end_date),
            ).fetchall()
            weight_row = db.execute(
                "SELECT weight FROM weight_records WHERE recorded_at >= ? AND recorded_at < ? "
                "ORDER BY ABS(julianday(recorded_at) - julianday(?)) LIMIT 1",
                (start, end_date, start if date_str else today),
            ).fetchone()

        totals = {"dietaryEnergyConsumed": 0, "dietaryCarbohydrates": 0,
                  "dietaryProtein": 0, "dietaryFatTotal": 0, "dietaryFiber": 0}
        meals_detail = []
        for m in rows:
            totals["dietaryEnergyConsumed"] += m["total_calories"] or 0
            totals["dietaryCarbohydrates"] += m["total_carbs"] or 0
            totals["dietaryProtein"] += m["total_protein"] or 0
            totals["dietaryFatTotal"] += m["total_fat"] or 0
            totals["dietaryFiber"] += m["total_fiber"] or 0
            meals_detail.append({
                "time": m["meal_time"], "meal_type": m["meal_type"],
                "foods": json.loads(m["foods_json"]),
            })

        for k in totals:
            totals[k] = round(totals[k], 1)

        return {
            "date": start if date_str else today, "period": period,
            "meal_count": len(rows), "meals": meals_detail, "health_data": totals,
            "weight_kg": round(weight_row["weight"], 1) if weight_row else None,
            "healthkit_mapping": {
                "dietaryEnergyConsumed": "HKQuantityTypeIdentifierDietaryEnergyConsumed",
                "dietaryCarbohydrates": "HKQuantityTypeIdentifierDietaryCarbohydrates",
                "dietaryProtein": "HKQuantityTypeIdentifierDietaryProtein",
                "dietaryFatTotal": "HKQuantityTypeIdentifierDietaryFatTotal",
                "dietaryFiber": "HKQuantityTypeIdentifierDietaryFiber",
                "bodyMass": "HKQuantityTypeIdentifierBodyMass",
            },
        }

    # ─── 维护 ───────────────────────────────────────────────────

    def checkpoint(self):
        with self._conn() as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return {"status": "ok", "message": "WAL checkpoint 完成"}

    def stats(self):
        with self._conn() as db:
            meals = db.execute("SELECT COUNT(*) as c FROM meals").fetchone()["c"]
            weights = db.execute("SELECT COUNT(*) as c FROM weight_records").fetchone()["c"]
        return {"status": "ok", "total_meals": meals, "weight_records": weights}


# ═══════════════════════════════════════════════════════════════
# 向后兼容：CalorieDB 委托给 FoodsDB + RecordsDB
# ═══════════════════════════════════════════════════════════════

class CalorieDB:
    """向后兼容的门面类，委托给 FoodsDB + RecordsDB"""

    def __init__(self, db_path=None):
        self.foods = FoodsDB()
        self.records = RecordsDB(db_path)

    # ─── 食物查询（委托 FoodsDB）───────────────────────────────

    def foods_lookup(self, keyword):
        return self.foods.lookup(keyword)

    def food_search(self, keyword):
        return self.foods.food_search(keyword)

    def food_barcode(self, code):
        return self.foods.food_barcode(code)

    def food_add(self, data):
        return self.foods.food_add(data)

    def food_update(self, food_id, data):
        return self.foods.food_update(food_id, data)

    def food_delete(self, food_id):
        return self.foods.food_delete(food_id)

    def food_list(self):
        return self.foods.food_list()

    # ─── 个人记录（委托 RecordsDB）─────────────────────────────

    def add_meal(self, foods, meal_type="", image_desc=""):
        return self.records.add_meal(foods, meal_type, image_desc)

    def summary(self, period="today"):
        return self.records.summary(period)

    def meal_list(self, date_str="today"):
        return self.records.meal_list(date_str)

    def meal_delete(self, meal_id):
        return self.records.meal_delete(meal_id)

    def meal_update(self, meal_id, data):
        return self.records.meal_update(meal_id, data)

    def repeat(self, n=1):
        return self.records.repeat(n)

    def delete_last(self):
        return self.records.delete_last()

    def recent_foods(self, limit=10):
        return self.records.recent_foods(limit)

    def goal_set(self, value):
        return self.records.goal_set(value)

    def goal_get(self):
        return self.records.goal_get()

    def macro_set(self, **kwargs):
        return self.records.macro_set(**kwargs)

    def macro_get(self):
        return self.records.macro_get()

    def weight_add(self, kg, note=""):
        return self.records.weight_add(kg, note)

    def weight_list(self, days=30):
        return self.records.weight_list(days)

    def weight_latest(self):
        return self.records.weight_latest()

    def health_export(self, period="today", date_str=None):
        return self.records.health_export(period, date_str)

    def checkpoint(self):
        return self.records.checkpoint()

    def stats(self):
        r = self.records.stats()
        f = self.foods.food_list()
        r["custom_foods"] = len(f.get("foods", []))
        return r
