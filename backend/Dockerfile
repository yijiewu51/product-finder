FROM python:3.11-slim

WORKDIR /app

# Install lightweight deps only (no torch/sentence-transformers — too heavy for Railway)
COPY requirements.railway.txt .
RUN pip install --no-cache-dir -r requirements.railway.txt

COPY . .

ENV DATA_DIR=/app/data
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
