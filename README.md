# Calorie Tracker — OpenClaw Skill

创建日期：2026-05-08 | 重构日期：2026-05-14

> 基于 OpenClaw 框架的飞书卡路里摄入追踪技能。用户通过飞书发图片/语音/文字，AI 自动识别食物并返回营养数据（热量、碳水、蛋白、脂肪、纤维），支持条码扫描、营养表录入、体重记录、Apple Health 导出。

---

## 文件结构

```
calorie-tracker/
├── SKILL.md                        # 技能核心定义（精简，86行）
├── README.md                       # 项目说明
├── skill/
│   ├── output-format.md            # 输出格式规范
│   ├── nutrition-estimation.md     # 营养估算参考
│   └── command-reference.md        # 完整命令速查表
├── scripts/
│   ├── config.py                   # 统一配置（环境变量优先）
│   ├── database.py                 # SQLite 数据访问层（CalorieDB 类）
│   ├── cli.py                      # argparse CLI 入口
│   ├── db.py                       # [旧版] 待废弃
│   └── health.py                   # Apple Health JSON/CSV 导出
├── data/
│   └── foods.csv                   # 中国食物成分参考表（200+ 食物）
└── tests/
```

## 配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `CALORIE_TRACKER_DATA_DIR` | `~/.openclaw/data/calorie-tracker` | 数据存储目录 |
| `CALORIE_TRACKER_DB_PATH` | `<DATA_DIR>/calories.db` | 数据库路径 |

## 数据库表

| 表名 | 用途 |
|------|------|
| `meals` | 餐食记录（多食物 JSON、各营养素合计） |
| `goals` | 热量目标（向后兼容） |
| `custom_foods` | 自定义食物库（条码+100g 营养数据） |
| `macro_goals` | 宏量营养素目标（蛋白/碳水/脂肪/纤维） |
| `weight_records` | 体重记录 |

## CLI 接口

```
python3 scripts/cli.py add '<json>'              添加餐食记录
python3 scripts/cli.py summary [period]          查看汇总
python3 scripts/cli.py goal set|get              热量目标管理
python3 scripts/cli.py macro set|get              宏量目标管理
python3 scripts/cli.py meal list|delete|update    餐食记录管理
python3 scripts/cli.py food add|search|barcode|list|delete|update  自定义食物
python3 scripts/cli.py lookup <keyword>           搜索 foods.csv 参考数据
python3 scripts/cli.py weight add|list|latest     体重记录
python3 scripts/cli.py repeat [n]                 复刻最近记录
python3 scripts/cli.py delete-last                删除最后一条
python3 scripts/cli.py recent [limit]             最近常吃食物
python3 scripts/cli.py health [period]            健康数据导出
python3 scripts/cli.py stats                      数据库统计
python3 scripts/cli.py checkpoint                 WAL checkpoint
```

## 导出

```
python3 scripts/health.py today              导出今日 JSON
python3 scripts/health.py csv today          导出今日 CSV
```

## 图片识别类型

| 图片特征 | 处理方式 |
|----------|----------|
| 条码（黑条+数字） | 识别条码号 → 查本地库 → 查不到引导录入 |
| 营养成分表表格 | Vision 读取每100g数据 → 确认 → 入库 |
| 完整餐食照片 | 识别食物 → lookup CSV参考 → food search 查自定义库 → 大模型估算 |
| 外卖订单截图 | 提取菜品列表 → 批量估算（油量+30-50%） |
| 体重秤屏幕 | 读取数字 → 记录体重 → 显示趋势 |

## 数据优先级

自定义食物库（精确） → foods.csv 参考表 → 大模型知识估算（兜底）
