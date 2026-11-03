from fastapi import FastAPI,Request
from contextlib import asynccontextmanager
from pydantic import BaseModel
from datetime import date, datetime
import uvicorn
import sqlite3


@asynccontextmanager
async def lifespan(app:FastAPI):
    conn = sqlite3.connect('processed/power_load.db',check_same_thread = False)
    conn.row_factory = sqlite3.Row
    app.state.db = conn
    yield
    print('closing')
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

@asynccontextmanager
async def lifespan(app:FastAPI):
    conn = sqlite3.connect('processed/power_load.db',check_same_thread = False)
    conn.row_factory = sqlite3.Row
    app.state.db = conn
    cursor = conn.cursor()
    cursor.execute("""SELECT 
        COUNT(*) AS rows,
        MIN(date) AS date_min,
        MAX(date) AS date_max,
        AVG(aep_mw) AS avg_mw,
        MAX(aep_mw) AS peak_mw,
        (SELECT dt FROM fact_load ORDER BY aep_mw DESC LIMIT 1) 
        AS peak_dt,
        MIN(aep_mw) AS valley_mw,
        (SELECT dt FROM fact_load ORDER BY aep_mw ASC LIMIT 1) 
        AS valley_dt
    FROM fact_load;""")
    row = cursor.fetchone()
    app.state.summary_cache = dict(row)
    cursor.close()
    yield
    app.state.db.close()



@app.get('/summary',response_model = Summary)
def get_summary(request:Request):
    return request.app.state.summary_cache

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)