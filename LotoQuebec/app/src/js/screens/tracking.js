import { ownerBars, legend } from "../charts.js";
import {
  actionTone,
  findSource,
  isOpenAction,
  personNames,
  subjectForStateKey,
  subjectName,
} from "../data.js";
import { documentHref, resolveRef, sourceChips } from "../refs.js";
import { href } from "../router.js";
import { badge, card, formatDateTime, html, icon, tag, typeIcon } from "../ui.js";
import { currentStatement, diffSubjects, previousVersion } from "../versions.js";
import {
  actionById,
  chartHost,
  dueBadge,
  isClosedRisk,
  isOffRegister,
  ownerStatusBadge,
  people,
  plural,
  reviewBadge,
  statusBadge,
  typeBadge,
} from "../views.js";

function splitOwners(owner, names) {
  const parts = owner.split(/\s*\/\s*|\s+avec\s+/i);
  const found = new Set();
  parts.forEach((part) => {
    const matched = names.filter((name) => part.includes(name));
    if (matched.length) matched.forEach((name) => found.add(name));
    else if (part.trim()) found.add(part.split("(")[0].trim());
  });
  return [...found];
}

function ownerRows(model) {
  const names = personNames(model);
  const counts = new Map();
  model.actions.filter(isOpenAction).forEach((action) => {
    splitOwners(action.owner, names).forEach((name) => {
      const entry = counts.get(name) || { label: name, documented: [], recommended: [] };
      (action.type === "engagement_documente" ? entry.documented : entry.recommended).push(action.id);
      counts.set(name, entry);
    });
  });
  return [...counts.values()]
    .map((entry) => ({ ...entry, total: entry.documented.length + entry.recommended.length }))
    .sort((left, right) => right.total - left.total || left.label.localeCompare(right.label));
}

function ownerChartRows(model) {
  return ownerRows(model).map((row) => ({
    label: row.label,
    total: row.total,
    href: href(`#/suivi/responsable:${encodeURIComponent(row.label)}`),
    segments: [
      {
        amount: row.documented.length,
        className: "fill-commitment",
        tip: [`${row.documented.length}`, "Engagement documenté", row.documented.join(", ")],
        showLabel: false,
      },
      {
        amount: row.recommended.length,
        className: "fill-recommendation",
        tip: [`${row.recommended.length}`, "Recommandation de l'équipe", row.recommended.join(", ")],
        showLabel: false,
      },
    ].filter((segment) => segment.amount > 0),
  }));
}

