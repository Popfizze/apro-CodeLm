import { invoiceChart, legend } from "../charts.js";
import { findSource } from "../data.js";
import { sourceChips } from "../refs.js";
import { card, formatMoney, html, normalize } from "../ui.js";
import { chartHost, mountPrintButton, printHeader } from "../views.js";

const MISSING = "non documenté au corpus";

function isPaid(status) {
  return /pay[ée]e/i.test(status) && !/non pay/i.test(status);
}

function sum(list, pick) {
  return list.reduce((total, entry) => total + pick(entry), 0);
}

function novaFigures(model) {
  const invoices = model.finance.invoices;
  return {
    name: model.project.split(" ")[0] || "NOVA",
    invoices: invoices.length,
    billed: sum(invoices, (invoice) => invoice.amount),
    paid: sum(
      invoices.filter((invoice) => isPaid(invoice.status)),
      (invoice) => invoice.amount,
    ),
    authorized: model.finance.totals.authorized,
    decisions: model.decisions.length,
    contradictions: model.contradictions.length,
    refs: model.finance.invoices.flatMap((invoice) => invoice.refs.slice(0, 1)),
  };
}

function otherProjects(model) {
  const byProject = new Map();
  model.finance.external.forEach((invoice) => {
    const key = invoice.project || MISSING;
    byProject.set(key, [...(byProject.get(key) || []), invoice]);
  });
  return [...byProject.entries()].map(([name, invoices]) => ({
    name,
    invoices: invoices.length,
    billed: sum(invoices, (invoice) => invoice.amount),
    paid: sum(
      invoices.filter((invoice) => isPaid(invoice.status)),
      (invoice) => invoice.amount,
    ),
    authorized: null,
    decisions: null,
    contradictions: null,
    refs: invoices.flatMap((invoice) => invoice.refs),
    notes: invoices.map((invoice) => invoice.note).filter(Boolean),
    summaries: invoices.map((invoice) => findSource(model, invoice.refs[0]?.source)?.summary).filter(Boolean),
  }));
}

function cell(value, format = (entry) => entry) {
  return value == null ? html`<span class="is-missing">${MISSING}</span>` : format(value);
}

function comparisonTable(model, projects) {
  const rows = [
    ["Factures au corpus", (project) => cell(project.invoices)],
    ["Facturé", (project) => cell(project.billed, formatMoney)],
    ["Payé", (project) => cell(project.paid, formatMoney)],
    ["En validation", (project) => cell(project.billed - project.paid, formatMoney)],
    ["Montant autorisé", (project) => cell(project.authorized, formatMoney)],
    ["Décisions documentées", (project) => cell(project.decisions)],
    ["Contradictions résolues", (project) => cell(project.contradictions)],
    ["Sources", (project) => sourceChips(model, project.refs, { max: 30 })],
  ];
  return html`<table class="data-table">
      <thead>
        <tr>
          <th></th>
          ${projects.map((project) => html`<th>${project.name}</th>`)}
        </tr>
      </thead>
      <tbody>
        ${rows.map(
          ([label, render]) =>
            html`<tr>
              <th scope="row">${label}</th>
              ${projects.map((project) => html`<td>${render(project)}</td>`)}
            </tr>`,
        )}
      </tbody>
    </table>
    ${projects
      .filter((project) => project.notes?.length || project.summaries?.length)
      .map(
        (project) =>
          html`<p class="muted">
            <b>${project.name}</b> · ${[...project.notes, ...project.summaries].join(" · ")}
          </p>`,
      )}`;
}

function projectBars(projects) {
  return projects.map((project) => ({
    id: project.name,
    amount: project.billed,
    href: "",
    segments: [
      {
        amount: project.paid,
        className: "fill-paid",
        label: "",
        tip: [formatMoney(project.paid), `${project.name} · payé`],
      },
      {
        amount: project.billed - project.paid,
        className: "fill-pending",
        label: "",
        tip: [formatMoney(project.billed - project.paid), `${project.name} · en validation`],
      },
    ].filter((segment) => segment.amount > 0),
  }));
}

function listCard(title, items, span) {
  return card({
    title,
    span,
    body: html`<ol class="plain-list numbered">
      ${items.map((item) => html`<li>${item}</li>`)}
    </ol>`,
  });
}

export function render({ model }) {
  const projects = [
    novaFigures(model),
    ...otherProjects(model).filter((project) => normalize(project.name) !== "nova"),
  ];
  const bars = projectBars(projects);
  return {
    className: "is-report",
    body: html`${printHeader(model, "Portefeuille")}
      <div class="grid report">
        ${card({ title: "Comparaison des projets", span: 7, body: comparisonTable(model, projects) })}
        <div class="span-5 stack">
          ${card({
            title: "Facturé par projet",
            extra: legend([
              { className: "fill-paid", label: "Payé" },
              { className: "fill-pending", label: "En validation" },
            ]),
            body: chartHost("projects", "is-fill"),
          })}
          ${listCard(
            "Règles réutilisables",
            model.rules.map((rule) => html`<b>${rule.id}</b> ${rule.text}`),
          )}
        </div>
        ${listCard(
          "Conditions de mise en production types",
          model.golive.conditions.map(
            (condition) => html`${condition.text} <span class="muted">· ${condition.validator}</span>`,
          ),
          6,
        )}
        ${listCard(
          "Étapes du runbook",
          (model.golive.runbook?.steps || []).map((step) => step.label),
          6,
        )}
      </div>`,
    charts: {
      projects: (width, available) =>
        invoiceChart({
          width,
          available,
          invoices: bars,
          maxAmount: Math.max(...bars.map((bar) => bar.amount), 1),
          step: 50000,
        }),
    },
    bind: mountPrintButton,
  };
}
