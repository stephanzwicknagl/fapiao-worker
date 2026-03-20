# Fix Missing flask-wtf and tomli-w Dependencies

- [x] Install the newly added dependencies (`flask-wtf` and `tomli-w`) into the project venv by running `.venv/bin/pip install -r requirements.txt`, then verify the app starts without import errors — installed flask-limiter 3.9.0 + rich 13.9.4 (downgrades); `from fapiao.web import app` succeeds with SECRET_KEY set (KeyError without it is expected)
