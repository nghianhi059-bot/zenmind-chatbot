import os
import datetime
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
import jwt
from passlib.context import CryptContext

from emotion_engine import EmotionEngine

# ==========================================
# 1. CẤU HÌNH BẢO MẬT & DATABASE
# ==========================================
SECRET_KEY = "zenmind_super_secret_key_nghia" # Khóa bí mật để tạo Token
ALGORITHM = "HS256"

# Cấu hình mã hóa mật khẩu
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user_admin:password123@db:5432/zenmind_db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 2. ĐỊNH NGHĨA DATABASE (CẬP NHẬT MỚI)
# ==========================================
# Bảng Người Dùng
class User(Base):
    __tablename__ = "users_v2" # Tạo bảng mới để tránh lỗi dữ liệu cũ
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    
    # Mối quan hệ: 1 User có nhiều lịch sử
    histories = relationship("EmotionHistory", back_populates="owner")

# Bảng Lịch sử Chat (Có thêm Chủ sở hữu)
class EmotionHistory(Base):
    __tablename__ = "emotion_history_v2"
    
    id = Column(Integer, primary_key=True, index=True)
    message = Column(String)
    label = Column(String)
    score = Column(Float)
    bot_reply = Column(String) # Lưu luôn câu trả lời của Bot
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Khóa ngoại nối với bảng User
    owner_id = Column(Integer, ForeignKey("users_v2.id"))
    owner = relationship("User", back_populates="histories")

Base.metadata.create_all(bind=engine)

# ==========================================
# 3. KHỞI TẠO MÁY CHỦ API
# ==========================================
app = FastAPI(title="ZenMind AI Sentiment API (Secured)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# Hàm hỗ trợ lấy Session DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 4. HỆ THỐNG ĐĂNG KÝ & ĐĂNG NHẬP
# ==========================================
class UserCreate(BaseModel):
    username: str
    password: str

@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    # Kiểm tra xem user đã tồn tại chưa
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã được sử dụng")
    
    # Mã hóa mật khẩu và lưu
    hashed_password = pwd_context.hash(user.password)
    new_user = User(username=user.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    return {"message": "Đăng ký thành công!"}

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    # Kiểm tra mật khẩu
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Sai tên đăng nhập hoặc mật khẩu")
    
    # Tạo Token
    token_data = {"sub": user.username}
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

# Hàm xác thực Token của người dùng (Bảo vệ API)
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Token không hợp lệ")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Người dùng không tồn tại")
    return user

# ==========================================
# 5. API CHAT VÀ LẤY LỊCH SỬ (ĐÃ BẢO VỆ)
# ==========================================
class UserInput(BaseModel):
    message: str

@app.post("/analyze-emotion")
# Thêm current_user vào hàm để bắt buộc phải có Token mới được gọi
async def analyze_and_save(data: UserInput, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not data.message:
        raise HTTPException(status_code=400, detail="Tin nhắn không được để trống")

    analysis = EmotionEngine.analyze_text(data.message)

    try:
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"Bạn là ZenMind, AI tư vấn tâm lý. Người dùng {current_user.username} vừa nói: '{data.message}'. Cảm xúc: '{analysis['label']}'. Hãy trả lời ấm áp, gợi mở bằng tiếng Việt."
        gemini_response = model.generate_content(prompt)
        response_text = gemini_response.text
    except Exception as e:
        response_text = "Hiện tại tâm trí mình đang bối rối, bạn chờ mình lát nhé!"

    # Lưu vào Database với ID của người dùng
    new_entry = EmotionHistory(
        message=data.message, 
        label=analysis['label'], 
        score=analysis['score'],
        bot_reply=response_text,
        owner_id=current_user.id
    )
    db.add(new_entry)
    db.commit()

    return {"emotion": analysis, "bot_response": response_text}

# API mới: Lấy lịch sử chat của riêng người dùng đó
@app.get("/history")
def get_user_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Tìm tất cả tin nhắn thuộc về user_id này
    history = db.query(EmotionHistory).filter(EmotionHistory.owner_id == current_user.id).order_by(EmotionHistory.created_at.asc()).all()
    return history
