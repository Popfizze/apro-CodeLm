import { field, hexBytes } from "./data.js";
import { normalize } from "./ui.js";

const OLLAMA_URL = "http://localhost:11434";
const DEFAULT_EMBEDDING = {
  model: "embeddinggemma",
  queryTemplate: "task: search result | query: {text}",
  documentTemplate: "title: {title} | text: {text}",
};
const RETRY_AFTER_MS = 20000;
const STOP_WORDS = new Set(
  (
    "a au aux avec ce ces cet cette dans de des du elle en et est etre il ils je la le les leur lui ma mais " +
    "me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu " +
    "un une vos votre vous c d j l m n s t y ete etait sont ont avait avons fait faire plus tres tout tous " +
    "toute toutes quel quelle quels quelles quoi comment pourquoi quand si deja encore aussi alors donc car comme lors projet nova"
  ).split(" "),
);
const PREPARED_SEMANTIC_THRESHOLD = 0.8;
const PREPARED_LEXICAL_THRESHOLD = 0.75;

let ollamaBlockedUntil = 0;
const embeddingCache = new Map();

function stem(token) {
  if (/^\d+$/.test(token)) return token;
  const trimmed = token.replace(/[sx]$/, "");
  return trimmed.length > 6 ? trimmed.slice(0, 6) : trimmed;
}

export function tokens(value) {
  return normalize(value)
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length > 1 && !STOP_WORDS.has(token))
    .map(stem);
}

function termFrequencies(list) {
  const frequencies = new Map();
  list.forEach((token) => frequencies.set(token, (frequencies.get(token) || 0) + 1));
  return frequencies;
}

export function createBm25(documents) {
  const prepared = documents.map((doc) => ({
    ...doc,
    tf: termFrequencies(doc.tokens),
    length: doc.tokens.length,
  }));
  const documentFrequency = new Map();
  prepared.forEach((doc) =>
    doc.tf.forEach((_, token) => documentFrequency.set(token, (documentFrequency.get(token) || 0) + 1)),
  );
  const count = prepared.length || 1;
  const averageLength = prepared.reduce((sum, doc) => sum + doc.length, 0) / count || 1;
  const scoreTerm = (doc, token) => {
    const frequency = doc.tf.get(token);
    if (!frequency) return 0;
    const df = documentFrequency.get(token);
    const idf = Math.log(1 + (count - df + 0.5) / (df + 0.5));
    return (idf * frequency * 2.4) / (frequency + 1.4 * (0.28 + (0.72 * doc.length) / averageLength));
  };
  return (query) => {
    const terms = [...new Set(tokens(query))];
    return prepared
      .map((doc) => ({
        item: doc.item,
        score: terms.reduce((sum, token) => sum + scoreTerm(doc, token), 0) * (doc.weight || 1),
      }))
      .filter((entry) => entry.score > 0)
      .sort((left, right) => right.score - left.score);
  };
}

function legacyTemplate(prefix) {
  return prefix == null ? null : `${prefix}{text}`;
}

export function embeddingConfig(vectors) {
  const source = { ...(vectors?.meta || {}), ...(vectors || {}) };
  return {
    model: field(source, "model", "embedding_model") || DEFAULT_EMBEDDING.model,
    queryTemplate:
      field(source, "query_template") ||
      legacyTemplate(source.query_prefix) ||
      DEFAULT_EMBEDDING.queryTemplate,
    documentTemplate:
      field(source, "document_template") ||
      legacyTemplate(source.document_prefix) ||
      DEFAULT_EMBEDDING.documentTemplate,
  };
}

function fillTemplate(template, item) {
  const entry = typeof item === "string" ? { text: item } : item;
  return template.replace("{title}", entry.title || "none").replace("{text}", entry.text);
}

function normalizeVector(values) {
  const vector = Float32Array.from(values);
  const length = Math.hypot(...vector) || 1;
  return vector.map((value) => value / length);
}

