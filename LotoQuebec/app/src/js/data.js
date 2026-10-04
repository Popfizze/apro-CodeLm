import { basename, isoDay, isoTime, normalize } from "./ui.js";

const FILE_ALIASES = {
  kb: ["kb.json", "knowledge.json", "synthese.json", "synthesis.json"],
  state: ["state.json", "state_v1.json"],
  passages: ["passages.jsonl", "passages_v1.jsonl", "passages.json"],
  decisions: ["jev_decisions.json", "decisions.json", "passage_decisions.json"],
  vectors: ["embeddings.json", "vectors.json"],
};

const MAX_PIPELINE_VERSION = 9;

const STATE_SUBJECTS = {
  go_live_date: "S-DATE",
  integration: "S-INT",
  hosting_data_residency: "S-HEB",
  security: "S-SEC",
  accessibility: "S-ACC",
  finance_invoices: "S-FIN",
  vendor_contract: "S-FIN",
  project_scope: "S-PORTEE",
  scope_mobile: "S-PORTEE",
  governance_owner: "S-GOUV",
  operations_runbook: "S-OPS",
  data_quality: "S-DATA",
  performance: "S-PERF",
  status_reporting: "S-COMM",
};

const CONDITION_SUBJECTS = { C1: "S-SEC", C2: "S-ACC", C3: "S-OPS" };

const RISK_SUBJECTS = {
  "R-01": "S-INT",
  "R-02": "S-SEC",
  "R-03": "S-OPS",
  "R-04": "S-ACC",
  "R-05": "S-DATA",
  "R-E1": "S-FIN",
  "R-E2": "S-COMM",
  "R-E3": "S-FIN",
};

const NATURES = {
  decision: { label: "Décision", group: "decision" },
  approbation: { label: "Approbation", group: "decision" },
  approval: { label: "Approbation", group: "decision" },
  changement_responsable: { label: "Changement de responsable", group: "decision" },
  owner_change: { label: "Changement de responsable", group: "decision" },
  proposition: { label: "Proposition", group: "proposal" },
  proposal: { label: "Proposition", group: "proposal" },
  validation: { label: "Validation", group: "validation" },
  constat: { label: "Constat", group: "other" },
  finding: { label: "Constat", group: "other" },
  information: { label: "Information", group: "other" },
  livraison: { label: "Livraison", group: "other" },
  delivery: { label: "Livraison", group: "other" },
  engagement: { label: "Engagement", group: "other" },
  commitment: { label: "Engagement", group: "other" },
  risque: { label: "Risque", group: "other" },
  risk: { label: "Risque", group: "other" },
  facture: { label: "Facture", group: "other" },
  paiement: { label: "Paiement", group: "other" },
  payment: { label: "Paiement", group: "other" },
  invoice: { label: "Facture", group: "other" },
  noise: { label: "Hors sujet", group: "other" },
};

export const NATURE_GROUPS = [
  { id: "decision", label: "Décision" },
  { id: "proposal", label: "Proposition" },
  { id: "validation", label: "Validation" },
  { id: "other", label: "Autres" },
];

const TYPE_BY_FOLDER = {
  "01_": "courriel",
  "02_": "reunion",
  "03_": "ticket",
  "04_": "document",
  "05_": "contrat",
  "06_": "adr",
  "07_": "teams",
  "08_": "archive",
};

const TYPE_LABELS = {
  courriel: "Courriel",
  reunion: "Réunion",
  ticket: "Ticket",
  document: "Document",
  contrat: "Contrat",
  facture: "Facture",
  adr: "Architecture et décision",
  teams: "Teams",
  archive: "Archive",
  import: "Document importé",
};

let cachedPayload = null;
let cachedModel = null;

export function field(source, ...keys) {
  if (!source || typeof source !== "object") return undefined;
  for (const key of keys) {
    if (source[key] != null && source[key] !== "") return source[key];
  }
  return undefined;
}

function list(value) {
  if (Array.isArray(value)) return value;
  return value == null || value === "" ? [] : [value];
}

function text(value) {
  if (value == null) return "";
  if (Array.isArray(value)) return value.map(text).filter(Boolean).join(", ");
  return typeof value === "object" ? "" : String(value);
}

