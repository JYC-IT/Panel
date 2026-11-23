import os

bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"
workers = 1
threads = 4
timeout = 180
keepalive = 5
max_requests = 50
max_requests_jitter = 10
