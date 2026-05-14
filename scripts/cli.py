#!/usr/bin/env python3
"""卡路里追踪 CLI — argparse 子命令入口"""

import argparse
import json
import sys

from database import CalorieDB


def _print(result):
    print(json.dumps(result, ensure_ascii=False))


def cmd_add(db, args):
    data = json.loads(args.json)
    _print(db.add_meal(
        foods=data.get("foods", []),
        meal_type=data.get("meal_type", ""),
        image_desc=data.get("image_desc", ""),
    ))


def cmd_summary(db, args):
    _print(db.summary(args.period or "today"))


def cmd_goal(db, args):
    if args.action == "set":
        _print(db.goal_set(args.value))
    else:
        _print(db.goal_get())


def cmd_macro(db, args):
    if args.action == "set":
        kwargs = {}
        for pair in args.kv:
            if "=" in pair:
                k, v = pair.split("=", 1)
                kwargs[k] = v
        if not kwargs:
            _print({"status": "error", "message": "格式: macro set protein=120 carbs=250"})
        else:
            _print(db.macro_set(**kwargs))
    else:
        _print(db.macro_get())


def cmd_meal(db, args):
    if args.action == "list":
        _print(db.meal_list(args.date or "today"))
    elif args.action == "delete":
        _print(db.meal_delete(args.id))
    elif args.action == "update":
        _print(db.meal_update(args.id, json.loads(args.json)))


def cmd_food(db, args):
    if args.action == "add":
        _print(db.food_add(json.loads(args.json)))
    elif args.action == "search":
        _print(db.food_search(args.keyword))
    elif args.action == "barcode":
        _print(db.food_barcode(args.code))
    elif args.action == "list":
        _print(db.food_list())
    elif args.action == "delete":
        _print(db.food_delete(args.id))
    elif args.action == "update":
        _print(db.food_update(args.id, json.loads(args.json)))


def cmd_weight(db, args):
    if args.action == "add":
        _print(db.weight_add(args.kg, args.note or ""))
    elif args.action == "list":
        _print(db.weight_list(args.days or 30))
    elif args.action == "latest":
        _print(db.weight_latest())


def cmd_repeat(db, args):
    _print(db.repeat(args.n or 1))


def cmd_recent(db, args):
    _print(db.recent_foods(args.limit or 10))


def cmd_delete_last(db, args):
    _print(db.delete_last())


def cmd_foods_lookup(db, args):
    _print(db.foods_lookup(args.keyword))


def cmd_health(db, args):
    _print(db.health_export(args.period or "today"))


def cmd_checkpoint(db, args):
    _print(db.checkpoint())


def cmd_stats(db, args):
    _print(db.stats())


