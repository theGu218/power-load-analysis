# 区域电力负荷分析（PJM / AEP）

> 用 PJM 互联电网 AEP 区域的真实小时级负荷数据，走完一条完整的链路：
> **清洗 → SQL 数据底座 → API 服务 → 预测建模**。
>
> 当前进度：**清洗、SQL、API、建模、容器化全链路已完成** —— 三表星型模型、4 个指标视图、
> 6 个 HTTP 接口（含 `/predict`），5 折 RMSE **312.8 MW** 的梯度提升模型，以及可运行的 Docker 镜像。
> 下一步：测试与 CI 收口。

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
├── main.py                  FastAPI 应用：6 个接口（含 /predict）
├── src/train.py             建模：特征、基线、Ridge、GBR、保存模型
├── models/                  模型与指标（power_gb_model.pkl / metrics.json）
├── tests/test_api.py        接口测试（pytest）
├── Dockerfile               容器化：python:3.12-slim + 依赖 + 代码
├── .dockerignore            构建上下文排除项
├── requirements.txt         API 运行依赖
├── AEP_hourly.csv           原始数据（不入库，自行下载）
├── processed/               清洗产物 + SQLite 库（不入库，可由脚本重建）
├── sql/
│   ├── db_build.py          建库：三张表、导入数据、建索引、执行视图
│   ├── query.py             命令行查询工具（执行 SQL 并打印结果）
│   ├── views.sql            指标视图：daily_metrics / monthly_metrics / hourly_profile / season_profile
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
```

也可以在 VS Code 里用 SQLite 扩展打开 `processed/power_load.db`，选中 SQL 直接执行。

已覆盖的查询：

| 文件 | 内容 |
|---|---|
| `sql/练习.sql` | `SELECT/WHERE/ORDER BY/LIMIT`、`GROUP BY/HAVING`、`JOIN`（INNER/LEFT/CROSS/自连接）、子查询、`CASE WHEN` |
| `sql/练习2.sql` | 日级指标、7 天移动平均（`ROWS BETWEEN`）、月度环比与同比（`LAG`）、每年最高月份（`RANK`）、占比（`SUM() OVER`）、CTE 链、连续 3 天高负荷 |
| `sql/views.sql` | 4 个视图：`daily_metrics`、`monthly_metrics`、`hourly_profile`、`season_profile` |

---

## 6. API 服务

```bash
# 在项目根目录启动（main.py 在根目录）
uvicorn main:app --reload
```

打开 `http://127.0.0.1:8000/docs` 可以直接调接口。

| 接口 | 说明 |
|---|---|
| `GET /health` | 服务状态 + 事实表行数 |
| `GET /summary` | 全库概览：行数、日期范围、均值、峰值/谷值及时间（启动时算一次，缓存） |
| `GET /daily?start=&end=` | 按日期区间返回日指标（来自 `daily_metrics` 视图） |
| `GET /anomalies?start=&end=&threshold=` | 区间内负荷超过阈值的小时，默认阈值 20000，必须 > 0 |
| `POST /predict` | 传入 9 个特征（日历 + 滞后），返回预测负荷；模型在启动时加载 |
| `GET /model_info` | 模型类型、5 折 RMSE、特征列表（来自 `models/metrics.json`） |

错误处理：日期格式错 → **422**；`start > end` → **400**；区间无数据 → **404**。

---

## 7. 建模

**任务**：用过去的信息预测下一小时的 `aep_mw`。

**特征**（9 个）

- 日历：`hour`、`weekday`、`month`、`is_weekend`、`season_code`
- 滞后：`lag1`（上一小时）、`lag24`（昨天同时刻）、`lag168`（上周同时刻）、`roll24`（过去 24 小时均值，先 `shift(1)` 再滚动，避免泄漏）

**评估**：`TimeSeriesSplit(5)`，指标 RMSE（MW）。

| 模型 | RMSE 均值 | std |
|---|---|---|
| 常数基线 | 2,644.6 | 93.9 |
| `lag24` 直接预测 | 1,299.7 | 76.3 |
| Ridge（只用日历） | 2,156.3 | 74.1 |
| Ridge（日历 + 滞后） | 508.5 | 21.2 |
| **GBR（100 树，depth=3，subsample=0.7）** | **312.8** | 9.3 |

结论：

1. **滞后特征比日历特征重要得多**：加滞后后误差从 2,156 降到 508（约 4 倍）；
2. 树模型比线性再降约 38%（508 → 313），说明负荷与特征之间有明显非线性；
3. 最终模型比 `lag24` 基线好 76%，比常数基线好 88%。

**产出**

| 文件 | 内容 |
|---|---|
| `src/train.py` | 完整训练流程（可重复跑） |
| `models/power_gb_model.pkl` | 最终模型 + 特征列名（joblib） |
| `models/metrics.json` | 每折 RMSE、均值、标准差、模型参数 |

> 训练完会覆盖 `models/`；仓库里已提供一份训练好的模型。

---

## 8. Docker 运行

```bash
# 构建（首次会装依赖，约 1 分钟）
docker build -t power-load-api .

# 运行（宿主机 8000 → 容器 8000）
docker run --rm -p 8000:8000 power-load-api
```

打开 `http://127.0.0.1:8000/docs` 验证。

- 镜像基于 `python:3.12-slim`，包含代码、SQLite 库和模型（约 1.2 GB）
- `.dockerignore` 排除了原始 CSV、`.git`、`__pycache__` 和文档
- pip 使用清华源，构建不依赖代理

---

## 9. 运行

```bash
pip install pandas numpy pyarrow fastapi uvicorn scikit-learn joblib

# 1) 清洗：CSV → parquet
python data_preprocessing.py

# 2) 建库：parquet → SQLite（同时建视图）
python sql/db_build.py

# 3) 训练模型（从项目根目录运行）
python src/train.py

# 4) 起 API
uvicorn main:app --reload
```

---

## 10. 已知局限

1. 2014–2017 年 4 个夏令时秋季日：源数据有两个 02:00 时间戳，去重保留了第一条，丢了 1 个真实小时。
2. 3 个普通缺失未补，占比 0.02%。
3. 极值只做了人工判断，还没有写成可复用的异常标记规则。
4. API 已包含 `/predict`，但没有限流、缓存和鉴权；生产环境还需要补这些。
5. 模型只做了**单步预测**（用 `lag1` 等特征）；如果改成预测未来 24 小时，特征要重新设计。
6. 模型文件依赖训练时的 sklearn 版本，换环境可能加载失败。

---

## 11. 下一步

1. **CI**：GitHub Actions 跑语法/格式检查；仓库不含数据与模型，接口测试在本地跑
2. **模型继续优化**：LightGBM、更多滚动特征、多步预测
3. **部署**：镜像推到阿里云容器镜像服务，或部署到云主机

---

## 数据说明

原始数据来自 PJM 公开的历史负荷记录（`AEP_hourly.csv`）。数据文件不随仓库分发，
需要自行下载后放到仓库根目录再运行 `python data_preprocessing.py`。
