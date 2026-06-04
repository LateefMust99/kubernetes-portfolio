# Assignment 04 — Lateef Mustapha

**GitHub username:** LateefMust99
**Date completed:** 2026-06-04

## 1. Answers to the 11 questions

**Q1 — default-bridge DNS gap.**
On the default `bridge`, `dig +short db` returned an empty result and `getent hosts db` reported "not found", even though `/etc/resolv.conf` listed a working nameserver (`192.168.65.7`, the Docker Desktop VM's upstream resolver — on a typical Linux host you'd see `127.0.0.11`). The resolver is fine; what's missing is the **service records** in it. Docker's embedded DNS server only auto-registers container-name → IP entries for containers that share a **user-defined** network. On the default bridge, the embedded resolver answers queries for `localhost`, the container's own name, and external public DNS, but it does **not** maintain an A-record for every other container on the same default bridge. The only built-in name-based shortcut available there is the deprecated `--link` flag, which writes static `/etc/hosts` entries — not real DNS. So even with a perfectly valid nameserver in `resolv.conf`, the api can't translate `db` into an IP, and Postgres connections fail with name-resolution errors.

**Q2 — db IP after restart + why hard-coding is wrong.**
A plain `docker container restart db` kept the IP at `172.17.0.2` — Docker's IPAM tries to hand the same address back if the slot is free. But that's a *best-effort coincidence*, not a guarantee. To prove it, I deleted `db`, started an interim `claim` container which grabbed `172.17.0.2`, then recreated `db` — it came up on `172.17.0.4`. The api was still pointed at `172.17.0.2` and connections to `/notes` hung. In production this is the same bug worn twice: (a) IPs are an implementation detail that can shift on any reschedule, host reboot, or co-tenant scaling event, and (b) without DNS you have no place to re-resolve, so every IP-coded reference becomes a config file you have to chase across the fleet. The "make it reliable on the default bridge" answer is essentially to rebuild what Docker already gives you for free on a user-defined bridge — pinning IPs with `--ip`, writing `/etc/hosts` via `--add-host`, scripting wrappers that re-`docker inspect` every restart. The professional answer is "don't": create a user-defined bridge and refer to services by name.

**Q3 — subnet/gateway + flags to control them.**
Docker picked `172.20.0.0/16` for `cohort-net` with gateway `172.20.0.1`, allocated from the daemon's default address pool. To pin them — for example to avoid the `172.17.0.0/16` that the office VPN uses — pass `--subnet 172.30.0.0/24 --gateway 172.30.0.1` at create time (optionally `--ip-range` to reserve a slice for dynamic allocation, and `--aux-address` to carve out gateways/reservations). For daemon-wide control you can also set `default-address-pools` in `/etc/docker/daemon.json` so every auto-created bridge falls inside a range you own.

**Q4 — user-defined bridge DNS + design implication.**
On `cohort-net`, `dig +short db` returned `172.20.0.2` and `dig +short api` returned `172.20.0.3`; `curl http://api:8080/healthz` returned `ok`. The difference vs Part 1 isn't the resolver — it's that the embedded DNS now has **service records** because both containers joined a user-defined network where Docker auto-registers each container by its `--name` (and any `--network-alias`). The design implication for a 10-service stack is that you address services by *stable identity* (`db`, `cache`, `api`, ...), and any service can find any other without anyone owning a routing table. Adding the 11th service is one `--network cohort-net` flag; on the default bridge it would be 10 new IP-to-name mappings to distribute and re-distribute on every restart. This is the same model Kubernetes uses — Service DNS is just a more elaborate version of the same idea.

**Q5 — what isolated the stranger + how to bridge it.**
A second container launched on `cohort-other` could neither resolve nor reach `db` — `ping db` said `Name does not resolve` and `dig +short db` returned no answer. The isolation came from the **Linux bridge** itself: each user-defined bridge is its own L2 broadcast domain with its own veth pairs and its own DNS service-record namespace, so containers on different bridges share neither IP routes nor name registration. The single change to let the stranger reach `db` while staying on `cohort-other` is `docker network connect cohort-net <stranger>` — a container can be attached to multiple networks at once, and once it joins `cohort-net` it picks up the second veth + DNS registration for that network.

