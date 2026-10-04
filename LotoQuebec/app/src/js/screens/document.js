import { displayEngine, subjectForStateKey, typeLabel } from "../data.js";
import { citesSource, documentHref, resolveRef } from "../refs.js";
import { href } from "../router.js";
import { badge, formatDateTime, formatDay, html, icon, isoDay, onDelegate, tag, typeIcon } from "../ui.js";
import { eventDayHref, natureBadge, people, subjectTag } from "../views.js";
import { authorityBadge } from "./ask.js";

const FLAGS = [
  ["deadline", "échéance"],
  ["commitment", "engagement avec responsable"],
  ["risk", "risque"],
];

function percent(probability) {
  if (probability == null || Number.isNaN(Number(probability))) return "";
  return html`<span class="probability">${Math.round(Number(probability) * 100)} %</span>`;
}

function subjectPart(model, typed) {
  const subjectId = subjectForStateKey(typed.subject);
  const label = subjectId ? subjectTag(model, subjectId) : typed.subject === "noise" ? tag("hors sujet") : "";
  return label ? html`<span class="typed-item">${label}${percent(typed.probability?.subject)}</span>` : "";
}

function naturePart(typed) {
  if (!typed.nature) return "";
  return html`<span class="typed-item"
    >${natureBadge(typed.nature)}${percent(typed.probability?.nature)}</span
  >`;
}

function authorityPart(model, typed) {
  if (typed.authority == null) return "";
  const label = model.authorityLabels[Math.round(typed.authority)] || typed.authority;
  return html`<span class="typed-item"
    >${tag(`autorité : ${label}`)}${percent(typed.probability?.authority)}</span
  >`;
}

function flagParts(typed) {
  return FLAGS.filter(([key]) => typed[key] >= 0.5).map(
    ([key, label]) => html`<span class="typed-item">${tag(label)}${percent(typed[key])}</span>`,
  );
}

function typedLine(model, passage) {
  const typed = passage.typed;
  if (!typed) return linkLine(model, passage);
  return html`<div class="typed">
    ${subjectPart(model, typed)} ${naturePart(typed)} ${authorityPart(model, typed)} ${flagParts(typed)}
    <span class="engine">moteur : ${displayEngine(typed.engine)}</span>
  </div>`;
}

function linkLine(model, passage) {
  const subjectId = passage.link?.subjectId;
  if (!subjectId) return "";
  return html`<div class="typed">
    <span class="muted">Sujet relié :</span> ${subjectTag(model, subjectId)}
  </div>`;
}

function relationLine(model, passage) {
  const parts = [];
  if (passage.duplicateOf) parts.push(relationLink(model, "doublon de", passage.duplicateOf));
  if (passage.attachmentOf) parts.push(relationLink(model, "pièce jointe de", passage.attachmentOf));
  return parts.length ? html`<div class="relation">${parts}</div>` : "";
}

function relationLink(model, label, targetId) {
  const passage = model.passageById.get(targetId);
  const source = passage
    ? model.sourceById.get(passage.sourceId)
    : model.sources.find((entry) => entry.passages[0]?.sourceKey === targetId);
  if (!source) return html`<span>${label} ${targetId}</span>`;
  return html`<span
    >${label}
    <a href="${documentHref(source.id, passage ? [passage.id] : [])}"
      >${source.file}${passage ? ` · ${passage.displayLocator}` : ""}</a
    ></span
  >`;
}

function passageMeta(source, passage) {
  const author = passage.author && passage.author !== source.author ? passage.author : "";
  const date =
    passage.date && isoDay(passage.date) !== isoDay(source.date) ? formatDateTime(passage.date) : "";
  return [author, date].filter(Boolean).join(" · ");
}

