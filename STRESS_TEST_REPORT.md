# Rapport de stress test — Forecast technique

## Résumé

Campagne exécutée le 26 septembre 2026 sur les moteurs :
- projection des primes ;
- cession / réassurance ;
- REC Local / IFRS ;
- commissions / récupération de commission ;
- DAC IFRS ;
- S/P exercice et global ;
- optimisation portefeuille sous contraintes ;
- charges et résultat technique.

## Résultats

- Tests unitaires existants : **40 / 40 passés**.
- Projections complètes primes/REC/commissions/DAC aléatoires : **20 000 scénarios, 0 échec**.
- Optimisations S/P portefeuille complètes : **5 000 scénarios, 0 échec**.
- Problèmes élémentaires d'optimisation bornée : **20 000 scénarios, 0 échec**.
- Tests trajectoires de taux et projection avec ancres : **28 292 contrôles, 0 échec**.
- Tests charges / résultat technique : **9 000 contrôles, 0 échec**.
- Grille de cas numériques extrêmes : **294 scénarios, 0 échec**.
- Compilation Python : OK.
- Démarrage Gradio/HTTP : **HTTP 200**.

## Cas couverts

- 1 à 3 années historiques ;
- trous dans l'historique ;
- baisse anormale d'un cumul historique ;
- atterrissages faibles, élevés ou nuls ;
- ancrages mensuels incompatibles avec l'atterrissage ;
- cession négative, supérieure à 100 %, proche de 0 % ou 100 % ;
- REC à forte reprise ou forte constitution ;
- REC de clôture empêchée de devenir négative ;
- conservation de la monotonie des primes acquises Direct/Réassurance lorsque la règle s'applique ;
- relation REC Direct prorata = REC CIMA 72 % / 72 % ;
- dépendance commission Réassurance = commission Direct × taux de récupération ;
- DAC IFRS ;
- branches S/P verrouillées ;
- overrides S/P mensuels ;
- cibles portefeuille réalisables et non réalisables ;
- bandes asymétriques ;
- prime acquise portefeuille nulle ;
- charges antérieures en boni et en mali ;
- identités Charge exercice + Charge antérieurs = Charge globale ;
- identité Résultat technique = Prime acquise nette - Charge globale - Commission nette CPC ;
- montants allant de 1e-9 à 1e15 sur les tests numériques extrêmes.

## Conclusion

Aucune rupture des identités critiques testées n'a été détectée. Les scénarios économiquement impossibles ou incohérents sont bornés ou signalés par des diagnostics plutôt que de provoquer un crash.

Ce rapport valide la robustesse technique du moteur sur les périmètres déjà implémentés. Il ne remplace pas la validation actuarielle des hypothèses métier qui seront ajoutées dans les prochains modules (paiements, SAP, IBNR, etc.).