**Q6 — `-p HOST:CONTAINER` semantics.**
The third probe (`curl http://api:18080` from a container on `cohort-net`) failed because `-p 18080:8080` does not change anything inside the container — the api still listens on `8080` only. What `-p` does is install a **DNAT rule on the host's network namespace** (iptables on Linux, pf on macOS via Docker Desktop's VM) that rewrites packets arriving at the *host* on `18080` to the container's `8080`. That rule lives in the *host's* netfilter tables, not on the container bridge, so a sibling container on `cohort-net` hitting `api:18080` is just sending a TCP SYN to a port nothing's listening on. The host-to-container path uses the DNAT rule (`-p`); the container-to-container path uses the bridge + container DNS and the **container's actual** listening port. `pfctl -s nat` on macOS / `iptables -t nat -L DOCKER -n` on Linux shows the DOCKER chain with one DNAT entry per published port.

**Q7 — `docker rm -v` vs named-volume behavior.**
After `docker container rm -fv throwaway-db`, `docker volume ls --filter name=cohort-db-data` still listed the volume. The `-v` flag on `docker container rm` only removes volumes that the container itself *owns* — that is, **anonymous** volumes created implicitly when an image declares `VOLUME` and the user didn't provide a `-v name:path`. A **named** volume is owned by the daemon, not by any one container; `-v` on `rm` walks away from it the same way it walks away from a bind mount. To actually delete the named volume you call `docker volume rm cohort-db-data`, and if any container (even a stopped one) still references it that command will refuse with "volume is in use". This asymmetry is exactly what you want in production: a container is cattle, the data is not.

**Q8 — bind vs named volume + why not to poke the mountpoint.**
Two things a bind mount can do that a named volume can't (easily): (1) point at an **arbitrary host path** you already curate — your laptop's `~/code` directory for live-reload dev, or `/etc/letsencrypt` for TLS certs — without copying into Docker's storage; (2) be **edited from outside Docker** by your normal tools (your editor, `rsync`, OS-level backups, even `inotify` watchers) because it's a real host filesystem path. Two reasons to still prefer a named volume in production: (1) **portability** — the volume name is the same on every host, while bind paths leak environment assumptions; (2) **performance + storage-driver integration** — on Docker Desktop Mac/Windows, named volumes live in the Linux VM filesystem and avoid the slow file-sharing translation layer, and on Linux they can use volume drivers (NFS, cloud block storage, encrypted overlays) that bind mounts simply can't. The `Mountpoint` of a named volume *is* a real host path (`/var/lib/docker/volumes/cohort-db-data/_data`), but poking it directly is a bad idea because it bypasses Docker's UID/GID mapping, file-locking expectations, and (most importantly) any volume-driver behavior — the next driver upgrade or migration to NFS-backed volumes turns your "direct edit" workflow into silent data loss.

**Q9 — when tmpfs is the right choice.**
A realistic workload: a build sandbox that pipes secrets (a pre-baked SSH key, a short-lived OAuth token) into `/run/secrets` for a few seconds while the build pulls a private dependency. The two guarantees `tmpfs` gives that disk-backed storage doesn't: (1) **the data never touches the host filesystem** — it lives in RAM, so it can't be recovered from an unmounted disk image, captured by a host-level backup, or read via the `Mountpoint` trick from Q8; (2) **lifetime is bounded by the container** — when the container stops the kernel reclaims the pages, with no `docker volume rm` step to forget. Same pattern applies to scratch space for compilers, ephemeral Unix sockets, and anything where "this byte exists for the next 30 seconds and then has never existed" is the actual security property you want.

**Q10 — stopping db before backup + production alternative.**
Stopping the db before tarring `/var/lib/postgresql/data` prevents **physical-backup torn-write / inconsistency** corruption: Postgres writes to multiple files (heap pages, WAL segments, the control file, indexes) that need to agree with each other, and `tar` walking the directory tree while the engine is mid-checkpoint can capture half-written pages, a control file that points at a WAL segment that doesn't exist yet, or an index out of sync with its heap. The restored cluster then fails recovery, or worse, succeeds and silently returns wrong rows. The production-grade alternative is **never stop the database**: take a logical backup with `pg_dump`/`pg_dumpall` over a live connection (transactionally consistent via a snapshot), or take a physical online backup with `pg_basebackup` plus streaming WAL replication (which is also the foundation of point-in-time recovery). Both are run *against* the live database — the "stop the writer" trick we used here is fine for a single-volume lab demo, but it's not a backup strategy.

