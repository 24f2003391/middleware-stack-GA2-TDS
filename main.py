import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Middleware Stack API")

EMAIL = "24f2003391@ds.study.iitm.ac.in"
RATE_LIMIT = 11
WINDOW_SECONDS = 10

ALLOWED_ORIGINS = [
    "https://app-n485jv.example.com",
    "https://exam.sanand.workers.dev",
]

# Store recent request times separately for each client ID.
request_times = defaultdict(deque)
rate_limit_lock = Lock()


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # CORS preflight requests should not consume a client's rate-limit quota.
    if request.method == "OPTIONS":
        return await call_next(request)

    client_id = request.headers.get("X-Client-Id")
    if not client_id:
        client_id = request.client.host if request.client else "unknown"

    now = time.monotonic()

    with rate_limit_lock:
        timestamps = request_times[client_id]

        # Remove requests that are outside the rolling 10-second window.
        while timestamps and now - timestamps[0] >= WINDOW_SECONDS:
            timestamps.popleft()

        if len(timestamps) >= RATE_LIMIT:
            retry_after = max(
                1,
                int(WINDOW_SECONDS - (now - timestamps[0])) + 1,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)

    return await call_next(request)


# Only these origins receive Access-Control-Allow-Origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["X-Request-ID", "X-Client-Id"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    # Preserve a supplied request ID; otherwise generate a UUID4.
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/ping")
async def ping(request: Request):
    return {
        "email": EMAIL,
        "request_id": request.state.request_id,
    }


@app.get("/")
async def home():
    return {
        "service": "Middleware Stack API",
        "endpoint": "/ping",
        "status": "ok",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
