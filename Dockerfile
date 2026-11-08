FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 bili \
    && mkdir /app/data && chown bili:bili /app/data
COPY main.py bili_http_client.py ./
COPY static ./static
USER bili
EXPOSE 13678
CMD ["python", "-u", "main.py"]