**Q11 — compose-managed network/volume + external:true.**
Compose auto-created the network as `assignment-04_cohort-net` — `<project>_<network-name>`, where the project name defaults to the directory name (`assignment-04`) and the network-name comes from the `networks:` key in `compose.yml` (`cohort-net`). The network I created by hand in Part 2 was just `cohort-net` because there's no project to prefix. Compose owns its prefixed network's lifecycle: `docker compose down` removes it. `external: true` on the volume matters because `docker compose down -v` deletes every volume that compose owns, but **refuses to touch externally-declared volumes**. In a real incident — say someone runs `docker compose down -v` to "reset" a staging stack — `external: true` on `cohort-db-data` is the difference between "lost the staging notes table" and "lost the production restore data we mounted into staging to debug an outage." It's the seatbelt that says "this resource has a lifecycle bigger than this compose project, hands off."

## 2. Network + volume listing

```text
=== docker network ls ===
NETWORK ID     NAME                       DRIVER    SCOPE
a5555dc4aefc   assignment-04_cohort-net   bridge    local
78e35d6dafef   bridge                     bridge    local
4eac3ef548a0   conquer-proj_default       bridge    local
52a892b4c0c3   host                       host      local
2c16d343ad4c   k3d-greeter                bridge    local
15be2866fff8   none                       null      local

=== docker network inspect assignment-04_cohort-net --format '{{json .IPAM.Config}}' | jq ===
[
  {
    "Subnet": "172.20.0.0/16",
    "Gateway": "172.20.0.1"
  }
]

=== docker volume ls (filtered to cohort) ===
DRIVER    VOLUME NAME
local     cohort-db-data
local     cohort-demo

=== docker volume inspect cohort-db-data ===
[
    {
        "CreatedAt": "2026-06-04T15:18:07Z",
        "Driver": "local",
        "Labels": null,
        "Mountpoint": "/var/lib/docker/volumes/cohort-db-data/_data",
        "Name": "cohort-db-data",
        "Options": null,
        "Scope": "local"
    }
]
```

## 3. Files

### `api/Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runtime
RUN useradd --uid 1000 --create-home app
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY app.py .
EXPOSE 8080
USER app
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
```

### `api/app.py`

```python
import os, time
import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_HOST = os.environ.get("DB_HOST", "db")
DB_USER = os.environ.get("DB_USER", "cohort")
DB_PASS = os.environ.get("DB_PASS", "cohort")
DB_NAME = os.environ.get("DB_NAME", "cohort")


def connect():
    for _ in range(30):
        try:
            return psycopg2.connect(
                host=DB_HOST, user=DB_USER, password=DB_PASS, dbname=DB_NAME
            )
        except psycopg2.OperationalError:
            time.sleep(1)
    raise RuntimeError("db never came up")


@app.before_request
def ensure_schema():
    if getattr(app, "_ready", False):
        return
    with connect() as c, c.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS notes (id SERIAL PRIMARY KEY, body TEXT NOT NULL)"
        )
        c.commit()
    app._ready = True


@app.get("/notes")
def list_notes():
    with connect() as c, c.cursor() as cur:
        cur.execute("SELECT id, body FROM notes ORDER BY id")
        return jsonify([{"id": i, "body": b} for i, b in cur.fetchall()])


@app.post("/notes")
def add_note():
    body = request.json.get("body", "")
    with connect() as c, c.cursor() as cur:
        cur.execute("INSERT INTO notes (body) VALUES (%s) RETURNING id", (body,))
        c.commit()
        return jsonify({"id": cur.fetchone()[0], "body": body}), 201


@app.get("/healthz")
def healthz():
    return ("ok", 200)
```

### `compose.yml`

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: cohort
      POSTGRES_PASSWORD: cohort
      POSTGRES_DB: cohort
    volumes:
      - cohort-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cohort"]
      interval: 5s
      retries: 5
    networks:
      - cohort-net

  api:
    image: cohort-api:0.1.0
    environment:
      DB_HOST: db
    ports:
      - "18080:8080"
    depends_on:
      db:
        condition: service_healthy
    networks:
      - cohort-net

networks:
  cohort-net:

volumes:
  cohort-db-data:
    external: true
```

## 4. Evidence

### Part 1.2 — netshoot DNS probe on default bridge (`dig db` empty)

```text
$ docker container run --rm --network container:api nicolaka/netshoot \
    sh -c 'cat /etc/resolv.conf; dig +short db; getent hosts db || echo "not found"'

--- resolv.conf ---
# Generated by Docker Engine.
# This file can be edited; Docker Engine will not make further changes once it
# has been modified.

nameserver 192.168.65.7

# Based on host file: '/etc/resolv.conf' (legacy)
# Overrides: []
--- dig db ---
                              <-- empty: embedded DNS has no record for `db`
--- getent ---
not found
```

