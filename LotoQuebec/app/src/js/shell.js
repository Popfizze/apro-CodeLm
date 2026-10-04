import { budgetMeter } from "./charts.js";
import { sourceChips } from "./refs.js";
import { currentPath, href, navigate } from "./router.js";
import { budgetSegments } from "./views.js";
import {
  closePopover,
  formatDateTime,
  formatDay,
  formatMoney,
  html,
  icon,
  mount,
  onDelegate,
  openPopover,
  raw,
  segmented,
  storageGet,
  storageSet,
  truncate,
} from "./ui.js";

const COLLAPSE_KEY = "nova.sidebar";

export const NAVIGATION = [
  { id: "vue", label: "Vue d'ensemble", icon: "home", path: "#/vue" },
  {
    id: "explorer",
    label: "Explorer",
    icon: "explore",
    path: "#/explorer",
    tabs: [
      { id: "interroger", label: "Interroger", href: "#/explorer" },
      { id: "sources", label: "Sources", href: "#/explorer/sources" },
    ],
  },
  {
    id: "historique",
    label: "Historique",
    icon: "history",
    path: "#/historique",
    tabs: [
      { id: "chronologie", label: "Chronologie", href: "#/historique" },
      { id: "evenements", label: "Événements", href: "#/historique/evenements" },
    ],
  },
  { id: "suivi", label: "Suivi", icon: "tracking", path: "#/suivi" },
  {
    id: "rapports",
    label: "Rapports",
    icon: "reports",
    path: "#/rapports/brief",
    tabs: [
      { id: "brief", label: "Brief de reprise", href: "#/rapports/brief" },
      { id: "briefing", label: "Briefing exécutif", href: "#/rapports/briefing" },
      { id: "dossier", label: "Dossier décisions et preuves", href: "#/rapports/dossier" },
      { id: "portefeuille", label: "Portefeuille", href: "#/rapports/portefeuille" },
    ],
  },
  { separator: true },
  {
    id: "documentation",
    label: "Documentation",
    icon: "docs",
    path: "#/documentation/defi",
    tabs: [
      { id: "defi", label: "Le défi", href: "#/documentation/defi" },
      { id: "reponses", label: "Réponses Q01-Q10", href: "#/documentation/reponses" },
      { id: "pipeline", label: "Pipeline", href: "#/documentation/pipeline" },
    ],
  },
];

function arcPath(radius, fromAngle, toAngle) {
  const point = (angle) => {
    const radians = (angle * Math.PI) / 180;
    return `${(24 + radius * Math.cos(radians)).toFixed(2)} ${(23 + radius * Math.sin(radians)).toFixed(2)}`;
  };
  return `M${point(fromAngle)} A${radius} ${radius} 0 0 1 ${point(toAngle)}`;
}

function logo() {
  const horns = [
    [12.5, 112, 248, 4.2],
    [17.5, 122, 238, 3.4],
    [22.5, 133, 227, 2.6],
  ]
    .map(([radius, from, to, stroke]) => `<path d="${arcPath(radius, from, to)}" stroke-width="${stroke}"/>`)
    .join("");
  const half = `<circle cx="24" cy="23" r="8" stroke="none" fill="currentColor"/>${horns}`;
  return raw(
    `<svg class="logo" viewBox="0 0 64 64" aria-hidden="true" fill="none" stroke="currentColor" stroke-linecap="round">` +
      `<g>${half}</g><g transform="rotate(180 32 32)">${half}</g></svg>`,
  );
}

function navItem(item) {
  if (item.separator) return html`<div class="nav-sep" role="separator"></div>`;
  return html`<a class="nav-item" href="${item.path}" data-group="${item.id}" data-label="${item.label}">
    ${icon(item.icon)}<span class="nav-label">${item.label}</span>
  </a>`;
}

function setCollapsed(collapsed) {
  document.getElementById("app").classList.toggle("is-collapsed", collapsed);
  const handle = document.getElementById("sidebar-handle");
  handle.setAttribute("aria-label", collapsed ? "Déplier le menu" : "Réduire le menu");
  document.querySelectorAll(".nav-item").forEach((item) => {
    if (collapsed) item.setAttribute("data-tip", item.dataset.label);
    else item.removeAttribute("data-tip");
  });
  storageSet(COLLAPSE_KEY, collapsed ? "1" : "0");
  window.dispatchEvent(new Event("resize"));
}

function toggleSidebar() {
  setCollapsed(!document.getElementById("app").classList.contains("is-collapsed"));
}

export function installSidebar() {
  mount(document.getElementById("brand"), html`${logo()}<span class="brand-word">Loto Québec</span>`);
  mount(document.getElementById("nav"), NAVIGATION.map(navItem));
  const handle = document.getElementById("sidebar-handle");
  mount(handle, icon("chevron"));
  handle.addEventListener("click", toggleSidebar);
  document.getElementById("sidebar").addEventListener("click", (event) => {
    if (!event.target.closest("a")) toggleSidebar();
  });
  setCollapsed(storageGet(COLLAPSE_KEY) === "1");
}

