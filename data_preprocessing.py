import numpy as np
import pandas as pd

df = pd.read_csv('data/raw/AEP_hourly.csv')
print('shape的值为:',df.shape)
print(df.dtypes)
print(df.head())
print(df.tail())

'''
shape 是多少？
1.(121273,2)
Datetime 的 dtype 是什么？ 是 datetime64 还是 object？想想为什么。
object
head(3) 的第一行时间和 tail(3) 的最后一行时间，跟"数据的真实时间范围"一致吗？
不一致，因为显示的时间是从1.00到0.00，说明这就不是按时间顺序排列的
这一问是本步第一个陷阱：df.head() 看着像开头，df.tail() 看着像结尾 —— 但它们都不是。先别急着信。
'''


#先看一眼排序前的 diff()：

df['dt'] = pd.to_datetime(df['Datetime'])
print('\n排序之前：',df['dt'].is_monotonic_increasing)            
print('排序之前：',
      df['dt'].diff().dt.total_seconds().div(3600).value_counts().head())
df = df.sort_values('dt',kind = 'stable')
print('\n排序之后：',df['dt'].is_monotonic_increasing)            
print('排序之后：',
      df['dt'].diff().dt.total_seconds().div(3600).value_counts().head())


'''

回答：

is_monotonic_increasing 是 True 还是 False？
是false，说明这就不是按时间排序的

为什么 diff() 会出现负数？这是数据坏了，还是你没排序就动时间？
.diff就是本行与上一行的差，出现负数说明这就不是按时间排序的，所以才会出现从负数到几万小时之后

排序之后再看 diff()，负数还在吗？
不在了，只剩下0,1,2

这就是"先取证再下结论"最朴素的一次练习： 如果你看到负的时间差就断定"数据坏了"、动手删掉 —— 你删掉的全是好数据。


'''

#重复时间戳：4 条重复，而且全在同一个日子类型上



print(df['dt'].duplicated().sum())
dup = df[df['dt'].duplicated(keep=False)].sort_values('dt')
print('重复：',dup)





'''

回答：

1.有几条重复？具体哪几个时间戳？
有四条重复的，是2014,15,16,17年的十一月

2.这四个时间点有什么共同点？为什么会出现这种重复？
都是凌晨两点，因为美国夏令时"回拨"那天，当地时间 2 点会过两遍

决定怎么处理：留第一条、留最后一条、还是取平均？说清理由。
留第一条。理由：没有 UTC 偏移就无法区分哪一行是回拨前、哪一行是回拨后，只能二选一；
keep='first' 规则确定、可复现，代价是 4 / 121,269 ≈ 0.0033% 的样本。
数据"重复"不一定是错误，可能只是时区/夏令时的产物。 

任务 4 · 缺口：27 个洞，54 小时
排序去重后再看采样间隔：
'''



d = df.sort_values('dt').drop_duplicates(subset='dt', keep='first').reset_index(drop=True)
print(d['dt'].diff().dt.total_seconds().div(3600).value_counts())

# 不插值：27 个缺口里 24 个是夏令时切换造成的 —— 春季那天真实只有 23 小时（被跳过的
# 小时不存在），秋季那天真实是 25 小时（重复的小时是两个真实小时）。插值会造出假的
# "24 小时结构"，让这 28 天的日电量偏 ±4%。另外 3 个普通缺口只占 0.02%，也不补。
# 需要"同口径"比较时，用 dim_date.n_hours 过滤，而不是把数据改成 24 小时。


'''

回答：

间隔分布是什么？（应该只有 1 小时和 2 小时两种，外加去重前的 0 小时）

2 小时的间隔有几个？相当于缺了多少小时？
27个，缺了27个小时

缺的这些要补吗？
不补：知道"这一小时没数据"，分析时用实际有数据的行数
补：插值 / 前后填充 —— 会凭空造出一个数，但时间轴连续
你的选择会怎样影响后面的"日用电量"计算？（这题必须答，它直接影响 SQL 那一步）

不补。这 27 个缺口里 24 个是夏令时切换造成的，不是"数据丢了"：
春季那天真实只有 23 小时（被跳过的小时不存在），秋季那天真实是 25 小时（重复的小时是两个真实小时）。
插值会把这些日子强行改成 24 小时，日电量反而偏 ±4%。
另外 3 个普通缺口（2010-12-10 00:00、2012-12-06 04:00、2014-03-11 14:00）占 0.02%，也不补。
日聚合时用 `n_hours` 过滤，只和同口径的天比较。
'''

