FROM python:3.12-slim

WORKDIR /agentic-loop

# Progress is printed as each step of the loop finishes, which is only useful if
# it is not sitting in a buffer until the run ends.
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "agentic_loop.py"]
