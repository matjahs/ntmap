FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend /app/backend
COPY www /app/www
COPY docker /app/docker
COPY docker-entrypoint.sh /app/docker-entrypoint.sh

RUN rm -f /etc/nginx/sites-enabled/default \
    && ln -s /app/docker/nginx.conf /etc/nginx/sites-enabled/ntmap.conf \
    && chmod +x /app/docker-entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/app/docker-entrypoint.sh"]
