

import httpx
import os
import sqlalchemy
import random
from fastapi import FastAPI, Response, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker, Session, declarative_base # CORRECTED: Added declarative_base import
from sqlalchemy import create_engine, Column, String, Integer
from collections import Counter

# --- Database Setup ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local.db")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base() # This line will now work correctly

class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    image_url = Column(String, index=True)
    board = Column(String)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- FastAPI App Setup ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Fetching & Caching ---
BOARDS_TO_FETCH = ['wg', 'w', 'hr', 'g', 'a'] 
media_cache = {board: [] for board in BOARDS_TO_FETCH}

@app.on_event("startup")
async def populate_media_cache():
    print("Populating media cache from 4chan for boards:", BOARDS_TO_FETCH)
    async with httpx.AsyncClient() as client:
        for board in BOARDS_TO_FETCH:
            try:
                response = await client.get(f"https://a.4cdn.org/{board}/catalog.json")
                response.raise_for_status()
                raw_data = response.json()
                board_posts = []
                for page in raw_data:
                    for thread in page["threads"]:
                        if "tim" in thread and thread.get("ext") not in [".webm", ".mp4"]:
                            board_posts.append({
                                "board": board,
                                "post_id": thread["no"],
                                "image_url": f"https://i.4cdn.org/{board}/{thread['tim']}{thread['ext']}",
                                "thumb_url": f"https://i.4cdn.org/{board}/{thread['tim']}s.jpg",
                            })
                media_cache[board] = board_posts
                print(f"-> Fetched {len(board_posts)} items for /{board}/")
            except Exception as e:
                print(f"Failed to fetch from board /{board}/: {e}")
    print("Media cache populated.")

# --- API Endpoints ---
@app.get("/boards")
def get_boards():
    """Returns the list of available boards."""
    return BOARDS_TO_FETCH

@app.get("/board/{board_name}")
def get_board_media(board_name: str, page: int = 1, limit: int = 21):
    """Returns a paginated list of media for a specific board."""
    if board_name not in media_cache:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    
    posts = media_cache[board_name]
    start_index = (page - 1) * limit
    end_index = start_index + limit
    
    return posts[start_index:end_index]

@app.get("/image")
async def get_image(url: str):
    """Proxy for fetching images."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            return Response(content=response.content, media_type=response.headers['content-type'])
        else:
            return Response(status_code=status.HTTP_404_NOT_FOUND)

@app.post("/like")
def like_image(like_data: dict, db: Session = Depends(get_db)):
    # Check if like already exists to prevent duplicates
    existing_like = db.query(Like).filter(Like.user_id == like_data["user_id"], Like.image_url == like_data["image_url"]).first()
    if existing_like:
        return existing_like

    new_like = Like(user_id=like_data["user_id"], image_url=like_data["image_url"], board=like_data["board"])
    db.add(new_like)
    db.commit()
    db.refresh(new_like)
    return new_like