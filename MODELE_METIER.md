# Modèle métier retenu

## Direct

### Flux pilotés par progression
- Primes émises
- Charge sinistres exercice
- Charge sinistres antérieurs
- Sinistres payés exercice
- Sinistres payés antérieurs
- Recours exercice
- Recours antérieurs

Pour chacun :

`Mois N = Mois N-1 × (1 + % appliqué)`

### Taux
- Commission / primes
- REC clôture / primes
- Part IBNR dans les provisions exercice
- Part IBNR dans les provisions antérieures

### Provisions
Le stock de provision nécessaire est déterminé par l'identité de charge, puis ventilé entre SAP et IBNR.

## Réassurance

La première version n'essaie pas de simuler un traité complexe.

- Cession prime par branche
- Récupération sinistre par branche
- Commission de réassurance

Les futurs modules pourront distinguer quote-part, surplus, XL, facultative et stop-loss sans changer la structure Hyp Direct / Hyp Reass.
