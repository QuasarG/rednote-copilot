FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-agent.txt .
RUN pip install --no-cache-dir -r requirements-agent.txt \
    && playwright install --with-deps chromium

COPY rednote_matrix ./rednote_matrix
COPY examples ./examples
COPY docs ./docs

ENV REDNOTE_DATA_DIR=/app/data
EXPOSE 8000 8501

CMD ["uvicorn", "rednote_matrix.server.api:app", "--host", "0.0.0.0", "--port", "8000"]
