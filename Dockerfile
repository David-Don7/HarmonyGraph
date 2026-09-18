FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_ROOT=/app/data
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY harmonygraph ./harmonygraph
COPY migrations ./migrations
COPY alembic.ini ./
COPY data/demo ./data/demo
RUN pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home harmony && mkdir -p /app/artifacts /app/data/imports && chown -R harmony:harmony /app
USER harmony
CMD ["uvicorn", "harmonygraph.api:app", "--host", "0.0.0.0", "--port", "8000"]
