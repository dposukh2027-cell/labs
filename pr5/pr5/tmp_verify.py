import sys
sys.path.insert(0, 'C:/Users/nikit/OneDrive/Desktop/Новая папка/pr5')
from app.api import create_app
from fastapi.testclient import TestClient

app = create_app()
client = TestClient(app)
resp = client.post(
    '/search',
    data={
        'query': 'Як повернути кошти за товар',
        'top_k': 3,
        'threshold': 0.0,
        'category': '',
        'product': '',
        'audience': '',
        'status': '',
    }
)
print('status', resp.status_code)
print(resp.text[:500])
