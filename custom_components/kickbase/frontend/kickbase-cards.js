/**
 * Modular Lovelace Cards Bundle for Kickbase Home Assistant Integration.
 * Exposes 8 standalone, interactive, visual-editor-enabled cards + window.customCards registration.
 */

import {
  KICKBASE_CSS,
  avatarImg,
  escapeHtml,
  formatCompactEur,
  formatDateTime,
  formatIsoCountdown,
  formatSecondsCountdown,
  formatSignedCompactEur,
  kickbaseStore,
  localImg,
  openKickbaseModal,
  playerImg,
  positionClass,
  renderPitchHtml,
  startingProbBadge,
  teamImg,
} from "./kickbase-shared.js?v=1.0.0";

/* -------------------------------------------------------------------------- */
/* Visual Lovelace Card Editor                                                */
/* -------------------------------------------------------------------------- */
class KickbaseCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._leagues = [];
    this._managers = [];
    this._loadedLeagueId = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (hass && (!this._leagues.length || this._loadedLeagueId !== (this._config.league_id || ""))) {
      this._loadEditorData();
    }
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    if (this._hass && this._loadedLeagueId !== (this._config.league_id || "")) {
      this._loadEditorData();
    }
    this._render();
  }

  _loadEditorData() {
    if (!this._hass) return;
    const lid = this._config.league_id || "";
    this._loadedLeagueId = lid;
    kickbaseStore
      .getSnapshot(this._hass, { leagueId: lid || undefined })
      .then((snap) => {
        this._leagues = snap?.leagues || [];
        this._managers = snap?.league_data?.league_overview?.standings || [];
        this._render();
      })
      .catch(() => {});
  }

  _emit(next) {
    this._config = next;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: next },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    const cfg = this._config;
    const leagueOpts = [
      `<option value="">Primäre Liga (Standard)</option>`,
      ...this._leagues.map(
        (l) =>
          `<option value="${escapeHtml(l.id)}" ${
            cfg.league_id === l.id ? "selected" : ""
          }>${escapeHtml(l.name)} (${escapeHtml(l.id)})</option>`
      ),
    ].join("");

    this.shadowRoot.innerHTML = `
      <style>
        .ed { display:flex; flex-direction:column; gap:12px; padding:8px 0; font-family:inherit; }
        label { display:flex; flex-direction:column; gap:4px; font-size:12px; font-weight:600; color:var(--primary-text-color); }
        input, select {
          padding:8px 10px; border-radius:8px; border:1px solid var(--divider-color, #444);
          background:var(--card-background-color, #1a1f29); color:var(--primary-text-color, #fff); font-size:14px;
        }
        .chk { flex-direction:row; align-items:center; gap:8px; }
      </style>
      <div class="ed">
        <label>
          Liga auswählen
          <select id="ed-league">${leagueOpts}</select>
        </label>
        ${
          cfg.type === "custom:kickbase-manager-card"
            ? `<label>
                Mitspieler / Manager auswählen
                <select id="ed-manager">
                  <option value="">Automatisch (erster Mitspieler)</option>
                  ${this._managers
                    .map(
                      (m) =>
                        `<option value="${escapeHtml(m.id)}" ${
                          String(cfg.manager_id || "") === String(m.id) ? "selected" : ""
                        }>#${m.rank ?? "?"} ${escapeHtml(m.name)} (${formatCompactEur(m.team_value)})</option>`
                    )
                    .join("")}
                </select>
              </label>`
            : ""
        }
        <label>
          Eigener Kartentitel (optional)
          <input id="ed-title" type="text" value="${escapeHtml(cfg.title || "")}" placeholder="Automatisch"/>
        </label>
        <label>
          Max. Einträge (Listen/Tabellen)
          <input id="ed-limit" type="number" min="3" max="50" value="${Number(cfg.limit || 12)}"/>
        </label>
        <label class="chk">
          <input id="ed-compact" type="checkbox" ${cfg.compact ? "checked" : ""}/>
          Kompakte Darstellung
        </label>
      </div>
    `;

    this.shadowRoot.getElementById("ed-league")?.addEventListener("change", (e) => {
      const next = { ...this._config };
      if (e.target.value) next.league_id = e.target.value;
      else delete next.league_id;
      this._emit(next);
      this._loadEditorData();
    });
    this.shadowRoot.getElementById("ed-manager")?.addEventListener("change", (e) => {
      const next = { ...this._config };
      if (e.target.value) next.manager_id = e.target.value;
      else delete next.manager_id;
      this._emit(next);
    });
    this.shadowRoot.getElementById("ed-title")?.addEventListener("input", (e) => {
      const next = { ...this._config };
      if (e.target.value) next.title = e.target.value;
      else delete next.title;
      this._emit(next);
    });
    this.shadowRoot.getElementById("ed-limit")?.addEventListener("change", (e) => {
      this._emit({ ...this._config, limit: Number(e.target.value || 12) });
    });
    this.shadowRoot.getElementById("ed-compact")?.addEventListener("change", (e) => {
      this._emit({ ...this._config, compact: Boolean(e.target.checked) });
    });
  }
}

if (!customElements.get("kickbase-card-editor")) {
  customElements.define("kickbase-card-editor", KickbaseCardEditor);
}

