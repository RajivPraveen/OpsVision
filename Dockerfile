FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN python -m pip install --no-cache-dir . \
    && useradd --create-home opsvision \
    && mkdir -p /app/data /app/reports /app/exports \
    && chown -R opsvision:opsvision /app/data /app/reports /app/exports

USER opsvision
EXPOSE 8000
CMD ["opsvision", "serve", "--host", "0.0.0.0", "--port", "8000"]