export function readPayload() {
  if (cachedPayload) return cachedPayload;
  const element = document.getElementById("nova-data");
  try {
    cachedPayload = JSON.parse(element?.textContent || "{}");
  } catch {
    cachedPayload = {};
  }
  return cachedPayload;
}

function pickFile(files, kind) {
  const name = FILE_ALIASES[kind].find((candidate) => files[candidate] != null);
  return name ? files[name] : null;
}

export function natureInfo(nature) {
  const key = normalize(nature).replace(/\s+/g, "_");
  return NATURES[key] || { label: text(nature) || "Information", group: "other" };
}

export function typeLabel(type) {
  return TYPE_LABELS[type] || text(type);
}

function sourceType(raw, path) {
  const declared = normalize(field(raw, "type"));
  if (declared) return declared;
  const folder = Object.keys(TYPE_BY_FOLDER).find((prefix) => path.startsWith(prefix));
  return folder ? TYPE_BY_FOLDER[folder] : "document";
}

function normalizeAttachment(raw) {
  return {
    file: text(field(raw, "fichier", "file", "name")),
    note: text(field(raw, "note")),
    sameAs: text(field(raw, "identique_a_source", "same_as", "identical_to")),
  };
}

function normalizeSource(raw) {
  const path = text(field(raw, "path", "fichier", "file"));
  return {
    id: text(field(raw, "id", "source_id")) || path,
    path,
    file: basename(path),
    title: text(field(raw, "titre", "title")) || basename(path),
    type: sourceType(raw, path),
    date: text(field(raw, "date_faits", "date")),
    author: text(field(raw, "auteur", "author")),
    recipients: text(field(raw, "destinataires", "recipients")),
    authority: normalize(field(raw, "autorite", "authority")),
    authorityReason: text(field(raw, "autorite_raison", "authority_reason")),
    summary: text(field(raw, "resume", "summary")),
    fullText: text(field(raw, "texte_integral", "full_text", "text")),
    attachments: list(field(raw, "pieces_jointes", "attachments")).map(normalizeAttachment),
    duplicateOf: text(field(raw, "doublon_de", "duplicate_of", "identical_to")),
    sha: text(field(raw, "sha256", "sha")),
    passages: [],
    subjectIds: [],
    image: null,
    version: 1,
  };
}

function sourceFromPassage(passage) {
  return normalizeSource({ id: passage.source_id || passage.path, path: passage.path });
}

function normalizePassage(raw, order) {
  return {
    id: text(raw.id),
    sourceKey: text(field(raw, "source_id", "source")),
    path: text(field(raw, "path", "file")),
    kind: text(raw.kind),
    locator: text(field(raw, "locator", "repere")),
    displayLocator: text(field(raw, "locator", "repere")),
    date: text(raw.date),
    author: text(raw.author),
    text: text(raw.text),
    attachmentOf: text(field(raw, "attachment_of")),
    duplicateOf: text(field(raw, "duplicate_of")),
    noise: false,
    typed: null,
    order,
    version: 1,
  };
}

function answerValue(answer) {
  if (!answer || typeof answer !== "object") return null;
  if (answer.type === "choice") return answer.choice ?? null;
  if (answer.type === "score") return answer.score ?? null;
  if (answer.type === "noul") return answer.noul ?? null;
  return field(answer, "value", "choice", "score", "noul") ?? null;
}

function answerProbability(answer) {
  if (!answer || typeof answer !== "object") return null;
  if (answer.type === "noul") return answer.noul ?? null;
  const value = answerValue(answer);
  return answer.probabilities?.[String(value)] ?? answer.confidence ?? null;
}

function answerEngine(answers, fallback) {
  const first = Object.values(answers || {}).find((answer) => answer && answer.engine);
  return text(first?.engine || fallback);
}

function normalizeTyped(answers, fallbackEngine) {
  if (!answers || typeof answers !== "object") return null;
  return {
    subject: answerValue(answers.subject),
    nature: answerValue(answers.nature),
    authority: answerValue(answers.authority),
    deadline: answerValue(answers.has_deadline),
    commitment: answerValue(answers.is_commitment_with_owner),
    risk: answerValue(answers.flags_risk),
    probability: {
      subject: answerProbability(answers.subject),
      nature: answerProbability(answers.nature),
      authority: answerProbability(answers.authority),
    },
    engine: answerEngine(answers, fallbackEngine),
  };
}

