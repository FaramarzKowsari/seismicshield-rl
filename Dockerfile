FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY configs ./configs
COPY data ./data
COPY scripts ./scripts
RUN pip install --no-cache-dir ".[api]"
EXPOSE 8000
CMD ["uvicorn","seismicshield_rl.api.app:app","--host","0.0.0.0","--port","8000"]
