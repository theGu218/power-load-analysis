"""跑一段 SQL，把结果按表格打印出来。

用法：
    python sql/query.py "SELECT * FROM dim_hour LIMIT 5"
    python sql/query.py -f sql/queries/q01.sql
    python sql/query.py            # 交互：粘贴多行 SQL，Ctrl+Z 回车结束

查得到结果时返回 DataFrame 视图；DDL/DML 会直接执行。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "processed" / "power_load.db"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sql", nargs="?", help="一行 SQL")
    ap.add_argument("-f", "--file", help="从 .sql 文件读")
    args = ap.parse_args()

    if args.file:
        sql = Path(args.file).read_text(encoding="utf-8")
    elif args.sql:
        sql = args.sql
    else:
        print("粘贴 SQL，结束按 Ctrl+Z 再回车：", file=sys.stderr)
        sql = sys.stdin.read()
    sql = sql.strip()
    if not sql:
        sys.exit("没有输入 SQL")

    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        if sql.lstrip().upper().startswith(("SELECT", "WITH", "EXPLAIN")):
            df = pd.read_sql_query(sql, conn)
            if df.empty:
                print("（0 行）")
            else:
                print(df.to_string(index=False))
                print(f"\n共 {len(df)} 行")
        else:
            conn.executescript(sql)
            conn.commit()
            print("已执行（非查询语句）")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
