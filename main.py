import httpx
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
import math # Import the math module

app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ... (image proxy and parsing function are the same)
@app.get("/image")
async def get_image(url: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            image_bytes = response.content
            content_type = response.headers['content-type']
            return Response(content=image_bytes, media_type=content_type)
        else:
            return Response(status_code=status.HTTP_404_NOT_FOUND)

CHAN_IMAGE_BASE_URL = "https://i.4cdn.org/wg/"
CHAN_WG_CATALOG_URL = "https://a.4cdn.org/wg/catalog.json"

def parse_catalog_for_media(catalog_data: list) -> list:
    media_list = []
    for page in catalog_data:
        for thread in page["threads"]:
            if "tim" in thread:
                image_id = thread["tim"]
                extension = thread["ext"]
                if extension not in [".webm", ".mp4"]:
                    image_url = f"{CHAN_IMAGE_BASE_URL}{image_id}{extension}"
                    thumb_url = f"{CHAN_IMAGE_BASE_URL}{image_id}s.jpg"
                    media_list.append({
                        "post_id": thread["no"],
                        "image_url": image_url,
                        "thumb_url": thumb_url,
                        "post_text": thread.get("com", "")
                    })
    return media_list

# This is our main data cache
media_cache = []

@app.get("/")
async def get_wallpapers(page: int = 1, limit: int = 21):
    """
    Fetches media from the cache or 4chan and returns a paginated response.
    """
    global media_cache
    # If the cache is empty, fill it
    if not media_cache:
        async with httpx.AsyncClient() as client:
            response = await client.get(CHAN_WG_CATALOG_URL)
            response.raise_for_status()
            raw_data = response.json()
            media_cache = parse_catalog_for_media(raw_data)

    # Calculate start and end for pagination
    start_index = (page - 1) * limit
    end_index = start_index + limit
    
    # Return the requested page of data
    return media_cache[start_index:end_index]