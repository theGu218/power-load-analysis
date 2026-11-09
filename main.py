from fastapi import FastAPI,Request,Query,HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel,Field
from datetime import date, datetime
import uvicorn
import joblib
import sqlite3
import os
import json
import pandas as pd


@asynccontextmanager
async def lifespan(app:FastAPI):
    conn = sqlite3.connect('processed/power_load.db',check_same_thread = False)
    conn.row_factory = sqlite3.Row
    app.state.db = conn
    # 启动时算一次全库概览，/summary 和 /anomalies 都复用
    cursor = conn.cursor()
    cursor.execute("""
    SELECT COUNT(*) AS rows, 
    MIN(date) AS date_min, 
    MAX(date) AS date_max,
    AVG(aep_mw) AS avg_mw, MAX(aep_mw) AS peak_mw,
    (SELECT dt FROM fact_load ORDER BY aep_mw DESC LIMIT 1) AS peak_dt,
    MIN(aep_mw) AS valley_mw,
    (SELECT dt FROM fact_load ORDER BY aep_mw ASC LIMIT 1) AS valley_dt
    FROM fact_load""")
    app.state.summary_cache = dict(cursor.fetchone())
    cursor.close()

    model_path = 'models/power_gb_model.pkl'
    metrics_path = 'models/metrics.json'

    if not os.path.exists(model_path):
        raise FileNotFoundError (f'找不到文件：{model_path}')
    if not os.path.exists(metrics_path):
        raise FileNotFoundError (f'找不到文件：{metrics_path}')

    model_package = joblib.load(model_path)
    app.state.model = model_package['model']
    app.state.features = model_package['features']

    with open(metrics_path,'r',encoding = 'utf-8')as f:
        app.state.metrics = json.load(f)
    
    yield
    conn.close()
app = FastAPI(lifespan = lifespan)

@app.get("/health")

def health_check(request:Request):
    db = request.app.state.db
    cursor = db.cursor()
    cursor.execute("select count(*) from fact_load")
    row_count = cursor.fetchone()[0]
    cursor.close()
    return {"state": "ok","rows" :row_count}

class Summary(BaseModel):
    rows:int
    date_min:date
    date_max:date
    avg_mw:float
    peak_mw:float
    peak_dt:datetime
    valley_mw:float
    valley_dt:datetime

@app.get('/summary',response_model = Summary)
def get_summary(request:Request):
    return request.app.state.summary_cache

class DailyMetric(BaseModel):
    date:date
    avg_mw:float
    peak_mw:float
    valley_mw:float 
    span_mw:float
    load_factor:float
    is_complete:bool


@app.get("/daily",response_model=list[DailyMetric])
def get_daily_data(
    request:Request,
    start:date = Query(...,description="开始日期"),
    end:date = Query(...,description="结束日期")
):
    if start > end:
        raise HTTPException(status_code=400 ,detail="开始日期不能大于结束日期")
    db = request.app.state.db
    cursor = db.cursor()
    sql = "SELECT*from daily_metrics where date between ? and ? order by date asc"
    cursor.execute(sql,(str(start),str(end)))

    rows = cursor.fetchall()
    cursor.close()

    if not rows:
        raise HTTPException(status_code=404,detail="区间内没有数据")

    return [dict(row) for row in rows]

class Anomaly(BaseModel):
    dt:datetime
    aep_mw:float
    diff_from_mean:float

@app.get("/anomalies",response_model=list[Anomaly])
def get_anomalies(
    request:Request,
    start:date,
    end:date,
    threshold:float=Query(20000,gt=0,description="负荷阈值，必须大于0")
):
    avg_mw = request.app.state.summary_cache["avg_mw"]
    db = request.app.state.db
    cursor = db.cursor()
    sql = """SELECT dt, aep_mw 
        FROM fact_load 
        WHERE date BETWEEN ? AND ? 
          AND aep_mw > ? 
        ORDER BY aep_mw DESC
        """
    cursor.execute(sql, (str(start), str(end), threshold))
    rows = cursor.fetchall()
    cursor.close()
    result = [dict(row) for row in rows]
    for row in result:
            row["diff_from_mean"] = row["aep_mw"] - avg_mw
            
    return result

class PredictRequest(BaseModel):
    hour:int = Field(...,ge=0,le=23)
    weekday:int = Field(...,ge=0,le=6)
    month:int = Field(...,ge=1,le=12)
    is_weekend:int = Field(...,ge=0,le=1)
    season_code:int = Field(...,ge=1,le=4)
    lag1:float = Field(...,ge=0)
    lag24:float = Field(...,ge=0)
    lag168:float = Field(...,ge=0)
    roll24:float = Field(...,ge=0)

@app.post('/predict')
def predict_load(data:PredictRequest,request:Request):
    model = request.app.state.model     
    features = request.app.state.features

    input_dict = data.model_dump()
    input_df = pd.DataFrame([input_dict])
    input_df = input_df[features]

    prediction = model.predict(input_df)[0]

    return{
        "prediction_mw":round(float(prediction),1),
        "model":request.app.state.metrics.get("model_type","HistGradientBoostingRegressor"),
        "features":features
    }

@app.get('/model_info')
def get_model_info(request:Request):
    return request.app.state.metrics
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)