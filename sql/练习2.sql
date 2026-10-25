-- 练习 1 · 日级指标（2 个查询）
-- 每天的电量（MWh）和日均（MW），按电量降序取前 5。
-- 每天的峰谷差和负荷率（AVG/MAX），按峰谷差降序取前 5。
-- 提示

-- 先 GROUP BY date，再 ORDER BY、LIMIT
-- 电量是 SUM(aep_mw)，不是 AVG
-- 负荷率用除法，注意整数除法问题（AVG 出来是小数，没问题）
-- 这两条用全量行即可：2009-01-16 和 2008-10-20 都是 24 小时的日子，DST 日不影响前 5 名的结论
-- 自查：电量第一 2009-01-16 = 548,349 MWh（日均 22,848）； 峰谷差第一 2008-10-20 = 12,412 MW，负荷率 0.626（第二低 2016-09-05 = 0.758）

SELECT DISTINCT
    date,
    SUM(aep_mw) OVER(
        PARTITION BY date
        ) AS sum_1,
    AVG(aep_mw) OVER(
        PARTITiON BY date
        ) AS avg_1
FROM fact_load 
ORDER BY sum_1 DESC
LIMIT 5;

WITH dailystats AS(
    SELECT DISTINCT
        date,
        MAX (aep_mw) OVER(PARTITION BY date
        ) AS max_1,
        MIN (aep_mw) OVER(PARTITION BY date
        ) AS min_1,
        AVG (aep_mw) OVER(PARTITION BY date
        ) AS avg_1
    FROM fact_load
)
SELECT
    date,
    max_1,
    min_1,
    avg_1,
    max_1 - min_1 AS diff_load,
    avg_1/max_1 AS 电荷率
FROM dailystats
ORDER BY diff_load DESC
LIMIT 5;
    
-- 练习 2 · 7 天移动平均
-- 先写 daily CTE（每天均值，限定 n_hours = 24 AND had_duplicate = 0）。
-- 在 daily 上算 7 天移动平均，输出前 10 行（date、avg_mw、ma7）。
-- 提示

-- AVG(avg_mw) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
-- 第一行为什么是 2004-10-02？想想 CTE 的条件
-- 自查：第一行 2004-10-02 → 12,999.9 / 12,999.9； 第 8 行 2004-10-09 → 12,934.5 / 13,876.4。
WITH daily AS(
    SELECT 
        f.date,
        AVG (f.aep_mw) AS avg_mw
    FROM fact_load f
    JOIN dim_date d ON f.date = d.date
    WHERE d.n_hours = 24 AND d.had_duplicate = 0
    GROUP BY f.date
)
SELECT 
    date,
    avg_mw,
    AVG(avg_mw) OVER(
    ORDER BY date
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    )AS moving_avd_7d
FROM daily
LIMIT 10;

-- 练习 3 · 月度均值 + 环比 + 同比
-- 1.monthly CTE（按年+月聚合）。
-- 2.加 LAG(…,1) 环比、LAG(…,12) 同比，输出前 24 行。
-- 3. 再写一版：先算窗口，外层再 WHERE year >= 2014，看 2014-01 的环比。
-- 提示

-- 同比 = 往前 12 行（一年 12 个月）
-- 第 3 问就是在验证第 3 节的坑
-- 自查：2015-01 → 17,332.1 / 环比 15,685.2 / 同比 18,449.3； 
-- 2015-02 → 18,407.1 / 环比 17,332.1 / 同比 17,398.5； 
-- "先算窗口再过滤"版本里，2014-01 环比 = 16,013.0（2013-12 的均值）。
WITH daily AS(
    SELECT 
        f.date,
        AVG (f.aep_mw) AS avg_mw
    FROM fact_load f
    JOIN dim_date d ON f.date = d.date
    WHERE d.n_hours = 24 AND d.had_duplicate = 0
    GROUP BY f.date
),
monthly AS(
    SELECT 
      d.year,
      d.month,
      AVG(dl.avg_mw) AS monthly_avg_mw
    FROM daily dl
    JOIN dim_date d ON dl.date = d.date
    GROUP BY d.year,d.month
)
SELECT 
    year,
    month,
    monthly_avg_mw,
    LAG(monthly_avg_mw,1) OVER (ORDER BY year,month) AS last_month_mw,
    monthly_avg_mw - LAG(monthly_avg_mw,1) OVER (ORDER BY year,month) AS mom_diff,

    LAG(monthly_avg_mw,12) OVER (ORDER BY year,month) AS last_year_mw,
    monthly_avg_mw - LAG(monthly_avg_mw,12) OVER (ORDER BY year,month) AS yoy_diff
FROM monthly
LIMIT 24;

WITH daily AS(
    SELECT 
        f.date,
        AVG (f.aep_mw) AS avg_mw
    FROM fact_load f
    JOIN dim_date d ON f.date = d.date
    WHERE d.n_hours = 24 AND d.had_duplicate = 0
    GROUP BY f.date
),
monthly AS(
    SELECT 
      d.year,
      d.month,
      AVG(dl.avg_mw) AS monthly_avg_mw
    FROM daily dl
    JOIN dim_date d ON dl.date = d.date
    GROUP BY d.year,d.month
),
monthly_with_lag AS (
    SELECT  
        year,month,
        monthly_avg_mw,
        LAG(monthly_avg_mw,1) OVER (ORDER BY year,month) AS last_month_mw,
        monthly_avg_mw - LAG(monthly_avg_mw,1) OVER (ORDER BY year,month) AS mom_diff
    FROM monthly
)
SELECT  
    year,month,
    monthly_avg_mw,
    last_month_mw,
    mom_diff
FROM monthly_with_lag
WHERE year >= 2014
ORDER BY year,month
LIMIT 12;