/* -------------------------------------------------------------------------- */
/* Shared Base Class for Modular Kickbase Cards                               */
/* -------------------------------------------------------------------------- */
class KickbaseBaseCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("kickbase-card-editor");
  }

  static getStubConfig() {
    return {};
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._snapshot = null;
    this._error = null;
    this._loading = false;
    this._lastFetch = 0;
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    this._lastFetch = 0;
    this._loadSnapshot();
  }

  set snapshot(data) {
    // Allows <kickbase-panel> to push shared snapshot directly without duplicate WS calls
    this._snapshot = data;
    this._error = null;
    this._loading = false;
    this._lastFetch = Date.now();
    this._render();
  }

  set hass(hass) {
    const firstHass = !this._hass;
    this._hass = hass;
    if (firstHass || Date.now() - this._lastFetch > 30000) {
      this._loadSnapshot();
    }
  }

  getCardSize() {
    return 4;
  }

  async _loadSnapshot(force = false) {
    if (!this._hass || this._loading) return;
    if (!force && this._snapshot && Date.now() - this._lastFetch < 15000) {
      return;
    }
    this._loading = true;
    if (!this._snapshot) this._render();
    try {
      const snap = await kickbaseStore.getSnapshot(this._hass, {
        leagueId: this._config.league_id,
        force,
      });
      this._snapshot = snap;
      this._error = null;
      this._lastFetch = Date.now();
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _activeLeagueId() {
    return this._config.league_id || this._snapshot?.selected_league_id || "";
  }

  _bindRefreshButton() {
    this.shadowRoot.querySelector("[data-refresh]")?.addEventListener("click", () => {
      if (!this._hass) return;
      this._loadSnapshot(true);
    });
  }

  _renderShell(title, subtitle, bodyHtml, pillHtml = "") {
    this.shadowRoot.innerHTML = `
      <style>${KICKBASE_CSS}</style>
      <div class="kb-card">
        <div class="kb-card-header">
          <div class="kb-title-wrap">
            <div class="kb-badge-icon">KB</div>
            <div style="min-width:0">
              <div class="kb-title">${escapeHtml(this._config.title || title)}</div>
              ${subtitle ? `<div class="kb-subtitle">${escapeHtml(subtitle)}</div>` : ""}
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:6px">
            ${pillHtml}
            <button class="kb-btn" data-refresh title="Aus lokaler Datenbank neu laden">${this._loading ? "⏳" : "↻"}</button>
          </div>
        </div>
        ${
          this._error
            ? `<div class="kb-empty">Fehler: ${escapeHtml(this._error)}</div>`
            : !this._snapshot
            ? `<div class="kb-empty">Lade Kickbase-Daten...</div>`
            : !this._snapshot.configured
            ? `<div class="kb-empty">Kickbase Integration noch nicht konfiguriert.</div>`
            : bodyHtml
        }
        ${
          this._snapshot && this._snapshot.last_sync_at
            ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.06);font-size:10px;color:var(--kb-muted)">
                 <span>💾 Letzter Sync: ${formatDateTime(this._snapshot.last_sync_at)}</span>
                 <span>📸 ${this._snapshot.db_stats?.photos_cached ?? 0} Fotos · ${this._snapshot.db_stats?.players_count ?? 0} Spieler</span>
               </div>`
            : ""
        }
      </div>
    `;
    this._bindRefreshButton();
    this._afterRender();
  }

  _afterRender() {}
  _render() {}
}

/* -------------------------------------------------------------------------- */
/* 1. kickbase-overview-card                                                  */
/* -------------------------------------------------------------------------- */
class KickbaseOverviewCard extends KickbaseBaseCard {
  _render() {
    const ld = this._snapshot?.league_data || {};
    const ov = ld.league_overview;
    const sq = ld.squad_lineup;
    const mk = ld.market_transfers;
    if (!this._snapshot?.configured || !ov) {
      return this._renderShell(
        "Liga & Budget",
        "Übersicht",
        `<div class="kb-empty">Modul „Liga & Budget“ nicht aktiv oder keine Daten.</div>`
      );
    }

    const lg = ov.league || {};
    const me = ov.me || {};
    const lineup = sq?.lineup || {};
    const summary = sq?.summary || {};
    const neg = Boolean(me.is_negative_budget);
    const pill = lg.is_live
      ? `<span class="kb-pill live"><span class="kb-dot"></span>LIVE</span>`
      : neg
      ? `<span class="kb-pill danger">Budget im Minus</span>`
      : `<span class="kb-pill ok">Spieltag ${escapeHtml(lg.matchday || "–")}</span>`;

    const body = `
      <div class="kb-kpi-grid">
        <div class="kb-kpi">
          <div class="kb-kpi-label">Budget</div>
          <div class="kb-kpi-val ${neg ? "kb-neg" : "kb-pos"}">${formatCompactEur(me.budget)}</div>
          <div class="kb-kpi-sub">Max Gebot: ${formatCompactEur(me.max_bid)}</div>
        </div>
        <div class="kb-kpi">
          <div class="kb-kpi-label">Teamwert</div>
          <div class="kb-kpi-val">${formatCompactEur(me.team_value || summary.total_market_value)}</div>
          <div class="kb-kpi-sub ${Number(summary.total_24h_change) >= 0 ? "kb-pos" : "kb-neg"}">${formatSignedCompactEur(summary.total_24h_change)} (24h)</div>
        </div>
        <div class="kb-kpi">
          <div class="kb-kpi-label">Platzierung</div>
          <div class="kb-kpi-val">#${me.rank || "–"} <span style="font-size:12px;color:var(--kb-muted)">/ ${lg.manager_count || "–"}</span></div>
          <div class="kb-kpi-sub">${me.season_points ?? 0} Pkt · ST ${me.matchday_points ?? 0}</div>
        </div>
        <div class="kb-kpi">
          <div class="kb-kpi-label">Deadline</div>
          <div class="kb-kpi-val" style="font-size:15px">${formatIsoCountdown(lineup.lock_at)}</div>
          <div class="kb-kpi-sub">${lineup.player_count ?? 0}/11 · ${escapeHtml(lineup.formation || "–")}</div>
        </div>
      </div>
      ${
        !this._config.compact && mk
          ? `
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
          <span class="kb-pill">Markt: ${mk.market_count ?? 0} Spieler</span>
          <span class="kb-pill">Scouts auf Markt: ${mk.scouted_on_market_count ?? 0}</span>
          <span class="kb-pill">Kader: ${summary.count ?? 0} Spieler</span>
          ${
            this._snapshot?.db_stats
              ? `<span class="kb-pill">💾 DB: ${this._snapshot.db_stats.players_count ?? 0} Spieler · ${this._snapshot.db_stats.photos_cached ?? 0} Fotos</span>`
              : ""
          }
          ${
            lineup.issue_count > 0
              ? `<span class="kb-pill warn">⚠ ${lineup.issue_count} Problem(e) in Startelf</span>`
              : `<span class="kb-pill ok">Startelf einsatzbereit</span>`
          }
        </div>`
          : ""
      }
    `;
    this._renderShell(lg.name || "Kickbase Liga", `${lg.competition_name || "Bundesliga"} · Saison ${lg.season || ""}`, body, pill);
  }
}

/* -------------------------------------------------------------------------- */
/* 2. kickbase-lineup-card                                                    */
/* -------------------------------------------------------------------------- */
class KickbaseLineupCard extends KickbaseBaseCard {
  getCardSize() { return 6; }

  _render() {
    const sq = this._snapshot?.league_data?.squad_lineup;
    const live = this._snapshot?.league_data?.live_matchday;
    if (!this._snapshot?.configured || !sq) {
      return this._renderShell(
        "Aufstellung",
        "Spielfeld",
        `<div class="kb-empty">Modul „Kader & Aufstellung“ nicht aktiv.</div>`
      );
    }
    const lineup = sq.lineup || {};
    const players = (live?.is_live && live?.my_eleven?.length) ? live.my_eleven : (lineup.players || []);
    const pill = `<span class="kb-pill accent">${escapeHtml(lineup.formation || "4-4-2")} · ${lineup.player_count ?? 0}/11</span>`;
    const body = `
      ${renderPitchHtml(players, lineup.formation)}
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:12px;color:var(--kb-muted)">
        <span>Lock: ${formatDateTime(lineup.lock_at)} (${formatIsoCountdown(lineup.lock_at)})</span>
        <span>${lineup.captain_name ? `👑 ${escapeHtml(lineup.captain_name)}` : "Kein Kapitän"}</span>
      </div>
    `;
    this._renderShell("Meine Aufstellung", `Spieltag ${lineup.matchday || "–"} · Klick für Spielerdetails`, body, pill);
  }

  _afterRender() {
    this.shadowRoot.querySelectorAll("[data-player-id]").forEach((el) => {
      el.addEventListener("click", () => {
        openKickbaseModal(this.shadowRoot, this._hass, "player", {
          leagueId: this._activeLeagueId(),
          playerId: el.dataset.playerId,
        });
      });
    });
  }
}

/* -------------------------------------------------------------------------- */
/* 3. kickbase-squad-card                                                     */
/* -------------------------------------------------------------------------- */
class KickbaseSquadCard extends KickbaseBaseCard {
  constructor() {
    super();
    this._sort = "mv";
    this._posFilter = "all";
  }
  getCardSize() { return 6; }

  _render() {
    const sq = this._snapshot?.league_data?.squad_lineup;
    if (!this._snapshot?.configured || !sq) {
      return this._renderShell(
        "Kader & Marktwerte",
        "Squad Tracker",
        `<div class="kb-empty">Modul „Kader & Aufstellung“ nicht aktiv.</div>`
      );
    }

    const summary = sq.summary || {};
    let players = [...(sq.squad || [])];
    if (this._posFilter !== "all") {
      players = players.filter((p) => String(p.position_code) === this._posFilter);
    }
    players.sort((a, b) => {
      if (this._sort === "pos") {
        const pa = Number(a.position_code || (a.position && a.position.code) || 9);
        const pb = Number(b.position_code || (b.position && b.position.code) || 9);
        return pa !== pb ? pa - pb : (b.market_value || 0) - (a.market_value || 0);
      }
      if (this._sort === "trend") return (b.market_value_24h_change || 0) - (a.market_value_24h_change || 0);
      if (this._sort === "ap") return (b.average_points || 0) - (a.average_points || 0);
      if (this._sort === "profit") return (b.market_value_since_buy || 0) - (a.market_value_since_buy || 0);
      return (b.market_value || 0) - (a.market_value || 0);
    });
    const limit = Number(this._config.limit || 25);
    players = players.slice(0, limit);

    const body = `
      <div class="kb-tabs">
        <button class="kb-btn ${this._posFilter === "all" ? "active" : ""}" data-pos="all">Alle</button>
        <button class="kb-btn ${this._posFilter === "1" ? "active" : ""}" data-pos="1">TW</button>
        <button class="kb-btn ${this._posFilter === "2" ? "active" : ""}" data-pos="2">ABW</button>
        <button class="kb-btn ${this._posFilter === "3" ? "active" : ""}" data-pos="3">MF</button>
        <button class="kb-btn ${this._posFilter === "4" ? "active" : ""}" data-pos="4">ST</button>
        <span style="flex:1"></span>
        <button class="kb-btn ${this._sort === "pos" ? "active" : ""}" data-sort="pos">Position</button>
        <button class="kb-btn ${this._sort === "mv" ? "active" : ""}" data-sort="mv">Marktwert</button>
        <button class="kb-btn ${this._sort === "trend" ? "active" : ""}" data-sort="trend">24h Trend</button>
        <button class="kb-btn ${this._sort === "ap" ? "active" : ""}" data-sort="ap">Ø Pkt</button>
        <button class="kb-btn ${this._sort === "profit" ? "active" : ""}" data-sort="profit">G&V</button>
      </div>
      <div class="kb-list">
        ${
          players.length
            ? players
                .map((p) => {
                  const chg = Number(p.market_value_24h_change || 0);
                  return `
                    <div class="kb-row clickable" data-player-id="${escapeHtml(p.id)}">
                      <div class="kb-row-left">
                        ${playerImg(p) ? `<img class="kb-avatar" src="${escapeHtml(playerImg(p))}" loading="lazy"/>` : ""}
                        ${teamImg(p) ? `<img class="kb-crest" src="${escapeHtml(teamImg(p))}" loading="lazy"/>` : ""}
                        <div class="kb-row-main">
                          <div class="kb-row-name">${p.in_starting_eleven ? "⭐ " : ""}${escapeHtml(p.name)}</div>
                          <div class="kb-row-meta">
                            <span class="kb-pos-tag ${positionClass(p.position_code)}">${escapeHtml(p.position?.short)}</span>
                            <span class="kb-pill ${escapeHtml(p.status?.severity || "ok")}" style="padding:1px 6px;font-size:10px">${escapeHtml(p.status?.label_de)}</span>
                            ${startingProbBadge(p)}
                            <span>Ø ${p.average_points ?? 0} · ${p.total_points ?? 0} Pkt</span>
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
            : `<div class="kb-empty">Keine Spieler im Filter</div>`
        }
      </div>
    `;

    const pill = `<span class="kb-pill ${Number(summary.total_24h_change) >= 0 ? "ok" : "danger"}">${formatSignedCompactEur(summary.total_24h_change)}</span>`;
    this._renderShell(
      "Kader & Marktwert-Tracker",
      `${summary.count ?? 0} Spieler · Gesamt ${formatCompactEur(summary.total_market_value)}`,
      body,
      pill
    );
  }

  _afterRender() {
    this.shadowRoot.querySelectorAll("[data-pos]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._posFilter = btn.dataset.pos;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-sort]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._sort = btn.dataset.sort;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-player-id]").forEach((el) =>
      el.addEventListener("click", () => {
        openKickbaseModal(this.shadowRoot, this._hass, "player", {
          leagueId: this._activeLeagueId(),
          playerId: el.dataset.playerId,
        });
      })
    );
  }
}

/* -------------------------------------------------------------------------- */
/* 4. kickbase-market-card                                                    */
/* -------------------------------------------------------------------------- */
class KickbaseMarketCard extends KickbaseBaseCard {
  constructor() {
    super();
    this._tab = "market";
    this._sort = "expiry";
    this._timer = null;
  }
  getCardSize() { return 6; }

  connectedCallback() {
    if (!this._timer) {
      this._timer = setInterval(() => this._tickCountdowns(), 1000);
    }
  }

  disconnectedCallback() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  _tickCountdowns() {
    if (!this.shadowRoot) return;
    this.shadowRoot.querySelectorAll("[data-countdown-iso]").forEach((el) => {
      const iso = el.dataset.countdownIso;
      if (iso) {
        el.textContent = `⏱ ${formatIsoCountdown(iso, true)}`;
      }
    });
  }

  _render() {
    const mk = this._snapshot?.league_data?.market_transfers;
    if (!this._snapshot?.configured || !mk) {
      return this._renderShell(
        "Transfermarkt & Scouting",
        "Angebote & Watchlist",
        `<div class="kb-empty">Modul „Transfermarkt & Scout-Liste“ nicht aktiv.</div>`
      );
    }

    let items = [...(this._tab === "scouted" ? (mk.scouted || []) : (mk.market || []))];
    items.sort((a, b) => {
      if (this._sort === "expiry") {
        const ea = a.expiry_at ? Date.parse(a.expiry_at) : (a.expiry_seconds !== undefined && a.expiry_seconds !== null ? Date.now() + Number(a.expiry_seconds) * 1000 : Number.MAX_SAFE_INTEGER);
        const eb = b.expiry_at ? Date.parse(b.expiry_at) : (b.expiry_seconds !== undefined && b.expiry_seconds !== null ? Date.now() + Number(b.expiry_seconds) * 1000 : Number.MAX_SAFE_INTEGER);
        if (ea !== eb) return ea - eb;
        return (b.market_value || 0) - (a.market_value || 0);
      }
      if (this._sort === "pos") {
        const pa = Number(a.position_code || (a.position && a.position.code) || 9);
        const pb = Number(b.position_code || (b.position && b.position.code) || 9);
        return pa !== pb ? pa - pb : (b.price || b.market_value || 0) - (a.price || a.market_value || 0);
      }
      if (this._sort === "trend") return (b.market_value_24h_change || 0) - (a.market_value_24h_change || 0);
      return (b.price || b.market_value || 0) - (a.price || a.market_value || 0);
    });
    const limit = Number(this._config.limit || 15);
    const list = items.slice(0, limit);

    const body = `
      <div class="kb-tabs">
        <button class="kb-btn ${this._tab === "market" ? "active" : ""}" data-tab="market">Transfermarkt (${mk.market_count ?? 0})</button>
        <button class="kb-btn ${this._tab === "scouted" ? "active" : ""}" data-tab="scouted">Scout-Liste (${mk.scouted_count ?? 0})</button>
        <span style="flex:1"></span>
        <button class="kb-btn ${this._sort === "expiry" ? "active" : ""}" data-sort="expiry">Ablauf</button>
        <button class="kb-btn ${this._sort === "pos" ? "active" : ""}" data-sort="pos">Position</button>
        <button class="kb-btn ${this._sort === "price" ? "active" : ""}" data-sort="price">Preis</button>
        <button class="kb-btn ${this._sort === "trend" ? "active" : ""}" data-sort="trend">Trend</button>
      </div>
      <div class="kb-list">
        ${
          list.length
            ? list
                .map((p) => {
                  const trend = Number(p.market_value_24h_change || 0);
                  const countdownHtml = p.expiry_at
                    ? `<span data-countdown-iso="${escapeHtml(p.expiry_at)}">⏱ ${formatIsoCountdown(p.expiry_at, true)}</span>`
                    : (p.expiry_seconds !== undefined && p.expiry_seconds !== null
                        ? `<span>⏱ ${formatSecondsCountdown(p.expiry_seconds, true)}</span>`
                        : "");
                  return `
                    <div class="kb-row clickable ${p.is_scouted ? "highlight" : ""}" data-player-id="${escapeHtml(p.id)}">
                      <div class="kb-row-left">
                        ${playerImg(p) ? `<img class="kb-avatar" src="${escapeHtml(playerImg(p))}" loading="lazy"/>` : ""}
                        ${teamImg(p) ? `<img class="kb-crest" src="${escapeHtml(teamImg(p))}" loading="lazy"/>` : ""}
                        <div class="kb-row-main">
                          <div class="kb-row-name">${p.is_scouted ? "🔭 " : ""}${escapeHtml(p.full_name || p.name)}</div>
                          <div class="kb-row-meta">
                            <span class="kb-pos-tag ${positionClass(p.position_code)}">${escapeHtml(p.position?.short)}</span>
                            <span>${escapeHtml(p.owner_name || "Kickbase")}</span>
                            ${countdownHtml}
                            ${startingProbBadge(p)}
                            <span>Ø ${p.average_points ?? 0}</span>
                          </div>
                        </div>
                      </div>
                      <div class="kb-row-right">
                        <div class="kb-row-val">${formatCompactEur(p.price || p.market_value)}</div>
                        <div class="kb-row-sub ${trend >= 0 ? "kb-pos" : "kb-neg"}">MW: ${formatCompactEur(p.market_value)}</div>
                      </div>
                    </div>
                  `;
                })
                .join("")
            : `<div class="kb-empty">Aktuell keine Einträge vorhanden</div>`
        }
      </div>
    `;

    const pill = mk.expiring_soon_count > 0
      ? `<span class="kb-pill warn">⏱ ${mk.expiring_soon_count} läuft bald ab</span>`
      : `<span class="kb-pill">Update ${formatIsoCountdown(mk.market_value_update_at)}</span>`;

    this._renderShell("Transfermarkt & Scouting", `Marktwert-Update: ${formatDateTime(mk.market_value_update_at)}`, body, pill);
  }

  _afterRender() {
    this.shadowRoot.querySelectorAll("[data-tab]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._tab = btn.dataset.tab;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-sort]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._sort = btn.dataset.sort;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-player-id]").forEach((el) =>
      el.addEventListener("click", () => {
        openKickbaseModal(this.shadowRoot, this._hass, "player", {
          leagueId: this._activeLeagueId(),
          playerId: el.dataset.playerId,
        });
      })
    );
  }
}

/* -------------------------------------------------------------------------- */
/* 5. kickbase-standings-card                                                 */
/* -------------------------------------------------------------------------- */
class KickbaseStandingsCard extends KickbaseBaseCard {
  constructor() {
    super();
    this._tab = "standings";
  }
  getCardSize() { return 5; }

  _render() {
    const ov = this._snapshot?.league_data?.league_overview;
    if (!this._snapshot?.configured || !ov) {
      return this._renderShell("Liga-Tabelle & Battles", "Manager-Ranking", `<div class="kb-empty">Modul „Liga & Budget“ nicht aktiv.</div>`);
    }

    const standings = (ov.standings || []).slice(0, Number(this._config.limit || 18));
    const battles = ov.battles || [];

    const body = `
      <div class="kb-tabs">
        <button class="kb-btn ${this._tab === "standings" ? "active" : ""}" data-tab="standings">Tabelle (${standings.length})</button>
        <button class="kb-btn ${this._tab === "battles" ? "active" : ""}" data-tab="battles">Liga-Battles (${battles.length})</button>
      </div>
      ${
        this._tab === "battles"
          ? `<div class="kb-list">
              ${
                battles.length
                  ? battles
                      .map(
                        (b) => {
                          const bImg = localImg(b, "local_leader_avatar", "leader_avatar");
                          return `
                        <div class="kb-row clickable" data-manager-id="${escapeHtml(b.leader_id)}">
                          <div class="kb-row-left">
                            ${bImg ? `<img class="kb-avatar round" src="${escapeHtml(bImg)}" loading="lazy"/>` : ""}
                            <div class="kb-row-main">
                              <div class="kb-row-name">🏆 ${escapeHtml(b.name)}</div>
                              <div class="kb-row-meta">${escapeHtml(b.description || "")}</div>
                            </div>
                          </div>
                          <div class="kb-row-val">${escapeHtml(b.leader_name || "–")}</div>
                        </div>`;
                        }
                      )
                      .join("")
                  : `<div class="kb-empty">Keine Battles aktiv</div>`
              }
            </div>`
          : `<div class="kb-list">
              ${standings
                .map(
                  (m) => `
                  <div class="kb-row clickable ${m.is_me ? "highlight" : ""}" data-manager-id="${escapeHtml(m.id)}">
                    <div class="kb-row-left">
                      <span class="kb-pill" style="min-width:34px;justify-content:center">#${m.rank || "–"}</span>
                      ${avatarImg(m) ? `<img class="kb-avatar round" src="${escapeHtml(avatarImg(m))}" loading="lazy"/>` : ""}
                      <div class="kb-row-main">
                        <div class="kb-row-name">${escapeHtml(m.name)} ${m.is_admin ? "🛡" : ""}</div>
                        <div class="kb-row-meta">Teamwert ${formatCompactEur(m.team_value)} · ST #${m.matchday_rank || "–"} (${m.matchday_points ?? 0} Pkt)</div>
                      </div>
                    </div>
                    <div class="kb-row-right">
                      <div class="kb-row-val">${m.season_points ?? 0} Pkt</div>
                      <div class="kb-row-sub">Ø ${m.points_avg ?? 0}</div>
                    </div>
                  </div>
                `
                )
                .join("")}
            </div>`
      }
    `;

    this._renderShell("Liga-Tabelle & Battles", "Klick auf Manager zeigt Kader & Transfers", body);
  }

  _afterRender() {
    this.shadowRoot.querySelectorAll("[data-tab]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._tab = btn.dataset.tab;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-sort]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._sort = btn.dataset.sort;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-manager-id]").forEach((el) =>
      el.addEventListener("click", () => {
        if (!el.dataset.managerId) return;
        openKickbaseModal(this.shadowRoot, this._hass, "manager", {
          leagueId: this._activeLeagueId(),
          managerId: el.dataset.managerId,
        });
      })
    );
  }
}

/* -------------------------------------------------------------------------- */
/* 6. kickbase-live-card                                                      */
/* -------------------------------------------------------------------------- */
class KickbaseLiveCard extends KickbaseBaseCard {
  constructor() {
    super();
    this._tab = "matches";
  }
  getCardSize() { return 6; }

  _render() {
    const live = this._snapshot?.league_data?.live_matchday;
    if (!this._snapshot?.configured || !live) {
      return this._renderShell("Live-Spieltag & Bundesliga", "Matchcenter", `<div class="kb-empty">Modul „Live-Spieltag“ nicht aktiv.</div>`);
    }

    const matches = live.current_matches || [];
    const table = live.competition_table || [];
    const pill = live.is_live
      ? `<span class="kb-pill live"><span class="kb-dot"></span>LIVE · ${live.live_points ?? 0} Pkt</span>`
      : `<span class="kb-pill">Spieltag ${live.current_matchday ?? "–"}</span>`;

    const body = `
      <div class="kb-tabs">
        <button class="kb-btn ${this._tab === "matches" ? "active" : ""}" data-tab="matches">Spiele (${matches.length})</button>
        <button class="kb-btn ${this._tab === "table" ? "active" : ""}" data-tab="table">Bundesliga-Tabelle</button>
        <button class="kb-btn ${this._tab === "live_rank" ? "active" : ""}" data-tab="live_rank">Spieltag-Ranking</button>
      </div>
      ${
        this._tab === "matches"
          ? `<div class="kb-list">
              ${
                matches.length
                  ? matches
                      .map(
                        (m) => {
                          const t1Img = localImg(m, "local_team1_image", "team1_image");
                          const t2Img = localImg(m, "local_team2_image", "team2_image");
                          return `
                        <div class="kb-row clickable ${m.is_live ? "highlight" : ""}" data-match-id="${escapeHtml(m.id)}">
                          <div class="kb-row-left">
                            ${t1Img ? `<img class="kb-crest" src="${escapeHtml(t1Img)}" loading="lazy"/>` : ""}
                            <div class="kb-row-main">
                              <div class="kb-row-name">${escapeHtml(m.team1_name)} vs. ${escapeHtml(m.team2_name)}</div>
                              <div class="kb-row-meta">${m.is_live ? `🔴 LIVE ${escapeHtml(m.minute)}'` : formatDateTime(m.date)} · ${escapeHtml(m.status)}</div>
                            </div>
                            ${t2Img ? `<img class="kb-crest" src="${escapeHtml(t2Img)}" loading="lazy"/>` : ""}
                          </div>
                          <div class="kb-row-val" style="font-size:16px">${m.status === "scheduled" ? "– : –" : `${m.team1_goals ?? 0} : ${m.team2_goals ?? 0}`}</div>
                        </div>`;
                        }
                      )
                      .join("")
                  : `<div class="kb-empty">Keine Partien für diesen Spieltag</div>`
              }
            </div>`
          : this._tab === "table"
          ? `<div class="kb-list">
              ${table
                .slice(0, 18)
                .map(
                  (t) => {
                    const cImg = localImg(t, "local_image", "image");
                    return `
                  <div class="kb-row">
                    <div class="kb-row-left">
                      <span class="kb-pill" style="min-width:30px;justify-content:center">${t.rank}</span>
                      ${cImg ? `<img class="kb-crest" src="${escapeHtml(cImg)}" loading="lazy"/>` : ""}
                      <div class="kb-row-main">
                        <div class="kb-row-name">${escapeHtml(t.team_name)}</div>
                        <div class="kb-row-meta">${t.matches_played} Sp · Diff ${t.goal_diff >= 0 ? "+" : ""}${t.goal_diff} · KB ST: ${t.kickbase_matchday_points}</div>
                      </div>
                    </div>
                    <div class="kb-row-val">${t.points} Pkt</div>
                  </div>
                `;
                  }
                )
                .join("")}
            </div>`
          : `<div class="kb-list">
              ${(live.teamcenter_standings || [])
                .map(
                  (u) => {
                    const uImg = avatarImg(u);
                    return `
                  <div class="kb-row ${u.is_me ? "highlight" : ""}">
                    <div class="kb-row-left">
                      <span class="kb-pill">#${u.rank}</span>
                      ${uImg ? `<img class="kb-avatar round" src="${escapeHtml(uImg)}" loading="lazy"/>` : ""}
                      <div class="kb-row-name">${escapeHtml(u.name)}</div>
                    </div>
                    <div class="kb-row-val">${u.matchday_points} Pkt</div>
                  </div>
                `;
                  }
                )
                .join("") || `<div class="kb-empty">Keine Spieltags-Rangliste verfügbar</div>`}
            </div>`
      }
    `;

    this._renderShell(
      "Spieltag & Matchcenter",
      `Mein Live-Stand: ${live.live_points ?? 0} Pkt${live.live_rank ? ` (Platz #${live.live_rank})` : ""}`,
      body,
      pill
    );
  }

  _afterRender() {
    this.shadowRoot.querySelectorAll("[data-tab]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._tab = btn.dataset.tab;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-sort]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._sort = btn.dataset.sort;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-match-id]").forEach((el) =>
      el.addEventListener("click", () => {
        openKickbaseModal(this.shadowRoot, this._hass, "match", {
          matchId: el.dataset.matchId,
          leagueId: this._activeLeagueId(),
        });
      })
    );
  }
}

/* -------------------------------------------------------------------------- */
/* 7. kickbase-feed-news-card                                                 */
/* -------------------------------------------------------------------------- */
class KickbaseFeedNewsCard extends KickbaseBaseCard {
  constructor() {
    super();
    this._tab = "feed";
  }
  getCardSize() { return 5; }

  _render() {
    const feedMod = this._snapshot?.league_data?.feed_achievements;
    const newsMod = this._snapshot?.news_predictions;
    if (!this._snapshot?.configured || (!feedMod && !newsMod)) {
      return this._renderShell("Feed, News & Prognosen", "Aktivitäten", `<div class="kb-empty">Module „Feed/Erfolge“ und „News“ nicht aktiv.</div>`);
    }
    if (!feedMod && newsMod && (this._tab === "feed" || this._tab === "ach")) {
      this._tab = "news";
    } else if (feedMod && !newsMod && (this._tab === "news" || this._tab === "preds")) {
      this._tab = "feed";
    }

    const activities = (feedMod?.activities || []).slice(0, Number(this._config.limit || 15));
    const achievements = feedMod?.achievements || [];
    const compId = (this._snapshot?.league_data?.league_overview?.league?.competition_id) || "1";
    const newsList = ((newsMod?.news_by_competition || {})[compId] || []).slice(0, Number(this._config.limit || 15));
    const predictions = (newsMod?.predictions_by_competition || {})[compId] || [];

    const body = `
      <div class="kb-tabs">
        ${feedMod ? `<button class="kb-btn ${this._tab === "feed" ? "active" : ""}" data-tab="feed">Liga-Feed (${activities.length})</button>` : ""}
        ${newsMod ? `<button class="kb-btn ${this._tab === "news" ? "active" : ""}" data-tab="news">News (${newsList.length})</button>` : ""}
        ${newsMod ? `<button class="kb-btn ${this._tab === "preds" ? "active" : ""}" data-tab="preds">Prognosen (${predictions.length})</button>` : ""}
        ${feedMod ? `<button class="kb-btn ${this._tab === "ach" ? "active" : ""}" data-tab="ach">Erfolge (${feedMod.earned_achievements_count ?? 0})</button>` : ""}
      </div>
      ${
        this._tab === "news"
          ? `<div class="kb-list">
              ${newsList
                .map(
                  (n) => {
                    const nImg = localImg(n, "local_image", "image");
                    return `
                  <div class="kb-row clickable" data-news-id="${escapeHtml(n.id)}">
                    <div class="kb-row-left">
                      ${nImg ? `<img class="kb-avatar" src="${escapeHtml(nImg)}" loading="lazy"/>` : ""}
                      <div class="kb-row-main">
                        <div class="kb-row-name">${escapeHtml(n.title)}</div>
                        <div class="kb-row-meta"><span class="kb-pill accent" style="padding:1px 6px;font-size:10px">${escapeHtml(n.label || "News")}</span><span>${formatDateTime(n.date)}</span></div>
                      </div>
                    </div>
                  </div>
                `;
                  }
                )
                .join("") || `<div class="kb-empty">Keine News verfügbar</div>`}
            </div>`
          : this._tab === "preds"
          ? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px">
              ${predictions
                .map(
                  (tm) => {
                    const tmCrest = localImg(tm, "local_team_image", "team_image");
                    const predImg = localImg(tm, "local_prediction_image", "prediction_image");
                    return `
                  <div class="kb-kpi" style="text-align:center">
                    ${tmCrest ? `<img class="kb-crest" style="width:32px;height:32px" src="${escapeHtml(tmCrest)}" loading="lazy"/>` : ""}
                    <div class="kb-row-name" style="margin-top:6px">${escapeHtml(tm.team_name)}</div>
                    ${predImg ? `<img src="${escapeHtml(predImg)}" style="width:100%;border-radius:8px;margin-top:6px" loading="lazy"/>` : ""}
                  </div>
                `;
                  }
                )
                .join("") || `<div class="kb-empty">Keine Aufstellungsprognosen verfügbar</div>`}
            </div>`
          : this._tab === "ach"
          ? `<div class="kb-list">
              ${achievements
                .map(
                  (a) => `
                  <div class="kb-row ${a.is_earned ? "highlight" : ""}">
                    <div class="kb-row-left">
                      <span>${a.is_earned ? "🏅" : "🔒"}</span>
                      <div class="kb-row-name">${escapeHtml(a.name)}</div>
                    </div>
                    <div class="kb-row-val">${a.count ?? 0}×</div>
                  </div>
                `
                )
                .join("") || `<div class="kb-empty">Keine Erfolge geladen</div>`}
            </div>`
          : `<div class="kb-list">
              ${activities
                .map(
                  (a) => `
                  <div class="kb-row">
                    <div class="kb-row-left">
                      <span class="kb-pill">${escapeHtml(a.type?.label_de || "Event")}</span>
                      <div class="kb-row-main">
                        <div class="kb-row-name">${escapeHtml(JSON.stringify(a.data || {}).slice(0, 72))}</div>
                        <div class="kb-row-meta">${formatDateTime(a.date)} · 💬 ${a.comment_count ?? 0}</div>
                      </div>
                    </div>
                  </div>
                `
                )
                .join("") || `<div class="kb-empty">Keine Liga-Aktivitäten</div>`}
            </div>`
      }
    `;

    this._renderShell("Feed, News & Prognosen", "Liga-Events, Artikel & Ligainsider", body);
  }

  _afterRender() {
    this.shadowRoot.querySelectorAll("[data-tab]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._tab = btn.dataset.tab;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-sort]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._sort = btn.dataset.sort;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-news-id]").forEach((el) =>
      el.addEventListener("click", () => {
        openKickbaseModal(this.shadowRoot, this._hass, "news", {
          itemId: el.dataset.newsId,
        });
      })
    );
  }
}

/* -------------------------------------------------------------------------- */
/* 8. kickbase-challenges-card                                                */
/* -------------------------------------------------------------------------- */
class KickbaseChallengesCard extends KickbaseBaseCard {
  getCardSize() { return 5; }

  _render() {
    const ch = this._snapshot?.challenges;
    if (!this._snapshot?.configured || !ch) {
      return this._renderShell("Challenges & Lobby", "Kickbase Challenges", `<div class="kb-empty">Modul „Challenges & Lobby“ nicht aktiv.</div>`);
    }

    const prof = ch.profile || {};
    const list = ch.active_challenges || [];
    const pill = `<span class="kb-pill accent">${escapeHtml(prof.division_name || "Lobby")}</span>`;

    const body = `
      <div class="kb-kpi-grid" style="margin-bottom:12px">
        <div class="kb-kpi"><div class="kb-kpi-label">Division</div><div class="kb-kpi-val" style="font-size:15px">${escapeHtml(prof.division_name || "–")}</div></div>
        <div class="kb-kpi"><div class="kb-kpi-label">Skill Points</div><div class="kb-kpi-val">${prof.skill_points ?? 0}</div><div class="kb-kpi-sub">Verfügbar: ${prof.available_skill_points ?? 0}</div></div>
        <div class="kb-kpi"><div class="kb-kpi-label">Ø Punkte</div><div class="kb-kpi-val">${prof.average_points ?? 0}</div></div>
      </div>
      <div class="kb-list">
        ${
          list.length
            ? list
                .map((c) => {
                  const det = (ch.challenge_details || {})[c.id];
                  const cImg = localImg(c, "local_image", "image");
                  return `
                    <div class="kb-row ${c.is_live ? "highlight" : ""}">
                      <div class="kb-row-left">
                        ${cImg ? `<img class="kb-avatar" src="${escapeHtml(cImg)}" loading="lazy"/>` : ""}
                        <div class="kb-row-main">
                          <div class="kb-row-name">${escapeHtml(c.name)}</div>
                          <div class="kb-row-meta">
                            ${c.is_live ? "🔴 LIVE · " : ""}${c.lineup_player_count ?? 0} Spieler · ${c.user_count ?? 0} Teilnehmer
                            ${det?.formation ? ` · ${escapeHtml(det.formation)}` : ""}
                          </div>
                        </div>
                      </div>
                      <div class="kb-row-right">
                        <div class="kb-row-val">${det ? `${det.live_points ?? 0} Pkt` : formatCompactEur(c.budget)}</div>
                        <div class="kb-row-sub">${formatDateTime(c.start_date)}</div>
                      </div>
                    </div>
                  `;
                })
                .join("")
            : `<div class="kb-empty">Keine aktiven Challenges gefunden</div>`
        }
      </div>
    `;

    this._renderShell("Challenges & Division Lobby", prof.season_name || "Kickbase Challenges", body, pill);
  }
}

/* -------------------------------------------------------------------------- */
/* 9. kickbase-manager-card (Mitspieler Kader & Aufstellung)                  */
/* -------------------------------------------------------------------------- */
class KickbaseManagerCard extends KickbaseBaseCard {
  constructor() {
    super();
    this._selectedManagerId = null;
    this._tab = "lineup";
    this._posFilter = "all";
    this._sort = "pos";
    this._detail = null;
    this._detailManagerId = null;
    this._detailLeagueId = null;
    this._detailLoading = false;
  }

  getCardSize() { return 7; }

  setConfig(config) {
    super.setConfig(config);
    if (config?.manager_id) {
      this._selectedManagerId = String(config.manager_id);
      this._detail = null;
      this._detailManagerId = null;
    }
  }

  async _ensureDetail(managerId) {
    const lid = this._activeLeagueId();
    if (!this._hass || !lid || !managerId) return;
    if (this._detailLoading) return;
    if (this._detail && this._detailManagerId === String(managerId) && this._detailLeagueId === String(lid)) {
      return;
    }
    this._detailLoading = true;
    try {
      const res = await kickbaseStore.getManagerDetail(this._hass, {
        leagueId: lid,
        managerId: String(managerId),
      });
      this._detail = res;
      this._detailManagerId = String(managerId);
      this._detailLeagueId = String(lid);
    } catch (_err) {
      this._detail = null;
    } finally {
      this._detailLoading = false;
      this._render();
    }
  }

  _render() {
    const ov = this._snapshot?.league_data?.league_overview;
    if (!this._snapshot?.configured || !ov) {
      return this._renderShell(
        "Mitspieler Kader & Aufstellung",
        "Manager-Inspektor",
        `<div class="kb-empty">Modul „Liga & Budget“ nicht aktiv.</div>`
      );
    }

    const standings = ov.standings || [];
    if (!standings.length) {
      return this._renderShell("Mitspieler Kader & Aufstellung", "Manager-Inspektor", `<div class="kb-empty">Keine Manager in der Liga gefunden.</div>`);
    }

    const chosenId = String(this._selectedManagerId || this._config.manager_id || standings[0].id);
    const mgrSummary = standings.find((m) => String(m.id) === chosenId) || standings[0];
    const activeId = String(mgrSummary.id);

    if (!this._detail || this._detailManagerId !== activeId || this._detailLeagueId !== String(this._activeLeagueId())) {
      this._ensureDetail(activeId);
    }

    const dash = this._detail?.dashboard || mgrSummary;
    const squad = [...(this._detail?.squad || [])];
    const lineupIds = new Set((this._detail?.lineup_ids || mgrSummary.lineup_ids || []).map((x) => String(x)));
    const lineupPlayers = squad.filter((p) => lineupIds.has(String(p.id)));
    const transfers = this._detail?.transfers || [];

    const posCounts = { all: squad.length, 1: 0, 2: 0, 3: 0, 4: 0 };
    for (const p of squad) {
      const code = Number(p.position_code || p.position?.code || 0);
      if (posCounts[code] !== undefined) posCounts[code] += 1;
    }

    let filteredSquad = squad.filter((p) => {
      if (this._posFilter === "all") return true;
      return String(p.position_code || p.position?.code || "") === String(this._posFilter);
    });
    filteredSquad.sort((a, b) => {
      if (this._sort === "pos") {
        const pa = Number(a.position_code || a.position?.code || 9);
        const pb = Number(b.position_code || b.position?.code || 9);
        return pa !== pb ? pa - pb : (b.market_value || 0) - (a.market_value || 0);
      }
      if (this._sort === "ap") return (b.average_points || 0) - (a.average_points || 0);
      return (b.market_value || 0) - (a.market_value || 0);
    });

    const mgrOpts = standings
      .map(
        (m) =>
          `<option value="${escapeHtml(m.id)}" ${String(m.id) === activeId ? "selected" : ""}>#${m.rank ?? "?"} ${escapeHtml(m.name)}</option>`
      )
      .join("");

    const body = `
      <div class="kb-tabs" style="align-items:center;margin-bottom:10px">
        <select id="kb-mgr-select" class="kb-select" style="max-width:230px">${mgrOpts}</select>
        <span style="flex:1"></span>
        <button class="kb-btn ${this._tab === "lineup" ? "active" : ""}" data-tab="lineup">Aufstellung (${lineupPlayers.length})</button>
        <button class="kb-btn ${this._tab === "squad" ? "active" : ""}" data-tab="squad">Kader (${squad.length})</button>
        <button class="kb-btn ${this._tab === "transfers" ? "active" : ""}" data-tab="transfers">Transfers (${transfers.length})</button>
      </div>

      <div class="kb-kpi-grid" style="margin-bottom:12px">
        <div class="kb-kpi">
          <div class="kb-kpi-label">Rang / Punkte</div>
          <div class="kb-kpi-val">#${dash.rank ?? "–"} · ${dash.total_points ?? 0}</div>
          <div class="kb-kpi-sub">Ø ${dash.average_points ?? 0} Pkt</div>
        </div>
        <div class="kb-kpi">
          <div class="kb-kpi-label">Teamwert</div>
          <div class="kb-kpi-val">${formatCompactEur(dash.team_value ?? mgrSummary.team_value)}</div>
          <div class="kb-kpi-sub">${squad.length} Spieler</div>
        </div>
        <div class="kb-kpi">
          <div class="kb-kpi-label">Spieltag-Siege</div>
          <div class="kb-kpi-val">${dash.matchday_wins ?? 0}</div>
          <div class="kb-kpi-sub">${this._detail?.from_local_db ? "💾 Lokale DB" : "Live"}</div>
        </div>
      </div>

      ${
        this._detailLoading && !this._detail
          ? `<div class="kb-empty">Lade Mitspieler-Daten aus lokaler DB…</div>`
          : this._tab === "lineup"
          ? lineupPlayers.length
            ? renderPitchHtml(lineupPlayers)
            : `<div class="kb-empty">Keine Aufstellungsdaten für ${escapeHtml(mgrSummary.name)} vorhanden.</div>`
          : this._tab === "squad"
          ? `
            <div class="kb-tabs" style="margin-bottom:8px">
              <button class="kb-btn ${this._posFilter === "all" ? "active" : ""}" data-pos="all">Alle (${posCounts.all})</button>
              <button class="kb-btn ${this._posFilter === "1" ? "active" : ""}" data-pos="1">TW (${posCounts[1]})</button>
              <button class="kb-btn ${this._posFilter === "2" ? "active" : ""}" data-pos="2">ABW (${posCounts[2]})</button>
              <button class="kb-btn ${this._posFilter === "3" ? "active" : ""}" data-pos="3">MF (${posCounts[3]})</button>
              <button class="kb-btn ${this._posFilter === "4" ? "active" : ""}" data-pos="4">ST (${posCounts[4]})</button>
              <span style="flex:1"></span>
              <button class="kb-btn ${this._sort === "pos" ? "active" : ""}" data-sort="pos">Position</button>
              <button class="kb-btn ${this._sort === "mv" ? "active" : ""}" data-sort="mv">Marktwert</button>
              <button class="kb-btn ${this._sort === "ap" ? "active" : ""}" data-sort="ap">Ø Pkt</button>
            </div>
            <div class="kb-list">
              ${
                filteredSquad.length
                  ? filteredSquad
                      .map((p) => {
                        const inStart = lineupIds.has(String(p.id));
                        return `
                          <div class="kb-row clickable ${inStart ? "highlight" : ""}" data-player-id="${escapeHtml(p.id)}">
                            <div class="kb-row-left">
                              ${playerImg(p) ? `<img class="kb-avatar" src="${escapeHtml(playerImg(p))}" loading="lazy"/>` : ""}
                              ${teamImg(p) ? `<img class="kb-crest" src="${escapeHtml(teamImg(p))}" loading="lazy"/>` : ""}
                              <div class="kb-row-main">
                                <div class="kb-row-name">${inStart ? "⭐ " : ""}${escapeHtml(p.full_name || p.name)}</div>
                                <div class="kb-row-meta">
                                  <span class="kb-pos-tag ${positionClass(p.position_code)}">${escapeHtml(p.position?.short)}</span>
                                  <span class="kb-pill ${escapeHtml(p.status?.severity || "ok")}" style="padding:1px 6px;font-size:10px">${escapeHtml(p.status?.label_de || "Fit")}</span>
                                  ${startingProbBadge(p)}
                                  <span>Ø ${p.average_points ?? 0}</span>
                                </div>
                              </div>
                            </div>
                            <div class="kb-row-right">
                              <div class="kb-row-val">${formatCompactEur(p.market_value)}</div>
                              <div class="kb-row-sub">${p.total_points ?? 0} Pkt</div>
                            </div>
                          </div>
                        `;
                      })
                      .join("")
                  : `<div class="kb-empty">Keine Spieler im Filter</div>`
              }
            </div>`
          : `<div class="kb-list">
              ${
                transfers.length
                  ? transfers
                      .slice(0, Number(this._config.limit || 20))
                      .map(
                        (t) => `
                        <div class="kb-row clickable" data-player-id="${escapeHtml(t.player_id)}">
                          <div class="kb-row-left">
                            <span class="kb-pill ${t.type === "buy" ? "warn" : "ok"}">${t.type === "buy" ? "Kauf" : "Verkauf"}</span>
                            <div class="kb-row-main">
                              <div class="kb-row-name">${escapeHtml(t.player_name || t.player_id)}</div>
                              <div class="kb-row-meta">${formatDateTime(t.date)}</div>
                            </div>
                          </div>
                          <div class="kb-row-right">
                            <div class="kb-row-val">${formatCompactEur(t.price)}</div>
                          </div>
                        </div>
                      `
                      )
                      .join("")
                  : `<div class="kb-empty">Keine Transfers gespeichert</div>`
              }
            </div>`
      }
    `;

    const mgrAvatar = avatarImg(mgrSummary);
    const pill = mgrAvatar
      ? `<img class="kb-avatar" style="width:26px;height:26px" src="${escapeHtml(mgrAvatar)}"/>`
      : `<span class="kb-pill accent">#${dash.rank ?? "–"}</span>`;

    this._renderShell(
      `${mgrSummary.name} · Kader & Aufstellung`,
      `Mitspieler-Inspektor`,
      body,
      pill
    );
  }

  _afterRender() {
    this.shadowRoot.getElementById("kb-mgr-select")?.addEventListener("change", (e) => {
      this._selectedManagerId = e.target.value;
      this._detail = null;
      this._detailManagerId = null;
      this._render();
    });
    this.shadowRoot.querySelectorAll("[data-tab]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._tab = btn.dataset.tab;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-pos]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._posFilter = btn.dataset.pos;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-sort]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._sort = btn.dataset.sort;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-player-id]").forEach((el) =>
      el.addEventListener("click", () => {
        openKickbaseModal(this.shadowRoot, this._hass, "player", {
          leagueId: this._activeLeagueId(),
          playerId: el.dataset.playerId,
        });
      })
    );
  }
}

const CARD_DEFS = [
  ["kickbase-overview-card", KickbaseOverviewCard, "Kickbase: Liga & Budget", "Modulare KPI-Karte für Budget, Teamwert, Rang & Deadline."],
  ["kickbase-lineup-card", KickbaseLineupCard, "Kickbase: Spielfeld-Aufstellung", "Interaktives Spielfeld mit Formation, Status-Badges & Spielerdetails."],
  ["kickbase-squad-card", KickbaseSquadCard, "Kickbase: Kader & Marktwerte", "Sortier- und filterbare Kaderliste mit 24h-Marktwert-Trend & Charts."],
  ["kickbase-market-card", KickbaseMarketCard, "Kickbase: Transfermarkt & Scouting", "Aktuelle Markt-Spieler, Ablauf-Timer & Scout-Watchlist."],
  ["kickbase-standings-card", KickbaseStandingsCard, "Kickbase: Tabelle & Battles", "Liga-Rangliste, Battles & Klick-Inspektion aller Rivalen-Kader."],
  ["kickbase-live-card", KickbaseLiveCard, "Kickbase: Live-Spieltag & Bundesliga", "Live-Spiele, Events, Spieltag-Ranking & Bundesliga-Tabelle."],
  ["kickbase-feed-news-card", KickbaseFeedNewsCard, "Kickbase: Feed, Erfolge & News", "Liga-Aktivitäten, Erfolge, Artikel & voraussichtliche Aufstellungen."],
  ["kickbase-challenges-card", KickbaseChallengesCard, "Kickbase: Challenges & Lobby", "Division, Skill Points & aktive Matchday-Challenges."],
  ["kickbase-manager-card", KickbaseManagerCard, "Kickbase: Mitspieler Kader & Aufstellung", "Wählbarer Mitspieler-Kader, Aufstellung auf dem Spielfeld & Transfers."],
];

window.customCards = window.customCards || [];
for (const [tag, cls, name, description] of CARD_DEFS) {
  if (!customElements.get(tag)) {
    customElements.define(tag, cls);
  }
  if (!window.customCards.some((c) => c.type === tag)) {
    window.customCards.push({ type: tag, name, description, preview: true });
  }
}
