FROM python:3.12-slim
WORKDIR /app

# Install dependencies (you can still use requirements.txt)
COPY python-requirements.txt .
RUN pip install --no-cache-dir -r python-requirements.txt

# Don't copy the source code — will use bind mount instead

# Run Gunicorn to serve the Flask app
CMD ["gunicorn", "-w", "2", "-k", "gevent", "-b", "0.0.0.0:8000", "--timeout", "180", "app:app"]