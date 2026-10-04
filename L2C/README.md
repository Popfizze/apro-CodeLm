# L2C — vérification des dessins d'atelier d'armature

Solution de l'équipe apro au défi L2C « Du plan aux dessins d'atelier en ingénierie » : lire les plans de structure et les dessins d'atelier d'un projet en PDF, apparier les éléments, relever les non-conformités d'armature et produire la base JSON et le rapport PDF par feuillet.

## Organisation du dossier

Les chemins sont relatifs au dossier `L2C/` du dépôt.

```
L2C/
├── l2c_verif/          paquet Python du pipeline ; point d'entrée : python -m l2c_verif
│   ├── extract/        un extracteur par type d'élément (fondation, poutre, mur, colonne, dalle)
│   ├── grid/           détection de la grille d'axes
│   ├── ocr/            OCR Tesseract des pages sans couche texte
│   └── llm/            scan IA local optionnel (Ollama)
├── app/                application web locale : server.py (API), index.html (interface), build_data.py
├── notebooks/          demo_pipeline_CLP.ipynb : exploration des données et démonstration sur CLP
├── data/               PDF des projets, data/<PROJET>/ (non versionné)
├── results/            sorties du pipeline, results/<PROJET>/ (non versionné)
├── cache/              cache OCR et IA (non versionné)
├── pyproject.toml      paquet l2c-verif et commande l2c-verif
└── requirements.txt    dépendances, notebook compris
```

## Installation

Python 3.11 ou plus récent.

```bash
pip install -r requirements.txt          # ou : pip install -e .  (ajoute la commande l2c-verif)
```

