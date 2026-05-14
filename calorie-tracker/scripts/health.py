#!/usr/bin/env python3
"""Apple Health 数据导出

用法：
  python3 health.py today       导出今日数据 JSON
  python3 health.py week        导出本周数据 JSON
  python3 health.py date 2026-05-08  导出指定日期
  python3 health.py csv today   导出 CSV
"""

import csv
import io
import json
import sys

from config import DB_PATH
from database import CalorieDB


def export_csv(period="today"):
    db = CalorieDB()
    if period == "today":
        data = db.health_export("today")
    elif period == "week":
        data = db.health_export("week")
    else:
        data = db.health_export("date", period)

    meals = data.get("meals", [])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["时间", "餐别", "食物", "热量(kcal)", "碳水(g)", "蛋白(g)", "脂肪(g)", "纤维(g)"])

    for m in meals:
        for f in m.get("foods", []):
            writer.writerow([
                m["time"], m.get("meal_type", ""), f.get("name", ""),
                f.get("calories", ""), f.get("carbs_g", ""), f.get("protein_g", ""),
                f.get("fat_g", ""), f.get("fiber_g", ""),
            ])
    print(output.getvalue())


def main():
    if len(sys.argv) < 2:
        print("用法: health.py <command> [args]")
        print("  today         导出今日数据 (JSON)")
        print("  week          导出本周数据 (JSON)")
        print("  date YYYY-MM-DD  导出指定日期")
        print("  csv today     导出今日 CSV")
        print("  csv week      导出本周 CSV")
        print("  csv month     导出近30天 CSV")
        sys.exit(1)

    cmd = sys.argv[1]
    db = CalorieDB()

    if cmd == "csv":
        export_csv(sys.argv[2] if len(sys.argv) > 2 else "today")
    elif cmd == "date":
        result = db.health_export("date", sys.argv[2] if len(sys.argv) > 2 else None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif cmd in ("today", "week"):
        result = db.health_export(cmd)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
