import hashlib
import os
import datetime
import random
import string
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, DateTime, JSON
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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_action = Column(DateTime, default=datetime.datetime.utcnow)
    level = Column(Integer, default=1)
    wins = Column(Integer, default=0)
    
# Модель игровой сессии (лобби)
class GameSession(Base):
    __tablename__ = "game_sessions"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    host_name = Column(String)
    guest_name = Column(String, nullable=True)
    status = Column(String, default="waiting") # waiting, playing, finished
    settings = Column(JSON) # Настройки карты, юнитов и т.д.
    seed = Column(Integer) # Сид для генерации мира
    current_turn = Column(String) # Имя игрока, чей сейчас ход
    last_move = Column(JSON, nullable=True) # Данные о последнем сделанном ходе
    board_state = Column(JSON, nullable=True) # Полное состояние поля (юниты, позиции, hp)
    last_update = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Pydantic модели для API
class AuthRequest(BaseModel):
    username: str
    password: str

class CreateGameRequest(BaseModel):
    host_name: str
    settings: dict

class JoinGameRequest(BaseModel):
    guest_name: str
    code: str

class MoveRequest(BaseModel):
    username: str
    move_data: dict
    end_turn: bool = False

class BoardUpdateRequest(BaseModel):
    username: str
    board_state: dict

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
    
    return {
        "status": "ok", 
        "username": db_user.username,
        "created_at": db_user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "level": db_user.level,
        "wins": db_user.wins
    }

@app.get("/profile/{username}")
def get_profile(username: str, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН")
    
    return {
        "status": "ok",
        "username": db_user.username,
        "created_at": db_user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "level": db_user.level,
        "wins": db_user.wins
    }

@app.post("/report_win/{username}")
def report_win(username: str, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН")
    
    db_user.wins += 1
    # Добавим логику уровня: каждые 5 побед - новый уровень
    db_user.level = 1 + (db_user.wins // 5)
    db_user.last_action = datetime.datetime.utcnow()
    
    db.commit()
    return {"status": "ok", "wins": db_user.wins, "level": db_user.level}

@app.post("/log_action/{username}")
def log_action(username: str, action: str, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН")
    
    db_user.last_action = datetime.datetime.utcnow()
    # Здесь можно было бы сохранять саму строку действия в отдельную таблицу логов,
    # но пока просто обновим время последней активности.
    db.commit()
    print(f"Action logged for {username}: {action}")
    return {"status": "ok"}

# --- МУЛЬТИПЛЕЕР ---

@app.post("/create_game")
def create_game(request: CreateGameRequest, db: Session = Depends(get_db)):
    # Генерация уникального кода из 6 цифр
    while True:
        code = ''.join(random.choices(string.digits, k=6))
        if not db.query(GameSession).filter(GameSession.code == code).first():
            break
            
    game_seed = random.randint(0, 1000000)
    new_session = GameSession(
        code=code,
        host_name=request.host_name,
        settings=request.settings,
        seed=game_seed,
        current_turn=request.host_name,
        status="waiting"
    )
    db.add(new_session)
    db.commit()
    return {"status": "ok", "code": code, "seed": game_seed}

@app.post("/join_game")
def join_game(request: JoinGameRequest, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.code == request.code).first()
    if not session:
        raise HTTPException(status_code=404, detail="ИГРА НЕ НАЙДЕНА")
    if session.guest_name:
        raise HTTPException(status_code=400, detail="ИГРА УЖЕ ЗАПОЛНЕНА")
    if session.host_name == request.guest_name:
        raise HTTPException(status_code=400, detail="НЕЛЬЗЯ ИГРАТЬ С САМИМ СОБОЙ")
        
    session.guest_name = request.guest_name
    session.last_update = datetime.datetime.utcnow()
    db.commit()
    return {"status": "ok", "settings": session.settings, "host_name": session.host_name, "seed": session.seed}

@app.get("/game_status/{code}")
def game_status(code: str, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.code == code).first()
    if not session:
        raise HTTPException(status_code=404, detail="ИГРА НЕ НАЙДЕНА")
        
    return {
        "status": session.status,
        "host_name": session.host_name,
        "guest_name": session.guest_name,
        "current_turn": session.current_turn,
        "last_move": session.last_move,
        "board_state": session.board_state,
        "seed": session.seed
    }

@app.post("/update_board/{code}")
def update_board(code: str, request: BoardUpdateRequest, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.code == code).first()
    if not session:
        raise HTTPException(status_code=404, detail="ИГРА НЕ НАЙДЕНА")
    
    # Обновляем состояние доски
    session.board_state = request.board_state
    
    # Синхронизируем текущий ход из board_state, если он там есть
    if request.board_state and isinstance(request.board_state, dict):
        # Если пришел флаг host_turn (кто сейчас ходит по мнению клиента)
        # Мы доверяем хосту в плане переключения ходов
        client_turn = request.board_state.get('turn')
        if client_turn:
            # Превращаем 'blue'/'red' обратно в имена пользователей
            if client_turn == 'blue':
                session.current_turn = session.host_name
            elif client_turn == 'red':
                session.current_turn = session.guest_name
                
    session.last_update = datetime.datetime.utcnow()
    db.commit()
    return {"status": "ok"}

@app.post("/make_move/{code}")
def make_move(code: str, request: MoveRequest, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.code == code).first()
    if not session:
        raise HTTPException(status_code=404, detail="ИГРА НЕ НАЙДЕНА")
    if session.current_turn != request.username:
        raise HTTPException(status_code=400, detail="СЕЙЧАС НЕ ВАШ ХОД")
        
    session.last_move = request.move_data
    
    # Передача хода только если end_turn=True
    if request.end_turn:
        session.current_turn = session.guest_name if request.username == session.host_name else session.host_name
        
    session.last_update = datetime.datetime.utcnow()
    db.commit()
    return {"status": "ok"}

@app.post("/finish_game/{code}")
def finish_game(code: str, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.code == code).first()
    if session:
        session.status = "finished"
        db.commit()
    return {"status": "ok"}

@app.post("/abort_game/{code}")
def abort_game(code: str, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.code == code).first()
    if session:
        session.status = "aborted"
        db.commit()
    return {"status": "ok"}

@app.post("/start_game/{code}")
def start_game(code: str, db: Session = Depends(get_db)):
    session = db.query(GameSession).filter(GameSession.code == code).first()
    if not session:
        raise HTTPException(status_code=404, detail="ИГРА НЕ НАЙДЕНА")
    
    session.status = "playing"
    # Случайный выбор первого игрока
    session.current_turn = random.choice([session.host_name, session.guest_name])
    session.last_update = datetime.datetime.utcnow()
    db.commit()
    return {"status": "ok", "first_turn": session.current_turn}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
