# Kickbase für Home Assistant (Modulare Integration + Lokale Datenbank + Lovelace Cards)

Eine **vollständig modulare, rein lesende** Home-Assistant-Integration (HACS-kompatibel) auf Basis der inoffiziellen [Kickbase API v4 Dokumentation](https://github.com/kevinskyba/kickbase-api-doc).

Sie kombiniert:
1. **Stündlichen Komplett-Sync (`3600 s`) + Lokale SQLite-Datenbank & Foto-Cache:** Fragt einmal pro Stunde gebündelt alle Spieler auf dem **Transfermarkt**, im **eigenen Kader** sowie in **allen anderen Manager-Kadern** der Liga ab, speichert Marktwert-Verläufe, Status-Historien, Manager-Snapshots und lädt Spielerfotos/Vereinswappen **nur einmalig** lokal in `<config>/kickbase_data/` herunter. Klicks in der UI lesen direkt aus SQLite (**0 Kickbase-API-Requests**).
2. **Native Home-Assistant-Entitäten** (Sensoren inkl. DB-Metriken, Binary Sensors, Kalender, Bilder, Query-Services & Bus-Events),
3. **8 eigenständige, modulare Lovelace Cards** (mit visuellem UI-Editor, klickbaren Spieler-/Manager-/Match-/News-Modals, Marktwert-Chart und Status-Historie),
4. **Ein integriertes Kickbase Sidebar-Panel („Command Center“)** inkl. Multi-Liga-Umschalter, lokalem **Datenbank-Explorer**, Sofortsuche und anpassbarer Karten-Sichtbarkeit.

> **Hinweis zur Sicherheit (Read-Only):** Diese Integration arbeitet **strikt lesend**. Es werden ausschließlich `GET`-Datenabfragen (sowie Login/Token-Refresh) ausgeführt. Es werden niemals Gebote abgegeben, Spieler verkauft, Aufstellungen verändert oder Boni eingesammelt.

---

## Gebündelter Sync & Lokale SQLite-Datenbank

Um API-Anfragen an Kickbase auf ein Minimum zu reduzieren, bündelt der `LeagueSyncCoordinator` den Liga-Abruf standardmäßig auf **1× pro Stunde (`3600 s`)**:

1. **Gebündelte Erfassung:** Liga-Übersicht, Budget & Tabelle, eigener Kader/Aufstellung, Transfermarkt + Scout-Liste sowie alle gegnerischen Manager-Kader in der Liga.
2. **Lokale SQLite-Datenbank (`<config>/kickbase_data/kickbase.db`):**
   - `players`: Alle eindeutigen Spieler (eigener Kader, Transfermarkt, Kader anderer Manager) inkl. aktuellem Status, Marktwert, Punkten & Besitzer.
   - `player_market_value_history`: Langfristige lokale Marktwert-Verläufe pro Tag (Backfill über `marketvalue/{timeframe}` alle ≥12 h + stündliche Fortschreibung).
   - `player_status_history`: Deduplizierte Historie über alle Status-, Verletzungs-, Besitzer- und Transfermarkt-Wechsel (inkl. `kickbase_player_status_changed`-Event).
   - `manager_snapshots` & `sync_runs`: Rivalen-Kader/Transfers und Audit-Logs über API-Requests & Foto-Downloads.
3. **Lokaler Foto-Cache (`<config>/kickbase_data/photos/` → `/api/kickbase_photos/`):**
   - Spielerfotos, Vereinswappen und Manager-Avatare werden lokal gespeichert; bereits vorhandene Dateien werden beim nächsten Sync **nicht erneut heruntergeladen**.

Über **Konfigurieren (Options Flow)** lassen sich weiterhin alle 7 Daten-Module gezielt ein-/ausschalten sowie Foto-Caching, Detail-/Verlaufs-Backup, optionales adaptives Live-Polling (60 s während laufender Spiele, standardmäßig deaktiviert) und das Sync-Intervall (`300–86400 s`) anpassen.

---

## Installation

### Option 1: HACS (Custom Repository)
1. Öffne **HACS → Integrationen → Drei-Punkte-Menü → Benutzerdefinierte Repositories**.
2. Füge die URL `https://github.com/<user>/<repo>` als Kategorie **Integration** hinzu (im Repo müssen `hacs.json` und `custom_components/kickbase/` im Root liegen).
3. Installiere **Kickbase** und starte Home Assistant neu.
4. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen → Kickbase**.

### Option 2: Manuelle Installation
1. Kopiere den Ordner [`custom_components/kickbase`](custom_components/kickbase) in dein Home-Assistant-Verzeichnis `<config>/custom_components/kickbase`.
2. Starte Home Assistant neu.
3. Richte die Integration über die UI unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** ein.

---

## Modulare Lovelace Cards & Command Center

Die Integration registriert automatisch `/api/kickbase_static/kickbase-cards.js` im Frontend – es ist keine manuelle Resource-Konfiguration nötig. Im Dashboard-Editor stehen folgende Karten inkl. visuellem Editor bereit:

- `custom:kickbase-overview-card` – Budget, Max-Gebot, Teamwert, Platzierung, Deadline & DB-Status-Pill
- `custom:kickbase-lineup-card` – Interaktives Spielfeld mit Formation, Status-Indikatoren, Kapitän & Spieler-Modal
- `custom:kickbase-squad-card` – Sortier- & filterbarer Kader mit 24h-Marktwert-Trend, G&V und Ø-Punkten
- `custom:kickbase-market-card` – Transfermarkt-Listings + Scout-Watchlist mit Ablauf-Timer
- `custom:kickbase-standings-card` – Liga-Tabelle & Battles (Klick auf Manager öffnet lokal gespeicherten Rivalen-Kader)
- `custom:kickbase-live-card` – Live-Spiele, Live-Events-Modal, Spieltags-Ranking & Bundesliga-Tabelle
- `custom:kickbase-feed-news-card` – Liga-Feed, Erfolge, Bundesliga-News & Voraussichtliche Aufstellungen
- `custom:kickbase-challenges-card` – Division, Skill Points & aktive Matchday-Challenges

Im Sidebar-Panel **Kickbase Command Center** gibt es zusätzlich den Tab **💾 Lokale Datenbank** mit Filtern nach Bereich (`Mein Kader`, `Transfermarkt`, `Andere Manager`, `Scout-Liste`), Fitness-Status (`⚠ Probleme`, `Fit`) sowie Klick-Inspektion aller lokalen Marktwert- und Status-Historien.

---

## Entitäten, Events & Services

### Sensoren & Binary Sensors (pro Liga + Global)
- **Lokale DB & Sync Sensoren:** `Lokale DB Spieler` (mit Attributen `my_squad_count`, `market_count`, `rival_players_count`, `market_value_points`, `status_events_count`, `photos_cached`, `db_size_kb`, `last_api_requests`), `Letzter Kickbase-Sync`.
- **Modul-Sensoren:** Budget, Max. Gebot, Teamwert, Tabellenplatz, Gesamtpunkte, Spieltagspunkte, Kadergröße, Marktwert-Trend 24h, Aufstellung Formation, Aufstellungs-Deadline, Transfermarkt-Spieler, Scout-Liste, Nächstes Marktwert-Update, Aktueller Spieltag, Live-Punkte, Letzte Liga-Aktivität, Erfolge, Letzte News, Challenge Division, Skill Points *(plus optional einzelne Spieler-Sensoren mit lokalem `entity_picture`)*.
- **Binary Sensors:** `Budget im Minus`, `Aufstellung unvollständig/Problem`, `Kader-Marktwert steigt`, `Scout-Spieler auf Transfermarkt`, `Spieltag Live`.
- **Kalender (`calendar`):** Spielplan & Aufstellungs-Deadlines.
- **Bilder (`image`):** Manager-Profilbild & Liga-Logos.

### Home Assistant Bus Events
- `kickbase_player_status_changed` – Spieler ändert Fitness-Status, Besitzer oder Transfermarkt-Status
- `kickbase_negative_budget` – Budget fällt unter 0 €
- `kickbase_scouted_on_market` – Beobachteter Spieler erscheint auf dem Transfermarkt
- `kickbase_new_activity` – Neuer Eintrag im Liga-Feed
- `kickbase_live_player_event` – Neues Live-Ereignis (Tor/Karte/etc.) eines eigenen Spielers

### Services
- `kickbase.refresh_data` – Aktualisiert ausgewählte Liga oder globale Module sofort auf Abruf.
- `kickbase.sync_database` – Führt den gebündelten Komplett-Sync sofort aus (optional `force_details: true`).
- `kickbase.get_player_history` – Liefert Marktwert-Verlauf & Status-Historie eines Spielers direkt aus SQLite zurück (**0 API-Anfragen**).
- `kickbase.query_local_players` – Filtert lokal gespeicherte Spieler nach Name, Bereich oder Status (**0 API-Anfragen**).

---

## Tests lokal ausführen

```bash
python -m unittest discover -s tests -v
```
