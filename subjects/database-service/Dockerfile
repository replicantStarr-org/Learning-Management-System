FROM python:3.11-slim

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY init_db.py .

RUN python init_db.py

EXPOSE 6001

CMD ["python", "app.py"]
