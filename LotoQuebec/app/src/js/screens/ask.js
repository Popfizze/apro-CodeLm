import { typeLabel } from "../data.js";
import { documentHref, resolveRef } from "../refs.js";
import { matchPrepared, searchPassages } from "../search.js";
import { badge, escapeHtml, formatDay, html, icon, mount, normalize, raw, typeIcon } from "../ui.js";
import { multiline } from "../views.js";

const MAX_SOURCES = 6;
const MAX_PASSAGES = 3;
const CANDIDATES = 60;
const conversation = [];

function authorityTone(authority) {
  return authority === "haute" ? "info" : "neutral";
}

export function authorityBadge(source, short = false) {
  const value = source.authority || "non évaluée";
  return badge(short ? value : `autorité ${value}`, authorityTone(value), source.authorityReason || value);
}

function highlight(text, terms) {
  const escaped = escapeHtml(text);
  if (!terms.length) return raw(escaped);
  const plain = normalize(escaped);
  const ranges = [];
  terms
    .filter((term) => term.length > 2)
    .forEach((term) => {
      for (let index = plain.indexOf(term); index >= 0; index = plain.indexOf(term, index + term.length)) {
        let end = index + term.length;
        while (end < plain.length && /[a-z0-9]/.test(plain[end])) end += 1;
        if (!/&[a-z#0-9]*$/.test(plain.slice(Math.max(0, index - 8), index))) ranges.push([index, end]);
      }
    });
  return raw(mergeMarks(escaped, ranges));
}

function mergeMarks(text, ranges) {
  let out = "";
  let last = 0;
  ranges
    .sort((left, right) => left[0] - right[0])
    .forEach(([start, end]) => {
      if (start < last) return;
      out += `${text.slice(last, start)}<mark>${text.slice(start, end)}</mark>`;
      last = end;
    });
  return out + text.slice(last);
}

function preparedSourceCard(model, ref, index) {
  const resolved = resolveRef(model, ref);
  const source = resolved.source;
  const tag = source ? "a" : "div";
  const target = source ? raw(` href="${escapeHtml(resolved.href)}"`) : "";
  return html`<${raw(tag)} class="evidence-card"${target}>
    <span class="evidence-index">${index + 1}</span>
    <span class="evidence-body">
      <span class="evidence-head">${source ? typeIcon(source.type) : icon("file")}<b>${source ? source.file : ref.source}</b><span class="muted">${ref.locator}</span></span>
      <span class="evidence-meta">${source?.date ? formatDay(source.date) : ""} ${source ? authorityBadge(source) : ""}</span>
      ${ref.quote ? html`<q class="evidence-quote">${ref.quote}</q>` : ""}
    </span>
  </${raw(tag)}>`;
}

function preparedBlock(model, entry) {
  return html`<div class="prepared">
    <div class="prepared-answer">
      ${badge(`Réponse préparée · ${entry.id}`, "info")}
      <p class="prepared-question">${entry.question}</p>
      <div class="prepared-text">${multiline(entry.answer)}</div>
    </div>
    <div class="prepared-sources">
      <h3 class="block-title">Sources</h3>
      <ol class="evidence-list">
        ${entry.refs.map((ref, index) => html`<li>${preparedSourceCard(model, ref, index)}</li>`)}
      </ol>
    </div>
  </div>`;
}

function groupResults(model, results) {
  const groups = new Map();
  const seen = new Map();
  results.slice(0, CANDIDATES).forEach(({ item: passage }) => {
    const canonical =
      passage.duplicateOf && model.passageById.has(passage.duplicateOf) ? passage.duplicateOf : passage.id;
    if (seen.has(canonical)) {
      seen.get(canonical).alsoIn.add(model.sourceById.get(passage.sourceId)?.file || passage.path);
      return;
    }
    const target = model.passageById.get(canonical);
    const entry = {
      passage: target,
      alsoIn: new Set(canonical !== passage.id ? [passage.path.split("/").pop()] : []),
    };
    seen.set(canonical, entry);
    const key = target.sourceId;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(entry);
  });
  return [...groups.entries()].slice(0, MAX_SOURCES).map(([sourceId, entries]) => ({
    source: model.sourceById.get(sourceId),
    entries: entries.slice(0, MAX_PASSAGES),
  }));
}

function passageItem(source, entry, terms) {
  const passage = entry.passage;
  const showAuthor = passage.author && passage.author !== source.author;
  return html`<a class="passage-hit" href="${documentHref(source.id, [passage.id])}">
    <span class="passage-loc">${passage.displayLocator}</span>
    <span class="passage-text">
      <span class="passage-snippet">${highlight(passage.text, terms)}</span>
      <span class="passage-meta">
        ${passage.date ? formatDay(passage.date) : ""}${showAuthor ? ` · ${passage.author}` : ""}
        ${entry.alsoIn.size ? html` · aussi dans ${[...entry.alsoIn].join(", ")}` : ""}
      </span>
    </span>
  </a>`;
}

function sourceGroup(group, terms) {
  const source = group.source;
  return html`<section class="hit-group">
    <header class="hit-head">
      ${typeIcon(source.type)}
      <span class="hit-title">${source.title}</span>
      <span class="mono">${source.file}</span>
      <span class="muted">${typeLabel(source.type)}${source.date ? ` · ${formatDay(source.date)}` : ""}</span>
      ${authorityBadge(source)} ${source.version > 1 ? badge(`v${source.version}`, "info") : ""}
    </header>
    ${group.entries.map((entry) => passageItem(source, entry, terms))}
  </section>`;
}

function answerBody(model, outcome) {
  const groups = groupResults(model, outcome.results);
  return html`${outcome.prepared ? preparedBlock(model, outcome.prepared) : ""}
    <h3 class="block-title">Passages pertinents</h3>
    ${groups.length ? groups.map((group) => sourceGroup(group, outcome.terms)) : html`<p class="muted">Aucun passage ne correspond à cette question.</p>`}`;
}

function messageHtml(model, message) {
  if (message.role === "user")
    return html`<div class="msg is-user"><div class="bubble">${message.text}</div></div>`;
  if (!message.outcome)
    return html`<div class="msg is-bot"><div class="answer is-pending">Recherche en cours…</div></div>`;
  return html`<div class="msg is-bot"><div class="answer">${answerBody(model, message.outcome)}</div></div>`;
}

function renderThread(root, model) {
  mount(
    root.querySelector(".thread-inner"),
    conversation.map((message) => messageHtml(model, message)),
  );
}

function isAtBottom(thread) {
  return thread.scrollHeight - thread.scrollTop - thread.clientHeight < 32;
}

async function answer(model, question) {
  const search = await searchPassages(model, question);
  const prepared = await matchPrepared(model, question, search.vector);
  return { ...search, prepared };
}

async function ask(root, model, question) {
  const thread = root.querySelector(".thread");
  const pending = { role: "bot", outcome: null };
  conversation.push({ role: "user", text: question }, pending);
  renderThread(root, model);
  thread.scrollTop = thread.scrollHeight;
  pending.outcome = await answer(model, question);
  const wasAtBottom = isAtBottom(thread);
  renderThread(root, model);
  if (wasAtBottom) {
    const last = thread.querySelector(".msg:last-child");
    thread.scrollTop = last.offsetTop - 12;
  }
}

function bindComposer(root, model) {
  const form = root.querySelector(".composer");
  const input = form.querySelector("textarea");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    ask(root, model, question);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  input.focus();
}

export function render({ model }) {
  return {
    body: html`<div class="thread" aria-live="polite"><div class="thread-inner"></div></div>
      <form class="composer" autocomplete="off">
        <label class="visually-hidden" for="question">Question</label>
        <textarea id="question" rows="2" placeholder="Posez une question sur NOVA"></textarea>
        <button class="btn btn-primary" type="submit">${icon("send")}Envoyer</button>
      </form>`,
    bind: (root) => {
      renderThread(root, model);
      root.querySelector(".thread").scrollTop = root.querySelector(".thread").scrollHeight;
      bindComposer(root, model);
    },
  };
}