const JEV_ENGINE = /^(jev|local:[\w.:-]+)$/i;

export function displayEngine(engine) {
  const value = text(engine).trim();
  return JEV_ENGINE.test(value) ? value : "non documenté";
}

function indexSources(rawSources, rawPassages) {
  const sources = rawSources.map(normalizeSource);
  const byPath = new Map(sources.map((source) => [source.path, source]));
  const passages = rawPassages.map(normalizePassage);
  passages.forEach((passage) => {
    let source = byPath.get(passage.path);
    if (!source) {
      source = sourceFromPassage({ source_id: passage.sourceKey, path: passage.path });
      sources.push(source);
      byPath.set(source.path, source);
    }
    passage.sourceId = source.id;
    source.passages.push(passage);
  });
  return { sources, passages };
}

export function hexBytes(value) {
  const bytes = new Uint8Array(value.length / 2);
  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = parseInt(value.slice(index * 2, index * 2 + 2), 16);
  }
  return bytes;
}

function imageUrl(image) {
  if (typeof image === "string") return image;
  if (!image?.hex) return null;
  return URL.createObjectURL(new Blob([hexBytes(image.hex)], { type: image.type || "image/png" }));
}

function attachImages(sources, images) {
  const byName = new Map(
    Object.entries(images || {}).map(([path, image]) => [basename(path), imageUrl(image)]),
  );
  sources.forEach((source) => {
    if (/\.png$/i.test(source.path)) source.image = byName.get(source.file) || null;
  });
}

function normalizeSubjects(kb, state) {
  const descriptions = {};
  Object.entries(state?.subjects || {}).forEach(([key, value]) => {
    const subjectId = STATE_SUBJECTS[key];
    if (subjectId) descriptions[subjectId] = [...(descriptions[subjectId] || []), { key, value }];
  });
  return list(kb.sujets).map((raw) => ({
    id: text(raw.id),
    name: text(field(raw, "nom", "name")),
    sourceIds: list(raw.sources).map(text),
    stateKeys: (descriptions[text(raw.id)] || []).map((entry) => entry.key),
  }));
}

export function subjectForStateKey(key) {
  return STATE_SUBJECTS[key] || null;
}

function citationSource(raw) {
  const passageId = text(field(raw, "passage", "passage_id"));
  return text(field(raw, "source", "fichier", "file", "source_id", "path")) || passageId.split(":")[0];
}

function normalizeRef(raw) {
  if (raw == null) return null;
  if (typeof raw === "string") return { source: raw, locator: "", quote: "", passageId: "" };
  return {
    source: citationSource(raw),
    locator: text(field(raw, "repere", "locator", "reperes")),
    quote: text(field(raw, "citation_courte", "citation", "quote")),
    passageId: text(field(raw, "passage", "passage_id")),
  };
}

function legacyRef(raw) {
  return {
    source: field(raw, "source"),
    repere: field(raw, "repere", "locator"),
    citation: field(raw, "citation"),
  };
}

function evidenceOf(raw, ...keys) {
  const listed = field(raw, ...keys);
  return listed ? refs(listed) : refs(typeof raw?.source === "string" ? legacyRef(raw) : null);
}

export function refs(value) {
  return list(value)
    .map(normalizeRef)
    .filter((ref) => ref && ref.source);
}

function eventDate(raw) {
  const value = text(raw.date);
  return { raw: value, day: isoDay(value), time: isoTime(value) };
}

function normalizeEvent(raw) {
  const date = eventDate(raw);
  return {
    id: text(raw.id),
    date: date.raw,
    day: date.day,
    time: date.time,
    subjectId: text(field(raw, "sujet", "subject")),
    nature: natureInfo(raw.nature),
    natureKey: text(raw.nature),
    summary: text(field(raw, "resume", "summary")),
    actors: list(field(raw, "acteurs", "actors")).map(text),
    refs: evidenceOf(raw, "preuves", "sources"),
    status: normalize(field(raw, "statut", "status")),
    replacedBy: text(field(raw, "remplace_par", "replaced_by")),
    confidence: normalize(field(raw, "confiance", "confidence")),
    quote: text(field(raw, "citation", "quote")) || evidenceOf(raw, "preuves")[0]?.quote || "",
  };
}

