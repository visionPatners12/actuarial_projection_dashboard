# Projection technique assurance — V4.1

Application Gradio en français, prête pour Render.

## Parcours
1. Historique des primes (mois en lignes, branches en colonnes)
2. Ancrages Direct Local (départ et/ou arrivée)
3. Passage IFRS : uniquement IBNR, DAC (%) et REC Réassurance IFRS (%)
4. Hypothèses Réassurance : cession primes, récupération sinistres, REC Réassurance / primes cédées, commission
5. Cibles CPC Local / IFRS
6. Pilotage interactif des courbes
7. Export Excel Direct Local / Reass Local / CPC SAZ Local + IFRS

## Règle REC Réassurance
La REC Réassurance est indépendante de la REC Direct.

REC Réassurance = Primes cédées × Taux REC Réassurance.

## Render
Build Command: `pip install --upgrade pip && pip install -r requirements.txt`
Start Command: `python app.py`
