import asyncio
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Union

import websockets
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


# ----------------------------
# Utility Functions
# ----------------------------

def combine_items_by_name(items):
    """Combine items with the same name by summing their quantities."""
    combined = defaultdict(int)
    for item in items:
        combined[item["name"]] += item.get("quantity", 0)
    return [{"name": name, "quantity": qty} for name, qty in combined.items()]


def clean_items(items, keys_to_keep={"name", "quantity"}):
    """Strip extraneous keys from items, retaining only those in keys_to_keep."""
    return [{k: item[k] for k in keys_to_keep if k in item} for item in items]


# ----------------------------
# Global Data Store
# ----------------------------

latest_data = {
    "weather": {},
    "gear": [],
    "seeds": [],
    "eggs": [],
    "honey": [],
    "cosmetics": [],
    "timestamp": 0,
}


# ----------------------------
# WebSocket Listener
# ----------------------------

async def websocket_listener():
    """Connects to the live stock WebSocket and updates global data."""
    uri = "wss://ws.growagardenpro.com/"

    while True:
        try:
            async with websockets.connect(uri) as websocket:
                print("API WebSocket Connected.")
                async for message in websocket:
                    data = json.loads(message)
                    if data.get("type"):
                        latest_data.update(data["data"])
                        latest_data["timestamp"] = int(asyncio.get_event_loop().time())

                        for category in ["gear", "seeds", "cosmetics", "honey"]:
                            if category in latest_data:
                                latest_data[category] = clean_items(latest_data[category])
                        if "eggs" in latest_data:
                            latest_data["eggs"] = combine_items_by_name(latest_data["eggs"])
        except Exception as e:
            print(f"WebSocket error: {e}. Retrying in 5s...")
            await asyncio.sleep(5)


# ----------------------------
# App Initialization
# ----------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(websocket_listener())
    yield


app = FastAPI(
    title="Grow a Garden API",
    description="An API that provides live stock and weather data from Grow a Garden.",
    version="1.0.0",
    lifespan=lifespan,
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    docs_url=None,
)

# Static & CORS
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ----------------------------
# Routes
# ----------------------------

@app.get("/docs", include_in_schema=False)
async def swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Grow a Garden API",
        swagger_favicon_url="/assets/Logo.ico"
    )


@app.get("/", summary="Health Check", description="Returns a simple status to verify the API is online.")
@limiter.limit("5/minute")
async def root(request: Request):
    return {"status": "200"}


@app.get("/alldata", summary="Get All Stock Data", description="Returns the complete currently collected data, including gear, seeds, eggs, cosmetics, event, and weather.")
@limiter.limit("5/minute")
async def alldata(request: Request):
    return latest_data


@app.get("/gear", summary="Get Gear Stock", description="Returns the list of gear currently in stock.")
@limiter.limit("5/minute")
async def get_gear(request: Request):
    return latest_data.get("gear", [])


@app.get("/seeds", summary="Get Seed Stock", description="Returns the list of seeds currently in stock.")
@limiter.limit("5/minute")
async def get_seeds(request: Request):
    return latest_data.get("seeds", [])


@app.get("/cosmetics", summary="Get Cosmetics Stock", description="Returns the list of cosmetic items currently in stock.")
@limiter.limit("5/minute")
async def get_cosmetics(request: Request):
    return latest_data.get("cosmetics", [])


@app.get("/eventshop", summary="Get Event Shop Stock", description="Returns the list of event shop items currently in stock.")
@limiter.limit("5/minute")
async def get_eventshop(request: Request):
    return latest_data.get("honey", [])


@app.get("/eggs", summary="Get Eggs Stock", description="Returns the list of available eggs and their quantities.")
@limiter.limit("5/minute")
async def get_eggs(request: Request):
    return latest_data.get("eggs", [])


@app.get("/weather", summary="Get Current Weather", description="Returns the current in-game weather and its effects.")
@limiter.limit("5/minute")
async def get_weather(request: Request):
    return latest_data.get("weather", {})
