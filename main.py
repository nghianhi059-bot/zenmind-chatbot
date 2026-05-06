import os
import datetime
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
import jwt
from passlib.context import CryptContext

from emotion_engine import EmotionEngine

# ==========================================
# CẤU HÌNH BẢO MẬT & DATABASE
# ==========================================
SECRET_KEY = "zenmind_super_secret_key_nghia" 
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user_admin:password123@db:5432/zenmind_db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users_v3" 
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    system_knowledge = Column(String, default="")
    sessions = relationship("ChatSession", back_populates="owner")

class ChatSession(Base):
    __tablename__ = "chat_sessions_v3"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="Đoạn chat mới")
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users_v3.id"))
    owner = relationship("User", back_populates="sessions")
    messages = relationship("EmotionHistory", back_populates="session", cascade="all, delete")

class EmotionHistory(Base):
    __tablename__ = "emotion_history_v3"
    id = Column(Integer, primary_key=True, index=True)
    message = Column(String)
    label = Column(String)
    score = Column(Float)
    bot_reply = Column(String) 
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    session_id = Column(Integer, ForeignKey("chat_sessions_v3.id"))
    session = relationship("ChatSession", back_populates="messages")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="ZenMind AI v3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=False, 
    allow_methods=["*"],  
    allow_headers=["*"],  
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserCreate(BaseModel):
    username: str
    password: str

@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")
    hashed_password = pwd_context.hash(user.password)
    new_user = User(username=user.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    return {"message": "Đăng ký thành công!"}

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not pwd_context.verify(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Sai thông tin")
    token = jwt.encode({"sub": user.username}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.query(User).filter(User.username == payload.get("sub")).first()
        if not user: raise Exception()
        return user
    except:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")

class KnowledgeInput(BaseModel):
    knowledge: str

@app.post("/knowledge")
def update_knowledge(data: KnowledgeInput, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.system_knowledge = data.knowledge
    db.commit()
    return {"message": "Đã cập nhật", "knowledge": current_user.system_knowledge}

@app.get("/knowledge")
def get_knowledge(current_user: User = Depends(get_current_user)):
    return {"knowledge": current_user.system_knowledge}

class SessionUpdate(BaseModel):
    title: str = None
    is_pinned: bool = None

@app.post("/sessions")
def create_session(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_session = ChatSession(owner_id=current_user.id)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session

@app.get("/sessions")
def get_sessions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(ChatSession).filter(ChatSession.owner_id == current_user.id).order_by(ChatSession.is_pinned.desc(), ChatSession.created_at.desc()).all()

@app.put("/sessions/{session_id}")
def update_session(session_id: int, data: SessionUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.owner_id == current_user.id).first()
    if data.title is not None: session.title = data.title
    if data.is_pinned is not None: session.is_pinned = data.is_pinned
    db.commit()
    return {"message": "Cập nhật thành công"}

@app.delete("/sessions/{session_id}")
def delete_session(session_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.owner_id == current_user.id).first()
    db.delete(session)
    db.commit()
    return {"message": "Đã xóa đoạn chat"}

class UserInput(BaseModel):
    message: str
    session_id: int

@app.post("/analyze-emotion")
async def analyze_and_save(data: UserInput, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == data.session_id, ChatSession.owner_id == current_user.id).first()
    analysis = EmotionEngine.analyze_text(data.message)

    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
        model = genai.GenerativeModel('gemini-1.5-flash')
        knowledge_context = f"Kiến thức: {current_user.system_knowledge}." if current_user.system_knowledge else ""
        prompt = f"Bạn là ZenMind. {knowledge_context} Người dùng nói: '{data.message}'. Cảm xúc: '{analysis['label']}'. Hãy trả lời ấm áp, gợi mở."
        gemini_response = model.generate_content(prompt)
        response_text = gemini_response.text
    except Exception as e:
        response_text = f"Lỗi não bộ: {str(e)}"

    new_entry = EmotionHistory(message=data.message, label=analysis['label'], score=analysis['score'], bot_reply=response_text, session_id=session.id)
    db.add(new_entry)
    if db.query(EmotionHistory).filter(EmotionHistory.session_id == session.id).count() == 1:
        session.title = data.message[:25]
    db.commit()
    return {"emotion": analysis, "bot_response": response_text}

@app.get("/sessions/{session_id}/history")
def get_session_history(session_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(EmotionHistory).filter(EmotionHistory.session_id == session_id).order_by(EmotionHistory.created_at.asc()).all()

# ==========================================
# CÔNG CỤ CHUẨN ĐOÁN LỖI BÍ MẬT
# ==========================================
@app.get("/kiem-tra-api")
def kiem_tra():
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return {"TrangThai": "LỖI", "NguyenNhan": "Render chưa nhận được API KEY. Biến môi trường đang bị bỏ trống!"}
    
    # Chỉ hiện vài ký tự đầu và cuối để bảo mật
    masked_key = api_key[:10] + "......" + api_key[-4:] if len(api_key) > 15 else api_key
    
    try:
        genai.configure(api_key=api_key)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        return {
            "TrangThai": "KẾT NỐI THÀNH CÔNG TỚI GOOGLE", 
            "API_Key_Dang_Dung": masked_key, 
            "Cac_Model_Duoc_Phep_Dung": models
        }
    except Exception as e:
        return {
            "TrangThai": "KẾT NỐI THẤT BẠI", 
            "API_Key_Dang_Dung": masked_key, 
            "ChiTietLoi": str(e)
        }