function laneNode(model, action, targetId) {
  const tone = actionTone(action.status);
  return html`<a
    class="lane-node ${action.id === targetId ? "is-target" : ""}"
    href="${href(`#/suivi/${action.id}`)}"
  >
    <span class="lane-node-head"><b>${action.id}</b>${statusBadge(action.status)}</span>
    <span class="lane-node-text">${action.text}</span>
    <span class="lane-node-meta"
      >${people(model, action.owner.split("(")[0].trim())} ${ownerStatusBadge(action.ownerStatus)}</span
    >
    <span class="lane-node-meta">${dueBadge(action.due)}</span>
    <span class="visually-hidden">${tone}</span>
  </a>`;
}

function actionDetail(model, action) {
  return html`<div class="lane-detail">
    <div><span class="muted">Statut</span> ${action.status}</div>
    <div><span class="muted">Échéance</span> ${action.due || "à confirmer"}</div>
    <div>
      <span class="muted">Type</span> ${typeBadge(action.type)} ·
      <span class="muted">Responsable</span> ${people(model, action.owner)}
      ${ownerStatusBadge(action.ownerStatus)}
    </div>
    <div><span class="muted">Preuve</span> ${sourceChips(model, action.refs, { max: 90 })}</div>
  </div>`;
}

function runbookBar(model) {
  const runbook = model.golive.runbook;
  if (!runbook?.steps.length) return "";
  const source = findSource(model, runbook.sourceKey);
  const tone = (status) => (/^ok/i.test(status) ? "positive" : /todo/i.test(status) ? "critical" : "warning");
  return html`<div class="runbook">
    <div class="runbook-head">
      <span class="muted">Runbook · ${runbook.version}</span>
      ${source ? html`<a href="${documentHref(source.id)}">${typeIcon("image")} ${source.file}</a>` : ""}
    </div>
    <div class="runbook-steps">
      ${runbook.steps.map(
        (step) =>
          html`<a
            class="runbook-step is-${tone(step.status)}"
            href="${source ? documentHref(source.id) : href("#/suivi")}"
            title="${step.label} · ${step.status}"
          >
            <span>${step.n}. ${step.label}</span>${badge(step.status, tone(step.status))}
          </a>`,
      )}
    </div>
    ${runbook.extraRequirement ? html`<p class="muted">${runbook.extraRequirement}</p>` : ""}
  </div>`;
}

function lane(model, condition, targetId) {
  const actions = condition.actionIds.map((id) => actionById(model, id)).filter(Boolean);
  const target = actions.find((action) => action.id === targetId);
  return html`<div class="lane ${condition.id === targetId ? "is-target" : ""}" id="${condition.id}">
    <div class="lane-head">
      <div class="lane-title">
        <span class="tag is-condition">${condition.id}</span>${reviewBadge(model, condition.subjectId)}
      </div>
      <p class="lane-condition">${condition.text}</p>
      ${badge(condition.unmet ? "NON remplie" : condition.state.split("—")[0], condition.unmet ? "critical" : "positive", condition.state)}
      <p class="muted">Validation : ${people(model, condition.validator)}</p>
    </div>
    <div class="lane-body">
      <div class="lane-chain">
        ${actions.map((action) => laneNode(model, action, targetId))}
        <div class="lane-node is-final">
          <span class="muted">Validation</span
          ><b>${people(model, condition.validator)}</b>${condition.due ? dueBadge(condition.due) : ""}
        </div>
      </div>
      ${target ? actionDetail(model, target) : ""}
      ${condition.id === runbookConditionId(model) ? runbookBar(model) : ""}
    </div>
  </div>`;
}

function runbookConditionId(model) {
  const source = findSource(model, model.golive.runbook?.sourceKey);
  const condition =
    source && model.golive.conditions.find((entry) => source.subjectIds.includes(entry.subjectId));
  return condition ? condition.id : "";
}

function lanesCard(model, targetId) {
  return card({
    title: "Chemin vers la mise en production",
    body: html`<div class="lanes">
      ${model.golive.conditions.map((condition) => lane(model, condition, targetId))}
    </div>`,
  });
}

function ownersCard() {
  return card({
    title: "Actions ouvertes par responsable",
    extra: legend([
      { className: "fill-commitment", label: "Engagement documenté" },
      { className: "fill-recommendation", label: "Recommandation de l'équipe" },
    ]),
    body: chartHost("owners"),
  });
}

function actionRow(model, action, targetId) {
  const done = actionTone(action.status) === "positive";
  return html`<tr
    class="${done ? "is-done" : ""} ${action.id === targetId ? "is-target" : ""}"
    id="${action.id}"
  >
    <td><span class="mono">${action.id}</span> ${action.text}</td>
    <td>${people(model, action.owner)} ${ownerStatusBadge(action.ownerStatus)}</td>
    <td>${dueBadge(action.due)}</td>
    <td>${statusBadge(action.status)}</td>
    <td>${typeBadge(action.type)}</td>
    <td>${sourceChips(model, action.refs, { max: 36 })}</td>
  </tr>`;
}

function otherActions(model, owner) {
  const names = personNames(model);
  return model.actions
    .filter((action) => !action.condition)
    .filter((action) => !owner || splitOwners(action.owner, names).includes(owner))
    .sort(
      (left, right) =>
        Number(actionTone(left.status) === "positive") - Number(actionTone(right.status) === "positive"),
    );
}

function actionsCard(model, targetId, owner) {
  const chip = owner
    ? html`<a class="tag is-filter" href="${href("#/suivi")}">Responsable : ${owner} ${icon("close")}</a>`
    : "";
  return card({
    title: "Autres actions",
    extra: chip,
    id: "autres-actions",
    body: html`<table class="data-table actions-table">
      <thead>
        <tr>
          <th>Action</th>
          <th>Responsable</th>
          <th>Échéance</th>
          <th>Statut</th>
          <th>Type</th>
          <th>Preuve</th>
        </tr>
      </thead>
      <tbody>
        ${otherActions(model, owner).map((action) => actionRow(model, action, targetId))}
      </tbody>
    </table>`,
  });
}

