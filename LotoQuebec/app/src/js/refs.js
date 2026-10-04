import { findSource } from "./data.js";
import { href } from "./router.js";
import { html, icon, normalize, truncate } from "./ui.js";

const MAX_RANGE = 60;

function expandRange(start, end) {
  const last = Math.min(end ?? start, start + MAX_RANGE);
  const values = [];
  for (let value = start; value <= last; value += 1) values.push(value);
  return values;
}

function collectNumbers(pattern, locator) {
  const values = new Set();
  for (const match of locator.matchAll(pattern)) {
    const start = Number(match[1]);
    const end = match[2] ? Number(match[2]) : start;
    expandRange(start, end).forEach((value) => values.add(value));
  }
  return values;
}

function collectTimes(locator) {
  const times = new Set();
  for (const match of locator.matchAll(/\b(\d{1,2})[:h](\d{2})\b/g)) {
    times.add(`${match[1].padStart(2, "0")}:${match[2]}`);
  }
  return times;
}

function isSheet(source) {
  return /\.(xlsx|xls|csv)$/i.test(source.path);
}

function parseLocator(source, locator) {
  const plain = normalize(locator);
  return {
    lines: new Set([
      ...collectNumbers(/\bL(\d+)(?:\s*[-–]\s*L?(\d+))?/g, locator),
      ...collectNumbers(/lignes?\s+(\d+)(?:\s*(?:[-–]|a)\s*(\d+))?/g, plain),
    ]),
    times: collectTimes(locator),
    pages: collectNumbers(/\bp\.?\s*(\d+)\b/g, locator),
    rows: isSheet(source) ? collectNumbers(/[A-Z]{1,2}(\d+)(?::[A-Z]{1,2}(\d+))?/g, locator) : new Set(),
    paragraphs: collectNumbers(/§\s*(\d+)(?:\s*[-–]\s*§?\s*(\d+))?/g, locator),
    header: /en-tete/.test(plain),
  };
}

function hasTokens(tokens) {
  return (
    tokens.header ||
    [tokens.lines, tokens.times, tokens.pages, tokens.rows, tokens.paragraphs].some((set) => set.size > 0)
  );
}

function suffixNumber(passage, prefix) {
  const match = passage.id.match(new RegExp(`:${prefix}(\\d+)$`));
  return match ? Number(match[1]) : null;
}

function locatorNumbers(passage, pattern) {
  return collectNumbers(pattern, normalize(passage.locator));
}

function matchesLine(passage, tokens) {
  if (!tokens.lines.size) return false;
  const own = suffixNumber(passage, "L");
  if (own != null && tokens.lines.has(own)) return true;
  const spans = locatorNumbers(passage, /lignes?\s+(\d+)(?:\s*[-–]\s*(\d+))?/g);
  return [...spans].some((line) => tokens.lines.has(line));
}

function matchesTime(passage, tokens) {
  if (!tokens.times.size) return false;
  const stamp = passage.locator.match(/\[(\d{1,2}:\d{2})/);
  const leading = passage.text.match(/^(\d{1,2}:\d{2})/);
  const time = (stamp || leading)?.[1]?.padStart(5, "0");
  return Boolean(time && tokens.times.has(time));
}

function matchesPage(passage, tokens) {
  const page = suffixNumber(passage, "p");
  return page != null && tokens.pages.has(page) && !passage.attachmentOf;
}

function matchesRow(passage, tokens) {
  if (!tokens.rows.size) return false;
  const row = suffixNumber(passage, "R") ?? [...locatorNumbers(passage, /ligne\s+(\d+)/g)][0];
  return row != null && tokens.rows.has(row);
}

function matchesParagraph(passage, tokens) {
  const match = passage.displayLocator.match(/^corps\s*§\s*(\d+)$/i);
  return Boolean(match && tokens.paragraphs.has(Number(match[1])) && !passage.attachmentOf);
}

function matchesHeader(passage, tokens) {
  return tokens.header && /^en-t[eê]te/i.test(passage.locator);
}

const MATCHERS = [matchesLine, matchesTime, matchesPage, matchesRow, matchesParagraph, matchesHeader];

function structuralMatches(source, tokens) {
  return source.passages.filter((passage) => MATCHERS.some((matcher) => matcher(passage, tokens)));
}

function quoteKey(value) {
  return normalize(value)
    .replace(/[«»"“”’'`*]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function quoteMatches(source, quote) {
  const wanted = quoteKey(quote).slice(0, 60);
  if (wanted.length < 8) return [];
  return source.passages.filter((passage) => quoteKey(passage.text).includes(wanted));
}

function wordMatches(source, locator) {
  const words = normalize(locator)
    .split(/[^a-z0-9]+/)
    .filter((word) => word.length > 3);
  if (!words.length) return [];
  const scored = source.passages.map((passage) => {
    const haystack = normalize(passage.locator);
    return { passage, score: words.filter((word) => haystack.includes(word)).length };
  });
  const best = Math.max(0, ...scored.map((entry) => entry.score));
  return best ? scored.filter((entry) => entry.score === best).map((entry) => entry.passage) : [];
}

export function matchPassages(source, ref) {
  const byQuote = quoteMatches(source, ref.quote);
  if (byQuote.length) return byQuote;
  const tokens = parseLocator(source, ref.locator || "");
  if (hasTokens(tokens)) return structuralMatches(source, tokens);
  return wordMatches(source, ref.locator || "");
}

export function documentHref(sourceId, passageIds = []) {
  const base = `#/explorer/sources/${encodeURIComponent(sourceId)}`;
  return href(passageIds.length ? `${base}/${encodeURIComponent(passageIds.join(","))}` : base);
}

function exactPassage(model, ref) {
  const passage = ref.passageId ? model.passageById.get(ref.passageId) : null;
  if (!passage) return null;
  const source = model.sourceById.get(passage.sourceId);
  return { source, passageIds: [passage.id], href: documentHref(source.id, [passage.id]) };
}

export function resolveRef(model, ref) {
  const exact = exactPassage(model, ref);
  if (exact) return exact;
  const source = findSource(model, ref.source);
  if (!source) return { source: null, passageIds: [], href: "" };
  const passages = matchPassages(source, ref);
  const passageIds = passages.map((passage) => passage.id);
  return { source, passageIds, href: documentHref(source.id, passageIds) };
}

export function citesSource(model, refList, sourceId) {
  return refList.some((ref) => resolveRef(model, ref).source?.id === sourceId);
}

export function sourceChip(model, ref, options = {}) {
  const resolved = resolveRef(model, ref);
  const name = resolved.source ? resolved.source.file : ref.source;
  const label = ref.locator ? `${name} · ${ref.locator}` : name;
  const title = ref.quote ? `${label}\n« ${ref.quote} »` : label;
  const shown = truncate(label, options.max || 64);
  if (!resolved.source) return html`<span class="chip-src is-dead" title="${title}">${shown}</span>`;
  return html`<a class="chip-src" href="${resolved.href}" title="${title}"
    >${icon("file")}<span>${shown}</span></a
  >`;
}

export function sourceChips(model, refList, options = {}) {
  if (!refList?.length) return "";
  return html`<span class="chips">${refList.map((ref) => sourceChip(model, ref, options))}</span>`;
}
