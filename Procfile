web: gunicorn diecastcollector.wsgi:application --log-file - --worker-tmp-dir /dev/shm --workers 2 --threads 8 --timeout 120
release: python manage.py migrate
