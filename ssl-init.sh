#!/bin/bash
# ssl-init.sh — One-time SSL certificate issuance for f1-chat.tomshaw.trentvision.cloud
# Run this script from the repo root on the server after initial deploy.
#
# Usage: bash ssl-init.sh <email>

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

echo "==> Force-resetting app.conf to bootstrap config..."
cp -f nginx/conf.d/app.conf.bootstrap nginx/conf.d/app.conf

echo "==> Bringing up stack with bootstrap config..."
docker compose up -d --force-recreate nginx

echo "==> Waiting for nginx to be ready..."
until curl -sf http://localhost/.well-known/acme-challenge/ > /dev/null 2>&1 || \
      curl -s http://localhost/ > /dev/null 2>&1; do
  echo "    nginx not ready yet, waiting..."
  sleep 2
done
echo "    nginx is ready."

echo "==> Requesting certificate for $DOMAIN..."
docker compose run --rm --entrypoint certbot certbot certonly \
  --webroot \
  --webroot-path /var/www/certbot \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  -d "$DOMAIN"

echo "==> Certificate issued. Switching to SSL config..."
cp -f nginx/conf.d/app.conf.ssl nginx/conf.d/app.conf

echo "==> Reloading nginx..."
docker compose exec nginx nginx -s reload

echo ""
echo "Done! https://$DOMAIN should now be serving with SSL."
