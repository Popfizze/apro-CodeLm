import { chainChart, dotStrip, invoiceChart, legend, riskMatrix, windowChart } from "../charts.js";
import { NATURE_GROUPS, natureInfo, sourceTitle } from "../data.js";
import { sourceChips } from "../refs.js";
import { href } from "../router.js";
import {
  addDays,
  badge,
  card,
  icon,
  normalize,
  footerLink,
  formatDay,
  formatLongDay,
  html,
  isoDay,
  onDelegate,
} from "../ui.js";
import {
  chartHost,
  conditionChainRows,
  conditionTag,
  criterionLabel,
  contractEnd,
  dueBadge,
  goliveSummary,
  invoiceLegend,
  invoiceRows,
  ownerStatusBadge,
  people,
  plural,
  priorityActions,
  reviewBadge,
  riskMatrixData,
  subjectTag,
  typeBadge,
} from "../views.js";
import { presetEventFilter } from "./events.js";

const RECENT_DAYS = 10;
const NEXT_ACTIONS = 5;
const CONTRADICTION_ROWS = 4;
function currentDecisionRefs(model, needle, limit) {
  const wanted = normalize(needle);
  return model.decisions
    .filter(
      (decision) =>
        /^actuelle/i.test(decision.status.trim()) && normalize(decision.statement).includes(wanted),
    )
    .flatMap((decision) => decision.refs)
    .map((ref) => ({ ref, decisive: isDecisivePassage(model, ref.passageId) }))
    .sort((left, right) => Number(right.decisive) - Number(left.decisive))
    .slice(0, limit)
    .map((entry) => entry.ref);
}

function isDecisivePassage(model, passageId) {
  const nature = model.passageById.get(passageId)?.typed?.nature;
  return Boolean(nature) && natureInfo(nature).group === "decision";
}

function ownerLine(model) {
  const owner = model.brief.owner;
  if (!owner) return html`<span class="is-missing">Chargé de projet non documenté</span>`;
  const name = owner.split(",")[0].trim();
  return html`<span>${people(model, owner.split("(")[0].replace(/[.;,\s]+$/, ""))}</span
    >${sourceChips(model, currentDecisionRefs(model, name, 1), { max: 34 })}`;
}

function dateRefs(model) {
  const date = model.golive.targetDate;
  return date ? currentDecisionRefs(model, formatLongDay(date).replace(/\s\d{4}$/, ""), 2) : [];
}

function goliveCard(model) {
  const summary = goliveSummary(model);
  const reviewIds = model.golive.conditions.map((condition) => condition.subjectId);
  return card({
    title: "Mise en production",
    span: 7,
    className: "golive-card",
    extra: html`<span class="muted"
        >${summary.toConfirm}/${summary.total} échéances à confirmer · ${summary.met}/${summary.total}
        conditions remplies</span
      >${reviewBadge(model, reviewIds)}`,
    body: html`<div class="golive-head">
        <span class="hero-date">${summary.date ? formatLongDay(summary.date) : "à confirmer"}</span>
        ${summary.conditional ? badge("conditionnelle", "warning", `${summary.unmet} condition(s) non remplie(s)`) : ""}
        ${summary.daysLeft != null ? html`<span class="countdown">J-${summary.daysLeft}</span>` : ""}
      </div>
      <p class="authority-line">
        ${model.golive.dateStatus} ${sourceChips(model, dateRefs(model), { max: 34 })}
      </p>
      <p class="owner-line">${ownerLine(model)}</p>
      ${chartHost("window", "is-window")} ${chartHost("chains", "is-fill")}`,
  });
}

