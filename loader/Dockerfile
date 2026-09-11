FROM python:3.11-slim

WORKDIR /app

RUN useradd -m -u 10001 appuser && \
    chown -R appuser:appuser /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY loader.py .

USER appuser

CMD ["python", "-u", "loader.py"]
