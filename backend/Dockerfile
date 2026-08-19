FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1
# Railway injects PORT; default kept for local runs
CMD ["sh", "-c", "uvicorn app.main:app --host :: --port ${PORT:-8080}"]