function normalizeDecision(raw) {
  return {
    id: text(raw.id),
    subjectId: text(field(raw, "sujet", "subject")),
    statement: text(field(raw, "enonce", "statement")),
    proposedOn: text(field(raw, "date_proposition", "proposed_on")),
    proposedBy: text(field(raw, "proposee_par", "proposed_by")),
    decidedOn: text(field(raw, "date_decision", "decided_on")),
    decidedBy: text(field(raw, "decidee_par", "decided_by")),
    rationale: text(field(raw, "justification", "rationale")),
    refs: refs(field(raw, "sources", "refs")),
    status: text(field(raw, "statut", "status")),
  };
}

function normalizeAction(raw) {
  return {
    id: text(raw.id),
    text: text(field(raw, "action", "text")),
    owner: text(field(raw, "responsable", "owner")),
    ownerStatus: normalize(field(raw, "responsable_statut", "owner_status")),
    due: text(field(raw, "echeance", "due")),
    status: text(field(raw, "statut", "status")),
    refs: refs(field(raw, "preuve", "preuves", "sources", "refs")),
    type: normalize(field(raw, "type")),
    condition: text(field(raw, "condition_golive", "condition")),
  };
}

function riskLevel(level) {
  const match = text(level).match(/Probabilit\S*\s+(\S+)\s*\/\s*Impact\s+(\S+)/i);
  return match ? { probability: match[1], impact: match[2] } : { probability: "", impact: "" };
}

function normalizeRisk(raw) {
  const id = text(raw.id);
  return {
    id,
    statement: text(field(raw, "enonce", "statement")),
    level: text(field(raw, "niveau", "level")),
    ...riskLevel(field(raw, "niveau", "level")),
    owner: text(field(raw, "proprietaire", "owner")),
    registerStatus: text(field(raw, "statut_registre", "register_status")),
    trend: text(field(raw, "tendance", "trend")),
    registerRef: text(field(raw, "source_registre", "register_source")),
    actualState: text(field(raw, "etat_reel_selon_autres_sources", "actual_state")),
    refs: refs(field(raw, "sources", "refs")),
    subjectId: text(field(raw, "sujet", "subject")) || RISK_SUBJECTS[id] || "",
  };
}

function normalizeVersionSide(raw) {
  return {
    statement: text(field(raw, "enonce", "statement", "repere")),
    refs: evidenceOf(raw, "preuves", "sources"),
  };
}

function normalizeContradiction(raw) {
  const prevails = text(field(raw, "prevaut", "prevails")).toUpperCase() || "B";
  return {
    id: text(raw.id),
    subject: text(field(raw, "sujet", "subject")),
    subjectId: text(field(raw, "sujet_id", "subject_id")),
    a: normalizeVersionSide(field(raw, "version_A", "a") || {}),
    b: normalizeVersionSide(field(raw, "version_B", "b") || {}),
    resolution: text(field(raw, "resolution")),
    criterion: normalize(field(raw, "critere", "criterion")),
    inPlanOrRegister: Boolean(field(raw, "au_moins_une_dans_plan_ou_registre", "in_plan_or_register")),
    prevails,
  };
}

function normalizeMissing(raw, index) {
  return {
    id: `M-${String(index + 1).padStart(2, "0")}`,
    subjectId: text(field(raw, "sujet", "subject")),
    info: text(field(raw, "information", "info")),
    toDecide: text(field(raw, "pour_trancher", "to_decide")),
  };
}

function normalizeCondition(raw) {
  const id = text(raw.id);
  const stateKey = Object.keys(raw).find((key) => key.startsWith("etat"));
  const state = text(stateKey ? raw[stateKey] : field(raw, "state", "status"));
  return {
    id,
    text: text(field(raw, "condition", "text")),
    validator: text(field(raw, "responsable_validation", "validator")),
    state,
    unmet: /^non\b/i.test(state),
    actionIds: list(field(raw, "actions", "action_ids")).map(text),
    due: text(field(raw, "echeance", "due")),
    refs: refs(field(raw, "sources", "refs")),
    subjectId: CONDITION_SUBJECTS[id] || "",
  };
}

