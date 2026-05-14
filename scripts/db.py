#!/usr/bin/env python3
"""卡路里追踪数据存储 - SQLite 读写"""

import sqlite3
import json
import os
import sys
from datetime import datetime, timedelta

DB_DIR = os.path.expanduser("~/.openclaw/data/calorie-tracker")
DB_PATH = os.path.join(DB_DIR, "calories.db")


def get_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_tables(conn)
    return conn


def _init_tables(conn):
    conn.executescript("""
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
    """)
    conn.commit()


# ─── CLI ───────────────────────────────────────────────────────────

def cmd_add(foods_json_str):
    """添加一顿餐食记录"""
    data = json.loads(foods_json_str)
    foods = data.get("foods", [])
    if not foods:
        print("ERROR: 没有食物数据")
        sys.exit(1)

    meal_type = data.get("meal_type", "")
    image_desc = data.get("image_desc", "")

    total_cal = sum(f.get("calories", 0) for f in foods)
    total_carbs = sum(f.get("carbs_g", 0) for f in foods)
    total_protein = sum(f.get("protein_g", 0) for f in foods)
    total_fat = sum(f.get("fat_g", 0) for f in foods)
    total_fiber = sum(f.get("fiber_g", 0) for f in foods)

    db = get_db()
    db.execute(
        """INSERT INTO meals (meal_type, foods_json, total_calories,
           total_carbs, total_protein, total_fat, total_fiber, image_desc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (meal_type, json.dumps(foods, ensure_ascii=False),
         total_cal, total_carbs, total_protein, total_fat, total_fiber, image_desc)
    )
    db.commit()

    meal_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    macro = _get_macro_goal(db)
    today_totals = _today_totals(db)
    db.close()

    print(json.dumps({
        "status": "ok",
        "meal_id": meal_id,
        "meal_type": meal_type,
        "foods": foods,
        "totals": {
            "calories": round(total_cal, 1),
            "carbs_g": round(total_carbs, 1),
            "protein_g": round(total_protein, 1),
            "fat_g": round(total_fat, 1),
            "fiber_g": round(total_fiber, 1)
        },
        "today": today_totals,
        "macro_goal": macro,
        "remaining": round(macro["calorie"] - today_totals["calories"], 1),
        "progress": _calc_progress(today_totals, macro)
    }, ensure_ascii=False))


def cmd_summary(period="today"):
    """查询汇总"""
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    if period == "today":
        start = today
        end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    elif period == "week":
        now = datetime.now()
        start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        end = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    elif period == "yesterday":
        start = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        end = today
    else:
        start = period
        end = (datetime.strptime(period, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    meals = db.execute(
        "SELECT * FROM meals WHERE meal_time >= ? AND meal_time < ? ORDER BY meal_time ASC",
        (start, end)
    ).fetchall()

    macro = _get_macro_goal(db)
    db.close()

    if not meals:
        print(json.dumps({
            "status": "ok",
            "period": period,
            "meals": [],
            "totals": {"calories": 0, "carbs_g": 0, "protein_g": 0, "fat_g": 0, "fiber_g": 0},
            "macro_goal": macro,
            "remaining": macro["calorie"],
            "progress": _calc_progress({"calories": 0, "carbs_g": 0, "protein_g": 0, "fat_g": 0, "fiber_g": 0}, macro),
            "message": "该时段还没有记录"
        }, ensure_ascii=False))
        return

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
            "id": m["id"],
            "time": m["meal_time"],
            "meal_type": m["meal_type"],
            "foods": foods,
            "totals": {
                "calories": round(m["total_calories"] or 0, 1),
                "carbs_g": round(m["total_carbs"] or 0, 1),
                "protein_g": round(m["total_protein"] or 0, 1),
                "fat_g": round(m["total_fat"] or 0, 1),
                "fiber_g": round(m["total_fiber"] or 0, 1)
            }
        })

    totals_rounded = {k: round(v, 1) for k, v in totals.items()}
    print(json.dumps({
        "status": "ok",
        "period": period,
        "meals": meal_list,
        "totals": totals_rounded,
        "macro_goal": macro,
        "remaining": round(macro["calorie"] - totals["calories"], 1),
        "progress": _calc_progress(totals_rounded, macro)
    }, ensure_ascii=False))


def _calc_progress(totals, macro):
    """计算各营养素完成百分比"""
    return {
        "calories_pct": round(totals["calories"] / macro["calorie"] * 100, 1) if macro["calorie"] else 0,
        "carbs_pct": round(totals["carbs_g"] / macro["carbs_g"] * 100, 1) if macro.get("carbs_g") else 0,
        "protein_pct": round(totals["protein_g"] / macro["protein_g"] * 100, 1) if macro.get("protein_g") else 0,
        "fat_pct": round(totals["fat_g"] / macro["fat_g"] * 100, 1) if macro.get("fat_g") else 0,
        "fiber_pct": round(totals["fiber_g"] / macro["fiber_g"] * 100, 1) if macro.get("fiber_g") else 0,
    }


def cmd_goal(action, value=None):
    """管理热量目标"""
    db = get_db()
    if action == "set":
        goal = int(value)
        db.execute("INSERT INTO goals (calorie_goal) VALUES (?)", (goal,))
        db.commit()
        print(json.dumps({"status": "ok", "goal": goal, "message": f"热量目标已更新为 {goal} kcal/天"}))
    elif action == "get":
        goal = _get_goal(db)
        print(json.dumps({"status": "ok", "goal": goal}))
    db.close()


def cmd_delete(target="last"):
    """删除记录"""
    db = get_db()
    if target == "last":
        row = db.execute("SELECT id, foods_json FROM meals ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            db.execute("DELETE FROM meals WHERE id = ?", (row["id"],))
            db.commit()
            foods = json.loads(row["foods_json"])
            names = ", ".join(f["name"] for f in foods)
            print(json.dumps({
                "status": "ok",
                "message": f"已删除最后一条记录：{names}",
                "deleted_id": row["id"]
            }, ensure_ascii=False))
        else:
            print(json.dumps({"status": "error", "message": "没有可删除的记录"}))
    db.close()


def cmd_recent_meals(limit=10):
    """获取最近的用餐记录，用于个性化参考"""
    db = get_db()
    rows = db.execute(
        "SELECT foods_json, meal_type, meal_time FROM meals ORDER BY id DESC LIMIT ?",
        (int(limit),)
    ).fetchall()
    db.close()

    foods_list = []
    for r in rows:
        foods_list.extend(json.loads(r["foods_json"]))

    seen = set()
    unique = []
    for f in foods_list:
        if f["name"] not in seen:
            seen.add(f["name"])
            unique.append(f["name"])

    print(json.dumps({"status": "ok", "recent_foods": unique[:20]}))


# ─── 自定义食物（条码 + 营养表） ─────────────────────────────

def cmd_food_add(json_str):
    """添加自定义食物（条码+营养数据）

    JSON 格式:
    {
        "name": "XX燕麦奶",
        "barcode": "6901234567890",  // 可选
        "brand": "XX品牌",           // 可选
        "serving_size_g": 250,       // 可选，每份克数
        "serving_desc": "1盒",       // 可选，份量描述
        "calories_per_100g": 55,
        "carbs_per_100g": 6.5,
        "protein_per_100g": 1.0,
        "fat_per_100g": 2.0,
        "fiber_per_100g": 1.2,
        "image_desc": ""             // 可选，营养表图片描述
    }
    """
    data = json.loads(json_str)

    if not data.get("name"):
        print(json.dumps({"status": "error", "message": "食物名称不能为空"}))
        return

    db = get_db()
    try:
        db.execute(
            """INSERT INTO custom_foods
               (name, barcode, brand, serving_size_g, serving_desc,
                calories_per_100g, carbs_per_100g, protein_per_100g,
                fat_per_100g, fiber_per_100g, image_desc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["name"],
                data.get("barcode"),
                data.get("brand", ""),
                data.get("serving_size_g"),
                data.get("serving_desc", ""),
                data.get("calories_per_100g", 0),
                data.get("carbs_per_100g", 0),
                data.get("protein_per_100g", 0),
                data.get("fat_per_100g", 0),
                data.get("fiber_per_100g", 0),
                data.get("image_desc", ""),
            )
        )
        db.commit()
        food_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.close()
        print(json.dumps({
            "status": "ok",
            "food_id": food_id,
            "name": data["name"],
            "barcode": data.get("barcode"),
            "message": f"已录入食物：{data['name']}" + (f"（条码：{data['barcode']}）" if data.get("barcode") else "")
        }, ensure_ascii=False))
    except sqlite3.IntegrityError:
        db.close()
        print(json.dumps({
            "status": "error",
            "message": f"条码 {data.get('barcode')} 已存在，请先查询再更新"
        }))


