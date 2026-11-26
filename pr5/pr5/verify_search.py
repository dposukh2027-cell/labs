import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.api import create_app
from fastapi.testclient import TestClient

app = create_app()
client = TestClient(app)
response = client.post(
    '/search',
    data={
        'query': 'Як повернути кошти за товар',
        'top_k': 3,
        'threshold': 0.0,
        'category': '',
        'product': '',
        'audience': '',
        'status': ''
    }
)
print('status_code=', response.status_code)
print('body=', response.json())
