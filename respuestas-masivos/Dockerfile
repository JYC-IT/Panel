FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8080

# Dependencias del sistema necesarias
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["gunicorn", "-w", "1", "--threads", "4", "--timeout", "180", "-b", "0.0.0.0:8080", "app:create_app()"]
