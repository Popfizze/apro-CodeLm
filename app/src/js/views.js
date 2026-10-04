import { actionTone, isOpenAction, natureInfo, shortStatus, subjectName } from "./data.js";
import { href } from "./router.js";
import { badge, daysBetween, formatDateTime, html, icon, mount, normalize, raw, tag } from "./ui.js";

const PROBABILITY_ORDER = ["elevee", "moyenne", "faible"];
const IMPACT_ORDER = ["faible", "moyen", "eleve"];
const TREND_GLYPHS = [
  [/^en hausse/, "↑"],
  [/^stable/, "→"],
  [/^en (forte )?baisse/, "↓"],
  [/^clos/, "✓"],
];

export function chartHost(name, className = "") {
  return html`<div class="chart ${className}" data-chart="${name}"></div>`;
}

export function statusBadge(status) {
  return badge(shortStatus(status) || "non documenté", actionTone(status), status);
}

export function dueBadge(due) {
  const value = normalize(due).trim();
  if (!value) return badge("à confirmer", "warning");
  if (value.startsWith("a confirmer")) return badge("à confirmer", "warning", due);
  if (value.startsWith("immediat")) return badge("immédiat", "critical", due);
  return html`<span class="due" title="${due}">${due}</span>`;
}

export function typeBadge(type) {
  if (type === "engagement_documente") return tag("Engagement documenté", "is-commitment");
  if (type === "recommandation_equipe") return tag("Recommandation de l'équipe", "is-recommendation");
  return "";
}

export function ownerStatusBadge(status) {
  if (status === "confirme") return tag("confirmé", "is-confirmed");
  if (status === "propose") return tag("proposé", "is-proposed");
  return "";
}

export function natureBadge(natureKey) {
  const info = natureInfo(natureKey);
  return html`<span class="nature is-${info.group}"
    ><span class="swatch fill-${info.group}"></span>${info.label}</span
  >`;
}

export function shortSubject(name) {
  return String(name || "").split(" (")[0];
}

export function subjectTag(model, subjectId) {
  const name = subjectName(model, subjectId);
  return name ? html`<span class="tag is-subject" title="${name}">${shortSubject(name)}</span>` : "";
}

export function reviewBadge(model, subjectIds) {
  const touched = [].concat(subjectIds).some((id) => id && model.reviewSubjects?.has(id));
  return touched ? badge("à revoir", "warning", "Sujet touché par une nouvelle version") : "";
}

export function conditionTag(conditionId) {
  return conditionId ? html`<span class="tag is-condition">${conditionId}</span>` : "";
}

function conditionOrder(model, action) {
  const index = model.golive.conditions.findIndex((condition) => condition.id === action.condition);
  return index < 0 ? 99 : index;
}

function actionRank(model, action) {
  return [
    conditionOrder(model, action),
    normalize(action.due).startsWith("immediat") ? 0 : 1,
    action.type === "engagement_documente" ? 0 : 1,
  ];
}

export function priorityActions(model) {
  return model.actions
    .filter(isOpenAction)
    .map((action) => ({ action, rank: actionRank(model, action) }))
    .sort(
      (left, right) => compareRanks(left.rank, right.rank) || left.action.id.localeCompare(right.action.id),
    )
    .map((entry) => entry.action);
}

function compareRanks(left, right) {
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) return left[index] - right[index];
  }
  return 0;
}

export function actionById(model, id) {
  return model.actions.find((action) => action.id === id) || null;
}

export function conditionChainRows(model) {
  return model.golive.conditions.map((condition) => ({
    id: condition.id,
    label: condition.text,
    state: condition.state,
    validator: condition.validator,
    href: href(`#/suivi/${condition.id}`),
    nodes: condition.actionIds.map((id) => chainNode(model, id)),
  }));
}

function chainNode(model, id) {
  const action = actionById(model, id);
  if (!action) return { id, label: "non documenté", tone: "neutral", href: href("#/suivi") };
  return {
    id,
    label: action.text,
    owner: `Responsable : ${action.owner}`,
    due: `Échéance : ${action.due || "à confirmer"}`,
    status: `Statut : ${action.status}`,
    tone: actionTone(action.status),
    href: href(`#/suivi/${id}`),
  };
}

export function goliveSummary(model) {
  const golive = model.golive;
  const unmet = golive.conditions.filter((condition) => condition.unmet).length;
  const toConfirm = golive.conditions.filter((condition) =>
    normalize(condition.due).startsWith("a confirmer"),
  ).length;
  return {
    date: golive.targetDate,
    daysLeft: golive.targetDate && model.asOf ? daysBetween(model.asOf, golive.targetDate) : null,
    conditional: unmet > 0,
    unmet,
    met: golive.conditions.length - unmet,
    total: golive.conditions.length,
    toConfirm,
  };
}

export function contractEnd(model) {
  const dates = model.finance.contract.period.match(/\d{4}-\d{2}-\d{2}/g) || [];
  return dates.length ? dates[dates.length - 1] : "";
}

export function invoiceRows(model) {
  return model.finance.invoices.map((invoice) => ({
    id: invoice.id,
    amount: invoice.amount,
    href: invoiceHref(model, invoice),
    segments: invoice.lines.map((line) => invoiceSegment(invoice, line)),
  }));
}

function invoiceHref(model, invoice) {
  const ref = invoice.refs[0];
  const source = ref && model.sourceById.get(ref.source);
  return source ? href(`#/explorer/sources/${encodeURIComponent(source.id)}`) : "";
}

