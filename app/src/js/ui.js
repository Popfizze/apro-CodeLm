const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const MONTHS = [
  "janv.",
  "févr.",
  "mars",
  "avr.",
  "mai",
  "juin",
  "juil.",
  "août",
  "sept.",
  "oct.",
  "nov.",
  "déc.",
];
const LONG_MONTHS = [
  "janvier",
  "février",
  "mars",
  "avril",
  "mai",
  "juin",
  "juillet",
  "août",
  "septembre",
  "octobre",
  "novembre",
  "décembre",
];

class SafeHtml {
  constructor(value) {
    this.value = value;
  }

  toString() {
    return this.value;
  }
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ESCAPES[char]);
}

export function raw(value) {
  return new SafeHtml(String(value ?? ""));
}

function toHtml(value) {
  if (value instanceof SafeHtml) return value.value;
  if (Array.isArray(value)) return value.map(toHtml).join("");
  if (value == null || value === false) return "";
  return escapeHtml(value);
}

export function html(strings, ...values) {
  let out = strings[0];
  values.forEach((value, index) => {
    out += toHtml(value) + strings[index + 1];
  });
  return new SafeHtml(out);
}

export function mount(element, content) {
  element.innerHTML = toHtml(content);
}

export function normalize(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();
}

export function truncate(value, max) {
  const text = String(value ?? "");
  return text.length > max ? text.slice(0, max - 1).trimEnd() + "…" : text;
}

export function firstSentence(value) {
  return String(value ?? "").split(/(?<=[.!?])\s/)[0];
}

export function basename(path) {
  return String(path ?? "")
    .split(/[\\/]/)
    .pop();
}

export function isoDay(value) {
  const match = String(value ?? "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? match[0] : null;
}

export function isoTime(value) {
  const match = String(value ?? "").match(/T(\d{2}):(\d{2})/);
  return match ? `${match[1]}:${match[2]}` : null;
}

function dayParts(value) {
  const day = isoDay(value);
  if (!day) return null;
  const [year, month, date] = day.split("-").map(Number);
  return { year, month, date };
}

export function formatDay(value, options = {}) {
  const parts = dayParts(value);
  if (!parts) return String(value ?? "");
  const label = `${parts.date} ${MONTHS[parts.month - 1]}`;
  return options.year === false ? label : `${label} ${parts.year}`;
}

export function formatLongDay(value) {
  const parts = dayParts(value);
  if (!parts) return String(value ?? "");
  return `${parts.date} ${LONG_MONTHS[parts.month - 1]} ${parts.year}`;
}

export function formatDateTime(value) {
  const time = isoTime(value);
  const day = formatDay(value);
  return time ? `${day}, ${time.replace(":", " h ")}` : day;
}

export function formatMoney(amount) {
  if (amount == null || Number.isNaN(Number(amount))) return "non documenté";
  return Number(amount).toLocaleString("fr-CA", { maximumFractionDigits: 0 }) + " $";
}

export function formatNumber(value) {
  return Number(value).toLocaleString("fr-CA");
}

export function daysBetween(fromIso, toIso) {
  const from = Date.parse(isoDay(fromIso) + "T00:00:00Z");
  const to = Date.parse(isoDay(toIso) + "T00:00:00Z");
  return Math.round((to - from) / 86400000);
}

export function addDays(iso, count) {
  const date = new Date(Date.parse(isoDay(iso) + "T00:00:00Z") + count * 86400000);
  return date.toISOString().slice(0, 10);
}

const ICON_PATHS = {
  home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
  explore: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  history: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  tracking: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2"/>',
  reports:
    '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  docs: '<path d="M4 5a2 2 0 0 1 2-2h5v18H6a2 2 0 0 1-2-2zM20 5a2 2 0 0 0-2-2h-5v18h5a2 2 0 0 0 2-2z"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  meeting:
    '<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M15 20c0-2.5 1.5-4.5 4-4.5"/>',
  ticket: '<path d="M4 7h16v3a2 2 0 0 0 0 4v3H4v-3a2 2 0 0 0 0-4z"/><path d="M14 7v10"/>',
  image:
    '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 17l-5-5-9 8"/>',
  sheet: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16"/>',
  invoice: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6"/>',
  contract: '<path d="M6 3h9l4 4v14H6z"/><path d="M9 12h7M9 16h4"/><path d="M15 3v4h4"/>',
  chat: '<path d="M4 5h16v11H9l-5 4z"/>',
  archive: '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v11h14V9M10 13h4"/>',
  decision: '<path d="M9 11l3 3 8-8"/><path d="M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>',
  print: '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M6 14h12v7H6z"/>',
  send: '<path d="M4 12l16-8-6 16-2.5-6.5z"/><path d="M11.5 13.5L20 4"/>',
  chevron: '<path d="M15 6l-6 6 6 6"/>',
  next: '<path d="M9 6l6 6-6 6"/>',
  down: '<path d="M6 9l6 6 6-6"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
};

export function icon(name, className = "icon") {
  return raw(
    `<svg class="${className}" viewBox="0 0 24 24" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`,
  );
}

const TYPE_ICONS = {
  courriel: "mail",
  reunion: "meeting",
  ticket: "ticket",
  document: "file",
  contrat: "contract",
  facture: "invoice",
  adr: "decision",
  teams: "chat",
  archive: "archive",
  image: "image",
  tableur: "sheet",
};

export function typeIcon(type) {
  return icon(TYPE_ICONS[type] || "file");
}

const TONE_GLYPHS = { critical: "✕", warning: "!", info: "i", positive: "✓", neutral: "–", accent: "" };

export function badge(label, tone = "neutral", title = "") {
  if (!label) return "";
  const glyph = TONE_GLYPHS[tone] ?? "";
  return html`<span class="badge is-${tone}" title="${title || label}"
    >${glyph ? html`<span class="badge-glyph" aria-hidden="true">${glyph}</span>` : ""}${label}</span
  >`;
}

export function tag(label, className = "") {
  return label ? html`<span class="tag ${className}">${label}</span>` : "";
}

export function card({ title, body, span = 12, extra = "", className = "", id = "" }) {
  return html`<section class="card span-${span} ${className}" ${raw(id ? `id="${escapeHtml(id)}"` : "")}>
    ${
      title
        ? html`<header class="card-head">
            <h2 class="card-title">${title}</h2>
            ${extra}
          </header>`
        : ""
    }
    <div class="card-body">${body}</div>
  </section>`;
}

export function link(href, label, className = "") {
  return html`<a class="${className}" href="${href}">${label}</a>`;
}

export function footerLink(href, label) {
  return html`<a class="card-foot" href="${href}">${label} ${icon("arrow")}</a>`;
}

export function placeholder(text = "non documenté") {
  return html`<span class="is-missing">${text}</span>`;
}

export function valueOr(value, fallback = "non documenté") {
  const text = value == null ? "" : String(value).trim();
  return text ? text : placeholder(fallback);
}

export function segmented(tabs, activeId) {
  return tabs.map(
    (tab) =>
      html`<a
        class="segment ${tab.id === activeId ? "is-active" : ""}"
        href="${tab.href}"
        ${raw(tab.id === activeId ? 'aria-current="page"' : "")}
        >${tab.label}</a
      >`,
  );
}

export function searchField({ id, value = "", placeholder: hint }) {
  return html`<label class="search-field">
    ${icon("explore")}
    <input id="${id}" type="search" value="${value}" placeholder="${hint}" autocomplete="off" />
  </label>`;
}

export function filterButton(count) {
  const label = count ? `Filtres · ${count}` : "Filtres";
  return html`<button type="button" class="btn btn-tertiary filter-btn" data-action="toggle-filters">
    ${icon("filter")}${label}
  </button>`;
}

export function onDelegate(root, eventName, selector, handler) {
  root.addEventListener(eventName, (event) => {
    const target = event.target.closest(selector);
    if (target && root.contains(target)) handler(event, target);
  });
}

export function debounce(callback, wait) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => callback(...args), wait);
  };
}

