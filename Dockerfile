FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home portal
COPY --chown=portal:portal . .
RUN mkdir -p /app/instance && chown portal:portal /app/instance
USER portal
EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn --no-control-socket --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 60 'app:create_app()'"]
