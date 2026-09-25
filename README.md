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

Aucun import de document n’est requis dans l’application : le fichier rempli peut être renvoyé séparément dans ChatGPT.
