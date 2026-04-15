import os
import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# 1. BẢO MẬT CORS VÀ THƯ VIỆN AI GEMINI
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai

# Import class AI cũ để lấy Nhãn Cảm Xúc lưu vào Database
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

Base.metadata.create_all(bind=engine)

# ==========================================
# 3. KHỞI TẠO MÁY CHỦ API (FASTAPI)
# ==========================================
app = FastAPI(title="ZenMind AI Sentiment API")

# CẤU HÌNH CORS CHO FRONTEND GITHUB PAGES
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

class UserInput(BaseModel):
    message: str

# ==========================================
# 4. API CHÍNH: XỬ LÝ VÀ PHẢN HỒI (TÍCH HỢP GEMINI)
# ==========================================
@app.post("/analyze-emotion")
async def analyze_and_save(data: UserInput):
    if not data.message:
        raise HTTPException(status_code=400, detail="Tin nhắn không được để trống")

    # BƯỚC 1: Lấy nhãn cảm xúc từ hàm cũ để phân loại và lưu Database
    analysis = EmotionEngine.analyze_text(data.message)

    # BƯỚC 2: Gọi não bộ Gemini để sinh câu trả lời thấu cảm
    try:
        # Lấy Key từ biến môi trường của Render (mặc định để rỗng nếu chưa cài)
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        
        if not GEMINI_API_KEY:
            response_text = "Hình như bạn chưa cấp API Key cho mình trên Render thì phải? Bạn kiểm tra lại nhé!"
        else:
            genai.configure(api_key=GEMINI_API_KEY)
            
            # Khởi tạo model Gemini 1.5 Flash
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Kịch bản ám thị (Prompt) cho Bot
            prompt = f"""Bạn là ZenMind, một AI tư vấn tâm lý nhẹ nhàng, thấu cảm. 
            Người dùng vừa nói: '{data.message}'. 
            Cảm xúc của họ đang nghiêng về: '{analysis['label']}'. 
            Hãy trả lời họ bằng 2-3 câu ngắn gọn, ấm áp, thấu hiểu và gợi mở bằng tiếng Việt. Không dùng các ký tự in đậm hay in nghiêng."""
            
            gemini_response = model.generate_content(prompt)
            response_text = gemini_response.text
            
    except Exception as e:
        print(f"Lỗi Gemini: {e}") 
        response_text = "Hiện tại tâm trí mình đang hơi bối rối do lỗi kết nối mạng, bạn chờ mình một lát rồi nhắn lại nhé!"

    # BƯỚC 3: Lưu vào Database
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

    # BƯỚC 4: Trả kết quả về cho Frontend
    return {
        "emotion": analysis,
        "bot_response": response_text,
        "db_status": "Đã lưu lịch sử thành công"
    }