function invoiceSegment(invoice, line) {
  const className = line.unauthorized ? "fill-unauthorized" : invoice.paid ? "fill-paid" : "fill-pending";
  return {
    amount: line.amount,
    className,
    label: `${Math.round(line.amount / 1000)} k$`,
    showLabel: !line.unauthorized,
    labelClass: invoice.paid && !line.unauthorized ? "is-light" : "",
    tip: [
      `${line.amount.toLocaleString("fr-CA")} $`,
      line.label,
      `${invoice.id} · ${shortStatus(invoice.status)}`,
      line.unauthorized ? invoice.issue : "",
    ],
  };
}

export function invoiceLegend() {
  return [
    { className: "fill-paid", label: "Payée" },
    { className: "fill-pending", label: "En validation" },
    { className: "fill-unauthorized", label: "Non autorisée" },
  ];
}

function orderedValues(values, order) {
  return [...new Set(values.filter(Boolean))].sort(
    (left, right) => order.indexOf(normalize(left)) - order.indexOf(normalize(right)),
  );
}

export function trendGlyph(trend) {
  const value = normalize(trend);
  return TREND_GLYPHS.find(([pattern]) => pattern.test(value))?.[1] || "";
}

export function isClosedRisk(risk) {
  return /^ferm|^clos/i.test(normalize(risk.registerStatus)) || /^clos/.test(normalize(risk.trend));
}

export function isOffRegister(risk) {
  return /absent/.test(normalize(risk.registerStatus));
}

export function riskMatrixData(model) {
  const placed = model.risks.filter((risk) => risk.probability && risk.impact);
  return {
    probabilities: orderedValues(
      placed.map((risk) => risk.probability),
      PROBABILITY_ORDER,
    ),
    impacts: orderedValues(
      placed.map((risk) => risk.impact),
      IMPACT_ORDER,
    ),
    risks: placed.map((risk) => ({
      ...risk,
      closed: isClosedRisk(risk),
      trendGlyph: trendGlyph(risk.trend),
      href: href(`#/suivi/${risk.id}`),
    })),
    offRegister: model.risks.filter(isOffRegister),
  };
}

export function riskSeverity(risk) {
  const probability = PROBABILITY_ORDER.length - PROBABILITY_ORDER.indexOf(normalize(risk.probability));
  const impact = IMPACT_ORDER.indexOf(normalize(risk.impact)) + 1;
  return probability > PROBABILITY_ORDER.length || impact < 1 ? 0 : probability * impact;
}

export function eventDayHref(event) {
  return href(`#/historique/${event.day || "non-date"}`);
}

export function plural(count, singular, pluralForm = `${singular}s`) {
  return `${count} ${count > 1 ? pluralForm : singular}`;
}

export function multiline(value) {
  return raw(
    String(value ?? "")
      .split("\n")
      .map((line) => line.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`))
      .join("<br>"),
  );
}

export function criterionLabel(criterion) {
  if (criterion.startsWith("auto")) return "autorité";
  if (criterion.startsWith("date")) return "date des faits";
  if (criterion.includes("deux")) return "autorité et date";
  return criterion || "non documenté";
}

export function printHeader(model, title) {
  return html`<div class="print-only print-header">
    NOVA · ${title} · v${model.version.n} · état au ${formatDateTime(model.asOf)}
  </div>`;
}

export function mountPrintButton() {
  const slot = document.getElementById("subtabs-extra");
  if (!slot) return;
  mount(
    slot,
    html`<button type="button" class="btn btn-secondary btn-sm" data-action="print">
      ${icon("print")}Imprimer
    </button>`,
  );
  slot.querySelector("[data-action='print']").addEventListener("click", () => window.print());
}

export function statTile(label, value, detail = "") {
  return html`<div class="stat">
    <span class="stat-label">${label}</span>
    <span class="stat-value">${value}</span>
    ${detail ? html`<span class="stat-detail">${detail}</span>` : ""}
  </div>`;
}

export function budgetSegments(totals) {
  const eligiblePending = Math.max(0, (totals.pending ?? 0) - (totals.disputed ?? 0));
  return [
    { amount: totals.paid ?? 0, className: "fill-paid", label: "Payé" },
    { amount: eligiblePending, className: "fill-pending", label: "En validation, admissible" },
    { amount: totals.disputed ?? 0, className: "fill-unauthorized", label: "Facturé non autorisé" },
    {
      amount: Math.max(0, (totals.authorized ?? 0) - (totals.billed ?? 0)),
      className: "fill-track",
      label: "Autorisé non facturé",
    },
  ];
}

const personPatterns = new WeakMap();

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function personPattern(model) {
  if (!personPatterns.has(model.people)) {
    const entries = model.people
      .filter((person) => person.name && person.role && !/[(/]/.test(person.name))
      .map((person) => ({
        label: person.name.replace(/\s+Inc\.?$/i, ""),
        tip: `${person.name}\n${person.role}`,
      }))
      .sort((left, right) => right.label.length - left.label.length);
    const tips = new Map(entries.map((entry) => [entry.label, entry.tip]));
    const pattern = entries.length
      ? new RegExp(entries.map((entry) => escapeRegExp(entry.label)).join("|"), "g")
      : null;
    personPatterns.set(model.people, { pattern, tips });
  }
  return personPatterns.get(model.people);
}

export function people(model, value) {
  const textValue = String(value ?? "");
  const { pattern, tips } = personPattern(model);
  if (!pattern || !textValue) return textValue;
  const parts = [];
  let last = 0;
  for (const match of textValue.matchAll(pattern)) {
    parts.push(textValue.slice(last, match.index));
    parts.push(html`<span class="person" data-tip="${tips.get(match[0])}">${match[0]}</span>`);
    last = match.index + match[0].length;
  }
  parts.push(textValue.slice(last));
  return parts;
}
