FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home portal
COPY --chown=portal:portal . .
RUN test -f templates/login.html && test -f templates/questionnaire.html && test -f static/styles.css && test -f static/brand.css && test -f static/favicon.svg && test -f static/app.js && test -f assets/fonts/DejaVuSans.ttf && test -f assets/fonts/DejaVuSans-Bold.ttf
RUN mkdir -p /app/instance && chown portal:portal /app/instance
USER portal
EXPOSE 8080
CMD ["sh", "start-web.sh"]
