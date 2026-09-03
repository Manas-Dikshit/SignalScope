#!/bin/sh
set -e
exec celery -A app.tasks worker --loglevel=info --concurrency=2
