import { displayEngine } from "../data.js";
import { href } from "../router.js";
import { basename, card, formatDateTime, formatNumber, html, icon } from "../ui.js";

function count(value, unit) {
  return value == null ? "non documenté" : `${formatNumber(value)} ${unit}`;
}

function extensions(model) {
  const counts = new Map();
  model.sources
    .filter((source) => source.version === 1)
    .forEach((source) => {
      const extension = (basename(source.path).split(".").pop() || "").toLowerCase();
      counts.set(extension, (counts.get(extension) || 0) + 1);
    });
  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1])
    .map(([extension, total]) => `${total} .${extension}`);
}

function contractQuestions(model) {
  const questions = model.files["jev_decisions.json"]?.questions || {};
  return Object.entries(questions).flatMap(([scope, entries]) =>
    Object.entries(entries || {}).map(([name, question]) => ({ scope, name, question })),
  );
}

function questionList(model) {
  return contractQuestions(model).map(
    ({ scope, name, question }) =>
      `${scope === "pair" ? "Paire" : "Passage"} · ${name} (${question.type || "type non documenté"}) : ${question.instructions || ""}`,
  );
}

function typeSummary(model) {
  const counts = new Map();
  contractQuestions(model).forEach(({ question }) =>
    counts.set(question.type, (counts.get(question.type) || 0) + 1),
  );
  const parts = [...counts.entries()].map(([type, total]) => `${total} ${type || "non documenté"}`);
  return parts.length ? parts.join(", ") : "non documenté";
}

function outputFile(model, ...names) {
  return names.filter((name) => model.files[name] != null);
}

function stepReading(model) {
  const attachments = model.passages.filter((passage) => passage.attachmentOf).length;
  return {
    name: "Lecture des fichiers",
    figure: count(model.counters.sources, "fichiers du corpus"),
    role: "Chaque fichier du corpus est lu dans son format d'origine, pièces jointes de courriels comprises.",
    inputs: ["data/corpus"],
    outputs: outputFile(model, "passages.jsonl", "sources.json"),
    facts: [
      `Formats : ${extensions(model).join(", ")}`,
      `${attachments} pièces jointes décodées`,
      `${count(model.counters.sources, "fichiers analysés")} · ${count(model.counters.corpusFiles, "sources décrites dans la mémoire")}`,
    ],
    rules: [],
  };
}

function stepDedup(model) {
  return {
    name: "Dédoublonnage",
    figure: count(model.counters.duplicates, "doublons"),
    role: "Un même contenu présent dans plusieurs fichiers est repéré et relié à son original.",
    inputs: outputFile(model, "passages.jsonl"),
    outputs: outputFile(model, "passages.jsonl"),
    facts: [`${count(model.counters.duplicates, "passages en doublon")}`],
    rules: model.rules.filter((rule) => rule.id === "R5"),
  };
}

function stepPassages(model) {
  return {
    name: "Passages repérés",
    figure: count(model.counters.passages, "passages"),
    role: "Chaque fichier est découpé en passages munis d'un repère précis : ligne, horodatage, cellule, page, paragraphe ou zone de capture.",
    inputs: ["data/corpus"],
    outputs: outputFile(model, "passages.jsonl"),
    facts: [
      model.conventions,
      "Champs d'un passage : identifiant, source, chemin, type, repère, date, auteur, texte, pièce jointe de, doublon de, empreinte",
    ],
    rules: [],
  };
}

function stepTyping(model) {
  return {
    name: "Décisions typées JEV",
    central: true,
    figure: `${count(model.counters.passageDecisions, "décisions")} · ${count(model.counters.pairs, "paires")}`,
    role:
      "Étape centrale du pipeline. Chaque passage, puis chaque paire de passages plausible, est soumis au contrat de décisions JEV : " +
      "réponses typées noul (vrai ou faux, valeur de 0 à 1), choice (une option parmi des critères) et score (échelle numérique) " +
      "sur le sujet, la nature, l'autorité, l'échéance, l'engagement et le risque, puis contredit et remplace pour les paires. " +
      "Avec une clé TYPESAFE_API_KEY, l'appel part vers JEV; sans clé, le même contrat JEV est exécuté par le moteur local. " +
      "Chaque décision porte le moteur qui l'a produite; la consolidation s'appuie uniquement sur ces décisions.",
    inputs: outputFile(model, "passages.jsonl"),
    outputs: outputFile(model, "jev_decisions.json"),
    facts: [
      `Moteur réel lu dans les données : ${displayEngine(model.engine)}`,
      `Questions du contrat : ${typeSummary(model)}`,
      ...questionList(model),
    ],
    rules: [],
  };
}

function stepConsolidation(model) {
  return {
    name: "Consolidation",
    figure: `${count(model.counters.contradictions, "contradictions")} · ${count(model.counters.supersessions, "remplacements")}`,
    role: "Les réponses typées sont consolidées en un état par sujet : énoncé courant, appuis, énoncés remplacés et contradictions.",
    inputs: outputFile(model, "passages.jsonl", "jev_decisions.json"),
    outputs: outputFile(model, "state.json"),
    facts: [
      `${count(model.counters.blockedSupersessions, "remplacements bloqués par les garde-fous")}`,
      `${count(model.counters.noisePassages, "passages hors sujet")}`,
      `État ${model.stateVersion || "v1"} au ${formatDateTime(model.files["state.json"]?.as_of || model.asOf)}`,
    ],
    rules: model.rules,
  };
}

