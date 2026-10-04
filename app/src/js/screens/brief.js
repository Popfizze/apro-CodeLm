import { budgetMeter, invoiceChart, legend } from "../charts.js";
import { badge, card, formatLongDay, formatMoney, html } from "../ui.js";
import {
  actionById,
  budgetSegments,
  chartHost,
  dueBadge,
  goliveSummary,
  invoiceLegend,
  invoiceRows,
  mountPrintButton,
  people,
  printHeader,
  statTile,
} from "../views.js";

function ownerTile(model) {
  const sentence = model.brief.owner
    .split("(")[0]
    .trim()
    .replace(/[.;,]$/, "");
  const [name, ...rest] = sentence.split(",");
  return statTile("Responsable", name || "non documenté", rest.join(",").trim());
}

function goliveTile(model) {
  const summary = goliveSummary(model);
  return statTile(
    "Mise en production",
    summary.date ? formatLongDay(summary.date) : "à confirmer",
    html`${summary.conditional ? badge("conditionnelle", "warning") : ""} ${summary.met}/${summary.total}
    conditions remplies`,
  );
}

function invoicesTile(model) {
  const totals = model.finance.totals;
  return statTile(
    "Factures",
    `${formatMoney(totals.paid)} payés`,
    `${formatMoney(totals.pending)} en validation`,
  );
}

function conditionsTable(model) {
  return html`<table class="data-table is-compact">
    <thead>
      <tr>
        <th>Condition</th>
        <th>Validation</th>
        <th>Actions</th>
        <th>Échéance</th>
      </tr>
    </thead>
    <tbody>
      ${model.golive.conditions.map(
        (condition) =>
          html`<tr>
            <td><b>${condition.id}</b> ${condition.text}</td>
            <td>${people(model, condition.validator)}</td>
            <td>
              ${condition.actionIds.map((id) => html`<div><b>${id}</b> ${people(model, actionById(model, id)?.owner.split("(")[0].trim() || "")}</div>`)}
            </td>
            <td>${dueBadge(condition.due)}</td>
          </tr>`,
      )}
    </tbody>
  </table>`;
}

function textBlock(value) {
  return html`<p>${value || "non documenté"}</p>`;
}

export function render({ model }) {
  const totals = model.finance.totals;
  const invoices = invoiceRows(model);
  return {
    className: "is-report",
    body: html`${printHeader(model, "Brief de reprise")}
      <div class="grid report brief">
        <section class="card span-3 tile-card">${ownerTile(model)}</section>
        <section class="card span-3 tile-card">${goliveTile(model)}</section>
        <section class="card span-3 tile-card">
          ${statTile("Autorisé", formatMoney(totals.authorized), "montant contractuel autorisé")}
        </section>
        <section class="card span-3 tile-card">${invoicesTile(model)}</section>
        ${card({ title: "Date approuvée et conditions", span: 7, body: html`${textBlock(model.brief.dateAndConditions)}${conditionsTable(model)}` })}
        ${card({
          title: "Priorités",
          span: 5,
          body: html`<ol class="priorities">
            ${model.brief.priorities.map((item) => html`<li>${item.replace(/^\d+\.\s*/, "")}</li>`)}
          </ol>`,
        })}
        ${card({ title: "Portée", span: 4, body: textBlock(model.brief.scope) })}
        ${card({
          title: "Budget",
          span: 4,
          body: html`${textBlock(model.brief.budget)}${budgetMeter(budgetSegments(totals), Math.max(totals.authorized ?? 0, totals.billed ?? 0) || 1)}
          ${legend([
            { className: "fill-paid", label: "Payé" },
            { className: "fill-pending", label: "En validation" },
            { className: "fill-unauthorized", label: "Non autorisé" },
            { className: "fill-track", label: "Non facturé" },
          ])}`,
        })}
        ${card({ title: "Situation des factures", span: 4, body: html`${textBlock(model.brief.invoices)}${legend(invoiceLegend())}${chartHost("invoices", "is-mini")}` })}
      </div>`,
    charts: {
      invoices: (width) =>
        invoiceChart({
          width,
          invoices,
          maxAmount: Math.max(...invoices.map((invoice) => invoice.amount), 1),
          step: 20000,
        }),
    },
    bind: mountPrintButton,
  };
}
