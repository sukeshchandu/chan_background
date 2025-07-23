from dotenv import load_dotenv
load_dotenv()


import httpx
import os
import sqlalchemy
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, Column, String, Integer

# --- Database Setup ---
DATABASE_URL = os.getenv("database_url")
# The DATABASE_URL from Render starts with postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Define our "likes" table model
class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    image_url = Column(String, unique=True)

# Create the table in the database
Base.metadata.create_all(bind=engine)

# --- FastAPI App Setup ---
app = FastAPI()

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Endpoints ---
@app.post("/like")
def like_image(like: dict):
    db = SessionLocal()
    # A simple way to add a like. We will improve this later.
    new_like = Like(user_id=like["user_id"], image_url=like["image_url"])
    db.add(new_like)
    db.commit()
    db.refresh(new_like)
    db.close()
    return {"status": "liked", "image_url": new_like.image_url}

# ... (The rest of your endpoints remain the same for now)
@app.get("/image")
async def get_image(url: str):
    # ... (code is unchanged)
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            image_bytes = response.content
            content_type = response.headers['content-type']
            return Response(content=image_bytes, media_type=content_type)
        else:
            return Response(status_code=status.HTTP_404_NOT_FOUND)

media_cache = []

@app.get("/")
async def get_wallpapers(page: int = 1, limit: int = 21):
    # ... (code is unchanged)
    global media_cache
    if not media_cache:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://a.4cdn.org/wg/catalog.json")
            response.raise_for_status()
            raw_data = response.json()
            media_list = []
            for p in raw_data:
                for thread in p["threads"]:
                    if "tim" in thread and thread["ext"] not in [".webm", ".mp4"]:
                        media_list.append({
                            "post_id": thread["no"],
                            "image_url": f"https://i.4cdn.org/wg/{thread['tim']}{thread['ext']}",
                            "thumb_url": f"https://i.4cdn.org/wg/{thread['tim']}s.jpg",
                            "post_text": thread.get("com", "")
                        })
            media_cache = media_list
    start_index = (page - 1) * limit
    end_index = start_index + limit
    return media_cache[start_index:end_index]