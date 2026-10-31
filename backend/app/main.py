from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.api import router
from app.config import settings
from app.db import Session, engine
from app.auth import router as auth_router
from app.moderation import router as moderation_router
from app.automation import router as automation_router
from app import automation_models
from app.smtp_transport import configure_smtp_logging

# Redis uses server time windows; INCR and expiry run atomically across API instances.
RATE_SCRIPT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return n
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_smtp_logging()
    app.state.redis = Redis.from_url(settings().redis_url)
    yield
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(title='Vagou!', version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings().allowed_origins, allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], allow_headers=['Authorization', 'Content-Type'])


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exception: RequestValidationError):
    # Never echo rejected passwords, codes or other PII from Pydantic's input.
    fields = []
    labels = {'password': 'senha', 'email': 'e-mail', 'name': 'nome',
              'company_cnpj': 'CNPJ', 'company_name': 'razão social',
              'company_contact_email': 'e-mail corporativo', 'phone': 'telefone',
              'company_phone': 'telefone corporativo', 'min_salary': 'pretensão salarial',
              'modalities': 'modalidade', 'titles': 'cargo de interesse',
              'skills': 'competências', 'completed_course_ids': 'cursos concluídos',
              'code': 'código de confirmação', 'locations': 'cidade/estado'}
    for error in exception.errors():
        field = str(error['loc'][-1])
        label = labels.get(field, 'campo informado')
        kind = error['type']
        if kind == 'string_too_short':
            message = f'O campo {label} precisa ter pelo menos {error.get("ctx", {}).get("min_length", 1)} caracteres.'
        elif kind == 'missing':
            message = f'Preencha o campo {label}.'
        elif field == 'email' or field.endswith('_email'):
            message = 'Informe um endereço de e-mail válido.'
        elif field == 'company_cnpj':
            message = 'Informe um CNPJ válido com 14 caracteres e dígitos verificadores corretos.'
        elif field in ('phone', 'company_phone'):
            message = 'Informe um telefone válido com DDD, como +5511999999999.'
        elif field == 'min_salary':
            message = 'Informe uma pretensão salarial válida, sem símbolos ou separadores incorretos.'
        elif field == 'locations':
            message = 'Informe cidade e estado, como Brasília / DF.'
        elif field == 'code':
            message = 'Digite o código de seis dígitos enviado ao seu e-mail.'
        else:
            message = f'Confira o campo {label} e tente novamente.'
        fields.append({'field': field, 'message': message})
    return JSONResponse({'detail': fields[0]['message'] if fields else 'Confira os dados informados.',
                         'errors': fields}, status_code=422)


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
app.include_router(auth_router)
app.include_router(moderation_router)
app.include_router(automation_router)
