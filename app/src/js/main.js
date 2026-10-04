import { baseModel } from "./data.js";
import { openImportDialog } from "./importer.js";
import { navigate, startRouter } from "./router.js";
import { NAVIGATION, installSidebar, renderSubtabs, renderTopbar, updateSidebar } from "./shell.js";
import { closePopover, debounce, html, installTooltip, mount } from "./ui.js";
import { versionModel } from "./versions.js";
import * as answers from "./screens/answers.js";
import * as ask from "./screens/ask.js";
import * as brief from "./screens/brief.js";
import * as briefing from "./screens/briefing.js";
import * as challenge from "./screens/challenge.js";
import * as documentPage from "./screens/document.js";
import * as dossier from "./screens/dossier.js";
import * as events from "./screens/events.js";
import * as overview from "./screens/overview.js";
import * as pipeline from "./screens/pipeline.js";
import * as portfolio from "./screens/portfolio.js";
import * as sources from "./screens/sources.js";
import * as timeline from "./screens/timeline.js";
import * as tracking from "./screens/tracking.js";

const ROUTES = [
  { pattern: "vue", group: "vue", screen: overview },
  { pattern: "explorer", group: "explorer", tab: "interroger", screen: ask, layout: "chat" },
  { pattern: "explorer/sources", group: "explorer", tab: "sources", screen: sources },
  {
    pattern: "explorer/sources/:sourceId/:passageIds?",
    group: "explorer",
    tab: "sources",
    screen: documentPage,
    hideTabs: true,
  },
  { pattern: "historique/evenements/:itemId?", group: "historique", tab: "evenements", screen: events },
  { pattern: "historique/:day?", group: "historique", tab: "chronologie", screen: timeline },
  { pattern: "suivi/:itemId?", group: "suivi", screen: tracking },
  { pattern: "rapports", group: "rapports", tab: "brief", screen: brief },
  { pattern: "rapports/brief", group: "rapports", tab: "brief", screen: brief },
  { pattern: "rapports/briefing", group: "rapports", tab: "briefing", screen: briefing },
  { pattern: "rapports/dossier/:decisionId?", group: "rapports", tab: "dossier", screen: dossier },
  { pattern: "rapports/portefeuille", group: "rapports", tab: "portefeuille", screen: portfolio },
  { pattern: "documentation", group: "documentation", tab: "defi", screen: challenge },
  { pattern: "documentation/defi", group: "documentation", tab: "defi", screen: challenge },
  { pattern: "documentation/reponses/:answerId?", group: "documentation", tab: "reponses", screen: answers },
  { pattern: "documentation/pipeline/:step?", group: "documentation", tab: "pipeline", screen: pipeline },
];

let activeCharts = {};
let lastRoute = null;

function matchSegment(part, value, params) {
  if (!part.startsWith(":")) return part === value;
  const optional = part.endsWith("?");
  if (value == null) return optional;
  params[part.replace(/[:?]/g, "")] = value;
  return true;
}

function matchRoute(route, segments) {
  const parts = route.pattern.split("/");
  if (segments.length > parts.length) return null;
  const params = {};
  const ok = parts.every((part, index) => matchSegment(part, segments[index], params));
  return ok ? params : null;
}

function resolve(segments) {
  for (const route of ROUTES) {
    const params = matchRoute(route, segments);
    if (params) return { route, params };
  }
  return { route: ROUTES[0], params: {} };
}

function baseCrumbs(route) {
  const group = NAVIGATION.find((entry) => entry.id === route.group);
  const crumbs = [
    { label: "NOVA", href: "#/vue" },
    { label: group.label, href: group.path },
  ];
  const tab = group.tabs?.find((entry) => entry.id === route.tab);
  return tab ? [...crumbs, { label: tab.label, href: tab.href }] : crumbs;
}

function drawChart(host, height) {
  const draw = activeCharts[host.dataset.chart];
  if (draw) mount(host, draw(Math.max(160, Math.floor(host.clientWidth)), height));
}

function drawCharts(root) {
  const hosts = [...root.querySelectorAll("[data-chart]")];
  hosts.forEach((host) => drawChart(host));
  hosts
    .filter((host) => host.classList.contains("is-fill"))
    .forEach((host) => drawChart(host, host.clientHeight));
}

function renderError(error) {
  console.error(error);
  return {
    body: html`<section class="card span-12">
      <p>Cet écran n'a pas pu être affiché : ${error.message}</p>
    </section>`,
  };
}

function renderScreen(screen, context) {
  try {
    return screen.render(context);
  } catch (error) {
    return renderError(error);
  }
}

function openImport(model) {
  openImportDialog({ base: baseModel(), model, onCreated: (n) => navigate("#/suivi", n) });
}

function render(routeState) {
  closePopover();
  const { route, params } = resolve(routeState.segments);
  const model = versionModel(baseModel(), routeState.version);
  const context = { model, params, base: baseModel(), refresh: () => render(routeState) };
  const view = renderScreen(route.screen, context);
  const content = document.getElementById("content");
  const sameRoute = lastRoute === route.pattern;
  lastRoute = route.pattern;
  activeCharts = view.charts || {};
  updateSidebar(route.group);
  renderTopbar(model, [...baseCrumbs(route), ...(view.crumbs || [])], () => openImport(model));
  renderSubtabs(route.hideTabs ? null : NAVIGATION.find((entry) => entry.id === route.group), route.tab);
  content.className = `content ${route.layout === "chat" ? "is-chat" : ""} ${view.className || ""}`;
  mount(content, view.body);
  if (!sameRoute || !view.keepScroll) content.scrollTop = 0;
  drawCharts(content);
  view.bind?.(content, context);
}

function start() {
  installSidebar();
  installTooltip();
  window.addEventListener(
    "resize",
    debounce(() => drawCharts(document.getElementById("content")), 120),
  );
  startRouter(render);
}

start();
