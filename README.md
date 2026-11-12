# Kickbase für Home Assistant (Modulare Integration + Lovelace Cards + Sidebar-Panel)

Eine **vollständig modulare, rein lesende** Home-Assistant-Integration (HACS-kompatibel) auf Basis der inoffiziellen [Kickbase API v4 Dokumentation](https://github.com/kevinskyba/kickbase-api-doc).

Sie kombiniert:
1. **Native Home-Assistant-Entitäten** (Sensoren, Binary Sensors, Kalender, Bilder & Bus-Events für Automationen),
2. **8 eigenständige, modulare Lovelace Cards** (mit visuellem UI-Editor, klickbaren Spieler-/Manager-/Match-/News-Modals und SVG-Marktwert-Charts),
3. **Ein integriertes Kickbase Sidebar-Panel („Command Center“)** mit Multi-Liga-Umschalter, Spielersuche, Tabs und anpassbarer Karten-Sichtbarkeit.

> **Hinweis zur Sicherheit (Read-Only):** Diese Integration arbeitet **strikt lesend**. Es werden ausschließlich `GET`-Datenabfragen sowie der Login (`POST /v4/user/login` / Token-Refresh) ausgeführt. Es werden niemals Gebote abgegeben, Spieler verkauft, Aufstellungen verändert oder Boni eingesammelt.

---

## Modulare Architektur

Im Einrichtungs-Assistenten und jederzeit nachträglich über **Konfigurieren (Options Flow)** lassen sich alle 7 Daten-Module unabhängig aktivieren/deaktivieren und im Abrufintervall anpassen:

| Modul-Key | Inhalt & Genutzte Kickbase-v4-Endpunkte | Standard-Intervall |
| --- | --- | --- |
| `league_overview` | Liga-Übersicht, Budget & Max-Gebot (`pbas`), Tabelle, Battles, Einstellungen (`/leagues/{id}/overview`, `/me`, `/me/budget`, `/ranking`, `/settings`) | 300 s |
| `squad_lineup` | Kader, Startelf, Formation, Lock-Countdown, Vereinslogos (`/leagues/{id}/squad`, `/lineup/overview`, `/lineup/teams`, `/teamcenter/myeleven`) | 300 s |
| `market_transfers` | Transfermarkt, Ablaufzeiten, Scout-Liste (`/leagues/{id}/market`, `/scoutedplayers`) + On-Demand Spielerdetails, 92T-Marktwert-Chart, Transfer-Historie | 180 s |
| `live_matchday` | Spieltage, Live-Spiele, Live-Punkte, Bundesliga-Tabelle, Team-Ranking, Match-Details & Eventtypen (`/competitions/{id}/matchdays`, `/table`, `/ranking`, `/matches/{id}/details`, `/live/eventtypes`) | 900 s *(automatisch **60 s** bei Live-Spielen)* |
| `feed_achievements` | Liga-Aktivitäten-Feed, Kommentare, Erfolge, Rivalen-Profile (`/leagues/{id}/activitiesFeed`, `/user/achievements`, `/managers/{id}/*`) | 300 s |
| `news_predictions` | Stage, Bundesliga-News, Detail-Artikel, Voraussichtliche Aufstellungen (`/base/overview`, `/stage`, `/news/{id}`, `/predictions/teams/{id}`, `/items/{id}`) | 1800 s |
| `challenges` | Challenge-Lobby, Division Ladder, Skill Points, Livepitch & Tabellen (`/challenges/lobby/*`, `/challenges/{id}/*`) | 900 s |

Zusätzlich stehen im **Sidebar-Panel** und in den **Karten** On-Demand-Detailabfragen über eine interne WebSocket-API (mit TTL-Cache) bereit, damit die Home-Assistant-Datenbank (Recorder) nicht durch riesige Verlaufs-Attribute aufgebläht wird.

---

## Installation

### Option 1: HACS (Custom Repository)
1. Öffne **HACS → Integrationen → Drei-Punkte-Menü → Benutzerdefinierte Repositories**.
2. Füge die URL deines Repositories als Kategorie **Integration** hinzu.
3. Installiere **Kickbase** und starte Home Assistant neu.
4. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen → Kickbase**.

### Option 2: Manuelle Installation
1. Kopiere den Ordner [`custom_components/kickbase`](custom_components/kickbase) in dein Home-Assistant-Verzeichnis `<config>/custom_components/kickbase`.
2. Starte Home Assistant neu.
3. Richte die Integration über die UI unter **Einstellungen → Geräte & Dienste → Integration hinzufügen** ein.

---

## Modulare Lovelace Cards

Die Integration registriert automatisch `/api/kickbase_static/kickbase-cards.js` im Frontend – es ist keine manuelle Resource-Konfiguration nötig. Im Dashboard-Editor findest du folgende Karten direkt im Picker (inkl. visuellem Konfigurations-Editor):

- `custom:kickbase-overview-card` – Budget, Max-Gebot, Teamwert, Platzierung, Deadline & Status-Pills
- `custom:kickbase-lineup-card` – Interaktives Spielfeld mit Formation, Status-Indikatoren, Kapitän & Spieler-Modal
- `custom:kickbase-squad-card` – Sortier- & filterbarer Kader mit 24h-Marktwert-Trend, G&V und Ø-Punkten
- `custom:kickbase-market-card` – Transfermarkt-Listings + Scout-Watchlist mit Ablauf-Timer
- `custom:kickbase-standings-card` – Liga-Tabelle & Battles (Klick auf Manager öffnet Rivalen-Kader & Transfers)
- `custom:kickbase-live-card` – Live-Spiele, Live-Events-Modal, Spieltags-Ranking & Bundesliga-Tabelle
- `custom:kickbase-feed-news-card` – Liga-Feed, Erfolge, Bundesliga-News & Voraussichtliche Aufstellungen
- `custom:kickbase-challenges-card` – Division, Skill Points & aktive Matchday-Challenges

Ein fertiges Beispiel-Dashboard findest du unter [`examples/lovelace-dashboard.yaml`](examples/lovelace-dashboard.yaml).

---

## Entitäten, Events & Services

### Sensoren & Binary Sensors (pro Liga + Global)
- **Sensoren:** Budget, Max. Gebot, Teamwert, Tabellenplatz, Gesamtpunkte, Spieltagspunkte, Kadergröße, Marktwert-Trend 24h, Aufstellung Formation, Aufstellungs-Deadline, Transfermarkt-Spieler, Scout-Liste, Nächstes Marktwert-Update, Aktueller Spieltag, Live-Punkte, Letzte Liga-Aktivität, Erfolge, Letzte News, Challenge Division, Skill Points *(plus optional einzelne Spieler-Sensoren pro Kader-Spieler)*.
- **Binary Sensors:** `Budget im Minus`, `Aufstellung unvollständig/Problem`, `Kader-Marktwert steigt`, `Scout-Spieler auf Transfermarkt`, `Spieltag Live`.
- **Kalender (`calendar`):** Spielplan & Aufstellungs-Deadlines für Home Assistant Kalender & Erinnerungen.
- **Bilder (`image`):** Manager-Profilbild & Liga-Logos.

### Home Assistant Bus Events
- `kickbase_negative_budget` – Budget fällt unter 0 €
- `kickbase_scouted_on_market` – Beobachteter Spieler erscheint auf dem Transfermarkt
- `kickbase_new_activity` – Neuer Eintrag im Liga-Feed
- `kickbase_live_player_event` – Neues Live-Ereignis (Tor/Karte/etc.) eines eigenen Spielers

Beispiel-Automationen findest du unter [`examples/automations.yaml`](examples/automations.yaml).

### Service
- `kickbase.refresh_data` – Aktualisiert wahlweise eine bestimmte `league_id` und/oder ein einzelnes `module` sofort auf Abruf.

---

## Tests lokal ausführen

```bash
python -m unittest discover -s tests -v
```
