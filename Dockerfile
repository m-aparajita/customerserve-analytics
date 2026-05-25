# HuggingFace Spaces Docker runtime
FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# HuggingFace Spaces exposes port 7860
EXPOSE 7860

# Store DuckDB file alongside the CSV data files (no persistent storage needed)
ENV DB_PATH=/app/Data/customerserve.duckdb
ENV DATA_DIR=/app/Data

CMD ["python", "app.py"]
