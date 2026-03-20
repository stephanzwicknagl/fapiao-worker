# Dev Access: Running the Web Server

## 1. Outside Docker — Flask dev server

```bash
FLASK_DEBUG=1 SECRET_KEY=dev .venv/bin/flask run
```

Binds to `127.0.0.1:5000` by default (localhost only). Open `http://localhost:5000`.

**To expose on your local network** (so other devices can reach it):

```bash
FLASK_DEBUG=1 SECRET_KEY=dev .venv/bin/flask run --host=0.0.0.0
```

Then access from any device on the same network at `http://<your-machine-ip>:5000`.

---

## 2. Inside Docker

There's no `docker-compose.yml` in the repo yet — CLAUDE.md references one but it doesn't exist.
Use `docker run` directly instead:

```bash
# Build the image
docker build -t fapiao-worker .

# Run — accessible only from localhost
docker run --rm -p 127.0.0.1:8000:8000 -e SECRET_KEY=dev fapiao-worker

# Run — accessible from local network (needed for phone access without SSH)
docker run --rm -p 0.0.0.0:8000:8000 -e SECRET_KEY=dev fapiao-worker
```

Gunicorn already binds to `0.0.0.0:8000` inside the container (see `gunicorn.conf.py`), so the only thing controlling exposure is the `-p` flag on the host side.

Open `http://localhost:8000` (or `http://<your-machine-ip>:8000` if using `0.0.0.0`).

---

## 3. Accessing from your phone via SSH

**Option A — Same WiFi, no SSH needed (simplest)**

Start the server with `--host=0.0.0.0` (option 1 above) or with `-p 0.0.0.0:8000:8000` (Docker).
Find your machine's LAN IP:

```bash
ip route get 1 | awk '{print $7; exit}'
# or: hostname -I | awk '{print $1}'
```

Then on your phone's browser: `http://192.168.x.x:5000` (Flask) or `:8000` (Docker/gunicorn).

---

**Option B — SSH local port forward from phone**

If you want to keep the server bound to localhost (more secure), use SSH tunneling from your phone.

Install an SSH client on your phone (e.g. **Termius**, **JuiceSSH**, or **Blink Shell**), then run:

```bash
# On your phone, in the SSH app's terminal:
ssh -L 8080:localhost:5000 youruser@your-machine-ip
# (use port 8000 instead of 5000 if running Docker/gunicorn)
```

While that SSH session is open, open your phone's browser and go to:
```
http://localhost:8080
```

The traffic is forwarded through SSH to the server on your machine.

---

**Option C — SSH remote port forward from the machine (no SSH client needed on phone)**

If your phone can act as an SSH server (e.g. via Termux+OpenSSH on Android), you can push the tunnel from your machine:

```bash
# On your machine:
ssh -R 8080:localhost:5000 your-phone-ip
# Then on phone browser: http://localhost:8080
```

---

### Quick decision guide

| Scenario | Best option |
|---|---|
| Phone on same WiFi, simplest setup | Option A (`--host=0.0.0.0`) |
| Keep server localhost-only, phone has SSH app | Option B (SSH `-L` from phone) |
| Phone on same WiFi, no SSH app on phone | Option A |
| Remote access (phone not on same network) | Option B via public IP/VPN, or a tunnel service like `ngrok` |