function actionRow(model, action) {
  return html`<a class="next-action" href="${href(`#/suivi/${action.id}`)}">
    <span class="next-action-text">${action.text}</span>
    <span class="next-action-meta">
      <span class="next-owner">${people(model, action.owner.split(/[(—]/)[0].trim())}</span
      >${ownerStatusBadge(action.ownerStatus)} ${dueBadge(action.due)} ${conditionTag(action.condition)}
      ${typeBadge(action.type)}
    </span>
  </a>`;
}

function nextActionsCard(model) {
  const open = priorityActions(model);
  return card({
    title: "Prochaines actions",
    span: 5,
    className: "is-inverted next-actions",
    body: html`<div class="next-list">
        ${open.slice(0, NEXT_ACTIONS).map((action) => actionRow(model, action))}
      </div>
      ${footerLink(href("#/suivi"), `${plural(open.length, "action ouverte", "actions ouvertes")} · Suivi`)}`,
  });
}

function offRegisterTags(data) {
  if (!data.offRegister.length) return "";
  return html`<span class="off-register">
    <span class="muted">Hors registre</span>
    ${data.offRegister.map(
      (risk) =>
        html`<a
          class="tag is-off"
          href="${href(`#/suivi/${risk.id}`)}"
          data-tip="${risk.id}
${risk.statement}"
          >${risk.id}</a
        >`,
    )}
  </span>`;
}

function risksCard(model) {
  return card({
    title: "Risques",
    span: 4,
    extra: offRegisterTags(riskMatrixData(model)),
    body: chartHost("risks", "is-fill"),
  });
}

function invoicesCard(model) {
  const unauthorized = model.finance.invoices.flatMap((invoice) =>
    invoice.lines.filter((line) => line.unauthorized),
  );
  const total = unauthorized.reduce((sum, line) => sum + line.amount, 0);
  return card({
    title: "Factures",
    span: 4,
    extra: total ? badge(`${total.toLocaleString("fr-CA")} $ non autorisés`, "critical") : "",
    body: html`${legend(invoiceLegend())}${chartHost("invoices", "is-fill")}`,
  });
}

function recentDays(model) {
  const end = isoDay(model.asOf);
  return Array.from({ length: RECENT_DAYS }, (_, index) => addDays(end, index - RECENT_DAYS));
}

function recentCard(model) {
  const days = recentDays(model);
  const count = model.events.filter((event) => days.includes(event.day)).length;
  return card({
    title: "Derniers faits",
    span: 4,
    extra: html`<span class="muted"
      >${plural(count, "événement")} · ${formatDay(days[0], { year: false })} →
      ${formatDay(days[days.length - 1], { year: false })}</span
    >`,
    body: html`${legend(NATURE_GROUPS.map((group) => ({ className: `fill-${group.id}`, label: group.label })))}${chartHost("recent", "is-fill")}`,
  });
}

function contradictionRow(model, contradiction) {
  return html`<a
    class="contradiction-row"
    href="${href(`#/historique/evenements/${contradiction.id}`)}"
    title="${contradiction.resolution}"
  >
    <span class="contradiction-a"
      ><span class="mark-no" aria-label="écartée">✕</span
      ><span class="ellipsis">${sourceTitle(model, contradiction.a.refs[0]?.source)}</span></span
    >
    <span class="contradiction-arrow">→</span>
    <span class="contradiction-b"
      ><span class="mark-yes" aria-label="prévaut">✓</span
      ><span class="ellipsis">${sourceTitle(model, contradiction.b.refs[0]?.source)}</span></span
    >
    ${badge(criterionLabel(contradiction.criterion), "info")}
  </a>`;
}

function contradictionsCard(model) {
  const sorted = [...model.contradictions].sort(
    (left, right) => Number(right.inPlanOrRegister) - Number(left.inPlanOrRegister),
  );
  const rows = Math.max(CONTRADICTION_ROWS, conditionMissing(model).length);
  return card({
    title: "Contradictions résolues",
    span: 6,
    extra: html`<a
      class="card-link"
      href="${href("#/historique/evenements")}"
      data-preset-type="contradiction"
      >${model.contradictions.length} contradictions · Événements ${icon("arrow")}</a
    >`,
    body: html`<div class="rows">
      ${sorted.slice(0, rows).map((entry) => contradictionRow(model, entry))}
    </div>`,
  });
}

function conditionMissing(model) {
  const subjects = model.golive.conditions.map((condition) => condition.subjectId);
  return model.missing.filter((entry) => subjects.includes(entry.subjectId));
}

function missingRow(model, entry) {
  return html`<div
    class="missing-row"
    data-tip="${entry.info}
Pour trancher : ${entry.toDecide}"
  >
    ${subjectTag(model, entry.subjectId)}
    <span class="ellipsis"
      ><b>${entry.info}</b> <span class="muted">Pour trancher : ${entry.toDecide}</span></span
    >
  </div>`;
}

function missingCard(model) {
  return card({
    title: "Informations manquantes liées aux conditions",
    span: 6,
    extra: html`<a class="card-link" href="${href("#/suivi/informations")}"
      >${model.missing.length} informations manquantes · Suivi ${icon("arrow")}</a
    >`,
    body: html`<div class="rows">${conditionMissing(model).map((entry) => missingRow(model, entry))}</div>`,
  });
}

function windowRefs(model) {
  const contract = model.finance.contract.refs[0];
  return { end: contract ? `${sourceTitle(model, contract.source)} · ${contract.locator}` : "" };
}

function recentData(model) {
  return recentDays(model).map((day) => ({
    day,
    href: href(`#/historique/${day}`),
    items: model.events
      .filter((event) => event.day === day)
      .sort((left, right) => (left.time || "").localeCompare(right.time || ""))
      .map((event) => ({
        className: `fill-${natureInfo(event.natureKey).group}`,
        time: event.time ? `${formatDay(day, { year: false })}, ${event.time}` : formatDay(day),
        label: natureInfo(event.natureKey).label,
        summary: event.summary,
        ref: event.refs[0] ? `${sourceTitle(model, event.refs[0].source)} · ${event.refs[0].locator}` : "",
      })),
  }));
}

function charts(model) {
  const invoices = invoiceRows(model);
  return {
    window: (width) =>
      windowChart({
        width,
        today: model.asOf,
        golive: model.golive.targetDate,
        contractEnd: contractEnd(model),
        refs: windowRefs(model),
      }),
    chains: (width, available) => chainChart({ width, rows: conditionChainRows(model), available }),
    risks: (width, available) => riskMatrix({ width, available, ...riskMatrixData(model) }),
    invoices: (width, available) =>
      invoiceChart({
        width,
        available,
        invoices,
        maxAmount: Math.max(...invoices.map((invoice) => invoice.amount), 1),
        step: 20000,
      }),
    recent: (width, available) =>
      dotStrip({ width, available, days: recentData(model), today: isoDay(model.asOf) }),
  };
}

export function render({ model }) {
  return {
    body: html`<div class="grid overview">
      ${goliveCard(model)} ${nextActionsCard(model)} ${risksCard(model)} ${invoicesCard(model)}
      ${recentCard(model)} ${contradictionsCard(model)} ${missingCard(model)}
    </div>`,
    charts: charts(model),
    bind: (root) =>
      onDelegate(root, "click", "[data-preset-type]", (_, link) =>
        presetEventFilter(link.dataset.presetType),
      ),
  };
}
