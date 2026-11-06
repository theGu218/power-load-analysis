-- 常用指标视图：建模和 API 的取数入口
DROP VIEW IF EXISTS daily_metrics;
CREATE VIEW daily_metrics AS
SELECT 
    d.date,
    AVG(f.aep_mw) AS avg_mw,
    MIN(f.aep_mw) AS valley_mw,
    MAX(f.aep_mw) AS peak_mw,
    MAX(f.aep_mw)-MIN(f.aep_mw) AS span_mw,
    AVG(f.aep_mw)*1.0 / MAX(f.aep_mw) AS load_factor,
    CASE WHEN d.n_hours = 24 AND d.had_duplicate = 0 THEN 1
    ELSE 0 END AS is_complete
FROM dim_date d
LEFT JOIN fact_load f ON d.date = f.date
group by d.date,d.n_hours,had_duplicate;





DROP VIEW IF EXISTS monthly_metrics;
CREATE VIEW monthly_metrics AS
WITH daily as (
    SELECT 
        f.date,
        AVG(f.aep_mw) as avg_mw
    from fact_load f
    join dim_date d on f.date = d.date
    where d.n_hours =24 and d.had_duplicate = 0
    group by f.date
),
monthly as (
    select 
        d.year,
        d.month,
        avg(dl.avg_mw) as avg_mw
    from daily dl
    join dim_date d on dl.date = d.date
    group by d.year,d.month
)
select 
    year,
    month,
    avg_mw,
    avg_mw - lag(avg_mw,1)over(order by year,month) as mom_diff,
    avg_mw - lag(avg_mw,12)over(order by year,month) as yoy_diff
from monthly;


DROP VIEW IF EXISTS hourly_profile;
CREATE VIEW hourly_profile AS
select
    hour,
    avg(aep_mw) as avg_mw,
    max(aep_mw) as peak_mw,
    min(aep_mw) as valley_mw
from fact_load
group by hour;

DROP VIEW IF EXISTS season_profile;
CREATE VIEW season_profile AS
select 
    d.season,
    avg(f.aep_mw) as avg_mw,
    max(f.aep_mw) as peak_mw,
    avg(f.aep_mw)*1.0 / max(f.aep_mw) as load_factor
from dim_date d
join fact_load f on d.date = f.date
where d.n_hours = 24 and d.had_duplicate = 0
group by d.season;