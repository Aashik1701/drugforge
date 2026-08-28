FROM python:3.10-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the ML models and code
COPY src/app.py /app/
COPY src/solubility_model.pkl /app/

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_DEBUG=0
ENV FLASK_PORT=5000
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose the port
EXPOSE 5000

# Run gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
