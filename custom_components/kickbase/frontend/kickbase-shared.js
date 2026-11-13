/**
 * Shared Design System, WebSocket Store, Charts, Pitch & Modals for Kickbase HA UI.
 */

export const KICKBASE_CSS = `
  :host {
    --kb-accent: #ff4600;
    --kb-accent-glow: rgba(255, 70, 0, 0.28);
    --kb-bg: var(--kickbase-card-bg, #11161d);
    --kb-surface: rgba(255, 255, 255, 0.04);
    --kb-surface-hover: rgba(255, 255, 255, 0.08);
    --kb-border: rgba(255, 255, 255, 0.09);
    --kb-text: var(--kickbase-text-color, #f1f5f9);
    --kb-muted: var(--kickbase-muted-color, #94a3b8);
    --kb-green: #22c55e;
    --kb-red: #ef4444;
    --kb-amber: #f59e0b;
    --kb-blue: #38bdf8;
    --kb-radius: var(--ha-card-border-radius, 16px);
    display: block;
    color: var(--kb-text);
    font-family: var(--paper-font-body1_-_font-family, system-ui, -apple-system, sans-serif);
  }

  * { box-sizing: border-box; }

  .kb-card {
    background: linear-gradient(155deg, rgba(22, 29, 40, 0.96), rgba(14, 19, 27, 0.98));
    border: 1px solid var(--kb-border);
    border-radius: var(--kb-radius);
    padding: 16px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
    overflow: hidden;
  }

  .kb-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 14px;
  }

  .kb-title-wrap {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .kb-badge-icon {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    background: linear-gradient(135deg, var(--kb-accent), #ff7a33);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 14px;
    color: #fff;
    flex-shrink: 0;
    box-shadow: 0 4px 12px var(--kb-accent-glow);
  }

  .kb-title {
    font-size: 16px;
    font-weight: 700;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .kb-subtitle {
    font-size: 12px;
    color: var(--kb-muted);
    margin-top: 2px;
  }

  .kb-pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    background: var(--kb-surface);
    border: 1px solid var(--kb-border);
    color: var(--kb-text);
    white-space: nowrap;
  }
  .kb-pill.live {
    background: rgba(239, 68, 68, 0.16);
    border-color: rgba(239, 68, 68, 0.45);
    color: #fca5a5;
  }
  .kb-pill.ok {
    background: rgba(34, 197, 94, 0.15);
    border-color: rgba(34, 197, 94, 0.4);
    color: #86efac;
  }
  .kb-pill.warn {
    background: rgba(245, 158, 11, 0.15);
    border-color: rgba(245, 158, 11, 0.4);
    color: #fcd34d;
  }
  .kb-pill.danger {
    background: rgba(239, 68, 68, 0.18);
    border-color: rgba(239, 68, 68, 0.45);
    color: #fca5a5;
  }
  .kb-pill.accent {
    background: rgba(255, 70, 0, 0.16);
    border-color: rgba(255, 70, 0, 0.45);
    color: #fdba74;
  }

  .kb-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
  }
  .kb-pill.live .kb-dot {
    animation: kb-pulse 1.4s infinite;
  }
  @keyframes kb-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.8); }
  }

  .kb-kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 10px;
  }

  .kb-kpi {
    background: var(--kb-surface);
    border: 1px solid var(--kb-border);
    border-radius: 12px;
    padding: 11px 12px;
  }
  .kb-kpi-label {
    font-size: 11px;
    color: var(--kb-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .kb-kpi-val {
    font-size: 18px;
    font-weight: 800;
    margin-top: 4px;
    line-height: 1.15;
  }
  .kb-kpi-sub {
    font-size: 11px;
    color: var(--kb-muted);
    margin-top: 3px;
  }

  .kb-pos { color: var(--kb-green); }
  .kb-neg { color: var(--kb-red); }
  .kb-warn-txt { color: var(--kb-amber); }

  .kb-btn {
    background: var(--kb-surface);
    border: 1px solid var(--kb-border);
    color: var(--kb-text);
    border-radius: 10px;
    padding: 6px 11px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .kb-btn:hover {
    background: var(--kb-surface-hover);
    border-color: rgba(255, 255, 255, 0.22);
  }
  .kb-btn.active {
    background: rgba(255, 70, 0, 0.2);
    border-color: var(--kb-accent);
    color: #fff;
  }

  .kb-tabs {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }

  .kb-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .kb-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 9px 11px;
    border-radius: 12px;
    background: var(--kb-surface);
    border: 1px solid transparent;
    transition: background 0.15s, border-color 0.15s, transform 0.12s;
  }
  .kb-row.clickable { cursor: pointer; }
  .kb-row.clickable:hover {
    background: var(--kb-surface-hover);
    border-color: rgba(255, 255, 255, 0.14);
  }
  .kb-row.highlight {
    border-color: rgba(255, 70, 0, 0.45);
    background: rgba(255, 70, 0, 0.09);
  }

  .kb-row-left {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    flex: 1;
  }

  .kb-avatar {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    object-fit: cover;
    background: rgba(255, 255, 255, 0.06);
    flex-shrink: 0;
  }
  .kb-avatar.round { border-radius: 50%; }
  .kb-crest {
    width: 22px;
    height: 22px;
    object-fit: contain;
    flex-shrink: 0;
  }

  .kb-row-main { min-width: 0; flex: 1; }
  .kb-row-name {
    font-size: 13px;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .kb-row-meta {
    font-size: 11px;
    color: var(--kb-muted);
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 2px;
  }

  .kb-row-right {
    text-align: right;
    flex-shrink: 0;
  }
  .kb-row-val { font-size: 13px; font-weight: 700; }
  .kb-row-sub { font-size: 11px; color: var(--kb-muted); margin-top: 2px; }

  .kb-pos-tag {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 6px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.03em;
  }
  .kb-pos-gk { background: rgba(245, 158, 11, 0.2); color: #fcd34d; }
  .kb-pos-def { background: rgba(56, 189, 248, 0.2); color: #7dd3fc; }
  .kb-pos-mid { background: rgba(34, 197, 94, 0.2); color: #86efac; }
  .kb-pos-fwd { background: rgba(239, 68, 68, 0.2); color: #fca5a5; }

  /* Pitch */
  .kb-pitch {
    position: relative;
    border-radius: 16px;
    padding: 18px 10px;
    background:
      radial-gradient(circle at 50% 50%, rgba(255,255,255,0.06) 0, rgba(255,255,255,0.06) 54px, transparent 55px),
      linear-gradient(180deg, #114b2d 0%, #0e3f25 50%, #114b2d 100%);
    border: 2px solid rgba(255, 255, 255, 0.16);
    display: flex;
    flex-direction: column-reverse;
    gap: 14px;
    overflow: hidden;
  }
  .kb-pitch::before {
    content: "";
    position: absolute;
    left: 0; right: 0; top: 50%;
    height: 1px;
    background: rgba(255, 255, 255, 0.18);
  }
  .kb-pitch-line {
    display: flex;
    justify-content: space-evenly;
    align-items: flex-start;
    gap: 6px;
    position: relative;
    z-index: 1;
  }
  .kb-pitch-player {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 72px;
    cursor: pointer;
    transition: transform 0.14s;
  }
  .kb-pitch-player:hover { transform: translateY(-3px); }
  .kb-pitch-avatar-wrap {
    position: relative;
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: rgba(10, 15, 20, 0.72);
    border: 2px solid rgba(255, 255, 255, 0.35);
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .kb-pitch-avatar-wrap.captain {
    border-color: #fbbf24;
    box-shadow: 0 0 12px rgba(251, 191, 36, 0.55);
  }
  .kb-pitch-avatar-wrap.problem {
    border-color: var(--kb-red);
  }
  .kb-pitch-avatar-wrap img {
    width: 100%; height: 100%; object-fit: cover;
  }
  .kb-pitch-status {
    position: absolute;
    bottom: 0; right: 0;
    width: 12px; height: 12px;
    border-radius: 50%;
    border: 2px solid #0e3f25;
  }
  .kb-pitch-status.ok { background: var(--kb-green); }
  .kb-pitch-status.warning { background: var(--kb-amber); }
  .kb-pitch-status.danger { background: var(--kb-red); }
  .kb-pitch-status.muted { background: #64748b; }

  .kb-pitch-name {
    margin-top: 4px;
    padding: 2px 6px;
    border-radius: 6px;
    background: rgba(8, 12, 18, 0.85);
    font-size: 11px;
    font-weight: 700;
    color: #fff;
    max-width: 74px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-align: center;
  }
  .kb-pitch-pts {
    font-size: 10px;
    color: #d1fae5;
    margin-top: 2px;
    font-weight: 600;
  }

  .kb-empty {
    padding: 22px 12px;
    text-align: center;
    color: var(--kb-muted);
    font-size: 13px;
    background: var(--kb-surface);
    border-radius: 12px;
  }

  /* Modal */
  .kb-modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(4, 8, 14, 0.78);
    backdrop-filter: blur(8px);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 18px;
  }
  .kb-modal {
    width: min(760px, 100%);
    max-height: 88vh;
    overflow-y: auto;
    background: #121822;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 18px;
    padding: 20px;
    box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6);
    color: var(--kb-text);
  }
  .kb-modal-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 16px;
  }
  .kb-chart-box {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--kb-border);
    border-radius: 12px;
    padding: 12px;
    margin: 12px 0;
  }
  .kb-news-html img { max-width: 100%; border-radius: 10px; }
  .kb-news-html a { color: var(--kb-accent); }
`;

