# backend/Dockerfile

FROM python:3.11-slim AS builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .

EXPOSE 5000

CMD ["python", "-m", "gunicorn","--chdir", "/app","--log-file", "-","--log-level", "debug","--preload","run:app","-w", "1","-b", "0.0.0.0:5000"]