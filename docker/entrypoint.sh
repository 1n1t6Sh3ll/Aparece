#!/bin/sh
# Start as root only to make /data (a Fly volume mounts root-owned) writable, then run as app.
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data
  chown -R 10001:10001 /data
  exec setpriv --reuid=10001 --regid=10001 --init-groups "$@"
fi
exec "$@"
