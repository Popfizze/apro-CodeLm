import { natureInfo } from "../data.js";
import { href } from "../router.js";
import { card, html, normalize } from "../ui.js";
import { plural } from "../views.js";

const DELIVERABLE_LINKS = [
  [{ label: "Brief de reprise", path: "#/rapports/brief" }],
  [
    { label: "Chronologie", path: "#/historique" },
    { label: "Événements", path: "#/historique/evenements" },
    { label: "Sources", path: "#/explorer/sources" },
    { label: "Suivi", path: "#/suivi" },
  ],
  [{ label: "Réponses Q01-Q10", path: "#/documentation/reponses/Q01" }],
  [{ label: "Suivi et sélecteur de version", path: "#/suivi" }],
  [],
];

function readmeSections(readme) {
  const sections = new Map();
  let current = "";
  readme.split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim();
    if (trimmed && trimmed === trimmed.toUpperCase() && /[A-ZÉ]{4}/.test(trimmed)) {
      current = normalize(trimmed);
      sections.set(current, []);
    } else if (current && trimmed) {
      sections.get(current).push(trimmed);
    }
  });
  return sections;
}

function section(sections, prefix) {
  const key = [...sections.keys()].find((name) => name.startsWith(prefix));
  return key ? sections.get(key) : [];
}

function consignesCard(sections) {
  const mission = section(sections, "mission");
  const rules = section(sections, "regles de lecture");
  return card({
    title: "Consignes en bref",
    span: 6,
    body: html`${mission.map((line) => html`<p>${line}</p>`)}
      <h3 class="block-title">Règles de lecture</h3>
      <ul class="plain-list bullets">
        ${rules.map((line) => html`<li>${line.replace(/^-\s*/, "")}</li>`)}
      </ul>`,
  });
}

function deliverablesCard(sections) {
  const items = section(sections, "livrables").filter((line) => /^\d+\./.test(line));
  return card({
    title: "Livrables",
    span: 6,
    body: html`<ol class="plain-list deliverables">
      ${items.map((line, index) => {
        const links = DELIVERABLE_LINKS[index] || [];
        return html`<li>
          <p>${line.replace(/^\d+\.\s*/, "")}</p>
          <span class="chips"
            >${links.length ? links.map((entry) => html`<a class="tag is-link" href="${href(entry.path)}">${entry.label}</a>`) : html`<span class="tag">README.md à la racine du dépôt (hors application)</span>`}</span
          >
        </li>`;
      })}
    </ol>`,
  });
}

function natureCounts(model) {
  const counts = new Map();
  model.events.forEach((event) => {
    const label = natureInfo(event.natureKey).label;
    counts.set(label, (counts.get(label) || 0) + 1);
  });
  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1])
    .map(([label, count]) => `${count} ${label.toLowerCase()}`)
    .join(", ");
}

function evidenceFor(model, criterion) {
  const key = normalize(criterion);
  const refs = model.answers.reduce((sum, answer) => sum + answer.refs.length, 0);
  const actions = new Set(model.golive.conditions.flatMap((condition) => condition.actionIds)).size;
  const inPlan = model.contradictions.filter((entry) => entry.inPlanOrRegister).length;
  const table = [
    [
      "reponses",
      `${plural(model.answers.length, "réponse")} avec ${refs} repères (fichier et repère)`,
      "#/documentation/reponses/Q01",
    ],
    [
      "preuves",
      `${plural(model.sources.length, "source")} consultables; chaque puce ouvre le passage surligné`,
      "#/explorer/sources",
    ],
    [
      "chronologie",
      `${plural(model.events.length, "événement")} (${natureCounts(model)}); ${model.contradictions.length} contradictions dont ${inPlan} dans un plan ou un registre`,
      "#/historique",
    ],
    [
      "brief",
      `${plural(model.golive.conditions.length, "condition")} reliées à ${plural(actions, "action")}; brief d'une page imprimable`,
      "#/rapports/brief",
    ],
    [
      "utilisation",
      `${plural(model.passages.length, "passage")} interrogeables; ${plural(model.missing.length, "information manquante", "informations manquantes")}`,
      "#/explorer",
    ],
    [
      "mise a jour",
      `${plural(model.versions.length, "version")}; la v1 reste figée et consultable`,
      "#/suivi",
    ],
  ];
  return table.find(([word]) => key.includes(word)) || null;
}

function scoringCard(model, sections) {
  const lines = section(sections, "evaluation").filter((line) => /^-\s.*:\s*\d+\s*points?/i.test(line));
  return card({
    title: "Couverture du barème",
    body: html`<table class="data-table">
      <thead>
        <tr>
          <th>Critère</th>
          <th>Points</th>
          <th>Ce que l'application montre</th>
          <th>Où</th>
        </tr>
      </thead>
      <tbody>
        ${lines.map((line) => {
          const [criterion, points] = line.replace(/^-\s*/, "").split(/\s*:\s*/);
          const evidence = evidenceFor(model, criterion);
          return html`<tr>
            <td>${criterion}</td>
            <td class="num">${points.split(".")[0]}</td>
            <td>${evidence ? evidence[1] : ""}</td>
            <td>${evidence ? html`<a href="${href(evidence[2])}">Ouvrir</a>` : ""}</td>
          </tr>`;
        })}
      </tbody>
    </table>`,
  });
}

export function render({ model }) {
  const sections = readmeSections(model.readme);
  return {
    body: html`<div class="grid">
      ${consignesCard(sections)} ${deliverablesCard(sections)} ${scoringCard(model, sections)}
    </div>`,
  };
}
