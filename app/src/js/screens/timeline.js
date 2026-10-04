import { NATURE_GROUPS, natureInfo } from "../data.js";
import { documentHref, sourceChips } from "../refs.js";
import { href } from "../router.js";
import { addDays, badge, daysBetween, formatDay, formatLongDay, html, icon, isoDay } from "../ui.js";
import { dayHistogram, legend } from "../charts.js";
import { chartHost, eventDayHref, natureBadge, people, plural, subjectTag } from "../views.js";

const UNDATED = "non-date";

function importedItems(model) {
  return model.passages
    .filter((passage) => passage.version > 1)
    .map((passage) => ({ passage, day: isoDay(passage.date) || isoDay(model.version.asOf) }));
}

function itemsByDay(model) {
  const days = new Map();
  const push = (day, item) => days.set(day, [...(days.get(day) || []), item]);
  model.events.forEach((event) =>
    push(event.day || UNDATED, { kind: "event", event, group: natureInfo(event.natureKey).group }),
  );
  importedItems(model).forEach((entry) =>
    push(entry.day, {
      kind: "import",
      passage: entry.passage,
      group: entry.passage.typed?.nature ? natureInfo(entry.passage.typed.nature).group : "other",
    }),
  );
  return days;
}

function firstOfMonth(day) {
  return `${day.slice(0, 7)}-01`;
}

function countOf(items, group, kind) {
  return items.filter((item) => item.group === group && item.kind === kind).length;
}

function stackFor(items) {
  return NATURE_GROUPS.flatMap((group) => [
    { label: group.label, className: `fill-${group.id}`, count: countOf(items, group.id, "event") },
    {
      label: `${group.label} · nouvelle information`,
      className: `fill-${group.id} is-imported`,
      count: countOf(items, group.id, "import"),
    },
  ]);
}

function columnsFor(model, days) {
  const dated = [...days.keys()].filter((day) => day !== UNDATED).sort();
  const last = isoDay(model.asOf);
  if (!dated.length || !last) return [];
  const start = firstOfMonth(dated[0]);
  const end = dated[dated.length - 1] > last ? dated[dated.length - 1] : last;
  return Array.from({ length: daysBetween(start, end) + 1 }, (_, index) => {
    const day = addDays(start, index);
    const stack = stackFor(days.get(day) || []);
    return {
      day,
      stack,
      total: stack.reduce((sum, part) => sum + part.count, 0),
      href: href(`#/historique/${day}`),
    };
  });
}

function defaultDay(model, days) {
  const limit = isoDay(model.asOf);
  return [...days.keys()]
    .filter((day) => day !== UNDATED && day <= limit)
    .sort()
    .pop();
}

function legendItems(days) {
  const all = [...days.values()].flat();
  const items = NATURE_GROUPS.map((group) => ({
    className: `fill-${group.id}`,
    label: group.label,
    total: all.filter((item) => item.kind === "event" && item.group === group.id).length,
  }));
  const imported = all.filter((item) => item.kind === "import").length;
  return imported
    ? [...items, { className: "fill-other is-imported", label: "Nouvelle information", total: imported }]
    : items;
}

function statusBadge(event) {
  if (event.status.startsWith("actuel")) return badge("actuel", "info");
  if (event.status.startsWith("remplac")) return badge("remplacé", "neutral");
  if (event.status.startsWith("histor")) return badge("historique", "neutral");
  return event.status ? badge(event.status, "neutral") : "";
}

function replacedBy(model, event) {
  if (!event.replacedBy) return "";
  const target = model.events.find((entry) => entry.id === event.replacedBy);
  return html`<span class="muted"
    >remplacé par
    <a href="${target ? eventDayHref(target) : href("#/historique")}">${event.replacedBy}</a></span
  >`;
}