function stepSynthesis(model) {
  return {
    name: "Synthèse sourcée",
    figure: `${count(model.events.length, "événements")} · ${count(model.decisions.length, "décisions")}`,
    role: "L'état consolidé est rédigé en mémoire de projet; chaque élément porte ses sources et ses repères.",
    inputs: outputFile(model, "state.json", "passages.jsonl"),
    outputs: outputFile(model, "kb.json"),
    facts: [
      `${model.events.length} événements, ${model.decisions.length} décisions, ${model.actions.length} actions`,
      `${model.risks.length} risques, ${model.contradictions.length} contradictions, ${model.missing.length} informations manquantes`,
      `${model.answers.length} réponses aux questions du défi`,
    ],
    rules: [],
  };
}

function stepVerification(model) {
  const answerRefs = model.answers.reduce((sum, entry) => sum + entry.refs.length, 0);
  const exampleRefs = model.examples.reduce((sum, entry) => sum + entry.refs.length, 0);
  return {
    name: "Contre-vérification",
    figure: count(answerRefs + exampleRefs, "citations"),
    role: "Chaque citation des réponses est rapprochée de son passage dans le corpus.",
    inputs: outputFile(model, "kb.json", "passages.jsonl"),
    outputs: [],
    facts: [
      `${answerRefs} citations dans les réponses Q01-Q10`,
      `${exampleRefs} citations dans les questions d'exemple`,
      model.counters.verifiedCitations != null
        ? `${formatNumber(model.counters.verifiedCitations)} citations vérifiées : extrait exact retrouvé dans le passage cité`
        : "Résultat détaillé de la vérification : non documenté",
    ],
    rules: [],
  };
}

function stepIndex(model) {
  const vectors = model.vectors;
  return {
    name: "Index de recherche",
    figure: count(model.counters.passages, "passages"),
    role: "Les passages sont indexés pour la recherche dans Explorer › Interroger.",
    inputs: outputFile(model, "passages.jsonl"),
    outputs: outputFile(model, "embeddings.json", "vectors.json"),
    facts: [
      vectors?.ids
        ? `${formatNumber(vectors.ids.length)} vecteurs de dimension ${vectors.dimension ?? vectors.dim ?? "non documentée"}`
        : "Index de vecteurs : non documenté",
    ],
    rules: [],
  };
}

function stepPublication(model) {
  return {
    name: "Publication",
    figure: "1 fichier HTML autonome",
    role: "Les sorties, les captures et l'index sont intégrés dans un seul fichier qui s'ouvre hors ligne.",
    inputs: Object.keys(model.files),
    outputs: ["app/dist/index.html"],
    facts: [`Construit le ${formatDateTime(model.builtAt)}`],
    rules: [],
  };
}

function stepImport(model) {
  return {
    name: "Import d'un document",
    figure: "nouvelle version",
    role: "Un document importé crée une nouvelle version à côté de la version de référence, qui reste figée.",
    inputs: [".txt", ".eml", ".md", ".csv"],
    outputs: [],
    facts: [`${model.versions.length} version(s) disponible(s)`],
    rules: model.rules.filter((rule) => ["R2", "R3"].includes(rule.id)),
  };
}

const STEPS = [
  stepReading,
  stepDedup,
  stepPassages,
  stepTyping,
  stepConsolidation,
  stepSynthesis,
  stepVerification,
  stepIndex,
  stepPublication,
  stepImport,
];

function diagram(steps, active) {
  return html`<ol class="pipeline">
    ${steps.map(
      (step, index) =>
        html`<li class="pipeline-item">
          <a
            class="pipeline-node ${index + 1 === active ? "is-active" : ""} ${step.central ? "is-central" : ""}"
            href="${href(`#/documentation/pipeline/${index + 1}`)}"
            ${index + 1 === active ? html`aria-current="step"` : ""}
          >
            <span class="pipeline-n">${index + 1}</span>
            <span class="pipeline-name">${step.name}</span>
            <span class="pipeline-figure">${step.figure}</span>
          </a>
          ${index < steps.length - 1 ? html`<span class="pipeline-arrow" aria-hidden="true">${icon("arrow")}</span>` : ""}
        </li>`,
    )}
  </ol>`;
}

function detail(step, number) {
  return card({
    title: `${number}. ${step.name}`,
    body: html`<div class="step-detail">
      <div>
        <h3 class="block-title">Rôle</h3>
        <p>${step.role}</p>
        <h3 class="block-title">Entrées → sorties</h3>
        <p>
          <span class="mono">${step.inputs.join(", ") || "—"}</span> →
          <span class="mono">${step.outputs.join(", ") || "—"}</span>
        </p>
      </div>
      <div>
        <h3 class="block-title">Chiffres</h3>
        <ul class="plain-list bullets">
          ${step.facts.filter(Boolean).map((fact) => html`<li>${fact}</li>`)}
        </ul>
        ${
          step.rules.length
            ? html`<h3 class="block-title">Règles</h3>
                <ul class="plain-list bullets">
                  ${step.rules.map((rule) => html`<li><b>${rule.id}</b> ${rule.text}</li>`)}
                </ul>`
            : ""
        }
      </div>
    </div>`,
  });
}

export function render({ model, params }) {
  const steps = STEPS.map((build) => build(model));
  const active = Math.min(steps.length, Math.max(1, Number(params.step) || 1));
  return {
    crumbs: [{ label: `${active}. ${steps[active - 1].name}` }],
    keepScroll: true,
    body: html`<div class="grid">
      <section class="card span-12 pipeline-card">${diagram(steps, active)}</section>
      ${detail(steps[active - 1], active)}
    </div>`,
  };
}
