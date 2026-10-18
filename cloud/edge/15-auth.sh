#!/bin/sh
set -eu
: "${AUTH_HTPASSWD:?An authentication hash is required}"
umask 077
printf '%s\n' "$AUTH_HTPASSWD" > /etc/nginx/htpasswd
chown root:nginx /etc/nginx/htpasswd
chmod 640 /etc/nginx/htpasswd
unset AUTH_HTPASSWD
