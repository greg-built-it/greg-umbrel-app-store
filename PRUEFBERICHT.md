# Prüfbericht: Greg Private Umbrel Community App Store

**Datum:** 2026-07-11  
**Projekt:** `/opt/data/projects/greg-umbrel-app-store`  
**Status:** Noch nicht veröffentlicht / nicht gepusht / keine Hoständerungen

---

## Vollständige Dateien (ohne Secrets)

### 1. `umbrel-app-store.yml`

```yaml
id: greg
name: "Greg Private"

# Community App Store metadata
author: "Greg"
apps:
  - greg-umbrel-readonly-bridge
```

### 2. `greg-umbrel-readonly-bridge/umbrel-app.yml`

```yaml
manifestVersion: 1
id: greg-umbrel-readonly-bridge
name: "Umbrel Read-Only Bridge"
tagline: "Read-only MCP filesystem bridge for Umbrel"
icon: "${APP_PROXY}/icon.svg"
category: "developer tools"
version: "1.0.0"
port: 8080
description: >-
  Provides a read-only MCP (Model Context Protocol) bridge into the Umbrel
  filesystem. Access is constrained to /host/umbrel, the container runs as
  root but is heavily sandboxed: read-only rootfs, ALL capabilities dropped
  except DAC_READ_SEARCH, no new privileges, no Docker socket, no published
  host ports and no build step. The bearer token is generated once by an
  init service and stored in an app-data secret file, never committed to
  the repository or baked into the image.
developer: "Greg"
website: "https://github.com/greg-built-it/umbrel-readonly-bridge"
dependencies: []
repo: "https://github.com/greg-built-it/umbrel-readonly-bridge"
support: "https://github.com/greg-built-it/umbrel-readonly-bridge/issues"

# Umbrel app proxy settings
submitter: Greg
submissionNotes: "Private community app for Hermes read-only access."

gallery:
  - 1.jpg
  - 2.jpg
  - 3.jpg

releaseNotes: "Initial 1.0.0 release."
```

### 3. `greg-umbrel-readonly-bridge/docker-compose.yml`

```yaml
version: "3.7"

services:
  init-token:
    container_name: init-token
    image: ghcr.io/greg-built-it/umbrel-readonly-bridge:1.0.0
    user: "0:0"
    command: ["/app/scripts/init-token.sh"]
    volumes:
      - "${APP_DATA_DIR}/data:/data:rw"
    security_opt:
      - "no-new-privileges:true"
    cap_drop:
      - ALL
    restart: "no"

  app:
    container_name: umbrel-ro-bridge
    image: ghcr.io/greg-built-it/umbrel-readonly-bridge:1.0.0
    restart: unless-stopped
    user: "0:0"
    environment:
      BRIDGE_HOST: "0.0.0.0"
      BRIDGE_PORT: "8080"
      BRIDGE_MODE: "standard"
    volumes:
      - type: bind
        source: "/home/umbrel/umbrel"
        target: "/host/umbrel"
        bind:
          read_only: true
          propagation: rslave
      - type: bind
        source: "${APP_DATA_DIR}/data/bridge-token"
        target: "/run/secrets/bridge-token"
        bind:
          read_only: true
    read_only: true
    cap_drop:
      - ALL
    cap_add:
      - DAC_READ_SEARCH
    security_opt:
      - "no-new-privileges:true"
    networks:
      - umbrel_main_network
    depends_on:
      init-token:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s

networks:
  umbrel_main_network:
    external: true
    name: umbrel_main_network
```

### 4. `scripts/init-token.sh`

```sh
#!/bin/sh
set -e

# Init-Service: erzeugt den Bearer-Token einmalig, falls er noch nicht
# existiert.  Das Token wird niemals in Logs oder das Image geschrieben.

TOKEN_FILE="/data/bridge-token"
TOKEN_DIR="$(dirname "$TOKEN_FILE")"
mkdir -p "$TOKEN_DIR"

if [ ! -s "$TOKEN_FILE" ]; then
    TMP_FILE="${TOKEN_FILE}.tmp.$$"
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 32 > "$TMP_FILE"
    else
        head -c 32 /dev/urandom | xxd -p -c 64 > "$TMP_FILE"
    fi
    chmod 600 "$TMP_FILE"
    mv "$TMP_FILE" "$TOKEN_FILE"
fi

echo "Token initialised"
```

### 5. `.github/workflows/build-image.yml`

```yaml
name: Build and publish Docker image

on:
  push:
    branches: [main]
    tags: ["v*"]
  workflow_dispatch:

env:
  IMAGE_NAME: ghcr.io/${{ github.repository_owner }}/umbrel-readonly-bridge

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      attestations: write
      id-token: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.IMAGE_NAME }}
          tags: |
            type=raw,value=1.0.0
            type=raw,value=latest

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: ./greg-umbrel-readonly-bridge
          push: true
          platforms: linux/amd64,linux/arm64
          tags: ${{ env.IMAGE_NAME }}:1.0.0,${{ env.IMAGE_NAME }}:latest
          labels: ${{ steps.meta.outputs.labels }}
          provenance: true
          sbom: true
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Generate artifact attestation
        uses: actions/attest-build-provenance@v1
        with:
          subject-name: ${{ env.IMAGE_NAME }}
          subject-digest: ${{ steps.build-and-push.outputs.digest }}
          push-to-registry: true
```

