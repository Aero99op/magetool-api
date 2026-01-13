# Magetool Backend - Hugging Face Spaces
FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libmagic1 \
    tesseract-ocr \
    poppler-utils \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (HF Spaces requirement)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Set working directory
WORKDIR $HOME/app

# Copy requirements first for caching
COPY --chown=user:user requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade yt-dlp

# Copy all app code
COPY --chown=user:user . .

# Create temp directory
RUN mkdir -p temp

# Expose port (HF uses 7860)
EXPOSE 7860

# Run FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
