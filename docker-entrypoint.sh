#!/bin/sh
set -eu

NTMAP_DB_HOST="${NTMAP_DB_HOST:-ntmap-db}"
NTMAP_DB_PORT="${NTMAP_DB_PORT:-5432}"
NTMAP_DB_NAME="${NTMAP_DB_NAME:-ntmap}"
NTMAP_DB_USER="${NTMAP_DB_USER:-ntmap}"
MAX_OBJECTS_AT_ONE_LEVEL="${MAX_OBJECTS_AT_ONE_LEVEL:-100}"
NTMAP_BACKEND_URI="${NTMAP_BACKEND_URI:-/data}"

if [ -z "${NTMAP_DB_PASSWORD:-}" ]; then
  echo "NTMAP_DB_PASSWORD is required" >&2
  exit 1
fi

if [ -z "${NETBOX_URL:-}" ] || [ -z "${NETBOX_TOKEN:-}" ]; then
  echo "NETBOX_URL and NETBOX_TOKEN are required" >&2
  exit 1
fi

# Escape single quotes for INI/JS string literals
escape_sq() {
  printf '%s' "$1" | sed "s/'/\\\\'/g"
}

NB_URL_ESC="$(escape_sq "$NETBOX_URL")"
NB_TOKEN_ESC="$(escape_sq "$NETBOX_TOKEN")"
DB_PASS_ESC="$(escape_sq "$NTMAP_DB_PASSWORD")"

cat > /app/backend/app/settings.ini <<EOF
[ntmap]
db = dbname='${NTMAP_DB_NAME}' user='${NTMAP_DB_USER}' host='${NTMAP_DB_HOST}' port='${NTMAP_DB_PORT}' password='${DB_PASS_ESC}'
max_objects_at_one_level = ${MAX_OBJECTS_AT_ONE_LEVEL}

[netbox]
url = ${NB_URL_ESC}
token = ${NB_TOKEN_ESC}
EOF

cat > /app/www/js/settings.js <<EOF
var NTMAP_BACKEND_URI = "${NTMAP_BACKEND_URI}";
var NETBOX_URL = "${NB_URL_ESC}";

// Key: device type in Netbox, value: SVG-image in /www/img directory
// If device with some other device type is selected from Netbox to be displayed on a map, "unknown.svg" image will be chosen
// You can add your own device types and their images here
// Note: use only SVG-images with dimensions 32 x 32 pixels
var DEVICE_ROLES = {
  "Router": "router.svg",
  "Firewall": "firewall.svg",
  "IPS": "ips.svg",
  "Server": "server.svg",
  "Encryption Gateway": "cryptogw.svg",
  "SAN Switch": "sanswitch.svg",
  "Switch": "switch.svg",
  "Blade Switch": "mngswitch.svg",
  "Management Switch": "mngswitch.svg",
  "Switch Chassis": "coreswitch.svg",
  "VRSG": "vrsg.svg",
  "Storage System": "storage.svg",
  "Tape Library": "tapelibrary.svg",
  "Load Balancer": "loadbalancer.svg",
  "Unknown": "unknown.svg"
}
EOF

GUNICORN_PID=""

shutdown() {
  if [ -n "$GUNICORN_PID" ] && kill -0 "$GUNICORN_PID" 2>/dev/null; then
    kill -TERM "$GUNICORN_PID" 2>/dev/null || true
    wait "$GUNICORN_PID" 2>/dev/null || true
  fi
  exit 0
}

trap shutdown TERM INT

cd /app/backend
gunicorn --pythonpath . --config /app/docker/gunicorn.py wsgi &
GUNICORN_PID=$!

nginx -g 'daemon off;' &
NGINX_PID=$!

wait "$NGINX_PID"
shutdown
