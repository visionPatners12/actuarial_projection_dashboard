# Projection technique assurance

Application Gradio de projection mensuelle pour huit branches. Le parcours principal
utilise optimized_forecast.py et projette les 1 à 12 mois restant dans une année.
Les anciens modules restent présents pour la lecture des classeurs historiques.

## Démarrage

    pip install -r requirements.txt
    python app.py

CVXPY/OSQP résout les programmes quadratiques en production. Si CVXPY n'est pas
installé dans un environnement de développement, le même problème est résolu
avec SciPy/SLSQP.

## Entrées

1. Saisir les primes émises cumulées de N−1 pour les huit branches. Des années
   supplémentaires peuvent être chargées par CSV/XLSX avec les colonnes
   period, branch et gwp_ytd. À partir de trois années complètes, les poids des
   profils historiques sont estimés par backtest chronologique.
2. Importer un classeur mensuel avec les onglets Direct Local et Reass Local.
   Indiquer le dernier mois N réellement clôturé. Avec zéro mois N clôturé, le
   classeur doit contenir décembre N−1. Les mois clôturés sont conservés.
3. Vérifier les taux annuels suggérés depuis les données importées, puis compléter
   les cellules manquantes. Aucun taux requis n'est inventé. Les taux sont en
   points de pourcentage ; les facteurs IFRS sont des multiplicateurs.
4. Ajouter au besoin des cibles, exceptions mensuelles ou verrous de point.
   Un verrou porte sur un cumul, un incrément ou un taux de progression.

Les champs de taux sont :

| Champ | Base |
| --- | --- |
| sp_current, sp_global | Charge courante/globale sur primes acquises |
| settlement_current | Paiements courants sur charge courante |
| settlement_prior | Paiements antérieurs futurs sur provision d'ouverture antérieure |
| ibnr_share_current, ibnr_share_prior | Part IBNR dans la provision de clôture |
| recourse_current, recourse_prior | Recours sur paiements |
| rec_direct, commission | REC de clôture et commission sur primes émises |
| cession, rec_reass, reass_commission | Taux sur primes cédées |
| recovery_current, recovery_prior | Récupération sur charge et paiements |
| ifrs_ibnr_factor, ifrs_rec_factor | Multiplicateurs IFRS/Local |

gwp_end impose la prime de décembre d'une branche. La ligne CONSOLIDATION
permet d'imposer sp_global brut et sp_net net. Les charges des branches autres
qu'Automobile et Santé sont ajustées, dans leurs bornes sp_min/sp_max ou
historiques. Une cible impossible bloque le calcul avec un diagnostic. Les
cibles sp_ifrs_current et sp_ifrs_global par branche recalant l'IBNR IFRS de
décembre sont appliquées seulement si cet IBNR reste non négatif.

## Calcul et export

Les identités de charge, les ouvertures fixes, les cumuls et les bornes de
cession/récupération sont contrôlés après optimisation. La REC Réassurance
est calculée sur les primes cédées. L'IFRS transforme le Local via IBNR, DAC
et REC à 100 %.

L'export contient les six blocs Direct/Réassurance/CPC Local/IFRS et les
entrées/diagnostics. Il est un instantané des valeurs optimisées ; les
changements de saisie doivent être recalculés dans l'application.

L'inventaire reproductible du classeur de référence est dans AUDIT_PD.csv,
généré par la commande python audit_pd.py. Les formules de pd.xlsx ne sont
pas utilisées comme vérité métier.

## Vérification

    python -m pytest -q test_optimized.py test_engine.py test_export.py
