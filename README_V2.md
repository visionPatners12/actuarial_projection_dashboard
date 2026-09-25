# Forecast technique V2 — Excel vivant

Cette version transforme l'export en **modèle Excel à formules** :

- `Hyp Direct` : inputs de base, +/- points, ajustement cible, `% appliqué` en formule.
- `Direct Local` : formules liées à `Hyp Direct` et aux blocs mensuels précédents.
- `Hyp Reass` : taux de cession, récupération et commission.
- `Reass Local` : formules liées à `Direct Local` et `Hyp Reass`.
- `CPC SAZ` : formules liées à `Direct Local` + `Reass Local`.
- `Cibles` : inputs optionnels utilisés par le dashboard pour calculer un ajustement d'atterrissage.

Les cellules d'entrée restent en dur par conception; les résultats dérivés sont des formules. Excel est configuré en recalcul automatique à l'ouverture.
