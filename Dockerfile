FROM python:3.11-slim

WORKDIR /app

# System deps for Pillow (freetype, zlib, libjpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

# Runtime directories
RUN mkdir -p storage/drafts storage/uploads storage/cache/icons storage/outputs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
