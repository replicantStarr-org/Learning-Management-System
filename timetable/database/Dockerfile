FROM python:3.11-slim

WORKDIR /app

RUN --mount=type=bind,source=init_db.py,target=/app/init_db.py \
    python init_db.py

RUN --mount=type=bind,source=requirements.txt,target=/app/requirements.txt \
    pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 6005

CMD ["python", "app.py"]