def cmd_food_search(keyword):
    """按名称搜索自定义食物"""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM custom_foods WHERE name LIKE ? ORDER BY name ASC",
        (f"%{keyword}%",)
    ).fetchall()
    db.close()

    if not rows:
        print(json.dumps({"status": "ok", "foods": [], "message": f"未找到包含「{keyword}」的食物"}))
        return

    foods = [_format_custom_food(r) for r in rows]
    print(json.dumps({"status": "ok", "foods": foods}, ensure_ascii=False))


def cmd_food_barcode(barcode):
    """按条码查找食物"""
    db = get_db()
    row = db.execute("SELECT * FROM custom_foods WHERE barcode = ?", (barcode,)).fetchone()
    db.close()

    if not row:
        print(json.dumps({
            "status": "not_found",
            "barcode": barcode,
            "message": f"未找到条码 {barcode} 对应的食物，可以拍照营养表录入"
        }))
        return

    food = _format_custom_food(row)
    # 按每份体积换算
    serving = None
    if food["serving_size_g"]:
        sf = food["serving_size_g"] / 100
        serving = {
            "calories": round(food["calories_per_100g"] * sf, 1),
            "carbs_g": round(food["carbs_per_100g"] * sf, 1),
            "protein_g": round(food["protein_per_100g"] * sf, 1),
            "fat_g": round(food["fat_per_100g"] * sf, 1),
            "fiber_g": round(food["fiber_per_100g"] * sf, 1)
        }
    print(json.dumps({
        "status": "found",
        "food": food,
        "per_serving": serving
    }, ensure_ascii=False))


