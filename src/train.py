import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import GradientBoostingRegressor,HistGradientBoostingRegressor
import joblib
import json
from pathlib import Path

df = pd.read_parquet('processed/fact_load.parquet')
df['dt'] = pd.to_datetime(df['dt'])
df = df.sort_values('dt').reset_index(drop=True)

df['hour'] = df['dt'].dt.hour
df['weekday'] = df['dt'].dt.dayofweek
df['month'] = df['dt'].dt.month
df['is_weekend'] = df['weekday'].isin([5,6]).astype(int)

def get_season(m):
    if m in [3,4,5] :return 1
    if m in [6,7,8] :return 2
    if m in [9,10,11] :return 3
    return 4
df['season_code'] = df['month'].apply(get_season)

# shift 的意思就是把数据向下移动一行，相当于拿到上一行的数据
df['lag1'] = df['aep_mw'].shift(1)
df['lag24'] = df['aep_mw'].shift(24)
df['lag168'] = df['aep_mw'].shift(168)

#因为roll24不包含当前行，所以说需要先把shift1剔除，然后rolling24行算平均值
df['roll24'] = df['aep_mw'].shift(1).rolling(24).mean()

df = df.dropna().reset_index(drop=True)
cols = [
    'dt',
    'aep_mw',
    'hour',
    'weekday',
    'month',
    'is_weekend',
    'season_code',
    'lag1',
    'lag24',
    'lag168',
    'roll24'
]

final_df = df[cols]

X = final_df.drop(columns=['dt','aep_mw'])
y = final_df['aep_mw']

tscv = TimeSeriesSplit(5)
rmse_baseline1 = []
rmse_baseline2 = []


for train_idx,test_idx in tscv.split(X):
    X_train,X_test = X.iloc[train_idx],X.iloc[test_idx]
    y_train,y_test = y.iloc[train_idx],y.iloc[test_idx]

    mean_y = y_train.mean()
    y_pred_1 = np.full(len(y_test),mean_y)
    rmse1 = np.sqrt(mean_squared_error(y_test,y_pred_1))
    rmse_baseline1.append(rmse1)

    y_pred_2 = X_test['lag24']
    rmse2 =np.sqrt(mean_squared_error(y_test,y_pred_2))
    rmse_baseline2.append(rmse2)

avg_rmse_1 = np.mean(rmse_baseline1)
avg_rmse_2 = np.mean(rmse_baseline2)

result_df = pd.DataFrame({
    "基线":["常数","lag24"],
    "5折RMSE均值":[avg_rmse_1,avg_rmse_2],
    "std":[np.std(rmse_baseline1),np.std(rmse_baseline2)]
}) 
result_df = result_df.set_index("基线")

print(result_df.round(2).to_string())

feat_calendar = [
    'hour',
    'weekday',
    'month',
    'is_weekend',
    'season_code'
]

X_cal = X[feat_calendar]

feat_calendar_lag = feat_calendar + [
    'lag1',
    'lag24',
    'lag168',
    'roll24'
]

X_cal_lag = X[feat_calendar_lag]

model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
rmse_cal = []
rmse_cal_lag = []
for train_idx,test_idx in tscv.split(X_cal):
    X_train_cal,X_test_cal = X_cal.iloc[train_idx],X_cal.iloc[test_idx]
    y_train,y_test = y.iloc[train_idx],y.iloc[test_idx]

    model.fit(X_train_cal,y_train)
    pred_cal = model.predict(X_test_cal)
    rmse_cal.append(np.sqrt(mean_squared_error(y_test,pred_cal)))

    X_train_lag = X_cal_lag.iloc[train_idx]
    X_test_lag = X_cal_lag.iloc[test_idx]
    model.fit(X_train_lag,y_train)
    pred_lag = model.predict(X_test_lag)
    rmse_cal_lag.append(np.sqrt(mean_squared_error(y_test,pred_lag)))
    
results_ridge = pd.DataFrame({
    '只给日历特征': rmse_cal,
    '日历+滞后': rmse_cal_lag
})
results_ridge.loc['均值'] = results_ridge.mean()
results_ridge.loc['标准差'] = results_ridge.std()

print(results_ridge.round(2).to_string())
#降了2156.3/508.5 = 4.24倍，这说明自回归特征比日历特征重要得多

gb_model = GradientBoostingRegressor(
    n_estimators=100, 
    learning_rate=0.1, 
    max_depth=3, 
    subsample=0.7, 
    random_state=42
)

rmse_gb = []
for train_idx, test_idx in tscv.split(X_cal_lag):
    X_train, X_test = X_cal_lag.iloc[train_idx], X_cal_lag.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    
    # 训练模型
    gb_model.fit(X_train, y_train)
    preds = gb_model.predict(X_test)
    
    # 算分并存入列表
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    rmse_gb.append(rmse)

print("5折 RMSE:", [round(float(x), 1) for x in rmse_gb],
      "| mean", round(float(np.mean(rmse_gb)), 1),
      "| std", round(float(np.std(rmse_gb)), 1))

'''
相比于ridge，树（508.5-312.8）/508.5 = 0.38
相比于lag24，(1299.7 - 312.8)÷1299.7≈0.759
最差的应该是第一折，因为训练集的数据最少

'''

# 最终模型与评估模型保持一致（GBR），指标才是真的
final_model = GradientBoostingRegressor(
    n_estimators=100,
    learning_rate=0.1,
    max_depth=3,
    subsample=0.7,
    random_state=42,
)

final_model.fit(X_cal_lag, y)
Path('models').mkdir(exist_ok=True)          # 目录不存在时先建
model_package = {
    "model": final_model,
    "features":list(X_cal_lag.columns)
}
joblib.dump(model_package,'models/power_gb_model.pkl')

metrics = {
    "model_type":"GradientBoostingRegressor",
    "rmse_folds": [round(float(x), 1) for x in rmse_gb],
    "rmse_mean": round(float(np.mean(rmse_gb)), 1),
    "rmse_std": round(float(np.std(rmse_gb)), 1),
    "parameters":{
        "n_estimators":100,
        "learning_rate":0.1,
        "max_depth":3,
        "subsample":0.7,
        "random_state":42
    }

}

with open('models/metrics.json','w',encoding = 'utf-8') as f:
    json.dump(metrics,f,indent = 4,ensure_ascii = False)

loaded_package = joblib.load('models/power_gb_model.pkl')
loaded_model = loaded_package["model"]
loaded_features = loaded_package["features"]

sample_X = X_cal_lag[loaded_features].head(5)
original_preds = final_model.predict(sample_X)
loaded_preds = loaded_model.predict(sample_X)

print('保存前的预测值',original_preds)
print('加载后的预测值',loaded_preds)

if np.allclose(original_preds,loaded_preds):
    print('通过')
else:
    print('不通过')