Bonus — IP-hack drift demo (Q2):

```text
$ DB_IP=$(docker container inspect db -f '{{.NetworkSettings.IPAddress}}')
DB_IP=172.17.0.2
$ curl -s -X POST localhost:18080/notes -d '{"body":"hello from the default bridge"}' ...
{"body":"hello from the default bridge","id":1}
$ docker container rm -f db && docker container run -d --name claim alpine sleep 600
claim container took 172.17.0.2          <-- the old db IP got reused
$ docker container run -d --name db ... postgres:16-alpine
$ docker container inspect db -f '{{.NetworkSettings.IPAddress}}'
db now has 172.17.0.4 (was 172.17.0.2)   <-- IP drifted
$ curl -s --max-time 5 http://localhost:18080/notes
                                         <-- api still pointed at .2, hangs
```

### Part 2.3 — netshoot DNS probe on `cohort-net` (`dig db` returns an IP)

```text
$ docker container run --rm --network cohort-net nicolaka/netshoot \
    sh -c 'dig +short db; dig +short api; curl -sf http://api:8080/healthz && echo'

--- dig db ---
172.20.0.2
--- dig api ---
172.20.0.3
--- curl api ---
ok

$ docker network inspect cohort-net --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}'
db 172.20.0.2/16
api 172.20.0.3/16
```

### Part 2.5 — stranger container on `cohort-other` cannot reach `db`

```text
$ docker container run --rm --network cohort-other nicolaka/netshoot \
    sh -c 'ping -c 2 -W 1 db 2>&1; dig +short db'

--- ping db ---
ping: db: Name does not resolve
--- dig db ---
              <-- empty; cohort-other has no record for `db`
```

### Part 3.1 — the three curls

```text
=== probe 1: host -> 18080 (uses -p mapping) ===
ok
(host -> 18080 OK)

=== probe 2: container -> api:8080 (DNS, container port) ===
ok
(container -> 8080 OK)

=== probe 3: container -> api:18080 (should fail) ===
(port 18080 from container failed -- as expected)
```

### Part 4.3 — `docker volume ls` after `docker rm -fv throwaway-db`

```text
$ docker container rm -fv throwaway-db
throwaway-db
$ docker volume ls --filter name=cohort-db-data
DRIVER    VOLUME NAME
local     cohort-db-data    <-- named volume survived `rm -fv`
```

### Part 5.1 — backup file exists

```text
$ ls -lh cohort-db-data-*.tar.gz
-rw-r--r--  1 lateefmust  staff   6.4M Jun  4 11:19 /Users/lateefmust/assignment-04/cohort-db-data-20260604.tar.gz
```

### Part 5.2 — `SELECT * FROM notes` against the restored verification db

```text
$ docker container exec db-verify psql -U cohort -d cohort -c 'SELECT id, body FROM notes;'

 id |          body
----+------------------------
  1 | this note IS protected
(1 row)
```

### Part 6 — compose stack working

```text
$ docker compose up -d
 Network assignment-04_cohort-net  Created
 Container assignment-04-db-1     Healthy
 Container assignment-04-api-1    Started

$ docker compose ps
NAME                  IMAGE                COMMAND                  SERVICE   STATUS                    PORTS
assignment-04-api-1   cohort-api:0.1.0     "gunicorn -b 0.0.0.0…"   api       Up 8 seconds              0.0.0.0:18080->8080/tcp
assignment-04-db-1    postgres:16-alpine   "docker-entrypoint.s…"   db        Up 14 seconds (healthy)   5432/tcp

$ curl -s http://localhost:18080/notes
[{"body":"this note IS protected","id":1}]
```

## 5. One trade-off I had to make

I declared the Postgres volume as `external: true` in `compose.yml` instead of letting compose own it. The win is that `docker compose down -v` cannot wipe production data by accident — the volume's lifecycle is decoupled from the project, which matches the rule of thumb that stateful resources should outlive the stack that consumes them. The cost is ergonomic: every fresh checkout of the repo now needs an explicit `docker volume create cohort-db-data` before `docker compose up`, and CI needs to be taught the same. For a real production project I'd accept that trade; for a throwaway demo I'd let compose own the volume so `up` is one command.

## 6. One thing I'm still unsure about

When a container is on multiple user-defined bridges at once (Q5 "the fix"), which DNS resolver wins if both networks happen to have a service named `db` — does Docker pick the network you joined first, or do queries hit both resolvers in some order?
