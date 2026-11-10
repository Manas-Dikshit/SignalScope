FROM python:3.12-slim

ARG INSTALL_TRANSFORMERS=0

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/ai/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/ai/requirements-transformers.txt /tmp/requirements-transformers.txt
RUN if [ "$INSTALL_TRANSFORMERS" = "1" ]; then \
        pip install --no-cache-dir -r /tmp/requirements-transformers.txt; \
    fi

COPY services/ai/app /app/app

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8100/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
