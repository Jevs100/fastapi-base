FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app



# Copy project
# Copy only the `app` directory (and the entrypoint script) into the image
COPY ./app .
COPY .config/entrypoint.sh /usr/local/bin/entrypoint.sh

# Copy requirements and install system build deps required to compile some Python packages (e.g. mysqlclient)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       gcc \
       pkg-config \
       default-libmysqlclient-dev \
       libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt


# Ensure entrypoint script is executable
RUN chmod +x /usr/local/bin/entrypoint.sh

# Create a non-root user and give ownership of the app directory
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Install entrypoint into a system bin dir so it's not hidden by a volume mount
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
