from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.api import router
from app.config import settings
from app.db import Session, engine

# Redis uses server time windows; INCR and expiry run atomically across API instances.
RATE_SCRIPT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return n
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = Redis.from_url(settings().redis_url)
    yield
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(title='Vagou!', version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings().allowed_origins, allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], allow_headers=['Authorization', 'Content-Type'])


@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = None
    if request.url.path.startswith('/v1/'):
        # Trust forwarded IPs only through uvicorn's explicitly configured proxy list.
        ip = request.client.host if request.client else 'unknown'
        auth = request.url.path.startswith('/v1/auth/')
        try:
            count = await request.app.state.redis.eval(RATE_SCRIPT, 1, f'rate:{"auth" if auth else "api"}:{ip}', 60)
            if count > (10 if auth else 180):
                response = JSONResponse({'detail': 'Too many requests'}, status_code=429, headers={'Retry-After': '60'})
        except Exception:
            response = JSONResponse({'detail': 'Rate limiting temporarily unavailable'}, status_code=503)
    if response is None:
        response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@app.get('/health/live')
async def live():
    return {'status': 'alive'}


@app.get('/health/ready')
async def ready(request: Request):
    try:
        async with Session() as db:
            await db.execute(text('SELECT 1'))
        await request.app.state.redis.ping()
    except Exception:
        return JSONResponse({'status': 'unavailable'}, status_code=503)
    return {'status': 'ready'}


app.include_router(router)