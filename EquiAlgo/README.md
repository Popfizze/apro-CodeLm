# ÉquiAlgo — un financement étudiant équitable

Équipe **apro** (Jeremy Vong, Sheng He Ge, Bryan Sanchez) · Défi **IVADO – ÉquiAlgo** · CodeML 2026.

## Résultat

Le comité applique la même règle dans toutes les régions, moins une pénalité constante pour les régions éloignées : −2,00 en logit (écart-type bootstrap 0,09), l'équivalent de 1,45 point de cote R. Sur l'écart de 21,1 points entre les grands centres (48,4 %) et les régions éloignées (27,3 %), 81 % ne s'explique pas par les différences de dossier (cote R, revenu, heures travaillées, programme, première génération).

Correction : le score du comité, pénalité régionale retirée, octroie la bourse aux 40 % meilleurs dossiers (1 600 sur 4 000). Métrique défendue : l'égalité des chances, mesurée contre quatre étalons de mérite plausibles, jamais contre `decision_octroi`.

| | Modèle en production | Modèle corrigé |
|---|---|---|
| Taux d'octroi | 39,0 % | 40,0 % |
| Grands centres / régions éloignées | 46,9 % / 27,5 % | 41,8 % / 37,4 % |
| Écart d'égalité des chances (moyenne des étalons, plage) | 0,231 (0,135 à 0,298) | 0,011 (−0,067 à 0,104) |
| Concordance moyenne avec les étalons | 88,1 % | 90,2 % |
| Écart de parité démographique | 0,194 | 0,044 |

Part de l'écart d'égalité des chances refermée : 71 % en moyenne (51 % à 86 % selon l'étalon).

## Exécution

Testé avec Python 3.14.3 sous Windows.

1. Créer l'environnement et installer les librairies :
   ```
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
2. Placer les deux CSV fournis par IVADO (`donnees_demandes.csv`, `candidats_evaluation.csv`) dans `data/`. Ces données ne sont pas dans le dépôt.
3. Exécuter les carnets, dans Jupyter ou en ligne de commande :
   ```
   .venv\Scripts\jupyter nbconvert --to notebook --execute --inplace audit_rapport.ipynb
   .venv\Scripts\jupyter nbconvert --to notebook --execute --inplace model_corrige.ipynb
   ```
   `audit_rapport.ipynb` mesure le biais, justifie les métriques et identifie les variables proxys ; il écrit `output/audit.json`. `model_corrige.ipynb` applique la correction, trace le front de Pareto (`figures/front_pareto.png`), propose le plan de surveillance et écrit `predictions.csv` et `output/modele.json`.

`baseline_model.ipynb` est le carnet de départ fourni. `presentation.pdf` est le support du pitch.

## Versions

Python 3.14.3, pandas 3.0.6, NumPy 2.5.3, SciPy 1.18.1, scikit-learn 1.9.1, fairlearn 0.14.0, Matplotlib 3.11.2, Jupyter 1.1.1, nbconvert 7.17.1, ipykernel 7.4.0.

## Références

- Carnet de départ `baseline_model.ipynb` et données synthétiques fournis par IVADO pour le défi.
- Hardt, M., Price, E. et Srebro, N. (2016). Equality of Opportunity in Supervised Learning. *Advances in Neural Information Processing Systems 29*.
- Barocas, S., Hardt, M. et Narayanan, A. (2023). *Fairness and Machine Learning: Limitations and Opportunities*. MIT Press. https://fairmlbook.org
- Bird, S. et al. (2020). Fairlearn, rapport technique MSR-TR-2020-32, Microsoft. https://fairlearn.org
- Pedregosa, F. et al. (2011). Scikit-learn: Machine Learning in Python. *Journal of Machine Learning Research*, 12, 2825-2830.
- Outils d'IA utilisés : Claude (Anthropic) et OpenAI Codex, comme aide à l'écriture et à la vérification du code.
