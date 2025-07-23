import httpx
import os
import sqlalchemy
import random
import asyncio
from fastapi import FastAPI, Response, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy import create_engine, Column, String, Integer
from collections import Counter

# --- Database Setup (Unchanged) ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local.db")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Like(Base): # Unchanged
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    image_url = Column(String, index=True)
    board = Column(String)

Base.metadata.create_all(bind=engine)

def get_db(): # Unchanged
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- FastAPI App Setup (Unchanged) ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Fetching & Caching ---
BOARDS_TO_FETCH = ['wg', 'w', 'hr', 'g', 'a', 'gif']
media_cache = {board: [] for board in BOARDS_TO_FETCH}
is_cache_populated = False # NEW: A flag to check if the background task is done

async def fetch_thread(client, board, thread_no): # Unchanged
    thread_posts = []
    # ... (rest of function is the same)
    try:
        thread_res = await client.get(f"https://a.4cdn.org/{board}/thread/{thread_no}.json")
        thread_res.raise_for_status()
        for post in thread_res.json()["posts"]:
            if "tim" in post and post.get("ext"):
                thread_posts.append({
                    "board": board, "post_id": post["no"],
                    "image_url": f"https://i.4cdn.org/{board}/{post['tim']}{post['ext']}",
                    "thumb_url": f"https://i.4cdn.org/{board}/{post['tim']}s.jpg",
                })
    except Exception:
        pass # Silently fail on single thread fetch
    return thread_posts

# This is the long-running task
async def populate_media_cache():
    global media_cache, is_cache_populated
    print("BACKGROUND TASK: Starting media cache population...")
    # ... (The core logic is the same, just moved into this function)
    async with httpx.AsyncClient(timeout=30.0) as client:
        for board in BOARDS_TO_FETCH:
            try:
                catalog_res = await client.get(f"https://a.4cdn.org/{board}/catalog.json")
                catalog_res.raise_for_status()
                thread_numbers = [thread["no"] for page in catalog_res.json() for thread in page["threads"]]
                tasks = [fetch_thread(client, board, thread_no) for thread_no in thread_numbers]
                results = await asyncio.gather(*tasks)
                all_board_posts = [post for thread_posts in results for post in thread_posts]
                random.shuffle(all_board_posts)
                media_cache[board] = all_board_posts
                print(f"-> Fetched {len(all_board_posts)} items for /{board}/")
            except Exception as e:
                print(f"Failed to process board /{board}/: {e}")
    is_cache_populated = True
    print("BACKGROUND TASK: Media cache population complete.")

# REWORKED: The startup event now starts the background task without waiting
@app.on_event("startup")
async def on_startup():
    print("Server starting up. Scheduling cache population.")
    asyncio.create_task(populate_media_cache())

# --- API Endpoints ---
@app.get("/boards")
def get_boards():
    return BOARDS_TO_FETCH

@app.get("/board/{board_name}")
def get_board_media(board_name: str, page: int = 1, limit: int = 21):
    # If cache is not ready, return empty list to prevent app from crashing
    if not is_cache_populated:
        return []

    if board_name not in media_cache:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    
    posts = media_cache[board_name]
    start_index = (page - 1) * limit
    end_index = start_index + limit
    return posts[start_index:end_index]

# ... (The rest of your endpoints: /image, /like, etc., can remain the same)
@app.get("/image")
async def get_image(url: str):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return Response(content=response.content, media_type=response.headers['content-type'])
        except httpx.HTTPStatusError:
            return Response(status_code=404)