# Cockpit actuariel V6 — UX optimisée

Application Gradio de projection technique assurance.

## Navigation
Données → Primes → Commissions & DAC → S/P & Charges → FG & Financier → Synthèse → Contrôles.

Le contexte Branche / Local-IFRS / Période est global. Les écrans métier utilisent une vue branche compacte, une vue portefeuille dédiée et des paramètres avancés repliés.

## Render
Build command:
`pip install --upgrade pip && pip install -r requirements.txt`

Start command:
`python app.py`

## Fichier d'hypothèses
Le modèle Excel est embarqué sous `hypotheses_projection_v5.xlsx` et reste importable depuis l'onglet Données.
