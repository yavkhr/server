import hashlib
import os
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Настройка базы данных SQLite
DB_PATH = "database.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель пользователя для БД
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    salt = Column(String)

Base.metadata.create_all(bind=engine)

# Pydantic модели для API
class AuthRequest(BaseModel):
    username: str
    password: str

app = FastAPI(title="TacticWar2 Auth Server")

# Утилиты для хеширования
def hash_password(password: str, salt: str = None):
    if salt is None:
        salt = os.urandom(16).hex()
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return hashed, salt

# Dependency для получения сессии БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/register")
def register(request: AuthRequest, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == request.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="НИКНЕЙМ ЗАНЯТ")
    
    hashed_pwd, salt = hash_password(request.password)
    new_user = User(username=request.username, hashed_password=hashed_pwd, salt=salt)
    db.add(new_user)
    db.commit()
    return {"status": "ok", "message": "Регистрация успешна"}

@app.post("/login")
def login(request: AuthRequest, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == request.username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН")
    
    check_hash, _ = hash_password(request.password, db_user.salt)
    if check_hash != db_user.hashed_password:
        raise HTTPException(status_code=401, detail="НЕВЕРНЫЙ ПАРОЛЬ")
    
    return {"status": "ok", "username": db_user.username}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
