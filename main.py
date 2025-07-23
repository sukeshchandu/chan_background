import httpx
import os
import sqlalchemy
import random
import asyncio # Import asyncio for concurrent requests
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

# --- FastAPI App Setup (Unchanged) ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- NEW: Advanced Data Fetching & Caching ---
BOARDS_TO_FETCH = ['wg', 'w', 'hr', 'g', 'a', 'gif'] # Added /gif/ board
media_cache = {board: [] for board in BOARDS_TO_FETCH}

async def fetch_thread(client, board, thread_no):
    """Fetches all posts from a single thread."""
    thread_posts = []
    try:
        thread_res = await client.get(f"https://a.4cdn.org/{board}/thread/{thread_no}.json")
        thread_res.raise_for_status()
        thread_data = thread_res.json()
        for post in thread_data["posts"]:
            if "tim" in post and post.get("ext"): # Check for image and extension
                thread_posts.append({
                    "board": board,
                    "post_id": post["no"],
                    "image_url": f"https://i.4cdn.org/{board}/{post['tim']}{post['ext']}",
                    "thumb_url": f"https://i.4cdn.org/{board}/{post['tim']}s.jpg",
                })
    except Exception as e:
        print(f"Could not fetch thread {thread_no} from /{board}/: {e}")
    return thread_posts

@app.on_event("startup")
async def populate_media_cache():
    print("Populating media cache from 4chan for boards:", BOARDS_TO_FETCH)
    async with httpx.AsyncClient(timeout=30.0) as client:
        for board in BOARDS_TO_FETCH:
            try:
                # 1. Get the list of thread numbers from the catalog
                catalog_res = await client.get(f"https://a.4cdn.org/{board}/catalog.json")
                catalog_res.raise_for_status()
                catalog_data = catalog_res.json()
                thread_numbers = [thread["no"] for page in catalog_data for thread in page["threads"]]
                
                # 2. Create tasks to fetch all threads concurrently
                tasks = [fetch_thread(client, board, thread_no) for thread_no in thread_numbers]
                
                # 3. Run all tasks and wait for them to complete
                results = await asyncio.gather(*tasks)
                
                # 4. Flatten the list of lists into a single list of posts
                all_board_posts = [post for thread_posts in results for post in thread_posts]
                random.shuffle(all_board_posts) # Shuffle posts for variety
                media_cache[board] = all_board_posts
                print(f"-> Fetched {len(all_board_posts)} items for /{board}/")
            except Exception as e:
                print(f"Failed to process board /{board}/: {e}")
    print("Media cache populated.")


# --- API Endpoints (Unchanged) ---
@app.get("/boards")
def get_boards():
    return BOARDS_TO_FETCH

@app.get("/board/{board_name}")
def get_board_media(board_name: str, page: int = 1, limit: int = 21):
    if board_name not in media_cache:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    posts = media_cache[board_name]
    start_index = (page - 1) * limit
    end_index = start_index + limit
    return posts[start_index:end_index]

# ... (The rest of your endpoints: /image, /like, etc., can remain the same)