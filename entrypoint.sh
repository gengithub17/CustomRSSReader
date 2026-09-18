#!/bin/sh
set -e

mkdir -p /app/data
chown -R appuser:appuser /app/data

exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
