FROM python:3.12-slim
WORKDIR /app

# Install dependencies (you can still use requirements.txt)
COPY web_app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Don't copy the source code — will use bind mount instead

# Run Gunicorn to serve the Flask app
CMD ["gunicorn", "-w", "4", "-k", "gevent", "-b", "0.0.0.0:8000", "--timeout", "3600", "--graceful-timeout", "60", "--keep-alive", "75", "app:app"]