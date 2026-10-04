# JADCO — Hausse de loyer 2026, Collection Équinoxe

Équipe **apro** (Jeremy Vong, Sheng He Ge, Bryan Sanchez) · Défi **JADCO – Collection Équinoxe : Clés en main** · CodeML 2026.

## Résultat

**Hausse de loyer 2026 estimée : 3,07 %** (scénario bas 1,09 %, scénario haut 4,92 %).

Définition : hausse annualisée du loyer effectif (`sRentEffective`) à unité constante. Chaque unité (`sPropCode` + `sUnitCode`) est comparée à son bail précédent. Le chiffre est la médiane par bail, renouvellements et relocations compris selon leur part observée.

| | Loyer effectif | Loyer contractuel |
|---|---|---|
| Portefeuille | 3,07 % | 6,59 % |
| Québec (cinq immeubles, TAL) | 3,39 % | 6,73 % |
| Ontario (The Met, ligne directrice) | 1,99 % | 5,61 % |

Backtest 2023-2025 de la méthode retenue : erreur absolue moyenne de 1,14 point.

## Exécution

Testé avec Python 3.14 sous Windows.

1. Créer l'environnement et installer les librairies :
   ```
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
2. Placer les quatre CSV fournis par JADCO (`equinoxe_listings.csv`, `equinoxe_lease_history.csv`, `equinoxe_concessions.csv`, `equinoxe_asking_history.csv`) à côté de `starter.ipynb`. Ces données sont confidentielles et ne sont pas dans le dépôt.
3. Exécuter le notebook, dans Jupyter ou en ligne de commande :
   ```
   .venv\Scripts\jupyter nbconvert --to notebook --execute --inplace starter.ipynb
   ```
   Il écrit `rent_model.json` (paramètres de la méthode retenue) et `output/results.json` (résultats agrégés).

## Versions

Python 3.14.3, pandas 3.0.6, NumPy 2.5.3, Matplotlib 3.11.2, scikit-learn 1.9.1, openpyxl 3.1.5, Jupyter 1.1.1, nbconvert 7.17.1, ipykernel 7.4.0.

## Sources publiques

- Statistique Canada, tableau 18-10-0004-01, Indice des prix à la consommation (loyers et ensemble, Québec et Ontario) : https://www150.statcan.gc.ca/t1/tbl1/fr/tv.action?pid=1810000401 — `public_sources/18100004-eng.zip`
- SCHL, Enquête sur les logements locatifs 2025, RMR de Montréal et d'Ottawa : https://www.cmhc-schl.gc.ca/professionals/housing-markets-data-and-research/housing-data/data-tables/rental-market/rental-market-report-data-tables — `public_sources/cmhc_montreal_2025.xlsx`, `public_sources/cmhc_ottawa_2025.xlsx`
- Tribunal administratif du logement, taux de référence 2017-2026 : `public_sources/tal_reference_rates.csv` (adresse de la source officielle sur chaque ligne)
- Gouvernement de l'Ontario, ligne directrice sur l'augmentation des loyers 2017-2026 : https://www.ontario.ca/page/residential-rent-increases — `public_sources/ontario_rent_guideline.csv`

## Références

- Notebook de départ `starter.ipynb` et données fournis par JADCO pour le défi.
- Clemen, R. T. (1989). Combining forecasts: A review and annotated bibliography. *International Journal of Forecasting*, 5(4), 559-583. https://doi.org/10.1016/0169-2070(89)90012-5
- Outils d'IA utilisés : Claude (Anthropic) et OpenAI Codex, comme aide à l'écriture et à la vérification du code.
