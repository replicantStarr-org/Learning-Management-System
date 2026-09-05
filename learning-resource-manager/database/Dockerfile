FROM python:3.12-slim

WORKDIR /app/database

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# The database file is built on first start rather than at build time, because
# it lives on a volume that only exists once the container runs.
#
# One worker, because SQLite takes a write lock over the whole file: extra
# processes would queue behind each other rather than write in parallel. Threads
# are what lets the backend's workers be served at the same time.
CMD ["sh", "-c", "python database_init.py && exec gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 8 --timeout 60 app:app"]
