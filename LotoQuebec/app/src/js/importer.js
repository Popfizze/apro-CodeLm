import { subjectForStateKey } from "./data.js";
import { cosine, createBm25, embedTexts, embeddingConfig, tokens } from "./search.js";
import { badge, basename, html, icon, mount, normalize, onDelegate } from "./ui.js";
import { nextVersionNumber, saveVersion, versionModel } from "./versions.js";

const BROWSER_FORMATS = ["txt", "md", "eml", "csv"];
const PIPELINE_FORMATS = ["pdf", "xlsx", "png"];
const PIPELINE_COMMAND = "python -m pipeline --event <fichier>";
const NEIGHBORS = 5;
const MAJORITY = 3;
const MONTHS = ["janv", "fevr", "mars", "avr", "mai", "juin", "juil", "aout", "sept", "oct", "nov", "dec"];
const STEPS = [
  "Lecture du fichier",
  "Découpage en passages",
  "Rapprochement des sujets",
  "Comparaison avec la version précédente",
];

const dialog = { files: [], progress: [], error: "" };

function extension(name) {
  return (name.split(".").pop() || "").toLowerCase();
}

function frenchDate(text) {
  const match = normalize(text).match(
    /\b(\d{1,2})(?:er)?\s+(janv|fevr|mars|avr|mai|juin|juil|aout|sept|oct|nov|dec)[a-z]*\.?\s+(\d{4})\b/,
  );
  if (!match) return null;
  const month = String(MONTHS.indexOf(match[2]) + 1).padStart(2, "0");
  return `${match[3]}-${month}-${match[1].padStart(2, "0")}`;
}

