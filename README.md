# Greg Private — Umbrel Community App Store

Dieser private Umbrel Community App Store enthält die App **Umbrel Read-Only Bridge**.

## Store

- **Store-ID:** `greg`
- **Name:** `Greg Private`

## App

- **App-ID:** `greg-umbrel-readonly-bridge`
- **Name:** `Umbrel Read-Only Bridge`
- **Version:** `1.0.2`

## Zweck

Die App stellt einen read-only MCP-Server (Model Context Protocol) über SSE zur
Verfügung. Hermes kann über den Endpunkt `/sse` lesend auf das Umbrel-Dateisystem
zugreifen, ohne dass Schreibzugriff, Docker-Socket oder Host-Ports freigegeben
werden.

## Sicherheitskonzept

- Nur lesende Dateisystem-Operationen unter `/host/umbrel`.
- Container-Rootfs read-only.
- Container-User `0:0`, aber alle Capabilities bis auf `DAC_READ_SEARCH` entzogen.
- `cap_drop: ALL`, `cap_add: [DAC_READ_SEARCH]`.
- `no-new-privileges`.
- Kein Docker-Socket.
- Keine veröffentlichten Hostports; der Port wird nur im `umbrel_main_network`
  innerhalb der Umbrel-Infrastruktur verwendet.
- Der Bearer-Token wird beim ersten Start durch einen Init-Service erzeugt und in
  `${APP_DATA_DIR}/data/bridge-token` gespeichert. Er fließt nicht ins Image,
  Repository oder Logs.
- Die Bridge liest den Token ausschließlich aus `/run/secrets/bridge-token`.

## Bauen und Veröffentlichen

Das Image wird über GitHub Actions für `linux/amd64` und `linux/arm64` gebaut
und nach GHCR veröffentlicht. Tags werden aus dem Git-Tag `v*.*.*` abgeleitet
(`1.0.2`) und zusätzlich `latest`.

## Voraussetzungen für Veröffentlichung

1. Das Repository muss auf GitHub **öffentlich** erreichbar sein, damit Umbrel den
   Community App Store laden kann.
2. Nach dem ersten Push muss das GHCR-Paket **öffentlich** gesetzt werden, sonst
   kann Umbrel das Image nicht pullen.
3. Ersetze **vor** Installation und Build überall `greg-built-it` durch den
   tatsächlichen GitHub-Account/Organisation.
4. Nach jedem erfolgreichen GitHub-Actions-Build solltest du den Image-Digest
   für das gerade veröffentlichte Tag ermitteln und in `docker-compose.yml`
   fixieren. Damit bleibt die App gegen ein unerwartetes Überschreiben von
   `latest` geschützt.
5. Aktualisiere Hermes `MCP_UMBREL_RO_API_KEY` nach der Installation gemäß
   `TOKEN-MIGRATION.md`.

## Noch offene Platzhalter

1. `greg-built-it` in:
   - `docker-compose.yml`
   - `umbrel-app.yml`
   - `.github/workflows/build-image.yml`
   - README (diese Datei)
2. Optional: `icon.svg` kann ersetzt werden.

## Dateibaum

```
.
├── .github/workflows/build-image.yml
├── README.md
├── TOKEN-MIGRATION.md
├── umbrel-app-store.yml
└── greg-umbrel-readonly-bridge/
    ├── docker-compose.yml
    ├── Dockerfile
    ├── icon.svg
    ├── requirements.txt
    ├── pyproject.toml
    ├── scripts/
    │   └── init-token.sh
    ├── src/umbrel_ro_bridge/
    │   ├── __init__.py
    │   ├── __main__.py
    │   ├── fs.py
    │   ├── policy.py
    │   ├── secrets_filter.py
    │   └── server.py
    ├── tests/
    │   ├── __init__.py
    │   └── test_bridge.py
    └── umbrel-app.yml
```

## Lizenz

Private Nutzung. Veröffentlichung und kommerzielle Weiterverwendung bedürfen
einer separaten Genehmigung.
