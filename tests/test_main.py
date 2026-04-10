from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_analyze_emotion_positive():
    # Kiểm tra với một câu tích cực
    response = client.post("/analyze-emotion", json={"message": "Tôi đang cảm thấy rất tuyệt vời"})
    assert response.status_code == 200

    data = response.json()
    assert "bot_response" in data
    assert data["emotion"]["label"] == "Tích cực/Vui vẻ"

def test_analyze_emotion_empty_input():
    # Kiểm tra xem hệ thống có báo lỗi khi gửi tin nhắn trống không
    response = client.post("/analyze-emotion", json={"message": ""})
    assert response.status_code == 400  # Mã lỗi do chúng ta định nghĩa trong HTTPException
