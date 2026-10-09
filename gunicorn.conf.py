"""gunicorn settings for production (inside the container)."""
import multiprocessing

bind = "0.0.0.0:8000"
workers = min(4, multiprocessing.cpu_count() * 2)
threads = 2
worker_class = "gthread"
worker_tmp_dir = "/dev/shm"          # root filesystem is read-only
timeout = 30
graceful_timeout = 20
keepalive = 5
max_requests = 2000                   # recycle workers regularly
max_requests_jitter = 200
# request size/shape limits (defence against malformed / slowloris-style requests)
limit_request_line = 4094
limit_request_fields = 60
limit_request_field_size = 8190
# the container is only reachable from Caddy on a private Docker network
forwarded_allow_ips = "*"
accesslog = "-"
errorlog = "-"
loglevel = "info"
# don't log query strings or referrers (privacy)
access_log_format = '%(t)s %(s)s %(m)s %(U)s %(b)s %(L)ss'
