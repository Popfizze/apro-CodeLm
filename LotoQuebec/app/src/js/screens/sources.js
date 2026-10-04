import { typeLabel } from "../data.js";
import { documentHref } from "../refs.js";
import { navigate } from "../router.js";
import {
  badge,
  closePopover,
  filterButton,
  formatDay,
  html,
  isoDay,
  mount,
  normalize,
  onDelegate,
  openPopover,
  searchField,
} from "../ui.js";
import { subjectTag } from "../views.js";
import { authorityBadge } from "./ask.js";

const state = {
  query: "",
  sort: { key: "date", direction: -1 },
  filters: {
    type: new Set(),
    authority: new Set(),
    subject: new Set(),
    month: new Set(),
    duplicate: new Set(),
  },
};

const COLUMNS = [
  { key: "title", label: "Titre" },
  { key: "type", label: "Type" },
  { key: "date", label: "Date des faits" },
  { key: "author", label: "Auteur" },
  { key: "authority", label: "Autorité" },
  { key: "subjects", label: "Sujets", sortable: false },
  { key: "passages", label: "Passages" },
  { key: "duplicate", label: "Doublon" },
];

const AUTHORITY_RANK = { haute: 4, moyenne: 3, faible: 2, bruit: 1 };

function firstIsoDay(value) {
  return isoDay(value) || (String(value).match(/\d{4}-\d{2}-\d{2}/) || [null])[0];
}

function monthKey(source) {
  const day = firstIsoDay(source.date) || (String(source.date).match(/^\d{4}-\d{2}/) || [""])[0];
  return day ? day.slice(0, 7) : "non daté";
}

function monthLabel(key) {
  if (key === "non daté") return key;
  return formatDay(`${key}-01`).replace(/^1 /, "");
}

function isDuplicate(source) {
  return Boolean(source.duplicateOf || source.attachments.some((attachment) => attachment.sameAs));
}

function rowsOf(model) {
  return model.sources.map((source) => ({
    source,
    title: source.title,
    type: source.type,
    date: firstIsoDay(source.date) || "",
    author: source.author,
    authority: AUTHORITY_RANK[source.authority] || 0,
    passages: source.passages.length,
    duplicate: isDuplicate(source) ? 1 : 0,
    month: monthKey(source),
    haystack: normalize(
      [source.title, source.path, source.author, source.summary, source.fullText].join(" "),
    ),
  }));
}

function matchesFilters(row) {
  const { type, authority, subject, month, duplicate } = state.filters;
  if (type.size && !type.has(row.type)) return false;
  if (authority.size && !authority.has(row.source.authority)) return false;
  if (subject.size && !row.source.subjectIds.some((id) => subject.has(id))) return false;
  if (month.size && !month.has(row.month)) return false;
  return !(duplicate.size && !row.duplicate);
}

function compareRows(left, right) {
  const { key, direction } = state.sort;
  if (left.source.version !== right.source.version) return right.source.version - left.source.version;
  const a = left[key];
  const b = right[key];
  if (a === b) return left.title.localeCompare(right.title);
  if (a === "" || a == null) return 1;
  if (b === "" || b == null) return -1;
  return (typeof a === "number" ? a - b : String(a).localeCompare(String(b))) * direction;
}

function visibleRows(model) {
  const terms = normalize(state.query).split(/\s+/).filter(Boolean);
  return rowsOf(model)
    .filter((row) => terms.every((term) => row.haystack.includes(term)))
    .filter(matchesFilters)
    .sort(compareRows);
}

function duplicateCell(model, source) {
  const original = source.duplicateOf ? model.sourceById.get(source.duplicateOf) : null;
  if (original) return html`<a href="${documentHref(original.id)}">${original.file}</a>`;
  const attachment = source.attachments.find((entry) => entry.sameAs && model.sourceById.has(entry.sameAs));
  if (!attachment) return "";
  return html`<a href="${documentHref(attachment.sameAs)}"
    >pièce jointe · ${model.sourceById.get(attachment.sameAs).file}</a
  >`;
}

function rowHtml(model, row) {
  const source = row.source;
  return html`<tr class="is-clickable" data-href="${documentHref(source.id)}">
    <td class="cell-title">
      <a href="${documentHref(source.id)}">${source.title}</a>
      ${source.version > 1 ? badge(`v${source.version}`, "info") : ""}
      <div class="mono">${source.path}</div>
    </td>
    <td>${typeLabel(source.type)}</td>
    <td>
      ${row.date ? html`<span class="num">${formatDay(row.date)}</span>` : html`<span class="muted">${source.date || "non daté"}</span>`}
    </td>
    <td>${source.author}</td>
    <td>${authorityBadge(source, true)}</td>
    <td><span class="chips">${source.subjectIds.map((id) => subjectTag(model, id))}</span></td>
    <td class="num">${row.passages}</td>
    <td>${duplicateCell(model, source)}</td>
  </tr>`;
}

