from fastapi.testclient import TestClient
from seismicshield_rl.api.app import app

def test_health():
    c=TestClient(app); r=c.get('/health')
    assert r.status_code==200
    assert r.json()['scientific_status']=='exploratory'
