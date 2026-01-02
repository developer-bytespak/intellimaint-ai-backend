FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including ffmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY services/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --retries 5

# Copy application code
COPY services/ .

# Copy chunking scripts needed for PDF processing
COPY scripts/chunking/pdf_universal_chunker.py /app/scripts/chunking/

# Expose port 8000
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