function headerCell(column) {
  if (column.sortable === false) return html`<th scope="col">${column.label}</th>`;
  const active = state.sort.key === column.key;
  const direction = active ? (state.sort.direction > 0 ? "ascending" : "descending") : "none";
  return html`<th scope="col" aria-sort="${direction}">
    <button type="button" class="sort-btn" data-sort="${column.key}">
      ${column.label}<span class="sort-glyph">${active ? (state.sort.direction > 0 ? "▲" : "▼") : ""}</span>
    </button>
  </th>`;
}

function activeFilterCount() {
  return Object.values(state.filters).reduce((sum, set) => sum + set.size, 0);
}

function optionGroup(title, name, options) {
  return html`<fieldset class="filter-group">
    <legend>${title}</legend>
    ${options.map(
      (option) =>
        html`<label class="check">
          <input
            type="checkbox"
            name="${name}"
            value="${option.value}"
            ${state.filters[name].has(option.value) ? html`checked` : ""}
          />
          ${option.label}
        </label>`,
    )}
  </fieldset>`;
}

function filterOptions(model) {
  const rows = rowsOf(model);
  const unique = (values) => [...new Set(values)].filter(Boolean);
  return {
    type: unique(rows.map((row) => row.type)).map((value) => ({ value, label: typeLabel(value) })),
    authority: unique(rows.map((row) => row.source.authority)).map((value) => ({ value, label: value })),
    subject: model.subjects.map((subject) => ({ value: subject.id, label: subject.name })),
    month: unique(rows.map((row) => row.month))
      .sort()
      .map((value) => ({ value, label: monthLabel(value) })),
    duplicate: [{ value: "1", label: "Doublon ou pièce jointe identique" }],
  };
}

function filtersPanel(model) {
  const options = filterOptions(model);
  return html`<form class="filters">
    <div class="filter-columns">
      ${optionGroup("Type", "type", options.type)} ${optionGroup("Autorité", "authority", options.authority)}
      ${optionGroup("Sujet", "subject", options.subject)} ${optionGroup("Période", "month", options.month)}
      ${optionGroup("Doublon", "duplicate", options.duplicate)}
    </div>
    <div class="filter-actions">
      <button type="button" class="btn btn-tertiary btn-sm" data-action="reset">Réinitialiser</button>
    </div>
  </form>`;
}

function refreshTable(root, model) {
  mount(
    root.querySelector("tbody"),
    visibleRows(model).map((row) => rowHtml(model, row)),
  );
  mount(root.querySelector("thead tr"), COLUMNS.map(headerCell));
  mount(root.querySelector(".filter-slot"), filterButton(activeFilterCount()));
}

function bindFilters(panel, root, model) {
  panel.addEventListener("change", (event) => {
    const input = event.target;
    const set = state.filters[input.name];
    if (input.checked) set.add(input.value);
    else set.delete(input.value);
    refreshTable(root, model);
  });
  onDelegate(panel, "click", "[data-action='reset']", () => {
    Object.values(state.filters).forEach((set) => set.clear());
    panel.querySelectorAll("input").forEach((input) => {
      input.checked = false;
    });
    refreshTable(root, model);
  });
}

function bind(root, model) {
  root.querySelector("#source-search").addEventListener("input", (event) => {
    state.query = event.target.value;
    refreshTable(root, model);
  });
  onDelegate(root, "click", "[data-sort]", (_, button) => {
    const key = button.dataset.sort;
    state.sort = { key, direction: state.sort.key === key ? -state.sort.direction : key === "date" ? -1 : 1 };
    refreshTable(root, model);
  });
  onDelegate(root, "click", "[data-action='toggle-filters']", (_, button) => {
    const panel = openPopover(button, filtersPanel(model), { className: "is-filters", align: "end" });
    if (panel) bindFilters(panel, root, model);
  });
  onDelegate(root, "click", "tr[data-href]", (event, row) => {
    if (event.target.closest("a")) return;
    closePopover();
    navigate(row.dataset.href.split("?")[0]);
  });
}

export function render({ model }) {
  return {
    body: html`<div class="toolbar">
        ${searchField({ id: "source-search", value: state.query, placeholder: "Rechercher un document (titre, fichier, auteur, contenu)" })}
        <span class="filter-slot"></span>
      </div>
      <div class="table-card">
        <table class="data-table sources-table">
          <thead>
            <tr></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>`,
    bind: (root) => {
      refreshTable(root, model);
      bind(root, model);
    },
  };
}
