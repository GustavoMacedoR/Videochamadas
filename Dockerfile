FROM python:3.11-slim

# Environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip
RUN pip install -r /app/requirements.txt \
  && pip install "uvicorn[standard]" daphne gunicorn

# Copy project
COPY . /app

# Entrypoint for migrations / collectstatic
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

CMD ["uvicorn", "video_backend.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
