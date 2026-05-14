"""卡路里追踪数据存储 — SQLite 封装"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

from config import DB_PATH, FOODS_CSV

SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_custom_foods_barcode ON custom_foods(barcode);
CREATE INDEX IF NOT EXISTS idx_custom_foods_name ON custom_foods(name);

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


class CalorieDB:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
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

    def _format_custom_food(self, row):
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

    # ─── 餐食记录 ───────────────────────────────────────────────

    def add_meal(self, foods, meal_type="", image_desc=""):
        if not foods:
            raise ValueError("没有食物数据")

        total_cal = sum(f.get("calories", 0) for f in foods)
        total_carbs = sum(f.get("carbs_g", 0) for f in foods)
        total_protein = sum(f.get("protein_g", 0) for f in foods)
        total_fat = sum(f.get("fat_g", 0) for f in foods)
        total_fiber = sum(f.get("fiber_g", 0) for f in foods)

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
            fields.append("total_calories = ?"); vals.append(sum(f.get("calories", 0) for f in foods))
            fields.append("total_carbs = ?"); vals.append(sum(f.get("carbs_g", 0) for f in foods))
            fields.append("total_protein = ?"); vals.append(sum(f.get("protein_g", 0) for f in foods))
            fields.append("total_fat = ?"); vals.append(sum(f.get("fat_g", 0) for f in foods))
            fields.append("total_fiber = ?"); vals.append(sum(f.get("fiber_g", 0) for f in foods))
        if "image_desc" in data:
            fields.append("image_desc = ?"); vals.append(data["image_desc"])

        if not fields:
            return {"status": "error", "message": "没有要更新的字段"}

        vals.append(int(meal_id))
        with self._conn() as db:
            db.execute(f"UPDATE meals SET {', '.join(fields)} WHERE id = ?", vals)
            affected = db.execute("SELECT changes()").fetchone()[0]
        if affected:
            return {"status": "ok", "updated_id": int(meal_id), "message": f"已更新记录 #{meal_id}"}
        return {"status": "error", "message": f"未找到 ID 为 {meal_id} 的记录"}

    def delete_last(self):
        with self._conn() as db:
            row = db.execute("SELECT id, foods_json FROM meals ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return {"status": "error", "message": "没有可删除的记录"}
            db.execute("DELETE FROM meals WHERE id = ?", (row["id"],))
            foods = json.loads(row["foods_json"])
            names = ", ".join(f["name"] for f in foods)
        return {"status": "ok", "message": f"已删除最后一条记录：{names}", "deleted_id": row["id"]}

    def repeat(self, n=1):
        offset = int(n) - 1
        with self._conn() as db:
            row = db.execute(
                "SELECT * FROM meals ORDER BY id DESC LIMIT 1 OFFSET ?", (offset,)
            ).fetchone()
            if not row:
                return {"status": "error", "message": f"没有找到第 {n} 条记录"}

            foods = json.loads(row["foods_json"])
            meal_type = row["meal_type"]
            total_cal = sum(f.get("calories", 0) for f in foods)
            total_carbs = sum(f.get("carbs_g", 0) for f in foods)
            total_protein = sum(f.get("protein_g", 0) for f in foods)
            total_fat = sum(f.get("fat_g", 0) for f in foods)
            total_fiber = sum(f.get("fiber_g", 0) for f in foods)

            db.execute(
                "INSERT INTO meals (meal_type, foods_json, total_calories, total_carbs, total_protein, total_fat, total_fiber) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (meal_type, row["foods_json"], total_cal, total_carbs, total_protein, total_fat, total_fiber),
            )
            new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            goal = self._get_macro_goal(db)["calorie"]
            today_cal = db.execute(
                "SELECT COALESCE(SUM(total_calories),0) FROM meals WHERE meal_time >= ?",
                (self._today_str(),),
            ).fetchone()[0]

        return {
            "status": "ok", "meal_id": new_id, "meal_type": meal_type, "foods": foods,
            "totals": {"calories": round(total_cal, 1), "carbs_g": round(total_carbs, 1),
                       "protein_g": round(total_protein, 1), "fat_g": round(total_fat, 1),
                       "fiber_g": round(total_fiber, 1)},
            "today": {"calories": round(today_cal, 1), "goal": goal,
                      "remaining": round(goal - today_cal, 1),
                      "progress_pct": round(today_cal / goal * 100, 1) if goal else 0},
            "message": "已复刻最近一餐",
        }

    def recent_foods(self, limit=10):
        with self._conn() as db:
            rows = db.execute(
                "SELECT foods_json FROM meals ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        seen = set()
        unique = []
        for r in rows:
            for f in json.loads(r["foods_json"]):
                if f["name"] not in seen:
                    seen.add(f["name"])
                    unique.append(f["name"])
        return {"status": "ok", "recent_foods": unique[:20]}

    # ─── 热量/宏量目标 ──────────────────────────────────────────

    def goal_set(self, value):
        goal = int(value)
        with self._conn() as db:
            db.execute("INSERT INTO goals (calorie_goal) VALUES (?)", (goal,))
        return {"status": "ok", "goal": goal, "message": f"热量目标已更新为 {goal} kcal/天"}

    def goal_get(self):
        with self._conn() as db:
            row = db.execute("SELECT calorie_goal FROM goals ORDER BY id DESC LIMIT 1").fetchone()
        return {"status": "ok", "goal": row["calorie_goal"] if row else 2000}

    def macro_get(self):
        with self._conn() as db:
            return {"status": "ok", "macro": self._get_macro_goal(db)}

    def macro_set(self, **kwargs):
        """统一的多字段宏量目标设置。kwargs key: calorie, protein, carbs, fat, fiber"""
        col_map = {
            "protein": "protein_g", "carbs": "carbs_g", "fat": "fat_g",
            "fiber": "fiber_g", "calorie": "calorie",
        }
        with self._conn() as db:
            current = self._get_macro_goal(db)
            update = {
                "calorie": current["calorie"],
                "protein_g": current["protein_g"],
                "carbs_g": current["carbs_g"],
                "fat_g": current["fat_g"],
                "fiber_g": current["fiber_g"],
            }
            for raw_key, raw_val in kwargs.items():
                col = col_map.get(raw_key, raw_key)
                update[col] = float(raw_val)

            db.execute(
                "INSERT INTO macro_goals (calorie, protein_g, carbs_g, fat_g, fiber_g) "
                "VALUES (?, ?, ?, ?, ?)",
                (update["calorie"], update["protein_g"], update["carbs_g"],
                 update["fat_g"], update["fiber_g"]),
            )

        msg_parts = []
        for k, v in update.items():
            unit = "kcal" if k == "calorie" else "g"
            msg_parts.append(f"{k.replace('_g','')} {v:.0f}{unit}")

        return {
            "status": "ok",
            "macro": {k: round(v, 1) for k, v in update.items()},
            "message": f"宏量目标已更新：{', '.join(msg_parts)}",
        }

    # ─── 自定义食物 ─────────────────────────────────────────────

    def food_add(self, data):
        if not data.get("name"):
            return {"status": "error", "message": "食物名称不能为空"}

        with self._conn() as db:
            try:
                db.execute(
                    """INSERT INTO custom_foods
                       (name, barcode, brand, serving_size_g, serving_desc,
                        calories_per_100g, carbs_per_100g, protein_per_100g,
                        fat_per_100g, fiber_per_100g, image_desc)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (data["name"], data.get("barcode"), data.get("brand", ""),
                     data.get("serving_size_g"), data.get("serving_desc", ""),
                     data.get("calories_per_100g", 0), data.get("carbs_per_100g", 0),
                     data.get("protein_per_100g", 0), data.get("fat_per_100g", 0),
                     data.get("fiber_per_100g", 0), data.get("image_desc", "")),
                )
                food_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            except sqlite3.IntegrityError:
                return {"status": "error", "message": f"条码 {data.get('barcode')} 已存在"}

        return {
            "status": "ok", "food_id": food_id, "name": data["name"],
            "barcode": data.get("barcode"),
            "message": f"已录入食物：{data['name']}" +
                       (f"（条码：{data['barcode']}）" if data.get("barcode") else ""),
        }

    def food_search(self, keyword):
        with self._conn() as db:
            rows = db.execute(
                "SELECT * FROM custom_foods WHERE name LIKE ? ORDER BY name ASC",
                (f"%{keyword}%",),
            ).fetchall()
        foods = [self._format_custom_food(r) for r in rows]
        if not foods:
            return {"status": "ok", "foods": [], "message": f"未找到包含「{keyword}」的食物"}
        return {"status": "ok", "foods": foods}

    def food_barcode(self, barcode):
        with self._conn() as db:
            row = db.execute(
                "SELECT * FROM custom_foods WHERE barcode = ?", (barcode,)
            ).fetchone()
        if not row:
            return {"status": "not_found", "barcode": barcode,
                    "message": f"未找到条码 {barcode} 对应的食物，可以拍照营养表录入"}

        food = self._format_custom_food(row)
        serving = None
        if food["serving_size_g"]:
            sf = food["serving_size_g"] / 100
            serving = {
                "calories": round(food["calories_per_100g"] * sf, 1),
                "carbs_g": round(food["carbs_per_100g"] * sf, 1),
                "protein_g": round(food["protein_per_100g"] * sf, 1),
                "fat_g": round(food["fat_per_100g"] * sf, 1),
                "fiber_g": round(food["fiber_per_100g"] * sf, 1),
            }
        return {"status": "found", "food": food, "per_serving": serving}

    def food_list(self):
        with self._conn() as db:
            rows = db.execute(
                "SELECT * FROM custom_foods ORDER BY added_date DESC"
            ).fetchall()
        foods = [self._format_custom_food(r) for r in rows]
        return {"status": "ok", "count": len(foods), "foods": foods}

    def food_delete(self, food_id):
        with self._conn() as db:
            db.execute("DELETE FROM custom_foods WHERE id = ?", (int(food_id),))
            affected = db.execute("SELECT changes()").fetchone()[0]
        if affected:
            return {"status": "ok", "message": f"已删除食物（ID: {food_id}）"}
        return {"status": "error", "message": f"未找到 ID 为 {food_id} 的食物"}

    def food_update(self, food_id, data):
        allowed = [
            "name", "barcode", "brand", "serving_size_g", "serving_desc",
            "calories_per_100g", "carbs_per_100g", "protein_per_100g",
            "fat_per_100g", "fiber_per_100g",
        ]
        sets, vals = [], []
        for f in allowed:
            if f in data:
                sets.append(f"{f} = ?"); vals.append(data[f])
        if not sets:
            return {"status": "error", "message": "没有要更新的字段"}

        vals.append(int(food_id))
        with self._conn() as db:
            db.execute(f"UPDATE custom_foods SET {', '.join(sets)} WHERE id = ?", vals)
            affected = db.execute("SELECT changes()").fetchone()[0]
        if affected:
            return {"status": "ok", "message": f"已更新食物（ID: {food_id}）"}
        return {"status": "error", "message": f"未找到 ID 为 {food_id} 的食物"}

    # ─── foods.csv 查询 ─────────────────────────────────────────

    def foods_lookup(self, keyword):
        """在 foods.csv 中搜索食物参考数据"""
        if not os.path.exists(FOODS_CSV):
            return {"status": "error", "message": "foods.csv 不存在"}

        import csv
        results = []
        with open(FOODS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if keyword in row.get("食物名称", ""):
                    results.append({
                        "category": row.get("分类", ""),
                        "name": row["食物名称"],
                        "calories": float(row.get("每100g热量(kcal)", 0)),
                        "carbs_g": float(row.get("碳水(g)", 0)),
                        "protein_g": float(row.get("蛋白质(g)", 0)),
                        "fat_g": float(row.get("脂肪(g)", 0)),
                        "fiber_g": float(row.get("膳食纤维(g)", 0)),
                        "note": row.get("备注", ""),
                    })
        return {"status": "ok", "keyword": keyword, "count": len(results), "foods": results}

    # ─── 体重记录 ───────────────────────────────────────────────

    def weight_add(self, weight_kg, note=""):
        try:
            weight = float(weight_kg)
        except (ValueError, TypeError):
            return {"status": "error", "message": f"无效的体重值: {weight_kg}"}

        with self._conn() as db:
            db.execute(
                "INSERT INTO weight_records (weight, note) VALUES (?, ?)", (weight, note)
            )
            record_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            prev = db.execute(
                "SELECT weight FROM weight_records WHERE id < ? ORDER BY id DESC LIMIT 1",
                (record_id,),
            ).fetchone()
            change = round(weight - prev["weight"], 1) if prev else 0

            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            week_rows = db.execute(
                "SELECT weight, recorded_at FROM weight_records WHERE recorded_at >= ? ORDER BY recorded_at ASC",
                (week_ago,),
            ).fetchall()

        result = {"status": "ok", "weight": weight, "record_id": record_id,
                  "note": note, "change_vs_last": change}
        if len(week_rows) >= 2:
            first_w, last_w = week_rows[0]["weight"], week_rows[-1]["weight"]
            if last_w != first_w:
                result["trend_7d"] = {"start": first_w, "end": last_w,
                                      "change": round(last_w - first_w, 1)}
        return result

    def weight_list(self, days=30):
        since = (datetime.now() - timedelta(days=int(days))).strftime("%Y-%m-%d")
        with self._conn() as db:
            rows = db.execute(
                "SELECT * FROM weight_records WHERE recorded_at >= ? ORDER BY recorded_at DESC",
                (since,),
            ).fetchall()
        records = [{"id": r["id"], "weight": r["weight"],
                    "recorded_at": r["recorded_at"], "note": r["note"]} for r in rows]
        return {"status": "ok", "count": len(records), "records": records}

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
            foods = db.execute("SELECT COUNT(*) as c FROM custom_foods").fetchone()["c"]
            weights = db.execute("SELECT COUNT(*) as c FROM weight_records").fetchone()["c"]
        return {"status": "ok", "total_meals": meals, "custom_foods": foods,
                "weight_records": weights}
