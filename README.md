# 区域电力负荷分析（PJM / AEP）

> 用 PJM 互联电网 AEP 区域的真实小时级负荷数据，走完一条完整的链路：
> **清洗 → SQL 数据底座 → 预测建模 → API 服务**。
>
> 当前进度：**数据清洗与 SQL 数据底座已完成** —— 建库（三表星型模型）、基础查询、
> 窗口函数指标（日级指标 / 移动平均 / 环比同比 / 排名 / 占比 / CTE 链 / 日指标表）。

---

## 1. 数据

| 项 | 情况 |
|---|---|
| 来源 | PJM Interconnection，AEP 区域历史负荷（公开数据） |
| 范围 | 2004-10-01 01:00 ~ 2018-08-03 00:00，约 13.8 年 |
| 粒度 | 小时级 |
| 规模 | 121,273 行 × 2 列（`Datetime`, `AEP_MW`） |
| 单位 | `AEP_MW` 是兆瓦（MW），不是 MWh |
| 排序 | **原始文件未按时间排序**，首尾行不等于真实起止 |

原始文件放在仓库根目录 `AEP_hourly.csv`，体积 3.4 MB，**不入库**（见 `.gitignore`）。

---

## 2. 目录结构

```
.
├── data_preprocessing.py    数据清洗：CSV → 两张 parquet
├── AEP_hourly.csv           原始数据（不入库，自行下载）
├── processed/               清洗产物 + SQLite 库（不入库，可由脚本重建）
├── sql/
│   ├── db_build.py          建库：三张表、导入数据、建索引
│   ├── query.py             命令行查询工具（执行 SQL 并打印结果）
│   ├── 练习.sql              基础查询：筛选、聚合、JOIN、子查询、CASE
│   └── 练习2.sql             窗口函数指标：日级指标、移动平均、环比/同比
├── 数据处理记录.md           清洗过程、判断依据、最终结果
└── .gitignore
```

清空 `processed/` 后，依次跑 `python data_preprocessing.py` 和 `python sql/db_build.py` 即可完全重建。

---

## 3. 清洗结论（核心数字）

| 项 | 结果 |
|---|---|
| 去重前 | 121,273 行，唯一时间戳 121,269 个 |
| 重复时间戳 | **4 条**，全部落在美国夏令时"回拨"日（2014–2017 年 11 月），同一本地时钟对应两个真实小时 |
| 去重后 | **121,269 行**（`keep='first'`，损失 0.0033%） |
| 采样缺口 | **27 个 2 小时间隔** = 27 个缺失整点：其中 **24 个在夏令时切换日**，3 个为普通缺失 |
| 缺失处理 | **不插值**。DST 日不是缺数据：春季那天真实只有 23 小时，秋季那天真实是 25 小时；插值会造出不存在的小时，反而让日电量偏 ±4% |
| 极值处理 | **不删除**。最大值 25,695 MW（2008-10-20 14:00，单点跳升约 9,300 MW，疑似采集异常）；最小值 9,581 MW（2016-10-02 05:00，连续低负荷，真实事件） |
| 最终行数 | **121,269**（28 天只有 23 行：24 个 DST 日 + 3 个普通缺口 + 首日 2004-10-01；末日 2018-08-03 只有 1 行） |

完整过程与判断依据见 [`数据处理记录.md`](数据处理记录.md)。

---

## 4. 产出

### 4.1 parquet

| 文件 | 形状 | 列 |
|---|---|---|
| `processed/fact_load.parquet` | 121,269 × 2 | `dt`, `aep_mw` |
| `processed/dim_date.parquet` | 121,269 × 9 | `dt`, `date`, `year`, `month`, `hour`, `weekday`, `is_weekend`, `n_hours`, `had_duplicate` |

### 4.2 SQLite 星型模型（`processed/power_load.db`）

| 表 | 行数 | 说明 |
|---|---|---|
| `dim_date` | 5,055 | 一天一行：年/季/月/日/星期/季节/`n_hours`/`had_duplicate` |
| `dim_hour` | 24 | 一小时一行：`period`（谷/平/峰）与 `period_rank`，按各小时平均负荷三分位划分 |
| `fact_load` | 121,269 | 一小时一行：`dt`、`date`、`hour`、`aep_mw`（MW） |

- `fact_load.date` 与 `fact_load.hour` 分别有外键指向两张维度表；
- 日级比较的口径：**`n_hours = 24 AND had_duplicate = 0`**；
- 索引：`fact_load(date)`、`fact_load(hour)`、`fact_load(date, hour)`。

> `processed/power_load.db` 不入库，由 `sql/db_build.py` 从 parquet 重建。

---

## 5. SQL 查询

```bash
# 建库（可重复跑，先删表再重建）
python sql/db_build.py

# 查一条
python sql/query.py "SELECT COUNT(*) FROM fact_load"

# 跑文件里保存的单条语句（多语句请一次拆一条，或用 VS Code 插件执行）
python sql/query.py -f sql/练习.sql
```

也可以在 VS Code 里用 SQLite 扩展打开 `processed/power_load.db`，选中 SQL 直接执行。

已覆盖的查询：

| 文件 | 内容 |
|---|---|
| `sql/练习.sql` | `SELECT/WHERE/ORDER BY/LIMIT`、`GROUP BY/HAVING`、`JOIN`（INNER/LEFT/CROSS/自连接）、子查询、`CASE WHEN` |
| `sql/练习2.sql` | 日级指标（电量/日均/峰谷差/负荷率）、7 天移动平均（`ROWS BETWEEN`）、月度环比与同比（`LAG`）、每年最高月份（`RANK`）、每月占全年比例（`SUM() OVER`）、CTE 链、连续 3 天高负荷、2018-07 日指标表 |

---

## 6. 运行

```bash
pip install pandas numpy pyarrow

# 1) 清洗：CSV → parquet
python data_preprocessing.py

# 2) 建库：parquet → SQLite
python sql/db_build.py

# 3) 查询
python sql/query.py "SELECT * FROM dim_hour LIMIT 5"
```

`data_preprocessing.py` 会打印行数、每天行数分布和空值检查；
`db_build.py` 会打印三张表行数与外键检查结果。

---

## 7. 已知局限

1. 2014–2017 年 4 个夏令时秋季日：源数据有两个 02:00 时间戳，去重保留了第一条，丢了 1 个真实小时；要严格保留需要带时区转 UTC。
2. 3 个普通缺失（2010-12-10 00:00、2012-12-06 04:00、2014-03-11 14:00）未补，占比 0.02%。
3. 极值只做了人工判断，还没有写成可复用的异常标记规则。
4. SQL 指标目前是手写查询，还没有接成自动化报表/视图。
5. 尚无模型（预测）与 API。

---

## 8. 下一步

1. **建模**：按 `TimeSeriesSplit` 做逐小时负荷预测
2. **服务化**：FastAPI 暴露预测与日指标接口，Docker 打包

---

## 数据说明

原始数据来自 PJM 公开的历史负荷记录（`AEP_hourly.csv`）。数据文件不随仓库分发，
需要自行下载后放到仓库根目录再运行 `python data_preprocessing.py`。
