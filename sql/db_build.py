import pandas as pd
import sqlite3
cx = sqlite3.connect('processed/power_load.db')
cx.execute("PRAGMA foreign_keys = ON")
"""
SQLite 为什么默认不强制外键？
SQLite 是先有表、后加的外键功能。
如果新版本默认强制开启，会导致大量旧数据库和旧代码因为历史脏数据突然报错崩溃。
"""
cx.execute("""
    CREATE TABLE dim_date(
    date TEXT PRIMARY KEY,
    year INTEGER,
    quarter INTEGER,
    month INTEGER,
    day INTEGER,
    weekday INTEGER,
    is_weekend INTEGER CHECK(is_weekend IN (0,1)),
    season TEXT,
    n_hours INTEGER,
    had_duplicate INTEGER
   
    );
""")
cx.execute("""
    CREATE TABLE dim_hour(
    hour INTEGER PRIMARY KEY,
    period TEXT CHECK(period IN ('谷','平','峰')),
    period_rank INTEGER
    );
""")
cx.execute("""
    CREATE TABLE fact_load(
    dt TEXT PRIMARY KEY,
    date TEXT,
    hour INTEGER,
    aep_mw REAL CHECK (aep_mw > 0),
    FOREIGN KEY (date) REFERENCES dim_date(date),
    FOREIGN KEY (hour) REFERENCES dim_hour(hour)
    );
""")

df_dim = pd.read_parquet('processed/dim_date.parquet')
df_fact = pd.read_parquet('processed/fact_load.parquet')
# 确保 dt 列是 datetime 格式，然后提取出 hour
df_fact['dt'] = pd.to_datetime(df_fact['dt'])
df_fact['hour'] = df_fact['dt'].dt.hour
hourly_mean = df_fact.groupby('hour')['aep_mw'].mean().reset_index()
hourly_mean['period'] = pd.qcut(hourly_mean['aep_mw'],q = 3,labels = ['谷','平','峰'])
rank_map = {'谷':1,'平':2,'峰':3}
hourly_mean['period_rank'] = hourly_mean['period'].map(rank_map)
df_hour = hourly_mean[['hour','period','period_rank']].copy()

df_fact['date'] = df_fact['dt'].dt.strftime('%Y-%m-%d')
print(df_hour)
df_fact['dt'] = df_fact['dt'].astype(str)
df_fact['date'] = df_fact['date'].astype(str)
df_dim['date'] = df_dim['date'].astype(str)

cursor = cx.cursor()
# 1. 插入 dim_hour
rows_hour = df_hour[['hour', 'period', 'period_rank']].values.tolist()
sql_hour = "INSERT INTO dim_hour (hour, period, period_rank) VALUES (?, ?, ?)"
cursor.executemany(sql_hour, rows_hour)
print(f"dim_hour 插入 {cursor.rowcount} 行")

# 2. 插入 dim_date (注意列的顺序必须和建表语句一模一样！)
rows_dim = df_dim[['date', 'year', 'quarter', 'month', 'day', 'weekday', 'is_weekend', 'season', 'n_hours', 'had_duplicate']].values.tolist()
sql_dim = "INSERT INTO dim_date (date, year, quarter, month, day, weekday, is_weekend, season, n_hours, had_duplicate) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
cursor.executemany(sql_dim, rows_dim)
print(f"dim_date 插入 {cursor.rowcount} 行")

# 3. 插入 fact_load
rows_fact = df_fact[['dt', 'date', 'hour', 'aep_mw']].values.tolist()
sql_fact = "INSERT INTO fact_load (dt, date, hour, aep_mw) VALUES (?, ?, ?, ?)"
cursor.executemany(sql_fact, rows_fact)
print(f"fact_load 插入 {cursor.rowcount} 行")

# 4. 提交事务（必须写，不然全白干）
cx.commit()
# 建索引
cursor.execute("CREATE INDEX idx_fact_date ON fact_load(date);")
cursor.execute("CREATE INDEX idx_fact_hour ON fact_load(hour);")
cursor.execute("CREATE INDEX idx_fact_date_hour ON fact_load(date, hour);")
print("索引建立成功！")

# 验收：查行数
cursor.execute("SELECT COUNT(*) FROM dim_hour")
print("dim_hour 总行数:", cursor.fetchone()[0])
cursor.execute("SELECT COUNT(*) FROM dim_date")
print("dim_date 总行数:", cursor.fetchone()[0])
cursor.execute("SELECT COUNT(*) FROM fact_load")
print("fact_load 总行数:", cursor.fetchone()[0])

# 验收：查外键有没有挂掉
cursor.execute("PRAGMA foreign_key_check")
print("外键检查结果(应为空[]):", cursor.fetchall())

cx.close()

