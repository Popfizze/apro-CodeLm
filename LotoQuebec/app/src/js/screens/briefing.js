import { chainChart, invoiceChart, legend } from "../charts.js";
import { sourceChips } from "../refs.js";
import { href } from "../router.js";
import { badge, card, formatDay, formatLongDay, formatMoney, html, isoDay } from "../ui.js";
import {
  chartHost,
  conditionChainRows,
  conditionTag,
  dueBadge,
  goliveSummary,
  invoiceLegend,
  invoiceRows,
  isClosedRisk,
  mountPrintButton,
  ownerStatusBadge,
  people,
  printHeader,
  priorityActions,
  riskSeverity,
  statTile,
  trendGlyph,
  typeBadge,
} from "../views.js";

const TOP_RISKS = 5;
const TOP_ACTIONS = 5;
const RECENT_DECISIONS = 4;

function unauthorizedInvoices(model) {
  return model.finance.invoices
    .filter((invoice) => invoice.lines.some((line) => line.unauthorized))
    .map((invoice) => invoice.id)
    .join(", ");
}

function verdictRow(model) {
  const summary = goliveSummary(model);
  const totals = model.finance.totals;
  return html`<section class="card span-12 verdict">
    ${statTile("Mise en production", summary.date ? formatLongDay(summary.date) : "à confirmer", summary.conditional ? badge("conditionnelle", "warning") : "")}
    ${statTile("Conditions", `${summary.met}/${summary.total} remplies`, summary.daysLeft != null ? `J-${summary.daysLeft}` : "")}
    ${statTile("Autorisé", formatMoney(totals.authorized), `Payé ${formatMoney(totals.paid)}`)}
    ${statTile("Facturé", formatMoney(totals.billed), `${formatMoney(totals.pending)} en validation`)}
    ${totals.disputed ? statTile("Non autorisé", formatMoney(totals.disputed), badge(unauthorizedInvoices(model), "critical")) : ""}
  </section>`;
}

function topRisks(model) {
  return model.risks
    .filter((risk) => !isClosedRisk(risk))
    .sort((left, right) => riskSeverity(right) - riskSeverity(left) || left.id.localeCompare(right.id))
    .slice(0, TOP_RISKS);
}

function risksCard(model) {
  return card({
    title: "Risques principaux",
    span: 6,
    body: html`<ul class="plain-list risk-list">
      ${topRisks(model).map(
        (risk) =>
          html`<li title="${risk.actualState}">
            <a href="${href(`#/suivi/${risk.id}`)}"><b>${risk.id}</b> ${risk.statement}</a>
            <span class="muted ellipsis"
              >${risk.level} · ${people(model, risk.owner)} · ${trendGlyph(risk.trend)} ${risk.trend}</span
            >
          </li>`,
      )}
    </ul>`,
  });
}

function actionsCard(model) {
  return card({
    title: "Actions prioritaires",
    span: 6,
    body: html`<ul class="plain-list">
      ${priorityActions(model)
        .slice(0, TOP_ACTIONS)
        .map(
          (action) =>
            html`<li>
              <a href="${href(`#/suivi/${action.id}`)}"><b>${action.id}</b> ${action.text}</a>
              <span class="row-meta"
                >${people(model, action.owner.split("(")[0].trim())} ${ownerStatusBadge(action.ownerStatus)}
                ${dueBadge(action.due)} ${conditionTag(action.condition)} ${typeBadge(action.type)}</span
              >
            </li>`,
        )}
    </ul>`,
  });
}

function decisionDay(decision) {
  return isoDay(decision.decidedOn) || (decision.decidedOn.match(/\d{4}-\d{2}-\d{2}/) || [""])[0];
}

function decisionsCard(model) {
  const recent = [...model.decisions]
    .sort((left, right) => decisionDay(right).localeCompare(decisionDay(left)))
    .slice(0, RECENT_DECISIONS);
  return card({
    title: "Décisions récentes",
    body: html`<div class="decision-strip">
      ${recent.map(
        (decision) =>
          html`<a class="decision-mini" href="${href(`#/rapports/dossier/${decision.id}`)}">
            <span class="muted"
              >${decisionDay(decision) ? formatDay(decisionDay(decision)) : decision.decidedOn} ·
              ${decision.id}</span
            >
            <b>${decision.statement}</b>
            <span class="muted">${people(model, decision.decidedBy)}</span>
            ${sourceChips(model, decision.refs.slice(0, 2), { max: 30 })}
          </a>`,
      )}
    </div>`,
  });
}

export function render({ model }) {
  const invoices = invoiceRows(model);
  return {
    className: "is-report",
    body: html`${printHeader(model, `Briefing exécutif — établi depuis l'état v${model.version.n}`)}
      <div class="grid report">
        ${verdictRow(model)}
        ${card({ title: "Conditions de mise en production", span: 6, body: chartHost("chains", "is-fill") })}
        ${risksCard(model)}
        ${card({ title: "Factures", span: 6, body: html`${legend(invoiceLegend())}${chartHost("invoices", "is-fill")}` })}
        ${actionsCard(model)} ${decisionsCard(model)}
      </div>`,
    charts: {
      chains: (width, available) =>
        chainChart({ width, rows: conditionChainRows(model), detail: true, available }),
      invoices: (width, available) =>
        invoiceChart({
          width,
          available,
          invoices,
          maxAmount: Math.max(...invoices.map((invoice) => invoice.amount), 1),
          step: 20000,
        }),
    },
    bind: mountPrintButton,
  };
}