let activePopover = null;

export function closePopover() {
  if (!activePopover) return;
  activePopover.element.remove();
  activePopover.anchor.setAttribute("aria-expanded", "false");
  document.removeEventListener("pointerdown", activePopover.onOutside, true);
  activePopover = null;
}

function placePopover(element, anchor, align) {
  const box = anchor.getBoundingClientRect();
  const width = element.offsetWidth;
  const left = align === "end" ? box.right - width : box.left;
  element.style.left = `${Math.max(8, Math.min(left, window.innerWidth - width - 8))}px`;
  element.style.top = `${box.bottom + 6}px`;
}

export function openPopover(anchor, content, options = {}) {
  const reopening = activePopover?.anchor === anchor;
  closePopover();
  if (reopening) return null;
  const element = document.createElement("div");
  element.className = `popover ${options.className || ""}`;
  mount(element, content);
  document.getElementById("layer").append(element);
  placePopover(element, anchor, options.align);
  const onOutside = (event) => {
    if (!element.contains(event.target) && !anchor.contains(event.target)) closePopover();
  };
  document.addEventListener("pointerdown", onOutside, true);
  anchor.setAttribute("aria-expanded", "true");
  activePopover = { element, anchor, onOutside };
  return element;
}

function tooltipLines(text) {
  return String(text)
    .split("\n")
    .filter(Boolean)
    .map((line, index) => {
      const row = document.createElement("div");
      row.className = index === 0 ? "tooltip-value" : "tooltip-line";
      row.textContent = line;
      return row;
    });
}

function showTooltip(tooltip, target, point) {
  tooltip.replaceChildren(...tooltipLines(target.getAttribute("data-tip")));
  tooltip.hidden = false;
  const box = tooltip.getBoundingClientRect();
  const left = Math.min(point.x + 14, window.innerWidth - box.width - 8);
  const top = point.y + 16 + box.height > window.innerHeight ? point.y - box.height - 12 : point.y + 16;
  tooltip.style.left = `${Math.max(8, left)}px`;
  tooltip.style.top = `${Math.max(8, top)}px`;
}

export function installTooltip() {
  const tooltip = document.getElementById("tooltip");
  const show = (event) => {
    const target = event.target.closest?.("[data-tip]");
    if (!target) return;
    const box = target.getBoundingClientRect();
    const point =
      event.clientX != null ? { x: event.clientX, y: event.clientY } : { x: box.right, y: box.bottom };
    showTooltip(tooltip, target, point);
  };
  const hide = (event) => {
    if (event.target.closest?.("[data-tip]")) tooltip.hidden = true;
  };
  document.addEventListener("pointermove", show);
  document.addEventListener("pointerout", hide);
  document.addEventListener("focusin", show);
  document.addEventListener("focusout", hide);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      tooltip.hidden = true;
      closePopover();
    }
  });
}

export function storageGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function storageSet(key, value) {
  try {
    window.localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}
