import os
import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Import class AI do chính bạn viết
from emotion_engine import EmotionEngine

# ==========================================
# 1. CẤU HÌNH CƠ SỞ DỮ LIỆU POSTGRESQL
# ==========================================
# Sử dụng os.getenv để lấy biến môi trường từ Docker, nếu không có sẽ tự lấy URL mặc định.
# Lưu ý: Chữ 'db' trong chuỗi kết nối chính là tên dịch vụ database trong docker-compose.yml
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user_admin:password123@db:5432/zenmind_db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 2. ĐỊNH NGHĨA BẢNG LƯU TRỮ (MODELS)
# ==========================================
class EmotionHistory(Base):
    __tablename__ = "emotion_history"
    
    id = Column(Integer, primary_key=True, index=True)
    message = Column(String)
    label = Column(String)
    score = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Lệnh này sẽ tự động kiểm tra và tạo bảng trong Database nếu nó chưa tồn tại
Base.metadata.create_all(bind=engine)

# ==========================================
# 3. KHỞI TẠO MÁY CHỦ API (FASTAPI)
# ==========================================
app = FastAPI(title="ZenMind AI Sentiment API")

# Cấu trúc dữ liệu yêu cầu từ người dùng gửi lên
class UserInput(BaseModel):
    message: str

# ==========================================
# 4. API CHÍNH: XỬ LÝ VÀ PHẢN HỒI
# ==========================================
@app.post("/analyze-emotion")
async def analyze_and_save(data: UserInput):
    # Kiểm tra tin nhắn trống
    if not data.message:
        raise HTTPException(status_code=400, detail="Tin nhắn không được để trống")

    # Gọi "Bộ não AI" phân tích câu chữ của người dùng
    analysis = EmotionEngine.analyze_text(data.message)

    # Lên kịch bản phản hồi dựa vào tâm trạng
    response_text = ""
    if analysis['label'] == "Buồn/Lo âu":
        response_text = "Mình cảm nhận được bạn đang có chút tâm sự. Bạn cứ bình tĩnh nói thêm nhé..."
    else:
        response_text = "Cảm ơn bạn đã chia sẻ, mình đang lắng nghe đây!"

    # Mở kết nối Database và lưu lịch sử chat vào PostgreSQL
    db = SessionLocal()
    try:
        new_entry = EmotionHistory(
            message=data.message, 
            label=analysis['label'], 
            score=analysis['score']
        )
        db.add(new_entry)
        db.commit()
    finally:
        # Luôn đảm bảo đóng kết nối để không bị tràn bộ nhớ
        db.close()

    # Trả về kết quả
    return {
        "emotion": analysis,
        "bot_response": response_text,
        "db_status": "Đã lưu lịch sử thành công"
    }