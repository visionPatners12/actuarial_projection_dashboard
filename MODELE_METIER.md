# Modèle métier de projection

## Entrées minimales

Le moteur requiert les primes émises cumulées N−1 par branche, la dernière
clôture mensuelle Direct/Réassurance et les taux annuels de charge, règlement,
REC, commission, cession, récupération et conversion IFRS. Les taux observables
dans un classeur importé sont proposés, puis restent modifiables. Une entrée
requise absente bloque la branche.

## Primes et cibles

Les incréments de primes futures suivent le profil historique disponible.
Avec au moins trois exercices complets, les poids des années sont calibrés
par backtest chronologique sous contraintes de somme à 1 et de positivité.
Une cible de décembre ou un verrou mensuel est exact. Le solveur minimise
d'abord l'écart absolu au profil, puis lisse les solutions équivalentes.

## Sinistres et provisions

La charge courante et globale découle des S/P sur primes acquises. Les
paiements courants suivent un taux de règlement de la charge. Les paiements
antérieurs suivent un taux de règlement de la provision antérieure
d'ouverture, réparti sur la trajectoire future des primes. SAP et IBNR
soldent ensuite les identités de charge. La part IBNR provient du taux
historique N−1 ou d'une saisie. Une provision négative rend le scénario
infaisable ; aucune charge n'est corrigée silencieusement.

## Réassurance et CPC

Primes cédées = primes Direct × taux de cession. La REC Réassurance de clôture
= primes cédées × taux REC Réassurance. Les charges et paiements récupérés
suivent leurs taux de récupération. Le CPC brut, réassurance et net est
recalculé depuis les deux blocs. Automobile et Santé sont préservées lors
du rééquilibrage de cible CPC ; les autres branches absorbent l'écart dans
les bornes disponibles.

## IFRS et contrôles

L'IFRS transforme le Local par les facteurs IBNR et REC à 100 %, puis par
le DAC. Les S/P IFRS saisis peuvent ajuster l'IBNR de clôture non négatif.
Les mois réalisés, les ouvertures annuelles et PAP/PANE restent fixes.
Les primes et paiements cumulés ne décroissent pas. Toute incompatibilité
d'entrées est signalée.