print(d['AEP_MW'].describe(percentiles=[.001,.01,.5,.99,.999]))
print(d.nlargest(5, 'AEP_MW'))
print(d.nsmallest(5, 'AEP_MW'))
'''

任务 5 · 异常值：先看，别删


回答：

最大值、最小值各是多少？和 99% 分位数差多少倍？
最大值是25695，最小值是9581,99%位数是22026，差了1.16倍

最高那天的前后几小时，负荷是不是一路爬上去的？（在 2008-10-20 附近看一眼）
不是，是突然上去又跌下去，这就是异常数据，

最低那天的前后几小时呢？（在 2016-10-02 附近看一眼）——最低的 5 个值是不是挤在同一段时间里？
是。最低的 5 个里有 3 个在 2016-10-02 04:00–06:00（9,581 / 9,623 / 9,604），另外两个是 2015-05-24 05:00（9,662）和 2012-06-30 05:00（9,669）

关键判断：这些极值，是采集错误还是真实事件？你用什么规则区分？
如果时间段比较连续，比如2016-10-02，连续五个小时都低于一万，那是真实事件
但是那个最大值，是数据采集错误
不要看到极端值就删。 这是负荷数据，"负荷飙高"和"负荷骤降"本身就是你要分析的对象。删掉它们，后面异常检测就没东西可检了。
'''

d['date'] = d['dt'].dt.strftime('%Y-%m-%d')      # 存成字符串，导 SQLite 直接用
d['year'] = d['dt'].dt.year
d['month'] = d['dt'].dt.month
d['hour'] = d['dt'].dt.hour
d['weekday'] = d['dt'].dt.dayofweek      # 0=周一
d['is_weekend'] = d['weekday'].isin([5, 6]).astype(int)
d['n_hours'] = d.groupby('date')['dt'].transform('count')   # 当天实际有几行（DST 日 23/25）
# 2014–2017 的秋季切换日源数据有重复时间戳，去重时丢了 1 个真实小时；标出来，
# 这些天的日电量同样不能直接和普通日比
dup_dates = set(dup['dt'].dt.strftime('%Y-%m-%d'))
d['had_duplicate'] = d['date'].isin(dup_dates).astype(int)
'''
任务 6 · 建维度表（为 SQL 那一步铺路）
清洗完顺手把时间维度拆出来，存成一张独立的表：

为什么要做这个？ 因为下一步（SQL）你要建的是事实表 + 维度表的星型结构，而不是一张大宽表。现在拆好，到时候直接导。

回答：一张 fact_load（事实）和一张 dim_date（维度），各放哪些列？为什么这么分？
fact_load 放 dt 和 aep_mw：事实表只记录发生的事，也就是负荷值本身。
dim_date 放 dt、date、year、month、hour、weekday、is_weekend、n_hours、had_duplicate：时间维度。
n_hours = 当天实际行数（DST 日 23/25）；had_duplicate = 那天源数据有重复时间戳、去重丢过 1 个真实小时。

这两列用来判断"这一天的日电量能不能直接和普通日比"。

'''

df_fact_load = d[['dt', 'AEP_MW']].rename(columns={'AEP_MW': 'aep_mw'})
df_dim_date = d[['dt', 'date', 'year', 'month', 'hour', 'weekday', 'is_weekend', 'n_hours', 'had_duplicate']]
df_fact_load.to_parquet('data/processed/fact_load.parquet', index=False)
df_dim_date.to_parquet('data/processed/dim_date.parquet', index=False)

# ---------- 落盘后自查 ----------
print('\n=== 落盘自查 ===')
print('fact_load:', df_fact_load.shape, '| dim_date:', df_dim_date.shape)
print('每天行数分布:', d.groupby('date').size().value_counts().sort_index().to_dict())
print('非 24 小时的日子:')
print(d[d['n_hours'] != 24].groupby('date').size().to_string())
print('去重丢过小时的日期:', d.loc[d['had_duplicate'] == 1, 'date'].nunique(), '天')
fact_check = pd.read_parquet('data/processed/fact_load.parquet')
dim_check = pd.read_parquet('data/processed/dim_date.parquet')
print('读回:', fact_check.shape, dim_check.shape,
      '| 空值:', int(fact_check.isna().sum().sum()), int(dim_check.isna().sum().sum()))

