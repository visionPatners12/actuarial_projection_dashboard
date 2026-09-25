# Moteur de projection actuarielle — Direct & Réassurance

MVP Python avec dashboard Gradio pour projeter des blocs mensuels par branche, à partir d'un historique, d'un bloc de départ, d'un bloc d'atterrissage et d'hypothèses métier.

## Principes du modèle

- Les **éléments d'ouverture sont toujours fixes** : l'ouverture de M+1 est la clôture de M. L'optimiseur ne peut jamais les changer.
- Les données historiques servent à estimer des profils (saisonnalité, commissions, cession, récupération) mais ne sont pas considérées comme une vérité théorique.
- Les identités de stocks/flux sont privilégiées : `encouru = payé + clôture - ouverture` et `prime acquise = prime émise + REC ouverture - REC clôture`.
- Le S/P de l'exercice, le S/P global et un taux REC d'atterrissage sont pilotables par branche. Le taux REC est une contrainte d'horizon, pas une formule simpliste imposée à tous les mois.
- La réassurance est générée avec des drivers distincts : taux de cession de primes, récupération des sinistres courant/antérieurs, commission de réassurance.
- Les frais généraux et produits financiers sont hors périmètre du MVP.
- Les objectifs incompatibles ne sont pas masqués : ils ressortent dans `Diagnostics`.

## Installation

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Le dashboard s'ouvre sur `http://127.0.0.1:7860`.

## Utilisation

1. Importer le classeur existant si souhaité. L'adaptateur reconnaît les feuilles `Direct Local` et `Reass Local` et détecte les blocs mensuels à partir des en-têtes de branches.
2. Vérifier/corriger le bloc de départ. Les valeurs de clôture constituent l'état d'ouverture de la première période projetée.
3. Saisir éventuellement des valeurs d'atterrissage. Une cellule vide signifie « laisser le moteur estimer ».
4. Définir les hypothèses par branche : S/P exercice, S/P global, commission, REC/UPR, cession, récupération, etc., avec un mode `Estimé`, `Cible` ou `Fixé`.
5. Choisir le nombre de périodes (1 à 120), puis lancer l'optimisation.
6. Contrôler les diagnostics et exporter le résultat Excel.

## Remarque sur le classeur fourni

L'importateur ne réplique pas aveuglément ses formules. Il extrait les historiques et signale notamment les incohérences de calendrier entre Direct et Réassurance. Le moteur de projection reste indépendant de la logique du classeur source.
