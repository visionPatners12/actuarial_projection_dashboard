# Architecture fonctionnelle

Données → Primes → Commissions/DAC → S/P/Charges → FG/Financier → Synthèse → Contrôles

## Contexte global
Les trois sélecteurs Branche, Référentiel et Mois sont globaux et pilotent les vues métier.

## KPI persistant
Le bandeau au-dessus des onglets reste visible et montre :
- taux FG branche ;
- taux FG portefeuille ;
- résultat après FG ;
- résultat financier net ;
- résultat après financier.

## Dépendances
- Primes produit les primes acquises nettes.
- Commissions/DAC produit la commission nette CPC.
- S/P produit les charges et le résultat technique avant FG.
- FG/Financier consomme ces sorties sans recalculer les modules amont.
