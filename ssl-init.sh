#!/bin/bash
# ssl-init.sh — One-time SSL certificate issuance for f1-chat.tomshaw.trentvision.cloud
# Run this script from the repo root on the server after initial deploy.
#
# Usage: bash ssl-init.sh

set -e

DOMAIN="f1-chat.tomshaw.trentvision.cloud"
EMAIL="${1:-}"

if [ -z "$EMAIL" ]; then
  echo "Usage: bash ssl-init.sh <your-email>"
  echo "Example: bash ssl-init.sh tom@trentvision.co.uk"
  exit 1
fi

echo "==> Ensuring certbot directories exist..."
mkdir -p nginx/certbot/www/.well-known/acme-challenge
mkdir -p nginx/certbot/conf

echo "==> Switching to bootstrap nginx config..."
cp nginx/conf.d/app.conf.bootstrap nginx/conf.d/app.conf

echo "==> Bringing up stack with bootstrap config..."
docker compose up -d --force-recreate nginx

echo "==> Waiting for nginx to be ready..."
sleep 5

echo "==> Requesting certificate for $DOMAIN..."
docker compose run --rm --entrypoint certbot certbot certonly \
  --webroot \
  --webroot-path /var/www/certbot \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  -d "$DOMAIN"

echo "==> Certificate issued. Switching to SSL config..."
cp nginx/conf.d/app.conf.ssl nginx/conf.d/app.conf

echo "==> Reloading nginx..."
docker compose exec nginx nginx -s reload

echo ""
echo "Done! https://$DOMAIN should now be serving with SSL."
