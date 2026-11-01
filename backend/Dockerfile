FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

# Aumenta o timeout do pip para evitar quedas de conexão
RUN --mount=type=secret,id=proxy_ca \
    set -eu; \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir --default-timeout=1000 -r requirements.txt && \
    useradd --uid 10001 --create-home app && \
    mkdir -p /data/resumes && \
    chown app:app /data/resumes

COPY --chown=app:app . .

USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