function registerRef(risk) {
  const match = risk.registerRef.match(/^(\S+\.(?:xlsx|csv))\s+(.+?)(?:\s+\(|$)/i);
  return match ? { source: match[1], locator: match[2], quote: "", passageId: "" } : null;
}

function riskEvidence(model, risk) {
  const register = registerRef(risk);
  const registerSource = register ? resolveRef(model, register).source : null;
  const documents = risk.refs
    .map((ref) => findSource(model, ref.source))
    .filter((source) => source && source.id !== registerSource?.id);
  return html`${register && registerSource ? sourceChips(model, [register], { max: 28 }) : ""}
    <span class="doc-links">
      ${documents.map((source) => html`<a href="${documentHref(source.id)}">${source.file}</a>`)}
    </span>`;
}

function riskRow(model, risk, targetId) {
  return html`<tr
    class="${risk.id === targetId ? "is-target" : ""} ${isClosedRisk(risk) ? "is-done" : ""}"
    id="${risk.id}"
  >
    <td>
      <b>${risk.id}</b> ${isOffRegister(risk) ? badge("hors registre", "warning") : ""}
      ${reviewBadge(model, risk.subjectId)}
    </td>
    <td>${risk.statement}</td>
    <td>${risk.probability || risk.level}</td>
    <td>${risk.impact}</td>
    <td>${people(model, risk.owner)}</td>
    <td>${risk.registerStatus}</td>
    <td>${risk.actualState}</td>
    <td>${risk.trend}</td>
    <td>${riskEvidence(model, risk)}</td>
  </tr>`;
}

function risksCard(model, targetId) {
  return card({
    title: "Registre des risques",
    body: html`<table class="data-table risks-table">
      <thead>
        <tr>
          <th>Risque</th>
          <th>Énoncé</th>
          <th>Probabilité</th>
          <th>Impact</th>
          <th>Propriétaire</th>
          <th>Statut registre</th>
          <th>État réel</th>
          <th>Tendance</th>
          <th>Sources</th>
        </tr>
      </thead>
      <tbody>
        ${model.risks.map((risk) => riskRow(model, risk, targetId))}
      </tbody>
    </table>`,
  });
}

function missingCard(model) {
  const groups = model.subjects
    .map((subject) => ({ subject, entries: model.missing.filter((entry) => entry.subjectId === subject.id) }))
    .filter((group) => group.entries.length);
  return card({
    title: "Informations à obtenir",
    id: "informations",
    extra: html`<span class="muted">${plural(model.missing.length, "information")}</span>`,
    body: html`<div class="missing-columns">
      ${groups.map(
        (group) =>
          html`<div class="missing-group">
            <h3 class="block-title">${group.subject.name} ${reviewBadge(model, group.subject.id)}</h3>
            ${group.entries.map((entry) => html`<p class="missing-entry"><b>${entry.info}</b><span class="muted">Pour trancher : ${entry.toDecide}</span></p>`)}
          </div>`,
      )}
    </div>`,
  });
}

function snapshotBlock(model, snapshot, className = "") {
  if (!snapshot?.text) return html`<p class="muted">non documenté</p>`;
  const passage = model.passageById.get(snapshot.id);
  const source = passage ? model.sourceById.get(passage.sourceId) : null;
  return html`<div class="statement ${className}">
    <p>${snapshot.text}</p>
    ${
      source
        ? html`<a class="chip-src" href="${documentHref(source.id, [passage.id])}"
            >${icon("file")}<span>${source.file} · ${passage.displayLocator}</span></a
          >`
        : ""
    }
    ${snapshot.date ? html`<span class="muted">${formatDateTime(snapshot.date)}</span>` : ""}
  </div>`;
}

function newPassageBlock(model, passage) {
  return snapshotBlock(model, passage, "is-new");
}

function diffEntries(diff, subjectId) {
  return Object.entries(diff?.subjects || {}).filter(([key]) => subjectForStateKey(key) === subjectId);
}

function diffFacts(entries) {
  const superseded = entries.reduce((sum, [, entry]) => sum + (entry.newly_superseded?.length || 0), 0);
  const contradictions = entries.reduce((sum, [, entry]) => sum + (entry.new_contradictions?.length || 0), 0);
  const changed = entries.some(([, entry]) => entry.current_changed);
  return html`${changed ? badge("énoncé courant modifié", "warning") : badge("énoncé courant inchangé", "neutral")}
  ${superseded ? tag(plural(superseded, "énoncé remplacé", "énoncés remplacés")) : ""}
  ${contradictions ? tag(plural(contradictions, "nouvelle contradiction", "nouvelles contradictions")) : ""}`;
}

function beforeAfter(model, base, subject) {
  const entries = diffEntries(model.changes.diff, subject.id);
  if (entries.length) {
    return {
      before: entries.map(([, entry]) => snapshotBlock(model, entry.current_v1)),
      after: html`${diffFacts(entries)}${entries.map(([, entry]) => snapshotBlock(model, entry.current_v2, "is-new"))}`,
    };
  }
  return {
    before: currentStatement(base, subject.id).map((statement) => snapshotBlock(model, statement.current)),
    after: subject.passages.map((passage) => newPassageBlock(model, passage)),
  };
}

function changedSubject(model, base, subject) {
  const { before, after } = beforeAfter(model, base, subject);
  return html`<div class="change-row">
    <h3 class="block-title">${subjectName(model, subject.id)} ${badge("à revoir", "warning")}</h3>
    <div class="change-cols">
      <div><span class="col-label">Avant (v${subject.previous})</span>${before}</div>
      <div><span class="col-label">Après (v${model.version.n})</span>${after}</div>
    </div>
  </div>`;
}

function touchedItems(model, subjects) {
  const touched = (subjectId) => subjects.has(subjectId);
  const conditionSubject = (action) =>
    model.golive.conditions.find((condition) => condition.id === action.condition)?.subjectId;
  return [
    ...model.golive.conditions
      .filter((condition) => touched(condition.subjectId))
      .map((condition) => ({ id: condition.id, label: condition.text, href: `#/suivi/${condition.id}` })),
    ...model.actions
      .filter((action) => touched(conditionSubject(action)))
      .map((action) => ({ id: action.id, label: action.text, href: `#/suivi/${action.id}` })),
    ...model.risks
      .filter((risk) => touched(risk.subjectId))
      .map((risk) => ({ id: risk.id, label: risk.statement, href: `#/suivi/${risk.id}` })),
    ...model.decisions
      .filter((decision) => touched(decision.subjectId))
      .map((decision) => ({
        id: decision.id,
        label: decision.statement,
        href: `#/rapports/dossier/${decision.id}`,
      })),
  ];
}

function changedSubjects(model) {
  const changes = model.changes;
  const ids = new Set([...changes.subjects.keys(), ...diffSubjects(changes.diff)]);
  return [...ids].map((id) => ({ id, passages: changes.subjects.get(id) || [] }));
}

function touchedList(model, subjects) {
  return html`<ul class="plain-list">
    ${touchedItems(model, subjects).map(
      (item) =>
        html`<li>
          <a href="${href(item.href)}"><b>${item.id}</b> ${item.label}</a> ${badge("à revoir", "warning")}
        </li>`,
    )}
  </ul>`;
}

function changesCard(model, base) {
  const previous = previousVersion(model);
  if (!model.changes || !previous) return "";
  const subjects = changedSubjects(model).map((subject) => ({ ...subject, previous: previous.n }));
  const ids = new Set(subjects.map((subject) => subject.id));
  const unchanged = model.subjects.filter((subject) => subject.stateKeys.length && !ids.has(subject.id));
  const files = model.changes.sources.map(
    (source) => html`<a href="${documentHref(source.id)}">${source.file}</a>`,
  );
  return card({
    title: `Ce qui a changé · v${previous.n} → v${model.version.n}`,
    extra: html`<span class="muted"
      >${formatDateTime(model.version.importedAt || model.version.asOf)} · ${files}</span
    >`,
    className: "changes-card",
    body: html`${
        subjects.length
          ? subjects.map((subject) => changedSubject(model, base, subject))
          : html`<p class="muted">Aucun sujet du projet n'est relié aux passages importés.</p>`
      }
      <div class="change-cols">
        <div><span class="col-label">Éléments touchés</span>${touchedList(model, ids)}</div>
        <div>
          <span class="col-label">Inchangé</span>
          <p>${unchanged.map((subject) => tag(subject.name, "is-subject"))}</p>
        </div>
      </div>`,
  });
}

function scrollTarget(root, targetId) {
  const element = targetId && root.querySelector(`[id="${CSS.escape(targetId)}"]`);
  if (element) requestAnimationFrame(() => element.scrollIntoView({ block: "center" }));
}

function readTarget(params) {
  const value = params.itemId || "";
  if (!value.startsWith("responsable:")) return { targetId: value, owner: "" };
  return { targetId: "autres-actions", owner: value.slice("responsable:".length) };
}

export function render({ model, base, params }) {
  const { targetId, owner } = readTarget(params);
  return {
    keepScroll: true,
    body: html`<div class="grid tracking">
      ${changesCard(model, base)} ${lanesCard(model, targetId)} ${ownersCard()}
      ${actionsCard(model, targetId, owner)} ${risksCard(model, targetId)} ${missingCard(model)}
    </div>`,
    charts: { owners: (width) => ownerBars({ width, rows: ownerChartRows(model) }) },
    bind: (root) => scrollTarget(root, targetId),
  };
}