function passageBlock(model, source, passage, targets) {
  const targeted = targets.has(passage.id);
  const meta = passageMeta(source, passage);
  return html`<article class="passage ${targeted ? "is-target" : ""}" id="p-${passage.id}">
    <div class="passage-gutter">
      <span>${passage.displayLocator}</span>
      <button
        type="button"
        class="copy-ref"
        data-copy="${source.file} · ${passage.displayLocator}"
        title="Copier le repère"
      >
        ${icon("copy")}
      </button>
    </div>
    <div class="passage-main">
      <p class="passage-body">${passage.text}</p>
      ${meta ? html`<div class="passage-meta">${meta}</div>` : ""}
      ${passage.noise ? badge("bruit", "neutral") : ""} ${relationLine(model, passage)}
      ${typedLine(model, passage)}
    </div>
  </article>`;
}

function contentBlock(model, source, targets) {
  const image = source.image
    ? html`<img class="capture" src="${source.image}" alt="Capture ${source.file}" />`
    : "";
  if (!source.passages.length) {
    return html`${image}
      <pre class="full-text">${source.fullText || "Aucun passage repéré dans ce document."}</pre>`;
  }
  const ordered = [...source.passages].sort((left, right) => left.order - right.order);
  return html`${image}${ordered.map((passage) => passageBlock(model, source, passage, targets))}`;
}

function metaRow(label, value) {
  return value
    ? html`<div class="meta-row">
        <dt>${label}</dt>
        <dd>${value}</dd>
      </div>`
    : "";
}

function attachmentsBlock(model, source) {
  if (!source.attachments.length) return "";
  return html`<div class="meta-row">
    <dt>Pièces jointes</dt>
    <dd>
      ${source.attachments.map((attachment) => {
        const same = model.sourceById.get(attachment.sameAs);
        return html`<div>
          ${attachment.file}${same ? html` · identique à <a href="${documentHref(same.id)}">${same.file}</a>` : ""}${attachment.note ? html`<div class="muted">${attachment.note}</div>` : ""}
        </div>`;
      })}
    </dd>
  </div>`;
}

function metadataCard(model, source) {
  return html`<section class="card side-card">
    <h2 class="card-title">Métadonnées</h2>
    <dl class="meta">
      ${metaRow("Date des faits", source.date ? (/^\d{4}-\d{2}-\d{2}/.test(source.date) ? formatDateTime(source.date) : source.date) : "")}
      ${metaRow("Auteur", source.author && people(model, source.author))}
      ${metaRow("Destinataires", source.recipients && people(model, source.recipients))}
      ${metaRow("Type", typeLabel(source.type))}
      ${metaRow("Empreinte", source.sha ? source.sha.slice(0, 12) : "")} ${metaRow("Résumé", source.summary)}
      ${metaRow("Version", source.version > 1 ? `importé dans la v${source.version}` : "")}
      ${attachmentsBlock(model, source)}
    </dl>
  </section>`;
}

function decisionsCard(model, source) {
  const related = model.decisions.filter((decision) => citesSource(model, decision.refs, source.id));
  if (!related.length) return "";
  return html`<section class="card side-card">
    <h2 class="card-title">Décisions associées</h2>
    <ul class="side-list">
      ${related.map((decision) => {
        const ref = decision.refs.find((entry) => resolveRef(model, entry).source?.id === source.id);
        const passages = resolveRef(model, ref).passageIds;
        return html`<li>
          <a href="${href(`#/rapports/dossier/${decision.id}`)}"
            ><b>${decision.id}</b> ${decision.statement}</a
          >
          <div class="muted">
            ${decision.decidedOn ? formatDay(decision.decidedOn) : "non documenté"} · ${decision.status}
          </div>
          ${ref.locator ? html`<a class="chip-src" href="${documentHref(source.id, passages)}">${icon("file")}<span>${ref.locator}</span></a>` : ""}
        </li>`;
      })}
    </ul>
  </section>`;
}

function citingList(title, items) {
  if (!items.length) return "";
  return html`<section class="card side-card">
    <h2 class="card-title">${title}</h2>
    <ul class="side-list">
      ${items.map(
        (item) =>
          html`<li>
            <a href="${item.href}"><b>${item.id}</b> <span>${item.label}</span></a>
          </li>`,
      )}
    </ul>
  </section>`;
}

