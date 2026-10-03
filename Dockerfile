FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
COPY pyproject.toml README.md constraints.txt ./
COPY orders_lab ./orders_lab
RUN pip install --no-cache-dir -c constraints.txt ".[postgres]" \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data /app/reports \
    && chown -R appuser:appuser /app/data /app/reports
USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "orders_lab.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