def cmd_food_list():
    """列出所有自定义食物"""
    db = get_db()
    rows = db.execute("SELECT * FROM custom_foods ORDER BY added_date DESC").fetchall()
    db.close()

    foods = [_format_custom_food(r) for r in rows]
    print(json.dumps({"status": "ok", "count": len(foods), "foods": foods}, ensure_ascii=False))


def cmd_food_delete(food_id):
    """删除自定义食物"""
    db = get_db()
    db.execute("DELETE FROM custom_foods WHERE id = ?", (int(food_id),))
    affected = db.execute("SELECT changes()").fetchone()[0]
    db.commit()
    db.close()

    if affected:
        print(json.dumps({"status": "ok", "message": f"已删除食物（ID: {food_id}）"}))
    else:
        print(json.dumps({"status": "error", "message": f"未找到 ID 为 {food_id} 的食物"}))


def cmd_food_update(food_id, json_str):
    """更新自定义食物数据"""
    data = json.loads(json_str)
    fields = [
        "name", "barcode", "brand", "serving_size_g", "serving_desc",
        "calories_per_100g", "carbs_per_100g", "protein_per_100g",
        "fat_per_100g", "fiber_per_100g"
    ]
    sets = []
    vals = []
    for f in fields:
        if f in data:
            sets.append(f"{f} = ?")
            vals.append(data[f])

    if not sets:
        print(json.dumps({"status": "error", "message": "没有要更新的字段"}))
        return

    vals.append(int(food_id))
    db = get_db()
    db.execute(f"UPDATE custom_foods SET {', '.join(sets)} WHERE id = ?", vals)
    affected = db.execute("SELECT changes()").fetchone()[0]
    db.commit()
    db.close()

    if affected:
        print(json.dumps({"status": "ok", "message": f"已更新食物（ID: {food_id}）"}))
    else:
        print(json.dumps({"status": "error", "message": f"未找到 ID 为 {food_id} 的食物"}))


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
        "added_date": row["added_date"]
    }


# ─── 宏量营养素目标 ─────────────────────────────────────────

