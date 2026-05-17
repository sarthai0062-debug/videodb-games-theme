FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
RUN mkdir -p data/sessions data/sandbox_sessions

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV SERVE_STATIC=false

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
