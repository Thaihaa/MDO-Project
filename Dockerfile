# Restaurant Microservices Deployment Orchestrator
# Multi-stage build để optimize image size

# Build stage
FROM python:3.9-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first để leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.9-slim

# Set metadata
LABEL maintainer="restaurant-team@company.com"
LABEL description="Restaurant Microservices Deployment Orchestrator"
LABEL version="1.0.0"

# Set working directory
WORKDIR /app

# Create non-root user
RUN groupadd -r deployuser && useradd -r -g deployuser deployuser

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder stage
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/temp && \
    chown -R deployuser:deployuser /app

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV AWS_DEFAULT_REGION=us-east-1

# Switch to non-root user
USER deployuser

# Expose port (cho dashboard web interface nếu cần)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import boto3; print('Health check passed')" || exit 1

# Default command
CMD ["python", "src/deployment_orchestrator.py", "--help"] 