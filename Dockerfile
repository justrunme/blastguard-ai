FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN ./scripts/install_tools.sh && useradd -u 10001 -m app && chown -R app /app
USER 10001
EXPOSE 8501
# NEBIUS_API_KEY must be provided at runtime (e.g. docker run -e NEBIUS_API_KEY ...)
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
