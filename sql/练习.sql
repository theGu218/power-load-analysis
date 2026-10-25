--2008-10-20 全天的负荷，按小时升序。先猜几行。---24行
SELECT dt,hour,aep_mw
FROM fact_load
WHERE date = '2008-10-20'
ORDER BY hour ASC;
--全库负荷最高的 10 个小时（dt、aep_mw）
SELECT dt,aep_mw
FROM fact_load
ORDER BY aep_mw DESC
LIMIT 10;
--2.3 2016-10-02 04:00 ~ 07:00 这四行。
SELECT dt,aep_mw
FROM fact_load
WHERE dt BETWEEN '2016-10-02 04:00' AND '2016-10-02 07:00';
--2.4 2018 年 7 月的平均负荷和最大负荷。 
SELECT AVG(aep_mw) AS avg_load,MAX(aep_mw) AS max_load
FROM fact_load
WHERE date LIKE '2018-07%';
--2.5 负荷超过 25,000 MW 的小时数。
SELECT COUNT(*) AS sum_load
FROM fact_load
WHERE aep_mw > 25000;
/*
3.1 每年的平均负荷 + 行数，按年升序。 
3.2 按"日历月"（1~12，跨年合并）的平均负荷。
3.3 一天 24 小时的平均负荷，降序。 
3.4 工作日 vs 周末的平均负荷 + 行数。 
3.5 平均负荷高于全库均值的年份。
*/
SELECT 
    d.year,
    AVG(f.aep_mw) AS avg_load,
    COUNT(*) AS row_count
FROM fact_load f
JOIN dim_date d ON f.date = d.date
GROUP BY d.year
ORDER BY d.year ASC; 

SELECT 
    d.month,
    AVG(f.aep_mw) AS avg_load,
    COUNT(*) AS row_count
FROM fact_load f
JOIN dim_date d ON f.date = d.date
GROUP BY d.month
ORDER BY d.month ASC;

SELECT 
    hour,
    AVG(aep_mw) AS avg_load,
    COUNT(*) AS row_count
FROM fact_load 
GROUP BY hour
ORDER BY avg_load DESC;

SELECT 
    CASE WHEN d.is_weekend = 1 
    THEN 'weekend'
    ELSE 'weekday' 
    END 
    AS day_type,
    AVG(f.aep_mw) AS avg_load,
    COUNT(*) AS row_count
FROM fact_load f
JOIN dim_date d ON f.date = d.date 
GROUP BY day_type;

SELECT 
    d.year,
    AVG(f.aep_mw) AS avg_load
FROM fact_load f
JOIN dim_date d ON f.date = d.date
GROUP BY d.year
HAVING AVG(f.aep_mw) > (SELECT AVG(aep_mw) FROM fact_load);
/*
4.1 fact_load JOIN dim_date，按季节算平均负荷 + 行数。 
4.2 fact_load JOIN dim_hour，按峰/平/谷算平均负荷 + 行数。 
4.3 LEFT JOIN 检查：dim_date.n_hours 和事实表实际行数是否一致，返回不一致的天数。 
4.4 自连接：找"下一个小时比当前高 2,000 MW 以上"的地方，按涨幅降序。 
4.5 CROSS JOIN 造完整网格，LEFT JOIN 事实表，数出缺多少"日期×小时"。
*/
SELECT 
    d.season,
    AVG(f.aep_mw) AS avg_load,
    COUNT(*) AS row_load
FROM fact_load f
JOIN dim_date d ON f.date = d.date
GROUP BY d.season;

SELECT 
    d.period,
    AVG(f.aep_mw) AS avg_load,
    COUNT(*) AS row_load
FROM fact_load f
JOIN dim_hour d ON f.hour = d.hour
GROUP BY d.period;

SELECT COUNT(*) AS missmatch_days
FROM dim_date d
LEFT JOIN (
    SELECT date,COUNT(*) AS actual_hours
    FROM fact_load
    GROUP BY date
)f ON d.date = f.date
WHERE d.n_hours != f.actual_hours OR f.actual_hours IS NULL;

SELECT 
    a.dt AS current_dt,
    a.aep_mw AS current_load,
    b.aep_mw AS next_load,
    (b.aep_mw - a.aep_mw) AS load_diff
FROM fact_load a
JOIN fact_load b ON b.dt = datetime(a.dt,'+1 hour')
WHERE (b.aep_mw - a.aep_mw) > 2000
ORDER BY load_diff DESC;

WITH complete_grid AS(
    SELECT d.date,h.hour
    FROM dim_date d
    CROSS JOIN dim_hour h
)
SELECT COUNT(*) AS missing_count
FROM complete_grid g
LEFT JOIN fact_load f
    ON g.date = f.date AND g.hour = f.hour
WHERE f.dt IS NULL;

/*
5.1 用 CASE WHEN 把 weekday 0~6 映射成中文（周一到周日，去重）。
5.2 负荷分三档：<13,000 低 / 13,000~17,000 中 / >17,000 高，统计各档小时数。
5.3 比全库均值高出最多的小时（dt、aep_mw、差值），降序取 5。 
5.4 相关子查询：2016 年 8 月里负荷最高的那一小时。
*/

SELECT DISTINCT weekday,
    CASE WHEN weekday = 0 THEN '周一'
    WHEN weekday = 1 THEN '周二'
    WHEN weekday = 2 THEN '周三'
    WHEN weekday = 3 THEN '周四'
    WHEN weekday = 4 THEN '周五'
    WHEN weekday = 5 THEN '周六'
    ELSE '周日' END AS 日期
FROM dim_date
ORDER BY weekday;

SELECT 
    CASE WHEN aep_mw < 13000 THEN '低'
    WHEN aep_mw >= 13000 AND aep_mw <= 17000 THEN '中'
    ELSE '高'END AS level_load,
    COUNT(*) AS hour_count
FROM fact_load
GROUP BY    
    CASE 
    WHEN aep_mw < 13000 THEN '低'
    WHEN aep_mw >= 13000 AND aep_mw <= 17000 THEN '中'
    ELSE '高'
END;

SELECT 
    dt,
    aep_mw,
    aep_mw - (SELECT AVG(aep_mw) FROM fact_load) AS 差值
FROM fact_load 
ORDER BY 差值 DESC
LIMIT 5;

SELECT
    dt,
    aep_mw,
    MAX(aep_mw) AS max
FROM fact_load 
WHERE date LIKE '2016-08%'
    AND aep_mw = (
        SELECT MAX(aep_mw)
        FROM fact_load
        WHERE date LIKE '2016-08%'
    );



