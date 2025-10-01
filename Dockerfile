# SQL-Guardian Dockerfile
# Multi-stage Docker build for production deployment

# Start from a lean, official Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /code

# Copy requirements.txt first for optimal Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the setup_databases.py script
COPY setup_databases.py .

# Execute setup_databases.py to ensure .db files are created within the image
# This makes the container fully self-contained
RUN python setup_databases.py

# Copy the entire ./app directory into the working directory
COPY ./app ./app

# Expose the application port
EXPOSE 8000

# Set the final CMD to run the application using uvicorn
# Bind to 0.0.0.0 to be accessible from outside the container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]