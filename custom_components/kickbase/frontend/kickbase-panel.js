/**
 * Kickbase Sidebar Panel for Home Assistant.
 * Renders a modular multi-league Command Center reusing the standalone card components
 * plus an integrated Local SQLite Player Database & History Explorer.
 */

import {
  KICKBASE_CSS,
  avatarImg,
  escapeHtml,
  formatCompactEur,
  formatDateTime,
  formatSignedCompactEur,
  kickbaseStore,
  openKickbaseModal,
  playerImg,
  positionClass,
  teamImg,
} from "./kickbase-shared.js?v=1.0.0";
import "./kickbase-cards.js?v=1.0.0";

const PANEL_MODULES = [
  { id: "overview", label: "Manager & Budget", tag: "kickbase-overview-card", requires: "league_overview" },
  { id: "lineup", label: "Spielfeld-Aufstellung", tag: "kickbase-lineup-card", requires: "squad_lineup" },
  { id: "squad", label: "Kader & Marktwerte", tag: "kickbase-squad-card", requires: "squad_lineup" },
  { id: "market", label: "Transfermarkt & Scout", tag: "kickbase-market-card", requires: "market_transfers" },
  { id: "standings", label: "Tabelle & Battles", tag: "kickbase-standings-card", requires: "league_overview" },
  { id: "live", label: "Live-Spieltag", tag: "kickbase-live-card", requires: "live_matchday" },
  { id: "feed", label: "Feed, News & Prognosen", tag: "kickbase-feed-news-card", requiresAny: ["feed_achievements", "news_predictions"] },
  { id: "challenges", label: "Challenges", tag: "kickbase-challenges-card", requires: "challenges" },
];

const SCOPE_LABELS = {
  my_squad: "Mein Kader",
  market: "Markt",
  rival_squad: "Anderes Team",
  scouted: "Scout",
};

const STORAGE_KEY = "kickbase_ha_panel_hidden_cards_v1";

class KickbasePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._snapshot = null;
    this._selectedLeagueId = null;
    this._activeTab = "dashboard";
    this._customizeOpen = false;
    this._loading = false;
    this._searchQuery = "";
    this._searchResults = [];
    this._searchTimer = null;
    this._hiddenCards = this._loadHiddenCards();

    // Local DB Explorer state
    this._dbScope = "all";
    this._dbStatus = "all";
    this._dbSort = "pos";
    this._dbQuery = "";
    this._dbPlayers = [];
    this._dbStats = null;
    this._dbLoading = false;
    this._dbLoadedLeague = null;

    // API Logs state (Item 8)
    this._apiLogs = [];
    this._apiLogsLoading = false;
    this._apiLogFilter = "";
  }

  _loadHiddenCards() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return new Set(raw ? JSON.parse(raw) : []);
    } catch {
      return new Set();
    }
  }

  _saveHiddenCards() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...this._hiddenCards]));
    } catch {
      // ignore storage quota errors
    }
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._loadSnapshot();
    } else {
      this._pushHassToCards();
    }
  }

  _pushHassToCards() {
    this.shadowRoot.querySelectorAll("[data-kb-card]").forEach((card) => {
      card.hass = this._hass;
      if (this._snapshot) {
        card.snapshot = this._snapshot;
      }
    });
  }

  async _loadSnapshot(force = false) {
    if (!this._hass || this._loading) return;
    this._loading = true;
    this._render();
    try {
      this._snapshot = await kickbaseStore.getSnapshot(this._hass, {
        leagueId: this._selectedLeagueId || undefined,
        force,
      });
      this._error = null;
      if (!this._selectedLeagueId && this._snapshot?.selected_league_id) {
        this._selectedLeagueId = this._snapshot.selected_league_id;
      }
      if (this._snapshot?.db_stats) {
        this._dbStats = this._snapshot.db_stats;
      }
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
      this._render();
      if (this._activeTab === "local_db") {
        this._loadLocalDbPlayers();
      }
    }
  }

  async _loadLocalDbPlayers() {
    const lid = this._selectedLeagueId || this._snapshot?.selected_league_id;
    if (!this._hass || !lid || this._dbLoading) return;
    this._dbLoading = true;
    this._renderLocalDbView();
    try {
      const res = await kickbaseStore.queryLocalPlayers(this._hass, {
        leagueId: lid,
        query: this._dbQuery,
        scope: this._dbScope,
        statusSeverity: this._dbStatus,
        limit: 150,
      });
      this._dbPlayers = res?.players || [];
      if (res?.stats) this._dbStats = res.stats;
      this._dbLoadedLeague = lid;
    } catch {
      // keep existing state on transient error
    } finally {
      this._dbLoading = false;
      this._renderLocalDbView();
    }
  }

  _isModuleAvailable(modDef) {
    const enabled = new Set(this._snapshot?.enabled_modules || []);
    if (modDef.requires) return enabled.has(modDef.requires);
    if (modDef.requiresAny) return modDef.requiresAny.some((m) => enabled.has(m));
    return true;
  }

  _visibleCardsForTab() {
    const available = PANEL_MODULES.filter((m) => this._isModuleAvailable(m));
    if (this._activeTab === "dashboard") {
      return available.filter((m) => !this._hiddenCards.has(m.id));
    }
    if (this._activeTab === "squad") {
      return available.filter((m) => ["lineup", "squad", "overview"].includes(m.id));
    }
    if (this._activeTab === "market") {
      return available.filter((m) => ["market", "overview"].includes(m.id));
    }
    if (this._activeTab === "live") {
      return available.filter((m) => ["live", "lineup"].includes(m.id));
    }
    if (this._activeTab === "league") {
      return available.filter((m) => ["standings", "feed"].includes(m.id));
    }
    if (this._activeTab === "challenges") {
      return available.filter((m) => ["challenges"].includes(m.id));
    }
    return available;
  }

  _render() {
    const snap = this._snapshot;
    const user = snap?.user || {};
    const leagues = snap?.leagues || [];
    const activeLeague = leagues.find((l) => l.id === this._selectedLeagueId) || leagues[0];
    const enabled = new Set(snap?.enabled_modules || []);
    const availableCards = PANEL_MODULES.filter((m) => this._isModuleAvailable(m));
    const dbStats = this._dbStats || snap?.db_stats;

    const tabs = [
      { id: "dashboard", label: "Modulares Dashboard", show: true },
      { id: "local_db", label: `💾 Alle Spieler DB${dbStats ? ` (${dbStats.players_count ?? 0})` : ""}`, show: Boolean(snap?.configured) },
      { id: "api_logs", label: "📋 API & DB Logs", show: Boolean(snap?.configured) },
      { id: "squad", label: "Kader & Aufstellung", show: enabled.has("squad_lineup") },
      { id: "market", label: "Transfermarkt", show: enabled.has("market_transfers") },
      { id: "live", label: "Live & Bundesliga", show: enabled.has("live_matchday") },
      { id: "league", label: "Tabelle, Feed & News", show: enabled.has("league_overview") || enabled.has("feed_achievements") || enabled.has("news_predictions") },
      { id: "challenges", label: "Challenges", show: enabled.has("challenges") },
    ].filter((t) => t.show);

    this.shadowRoot.innerHTML = `
      <style>
        ${KICKBASE_CSS}
        :host {
          min-height: 100vh;
          background: radial-gradient(circle at top right, rgba(255, 70, 0, 0.14), transparent 45%), #0b0f15;
          padding: 18px;
        }
        .kb-shell { max-width: 1480px; margin: 0 auto; }
        .kb-topbar {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 14px 18px;
          border-radius: 18px;
          background: rgba(18, 24, 34, 0.92);
          border: 1px solid var(--kb-border);
          margin-bottom: 16px;
        }
        .kb-topbar-left, .kb-topbar-right {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-wrap: wrap;
        }
        .kb-select, .kb-input {
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid var(--kb-border);
          color: var(--kb-text);
          border-radius: 10px;
          padding: 7px 12px;
          font-size: 13px;
          font-weight: 600;
          outline: none;
        }
        .kb-select option { background: #141a24; color: #f1f5f9; }
        .kb-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
          gap: 16px;
          align-items: start;
        }
        @media (max-width: 600px) {
          :host { padding: 10px; }
          .kb-grid { grid-template-columns: 1fr; }
        }
        .kb-customizer {
          background: rgba(18, 24, 34, 0.96);
          border: 1px solid var(--kb-border);
          border-radius: 14px;
          padding: 12px 16px;
          margin-bottom: 16px;
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          align-items: center;
        }
        .kb-search-wrap { position: relative; }
        .kb-search-dropdown {
          position: absolute;
          top: calc(100% + 6px);
          right: 0;
          width: min(380px, 90vw);
          max-height: 380px;
          overflow-y: auto;
          background: #131a24;
          border: 1px solid rgba(255,255,255,0.16);
          border-radius: 14px;
          padding: 8px;
          z-index: 50;
          box-shadow: 0 18px 40px rgba(0,0,0,0.5);
        }
      </style>

      <div class="kb-shell">
        <div class="kb-topbar">
          <div class="kb-topbar-left">
            <button class="kb-btn" id="kb-menu-btn" title="Home Assistant Menü">☰</button>
            <div class="kb-badge-icon">KB</div>
            ${avatarImg(user) ? `<img class="kb-avatar round" src="${escapeHtml(avatarImg(user))}"/>` : ""}
            <div>
              <div class="kb-title" style="font-size:18px">Kickbase Command Center</div>
              <div class="kb-subtitle">
                ${escapeHtml(user.name || "Manager")} ${user.has_pro ? "· ⭐ Pro" : ""} · Nur lokale DB-Werte
                ${dbStats ? ` · 💾 ${dbStats.players_count ?? 0} Spieler · 📸 ${dbStats.photos_cached ?? 0} Fotos · Sync ${formatDateTime(snap?.last_sync_at)}` : ""}
              </div>
            </div>
          </div>

          <div class="kb-topbar-right">
            ${
              leagues.length
                ? `
              <select class="kb-select" id="kb-league-select">
                ${leagues
                  .map(
                    (l) =>
                      `<option value="${escapeHtml(l.id)}" ${
                        l.id === (activeLeague?.id || "") ? "selected" : ""
                      }>${escapeHtml(l.name)} (#${l.rank || "–"})</option>`
                  )
                  .join("")}
              </select>`
                : ""
            }
            <div class="kb-search-wrap">
              <input class="kb-input" id="kb-player-search" type="search" placeholder="Lokal suchen (0 API-Calls)..." value="${escapeHtml(this._searchQuery)}"/>
              <div id="kb-search-dropdown-slot"></div>
            </div>
            <button class="kb-btn ${this._customizeOpen ? "active" : ""}" id="kb-customize-btn">⚙ Module</button>
            <button class="kb-btn" id="kb-panel-refresh" title="Ansicht aus lokaler Datenbank neu laden (0 API-Calls)">${this._loading ? "⏳ Lädt..." : "↻ DB laden"}</button>
          </div>
        </div>

        ${
          this._customizeOpen
            ? `
          <div class="kb-customizer">
            <span class="kb-kpi-label" style="margin-right:8px">Sichtbare Dashboard-Karten:</span>
            ${availableCards
              .map((m) => {
                const visible = !this._hiddenCards.has(m.id);
                return `<button class="kb-btn ${visible ? "active" : ""}" data-toggle-card="${escapeHtml(m.id)}">${visible ? "✓ " : ""}${escapeHtml(m.label)}</button>`;
              })
              .join("")}
          </div>`
            : ""
        }

        <div class="kb-tabs" style="margin-bottom:16px">
          ${tabs
            .map(
              (t) =>
                `<button class="kb-btn ${this._activeTab === t.id ? "active" : ""}" data-panel-tab="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`
            )
            .join("")}
        </div>

        <div id="kb-main-content"></div>
      </div>
    `;

    const mainContent = this.shadowRoot.getElementById("kb-main-content");
    if (this._error) {
      mainContent.innerHTML = `<div class="kb-empty">Fehler beim Laden: ${escapeHtml(this._error)}</div>`;
    } else if (!snap) {
      mainContent.innerHTML = `<div class="kb-empty">Lade Kickbase-Module...</div>`;
    } else if (!snap.configured) {
      mainContent.innerHTML = `<div class="kb-empty">Bitte richte zuerst die Kickbase-Integration unter Einstellungen → Geräte & Dienste ein.</div>`;
    } else if (this._activeTab === "local_db") {
      mainContent.innerHTML = `<div id="kb-local-db-slot"></div>`;
      this._renderLocalDbView();
      const targetLid = this._selectedLeagueId || activeLeague?.id;
      if (this._dbLoadedLeague !== targetLid && !this._dbLoading) {
        this._loadLocalDbPlayers();
      }
    } else if (this._activeTab === "api_logs") {
      mainContent.innerHTML = `<div id="kb-api-logs-slot"></div>`;
      this._renderApiLogsView();
      if (!this._apiLogs.length && !this._apiLogsLoading) {
        this._loadApiLogs();
      }
    } else {
      const grid = document.createElement("div");
      grid.className = "kb-grid";
      mainContent.appendChild(grid);

      const cards = this._visibleCardsForTab();
      for (const modDef of cards) {
        const el = document.createElement(modDef.tag);
        el.setAttribute("data-kb-card", modDef.id);
        el.setConfig({
          league_id: this._selectedLeagueId || activeLeague?.id || "",
          limit: this._activeTab === "dashboard" ? 10 : 30,
        });
        el.snapshot = snap;
        el.hass = this._hass;
        grid.appendChild(el);
      }
      if (!cards.length) {
        grid.innerHTML = `<div class="kb-empty">Alle Karten sind ausgeblendet. Klicke auf „⚙ Module“, um Karten einzublenden.</div>`;
      }
    }

    this._renderSearchDropdown(activeLeague);
    this._bindEvents(activeLeague);
  }

  _renderLocalDbView() {
    const slot = this.shadowRoot.getElementById("kb-local-db-slot");
    if (!slot) return;
    const stats = this._dbStats || this._snapshot?.db_stats || {};
    const activeLeagueId = this._selectedLeagueId || this._snapshot?.selected_league_id;
    const players = this._dbPlayers || [];

    let sortedPlayers = [...players];
    sortedPlayers.sort((a, b) => {
      if (this._dbSort === "pos") {
        const pa = Number(a.position_code || (a.position && a.position.code) || 99);
        const pb = Number(b.position_code || (b.position && b.position.code) || 99);
        return pa !== pb ? pa - pb : (b.market_value || 0) - (a.market_value || 0);
      }
      if (this._dbSort === "trend") return (b.market_value_24h_change || 0) - (a.market_value_24h_change || 0);
      if (this._dbSort === "name") return (a.name || "").localeCompare(b.name || "");
      return (b.market_value || 0) - (a.market_value || 0);
    });

    slot.innerHTML = `
      <div class="kb-card">
        <div class="kb-card-header">
          <div class="kb-title-wrap">
            <div class="kb-badge-icon">DB</div>
            <div>
              <div class="kb-title">Lokale SQLite Spieler-Datenbank & Historie</div>
              <div class="kb-subtitle">
                Gebündelter Stündlicher Sync · Abfragen hier kosten 0 Kickbase-API-Requests · Letzter Sync: ${formatDateTime(stats.last_sync_at || this._snapshot?.last_sync_at)}
              </div>
            </div>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <button class="kb-btn" id="kb-db-sync-now" ${this._loading ? "disabled" : ""} title="Manuellen Abruf vom Kickbase-Server außerhalb des 1h-Intervalls starten">${this._loading ? "⏳ Server-Sync..." : "🌐 Server-Sync jetzt"}</button>
            <button class="kb-btn" id="kb-db-sync-full" ${this._loading ? "disabled" : ""} title="Erzwingt kompletten Historien-Download vom Server für alle Spieler">📊 Komplette Historie laden</button>
            <button class="kb-btn" id="kb-btn-claim-bonus" title="Tägliches Bonusgeld sichern (jeden Tag um 08:00 Uhr)">🎁 Bonus sichern</button>
            <button class="kb-btn" id="kb-btn-sync-all-players" title="Alle Spieler in SQLite dauerhaft aktualisieren (11:00 / 23:00 Uhr)">⚡ DB-Spieler syncen</button>
          </div>
        </div>

        <div class="kb-kpi-grid" style="margin-bottom:14px">
          <div class="kb-kpi">
            <div class="kb-kpi-label">Spieler lokal</div>
            <div class="kb-kpi-val">${stats.players_count ?? 0}</div>
            <div class="kb-kpi-sub">Kader ${stats.my_squad_count ?? 0} · Markt ${stats.market_count ?? 0} · Rivalen ${stats.rival_players_count ?? 0}</div>
          </div>
          <div class="kb-kpi">
            <div class="kb-kpi-label">Marktwert-Punkte</div>
            <div class="kb-kpi-val">${stats.market_value_points ?? 0}</div>
            <div class="kb-kpi-sub">Tägliche Verläufe in SQLite</div>
          </div>
          <div class="kb-kpi">
            <div class="kb-kpi-label">Status-Ereignisse</div>
            <div class="kb-kpi-val">${stats.status_events_count ?? 0}</div>
            <div class="kb-kpi-sub">Verletzungen, Besitzer & Marktwechsel</div>
          </div>
          <div class="kb-kpi">
            <div class="kb-kpi-label">Foto-Cache & DB</div>
            <div class="kb-kpi-val">${stats.photos_cached ?? 0} Fotos</div>
            <div class="kb-kpi-sub">${stats.db_size_kb ?? 0} KB SQLite · ${(stats.last_sync?.api_requests ?? this._snapshot?.last_api_requests ?? 0)} API-Calls zuletzt</div>
          </div>
        </div>

        <div class="kb-tabs" style="align-items:center">
          <button class="kb-btn ${this._dbScope === "all" ? "active" : ""}" data-db-scope="all">Alle</button>
          <button class="kb-btn ${this._dbScope === "my_squad" ? "active" : ""}" data-db-scope="my_squad">Mein Kader</button>
          <button class="kb-btn ${this._dbScope === "market" ? "active" : ""}" data-db-scope="market">Transfermarkt</button>
          <button class="kb-btn ${this._dbScope === "rival_squad" ? "active" : ""}" data-db-scope="rival_squad">Andere Manager</button>
          <button class="kb-btn ${this._dbScope === "scouted" ? "active" : ""}" data-db-scope="scouted">Scout-Liste</button>
          <span style="flex:1"></span>
          <button class="kb-btn ${this._dbStatus === "all" ? "active" : ""}" data-db-status="all">Alle Status</button>
          <button class="kb-btn ${this._dbStatus === "issues" ? "active" : ""}" data-db-status="issues">⚠ Probleme</button>
          <button class="kb-btn ${this._dbStatus === "ok" ? "active" : ""}" data-db-status="ok">Fit</button>
          <input class="kb-input" id="kb-db-filter-input" type="search" placeholder="Name / Manager filtern..." value="${escapeHtml(this._dbQuery)}"/>
        </div>

        <div class="kb-tabs" style="align-items:center;margin-top:8px">
          <span style="font-size:11px;color:var(--kb-muted);margin-right:6px">Sortierung:</span>
          <button class="kb-btn ${this._dbSort === "pos" ? "active" : ""}" data-db-sort="pos">Position</button>
          <button class="kb-btn ${this._dbSort === "mv" ? "active" : ""}" data-db-sort="mv">Marktwert</button>
          <button class="kb-btn ${this._dbSort === "trend" ? "active" : ""}" data-db-sort="trend">24h Trend</button>
          <button class="kb-btn ${this._dbSort === "name" ? "active" : ""}" data-db-sort="name">Name</button>
        </div>

        <div class="kb-list">
          ${
            this._dbLoading && !sortedPlayers.length
              ? `<div class="kb-empty">Lade lokale Datenbank...</div>`
              : sortedPlayers.length
              ? sortedPlayers
                  .map((p) => {
                    const chg = Number(p.market_value_24h_change || 0);
                    const pImg = playerImg(p);
                    const tImg = teamImg(p);
                    const scopeBadges = (p.scopes || [])
                      .map((sc) => `<span class="kb-pill" style="padding:1px 6px;font-size:10px">${escapeHtml(SCOPE_LABELS[sc] || sc)}</span>`)
                      .join("");
                    return `
                      <div class="kb-row clickable" data-db-player-id="${escapeHtml(p.id)}">
                        <div class="kb-row-left">
                          ${pImg ? `<img class="kb-avatar" src="${escapeHtml(pImg)}" loading="lazy"/>` : ""}
                          ${tImg ? `<img class="kb-crest" src="${escapeHtml(tImg)}" loading="lazy"/>` : ""}
                          <div class="kb-row-main">
                            <div class="kb-row-name">${escapeHtml(p.full_name || p.name)}</div>
                            <div class="kb-row-meta">
                              <span class="kb-pos-tag ${positionClass(p.position_code)}">${escapeHtml(p.position?.short)}</span>
                              <span class="kb-pill ${escapeHtml(p.status?.severity || "ok")}" style="padding:1px 6px;font-size:10px">${escapeHtml(p.status?.label_de || "Fit")}</span>
                              ${scopeBadges}
                              <span>Besitzer: ${escapeHtml(p.owner_name || "Kickbase")}</span>
                              <span>· Ø ${p.average_points ?? 0}</span>
                            </div>
                          </div>
                        </div>
                        <div class="kb-row-right">
                          <div class="kb-row-val">${formatCompactEur(p.market_value)}</div>
                          <div class="kb-row-sub ${chg >= 0 ? "kb-pos" : "kb-neg"}">${formatSignedCompactEur(chg)} (24h)</div>
                        </div>
                      </div>
                    `;
                  })
                  .join("")
              : `<div class="kb-empty">Keine Spieler in diesem Filter in der lokalen Datenbank gefunden.</div>`
          }
        </div>
      </div>
    `;

    slot.querySelectorAll("[data-db-scope]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._dbScope = btn.dataset.dbScope;
        this._loadLocalDbPlayers();
      })
    );
    slot.querySelectorAll("[data-db-status]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._dbStatus = btn.dataset.dbStatus;
        this._loadLocalDbPlayers();
      })
    );
    const filterInput = slot.querySelector("#kb-db-filter-input");
    if (filterInput) {
      filterInput.addEventListener("input", (e) => {
        this._dbQuery = e.target.value;
        this._loadLocalDbPlayers();
      });
    }
    slot.querySelectorAll("[data-db-sort]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._dbSort = btn.dataset.dbSort;
        this._renderLocalDbView();
      })
    );
    slot.querySelector("#kb-btn-claim-bonus")?.addEventListener("click", () => {
      this._claimDailyBonus(activeLeagueId);
    });
    slot.querySelector("#kb-btn-sync-all-players")?.addEventListener("click", () => {
      this._syncAllDbPlayers(activeLeagueId);
    });
    slot.querySelector("#kb-db-sync-now")?.addEventListener("click", () => {
      this._triggerSync(activeLeagueId, false);
    });
    slot.querySelector("#kb-db-sync-full")?.addEventListener("click", () => {
      this._triggerSync(activeLeagueId, true);
    });
    slot.querySelectorAll("[data-db-player-id]").forEach((row) =>
      row.addEventListener("click", () => {
        openKickbaseModal(this.shadowRoot, this._hass, "player", {
          leagueId: activeLeagueId,
          playerId: row.dataset.dbPlayerId,
        });
      })
    );
  }

  async _triggerSync(leagueId, forceDetails = false) {
    if (!this._hass || this._loading) return;
    this._loading = true;
    this._render();
    try {
      this._snapshot = await kickbaseStore.refresh(this._hass, {
        leagueId,
        forceDetails,
      });
      if (this._snapshot?.db_stats) {
        this._dbStats = this._snapshot.db_stats;
      }
      this._error = null;
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
      this._render();
      if (this._activeTab === "local_db") {
        this._loadLocalDbPlayers();
      }
    }
  }

  async _claimDailyBonus(leagueId) {
    if (!this._hass || this._bonusLoading) return;
    this._bonusLoading = true;
    try {
      const res = await kickbaseStore.collectDailyBonus(this._hass, { leagueId });
      alert(`Daily Bonus: ${res?.status || "erfolgreich"} · Budget: ${formatCompactEur(res?.budget)}`);
      this._loadSnapshot(true);
    } catch (err) {
      alert(`Fehler beim Bonus-Abruf: ${err.message || err}`);
    } finally {
      this._bonusLoading = false;
    }
  }

  async _syncAllDbPlayers(leagueId) {
    if (!this._hass || this._dbSyncLoading) return;
    this._dbSyncLoading = true;
    try {
      const res = await kickbaseStore.syncAllDatabasePlayers(this._hass, { leagueId });
      alert(`DB-Sync abgeschlossen: ${res?.synced_count ?? 0} von ${res?.total_count ?? 0} Spielern aktualisiert.`);
      this._loadSnapshot(true);
    } catch (err) {
      alert(`Fehler beim DB-Sync: ${err.message || err}`);
    } finally {
      this._dbSyncLoading = false;
    }
  }

  async _loadApiLogs() {
    if (!this._hass) return;
    this._apiLogsLoading = true;
    this._renderApiLogsView();
    try {
      const lid = this._selectedLeagueId || this._snapshot?.selected_league_id;
      const res = await kickbaseStore.getRequestLogs(this._hass, { leagueId: lid, limit: 150 });
      this._apiLogs = res?.logs || [];
    } catch (err) {
      console.error("Failed to load API logs:", err);
    } finally {
      this._apiLogsLoading = false;
      this._renderApiLogsView();
    }
  }

  _renderApiLogsView() {
    const slot = this.shadowRoot.getElementById("kb-api-logs-slot");
    if (!slot) return;
    const logs = this._apiLogs || [];
    const filter = (this._apiLogFilter || "").toLowerCase().trim();
    const filtered = filter
      ? logs.filter((l) => (l.url || "").toLowerCase().includes(filter) || (l.method || "").toLowerCase().includes(filter) || String(l.status_code || "").includes(filter))
      : logs;

    slot.innerHTML = `
      <div class="kb-card">
        <div class="kb-card-header">
          <div class="kb-title-wrap">
            <div class="kb-badge-icon">LOG</div>
            <div>
              <div class="kb-title">Kickbase HTTP API Anfragen & Antworten (SQLite)</div>
              <div class="kb-subtitle">
                Alle Abfragen & von Kickbase erhaltene Daten · Klick auf einen Eintrag öffnet die vollständige JSON-Antwort
              </div>
            </div>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <input class="kb-input" id="kb-api-log-filter" type="search" placeholder="Endpunkt / Status filtern..." value="${escapeHtml(this._apiLogFilter)}"/>
            <button class="kb-btn" id="kb-api-log-refresh">${this._apiLogsLoading ? "⏳ Lädt..." : "↻ Logs laden"}</button>
          </div>
        </div>

        <div class="kb-list">
          ${
            this._apiLogsLoading && !logs.length
              ? `<div class="kb-empty">Lade API-Logs aus der Datenbank...</div>`
              : !filtered.length
              ? `<div class="kb-empty">Keine API-Logs aufgezeichnet. Führe einen Sync aus oder filtere anders.</div>`
              : filtered
                  .map((l) => {
                    const statusOk = Number(l.status_code) >= 200 && Number(l.status_code) < 300;
                    const methodColor = l.method === "POST" ? "style='background:rgba(59,130,246,0.2);color:#93c5fd'" : "style='background:rgba(34,197,94,0.2);color:#86efac'";
                    return `
                      <div class="kb-row clickable" data-api-log-id="${l.id}">
                        <div class="kb-row-left">
                          <span class="kb-pill" ${methodColor}>${escapeHtml(l.method)}</span>
                          <span class="kb-pill ${statusOk ? "ok" : "danger"}">${l.status_code}</span>
                          <div class="kb-row-main">
                            <div class="kb-row-name" style="font-family:monospace;font-size:12px">${escapeHtml(l.url)}</div>
                            <div class="kb-row-meta">
                              <span>⏱ ${l.duration_ms ?? 0} ms</span>
                              <span>· 📅 ${formatDateTime(l.created_at)}</span>
                              <span>· ${escapeHtml(l.response_preview || "")}</span>
                            </div>
                          </div>
                        </div>
                        <div class="kb-row-right">
                          <button class="kb-btn" style="padding:4px 8px;font-size:11px">Inspect JSON ↗</button>
                        </div>
                      </div>
                    `;
                  })
                  .join("")
          }
        </div>
      </div>
    `;

    slot.querySelector("#kb-api-log-refresh")?.addEventListener("click", () => {
      this._loadApiLogs();
    });
    slot.querySelector("#kb-api-log-filter")?.addEventListener("input", (e) => {
      this._apiLogFilter = e.target.value;
      this._renderApiLogsView();
    });
    slot.querySelectorAll("[data-api-log-id]").forEach((row) => {
      row.addEventListener("click", () => {
        this._showApiLogDetail(row.dataset.apiLogId);
      });
    });
  }

  async _showApiLogDetail(logId) {
    let backdrop = this.shadowRoot.querySelector(".kb-modal-backdrop");
    if (backdrop) backdrop.remove();

    backdrop = document.createElement("div");
    backdrop.className = "kb-modal-backdrop";
    backdrop.innerHTML = `<div class="kb-modal"><div class="kb-empty">Lade vollständige Kickbase-Antwort #${logId}...</div></div>`;
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.remove();
    });
    this.shadowRoot.appendChild(backdrop);

    const modal = backdrop.querySelector(".kb-modal");
    try {
      const detail = await kickbaseStore.getRequestLogDetail(this._hass, { logId });
      let prettyJson = detail.response_json || "{}";
      try {
        prettyJson = JSON.stringify(JSON.parse(prettyJson), null, 2);
      } catch {
        // raw
      }

      modal.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
          <div>
            <div class="kb-title" style="font-size:16px">${escapeHtml(detail.method)} ${escapeHtml(detail.url)}</div>
            <div class="kb-subtitle">Status: ${detail.status_code} · Dauer: ${detail.duration_ms} ms · ${formatDateTime(detail.created_at)}</div>
          </div>
          <div style="display:flex;gap:6px">
            <button class="kb-btn" id="kb-copy-log-json">📋 Copy JSON</button>
            <button class="kb-btn" id="kb-close-log-modal">✕</button>
          </div>
        </div>
        <div style="background:#0a0d13;border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:12px;max-height:65vh;overflow:auto">
          <pre style="margin:0;font-family:monospace;font-size:12px;color:#a5f3fc;white-space:pre-wrap;word-break:break-all">${escapeHtml(prettyJson)}</pre>
        </div>
      `;
      modal.querySelector("#kb-close-log-modal")?.addEventListener("click", () => backdrop.remove());
      modal.querySelector("#kb-copy-log-json")?.addEventListener("click", (e) => {
        navigator.clipboard.writeText(prettyJson).then(() => {
          e.target.textContent = "✓ Copied!";
          setTimeout(() => { e.target.textContent = "📋 Copy JSON"; }, 2000);
        });
      });
    } catch (err) {
      modal.innerHTML = `<div class="kb-empty">Fehler beim Laden des Logs: ${escapeHtml(err.message || String(err))}</div>`;
    }
  }

  _renderSearchDropdown(activeLeague) {
    const slot = this.shadowRoot.getElementById("kb-search-dropdown-slot");
    if (!slot) return;
    const q = this._searchQuery.trim();
    if (!this._searchResults.length && (!q || q.length < 2)) {
      slot.innerHTML = "";
      return;
    }
    if (!this._searchResults.length && q.length >= 2) {
      slot.innerHTML = `
        <div class="kb-search-dropdown">
          <div class="kb-empty" style="padding:10px">Kein Treffer in der lokalen Datenbank.</div>
        </div>
      `;
    } else {
      slot.innerHTML = `
        <div class="kb-search-dropdown">
          <div style="font-size:10px;color:var(--kb-muted);padding:2px 6px 6px;display:flex;justify-content:space-between">
            <span>💾 Lokale Datenbank (0 API-Calls)</span>
          </div>
          <div class="kb-list">
            ${this._searchResults
              .map(
                (p) => `
                <div class="kb-row clickable" data-search-player-id="${escapeHtml(p.id)}">
                  <div class="kb-row-left">
                    ${playerImg(p) ? `<img class="kb-avatar" src="${escapeHtml(playerImg(p))}"/>` : ""}
                    <div class="kb-row-main">
                      <div class="kb-row-name">${escapeHtml(p.full_name || p.name)}</div>
                      <div class="kb-row-meta"><span class="kb-pos-tag ${positionClass(p.position_code)}">${escapeHtml(p.position?.short)}</span> · ${escapeHtml(p.owner_name || "Kickbase")}</div>
                    </div>
                  </div>
                  <div class="kb-row-val">${formatCompactEur(p.market_value)}</div>
                </div>`
              )
              .join("")}
          </div>
        </div>
      `;
    }

    slot.querySelectorAll("[data-search-player-id]").forEach((row) => {
      row.addEventListener("click", () => {
        const pid = row.dataset.searchPlayerId;
        this._searchResults = [];
        this._renderSearchDropdown(activeLeague);
        openKickbaseModal(this.shadowRoot, this._hass, "player", {
          leagueId: this._selectedLeagueId || activeLeague?.id,
          playerId: pid,
        });
      });
    });
  }

  _bindEvents(activeLeague) {
    this.shadowRoot.getElementById("kb-menu-btn")?.addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
    });

    this.shadowRoot.getElementById("kb-league-select")?.addEventListener("change", (e) => {
      this._selectedLeagueId = e.target.value;
      this._dbLoadedLeague = null;
      this._loadSnapshot(false);
    });

    this.shadowRoot.getElementById("kb-customize-btn")?.addEventListener("click", () => {
      this._customizeOpen = !this._customizeOpen;
      this._render();
    });

    this.shadowRoot.getElementById("kb-panel-refresh")?.addEventListener("click", () => {
      this._loadSnapshot(true);
    });

    this.shadowRoot.querySelectorAll("[data-toggle-card]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.dataset.toggleCard;
        if (this._hiddenCards.has(id)) this._hiddenCards.delete(id);
        else this._hiddenCards.add(id);
        this._saveHiddenCards();
        this._render();
      });
    });

    this.shadowRoot.querySelectorAll("[data-panel-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._activeTab = btn.dataset.panelTab;
        this._render();
      });
    });

    const searchInput = this.shadowRoot.getElementById("kb-player-search");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this._searchQuery = e.target.value;
        clearTimeout(this._searchTimer);
        const q = this._searchQuery.trim();
        if (q.length < 2) {
          this._searchResults = [];
          this._renderSearchDropdown(activeLeague);
          return;
        }
        this._searchTimer = setTimeout(async () => {
          const lid = this._selectedLeagueId || activeLeague?.id;
          if (!lid) return;
          try {
            const res = await kickbaseStore.queryLocalPlayers(this._hass, {
              leagueId: lid,
              query: q,
              limit: 20,
            });
            this._searchResults = res?.players || [];
            this._renderSearchDropdown(activeLeague);
          } catch {
            // ignore transient search errors
          }
        }, 180);
      });
    }
  }
}

if (!customElements.get("kickbase-panel")) {
  customElements.define("kickbase-panel", KickbasePanel);
}
