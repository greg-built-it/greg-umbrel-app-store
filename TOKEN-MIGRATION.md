# Token-Migration

Diese Anleitung beschreibt, wie ein bestehender Token der alten Umbrel Read-Only Bridge sicher in die neue Community-App übernommen wird, ohne dass der Token in das Repository, ein Docker-Image oder Logs gelangt.

## Voraussetzungen

- Zugriff auf das alte Bridge-Container-Secret oder die Hermes-Konfiguration.
- Berechtigung, die Hermes-Konfiguration (`MCP_UMBREL_RO_API_KEY`) zu ändern.

## Schritt 1: Alten Token ermitteln (ohne Ausgabe)

Das alte Token befindet sich im laufenden Bridge-Container unter `/run/secrets/bridge-token` bzw. im Hermes-Environment-Parameter `MCP_UMBREL_RO_API_KEY`.

Kopiere den alten Token direkt in eine temporäre Datei auf dem Host, **ohne ihn anzuzeigen**:

```bash
# Variante A: Vom alten Container in eine Datei kopieren
docker cp umbrel-ro-bridge:/run/secrets/bridge-token /tmp/old-bridge-token

# Variante B: Aus der Hermes-Konfiguration auslesen und speichern
# (konkreter Befehl hängt vom Konfigurationspfad ab)
```

## Schritt 2: Neuen App-Datastore vorbereiten

Die neue App legt den Token unter `${APP_DATA_DIR}/data/bridge-token` ab. Vor dem ersten Start muss das Verzeichnis existieren und leer sein:

```bash
mkdir -p "/path/to/app-data/greg-umbrel-readonly-bridge/data"
```

## Schritt 3: Alten Token übernehmen

Kopiere die gespeicherte Datei an den neuen App-Pfad und setze Berechtigungen:

```bash
install -m 600 /tmp/old-bridge-token "/path/to/app-data/greg-umbrel-readonly-bridge/data/bridge-token"
rm /tmp/old-bridge-token
```

Damit startet der Init-Service der neuen App und erkennt, dass bereits ein Token vorhanden ist (`-s` Prüfung). Er wird keinen neuen Token erzeugen.

## Schritt 4: Neuen Token erzeugen (falls gewünscht)

Falls du stattdessen einen neuen Token verwenden möchtest, lösche oder leere die Datei vor dem ersten Start. Der Init-Service erzeugt dann automatisch einen neuen zufälligen Token.

## Schritt 5: Hermes-Konfiguration aktualisieren

Passe den Wert von `MCP_UMBREL_RO_API_KEY` an den aktuellen Token an. Der Wert darf nur aus der Datei `bridge-token` gelesen und direkt in die Konfiguration übernommen werden.

**Wichtig:**

- Verwende keine Beispielbefehle wie `cat bridge-token` in gemeinsam genutzten Logs oder Chat-Verläufen.
- Speichere den Token nicht im Repository.
- Nach der Konfiguration lösche alle temporären Dateien und Shell-History-Einträge, die den Token enthalten könnten.

## Schritt 6: App starten und Verbindung prüfen

Starte die App über das Umbrel-Dashboard. Der Containername bleibt `umbrel-ro-bridge`, damit die Hermes-URL `http://umbrel-ro-bridge:8080/sse` gleich bleibt.

Prüfe die Erreichbarkeit:

```bash
curl -s http://umbrel-ro-bridge:8080/health
```

Mit korrektem Bearer-Token:

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://umbrel-ro-bridge:8080/sse
```

## Bereinigung

Entferne alle temporären Dateien und Umgebungsvariablen, die den Token enthalten:

```bash
unset TOKEN
history -c
```