def main():
    parser = argparse.ArgumentParser(prog="calorie-tracker", description="卡路里摄入追踪助手 CLI")
    sub = parser.add_subparsers(dest="command")

    # meal add
    p = sub.add_parser("add", help="添加餐食记录")
    p.add_argument("json", help='JSON: {"foods":[...], "meal_type":"...", "image_desc":"..."}')
    p.set_defaults(func=cmd_add)

    # summary
    p = sub.add_parser("summary", help="查看汇总")
    p.add_argument("period", nargs="?", default="today", help="today|week|yesterday|YYYY-MM-DD")
    p.set_defaults(func=cmd_summary)

    # goal
    p = sub.add_parser("goal", help="热量目标管理")
    sp = p.add_subparsers(dest="action")
    sp_set = sp.add_parser("set", help="设置热量目标")
    sp_set.add_argument("value", type=int, help="目标 kcal 值")
    sp_get = sp.add_parser("get", help="查看热量目标")
    p.set_defaults(func=cmd_goal)

    # macro
    p = sub.add_parser("macro", help="宏量营养素目标管理")
    sp = p.add_subparsers(dest="action")
    sp_set = sp.add_parser("set", help="设置宏量目标")
    sp_set.add_argument("kv", nargs="+", help="key=value 对，如 protein=120 carbs=250")
    sp_get = sp.add_parser("get", help="查看宏量目标")
    p.set_defaults(func=cmd_macro)

    # meal (sub)
    p = sub.add_parser("meal", help="餐食记录管理")
    sp = p.add_subparsers(dest="action")
    sp_list = sp.add_parser("list", help="列出记录")
    sp_list.add_argument("date", nargs="?", default="today", help="today|YYYY-MM-DD")
    sp_del = sp.add_parser("delete", help="删除记录")
    sp_del.add_argument("id", type=int, help="记录 ID")
    sp_upd = sp.add_parser("update", help="更新记录")
    sp_upd.add_argument("id", type=int, help="记录 ID")
    sp_upd.add_argument("json", help="JSON 更新字段")
    p.set_defaults(func=cmd_meal)

    # food
    p = sub.add_parser("food", help="自定义食物管理")
    sp = p.add_subparsers(dest="action")
    sp_add = sp.add_parser("add", help="录入食物")
    sp_add.add_argument("json", help="JSON 食物数据")
    sp_search = sp.add_parser("search", help="搜索食物")
    sp_search.add_argument("keyword", help="搜索关键词")
    sp_bc = sp.add_parser("barcode", help="按条码查询")
    sp_bc.add_argument("code", help="条码数字")
    sp_list = sp.add_parser("list", help="列出所有")
    sp_del = sp.add_parser("delete", help="删除食物")
    sp_del.add_argument("id", type=int, help="食物 ID")
    sp_upd = sp.add_parser("update", help="更新食物")
    sp_upd.add_argument("id", type=int, help="食物 ID")
    sp_upd.add_argument("json", help="JSON 更新字段")
    p.set_defaults(func=cmd_food)

    # weight
    p = sub.add_parser("weight", help="体重记录管理")
    sp = p.add_subparsers(dest="action")
    sp_add = sp.add_parser("add", help="记录体重")
    sp_add.add_argument("kg", type=float, help="体重 (kg)")
    sp_add.add_argument("note", nargs="?", default="", help="备注")
    sp_list = sp.add_parser("list", help="查看历史")
    sp_list.add_argument("days", nargs="?", type=int, default=30, help="天数")
    sp_latest = sp.add_parser("latest", help="最新体重")
    p.set_defaults(func=cmd_weight)

    # repeat
    p = sub.add_parser("repeat", help="复刻最近记录")
    p.add_argument("n", nargs="?", type=int, default=1, help="最近第N条")
    p.set_defaults(func=cmd_repeat)

    # recent
    p = sub.add_parser("recent", help="最近常吃食物")
    p.add_argument("limit", nargs="?", type=int, default=10, help="条数限制")
    p.set_defaults(func=cmd_recent)

    # delete last
    p = sub.add_parser("delete-last", help="删除最后一条记录")
    p.set_defaults(func=cmd_delete_last)

    # foods lookup (CSV)
    p = sub.add_parser("lookup", help="在 foods.csv 中搜索食物参考数据")
    p.add_argument("keyword", help="搜索关键词")
    p.set_defaults(func=cmd_foods_lookup)

    # health export
    p = sub.add_parser("health", help="导出健康数据")
    p.add_argument("period", nargs="?", default="today", help="today|week|date YYYY-MM-DD")
    p.set_defaults(func=cmd_health)

    # maintenance
    p = sub.add_parser("checkpoint", help="WAL checkpoint")
    p.set_defaults(func=cmd_checkpoint)

    p = sub.add_parser("stats", help="数据库统计")
    p.set_defaults(func=cmd_stats)

    # parse
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    db = CalorieDB()
    try:
        args.func(db, args)
    except ValueError as e:
        _print({"status": "error", "message": str(e)})
    except json.JSONDecodeError as e:
        _print({"status": "error", "message": f"JSON 解析错误: {e}"})


if __name__ == "__main__":
    main()
