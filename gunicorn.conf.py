bind = "0.0.0.0:8000"
workers = 2
timeout = 120          # PDF processing can take several seconds on large batches
max_requests = 500     # recycle workers periodically to avoid memory drift
max_requests_jitter = 50
accesslog = "-"        # stdout → captured by systemd journal
errorlog = "-"
loglevel = "info"