function citingAnswersCard(model, source) {
  const answers = model.answers.filter((answer) => citesSource(model, answer.refs, source.id));
  return citingList(
    "Réponses qui citent ce document",
    answers.map((answer) => ({
      id: answer.id,
      label: answer.question,
      href: href(`#/documentation/reponses/${answer.id}`),
    })),
  );
}

function citingActionsCard(model, source) {
  const actions = model.actions.filter((action) => citesSource(model, action.refs, source.id));
  return citingList(
    "Actions qui citent ce document",
    actions.map((action) => ({ id: action.id, label: action.text, href: href(`#/suivi/${action.id}`) })),
  );
}

function citedByCard(model, source) {
  const events = model.events.filter((event) => citesSource(model, event.refs, source.id));
  if (!events.length) return "";
  return html`<section class="card side-card">
    <h2 class="card-title">Cité par</h2>
    <ul class="side-list">
      ${events.map(
        (event) =>
          html`<li>
            <a href="${eventDayHref(event)}">
              <span class="muted"
                >${event.day ? formatDay(event.day) : event.date}${event.time ? `, ${event.time}` : ""}</span
              >
              ${natureBadge(event.natureKey)}
              <span>${event.summary}</span>
            </a>
            <div class="muted">${event.refs[0]?.locator || ""}</div>
          </li>`,
      )}
    </ul>
  </section>`;
}

function headerBlock(model, source) {
  const original = source.duplicateOf ? model.sourceById.get(source.duplicateOf) : null;
  return html`<header class="doc-head span-12">
    <span class="doc-icon">${typeIcon(source.type)}</span>
    <div class="doc-titles">
      <h2 class="doc-title">${source.title}</h2>
      <div class="mono">${source.path}</div>
      ${source.authorityReason ? html`<p class="muted">${source.authorityReason}</p>` : ""}
    </div>
    <div class="doc-badges">
      ${tag(typeLabel(source.type))} ${authorityBadge(source)}
      ${source.version > 1 ? badge(`v${source.version}`, "info") : ""}
      ${original ? html`<a class="badge is-neutral" href="${documentHref(original.id)}">doublon de ${original.file}</a>` : ""}
      ${source.subjectIds.map((id) => subjectTag(model, id))}
    </div>
  </header>`;
}

function scrollToTarget(root, targets) {
  const first = [...targets].map((id) => root.querySelector(`[id="p-${CSS.escape(id)}"]`)).find(Boolean);
  if (first) first.scrollIntoView({ block: "center" });
}

function bindCopy(root) {
  onDelegate(root, "click", "[data-copy]", (_, button) => {
    navigator.clipboard?.writeText(button.dataset.copy).then(
      () => button.classList.add("is-done"),
      () => button.classList.remove("is-done"),
    );
  });
}

function notFound(id) {
  return {
    crumbs: [{ label: id }],
    body: html`<section class="card">
      <p>Document introuvable : ${id}. <a href="${href("#/explorer/sources")}">Retour aux sources</a></p>
    </section>`,
  };
}

export function render({ model, params }) {
  const source = model.sourceById.get(params.sourceId);
  if (!source) return notFound(params.sourceId);
  const targets = new Set((params.passageIds || "").split(",").filter(Boolean));
  return {
    crumbs: [{ label: source.title }],
    body: html`<div class="grid document">
      ${headerBlock(model, source)}
      <div class="span-8 doc-content">${contentBlock(model, source, targets)}</div>
      <aside class="span-4 doc-side">
        ${metadataCard(model, source)} ${citingAnswersCard(model, source)} ${citingActionsCard(model, source)}
        ${decisionsCard(model, source)} ${citedByCard(model, source)}
      </aside>
    </div>`,
    bind: (root) => {
      bindCopy(root);
      requestAnimationFrame(() => scrollToTarget(root, targets));
    },
  };
}
