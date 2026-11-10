"""接口测试：在项目根目录、有 processed/ 和 models/ 的情况下运行。

    pip install -r requirements-dev.txt
    pytest tests -q
"""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

PAYLOAD = {
    "hour": 17,
    "weekday": 6,
    "month": 7,
    "is_weekend": 1,
    "season_code": 2,
    "lag1": 18000,
    "lag24": 17500,
    "lag168": 17000,
    "roll24": 17800,
}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["rows"] == 121269


def test_summary():
    r = client.get("/summary")
    assert r.status_code == 200
    assert r.json()["peak_dt"] == "2008-10-20T14:00:00"


def test_predict_ok():
    r = client.post("/predict", json=PAYLOAD)
    assert r.status_code == 200
    assert 15000 < r.json()["prediction_mw"] < 25000


def test_predict_bad_hour():
    bad = dict(PAYLOAD, hour=25)
    assert client.post("/predict", json=bad).status_code == 422


def test_predict_missing_field():
    missing = dict(PAYLOAD)
    missing.pop("lag1")
    assert client.post("/predict", json=missing).status_code == 422
