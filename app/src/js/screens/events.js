import { NATURE_GROUPS, natureInfo, subjectName } from "../data.js";
import { sourceChips } from "../refs.js";
import { href, navigate } from "../router.js";
import {
  badge,
  filterButton,
  formatDay,
  html,
  isoDay,
  mount,
  normalize,
  onDelegate,
  openPopover,
  searchField,
  valueOr,
} from "../ui.js";
import { criterionLabel, natureBadge, people, reviewBadge, shortSubject } from "../views.js";

const TYPES = [
  { id: "event", label: "Événement" },
  { id: "decision", label: "Décision" },
  { id: "contradiction", label: "Contradiction" },
  { id: "missing", label: "Information manquante" },
];

const state = {
  query: "",
  sort: { key: "date", direction: -1 },
  filters: { type: new Set(), subject: new Set(), nature: new Set(), status: new Set(), month: new Set() },
};

const COLUMNS = [
  { key: "typeLabel", label: "Type" },
  { key: "date", label: "Date" },
  { key: "subject", label: "Sujet" },
  { key: "statement", label: "Énoncé", sortable: false },
  { key: "status", label: "Statut" },
  { key: "sources", label: "Sources", sortable: false },
];

export function presetEventFilter(type) {
  Object.values(state.filters).forEach((set) => set.clear());
  state.query = "";
  if (type) state.filters.type.add(type);
}

function eventRow(model, event) {
  return {
    id: event.id,
    type: "event",
    date: event.day ? `${event.day}${event.time ? `T${event.time}` : ""}` : "",
    dateLabel: event.day ? `${formatDay(event.day)}${event.time ? `, ${event.time}` : ""}` : event.date,
    subjectId: event.subjectId,
    subject: subjectName(model, event.subjectId),
    statement: event.summary,
    nature: natureInfo(event.natureKey).group,
    natureKey: event.natureKey,
    status: event.status,
    refs: event.refs,
    extra: `${event.quote} ${event.actors.join(" ")}`,
    item: event,
  };
}

function decisionRow(model, decision) {
  const day = isoDay(decision.decidedOn) || (decision.decidedOn.match(/\d{4}-\d{2}-\d{2}/) || [""])[0];
  return {
    id: decision.id,
    type: "decision",
    date: day,
    dateLabel: day ? formatDay(day) : decision.decidedOn,
    subjectId: decision.subjectId,
    subject: subjectName(model, decision.subjectId),
    statement: decision.statement,
    status: decision.status,
    refs: decision.refs,
    extra: `${decision.rationale} ${decision.proposedBy} ${decision.decidedBy}`,
    item: decision,
  };
}

function contradictionRow(contradiction) {
  return {
    id: contradiction.id,
    type: "contradiction",
    date: "",
    dateLabel: "",
    subjectId: contradiction.subjectId,
    subject: contradiction.subject,
    statement: contradiction.resolution,
    status: criterionLabel(contradiction.criterion),
    refs: [...contradiction.a.refs, ...contradiction.b.refs],
    extra: "",
    item: contradiction,
  };
}

function missingRow(model, entry) {
  return {
    id: entry.id,
    type: "missing",
    date: "",
    dateLabel: "",
    subjectId: entry.subjectId,
    subject: subjectName(model, entry.subjectId),
    statement: entry.info,
    status: "manquante",
    refs: [],
    extra: entry.toDecide,
    item: entry,
  };
}

function allRows(model) {
  const rows = [
    ...model.events.map((event) => eventRow(model, event)),
    ...model.decisions.map((decision) => decisionRow(model, decision)),
    ...model.contradictions.map(contradictionRow),
    ...model.missing.map((entry) => missingRow(model, entry)),
  ];
  return rows.map((row) => ({
    ...row,
    typeLabel: TYPES.find((type) => type.id === row.type).label,
    month: row.date ? row.date.slice(0, 7) : "",
    haystack: normalize([row.id, row.dateLabel, row.subject, row.statement, row.status, row.extra].join(" ")),
  }));
}

