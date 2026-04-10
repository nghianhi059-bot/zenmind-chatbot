import os
import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. KHAI BÁO CƠ CHẾ BẢO MẬT CORS
from fastapi.middleware.cors import CORSMiddleware

# Import class AI do chính bạn viết
from emotion_engine import EmotionEngine

# ==========================================
# 1. CẤU HÌNH CƠ SỞ DỮ LIỆU POSTGRESQL
# ==========================================
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

# Tự động tạo bảng
Base.metadata.create_all(bind=engine)

# ==========================================
# 3. KHỞI TẠO MÁY CHỦ API (FASTAPI)
# ==========================================
app = FastAPI(title="ZenMind AI Sentiment API")

# --- CẤU HÌNH QUAN TRỌNG: CHO PHÉP FRONTEND TRUY CẬP ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cho phép tất cả các nguồn (bao gồm GitHub Pages)
    allow_credentials=True,
    allow_methods=["*"],  # Cho phép tất cả các phương thức (GET, POST,...)
    allow_headers=["*"],  # Cho phép tất cả các tiêu đề
)

class UserInput(BaseModel):
    message: str

# ==========================================
# 4. API CHÍNH: XỬ LÝ VÀ PHẢN HỒI
# ==========================================
@app.post("/analyze-emotion")
async def analyze_and_save(data: UserInput):
    if not data.message:
        raise HTTPException(status_code=400, detail="Tin nhắn không được để trống")

    # Phân tích cảm xúc
    analysis = EmotionEngine.analyze_text(data.message)

    # Lên kịch bản phản hồi
    response_text = ""
    if analysis['label'] == "Buồn/Lo âu":
        response_text = "Mình cảm nhận được bạn đang có chút tâm sự. Bạn cứ bình tĩnh nói thêm nhé..."
    elif analysis['label'] == "Tích cực/Vui vẻ":
        response_text = "Thật tuyệt vời khi nghe điều đó! Hãy giữ vững năng lượng này nhé!"
    else:
        response_text = "Cảm ơn bạn đã chia sẻ, mình đang lắng nghe đây!"

    # Lưu vào Database
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
        db.close()

    return {
        "emotion": analysis,
        "bot_response": response_text,
        "db_status": "Đã lưu lịch sử thành công"
    }