function normalizeRunbook(raw) {
  if (!raw) return null;
  const evidence = evidenceOf(raw, "preuves", "sources");
  return {
    sourceKey: text(field(raw, "source", "fichier")) || evidence[0]?.source || "",
    refs: evidence,
    file: text(field(raw, "fichier", "file")),
    version: text(field(raw, "version")),
    steps: list(field(raw, "etapes", "steps")).map((step) => ({
      n: Number(field(step, "n", "number")),
      label: text(field(step, "etape", "label")),
      status: text(field(step, "statut", "status")),
    })),
    missingWork: list(field(raw, "travaux_manquants", "missing_work")).map(text),
    extraRequirement: text(field(raw, "exigence_additionnelle", "extra_requirement")),
  };
}

function normalizeGolive(raw) {
  const golive = raw || {};
  return {
    targetDate: text(field(golive, "date_cible", "target_date")),
    dateStatus: text(field(golive, "statut_date", "date_status")),
    conditions: list(field(golive, "conditions")).map(normalizeCondition),
    runbook: normalizeRunbook(field(golive, "runbook_capture", "runbook")),
  };
}

function normalizeInvoiceLine(raw, draftIds) {
  const label = text(field(raw, "description", "label"));
  return {
    label,
    amount: Number(field(raw, "montant", "amount")) || 0,
    unauthorized: draftIds.some((id) => label.includes(id)),
  };
}

function normalizeInvoice(raw, draftIds) {
  const status = text(field(raw, "statut", "status"));
  return {
    id: text(field(raw, "id", "numero")),
    date: text(raw.date),
    amount: Number(field(raw, "montant", "amount")) || 0,
    lines: list(field(raw, "lignes", "lines")).map((line) => normalizeInvoiceLine(line, draftIds)),
    status,
    paid: /pay[ée]e/i.test(status) && !/non pay/i.test(status),
    issue: text(field(raw, "probleme", "issue")),
    refs: refs(field(raw, "sources", "refs")),
  };
}

function normalizeChange(raw) {
  return {
    id: text(raw.id),
    title: text(field(raw, "objet", "title")),
    amount: Number(field(raw, "montant", "montant_estime", "amount")) || 0,
    date: text(field(raw, "date_decision", "date_demande", "date")),
    authority: text(field(raw, "autorite", "authority")),
    status: text(field(raw, "statut", "status")),
    followUp: text(field(raw, "suite", "follow_up")),
    refs: evidenceOf(raw, "preuves", "sources"),
  };
}

function normalizeTotals(raw) {
  const totals = raw || {};
  const number = (...keys) => (field(totals, ...keys) == null ? null : Number(field(totals, ...keys)));
  return {
    authorized: number("autorise", "authorized"),
    billed: number("facture_brut", "billed"),
    eligible: number("facture_admissible", "eligible"),
    paid: number("paye", "paid"),
    pending: number("en_validation", "pending"),
    disputed: number("conteste", "disputed"),
    detail: text(field(totals, "detail")),
  };
}

function normalizeExternal(raw) {
  return {
    id: text(raw.id),
    project: text(field(raw, "projet", "project")),
    date: text(raw.date),
    amount: Number(field(raw, "montant", "amount")) || 0,
    status: text(field(raw, "statut", "status")),
    note: text(raw.note),
    refs: evidenceOf(raw, "preuves", "sources"),
  };
}

function normalizeFinance(raw) {
  const finance = raw || {};
  const contract = field(finance, "contrat", "contract") || {};
  const drafts = list(field(finance, "cr_brouillons", "draft_changes")).map(normalizeChange);
  const draftIds = drafts.map((draft) => draft.id).filter(Boolean);
  return {
    contract: {
      amount: Number(field(contract, "montant_base", "amount")) || null,
      label: text(field(contract, "libelle", "label")),
      period: text(field(contract, "periode", "period")),
      clause: text(field(contract, "clause_changement", "clause")),
      refs: evidenceOf(contract, "preuves", "sources"),
    },
    approvedChanges: list(field(finance, "cr_approuves", "approved_changes")).map(normalizeChange),
    draftChanges: drafts,
    absentChanges: list(field(finance, "cr_absents", "absent_changes")).map(text),
    authorizedCalc: text(field(finance, "calcul_autorise", "authorized_calc")),
    invoices: list(field(finance, "factures", "invoices")).map((invoice) =>
      normalizeInvoice(invoice, draftIds),
    ),
    external: list(field(finance, "hors_projet", "external")).map(normalizeExternal),
    totals: normalizeTotals(field(finance, "totaux", "totals")),
  };
}

