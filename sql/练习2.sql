-- 练习 1 · 日级指标（2 个查询）
-- 每天的电量（MWh）和日均（MW），按电量降序取前 5。
-- 每天的峰谷差和负荷率（AVG/MAX），按峰谷差降序取前 5。
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
    avg_1/max_1 AS 负荷率
FROM dailystats
ORDER BY diff_load DESC
LIMIT 5;
    
-- 练习 2 · 7 天移动平均
-- 先写 daily CTE（每天均值，限定 n_hours = 24 AND had_duplicate = 0）。
-- 在 daily 上算 7 天移动平均，输出前 10 行（date、avg_mw、ma7）。

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
    )AS moving_avg_7d
FROM daily
ORDER BY date
LIMIT 10;

-- 练习 3 · 月度均值 + 环比 + 同比
-- 1.monthly CTE（按年+月聚合）。
-- 2.加 LAG(…,1) 环比、LAG(…,12) 同比，输出前 24 行。
-- 3. 再写一版：先算窗口，外层再 WHERE year >= 2014，看 2014-01 的环比。

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
ORDER BY year,month
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

-- 练习 4 · 排名：每年负荷最高的月份
-- 1.在 monthly 上算 RANK() 和 DENSE_RANK()（PARTITION BY year ORDER BY avg_mw DESC）。
-- 2.只取每年第 1 名，列出 15 年。


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
monthly_ranked AS(
    SELECT 
        year,
        month,
        monthly_avg_mw,
        RANK() OVER (PARTITION BY year ORDER BY monthly_avg_mw DESC) AS rank_year,
        DENSE_RANK() OVER (PARTITION BY year ORDER BY monthly_avg_mw DESC) AS dense_rank_year
    FROM monthly
)
SELECT * FROM monthly_ranked
WHERE rank_year = 1 AND dense_rank_year = 1
ORDER BY year
LIMIT 15;

-- 练习 5 · 占比
-- 在 monthly 上算 2017 年每月占全年 12 个月合计的比例（%）。

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
      SUM(dl.avg_mw) AS monthly_avg_mw,
      SUM(SUM(dl.avg_mw))OVER (partition by d.year) AS sum_avg_mw 
    FROM daily dl
    JOIN dim_date d ON dl.date = d.date
    GROUP BY d.year,d.month
)

SELECT 
    year,
    month,
    round(100.0*monthly_avg_mw/sum_avg_mw ,1)as rate_avg_mw
FROM monthly
where year = 2017
ORDER BY month;

-- 练习 6 · CTE 链：日 → 月 → 同比
-- 三个 CTE：daily（限定 24 小时日）→ monthly → 加同比并算差值。
-- 取同比降幅最大的 5 个月。
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
    GROUP BY d.year, d.month
),
monthly_lag as(
    select 
        year,
        month,
        monthly_avg_mw,
        LAG(monthly_avg_mw,12) over (order by year,month) as lag_avg_mw,
        monthly_avg_mw - LAG(monthly_avg_mw,12) over (order by year,month) as yoy_avg_mw
    from monthly
)
select*from monthly_lag
WHERE yoy_avg_mw IS NOT NULL 
order by yoy_avg_mw asc
limit 5;

-- 练习 7 · 滑动窗口找"连续 3 天高负荷"
-- daily 上算 3 天移动平均。
-- 找 ma3 > 16500 的日期，按日期升序取前 8。
WITH daily AS(
    SELECT 
        f.date,
        AVG (f.aep_mw) AS avg_mw
    FROM fact_load f
    JOIN dim_date d ON f.date = d.date
    WHERE d.n_hours = 24 AND d.had_duplicate = 0
    GROUP BY f.date
),
ma3 AS (
SELECT 
    date,
    avg_mw,
    AVG(avg_mw) OVER (
            order by date
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS d3
FROM daily
)
SELECT * from ma3
WHERE d3 > 16500
ORDER BY date ASC
LIMIT 8;


-- 练习 8 · 综合：2018 年 7 月的日指标表
-- 输出 date, avg_mw, peak_mw, valley_mw, span_mw, load_factor 六列，
-- 按日期排序。
WITH daily AS (
    select 
        f.date,
        AVG(f.aep_mw) as avg_mw,
        MIN(f.aep_mw) as valley_mw,
        MAX(f.aep_mw) as peak_mw
    FROM fact_load f
    
    JOIN dim_date d ON f.date = d.date
    WHERE d.n_hours = 24 AND d.had_duplicate = 0
    GROUP BY f.date
)
SELECT 
    date,
    avg_mw,
    peak_mw,
    valley_mw,
    peak_mw - valley_mw as span_mw,
    avg_mw/peak_mw as load_factor
FROM daily
WHERE date like '2018-07%'
ORDER BY date ASC;



SELECT 
    f.date,
    round(AVG(f.aep_mw),2) as avg_mw,
    MIN(f.aep_mw) as valley_mw,
    MAX(f.aep_mw) as peak_mw,
    MAX(f.aep_mw) - MIN(f.aep_mw) as span_mw,
    AVG(f.aep_mw) / MAX(f.aep_mw) as load_factor
FROM fact_load f
JOIN dim_date d ON f.date = d.date
WHERE d.n_hours = 24 and d.had_duplicate = 0
    AND d.date like '2018-07%'
GROUP BY d.date
ORDER BY d.date ASC;

