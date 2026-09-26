FROM python:3.12-slim

WORKDIR /app/backend

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Chat replies come from a local language model, which regularly takes longer
# than gunicorn's 30 second default before the first byte is written. Keep more
# than one worker: a RAG ingest waits on the RAG server while it calls back into
# this backend, and only another worker can answer that call.
CMD ["gunicorn", "--bind", "0.0.0.0:5002", "--workers", "4", "--timeout", "360", "app:app"]
