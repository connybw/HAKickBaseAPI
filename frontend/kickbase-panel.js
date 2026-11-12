/**
 * Kickbase Sidebar Panel for Home Assistant.
 * Renders a modular multi-league Command Center reusing the standalone card components.
 */

import {
  KICKBASE_CSS,
  escapeHtml,
  formatCompactEur,
  kickbaseStore,
  openKickbaseModal,
  positionClass,
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
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
      this._render();
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

    const tabs = [
      { id: "dashboard", label: "Modulares Dashboard", show: true },
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
          width: min(360px, 90vw);
          max-height: 360px;
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
            ${user.avatar ? `<img class="kb-avatar round" src="${escapeHtml(user.avatar)}"/>` : ""}
            <div>
              <div class="kb-title" style="font-size:18px">Kickbase Command Center</div>
              <div class="kb-subtitle">
                ${escapeHtml(user.name || "Manager")} ${user.has_pro ? "· ⭐ Pro" : ""} · Rein lesend
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
              <input class="kb-input" id="kb-player-search" type="search" placeholder="Spieler suchen (z. B. Kane)..." value="${escapeHtml(this._searchQuery)}"/>
              <div id="kb-search-dropdown-slot"></div>
            </div>
            <button class="kb-btn ${this._customizeOpen ? "active" : ""}" id="kb-customize-btn">⚙ Module</button>
            <button class="kb-btn" id="kb-panel-refresh">${this._loading ? "⏳ Lädt..." : "↻ Aktualisieren"}</button>
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

        <div class="kb-grid" id="kb-cards-grid"></div>
      </div>
    `;

    // Mount modular cards into grid
    const grid = this.shadowRoot.getElementById("kb-cards-grid");
    if (this._error) {
      grid.innerHTML = `<div class="kb-empty">Fehler beim Laden: ${escapeHtml(this._error)}</div>`;
    } else if (!snap) {
      grid.innerHTML = `<div class="kb-empty">Lade Kickbase-Module...</div>`;
    } else if (!snap.configured) {
      grid.innerHTML = `<div class="kb-empty">Bitte richte zuerst die Kickbase-Integration unter Einstellungen → Geräte & Dienste ein.</div>`;
    } else {
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

  _renderSearchDropdown(activeLeague) {
    const slot = this.shadowRoot.getElementById("kb-search-dropdown-slot");
    if (!slot) return;
    if (!this._searchResults.length) {
      slot.innerHTML = "";
      return;
    }
    slot.innerHTML = `
      <div class="kb-search-dropdown">
        <div class="kb-list">
          ${this._searchResults
            .map(
              (p) => `
              <div class="kb-row clickable" data-search-player-id="${escapeHtml(p.id)}">
                <div class="kb-row-left">
                  ${p.image ? `<img class="kb-avatar" src="${escapeHtml(p.image)}"/>` : ""}
                  <div class="kb-row-main">
                    <div class="kb-row-name">${escapeHtml(p.name)}</div>
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
      this._loadSnapshot(false);
    });

    this.shadowRoot.getElementById("kb-customize-btn")?.addEventListener("click", () => {
      this._customizeOpen = !this._customizeOpen;
      this._render();
    });

    this.shadowRoot.getElementById("kb-panel-refresh")?.addEventListener("click", async () => {
      if (!this._hass || this._loading) return;
      this._loading = true;
      this._render();
      try {
        this._snapshot = await kickbaseStore.refresh(this._hass, {
          leagueId: this._selectedLeagueId || activeLeague?.id,
        });
        this._error = null;
      } catch (err) {
        this._error = err?.message || String(err);
      } finally {
        this._loading = false;
        this._render();
      }
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
          try {
            const res = await this._hass.callWS({
              type: "kickbase/search_players",
              competition_id: activeLeague?.competition_id || "1",
              league_id: activeLeague?.id,
              query: q,
            });
            this._searchResults = res?.players || [];
            this._renderSearchDropdown(activeLeague);
          } catch {
            // ignore transient search errors
          }
        }, 320);
      });
    }
  }
}

if (!customElements.get("kickbase-panel")) {
  customElements.define("kickbase-panel", KickbasePanel);
}
