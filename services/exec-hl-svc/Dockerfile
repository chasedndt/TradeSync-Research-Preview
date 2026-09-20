FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY services/exec-hl-svc/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared library, installed as signer-svc and state-api install it: the caller
# tokens for the order route and for the signer (tradesync_core.service_tokens).
COPY libs/tradesync_core /tmp/tradesync_core
RUN pip install --no-cache-dir /tmp/tradesync_core && rm -rf /tmp/tradesync_core

COPY services/exec-hl-svc/app /app/app

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