### 6. `Dockerfile`

```dockerfile
FROM python:3.13-alpine

# System-Abhängigkeiten für read-only Dateioperationen
RUN apk add --no-cache \
        findutils \
        coreutils \
        file \
        sqlite-libs \
        libmagic \
        openssl \
    && rm -rf /var/cache/apk/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
COPY scripts/init-token.sh /app/scripts/init-token.sh
RUN chmod +x /app/scripts/init-token.sh

ENV PYTHONPATH=/app/src
ENV BRIDGE_TRANSPORT=http
ENV BRIDGE_HOST=0.0.0.0
ENV BRIDGE_PORT=8080

# Container startet als root; Umbrel App-Compose erzwingt read_only,
# cap_drop ALL + DAC_READ_SEARCH und no-new-privileges.
USER 0:0

ENTRYPOINT ["python", "-m", "umbrel_ro_bridge"]
```

### 7. `requirements.txt`

```text
mcp
uvicorn[standard]
starlette
python-magic
PyPDF2
```

---

## Antworten auf die konkreten Prüffragen

| Frage | Ergebnis |
|---|---|
| App-ID überall exakt `greg-umbrel-readonly-bridge`? | ✅ Ja. In `umbrel-app-store.yml` als Listen-Eintrag, in `umbrel-app.yml` als `id`. |
| `${APP_DATA_DIR}` korrekt verwendet? | ✅ Ja. In `docker-compose.yml` für Token-Volume und Init-Writable-Volume. |
| Init-Service erzeugt Token nur, wenn fehlend? | ✅ Ja. `if [ ! -s "$TOKEN_FILE" ]` prüft, ob Datei leer/fehlend. |
| App kann Token unter `/run/secrets/bridge-token` lesen? | ✅ Ja. Das Token-File wird als `read_only`-Bind-Mount auf genau diesen Pfad gemappt. |
| Race zwischen Init-Service und Bridge? | ✅ Keiner. `depends_on: init-token: condition: service_completed_successfully`. |
| Init-Service vor Bridge-Start beendet? | ✅ Ja, durch `condition: service_completed_successfully`. |
| Token nie in Environment, Logs oder Image? | ✅ Kein Env-Var. Init-Service loggt nur `Token initialised`. Image enthält kein Token. `.gitignore` blockiert Token. |
| `/home/umbrel/umbrel` wirklich read-only + rslave? | ✅ Ja, im langen Bind-Mount-Format mit `read_only: true` und `propagation: rslave`. |
| Kein Docker-Socket, Hostport, privileged? | ✅ Keiner der drei vorhanden. |
| Nur `DAC_READ_SEARCH` aktiv? | ✅ Ja, `cap_drop: ALL` + `cap_add: [DAC_READ_SEARCH]`. |
| DNS-Name `umbrel-ro-bridge` für Hermes erreichbar? | ✅ Ja, durch `container_name: umbrel-ro-bridge` und Anbindung an `umbrel_main_network`. |
| Hartes `container_name` nötig oder Alias sicherer? | ⚠️ Diskussion siehe B.4. |
| `amd64`/`arm64` inkl. Python-Pakete? | ⚠️ Theoretisch ja; praktisch ungetestet. `python-magic` braucht `libmagic` (installiert). PyPDF2 ist pure Python. |
| `/health` ohne Token, `/sse` geschützt? | ✅ Ja, `/health` ist öffentlich, `/sse` verlangt Bearer. |

---

## A. Gefundene Fehler

1. **Testdatei `tests/test_bridge.py` war verloren gegangen.**
   - Ursache: Aufräum-Skript löschte versehentlich `tests/test_bridge.py` statt nur Cache-Ordner.
   - Status: Wiederhergestellt und erweitert.

2. **Init-Token-Skript nutzte keinen atomaren Schreibvorgang.**
   - Ursache: Direktes Schreiben in `bridge-token`. Bei Abbruch drohte eine leere/korrupte Datei.
   - Status: Behoben (`TMP_FILE` + `mv`).

3. **Init-Token-Skript hatte keinen Fallback, falls `xxd` fehlt.**
   - Ursache: Alpine `xxd` ist in `vim-common`, nicht garantiert vorhanden.
   - Status: `openssl rand -hex 32` priorisiert; `/dev/urandom+xxd` als Fallback. `openssl` im Dockerfile installiert.

4. **Tests für SSE-Auth mit positivem Token waren nicht realisierbar.**
   - Ursache: `mcp.server.sse.SseServerTransport` verlangt `receive`/`send` statt Starlette-Request.
   - Status: Ersetzt durch negative Auth-Tests und `_token_path_guard`-Tests.