export function updateSidebar(groupId) {
  document.querySelectorAll(".nav-item").forEach((item) => {
    const active = item.dataset.group === groupId;
    item.classList.toggle("is-active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
    item.setAttribute("href", href(NAVIGATION.find((entry) => entry.id === item.dataset.group).path));
  });
}

function crumbList(crumbs) {
  return crumbs.map((crumb, index) => {
    const last = index === crumbs.length - 1;
    if (last) return html`<h1 class="crumb-current" title="${crumb.label}">${truncate(crumb.label, 56)}</h1>`;
    return html`<a class="crumb" href="${href(crumb.href)}">${crumb.label}</a
      ><span class="crumb-sep" aria-hidden="true">›</span>`;
  });
}

export function versionLabel(version) {
  const kind = version.n === 1 ? "référence" : "nouvelle version";
  return `v${version.n} · ${kind} · ${formatDateTime(version.asOf)}`;
}

function budgetBlock(model) {
  const totals = model.finance.totals;
  if (totals.authorized == null) {
    return html`<div class="budget"><span class="budget-labels">Budget : à confirmer</span></div>`;
  }
  return html`<button
    type="button"
    class="budget"
    data-action="budget"
    aria-expanded="false"
    aria-label="Détail du budget"
  >
    <span class="budget-labels">
      <span>Autorisé<b>${formatMoney(totals.authorized)}</b></span>
      <span>Facturé<b>${formatMoney(totals.billed)}</b></span>
      <span>Payé<b>${formatMoney(totals.paid)}</b></span>
    </span>
    ${budgetMeter(budgetSegments(totals), Math.max(totals.authorized, totals.billed ?? 0))}
  </button>`;
}

function changeRow(model, change, amountLabel) {
  return html`<li>
    <b>${change.id}</b> · ${change.title} · ${formatMoney(change.amount)} ${amountLabel}
    <div class="muted">
      ${[change.date ? formatDay(change.date) : "", change.authority, change.status].filter(Boolean).join(" · ")}
    </div>
    ${sourceChips(model, change.refs)}
  </li>`;
}

function budgetPopover(model) {
  const finance = model.finance;
  return html`<div class="popover-title">Budget autorisé</div>
    <p>${finance.authorizedCalc}</p>
    ${sourceChips(model, finance.contract.refs)}
    <div class="popover-title">Demandes de changement</div>
    <ul class="plain-list">
      ${finance.approvedChanges.map((change) => changeRow(model, change, "approuvée"))}
      ${finance.draftChanges.map((change) => changeRow(model, change, "brouillon"))}
      ${finance.absentChanges.length ? html`<li><b>Absentes du corpus :</b> ${finance.absentChanges.join(", ")}</li>` : ""}
    </ul>
    <div class="popover-title">Calcul</div>
    <p>${finance.totals.detail}</p>`;
}

function versionMenu(model) {
  return html`<ul class="menu-list" role="menu">
    ${model.versions.map(
      (version) =>
        html`<li role="none">
          <button
            type="button"
            role="menuitemradio"
            aria-checked="${version.n === model.version.n}"
            class="menu-item ${version.n === model.version.n ? "is-active" : ""}"
            data-version="${version.n}"
          >
            <b>v${version.n}</b>
            <span>${formatDateTime(version.asOf)}</span>
            <span class="muted"
              >${version.n === 1 ? "référence · figée" : version.files.map((file) => file.name).join(", ")}</span
            >
          </button>
        </li>`,
    )}
  </ul>`;
}

export function renderTopbar(model, crumbs, onImport) {
  const topbar = document.getElementById("topbar");
  mount(
    topbar,
    html`<nav class="crumbs" aria-label="Fil d'Ariane">${crumbList(crumbs)}</nav>
      <button
        type="button"
        class="version-pill"
        data-action="versions"
        aria-haspopup="menu"
        aria-expanded="false"
        title="${versionLabel(model.version)}"
      >
        <span class="version-main"
          >v${model.version.n} · ${model.version.n === 1 ? "référence" : "nouvelle version"}</span
        >
        <span class="version-date">${formatDateTime(model.version.asOf)}</span>${icon("down")}
      </button>
      ${budgetBlock(model)}
      <button type="button" class="btn btn-primary" data-action="import">
        ${icon("upload")}Importer des documents
      </button>`,
  );
  topbar.onclick = (event) => handleTopbarClick(event, model, onImport);
}

function handleTopbarClick(event, model, onImport) {
  const action = event.target.closest("[data-action]");
  if (!action) return;
  if (action.dataset.action === "import") onImport();
  if (action.dataset.action === "budget")
    openPopover(action, budgetPopover(model), { className: "is-wide", align: "end" });
  if (action.dataset.action === "versions") openVersionMenu(action, model);
}

function openVersionMenu(anchor, model) {
  const menu = openPopover(anchor, versionMenu(model), { className: "is-menu" });
  if (!menu) return;
  onDelegate(menu, "click", "[data-version]", (_, button) => {
    closePopover();
    navigate(currentPath(), Number(button.dataset.version));
  });
}

export function renderSubtabs(group, activeTab) {
  const element = document.getElementById("subtabs");
  const tabs = group?.tabs;
  element.hidden = !tabs;
  if (!tabs) return;
  mount(
    element,
    html`<div class="segmented">
        ${segmented(
          tabs.map((tab) => ({ ...tab, href: href(tab.href) })),
          activeTab,
        )}
      </div>
      <div class="subtabs-extra" id="subtabs-extra"></div>`,
  );
}
