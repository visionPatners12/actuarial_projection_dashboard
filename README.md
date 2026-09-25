# Projection technique assurance — V4.2

Application Gradio en français pour la projection Direct / Réassurance / CPC, Local et IFRS.

## Démarrage

```bash
pip install -r requirements.txt
python app.py
```

## Render

- Build Command : `pip install --upgrade pip && pip install -r requirements.txt`
- Start Command : `python app.py`

## Première page

La première page contient maintenant un bouton **« Télécharger le fichier d’hypothèses à remplir »**.
Le fichier couvre :
- historique ;
- ancrages Direct départ / arrivée ;
- hypothèses Réassurance par taux ;
- paramètres IFRS (IBNR, DAC, REC Réassurance) ;
- cibles CPC Local / IFRS.

L’application fonctionne sans import de document ; les données peuvent être saisies directement dans les grilles prévues.

## V4.3 — Alignement exact avec pd.xlsx
- Les lignes de l'onglet **Ancrages du modèle** reprennent les libellés de `Direct Local` de `pd.xlsx`.
- Une colonne **Section** distingue les libellés répétés (`Ouverture`, `Clôture Per.`, `Clôture Ant.`).
- Le passage IFRS reprend les lignes source `IBNR BE Per.`, `IBNR BE Ant.`, `DAC Ouv`, `DAC Clo`, `REC Ouverture 100%` et `REC Clôture 100%`.
- Les blocs Réassurance Départ/Arrivée sont disponibles mais facultatifs ; s'ils sont vides, la Réassurance est pilotée par les taux de cession, récupération et REC Réassurance.

- Le fichier d'hypothèses téléchargé peut être réimporté depuis la première page pour recharger automatiquement l'historique, les ancrages, la Réassurance et les cibles CPC.
