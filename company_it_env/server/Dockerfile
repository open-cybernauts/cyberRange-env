FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENABLE_WEB_INTERFACE=true \
    PYTHONPATH=/app/env

WORKDIR /app/env

COPY . /app/env

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
