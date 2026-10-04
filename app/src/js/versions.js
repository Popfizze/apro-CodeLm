import { subjectForStateKey } from "./data.js";
import { decodeVectors } from "./search.js";
import { basename, isoDay, storageGet, storageSet } from "./ui.js";

const STORAGE_KEY = "nova.versions";
const models = new Map();
let revision = 0;

function readLocalVersions() {
  try {
    const parsed = JSON.parse(storageGet(STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function referenceVersion(base) {
  return { n: 1, asOf: base.asOf, files: [], frozen: true, origin: "reference", passages: [], links: {} };
}

function pipelineLinks(entry) {
  return Object.fromEntries(
    entry.passages.map((raw) => [
      raw.id,
      { subjectId: subjectForStateKey(entry.typed[raw.id]?.subject), score: null, mode: "pipeline" },
    ]),
  );
}

function pipelineVersion(entry) {
  return { ...entry, frozen: false, origin: "pipeline", links: pipelineLinks(entry) };
}

export function allVersions(base) {
  const pipeline = base.pipelineVersions.map(pipelineVersion);
  const local = readLocalVersions().map((entry) => ({ ...entry, origin: "import", frozen: false }));
  return [referenceVersion(base), ...pipeline, ...local].sort((left, right) => left.n - right.n);
}

export function nextVersionNumber(base) {
  return Math.max(...allVersions(base).map((version) => version.n)) + 1;
}

export function saveVersion(version) {
  const versions = readLocalVersions().filter((entry) => entry.n !== version.n);
  const stored = storageSet(STORAGE_KEY, JSON.stringify([...versions, version]));
  revision += 1;
  models.clear();
  return stored;
}

export function removeVersion(n) {
  storageSet(STORAGE_KEY, JSON.stringify(readLocalVersions().filter((entry) => entry.n !== n)));
  revision += 1;
  models.clear();
}

function importedSource(passages, version, fileName) {
  const first = passages[0];
  return {
    id: `v${version.n}:${fileName}`,
    path: first.path,
    file: fileName,
    title: fileName,
    type: "import",
    date: first.date || version.asOf,
    author: first.author || "",
    recipients: "",
    authority: "non évaluée",
    authorityReason: "",
    summary: "",
    fullText: "",
    attachments: [],
    duplicateOf: "",
    sha: "",
    passages,
    subjectIds: [],
    image: null,
    version: version.n,
  };
}

function importedPassage(raw, version, order) {
  return {
    id: raw.id,
    sourceKey: raw.source_id,
    path: raw.path,
    kind: raw.kind,
    locator: raw.locator,
    displayLocator: raw.locator,
    date: raw.date || "",
    author: raw.author || "",
    text: raw.text,
    attachmentOf: "",
    duplicateOf: raw.duplicate_of || "",
    noise: false,
    typed: version.typed?.[raw.id] || null,
    order,
    version: version.n,
    link: version.links?.[raw.id] || null,
  };
}

function versionSources(version) {
  const byFile = new Map();
  (version.passages || []).forEach((raw, order) => {
    const fileName = basename(raw.path);
    const passage = importedPassage(raw, version, order);
    byFile.set(fileName, [...(byFile.get(fileName) || []), passage]);
  });
  return [...byFile.entries()].map(([fileName, passages]) => {
    const source = importedSource(passages, version, fileName);
    passages.forEach((passage) => {
      passage.sourceId = source.id;
    });
    return source;
  });
}

function linkedSubjects(sources) {
  const subjects = new Map();
  sources
    .flatMap((source) => source.passages)
    .forEach((passage) => {
      const subjectId = passage.link?.subjectId;
      if (subjectId) subjects.set(subjectId, [...(subjects.get(subjectId) || []), passage]);
    });
  return subjects;
}

function addImportedVectors(index, version) {
  const vectors = version.vectors;
  if (!vectors?.int8) return;
  decodeVectors(vectors).forEach((entry, id) => index.set(id, entry));
}

function baseVectorIndex(base) {
  if (!base.vectorIndex) base.vectorIndex = decodeVectors(base.vectors);
  return base.vectorIndex;
}

export function diffSubjects(diff) {
  return Object.keys(diff?.subjects || {})
    .map(subjectForStateKey)
    .filter(Boolean);
}

function reviewSubjects(imported, included) {
  const subjects = new Set(linkedSubjects(imported).keys());
  included.forEach((version) => diffSubjects(version.diff).forEach((id) => subjects.add(id)));
  return subjects;
}

function overlay(base, target, versions) {
  const included = versions.filter((version) => version.n > 1 && version.n <= target.n);
  const importedByVersion = included.map((version) => ({ version, sources: versionSources(version) }));
  const imported = importedByVersion.flatMap((entry) => entry.sources);
  const latest = importedByVersion.find((entry) => entry.version.n === target.n);
  const vectorIndex = new Map(baseVectorIndex(base));
  included.forEach((version) => addImportedVectors(vectorIndex, version));
  const passages = [...base.passages, ...imported.flatMap((source) => source.passages)];
  const sources = [...imported, ...base.sources];
  return {
    ...base,
    asOf: target.asOf || base.asOf,
    version: target,
    versions,
    sources,
    sourceById: new Map(sources.map((source) => [source.id, source])),
    passages,
    passageById: new Map(passages.map((passage) => [passage.id, passage])),
    vectorIndex,
    lexicalSearch: null,
    reviewSubjects: reviewSubjects(imported, included),
    changes: latest
      ? {
          sources: latest.sources,
          subjects: linkedSubjects(latest.sources),
          diff: latest.version.diff || null,
        }
      : null,
  };
}

function referenceModel(base, target, versions) {
  return {
    ...base,
    version: target,
    versions,
    vectorIndex: baseVectorIndex(base),
    reviewSubjects: new Set(),
    changes: null,
  };
}

export function versionModel(base, requested) {
  const versions = allVersions(base);
  const target = versions.find((version) => version.n === requested) || versions[versions.length - 1];
  const key = `${revision}:${target.n}`;
  if (!models.has(key)) {
    const model = target.n === 1 ? referenceModel(base, target, versions) : overlay(base, target, versions);
    models.set(key, model);
  }
  return models.get(key);
}

export function isLatest(model) {
  return model.version.n === model.versions[model.versions.length - 1].n;
}

export function previousVersion(model) {
  return model.versions.filter((version) => version.n < model.version.n).pop() || null;
}

export function currentStatement(base, subjectId) {
  return Object.entries(base.stateSubjects)
    .filter(([key]) => subjectForStateKey(key) === subjectId)
    .map(([key, value]) => ({ key, description: value?.description || "", current: value?.current || null }));
}

export function versionDay(model) {
  return isoDay(model.asOf);
}
