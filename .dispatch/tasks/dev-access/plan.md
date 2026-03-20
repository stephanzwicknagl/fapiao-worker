# Dev Access: Running the Web Server and Accessing from Phone

- [x] Read CLAUDE.md for existing run instructions (docker, flask dev mode)
- [x] Read `docker-compose.yml` (or equivalent) to understand docker setup and port bindings — no docker-compose.yml exists; Dockerfile uses gunicorn binding 0.0.0.0:8000
- [x] Check if there's a way to expose the dev server to the local network (host binding) — Flask: `--host=0.0.0.0`; Docker: `-p 0.0.0.0:8000:8000`
- [x] Research SSH port forwarding / tunneling approach to access from phone — SSH `-L` (local forward from phone) is the cleanest approach
- [x] Write a clear how-to guide to `.dispatch/tasks/dev-access/output.md` covering: (1) running outside docker in dev mode, (2) running in docker, (3) accessing from phone via SSH tunnel
