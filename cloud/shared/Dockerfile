FROM python:3.12-slim
ARG SERVICE
WORKDIR /app
COPY ${SERVICE}/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY ${SERVICE}/ /app/
# The build context excludes developer secrets, datasets, logs, and virtualenvs.
