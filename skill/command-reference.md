# 命令速查表

所有命令通过 `python3 scripts/cli.py <command>` 执行，返回 JSON。

## 餐食记录

| 用户说 | CLI 命令 |
|--------|---------|
| "今天吃了多少" / "今日汇总" | `cli.py summary today` |
| "本周汇总" | `cli.py summary week` |
| "昨天吃了什么" | `cli.py summary yesterday` |
| "列出今天记录" | `cli.py meal list today` |
| "列出5月8日" | `cli.py meal list 2026-05-08` |
| 添加一餐（AI 构造 JSON） | `cli.py add '<json>'` |
| "删掉 #3" | `cli.py meal delete 3`（需确认） |
| "把 #3 的米饭改成150g" | `cli.py meal update 3 '<json>'` |
| "删除最后一条" | `cli.py delete-last` |
| "老样子" / "再来一份" | `cli.py repeat 1` |
| "复刻午餐" | `cli.py repeat 2` |
| "最近常吃什么" | `cli.py recent 10` |

## 宏量目标

| 用户说 | CLI 命令 |
|--------|---------|
| "设置热量目标 2000" | `cli.py goal set 2000` |
| "查看热量目标" | `cli.py goal get` |
| "设置蛋白目标120g" | `cli.py macro set protein=120` |
| "设置碳水250g 脂肪60g" | `cli.py macro set carbs=250 fat=60` |
| "设置脂肪60g 纤维25g" | `cli.py macro set fat=60 fiber=25` |
| "查看所有营养目标" | `cli.py macro get` |

## 自定义食物

| 用户说 | CLI 命令 |
|--------|---------|
| 录入食物（AI 构造 JSON） | `cli.py food add '<json>'` |
| "搜索 燕麦" | `cli.py food search 燕麦` |
| "扫条码 6901234567890" | `cli.py food barcode 6901234567890` |
| "查看我的食物库" | `cli.py food list` |
| "删除食物 1" | `cli.py food delete 1` |
| 更新食物 | `cli.py food update 1 '<json>'` |

### food add JSON 格式

```json
{
  "name": "XX燕麦奶",
  "barcode": "6901234567890",
  "brand": "XX品牌",
  "serving_size_g": 250,
  "serving_desc": "1盒",
  "calories_per_100g": 55,
  "carbs_per_100g": 6.5,
  "protein_per_100g": 1.0,
  "fat_per_100g": 2.0,
  "fiber_per_100g": 1.2
}
```

## 食物参考库查询

| 用户说 | CLI 命令 |
|--------|---------|
| "米饭热量多少" | `cli.py lookup 米饭` |
| "查询 鸡胸肉" | `cli.py lookup 鸡胸肉` |

## 体重管理

| 用户说 | CLI 命令 |
|--------|---------|
| "体重 65.5" | `cli.py weight add 65.5` |
| "记录体重66.2" | `cli.py weight add 66.2` |
| "查看体重" | `cli.py weight latest` |
| "近7天体重变化" | `cli.py weight list 7` |

## 导出

| 用户说 | CLI 命令 |
|--------|---------|
| "导出今天数据" | `cli.py health today` |
| "导出本周数据" | `cli.py health week` |
| 导出 CSV | `python3 scripts/health.py csv today` |

## 维护

| 命令 | 说明 |
|------|------|
| `cli.py stats` | 查看数据库统计 |
| `cli.py checkpoint` | 执行 WAL checkpoint |
