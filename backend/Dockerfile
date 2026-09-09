FROM python:3.11-slim

WORKDIR /app

# System dependencies for psycopg2, docling, and general build tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    cmake \
    git \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