function detectDate(text) {
  const iso = String(text).match(/\b(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?/);
  if (iso) return iso[2] ? `${iso[1]}T${iso[2]}` : iso[1];
  return frenchDate(text);
}

function passage(context, { suffix, locator, text, date = null, author = null }) {
  return {
    id: `v${context.version}-${context.stem}:${suffix}`,
    source_id: `v${context.version}-${context.stem}`,
    path: `import/v${context.version}/${context.name}`,
    kind: context.kind,
    locator,
    date: date || context.date || null,
    author,
    text: text.trim(),
    duplicate_of: null,
  };
}

function splitLines(context, content) {
  return content
    .split(/\r?\n/)
    .map((line, index) => ({ line: line.trim(), number: index + 1 }))
    .filter((entry) => entry.line)
    .map((entry) =>
      passage(context, { suffix: `L${entry.number}`, locator: `ligne ${entry.number}`, text: entry.line }),
    );
}

function splitCsv(context, content) {
  const rows = content.split(/\r?\n/).filter((row) => row.trim());
  const header = (rows[0] || "").split(/[;,]/).map((cell) => cell.trim());
  return rows.slice(1).map((row, index) => {
    const cells = row.split(/[;,]/).map((cell) => cell.trim());
    const text = cells
      .map((cell, position) => `${header[position] || `colonne ${position + 1}`}: ${cell}`)
      .join(" | ");
    return passage(context, { suffix: `R${index + 2}`, locator: `ligne ${index + 2}`, text });
  });
}

function decodeQuotedPrintable(text) {
  const joined = text.replace(/=\r?\n/g, "");
  const bytes = [];
  for (let index = 0; index < joined.length; index += 1) {
    const hex = joined[index] === "=" ? joined.slice(index + 1, index + 3) : "";
    if (/^[0-9A-F]{2}$/i.test(hex)) {
      bytes.push(parseInt(hex, 16));
      index += 2;
    } else {
      bytes.push(joined.charCodeAt(index) & 255);
    }
  }
  return new TextDecoder("utf-8").decode(Uint8Array.from(bytes));
}

function emailParts(content) {
  const [head, ...rest] = content.split(/\r?\n\r?\n/);
  const headers = {};
  head
    .replace(/\r?\n[ \t]+/g, " ")
    .split(/\r?\n/)
    .forEach((line) => {
      const match = line.match(/^([\w-]+):\s*(.*)$/);
      if (match) headers[match[1].toLowerCase()] = match[2];
    });
  let body = rest.join("\n\n");
  if (/quoted-printable/i.test(headers["content-transfer-encoding"] || ""))
    body = decodeQuotedPrintable(body);
  return { headers, body };
}

function emailDate(value) {
  const time = Date.parse(value || "");
  if (Number.isNaN(time)) return null;
  const match = String(value).match(/([+-])(\d{2})(\d{2})\s*$/);
  if (!match) return new Date(time).toISOString().slice(0, 16) + "Z";
  const minutes = (match[1] === "-" ? -1 : 1) * (Number(match[2]) * 60 + Number(match[3]));
  return new Date(time + minutes * 60000).toISOString().slice(0, 16) + `${match[1]}${match[2]}:${match[3]}`;
}

function splitEmail(context, content) {
  const { headers, body } = emailParts(content);
  const date = emailDate(headers.date);
  const author = (headers.from || "").replace(/<.*>/, "").trim() || null;
  const header = ["from", "to", "date", "subject"]
    .filter((key) => headers[key])
    .map((key) => `${key}: ${headers[key]}`)
    .join("\n");
  const paragraphs = body
    .split(/\r?\n\s*\r?\n/)
    .map((part) => part.replace(/\s+/g, " ").trim())
    .filter(Boolean);
  return [
    passage(context, { suffix: "hdr", locator: "en-tête", text: header, date, author }),
    ...paragraphs.map((text, index) =>
      passage(context, { suffix: `b${index + 1}`, locator: `corps §${index + 1}`, text, date, author }),
    ),
  ];
}

const SPLITTERS = { txt: splitLines, md: splitLines, csv: splitCsv, eml: splitEmail };
const KINDS = { txt: "document", md: "document", csv: "csv", eml: "email" };

async function readPassages(file, version) {
  const type = extension(file.name);
  const content = await file.text();
  const context = {
    version,
    name: file.name,
    stem: file.name.replace(/\.[^.]+$/, "").replace(/\s+/g, "_"),
    kind: KINDS[type],
    date: detectDate(content),
  };
  return SPLITTERS[type](context, content).filter((entry) => entry.text);
}

function documentTitle(path) {
  return basename(path)
    .replace(/\.[^.]+$/, "")
    .replace(/_/g, " ");
}

function referencePassages(model) {
  return model.passages.filter((entry) => entry.typed);
}

function vote(neighbors) {
  const tally = new Map();
  neighbors.forEach(({ item, score }) => {
    const subjectId = subjectForStateKey(item.typed?.subject) || "";
    const entry = tally.get(subjectId) || { subjectId, count: 0, total: 0 };
    entry.count += 1;
    entry.total += score;
    tally.set(subjectId, entry);
  });
  const best = [...tally.values()].sort(
    (left, right) => right.count - left.count || right.total - left.total,
  )[0];
  if (!best?.subjectId || best.count < MAJORITY)
    return { subjectId: null, votes: best?.count || 0, score: null };
  return { subjectId: best.subjectId, votes: best.count, score: best.total / best.count };
}

function nearest(model, references, vector) {
  return references
    .map((entry) => ({ item: entry, score: cosine(vector, model.vectorIndex.get(entry.id)) }))
    .sort((left, right) => right.score - left.score)
    .slice(0, NEIGHBORS);
}

async function semanticLinks(model, passages) {
  const references = referencePassages(model).filter((entry) => model.vectorIndex.has(entry.id));
  if (!references.length) return null;
  const items = passages.map((entry) => ({ text: entry.text, title: documentTitle(entry.path) }));
  const vectors = await embedTexts(embeddingConfig(model.vectors), items, "document");
  if (!vectors) return null;
  const links = {};
  passages.forEach((entry, index) => {
    links[entry.id] = { ...vote(nearest(model, references, vectors[index])), mode: "semantic" };
  });
  return { links, vectors };
}

function lexicalLinks(model, passages) {
  const search = createBm25(
    referencePassages(model).map((entry) => ({ item: entry, tokens: tokens(entry.text) })),
  );
  const mode = model.vectorIndex.size ? "lexical" : "lexical-no-index";
  const links = {};
  passages.forEach((entry) => {
    links[entry.id] = { ...vote(search(entry.text).slice(0, NEIGHBORS)), score: null, mode };
  });
  return { links, vectors: null };
}

function packVectors(passages, vectors) {
  if (!vectors) return null;
  const dim = vectors[0].length;
  const bytes = new Int8Array(passages.length * dim);
  vectors.forEach((vector, row) =>
    vector.forEach((value, column) => {
      bytes[row * dim + column] = Math.max(-127, Math.min(127, Math.round(value * 127)));
    }),
  );
  let binary = "";
  new Uint8Array(bytes.buffer).forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return { ids: passages.map((entry) => entry.id), dim, int8: btoa(binary) };
}

function findDuplicate(model, passages) {
  const known = new Map(model.passages.map((entry) => [normalize(entry.text).replace(/\s+/g, " "), entry]));
  const matches = passages.map((entry) => known.get(normalize(entry.text).replace(/\s+/g, " ")));
  if (!matches.length || matches.some((entry) => !entry)) return null;
  return model.sourceById.get(matches[0].sourceId) || null;
}

function latestDate(passages) {
  return (
    passages
      .map((entry) => entry.date)
      .filter(Boolean)
      .sort()
      .pop() || null
  );
}

function stepRow(label, status, message = "") {
  const tone = { done: "positive", running: "info", error: "critical", waiting: "neutral" }[status];
  const text = { done: "terminé", running: "en cours", error: "erreur", waiting: "en attente" }[status];
  return html`<li class="progress-row">
    ${badge(text, tone)}<span>${label}</span>${message ? html`<span class="muted">${message}</span>` : ""}
  </li>`;
}

function fileRow(file, index) {
  const type = extension(file.name);
  const supported = BROWSER_FORMATS.includes(type);
  const pipeline = PIPELINE_FORMATS.includes(type);
  return html`<li class="file-row">
    <span class="file-name">${icon("file")}${file.name}</span>
    <span class="muted">${Math.max(1, Math.round(file.size / 1024))} Ko</span>
    ${supported ? html`<span></span>` : badge(pipeline ? "format pris en charge par le pipeline" : "format non pris en charge", "warning")}
    <button type="button" class="icon-btn" data-remove="${index}" aria-label="Retirer ${file.name}">
      ${icon("close")}
    </button>
    ${pipeline ? html`<code class="command">${PIPELINE_COMMAND.replace("<fichier>", file.name)}</code>` : ""}
  </li>`;
}

function dialogBody(nextVersion) {
  const readable = dialog.files.filter((file) => BROWSER_FORMATS.includes(extension(file.name)));
  return html`<div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="import-title">
    <header class="modal-head">
      <h2 id="import-title">Importer des documents</h2>
      <button type="button" class="icon-btn" data-action="close" aria-label="Fermer">${icon("close")}</button>
    </header>
    <label class="dropzone" data-dropzone>
      ${icon("upload")}
      <span>Déposez des fichiers ici ou <u>choisissez des fichiers</u></span>
      <span class="muted">Lus ici : .txt, .eml, .md, .csv · traités par le pipeline : .pdf, .xlsx, .png</span>
      <input type="file" multiple accept=".txt,.eml,.md,.csv,.pdf,.xlsx,.png" class="visually-hidden" />
    </label>
    <ul class="file-list">
      ${dialog.files.map(fileRow)}
    </ul>
    ${
      dialog.progress.length
        ? html`<ol class="progress-list">
            ${dialog.progress.map((step) => stepRow(step.label, step.status, step.message))}
          </ol>`
        : ""
    }
    ${dialog.error ? html`<p class="error-line">${dialog.error}</p>` : ""}
    <footer class="modal-foot">
      <button type="button" class="btn btn-tertiary" data-action="close">Annuler</button>
      <button
        type="button"
        class="btn btn-primary"
        data-action="run"
        ${readable.length ? "" : html`disabled`}
      >
        Importer et créer v${nextVersion}
      </button>
    </footer>
  </div>`;
}

function setStep(index, status, message = "") {
  dialog.progress = STEPS.map((label, position) => {
    if (position < index) return { label, status: "done" };
    if (position === index) return { label, status, message };
    return { label, status: "waiting" };
  });
}

async function buildVersion(base, model, render) {
  const number = nextVersionNumber(base);
  const files = dialog.files.filter((file) => BROWSER_FORMATS.includes(extension(file.name)));
  setStep(0, "running");
  render();
  const passages = (await Promise.all(files.map((file) => readPassages(file, number)))).flat();
  setStep(1, "running", `${passages.length} passages`);
  render();
  const duplicate = findDuplicate(model, passages);
  if (!passages.length || duplicate) {
    setStep(1, "error", duplicate ? `Document identique à ${duplicate.title}` : "Aucun passage lisible");
    return null;
  }
  setStep(2, "running");
  render();
  const linked = (await semanticLinks(model, passages)) || lexicalLinks(model, passages);
  setStep(3, "running");
  render();
  const importedAt = new Date().toISOString();
  return {
    n: number,
    asOf: latestDate(passages) || importedAt.slice(0, 10),
    importedAt,
    files: files.map((file) => ({ name: basename(file.name), size: file.size })),
    passages,
    links: linked.links,
    vectors: packVectors(passages, linked.vectors),
  };
}

function closeDialog() {
  mount(document.getElementById("layer"), "");
  dialog.files = [];
  dialog.progress = [];
  dialog.error = "";
}

async function runImport(options, render) {
  const version = await buildVersion(options.base, versionModel(options.base, null), render);
  if (!version) return render();
  if (!saveVersion(version)) {
    dialog.error = "La nouvelle version n'a pas pu être enregistrée dans ce navigateur.";
    return render();
  }
  closeDialog();
  options.onCreated(version.n);
  return null;
}

function addFiles(list) {
  dialog.files = [...dialog.files, ...list];
  dialog.progress = [];
  dialog.error = "";
}

function bindDialog(root, options, render) {
  onDelegate(root, "click", "[data-action='close']", closeDialog);
  onDelegate(root, "click", "[data-remove]", (_, button) => {
    dialog.files.splice(Number(button.dataset.remove), 1);
    render();
  });
  onDelegate(root, "click", "[data-action='run']", (_, button) => {
    button.disabled = true;
    runImport(options, render);
  });
  root.addEventListener("change", (event) => {
    if (event.target.type === "file") {
      addFiles([...event.target.files]);
      render();
    }
  });
  root.addEventListener("dragover", (event) => event.preventDefault());
  root.addEventListener("drop", (event) => {
    event.preventDefault();
    addFiles([...event.dataTransfer.files]);
    render();
  });
}

export function openImportDialog(options) {
  const layer = document.getElementById("layer");
  const shell = document.createElement("div");
  shell.className = "modal";
  layer.replaceChildren(shell);
  const render = () => mount(shell, dialogBody(nextVersionNumber(options.base)));
  bindDialog(shell, options, render);
  shell.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDialog();
  });
  render();
  shell.querySelector("[data-action='close']").focus();
}
