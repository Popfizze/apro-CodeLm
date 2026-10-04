# Mémoire NOVA — Projet 360

Équipe **apro** (Jeremy Vong, Sheng He Ge, Bryan Sanchez) · Défi **Loto-Québec – Projet 360 / NOVA** · CodeML 2026.

Les 62 documents du projet NOVA (courriels, comptes rendus, tickets, plans, contrats, factures, décisions, Teams) deviennent une mémoire consultable au 30 septembre 2026, 9 h (Montréal). Chaque réponse renvoie au passage exact qui la prouve. Un nouveau document produit une nouvelle version sans effacer la précédente.

## Regarder le projet

1. Ouvrir `app/dist/index.html` dans un navigateur. Le fichier est autonome et fonctionne hors ligne.
2. Pour la recherche sémantique, servir l'app en local avec Ollama lancé :
   ```
   python -m http.server 8765 -d app/dist
   ```
   puis ouvrir http://localhost:8765. Sans Ollama, la recherche se fait par mots.

`app/dist/index.html` contient le texte du corpus : il n'est pas versionné. Il est joint à la remise Devpost, ou se reconstruit (voir plus bas).

## Navigation

| Section | Contenu |
|---|---|
| Vue d'ensemble | Date de mise en production et ses trois conditions, prochaines actions, risques, factures, budget |
| Explorer | Questions en langage naturel avec leurs passages sources ; tableau des 62 documents et page de chaque document |
| Historique | Événements par jour ; tableau des événements, décisions, contradictions et informations manquantes |
| Suivi | Ce qui reste à faire et par qui ; versions et changements après import d'un document |
| Rapports | Brief de reprise d'une page, briefing exécutif, dossier décisions et preuves, portefeuille NOVA / ORION |
| Documentation | Pipeline, livrables du défi, réponses Q01 à Q10 |

Le fil d'Ariane indique l'écran courant. Chaque puce de source ouvre le document sur le passage cité. Le bouton **Importer** (en haut à droite) ajoute un document et crée une version 2 à côté de la version 1.

## Organisation

```
pipeline/           traitement du corpus (python -m pipeline)
  ingest/           découpage en passages : courriels, PDF, Excel, texte, captures
  jev/              décisions typées au contrat JEV (contract.json)
  content/kb.json   réponses rédigées, vérifiées contre les sources à chaque exécution
app/
  src/              interface (HTML, CSS, modules JavaScript)
  build.py          assemble app/dist/index.html avec les données
data/corpus/        corpus NOVA (non versionné)
out/                sorties du pipeline (non versionné)
```

## Reconstruire

Prérequis : Python 3.12 ou plus, Ollama avec `qwen3:8b`, `qwen2.5vl:7b` et `embeddinggemma`.

```
pip install -e .
python -m pipeline
python app/build.py
```

Le corpus se place dans `data/corpus/Projet360_NOVA_ETUDIANTS/`. Sous Windows, définir `PYTHONIOENCODING=utf-8`.

Nouvelle information : `python -m pipeline --event <fichier>` écrit la version 2 et la liste des changements à côté de la version 1, puis `python app/build.py`.

## Pipeline

1. Contrôle du corpus contre son manifeste.
2. Passages avec repère : page, cellule, ligne horodatée, paragraphe de courriel, ligne de capture.
3. Dédoublonnage : une pièce jointe identique à un fichier n'est pas une seconde preuve.
4. **JEV** : décisions typées `choice`, `score` et `noul` par passage (sujet, nature, autorité, échéance, engagement, risque) et par paire (contredit, remplace). Avec `TYPESAFE_API_KEY`, le contrat est envoyé à JEV ; sans clé, il est exécuté par `qwen3:8b` en local. Le moteur réel est inscrit dans chaque décision.
5. Consolidation : état actuel, historique et contradictions, selon l'autorité puis la date des faits.
6. Vérification des preuves : chaque citation doit se retrouver dans son passage, sinon le pipeline s'arrête.
7. Index de recherche EmbeddingGemma.

## Outils utilisés

Python (PyMuPDF, openpyxl), Ollama (qwen3:8b, qwen2.5vl:7b, EmbeddingGemma), HTML, CSS et JavaScript sans framework. Claude (Anthropic) a servi au développement du code, à l'analyse du corpus et à la rédaction des réponses ; chaque citation est vérifiée automatiquement contre les sources.

## Limites

- Aucun compte JEV : les décisions au contrat JEV sont produites par le modèle local.
- Le classement automatique de la nature d'un passage est imparfait ; les réponses, la chronologie et les contradictions affichées viennent du contenu rédigé et vérifié.
- La recherche sémantique demande Ollama ; une page ouverte en `file://` exige `OLLAMA_ORIGINS=null`.
- Absents du corpus : compte rendu formel du comité du 26 septembre, dates des re-tests SEC-210 et ACC-303, date du runbook final, avenant qui fixe le plafond de 204 000 $. Les autres incertitudes sont listées dans Historique › Événements.