function statusKey(row) {
  return normalize(row.status).split(/[\s,;(—–-]/)[0];
}

function matchesFilters(row) {
  const { type, subject, nature, status, month } = state.filters;
  if (type.size && !type.has(row.type)) return false;
  if (subject.size && !subject.has(row.subjectId)) return false;
  if (nature.size && !nature.has(row.nature)) return false;
  if (status.size && !status.has(statusKey(row))) return false;
  return !(month.size && !month.has(row.month));
}

function compareRows(left, right) {
  const { key, direction } = state.sort;
  const a = left[key] || "";
  const b = right[key] || "";
  if (a === b) return left.id.localeCompare(right.id);
  if (!a) return 1;
  if (!b) return -1;
  return String(a).localeCompare(String(b)) * direction;
}

function visibleRows(model) {
  const terms = normalize(state.query).split(/\s+/).filter(Boolean);
  return allRows(model)
    .filter((row) => terms.every((term) => row.haystack.includes(term)))
    .filter(matchesFilters)
    .sort(compareRows);
}

function statusCell(row) {
  if (row.type === "missing") return badge("manquante", "warning");
  if (row.type === "contradiction") return badge(row.status, "info");
  if (row.type === "decision")
    return html`<span title="${row.status}">${row.status.split(/[;(—]/)[0]}</span>`;
  return row.status;
}

function decisionDetail(model, decision) {
  return html`<div class="flow">
      <div>
        <span class="muted">Proposée</span
        ><b>${decision.proposedBy ? people(model, decision.proposedBy) : valueOr("")}</b
        ><span>${valueOr(decision.proposedOn)}</span>
      </div>
      <span class="flow-arrow">→</span>
      <div>
        <span class="muted">Décidée</span
        ><b>${decision.decidedBy ? people(model, decision.decidedBy) : valueOr("")}</b
        ><span>${valueOr(decision.decidedOn)}</span>
      </div>
    </div>
    <p>${decision.rationale}</p>`;
}

function contradictionDetail(model, contradiction) {
  const side = (version, mark, label) =>
    html`<div class="versus-side">
      <span class="${mark}">${label}</span>
      <span>${version.statement}</span>
      ${sourceChips(model, version.refs, { max: 120 })}
    </div>`;
  return html`<div class="versus">
      ${side(contradiction.a, "mark-no", contradiction.prevails === "A" ? "✓ prévaut" : "✕ écartée")}
      ${side(contradiction.b, "mark-yes", contradiction.prevails === "B" ? "✓ prévaut" : "✕ écartée")}
    </div>
    <p>${contradiction.resolution}</p>`;
}

function eventDetail(model, event) {
  const target = event.replacedBy ? model.events.find((entry) => entry.id === event.replacedBy) : null;
  return html`${event.quote ? html`<q class="quote">${event.quote}</q>` : ""}
  ${event.actors.length ? html`<p><span class="muted">Acteurs :</span> ${people(model, event.actors.join(", "))}</p>` : ""}
  ${target ? html`<p><span class="muted">Remplacé par :</span> <a href="${href(`#/historique/evenements/${target.id}`)}">${target.id}</a> ${target.summary}</p>` : ""}`;
}

function detail(model, row) {
  if (row.type === "decision") return decisionDetail(model, row.item);
  if (row.type === "contradiction") return contradictionDetail(model, row.item);
  if (row.type === "missing")
    return html`<p><span class="muted">Pour trancher :</span> ${row.item.toDecide}</p>`;
  return eventDetail(model, row.item);
}

function rowHtml(model, row, expandedId) {
  const expanded = row.id === expandedId;
  return html`<tr
      class="is-clickable ${expanded ? "is-expanded" : ""}"
      data-id="${row.id}"
      id="row-${row.id}"
      aria-expanded="${expanded}"
    >
      <td><span class="type-cell">${row.typeLabel}</span><span class="mono">${row.id}</span></td>
      <td class="date-cell">${row.dateLabel || html`<span class="muted">—</span>`}</td>
      <td title="${row.subject}">${shortSubject(row.subject)} ${reviewBadge(model, row.subjectId)}</td>
      <td>${row.statement} ${row.type === "event" ? natureBadge(row.natureKey) : ""}</td>
      <td>${statusCell(row)}</td>
      <td>${sourceChips(model, row.refs, { max: 40 })}</td>
    </tr>
    ${
      expanded
        ? html`<tr class="row-detail">
            <td colspan="6">${detail(model, row)}</td>
          </tr>`
        : ""
    }`;
}

function headerCell(column) {
  if (column.sortable === false) return html`<th scope="col">${column.label}</th>`;
  const active = state.sort.key === column.key;
  return html`<th
    scope="col"
    aria-sort="${active ? (state.sort.direction > 0 ? "ascending" : "descending") : "none"}"
  >
    <button type="button" class="sort-btn" data-sort="${column.key}">
      ${column.label}<span class="sort-glyph">${active ? (state.sort.direction > 0 ? "▲" : "▼") : ""}</span>
    </button>
  </th>`;
}

function optionGroup(title, name, options) {
  return html`<fieldset class="filter-group">
    <legend>${title}</legend>
    ${options.map(
      (option) =>
        html`<label class="check"
          ><input
            type="checkbox"
            name="${name}"
            value="${option.value}"
            ${state.filters[name].has(option.value) ? html`checked` : ""}
          />${option.label}</label
        >`,
    )}
  </fieldset>`;
}

function filterOptions(model) {
  const rows = allRows(model);
  const statuses = [...new Set(rows.map(statusKey).filter(Boolean))].sort();
  const months = [...new Set(rows.map((row) => row.month).filter(Boolean))].sort();
  return html`${optionGroup(
    "Type",
    "type",
    TYPES.map((type) => ({ value: type.id, label: type.label })),
  )}
  ${optionGroup(
    "Sujet",
    "subject",
    model.subjects.map((subject) => ({ value: subject.id, label: subject.name })),
  )}
  ${optionGroup(
    "Nature",
    "nature",
    NATURE_GROUPS.map((group) => ({ value: group.id, label: group.label })),
  )}
  ${optionGroup(
    "Statut",
    "status",
    statuses.map((value) => ({ value, label: value })),
  )}
  ${optionGroup(
    "Période",
    "month",
    months.map((value) => ({ value, label: formatDay(`${value}-01`).replace(/^1 /, "") })),
  )}`;
}

function filtersPanel(model) {
  return html`<form class="filters">
    <div class="filter-columns">${filterOptions(model)}</div>
    <div class="filter-actions">
      <button type="button" class="btn btn-tertiary btn-sm" data-action="reset">Réinitialiser</button>
    </div>
  </form>`;
}

function activeCount() {
  return Object.values(state.filters).reduce((sum, set) => sum + set.size, 0);
}

function refresh(root, model, expandedId) {
  mount(root.querySelector("thead tr"), COLUMNS.map(headerCell));
  mount(
    root.querySelector("tbody"),
    visibleRows(model).map((row) => rowHtml(model, row, expandedId)),
  );
  mount(root.querySelector(".filter-slot"), filterButton(activeCount()));
}

function bindFilters(panel, root, model, expandedId) {
  panel.addEventListener("change", (event) => {
    const set = state.filters[event.target.name];
    if (event.target.checked) set.add(event.target.value);
    else set.delete(event.target.value);
    refresh(root, model, expandedId);
  });
  onDelegate(panel, "click", "[data-action='reset']", () => {
    Object.values(state.filters).forEach((set) => set.clear());
    panel.querySelectorAll("input").forEach((input) => {
      input.checked = false;
    });
    refresh(root, model, expandedId);
  });
}

function bind(root, model, expandedId) {
  root.querySelector("#event-search").addEventListener("input", (event) => {
    state.query = event.target.value;
    refresh(root, model, expandedId);
  });
  onDelegate(root, "click", "[data-sort]", (_, button) => {
    const key = button.dataset.sort;
    state.sort = { key, direction: state.sort.key === key ? -state.sort.direction : key === "date" ? -1 : 1 };
    refresh(root, model, expandedId);
  });
  onDelegate(root, "click", "[data-action='toggle-filters']", (_, button) => {
    const panel = openPopover(button, filtersPanel(model), { className: "is-filters", align: "end" });
    if (panel) bindFilters(panel, root, model, expandedId);
  });
  onDelegate(root, "click", "tr[data-id]", (event, row) => {
    if (event.target.closest("a, button")) return;
    const id = row.dataset.id;
    navigate(
      id === expandedId ? "#/historique/evenements" : `#/historique/evenements/${encodeURIComponent(id)}`,
    );
  });
}

export function render({ model, params }) {
  const expandedId = params.itemId || "";
  return {
    keepScroll: true,
    body: html`<div class="toolbar">
        ${searchField({ id: "event-search", value: state.query, placeholder: "Rechercher un événement, une décision, une contradiction, une information manquante" })}
        <span class="filter-slot"></span>
      </div>
      <div class="table-card">
        <table class="data-table events-table">
          <thead>
            <tr></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>`,
    bind: (root) => {
      refresh(root, model, expandedId);
      bind(root, model, expandedId);
      const row = expandedId && root.querySelector(`[id="row-${CSS.escape(expandedId)}"]`);
      if (row) requestAnimationFrame(() => row.scrollIntoView({ block: "center" }));
    },
  };
}
