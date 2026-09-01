FROM python:3.12-slim

WORKDIR /app/backend

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Chat replies come from a local language model, which regularly takes longer
# than gunicorn's 30 second default before the first byte is written.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "180", "app:app"]
