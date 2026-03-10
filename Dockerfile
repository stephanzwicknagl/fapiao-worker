FROM python:3.13-slim

WORKDIR /app

# Install dependencies first (separate layer — cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py extract_fapiaos.py fill_excel.py gunicorn.conf.py ./
COPY templates/ templates/

# Unbuffered output so logs appear immediately in docker logs
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
