FROM alpine:latest
RUN apk add --no-cache postgresql-dev cc musl-dev libffi-dev
COPY requirements.txt .
RUN pip install -r packages.txt