Tesseract (dessins d'atelier sans couche texte) :

| Système | Commande |
|---|---|
| Windows | `winget install UB-Mannheim.TesseractOCR` |
| Linux (Debian/Ubuntu) | `sudo apt install tesseract-ocr` |
| macOS | `brew install tesseract` |

L'exécutable est cherché dans `TESSERACT_CMD`, puis dans le `PATH`, puis dans `C:\Program Files\Tesseract-OCR\`. Sans Tesseract, les pages sans couche texte sont ignorées avec un avertissement.

IA locale (facultative, option `--llm`) : installer Ollama (https://ollama.com), puis `ollama pull qwen3:8b`.

Données : `data/<PROJET>/L2C_PLAN_STR_<PROJET>.pdf`, dessins d'atelier sous `data/<PROJET>/DA/<catégorie>/*.pdf`, vérité terrain facultative `data/<PROJET>/*dismatch*.xlsx`.

## Exécution

```bash
# un projet
python -m l2c_verif run --project data/CLP --out results/CLP

# un projet avec vérité terrain (rappel et précision)
python -m l2c_verif run --project data/CLP --out results/CLP --gt data/CLP/CLP_dismatch.xlsx

# certains feuillets du plan seulement
python -m l2c_verif run --project data/CLP --out results/CLP --pages S-100,S-500

# avec le scan IA local (Ollama qwen3:8b)
python -m l2c_verif run --project data/CLP --out results/CLP_IA --llm

# tous les projets de data/ (vérité terrain *dismatch*.xlsx détectée)
python -m l2c_verif run-all

# régénérer report.pdf, annotated.pdf et l'annexe A à partir des JSON d'un run
python -m l2c_verif.report results/CLP --data data/CLP
```

Sorties dans `results/<PROJET>/` :

| Fichier | Contenu |
|---|---|
| `items_plan.json`, `items_atelier.json` | éléments extraits (annexe A + niveau, localisation, bbox, confiance, méthode) |
| `annexe_a_plan.json`, `annexe_a_atelier.json` | éléments au schéma strict de l'annexe A |
| `findings.json` | un constat par élément : statut et écarts détaillés |
| `summary.json` | comptes par feuillet, totaux, évaluation (avec `--gt`), durée des étapes |
| `run.json` | manifeste du run : entrées (SHA-256), mode, modèle, sorties, durée |
| `report.pdf` | conformités et non-conformités par feuillet, puis détail des écarts |
| `annotated.pdf` | écarts encerclés sur le plan et sur le dessin d'atelier, liés entre eux |

Application web :

```bash
python app/build_data.py     # charge les runs de results/ dans l'interface
python app/server.py         # http://localhost:8000
```

Bouton « Téléverser » : nom du projet, PDF du plan, PDF des dessins d'atelier, puis « Lancer l'analyse » ; le serveur exécute le pipeline et `build_data.py`, puis l'interface affiche le run.

Notebook : ouvrir `notebooks/demo_pipeline_CLP.ipynb` dans Jupyter ou VS Code, ou `jupyter-execute notebooks/demo_pipeline_CLP.ipynb`.

## Architecture

```
data/<P>/L2C_PLAN_STR_<P>.pdf + data/<P>/DA/<catégorie>/*.pdf
  1 indexation         ingest.py, ocr/     feuillet, série → type, niveau ; OCR si pas de couche texte
  2 grille d'axes      grid/               bulles d'axes → localisation <lettre>-<numéro>
  3 blocs              blocks.py           encadrés, piles d'annotations, lignes de tableau
  4 scan IA (--llm)    llm/                qwen3:8b lit les lignes que la regex n'a pas lues
  5 lecture            readers.py          lecture déterministe des libellés d'armature (rebar.py)
  6 extraction         extract/            éléments plan et atelier, par type
  7 appariement        match.py            type + niveau + localisation, puis tolérances
  8 comparaison        compare.py          conforme | non_conforme | manquant_atelier | ajoute_atelier
  9 évaluation (--gt)  evaluate.py         rappel, précision
 10 sorties            annex_a.py, report.py, annotate.py, manifest.py
```

Tout s'exécute sur le poste : aucun document n'est envoyé vers un service infonuagique ou une API externe ; l'IA passe par Ollama sur `localhost` et le serveur web n'écoute que sur `127.0.0.1`.

## Hypothèses

- Le type d'un feuillet de plan vient de sa série : S-1xx fondation (si le titre mentionne fondation, semelle ou radier), S-3xx poutre, S-4xx mur, S-5xx colonne, S-6xx dalle ; les autres feuillets ne sont pas vérifiés. Le type d'un dessin d'atelier vient de son dossier `DA/<catégorie>`.
- Le niveau vient du titre du feuillet (plan) et du nom du fichier (atelier).
- Le plan et l'atelier partagent la même grille d'axes ; un élément est localisé par l'intersection d'axes la plus proche.
- Appariement : colonne et dalle par niveau + localisation ; fondation par localisation (semelles isolées, type lu dans la nomenclature du plan) ; poutre par numéro de poutre ; mur par élévation + bande de niveaux. À défaut de correspondance exacte : tolérance d'un quart d'axe, puis axe adjacent.
- Seuls les attributs inscrits au plan sont comparés : diamètre, quantité, espacement (± 5 mm), longueur (± 25 mm). Une quantité est conforme si une combinaison des lignes d'atelier de même diamètre la donne. Unités impériales converties en millimètres.
- Dalles : seules les barres du haut en bande de colonne sont comparées.
- Un écart lu avec une confiance inférieure à 0,5 (appariement approximatif, lecture incomplète, OCR incertain) n'est pas retenu comme non-conformité ; il reste noté dans le constat.
- Un élément du plan dont le type et le niveau n'ont aucun élément lu à l'atelier est compté `hors_portee_atelier` sur son feuillet, et non `manquant_atelier`.
- Coordonnées X, Y en points PDF, origine en haut à gauche, centre de l'annotation. Le `feuillet` d'un élément d'atelier dans l'annexe A est celui du plan apparié.

## Limites connues

- Murs : aucun dessin d'atelier de mur n'est lu (CLP n'en contient pas, ceux des autres projets ne sont pas interprétés) ; les murs du plan sont extraits mais jamais comparés.
- Dalles et fondations : comparées seulement quand l'atelier a une couche texte (CLP) ; l'OCR ne les lit pas encore sur les autres projets. Les radiers ne sont pas extraits.
- Longueurs : jamais extraites des documents fournis, donc jamais comparées.
- CLP : 4 écarts connus sur 5 détectés (l'écart manqué porte sur un mur). Les 17 autres non-conformités signalées ne figurent pas dans la vérité terrain ; vérifiées visuellement, 16 sont de vrais écarts du dessin d'atelier et 1 est une colonne sans armature indiquée au plan.
- Seul CLP a une vérité terrain : rappel et précision ne sont pas mesurés sur les autres projets.
- OCR : lecture moins fiable que le texte natif (confiance plus basse, écarts incertains non retenus).
- Mode `--llm` : environ 5 minutes sur CLP et sans effet sur les totaux de CLP ; nécessite Ollama.

## Outils et modèles utilisés

- Python, PyMuPDF (lecture des PDF, rendu, rapport et PDF annoté), NumPy, Pydantic, openpyxl, FastAPI, Uvicorn, python-multipart.
- Tesseract OCR 5, modèle de langue `eng`, exécuté localement.
- Ollama et Qwen3 8B (`qwen3:8b`, modèle open-weight), exécutés localement.
- Notebook : Jupyter (nbformat, nbclient, ipykernel), pandas, matplotlib.
- Aucun modèle n'a été entraîné ni affiné.
- Données : plans et dessins d'atelier fournis par L2C pour le hackathon, confidentiels, non inclus dans le dépôt.