async function postEmbed(model, inputs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(`${OLLAMA_URL}/api/embed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, input: inputs }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    return payload.embeddings.map(normalizeVector);
  } finally {
    clearTimeout(timer);
  }
}

export async function embedTexts(config, items, role) {
  if (Date.now() < ollamaBlockedUntil || !items.length) return null;
  const template = role === "query" ? config.queryTemplate : config.documentTemplate;
  const inputs = items.map((item) => fillTemplate(template, item));
  try {
    return await postEmbed(config.model, inputs);
  } catch {
    ollamaBlockedUntil = Date.now() + RETRY_AFTER_MS;
    return null;
  }
}

function binaryBytes(value, binary) {
  if (binary === "hex") return hexBytes(value);
  return Uint8Array.from(atob(value), (char) => char.charCodeAt(0));
}

function packedEntries(vectors) {
  const dim = Number(vectors.dimension || vectors.dim);
  const values = new Int8Array(binaryBytes(vectors.vectors || vectors.int8, vectors.binary).buffer);
  const scales = vectors.scales ? new Float32Array(binaryBytes(vectors.scales, vectors.binary).buffer) : null;
  return vectors.ids.map((id, position) => [
    id,
    {
      values: values.subarray(position * dim, (position + 1) * dim),
      scale: scales ? scales[position] : 1 / 127,
    },
  ]);
}

function floatEntries(vectors) {
  const rows = vectors.passages || {};
  return Object.entries(rows).map(([id, values]) => [id, { values: normalizeVector(values), scale: 1 }]);
}

export function decodeVectors(vectors) {
  if (!vectors || typeof vectors !== "object") return new Map();
  const packed = typeof (vectors.vectors || vectors.int8) === "string" && Array.isArray(vectors.ids);
  return new Map(packed ? packedEntries(vectors) : floatEntries(vectors));
}

export function cosine(query, entry) {
  let sum = 0;
  for (let position = 0; position < query.length; position += 1)
    sum += query[position] * entry.values[position];
  return sum * entry.scale;
}

function passageWeight(passage) {
  return passage.duplicateOf ? 0.6 : 1;
}

function lexicalIndex(model) {
  if (!model.lexicalSearch) {
    const documents = model.passages
      .filter((passage) => !passage.noise)
      .map((passage) => ({
        item: passage,
        tokens: tokens(`${passage.text} ${passage.locator} ${passage.path}`),
        weight: passageWeight(passage),
      }));
    model.lexicalSearch = createBm25(documents);
  }
  return model.lexicalSearch;
}

function semanticResults(model, queryVector) {
  return model.passages
    .filter((passage) => !passage.noise && model.vectorIndex.has(passage.id))
    .map((passage) => ({
      item: passage,
      score: cosine(queryVector, model.vectorIndex.get(passage.id)) * passageWeight(passage),
    }))
    .sort((left, right) => right.score - left.score);
}

async function queryVector(model, query) {
  if (!model.vectorIndex.size) return null;
  const vectors = await embedTexts(embeddingConfig(model.vectors), [query], "query");
  return vectors ? vectors[0] : null;
}

export async function searchPassages(model, query) {
  const vector = await queryVector(model, query);
  if (vector) return { mode: "semantic", vector, results: semanticResults(model, vector), terms: [] };
  return {
    mode: model.vectorIndex.size ? "lexical" : "lexical-no-index",
    vector: null,
    results: lexicalIndex(model)(query),
    terms: [...new Set(tokens(query))],
  };
}

function preparedEntries(model) {
  return [...model.answers, ...model.examples].filter((entry) => entry.question && entry.answer);
}

function explicitPrepared(model, query) {
  const match = query.match(/\b(Q\d{2}|EX\d)\b/i);
  if (!match) return null;
  return preparedEntries(model).find((entry) => entry.id.toUpperCase() === match[1].toUpperCase()) || null;
}

function tokenCosine(left, right) {
  const a = new Set(tokens(left));
  const b = new Set(tokens(right));
  if (!a.size || !b.size) return 0;
  const shared = [...a].filter((token) => b.has(token)).length;
  return shared / Math.sqrt(a.size * b.size);
}

async function questionVectors(model, entries) {
  const config = embeddingConfig(model.vectors);
  const missing = entries.filter(
    (entry) => !embeddingCache.has(entry.id) && !model.vectorIndex.has(entry.id),
  );
  if (missing.length) {
    const vectors = await embedTexts(
      config,
      missing.map((entry) => entry.question),
      "query",
    );
    if (!vectors) return null;
    missing.forEach((entry, position) =>
      embeddingCache.set(entry.id, { values: vectors[position], scale: 1 }),
    );
  }
  return entries.map((entry) => embeddingCache.get(entry.id) || model.vectorIndex.get(entry.id));
}

function bestBy(entries, scoreOf) {
  return entries
    .map((entry, position) => ({ entry, score: scoreOf(entry, position) }))
    .sort((left, right) => right.score - left.score)[0];
}

export async function matchPrepared(model, query, vector) {
  const explicit = explicitPrepared(model, query);
  if (explicit) return explicit;
  const entries = preparedEntries(model);
  if (!entries.length) return null;
  const vectors = vector ? await questionVectors(model, entries) : null;
  if (vectors) {
    const best = bestBy(entries, (_, position) => cosine(vector, vectors[position]));
    return best.score >= PREPARED_SEMANTIC_THRESHOLD ? best.entry : null;
  }
  const best = bestBy(entries, (entry) => tokenCosine(entry.question, query));
  return best.score >= PREPARED_LEXICAL_THRESHOLD ? best.entry : null;
}
