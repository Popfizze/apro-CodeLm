import { dumbbellChart, legend } from "../charts.js";
import { sourceChips } from "../refs.js";
import { href } from "../router.js";
import { badge, card, html, valueOr } from "../ui.js";
import { chartHost, mountPrintButton, people, printHeader, subjectTag } from "../views.js";

function isoDays(value) {
  return String(value || "").match(/\d{4}-\d{2}-\d{2}/g) || [];
}

function decidedRange(decision) {
  const days = isoDays(decision.decidedOn);
  if (/^entre/i.test(decision.decidedOn.trim()) && days.length > 1) return days.slice(0, 2);
  return days.slice(0, 1);
}

function isCurrent(decision) {
  return /^actuelle/i.test(decision.status.trim());
}

function dumbbellRows(model) {
  return model.decisions
    .map((decision) => ({
      id: decision.id,
      statement: decision.statement,
      proposedDay: isoDays(decision.proposedOn)[0] || null,
      decidedRange: decidedRange(decision),
      proposedLabel: `${decision.proposedBy || "non documenté"}, ${decision.proposedOn || "non documentée"}`,
      decidedLabel: `${decision.decidedBy || "non documenté"}, ${decision.decidedOn || "non documentée"}`,
      status: decision.status,
      current: isCurrent(decision),
      href: href(`#/rapports/dossier/${decision.id}`),
    }))
    .filter((row) => row.decidedRange.length)
    .sort((left, right) => left.decidedRange[0].localeCompare(right.decidedRange[0]));
}

function timeBounds(rows) {
  const days = rows
    .flatMap((row) => [row.proposedDay, ...row.decidedRange])
    .filter(Boolean)
    .sort();
  const first = days[0];
  const last = days[days.length - 1];
  return { start: `${first.slice(0, 7)}-01`, end: last };
}

function statusBadge(decision) {
  if (isCurrent(decision)) return badge("en vigueur", "info", decision.status);
  return badge(decision.status.split(/[(;]/)[0].trim() || "non documenté", "neutral", decision.status);
}

function decisionCard(model, decision, targetId) {
  return html`<article
    class="card decision-card span-6 ${decision.id === targetId ? "is-target" : ""}"
    id="${decision.id}"
  >
    <header class="decision-head">
      <b>${decision.id}</b> ${subjectTag(model, decision.subjectId)} ${statusBadge(decision)}
    </header>
    <p class="decision-statement">${decision.statement}</p>
    <div class="flow">
      <div>
        <span class="muted">Proposée</span
        ><b>${decision.proposedBy ? people(model, decision.proposedBy) : valueOr("")}</b
        ><span>${valueOr(decision.proposedOn, "non documentée")}</span>
      </div>
      <span class="flow-arrow">→</span>
      <div>
        <span class="muted">Décidée</span
        ><b>${decision.decidedBy ? people(model, decision.decidedBy) : valueOr("")}</b
        ><span>${valueOr(decision.decidedOn, "non documentée")}</span>
      </div>
    </div>
    ${decision.rationale ? html`<p>${decision.rationale}</p>` : ""} ${sourceChips(model, decision.refs)}
  </article>`;
}

function scrollToDecision(root, targetId) {
  const element = targetId && root.querySelector(`[id="${CSS.escape(targetId)}"]`);
  if (element) requestAnimationFrame(() => element.scrollIntoView({ block: "start" }));
}

export function render({ model, params }) {
  const rows = dumbbellRows(model);
  const bounds = rows.length ? timeBounds(rows) : null;
  const targetId = params.decisionId || "";
  return {
    className: "is-report",
    keepScroll: true,
    body: html`${printHeader(model, "Dossier décisions et preuves")}
      <div class="grid report">
        ${card({
          title: "Proposition puis décision",
          extra: legend([
            { className: "dot-open", label: "Proposée" },
            { className: "dot-current", label: "Décidée, en vigueur" },
            { className: "dot-past", label: "Décidée, remplacée ou complétée" },
          ]),
          body: chartHost("dumbbell"),
        })}
        ${model.decisions.map((decision) => decisionCard(model, decision, targetId))}
      </div>`,
    charts: bounds ? { dumbbell: (width) => dumbbellChart({ width, rows, ...bounds }) } : {},
    bind: (root) => {
      mountPrintButton();
      scrollToDecision(root, targetId);
    },
  };
}
