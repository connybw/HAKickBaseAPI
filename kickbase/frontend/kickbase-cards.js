/**
 * Modular Lovelace Cards Bundle for Kickbase Home Assistant Integration.
 * Exposes 8 standalone, interactive, visual-editor-enabled cards + window.customCards registration.
 */

import {
  KICKBASE_CSS,
  escapeHtml,
  formatCompactEur,
  formatDateTime,
  formatIsoCountdown,
  formatSecondsCountdown,
  formatSignedCompactEur,
  kickbaseStore,
  openKickbaseModal,
  positionClass,
  renderPitchHtml,
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
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._leagues.length && hass) {
      kickbaseStore
        .getSnapshot(hass)
        .then((snap) => {
          this._leagues = snap?.leagues || [];
          this._render();
        })
        .catch(() => {});
    }
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    this._render();
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
    this.shadowRoot.querySelector("[data-refresh]")?.addEventListener("click", async () => {
      if (!this._hass) return;
      this._loading = true;
      this._render();
      try {
        this._snapshot = await kickbaseStore.refresh(this._hass, {
          leagueId: this._activeLeagueId(),
        });
        this._lastFetch = Date.now();
      } catch (err) {
        this._error = err?.message || String(err);
      } finally {
        this._loading = false;
        this._render();
      }
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
            <button class="kb-btn" data-refresh title="Aktualisieren">${this._loading ? "⏳" : "↻"}</button>
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
                        ${p.image ? `<img class="kb-avatar" src="${escapeHtml(p.image)}" loading="lazy"/>` : ""}
                        ${p.team_image ? `<img class="kb-crest" src="${escapeHtml(p.team_image)}" loading="lazy"/>` : ""}
                        <div class="kb-row-main">
                          <div class="kb-row-name">${p.in_starting_eleven ? "⭐ " : ""}${escapeHtml(p.name)}</div>
                          <div class="kb-row-meta">
                            <span class="kb-pos-tag ${positionClass(p.position_code)}">${escapeHtml(p.position?.short)}</span>
                            <span class="kb-pill ${escapeHtml(p.status?.severity || "ok")}" style="padding:1px 6px;font-size:10px">${escapeHtml(p.status?.label_de)}</span>
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
  }
  getCardSize() { return 6; }

  _render() {
    const mk = this._snapshot?.league_data?.market_transfers;
    if (!this._snapshot?.configured || !mk) {
      return this._renderShell(
        "Transfermarkt & Scouting",
        "Angebote & Watchlist",
        `<div class="kb-empty">Modul „Transfermarkt & Scout-Liste“ nicht aktiv.</div>`
      );
    }

    const items = this._tab === "scouted" ? (mk.scouted || []) : (mk.market || []);
    const limit = Number(this._config.limit || 15);
    const list = items.slice(0, limit);

    const body = `
      <div class="kb-tabs">
        <button class="kb-btn ${this._tab === "market" ? "active" : ""}" data-tab="market">Transfermarkt (${mk.market_count ?? 0})</button>
        <button class="kb-btn ${this._tab === "scouted" ? "active" : ""}" data-tab="scouted">Scout-Liste (${mk.scouted_count ?? 0})</button>
      </div>
      <div class="kb-list">
        ${
          list.length
            ? list
                .map((p) => {
                  const trend = Number(p.market_value_24h_change || 0);
                  return `
                    <div class="kb-row clickable ${p.is_scouted ? "highlight" : ""}" data-player-id="${escapeHtml(p.id)}">
                      <div class="kb-row-left">
                        ${p.image ? `<img class="kb-avatar" src="${escapeHtml(p.image)}" loading="lazy"/>` : ""}
                        <div class="kb-row-main">
                          <div class="kb-row-name">${p.is_scouted ? "🔭 " : ""}${escapeHtml(p.full_name || p.name)}</div>
                          <div class="kb-row-meta">
                            <span class="kb-pos-tag ${positionClass(p.position_code)}">${escapeHtml(p.position?.short)}</span>
                            <span>${escapeHtml(p.owner_name || "Kickbase")}</span>
                            ${p.expiry_seconds !== undefined && p.expiry_seconds !== null ? `<span>⏱ ${formatSecondsCountdown(p.expiry_seconds)}</span>` : ""}
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
                        (b) => `
                        <div class="kb-row clickable" data-manager-id="${escapeHtml(b.leader_id)}">
                          <div class="kb-row-left">
                            ${b.leader_avatar ? `<img class="kb-avatar round" src="${escapeHtml(b.leader_avatar)}"/>` : ""}
                            <div class="kb-row-main">
                              <div class="kb-row-name">🏆 ${escapeHtml(b.name)}</div>
                              <div class="kb-row-meta">${escapeHtml(b.description || "")}</div>
                            </div>
                          </div>
                          <div class="kb-row-val">${escapeHtml(b.leader_name || "–")}</div>
                        </div>`
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
                      ${m.avatar ? `<img class="kb-avatar round" src="${escapeHtml(m.avatar)}" loading="lazy"/>` : ""}
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
                        (m) => `
                        <div class="kb-row clickable ${m.is_live ? "highlight" : ""}" data-match-id="${escapeHtml(m.id)}">
                          <div class="kb-row-left">
                            ${m.team1_image ? `<img class="kb-crest" src="${escapeHtml(m.team1_image)}"/>` : ""}
                            <div class="kb-row-main">
                              <div class="kb-row-name">${escapeHtml(m.team1_name)} vs. ${escapeHtml(m.team2_name)}</div>
                              <div class="kb-row-meta">${m.is_live ? `🔴 LIVE ${escapeHtml(m.minute)}'` : formatDateTime(m.date)} · ${escapeHtml(m.status)}</div>
                            </div>
                            ${m.team2_image ? `<img class="kb-crest" src="${escapeHtml(m.team2_image)}"/>` : ""}
                          </div>
                          <div class="kb-row-val" style="font-size:16px">${m.status === "scheduled" ? "– : –" : `${m.team1_goals ?? 0} : ${m.team2_goals ?? 0}`}</div>
                        </div>`
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
                  (t) => `
                  <div class="kb-row">
                    <div class="kb-row-left">
                      <span class="kb-pill" style="min-width:30px;justify-content:center">${t.rank}</span>
                      ${t.image ? `<img class="kb-crest" src="${escapeHtml(t.image)}"/>` : ""}
                      <div class="kb-row-main">
                        <div class="kb-row-name">${escapeHtml(t.team_name)}</div>
                        <div class="kb-row-meta">${t.matches_played} Sp · Diff ${t.goal_diff >= 0 ? "+" : ""}${t.goal_diff} · KB ST: ${t.kickbase_matchday_points}</div>
                      </div>
                    </div>
                    <div class="kb-row-val">${t.points} Pkt</div>
                  </div>
                `
                )
                .join("")}
            </div>`
          : `<div class="kb-list">
              ${(live.teamcenter_standings || [])
                .map(
                  (u) => `
                  <div class="kb-row ${u.is_me ? "highlight" : ""}">
                    <div class="kb-row-left">
                      <span class="kb-pill">#${u.rank}</span>
                      ${u.avatar ? `<img class="kb-avatar round" src="${escapeHtml(u.avatar)}"/>` : ""}
                      <div class="kb-row-name">${escapeHtml(u.name)}</div>
                    </div>
                    <div class="kb-row-val">${u.matchday_points} Pkt</div>
                  </div>
                `
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
    this.shadowRoot.querySelectorAll("[data-match-id]").forEach((el) =>
      el.addEventListener("click", () => {
        openKickbaseModal(this.shadowRoot, this._hass, "match", {
          matchId: el.dataset.matchId,
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
                  (n) => `
                  <div class="kb-row clickable" data-news-id="${escapeHtml(n.id)}">
                    <div class="kb-row-left">
                      ${n.image ? `<img class="kb-avatar" src="${escapeHtml(n.image)}" loading="lazy"/>` : ""}
                      <div class="kb-row-main">
                        <div class="kb-row-name">${escapeHtml(n.title)}</div>
                        <div class="kb-row-meta"><span class="kb-pill accent" style="padding:1px 6px;font-size:10px">${escapeHtml(n.label || "News")}</span><span>${formatDateTime(n.date)}</span></div>
                      </div>
                    </div>
                  </div>
                `
                )
                .join("") || `<div class="kb-empty">Keine News verfügbar</div>`}
            </div>`
          : this._tab === "preds"
          ? `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px">
              ${predictions
                .map(
                  (tm) => `
                  <div class="kb-kpi" style="text-align:center">
                    ${tm.team_image ? `<img class="kb-crest" style="width:32px;height:32px" src="${escapeHtml(tm.team_image)}"/>` : ""}
                    <div class="kb-row-name" style="margin-top:6px">${escapeHtml(tm.team_name)}</div>
                    ${tm.prediction_image ? `<img src="${escapeHtml(tm.prediction_image)}" style="width:100%;border-radius:8px;margin-top:6px" loading="lazy"/>` : ""}
                  </div>
                `
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
                  return `
                    <div class="kb-row ${c.is_live ? "highlight" : ""}">
                      <div class="kb-row-left">
                        ${c.image ? `<img class="kb-avatar" src="${escapeHtml(c.image)}" loading="lazy"/>` : ""}
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

const CARD_DEFS = [
  ["kickbase-overview-card", KickbaseOverviewCard, "Kickbase: Liga & Budget", "Modulare KPI-Karte für Budget, Teamwert, Rang & Deadline."],
  ["kickbase-lineup-card", KickbaseLineupCard, "Kickbase: Spielfeld-Aufstellung", "Interaktives Spielfeld mit Formation, Status-Badges & Spielerdetails."],
  ["kickbase-squad-card", KickbaseSquadCard, "Kickbase: Kader & Marktwerte", "Sortier- und filterbare Kaderliste mit 24h-Marktwert-Trend & Charts."],
  ["kickbase-market-card", KickbaseMarketCard, "Kickbase: Transfermarkt & Scouting", "Aktuelle Markt-Spieler, Ablauf-Timer & Scout-Watchlist."],
  ["kickbase-standings-card", KickbaseStandingsCard, "Kickbase: Tabelle & Battles", "Liga-Rangliste, Battles & Klick-Inspektion aller Rivalen-Kader."],
  ["kickbase-live-card", KickbaseLiveCard, "Kickbase: Live-Spieltag & Bundesliga", "Live-Spiele, Events, Spieltag-Ranking & Bundesliga-Tabelle."],
  ["kickbase-feed-news-card", KickbaseFeedNewsCard, "Kickbase: Feed, Erfolge & News", "Liga-Aktivitäten, Erfolge, Artikel & voraussichtliche Aufstellungen."],
  ["kickbase-challenges-card", KickbaseChallengesCard, "Kickbase: Challenges & Lobby", "Division, Skill Points & aktive Matchday-Challenges."],
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