function eventCard(model, event) {
  return html`<article class="event-card" id="${event.id}">
    <header class="event-head">
      ${event.time ? html`<span class="event-time">${event.time}</span>` : ""} ${natureBadge(event.natureKey)}
      ${subjectTag(model, event.subjectId)} ${statusBadge(event)}
      ${event.confidence === "moyenne" ? badge("confiance moyenne", "warning") : ""}
      <span class="event-id">${event.id}</span>
    </header>
    <p class="event-summary">${event.summary}</p>
    ${event.actors.length ? html`<p class="muted">${people(model, event.actors.join(", "))}</p>` : ""}
    ${event.quote ? html`<q class="quote">${event.quote}</q>` : ""}
    <footer class="event-foot">${sourceChips(model, event.refs)} ${replacedBy(model, event)}</footer>
  </article>`;
}

function importCard(model, passage) {
  const source = model.sourceById.get(passage.sourceId);
  return html`<article class="event-card is-imported">
    <header class="event-head">
      ${badge(`Nouvelle information · v${passage.version}`, "info")}
      ${passage.typed?.nature ? natureBadge(passage.typed.nature) : ""}
      ${passage.link?.subjectId ? subjectTag(model, passage.link.subjectId) : ""}
    </header>
    <p class="event-summary">${passage.text}</p>
    <footer class="event-foot">
      <a class="chip-src" href="${documentHref(source.id, [passage.id])}"
        >${source.file} · ${passage.displayLocator}</a
      >
    </footer>
  </article>`;
}

function sortItems(items) {
  const key = (item) => (item.kind === "event" ? item.event.time || "" : "99:99");
  return [...items].sort((left, right) => key(left).localeCompare(key(right)));
}

function neighbours(days, active) {
  const ordered = [
    ...(days.has(UNDATED) ? [UNDATED] : []),
    ...[...days.keys()].filter((day) => day !== UNDATED).sort(),
  ];
  const index = ordered.indexOf(active);
  return { previous: ordered[index - 1] || null, next: ordered[index + 1] || null };
}

function dayArrow(day, label, iconName) {
  if (!day) return html`<span class="icon-btn is-disabled" aria-hidden="true">${icon(iconName)}</span>`;
  return html`<a
    class="icon-btn"
    href="${href(`#/historique/${day}`)}"
    aria-label="${label}"
    data-tip="${label}"
    >${icon(iconName)}</a
  >`;
}

function dayPanel(model, day, days) {
  const items = days.get(day) || [];
  const title = day === UNDATED ? "Éléments non datés" : formatLongDay(day);
  const sorted = sortItems(items);
  const { previous, next } = neighbours(days, day);
  return html`<section class="day-panel">
    <header class="day-head">
      ${dayArrow(previous, "Jour précédent", "chevron")}
      <h2 class="card-title">${title}</h2>
      ${dayArrow(next, "Jour suivant", "next")}
      <span class="muted">${plural(items.length, "élément")}</span>
    </header>
    <div class="day-grid">
      ${sorted.map((item) => (item.kind === "event" ? eventCard(model, item.event) : importCard(model, item.passage)))}
    </div>
  </section>`;
}

export function render({ model, params }) {
  const days = itemsByDay(model);
  const active =
    params.day && (days.has(params.day) || params.day === UNDATED) ? params.day : defaultDay(model, days);
  const columns = columnsFor(model, days);
  const undatedItems = days.get(UNDATED) || [];
  const undated = undatedItems.length
    ? { stack: stackFor(undatedItems), total: undatedItems.length, href: href(`#/historique/${UNDATED}`) }
    : null;
  return {
    crumbs: active ? [{ label: active === UNDATED ? "Non daté" : formatDay(active) }] : [],
    keepScroll: true,
    body: html`<section class="card span-12 histogram-card">
        <header class="card-head">
          <h2 class="card-title">Événements par jour</h2>
          ${legend(legendItems(days))}
        </header>
        ${chartHost("histogram")}
      </section>
      ${active ? dayPanel(model, active, days) : ""}`,
    charts: {
      histogram: (width) =>
        dayHistogram({ width, columns, undated, today: isoDay(model.asOf), activeDay: active }),
    },
  };
}