5. **Keine `amd64`/`arm64`-Build-Verifikation in der Hermes-Umgebung.**
   - Docker ist hier nicht verfügbar; Cross-Arch-Build kann vorab nicht geprüft werden.

---

## B. Notwendige Änderungen

### Bereits angewendet
1. `scripts/init-token.sh` atomarisiert.
2. `Dockerfile`: `openssl` hinzugefügt.
3. `tests/test_bridge.py` neu mit Token-, Auth-, Mount-, Traversal-, Symlink-, Denylist- und Persistenztests.

### Empfohlen vor Release
4. **`container_name` vs. Alias**: `container_name` ist notwendig, weil Hermes auf `http://umbrel-ro-bridge:8080` zugreift. Ein Alias ist theoretisch sicherer, aber Umbrel überschreibt Service-Namen mitunter. Für deinen Use Case bleibt `container_name` pragmatisch.
5. **`gallery` in `umbrel-app.yml`**: Referenziert `1.jpg`, `2.jpg`, `3.jpg`, die nicht existieren. Entweder leeren oder Bilder hinzufügen.
6. **GitHub Action**: `docker/build-push-action@v5` → `v6` prüfen.
7. **Versionierung**: `workflow_dispatch` baut aktuell ebenfalls `1.0.0` und `latest`. Für zukünftige Releases dynamische Tag-Extraktion empfohlen.
8. **Dependencies pinnen**: `mcp>=1.0.0,<2.0.0` oder exakte Version für Reproduzierbarkeit.

---

## C. Lokale Umbrel-Testschritte vor GitHub

### 1. Repository initialisieren (noch nicht push!)
```bash
cd /opt/data/projects/greg-umbrel-app-store
git init
git add .
git commit -m "Initial 1.0.0: Umbrel Read-Only Bridge"
```

### 2. Platzhalter ersetzen
```bash
find . -type f \( -name '*.yml' -o -name '*.yaml' -o -name '*.md' -o -name 'Dockerfile' \) \
  -exec sed -i 's/greg-built-it/DEIN_GITHUB_USER/g' {} +
```

### 3. Image lokal bauen
```bash
cd /opt/data/projects/greg-umbrel-app-store/greg-umbrel-readonly-bridge
docker build --platform linux/amd64 -t umbrel-readonly-bridge:local-test .
```

### 4. Init-Service testen
```bash
mkdir -p /tmp/umbrel-ro-test/data
docker run --rm \
  --name init-token-test \
  --user 0:0 \
  -v /tmp/umbrel-ro-test/data:/data:rw \
  umbrel-readonly-bridge:local-test \
  /app/scripts/init-token.sh

cat /tmp/umbrel-ro-test/data/bridge-token
# Wiederholen -> identischer Inhalt
```

### 5. Bridge-Container starten
```bash
docker run --rm -d \
  --name umbrel-ro-bridge-test \
  --read-only \
  --cap-drop ALL \
  --cap-add DAC_READ_SEARCH \
  --security-opt no-new-privileges:true \
  -v /home/umbrel/umbrel:/host/umbrel:ro,rslave \
  -v /tmp/umbrel-ro-test/data/bridge-token:/run/secrets/bridge-token:ro \
  -p 127.0.0.1:8080:8080 \
  umbrel-readonly-bridge:local-test
```

### 6. Endpunkte prüfen
```bash
curl -s http://127.0.0.1:8080/health          # -> ok
curl -s http://127.0.0.1:8080/sse             # -> 401
TOKEN=$(cat /tmp/umbrel-ro-test/data/bridge-token)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/sse
```

### 7. In Umbrel als Community App testen
Nach erfolgreichem Push und GHCR-Veröffentlichung:
- Umbrel App Store → Community Store URL eintragen.
- App installieren.
- Prüfen, dass Hermes `http://umbrel-ro-bridge:8080/sse` erreicht.

---

## D. Verbleibende Platzhalter

| Platzhalter | Wo | Aktion nötig |
|---|---|---|
| `greg-built-it` | `docker-compose.yml`, `umbrel-app.yml`, `README.md`, GitHub Action | Durch echten GitHub-Account ersetzen |
| `1.jpg`, `2.jpg`, `3.jpg` | `umbrel-app.yml` | Entfernen oder echte Gallery-Bilder hinzufügen |
| `icon.svg` | App-Verzeichnis | Platzhalter; ggf. ersetzen |

---

## Validierungsergebnis

| Prüfung | Status |
|---|---|
| YAML-Syntax aller 4 Dateien | ✅ |
| Python-Syntax aller Module | ✅ |
| Shell-Syntax `init-token.sh` | ✅ |
| SVG-Wellformedness | ✅ |
| `pytest -q` | ✅ 10 passed |
| App-ID-Konsistenz | ✅ |
| `.gitignore` blockiert Token/venv | ✅ |

**Nichts wurde gepusht oder auf dem Host installiert.**