function normalizeAnswer(raw) {
  return {
    id: text(field(raw, "q", "id")),
    question: text(raw.question),
    answer: text(field(raw, "reponse", "answer")),
    refs: refs(field(raw, "sources", "refs")),
  };
}

function normalizePerson(raw) {
  return {
    name: text(field(raw, "nom", "name")),
    organization: text(field(raw, "organisation", "organization")),
    role: text(raw.role),
    period: text(field(raw, "periode", "period")),
    sourceIds: list(raw.sources).map(text),
  };
}

function normalizeBrief(raw) {
  const brief = raw || {};
  return {
    owner: text(field(brief, "responsable", "owner")),
    dateAndConditions: text(field(brief, "date_approuvee_et_conditions", "date_and_conditions")),
    scope: text(field(brief, "portee", "scope")),
    budget: text(field(brief, "budget")),
    invoices: text(field(brief, "factures", "invoices")),
    priorities: list(field(brief, "priorites", "priorities")).map(text),
  };
}

const COUNTER_KEYS = {
  passages: "passages",
  sources: "sources",
  duplicates: "duplicates",
  passageDecisions: "passage_decisions",
  pairs: "pairs",
  contradictions: "contradictions",
  supersessions: "supersessions",
  blockedSupersessions: "supersessions_blocked_by_guards",
  noisePassages: "noise_passages",
};

function normalizeCounters(state, kb) {
  const counters = state?.counters || {};
  const result = Object.fromEntries(
    Object.entries(COUNTER_KEYS).map(([name, key]) => [name, counters[key] ?? null]),
  );
  return {
    ...result,
    corpusFiles: kb?.meta?.nb_sources ?? null,
    verifiedCitations: kb?.meta?.nb_citations_verifiees ?? null,
  };
}

function normalizeRules(state) {
  return Object.entries(state?.rules || {}).map(([id, value]) => ({ id, text: text(value) }));
}

function linkSubjectsToSources(subjects, sourceById) {
  subjects.forEach((subject) => {
    subject.sourceIds.forEach((id) => sourceById.get(id)?.subjectIds.push(subject.id));
  });
}

function applyTyped(passages, decisionsFile) {
  const answers = decisionsFile?.passages || {};
  passages.forEach((passage) => {
    passage.typed = normalizeTyped(answers[passage.id], decisionsFile?.engine);
  });
}

function markNoise(passages, state) {
  const noise = new Set(list(state?.noise_passages).map(text));
  passages.forEach((passage) => {
    passage.noise = noise.has(passage.id);
  });
}

function authorityLabels(decisionsFile) {
  const criteria = decisionsFile?.questions?.passage?.authority?.criteria;
  return list(criteria).map((entry) => text(entry).split(/\s+:/)[0].trim());
}

export function typedDecisions(decisionsFile) {
  const answers = decisionsFile?.passages || {};
  return Object.fromEntries(
    Object.entries(answers).map(([id, entry]) => [id, normalizeTyped(entry, decisionsFile?.engine)]),
  );
}

function pipelineVersion(files, n) {
  const state = files[`state_v${n}.json`];
  if (!state || typeof state !== "object") return null;
  const newIds = new Set(list(state.event?.passages).map(text));
  return {
    n,
    asOf: text(state.as_of),
    files: [{ name: basename(text(state.event?.file)) }],
    passages: list(files[`passages_v${n}.jsonl`]).filter((entry) => newIds.has(entry.id)),
    typed: typedDecisions(files[`jev_decisions_v${n}.json`]),
    diff: files[`diff_v${n - 1}_v${n}.json`] || null,
    vectors: files[`embeddings_v${n}.json`] || null,
  };
}

function pipelineVersions(files) {
  const versions = [];
  for (let n = 2; n <= MAX_PIPELINE_VERSION; n += 1) {
    const version = pipelineVersion(files, n);
    if (version) versions.push(version);
  }
  return versions;
}