def cmd_macro(action, key=None, value=None):
    """管理宏量营养素目标"""
    db = get_db()

    if action == "set":
        # 格式: macro set calorie=2000 protein=120 ...
        if key and "=" in key:
            parts = key.split("=")
            key = parts[0]
            value = parts[1]

        if key and value is not None:
            # 单字段更新：macro set protein=120
            current = _get_macro_goal(db)
            update = {
                "calorie": current["calorie"],
                "protein_g": current["protein_g"],
                "carbs_g": current["carbs_g"],
                "fat_g": current["fat_g"],
                "fiber_g": current["fiber_g"],
            }
            col_map = {"protein": "protein_g", "carbs": "carbs_g", "fat": "fat_g", "fiber": "fiber_g",
                       "calorie": "calorie"}
            col = col_map.get(key, key)
            update[col] = float(value)

            db.execute(
                """INSERT INTO macro_goals (calorie, protein_g, carbs_g, fat_g, fiber_g)
                   VALUES (?, ?, ?, ?, ?)""",
                (update["calorie"], update["protein_g"], update["carbs_g"],
                 update["fat_g"], update["fiber_g"])
            )
            db.commit()
            msg_parts = []
            for k, v in update.items():
                unit = "kcal" if k == "calorie" else "g"
                msg_parts.append(f"{k.replace('_g','')} {v:.0f}{unit}")
            print(json.dumps({
                "status": "ok",
                "macro": {k: round(v, 1) for k, v in update.items()},
                "message": f"宏量目标已更新：{', '.join(msg_parts)}"
            }, ensure_ascii=False))
        else:
            print(json.dumps({"status": "error", "message": "格式: macro set protein=120 或 macro set calorie=2000 protein=120 fat=60"}))
    elif action == "get":
        macro = _get_macro_goal(db)
        print(json.dumps({"status": "ok", "macro": macro}))
    db.close()


def _get_macro_goal(db):
    """获取最新宏量目标，默认值也从中获取"""
    row = db.execute("SELECT * FROM macro_goals ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        return {
            "calorie": row["calorie"] or 2000,
            "protein_g": row["protein_g"] or 0,
            "carbs_g": row["carbs_g"] or 0,
            "fat_g": row["fat_g"] or 0,
            "fiber_g": row["fiber_g"] or 0
        }
    # 回退到老的 calorie_goal
    cal_row = db.execute("SELECT calorie_goal FROM goals ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "calorie": cal_row["calorie_goal"] if cal_row else 2000,
        "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0
    }


# ─── 体重记录 ───────────────────────────────────────────────

def cmd_weight(action, *args):
    """管理体重记录"""
    db = get_db()

    if action == "add":
        if not args:
            print(json.dumps({"status": "error", "message": "请输入体重数值，如: weight add 65.5"}))
            db.close()
            return
        try:
            weight = float(args[0])
        except ValueError:
            print(json.dumps({"status": "error", "message": f"无效的体重值: {args[0]}"}))
            db.close()
            return
        note = " ".join(args[1:]) if len(args) > 1 else ""
        db.execute("INSERT INTO weight_records (weight, note) VALUES (?, ?)", (weight, note))
        db.commit()
        record_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 计算变化
        prev = db.execute(
            "SELECT weight FROM weight_records WHERE id < ? ORDER BY id DESC LIMIT 1",
            (record_id,)
        ).fetchone()
        change = round(weight - prev["weight"], 1) if prev else 0

        # 7天趋势
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        week_rows = db.execute(
            "SELECT weight, recorded_at FROM weight_records WHERE recorded_at >= ? ORDER BY recorded_at ASC",
            (week_ago,)
        ).fetchall()
        trend = None
        if len(week_rows) >= 2:
            first_w = week_rows[0]["weight"]
            last_w = week_rows[-1]["weight"]
            if last_w != first_w:
                trend = {"start": first_w, "end": last_w, "change": round(last_w - first_w, 1)}

        db.close()

        result = {
            "status": "ok",
            "weight": weight,
            "record_id": record_id,
            "note": note,
            "change_vs_last": change
        }
        if trend:
            result["trend_7d"] = trend
        print(json.dumps(result, ensure_ascii=False))

    elif action == "list":
        days = int(args[0]) if args and args[0].isdigit() else 30
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = db.execute(
            "SELECT * FROM weight_records WHERE recorded_at >= ? ORDER BY recorded_at DESC",
            (since,)
        ).fetchall()
        db.close()

        records = [{
            "id": r["id"],
            "weight": r["weight"],
            "recorded_at": r["recorded_at"],
            "note": r["note"]
        } for r in rows]

        print(json.dumps({"status": "ok", "count": len(records), "records": records}, ensure_ascii=False))

    elif action == "latest":
        row = db.execute("SELECT * FROM weight_records ORDER BY id DESC LIMIT 1").fetchone()
        db.close()
        if row:
            print(json.dumps({
                "status": "ok",
                "weight": row["weight"],
                "recorded_at": row["recorded_at"],
                "note": row["note"]
            }, ensure_ascii=False))
        else:
            print(json.dumps({"status": "ok", "weight": None, "message": "还没有体重记录"}))
    else:
        print(json.dumps({"status": "error", "message": f"未知 weight 命令: {action}"}))
        db.close()


