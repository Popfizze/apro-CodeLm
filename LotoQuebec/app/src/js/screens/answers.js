import { typeLabel } from "../data.js";
import { resolveRef } from "../refs.js";
import { href } from "../router.js";
import { formatDay, html, icon, typeIcon } from "../ui.js";
import { multiline } from "../views.js";
import { authorityBadge } from "./ask.js";

function answerList(model, activeId) {
  return html`<nav class="answer-nav" aria-label="Questions">
    ${model.answers.map(
      (entry) =>
        html`<a
          class="answer-link ${entry.id === activeId ? "is-active" : ""}"
          href="${href(`#/documentation/reponses/${entry.id}`)}"
          ${entry.id === activeId ? html`aria-current="page"` : ""}
        >
          <b>${entry.id}</b><span>${entry.question}</span>
        </a>`,
    )}
  </nav>`;
}

function sourceCard(model, ref, index) {
  const resolved = resolveRef(model, ref);
  const source = resolved.source;
  const head = html`<span class="evidence-index">${index + 1}</span>
    <span class="evidence-body">
      <span class="evidence-head"
        >${source ? typeIcon(source.type) : icon("file")}<b>${source ? source.file : ref.source}</b></span
      >
      <span class="evidence-meta"><span class="mono">${ref.locator}</span></span>
      <span class="evidence-meta"
        >${source ? typeLabel(source.type) : ""}${source?.date ? ` · ${formatDay(source.date)}` : ""}
        ${source ? authorityBadge(source) : ""}</span
      >
      ${ref.quote ? html`<q class="evidence-quote">${ref.quote}</q>` : ""}
    </span>`;
  return source
    ? html`<a class="evidence-card" href="${resolved.href}">${head}</a>`
    : html`<div class="evidence-card">${head}</div>`;
}

export function render({ model, params }) {
  const active = model.answers.find((entry) => entry.id === params.answerId) || model.answers[0];
  if (!active) return { body: html`<section class="card"><p>Aucune réponse documentée.</p></section>` };
  return {
    crumbs: [{ label: active.id }],
    body: html`<div class="grid answers">
      <aside class="span-4 answers-side">${answerList(model, active.id)}</aside>
      <section class="span-8 answers-main">
        <article class="card">
          <h2 class="answer-question">
            <span class="tag is-condition">${active.id}</span> ${active.question}
          </h2>
          <div class="answer-text">${multiline(active.answer)}</div>
        </article>
        <h3 class="block-title">Sources</h3>
        <div class="evidence-grid">${active.refs.map((ref, index) => sourceCard(model, ref, index))}</div>
      </section>
    </div>`,
  };
}