function corpusModel(payload, kb, state, decisionsFile) {
  const { sources, passages } = indexSources(
    list(kb.sources),
    list(pickFile(payload.files || {}, "passages")),
  );
  const sourceById = new Map(sources.map((source) => [source.id, source]));
  const subjects = normalizeSubjects(kb, state);
  const conventions = text(kb.meta?.conventions);
  markNoise(passages, state);
  applyTyped(passages, decisionsFile);
  attachImages(sources, payload.images);
  linkSubjectsToSources(subjects, sourceById);
  return {
    conventions,
    sources,
    sourceById,
    passages,
    passageById: new Map(passages.map((passage) => [passage.id, passage])),
    subjects,
    subjectById: new Map(subjects.map((subject) => [subject.id, subject])),
  };
}

function synthesisModel(kb) {
  return {
    people: list(kb.personnes).map(normalizePerson),
    events: list(kb.evenements).map(normalizeEvent),
    decisions: list(kb.decisions).map(normalizeDecision),
    actions: list(field(kb, "engagements_actions", "actions")).map(normalizeAction),
    risks: list(field(kb, "risques", "risks")).map(normalizeRisk),
    contradictions: list(kb.contradictions).map(normalizeContradiction),
    missing: list(field(kb, "manquants", "missing")).map(normalizeMissing),
    finance: normalizeFinance(kb.finances),
    golive: normalizeGolive(kb.golive),
    answers: list(field(kb, "reponses", "answers")).map(normalizeAnswer),
    examples: list(field(kb, "exemples", "examples")).map(normalizeAnswer),
    brief: normalizeBrief(kb.brief),
  };
}

function stateModel(payload, kb, state, decisionsFile) {
  return {
    project: text(kb.meta?.projet) || "NOVA",
    asOf: text(field(state, "as_of") || kb.meta?.date_reference),
    stateVersion: text(state.version),
    builtAt: text(payload.builtAt),
    readme: text(payload.readme),
    engine: text(decisionsFile?.engine || state.engine),
    authorityLabels: authorityLabels(decisionsFile),
    rules: normalizeRules(state),
    counters: normalizeCounters(state, kb),
    stateSubjects: state.subjects || {},
  };
}

function buildModel(payload) {
  const files = payload.files || {};
  const kb = pickFile(files, "kb") || {};
  const state = pickFile(files, "state") || {};
  const decisionsFile = pickFile(files, "decisions");
  return {
    ...stateModel(payload, kb, state, decisionsFile),
    ...corpusModel(payload, kb, state, decisionsFile),
    ...synthesisModel(kb),
    vectors: pickFile(files, "vectors"),
    pipelineVersions: pipelineVersions(files),
    files,
  };
}

export function baseModel() {
  if (!cachedModel) cachedModel = buildModel(readPayload());
  return cachedModel;
}

export function subjectName(model, subjectId) {
  return model.subjectById.get(subjectId)?.name || subjectId || "";
}

export function sourceTitle(model, sourceKey) {
  const source = findSource(model, sourceKey);
  return source ? source.title : sourceKey;
}

export function findSource(model, key) {
  if (!key) return null;
  if (model.sourceById.has(key)) return model.sourceById.get(key);
  const wanted = normalize(String(key).replace(/\\/g, "/"));
  const file = normalize(basename(key));
  return (
    model.sources.find((source) => normalize(source.path) === wanted) ||
    model.sources.find((source) => normalize(source.file) === file) ||
    model.sources.find((source) => wanted.endsWith("/" + normalize(source.file))) ||
    null
  );
}

export function personNames(model) {
  return model.people
    .filter((person) => person.organization && !/gouvernance|divers/i.test(person.organization))
    .map((person) => person.name.replace(/\s+Inc\.?$/i, ""))
    .filter((name) => !/\(/.test(name));
}

export function actionTone(status) {
  const value = normalize(status).trim();
  if (value.startsWith("realise")) return "positive";
  if (value.startsWith("en retard")) return "critical";
  if (/^(en cours|planifie|en attente|partiel)/.test(value)) return "warning";
  if (/^(a faire|ouvert|non realise)/.test(value)) return "info";
  return "neutral";
}

export function isOpenAction(action) {
  return actionTone(action.status) !== "positive";
}

export function shortStatus(status) {
  return text(status)
    .split(/\s+[—–-]\s+|;|\(/)[0]
    .trim();
}

export function isPreparedAnswerId(id) {
  return /^(Q\d{2}|EX\d+)$/i.test(id);
}