# ─── 修改/删除记录 ───────────────────────────────────────

def cmd_meal(action, *args):
    """管理餐食记录：list / delete / update"""
    db = get_db()

    if action == "list":
        period = args[0] if args else "today"
        today = datetime.now().strftime("%Y-%m-%d")

        if period == "today":
            start = today
            end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start = period
            end = (datetime.strptime(period, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

        rows = db.execute(
            "SELECT id, meal_time, meal_type, foods_json, total_calories FROM meals WHERE meal_time >= ? AND meal_time < ? ORDER BY meal_time ASC",
            (start, end)
        ).fetchall()
        db.close()

        meals = []
        for r in rows:
            meals.append({
                "id": r["id"],
                "time": r["meal_time"],
                "meal_type": r["meal_type"],
                "foods": json.loads(r["foods_json"]),
                "calories": round(r["total_calories"] or 0, 1)
            })
        print(json.dumps({"status": "ok", "period": period, "meals": meals}, ensure_ascii=False))

    elif action == "delete":
        if not args:
            print(json.dumps({"status": "error", "message": "请输入要删除的记录 ID"}))
            db.close()
            return
        meal_id = int(args[0])
        db.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
        affected = db.execute("SELECT changes()").fetchone()[0]
        db.commit()
        db.close()
        if affected:
            print(json.dumps({"status": "ok", "deleted_id": meal_id, "message": f"已删除记录 #{meal_id}"}))
        else:
            print(json.dumps({"status": "error", "message": f"未找到 ID 为 {meal_id} 的记录"}))

    elif action == "update":
        if len(args) < 2:
            print(json.dumps({"status": "error", "message": "格式: meal update <id> <json>"}))
            db.close()
            return
        meal_id = int(args[0])
        data = json.loads(args[1])

        fields = []
        vals = []

        if "meal_type" in data:
            fields.append("meal_type = ?")
            vals.append(data["meal_type"])
        if "foods" in data:
            foods = data["foods"]
            fields.append("foods_json = ?")
            vals.append(json.dumps(foods, ensure_ascii=False))
            fields.append("total_calories = ?")
            vals.append(sum(f.get("calories", 0) for f in foods))
            fields.append("total_carbs = ?")
            vals.append(sum(f.get("carbs_g", 0) for f in foods))
            fields.append("total_protein = ?")
            vals.append(sum(f.get("protein_g", 0) for f in foods))
            fields.append("total_fat = ?")
            vals.append(sum(f.get("fat_g", 0) for f in foods))
            fields.append("total_fiber = ?")
            vals.append(sum(f.get("fiber_g", 0) for f in foods))
        if "image_desc" in data:
            fields.append("image_desc = ?")
            vals.append(data["image_desc"])

        if not fields:
            print(json.dumps({"status": "error", "message": "没有要更新的字段"}))
            db.close()
            return

        vals.append(meal_id)
        db.execute(f"UPDATE meals SET {', '.join(fields)} WHERE id = ?", vals)
        affected = db.execute("SELECT changes()").fetchone()[0]
        db.commit()
        db.close()

        if affected:
            print(json.dumps({"status": "ok", "updated_id": meal_id, "message": f"已更新记录 #{meal_id}"}))
        else:
            print(json.dumps({"status": "error", "message": f"未找到 ID 为 {meal_id} 的记录"}))

    else:
        print(json.dumps({"status": "error", "message": f"未知 meal 命令: {action}"}))
        db.close()


# ─── 快捷复刻 ───────────────────────────────────────────────

def cmd_repeat(n):
    """复刻最近第 N 次餐食记录（N=1 最近一次）"""
    db = get_db()
    offset = int(n) - 1 if n else 0
    row = db.execute(
        "SELECT * FROM meals ORDER BY id DESC LIMIT 1 OFFSET ?",
        (offset,)
    ).fetchone()

    if not row:
        db.close()
        print(json.dumps({"status": "error", "message": f"没有找到第 {n} 条记录"}))
        return

    foods = json.loads(row["foods_json"])
    meal_type = row["meal_type"]

    # 重新插入
    total_cal = sum(f.get("calories", 0) for f in foods)
    total_carbs = sum(f.get("carbs_g", 0) for f in foods)
    total_protein = sum(f.get("protein_g", 0) for f in foods)
    total_fat = sum(f.get("fat_g", 0) for f in foods)
    total_fiber = sum(f.get("fiber_g", 0) for f in foods)

    db.execute(
        "INSERT INTO meals (meal_type, foods_json, total_calories, total_carbs, total_protein, total_fat, total_fiber) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (meal_type, row["foods_json"], total_cal, total_carbs, total_protein, total_fat, total_fiber)
    )
    db.commit()
    new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    goal = _get_macro_goal(db)["calorie"]
    today_cal = _today_calories(db)
    db.close()

    print(json.dumps({
        "status": "ok",
        "meal_id": new_id,
        "meal_type": meal_type,
        "foods": foods,
        "totals": {
            "calories": round(total_cal, 1),
            "carbs_g": round(total_carbs, 1),
            "protein_g": round(total_protein, 1),
            "fat_g": round(total_fat, 1),
            "fiber_g": round(total_fiber, 1)
        },
        "today": {
            "calories": round(today_cal, 1),
            "goal": goal,
            "remaining": round(goal - today_cal, 1),
            "progress_pct": round(today_cal / goal * 100, 1) if goal else 0
        },
        "message": f"已复刻最近一餐"
    }, ensure_ascii=False))


# ─── helpers ───────────────────────────────────────────────────────

def _get_goal(db):
    row = db.execute("SELECT calorie_goal FROM goals ORDER BY id DESC LIMIT 1").fetchone()
    return row["calorie_goal"] if row else 2000


def _today_calories(db):
    today = datetime.now().strftime("%Y-%m-%d")
    row = db.execute(
        "SELECT COALESCE(SUM(total_calories), 0) FROM meals WHERE meal_time >= ?",
        (today,)
    ).fetchone()
    return row[0]


def _today_totals(db):
    """获取今日所有营养素累计，含宏量目标"""
    today = datetime.now().strftime("%Y-%m-%d")
    row = db.execute(
        """SELECT
            COALESCE(SUM(total_calories), 0) as calories,
            COALESCE(SUM(total_carbs), 0) as carbs_g,
            COALESCE(SUM(total_protein), 0) as protein_g,
            COALESCE(SUM(total_fat), 0) as fat_g,
            COALESCE(SUM(total_fiber), 0) as fiber_g
           FROM meals WHERE meal_time >= ?""",
        (today,)
    ).fetchone()
    return {
        "calories": round(row["calories"], 1),
        "carbs_g": round(row["carbs_g"], 1),
        "protein_g": round(row["protein_g"], 1),
        "fat_g": round(row["fat_g"], 1),
        "fiber_g": round(row["fiber_g"], 1)
    }


# ─── main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: db.py <command> [args...]")
        print("  餐食记录:")
        print("    add '<json>'           添加餐食记录")
        print("    summary today|week     查看汇总（带宏量目标进度）")
        print("    meal list [日期]       列出指定日期的记录及编号")
        print("    meal delete <id>       按 ID 删除记录")
        print("    meal update <id> json  更新记录的字段")
        print("    delete last            删除最后一条记录")
        print("    repeat <n>             复刻最近第 N 条记录")
        print("    recent                 最近常吃食物")
        print("")
        print("  热量/宏量目标:")
        print("    goal set <n>           设置热量目标")
        print("    goal get               查看热量目标")
        print("    macro set <k=v>...     设置宏量目标 (如: macro set protein=120 carbs=250)")
        print("    macro get              查看宏量目标")
        print("")
        print("  自定义食物（条码+营养表）:")
        print("    food add '<json>'      录入食物（条码+100g营养数据）")
        print("    food search <keyword>  按名称搜索")
        print("    food barcode <code>    按条码查询")
        print("    food list              列出所有")
        print("    food update <id> json  更新")
        print("    food delete <id>       删除")
        print("")
        print("  体重:")
        print("    weight add <kg> [备注] 记录体重")
        print("    weight list [天数]     查看历史体重")
        print("    weight latest          查看最新体重")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "add":
        cmd_add(sys.argv[2] if len(sys.argv) > 2 else sys.stdin.read())
    elif cmd == "summary":
        cmd_summary(sys.argv[2] if len(sys.argv) > 2 else "today")
    elif cmd == "goal":
        cmd_goal(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "delete":
        cmd_delete(sys.argv[2] if len(sys.argv) > 2 else "last")
    elif cmd == "recent":
        cmd_recent_meals(sys.argv[2] if len(sys.argv) > 2 else 10)
    elif cmd == "food" and len(sys.argv) >= 3:
        sub = sys.argv[2]
        if sub == "add":
            cmd_food_add(sys.argv[3] if len(sys.argv) > 3 else sys.stdin.read())
        elif sub == "search":
            cmd_food_search(sys.argv[3] if len(sys.argv) > 3 else "")
        elif sub == "barcode":
            cmd_food_barcode(sys.argv[3] if len(sys.argv) > 3 else "")
        elif sub == "list":
            cmd_food_list()
        elif sub == "delete":
            cmd_food_delete(sys.argv[3] if len(sys.argv) > 3 else "")
        elif sub == "update":
            cmd_food_update(sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "{}")
        else:
            print(f"未知 food 子命令: {sub}")
            sys.exit(1)
    elif cmd == "macro" and len(sys.argv) >= 3:
        sub = sys.argv[2]
        if sub == "set":
            kv_pairs = {}
            for arg in sys.argv[3:]:
                if "=" in arg:
                    k, v = arg.split("=", 1)
                    kv_pairs[k] = v
            if kv_pairs:
                # 一次性设置所有字段
                db = get_db()
                current = _get_macro_goal(db)
                col_map = {"protein": "protein_g", "carbs": "carbs_g", "fat": "fat_g", "fiber": "fiber_g"}
                for k, v in kv_pairs.items():
                    col = col_map.get(k, k)
                    current[col] = float(v)
                db.execute(
                    "INSERT INTO macro_goals (calorie, protein_g, carbs_g, fat_g, fiber_g) VALUES (?, ?, ?, ?, ?)",
                    (current["calorie"], current["protein_g"], current["carbs_g"], current["fat_g"], current["fiber_g"])
                )
                db.commit()
                db.close()
                msg_parts = [f"{k.replace('_g','')} {v:.0f}{'g' if k != 'calorie' else 'kcal'}" for k, v in current.items()]
                print(json.dumps({
                    "status": "ok",
                    "macro": {k: round(v, 1) for k, v in current.items()},
                    "message": f"宏量目标已更新！{', '.join(msg_parts)}"
                }, ensure_ascii=False))
            else:
                print(json.dumps({"status": "error", "message": "格式: macro set protein=120 carbs=250"}))
        else:
            cmd_macro(sub)
    elif cmd == "weight":
        cmd_weight(sys.argv[2] if len(sys.argv) > 2 else "latest",
                   *sys.argv[3:])
    elif cmd == "meal":
        cmd_meal(sys.argv[2] if len(sys.argv) > 2 else "list",
                 *sys.argv[3:])
    elif cmd == "repeat":
        cmd_repeat(sys.argv[2] if len(sys.argv) > 2 else "1")
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