export function sanitizeHtml(rawHtml) {
  if (!rawHtml) return "";
  const doc = new DOMParser().parseFromString(String(rawHtml), "text/html");
  doc.querySelectorAll("script,iframe,object,embed,style").forEach((el) => el.remove());
  doc.querySelectorAll("*").forEach((el) => {
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name.toLowerCase();
      const val = attr.value.trim().toLowerCase();
      if (name.startsWith("on") || ((name === "href" || name === "src") && val.startsWith("javascript:"))) {
        el.removeAttribute(attr.name);
      }
      if (el.tagName === "IMG" && name === "src" && !isLocalUrl(attr.value)) {
        el.remove();
        return;
      }
    }
  });
  return doc.body.innerHTML;
}

export function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function formatEur(val) {
  if (val === null || val === undefined || Number.isNaN(Number(val))) return "–";
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(Number(val));
}

export function formatCompactEur(val) {
  if (val === null || val === undefined || Number.isNaN(Number(val))) return "–";
  const num = Number(val);
  const abs = Math.abs(num);
  const sign = num < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(2).replace(".", ",")} Mio €`;
  if (abs >= 1_000) return `${sign}${Math.round(abs / 1_000)} Tsd €`;
  return `${num} €`;
}

export function formatSignedCompactEur(val) {
  if (val === null || val === undefined || Number.isNaN(Number(val))) return "–";
  const num = Number(val);
  const prefix = num > 0 ? "+" : "";
  return `${prefix}${formatCompactEur(num)}`;
}

export function formatSecondsCountdown(sec, withSeconds = false) {
  if (sec === null || sec === undefined) return "–";
  const s = Math.max(0, Math.floor(Number(sec)));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const remS = s % 60;
  if (d > 0) return withSeconds ? `${d}d ${h}h ${m}m` : `${d}d ${h}h`;
  if (h > 0) return withSeconds ? `${h}h ${m}m ${String(remS).padStart(2, "0")}s` : `${h}h ${m}m`;
  return withSeconds ? `${m}m ${String(remS).padStart(2, "0")}s` : `${m}m`;
}

export function formatDateTime(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatIsoCountdown(iso, withSeconds = false) {
  if (!iso) return "–";
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return "–";
  const diffSec = Math.floor((target - Date.now()) / 1000);
  if (diffSec <= 0) return "Abgelaufen";
  return formatSecondsCountdown(diffSec, withSeconds);
}

export function startingProbBadge(p) {
  const sp = p?.starting_prob;
  if (!sp || !sp.short) return "";
  return `<span class="kb-pill ${escapeHtml(sp.severity || "muted")}" style="padding:1px 6px;font-size:10px" title="Startelf-Wahrscheinlichkeit: ${escapeHtml(sp.label_de || sp.short)}">S11 ${escapeHtml(sp.short)}</span>`;
}

export function positionClass(posCode) {
  switch (Number(posCode)) {
    case 1: return "kb-pos-gk";
    case 2: return "kb-pos-def";
    case 3: return "kb-pos-mid";
    case 4: return "kb-pos-fwd";
    default: return "";
  }
}

export function sortPlayersByPosition(players) {
  return [...players].sort((a, b) => {
    const posA = Number(a.position_code || (a.position && a.position.code) || 99);
    const posB = Number(b.position_code || (b.position && b.position.code) || 99);
    if (posA !== posB) return posA - posB;
    return (b.market_value || 0) - (a.market_value || 0);
  });
}

export function isLocalUrl(url) {
  return typeof url === "string" && (url.startsWith("/") || url.startsWith("data:"));
}

export function localImg(obj, ...keys) {
  if (!obj) return null;
  for (const k of keys) {
    const val = obj[k];
    if (isLocalUrl(val)) return val;
  }
  return null;
}

export function playerImg(p) {
  return localImg(p, "local_image", "image");
}

export function teamImg(p) {
  return localImg(p, "local_team_image", "team_image");
}

export function avatarImg(m) {
  return localImg(m, "local_avatar", "avatar");
}

export function renderMarketValueChartSvg(series, width = 620, height = 170) {
  if (!Array.isArray(series) || series.length < 2) {
    return `<div class="kb-empty">Keine Marktwert-Historie verfügbar</div>`;
  }
  const values = series.map((p) => Number(p.market_value || 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(1, max - min);
  const padX = 10;
  const padY = 16;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const coords = values.map((v, idx) => {
    const x = padX + (idx / (values.length - 1)) * innerW;
    const y = padY + innerH - ((v - min) / span) * innerH;
    return [x, y];
  });

  const linePath = coords
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");
  const areaPath = `${linePath} L${coords[coords.length - 1][0].toFixed(1)},${(
    height - padY
  ).toFixed(1)} L${coords[0][0].toFixed(1)},${(height - padY).toFixed(1)} Z`;

  const rising = values[values.length - 1] >= values[0];
  const stroke = rising ? "#22c55e" : "#ef4444";
  const fill = rising ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)";

  const firstDate = escapeHtml(series[0]?.date || "");
  const lastDate = escapeHtml(series[series.length - 1]?.date || "");

  return `
    <svg viewBox="0 0 ${width} ${height}" width="100%" style="display:block;overflow:visible">
      <defs>
        <linearGradient id="kbAreaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${stroke}" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="${stroke}" stop-opacity="0.02"/>
        </linearGradient>
      </defs>
      <path d="${areaPath}" fill="url(#kbAreaGrad)"/>
      <path d="${linePath}" fill="none" stroke="${stroke}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="${coords[coords.length - 1][0].toFixed(1)}" cy="${coords[coords.length - 1][1].toFixed(1)}" r="4" fill="${stroke}"/>
    </svg>
    <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--kb-muted);margin-top:4px">
      <span>${firstDate} (${formatCompactEur(values[0])})</span>
      <span>Min: ${formatCompactEur(min)} · Max: ${formatCompactEur(max)}</span>
      <span>${lastDate} (${formatCompactEur(values[values.length - 1])})</span>
    </div>
  `;
}

export function renderPitchHtml(players, formation = "4-4-2") {
  const byPos = { 1: [], 2: [], 3: [], 4: [] };
  for (const p of players || []) {
    const code = Number(p.position_code || 0);
    if (byPos[code]) byPos[code].push(p);
  }
  const rows = [byPos[1], byPos[2], byPos[3], byPos[4]].filter((r) => r.length > 0);
  if (rows.length === 0) {
    return `<div class="kb-empty">Keine Aufstellungsdaten für Formation ${escapeHtml(formation)}</div>`;
  }

  return `
    <div class="kb-pitch">
      ${rows
        .map(
          (row) => `
          <div class="kb-pitch-line">
            ${row
              .map((p) => {
                const sev = p.status?.severity || "muted";
                const cap = p.is_captain ? "captain" : "";
                const prob = sev === "danger" || p.matchday_status === 8 ? "problem" : "";
                const ptsLabel =
                  p.points !== undefined && p.points !== 0
                    ? `${p.points} Pkt`
                    : `Ø ${p.average_points ?? 0}`;
                return `
                  <div class="kb-pitch-player" data-player-id="${escapeHtml(p.id)}">
                    <div class="kb-pitch-avatar-wrap ${cap} ${prob}">
                      ${
                        playerImg(p)
                          ? `<img src="${escapeHtml(playerImg(p))}" alt="${escapeHtml(p.name)}" loading="lazy"/>`
                          : `<span>${escapeHtml((p.name || "?").slice(0, 2))}</span>`
                      }
                      <span class="kb-pitch-status ${escapeHtml(sev)}" title="${escapeHtml(
                        p.status?.label_de || ""
                      )}"></span>
                    </div>
                    <div class="kb-pitch-name">${p.is_captain ? "👑 " : ""}${escapeHtml(
                  p.name
                )}</div>
                    <div class="kb-pitch-pts">${escapeHtml(ptsLabel)}</div>
                  </div>
                `;
              })
              .join("")}
          </div>
        `
        )
        .join("")}
    </div>
  `;
}

/**
 * Shared Snapshot Store with lightweight caching across modular cards.
 */
class KickbaseStore {
  constructor() {
    this._cache = new Map();
    this._inflight = new Map();
  }

  async getSnapshot(hass, { entryId, leagueId, force = false } = {}) {
    const key = `${entryId || "_"}:${leagueId || "_"}`;
    const cached = this._cache.get(key);
    if (!force && cached && Date.now() - cached.ts < 8000) {
      return cached.data;
    }
    if (!force && this._inflight.has(key)) {
      return this._inflight.get(key);
    }
    const msg = { type: "kickbase/get_snapshot" };
    if (entryId) msg.entry_id = entryId;
    if (leagueId) msg.league_id = leagueId;

    const promise = hass
      .callWS(msg)
      .then((data) => {
        this._cache.set(key, { ts: Date.now(), data });
        this._inflight.delete(key);
        return data;
      })
      .catch((err) => {
        this._inflight.delete(key);
        throw err;
      });
    this._inflight.set(key, promise);
    return promise;
  }

  async refresh(hass, { entryId, leagueId, module, forceDetails = false } = {}) {
    const msg = { type: "kickbase/refresh" };
    if (entryId) msg.entry_id = entryId;
    if (leagueId) msg.league_id = leagueId;
    if (module) msg.module = module;
    if (forceDetails) msg.force_details = true;
    const data = await hass.callWS(msg);
    const key = `${entryId || "_"}:${leagueId || "_"}`;
    this._cache.set(key, { ts: Date.now(), data });
    return data;
  }

  async queryLocalPlayers(hass, { entryId, leagueId, query, scope, statusSeverity, limit = 120 } = {}) {
    const msg = { type: "kickbase/query_local_players", league_id: leagueId, limit };
    if (entryId) msg.entry_id = entryId;
    if (query) msg.query = query;
    if (scope && scope !== "all") msg.scope = scope;
    if (statusSeverity && statusSeverity !== "all") msg.status_severity = statusSeverity;
    return hass.callWS(msg);
  }

  async getDbStats(hass, { entryId, leagueId } = {}) {
    const msg = { type: "kickbase/get_db_stats" };
    if (entryId) msg.entry_id = entryId;
    if (leagueId) msg.league_id = leagueId;
    return hass.callWS(msg);
  }

  async getRequestLogs(hass, { entryId, leagueId, limit = 100, offset = 0 } = {}) {
    const msg = { type: "kickbase/get_request_logs", limit, offset };
    if (entryId) msg.entry_id = entryId;
    if (leagueId) msg.league_id = leagueId;
    return hass.callWS(msg);
  }

  async getRequestLogDetail(hass, { logId, entryId } = {}) {
    const msg = { type: "kickbase/get_request_log_detail", log_id: Number(logId) };
    if (entryId) msg.entry_id = entryId;
    return hass.callWS(msg);
  }

  async getAllDatabasePlayers(hass, { entryId, leagueId } = {}) {
    const msg = { type: "kickbase/get_all_database_players" };
    if (entryId) msg.entry_id = entryId;
    if (leagueId) msg.league_id = leagueId;
    return hass.callWS(msg);
  }

  async collectDailyBonus(hass, { entryId, leagueId } = {}) {
    const msg = { type: "kickbase/collect_daily_bonus" };
    if (entryId) msg.entry_id = entryId;
    if (leagueId) msg.league_id = leagueId;
    return hass.callWS(msg);
  }

  async syncAllDatabasePlayers(hass, { entryId, leagueId } = {}) {
    const msg = { type: "kickbase/sync_all_database_players" };
    if (entryId) msg.entry_id = entryId;
    if (leagueId) msg.league_id = leagueId;
    return hass.callWS(msg);
  }

  async getManagerDetail(hass, { entryId, leagueId, managerId } = {}) {
    const msg = { type: "kickbase/get_manager_detail", manager_id: String(managerId) };
    if (entryId) msg.entry_id = entryId;
    if (leagueId) msg.league_id = leagueId;
    return hass.callWS(msg);
  }
}

export const kickbaseStore = new KickbaseStore();

/**
 * Interactive detail modal helper rendered inside a host shadowRoot.
 */
export async function openKickbaseModal(shadowRoot, hass, kind, params) {
  let backdrop = shadowRoot.querySelector(".kb-modal-backdrop");
  if (backdrop) backdrop.remove();

  backdrop = document.createElement("div");
  backdrop.className = "kb-modal-backdrop";
  backdrop.innerHTML = `<div class="kb-modal"><div class="kb-empty">Lade Kickbase-Details...</div></div>`;
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) backdrop.remove();
  });
  shadowRoot.appendChild(backdrop);

  const modal = backdrop.querySelector(".kb-modal");
  try {
    if (kind === "player") {
      const data = await hass.callWS({
        type: "kickbase/get_player_detail",
        league_id: params.leagueId,
        player_id: params.playerId,
      });
      const p = data.player || {};
      const mv = data.market_value || {};
      const perfSeasons = data.performance || [];
      const latestSeason = perfSeasons[perfSeasons.length - 1] || {};
      const ph = (latestSeason.ph || []).slice(-10);
      const history = (data.transfer_history || []).slice(0, 8);
      const statusHistory = (data.status_history || []).slice(0, 20);
      const pImg = playerImg(p);
      const tImg = teamImg(p);
      const dbStand = data.db_updated_at || p.db_updated_at;

      modal.innerHTML = `
        <div class="kb-modal-head">
          <div class="kb-row-left">
            ${pImg ? `<img class="kb-avatar" style="width:56px;height:56px" src="${escapeHtml(pImg)}"/>` : ""}
            ${tImg ? `<img class="kb-crest" style="width:28px;height:28px" src="${escapeHtml(tImg)}"/>` : ""}
            <div>
              <div class="kb-title" style="font-size:20px">${escapeHtml(p.full_name || p.name)}</div>
              <div class="kb-subtitle">
                ${escapeHtml(p.team_name || "")} · ${escapeHtml(p.position?.name_de || "")} ·
                <span class="kb-pill ${escapeHtml(p.status?.severity || "ok")}">${escapeHtml(p.status?.label_de || "Fit")}</span>
                ${startingProbBadge(p)}
                <span class="kb-pill ok" style="margin-left:4px">💾 Lokale DB${dbStand ? ` · ${formatDateTime(dbStand)}` : ""}</span>
              </div>
              ${p.owner_name ? `<div class="kb-subtitle" style="margin-top:2px">Besitzer: ${escapeHtml(p.owner_name)}${p.is_on_market ? ` · Auf Transfermarkt (${formatCompactEur(p.price || p.market_value)})` : ""}</div>` : ""}
              ${p.status_text ? `<div class="kb-subtitle kb-warn-txt" style="margin-top:4px">${escapeHtml(p.status_text)}</div>` : ""}
            </div>
          </div>
          <div style="display:flex;gap:6px;flex-shrink:0">
            <button class="kb-btn" data-close>Schließen</button>
          </div>
        </div>

        <div class="kb-kpi-grid">
          <div class="kb-kpi">
            <div class="kb-kpi-label">Marktwert</div>
            <div class="kb-kpi-val">${formatCompactEur(p.market_value)}</div>
            <div class="kb-kpi-sub ${Number(p.market_value_24h_change) >= 0 ? "kb-pos" : "kb-neg"}">${formatSignedCompactEur(p.market_value_24h_change)} (24h)</div>
          </div>
          <div class="kb-kpi">
            <div class="kb-kpi-label">Punkte Gesamt</div>
            <div class="kb-kpi-val">${p.total_points ?? 0}</div>
            <div class="kb-kpi-sub">Ø ${p.average_points ?? 0} Pkt / Spiel</div>
          </div>
          <div class="kb-kpi">
            <div class="kb-kpi-label">Tore / Vorlagen</div>
            <div class="kb-kpi-val">${p.goals ?? 0} / ${p.assists ?? 0}</div>
            <div class="kb-kpi-sub">Gelb: ${p.yellow_cards ?? 0} · Rot: ${p.red_cards ?? 0}</div>
          </div>
          <div class="kb-kpi">
            <div class="kb-kpi-label">Kaufpreis / G&V</div>
            <div class="kb-kpi-val">${mv.transfer_price ? formatCompactEur(mv.transfer_price) : "–"}</div>
            <div class="kb-kpi-sub ${Number(mv.profit_loss) >= 0 ? "kb-pos" : "kb-neg"}">${mv.profit_loss ? formatSignedCompactEur(mv.profit_loss) : "Kein Kaufpreis"}</div>
          </div>
        </div>

        <div class="kb-chart-box">
          <div class="kb-kpi-label" style="margin-bottom:6px">Lokaler Marktwert-Verlauf (${(mv.series || []).length} Tage)</div>
          ${renderMarketValueChartSvg(mv.series)}
        </div>

        ${
          statusHistory.length
            ? `
          <div class="kb-chart-box">
            <div class="kb-kpi-label" style="margin-bottom:8px">Lokale Status- & Besitzer-Historie (${statusHistory.length})</div>
            <div class="kb-list">
              ${statusHistory
                .map(
                  (st) => `
                  <div class="kb-row">
                    <div class="kb-row-left">
                      <span class="kb-pill ${escapeHtml(st.status_severity || "ok")}">${escapeHtml(st.status_label_de || "Fit")}</span>
                      <div class="kb-row-main">
                        <div class="kb-row-name">${escapeHtml(st.status_text || st.owner_name || "Status erfasst")}</div>
                        <div class="kb-row-meta">${formatDateTime(st.recorded_at)} · Besitzer: ${escapeHtml(st.owner_name || "Kickbase")}${st.is_on_market ? ` · 🛒 Auf Markt (${formatCompactEur(st.market_price)})` : ""}</div>
                      </div>
                    </div>
                    <div class="kb-row-val">${formatCompactEur(st.market_value)}</div>
                  </div>
                `
                )
                .join("")}
            </div>
          </div>
        `
            : ""
        }

        ${
          ph.length
            ? `
          <div class="kb-chart-box">
            <div class="kb-kpi-label" style="margin-bottom:8px">Letzte Spieltage (${escapeHtml(latestSeason.ti || "")})</div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(52px,1fr));gap:6px">
              ${ph
                .map(
                  (d) => `
                  <div class="kb-kpi" style="padding:6px;text-align:center">
                    <div style="font-size:10px;color:var(--kb-muted)">ST ${escapeHtml(d.day)}</div>
                    <div style="font-size:14px;font-weight:800;color:${Number(d.p) >= 100 ? "var(--kb-green)" : Number(d.p) < 0 ? "var(--kb-red)" : "var(--kb-text)"}">${d.p ?? 0}</div>
                    <div style="font-size:10px;color:var(--kb-muted)">${escapeHtml(d.mp || "0'")}</div>
                  </div>
                `
                )
                .join("")}
            </div>
          </div>
        `
            : ""
        }

        ${
          history.length
            ? `
          <div class="kb-chart-box">
            <div class="kb-kpi-label" style="margin-bottom:8px">Transfer-Historie in der Liga</div>
            <div class="kb-list">
              ${history
                .map(
                  (h) => `
                  <div class="kb-row">
                    <div class="kb-row-left">
                      <div class="kb-row-name">${escapeHtml(h.user_name)}</div>
                      <div class="kb-row-meta">${formatDateTime(h.date)}</div>
                    </div>
                    <div class="kb-row-val">${formatCompactEur(h.price)}</div>
                  </div>
                `
                )
                .join("")}
            </div>
          </div>
        `
            : ""
        }
      `;
    } else if (kind === "manager") {
      const data = await hass.callWS({
        type: "kickbase/get_manager_detail",
        league_id: params.leagueId,
        manager_id: params.managerId,
      });
      const d = data.dashboard || {};
      const squad = data.squad || [];
      const transfers = (data.transfers || []).slice(0, 10);
      const mgrAvatar = avatarImg(d);

      modal.innerHTML = `
        <div class="kb-modal-head">
          <div class="kb-row-left">
            ${mgrAvatar ? `<img class="kb-avatar round" style="width:52px;height:52px" src="${escapeHtml(mgrAvatar)}"/>` : ""}
            <div>
              <div class="kb-title" style="font-size:20px">${escapeHtml(d.name)}</div>
              <div class="kb-subtitle">
                Platz #${d.rank ?? "–"} · ${d.matchday_wins ?? 0} Spieltagssiege ·
                <span class="kb-pill ok">💾 Lokale DB${data.db_updated_at ? ` · ${formatDateTime(data.db_updated_at)}` : ""}</span>
              </div>
            </div>
          </div>
          <button class="kb-btn" data-close>Schließen</button>
        </div>

        <div class="kb-kpi-grid" style="margin-bottom:14px">
          <div class="kb-kpi"><div class="kb-kpi-label">Teamwert</div><div class="kb-kpi-val">${formatCompactEur(d.team_value)}</div></div>
          <div class="kb-kpi"><div class="kb-kpi-label">Gesamtpunkte</div><div class="kb-kpi-val">${d.total_points ?? 0}</div></div>
          <div class="kb-kpi"><div class="kb-kpi-label">Schnitt / ST</div><div class="kb-kpi-val">${d.average_points ?? 0}</div></div>
          <div class="kb-kpi"><div class="kb-kpi-label">Kadergröße</div><div class="kb-kpi-val">${squad.length}</div></div>
        </div>

        <div class="kb-kpi-label" style="margin-bottom:8px">Kader (${squad.length} Spieler · Klick für lokalen Verlauf)</div>
        <div class="kb-list" style="margin-bottom:14px">
          ${squad
            .map(
              (p) => `
              <div class="kb-row clickable" data-modal-player-id="${escapeHtml(p.id)}">
                <div class="kb-row-left">
                  ${playerImg(p) ? `<img class="kb-avatar" src="${escapeHtml(playerImg(p))}"/>` : ""}
                  <div class="kb-row-main">
                    <div class="kb-row-name">${escapeHtml(p.name)}</div>
                    <div class="kb-row-meta"><span class="kb-pos-tag ${positionClass(p.position_code)}">${escapeHtml(p.position?.short)}</span> · ${escapeHtml(p.status?.label_de || "Fit")} · Ø ${p.average_points ?? 0}</div>
                  </div>
                </div>
                <div class="kb-row-right">
                  <div class="kb-row-val">${formatCompactEur(p.market_value)}</div>
                  <div class="kb-row-sub ${Number(p.market_value_since_buy) >= 0 ? "kb-pos" : "kb-neg"}">${formatSignedCompactEur(p.market_value_since_buy)}</div>
                </div>
              </div>
            `
            )
            .join("")}
        </div>

        ${
          transfers.length
            ? `
          <div class="kb-kpi-label" style="margin-bottom:8px">Letzte Transfers</div>
          <div class="kb-list">
            ${transfers
              .map(
                (t) => `
                <div class="kb-row">
                  <div class="kb-row-left">
                    <div class="kb-row-main">
                      <div class="kb-row-name">${escapeHtml(t.player_name)} ${t.other_manager ? `↔ ${escapeHtml(t.other_manager)}` : ""}</div>
                      <div class="kb-row-meta">${formatDateTime(t.date)}</div>
                    </div>
                  </div>
                  <div class="kb-row-val">${formatCompactEur(t.price)}</div>
                </div>
              `
              )
              .join("")}
          </div>
        `
            : ""
        }
      `;
    } else if (kind === "match") {
      const m = await hass.callWS({
        type: "kickbase/get_match_detail",
        match_id: params.matchId,
        ...(params.leagueId ? { league_id: params.leagueId } : {}),
      });
      const mT1Img = localImg(m, "local_team1_image", "team1_image");
      const mT2Img = localImg(m, "local_team2_image", "team2_image");
      modal.innerHTML = `
        <div class="kb-modal-head">
          <div class="kb-row-left">
            ${mT1Img ? `<img class="kb-crest" style="width:28px;height:28px" src="${escapeHtml(mT1Img)}"/>` : ""}
            <div>
              <div class="kb-title" style="font-size:19px">${escapeHtml(m.team1_name)} ${m.team1_goals ?? 0} : ${m.team2_goals ?? 0} ${escapeHtml(m.team2_name)}</div>
              <div class="kb-subtitle">
                ${m.is_live ? `LIVE ${escapeHtml(m.minute)}'` : formatDateTime(m.date)} ·
                <span class="kb-pill ok">💾 Lokale DB</span>
              </div>
            </div>
            ${mT2Img ? `<img class="kb-crest" style="width:28px;height:28px" src="${escapeHtml(mT2Img)}"/>` : ""}
          </div>
          <button class="kb-btn" data-close>Schließen</button>
        </div>

        <div class="kb-kpi-label" style="margin-bottom:8px">Live-Ereignisse (${(m.events || []).length})</div>
        <div class="kb-list" style="margin-bottom:14px">
          ${(m.events || []).length
            ? (m.events || [])
                .slice()
                .reverse()
                .map(
                  (ev) => `
                  <div class="kb-row">
                    <div class="kb-row-left">
                      <span class="kb-pill">${escapeHtml(ev.minute)}'</span>
                      <div>
                        <div class="kb-row-name">${escapeHtml(ev.event_label)}</div>
                        <div class="kb-row-meta">${escapeHtml(ev.player_name || "Spielereignis")}</div>
                      </div>
                    </div>
                  </div>
                `
                )
                .join("")
            : `<div class="kb-empty">Noch keine Ereignisse</div>`}
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div>
            <div class="kb-kpi-label" style="margin-bottom:6px">${escapeHtml(m.team1_name)} Startelf</div>
            <div class="kb-list">
              ${(m.team1_lineup || [])
                .map((p) => `<div class="kb-row"><div class="kb-row-name">${escapeHtml(p.name)}</div><span class="kb-pos-tag ${positionClass(p.position_code)}">${escapeHtml(p.position?.short)}</span></div>`)
                .join("")}
            </div>
          </div>
          <div>
            <div class="kb-kpi-label" style="margin-bottom:6px">${escapeHtml(m.team2_name)} Startelf</div>
            <div class="kb-list">
              ${(m.team2_lineup || [])
                .map((p) => `<div class="kb-row"><div class="kb-row-name">${escapeHtml(p.name)}</div><span class="kb-pos-tag ${positionClass(p.position_code)}">${escapeHtml(p.position?.short)}</span></div>`)
                .join("")}
            </div>
          </div>
        </div>
      `;
    } else if (kind === "news") {
      const item = await hass.callWS({
        type: "kickbase/get_news_item",
        item_id: params.itemId,
      });
      const nImg = localImg(item, "local_image", "image");
      modal.innerHTML = `
        <div class="kb-modal-head">
          <div>
            <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">
              <span class="kb-pill accent">${escapeHtml(item.label || "News")}</span>
              <span class="kb-pill ok">💾 Lokale DB</span>
            </div>
            <div class="kb-title" style="font-size:19px">${escapeHtml(item.title)}</div>
            <div class="kb-subtitle">${formatDateTime(item.date)}</div>
          </div>
          <button class="kb-btn" data-close>Schließen</button>
        </div>
        ${nImg ? `<img src="${escapeHtml(nImg)}" style="width:100%;max-height:240px;object-fit:cover;border-radius:12px;margin-bottom:12px"/>` : ""}
        <div class="kb-news-html">${sanitizeHtml(item.html) || "<p>Kein Inhalt.</p>"}</div>
      `;
    }
  } catch (err) {
    modal.innerHTML = `
      <div class="kb-modal-head">
        <div class="kb-title">Fehler beim Laden</div>
        <button class="kb-btn" data-close>Schließen</button>
      </div>
      <div class="kb-empty">${escapeHtml(err?.message || err)}</div>
    `;
  }

  modal.querySelector("[data-close]")?.addEventListener("click", () => backdrop.remove());
  modal.querySelectorAll("[data-modal-player-id]").forEach((el) => {
    el.addEventListener("click", () => {
      backdrop.remove();
      openKickbaseModal(shadowRoot, hass, "player", {
        leagueId: params.leagueId,
        playerId: el.dataset.modalPlayerId,
      });
    });
  });
}
