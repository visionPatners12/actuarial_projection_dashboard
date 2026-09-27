# Refonte UX V6

Cette version conserve les moteurs actuariels existants et restructure uniquement l'expérience de pilotage.

## Principes
- Contexte global unique : Branche, Référentiel Local/IFRS, Période et scénario actif.
- KPI persistants visibles entre les onglets.
- Chaque module est organisé en Vue branche / Vue portefeuille / Paramètres avancés.
- Les matrices 12 mois × 8 branches sont déplacées vers les vues portefeuille et les détails.
- Les écrans de branche privilégient un graphique principal, un tableau compact de 12 mois et les variables réellement pilotables.
- Les diagnostics techniques sont centralisés dans l'onglet Contrôles.
- Les hypothèses éditées dans les tableaux avancés déclenchent un recalcul automatique côté utilisateur.

## Navigation
1. Données
2. Primes
3. Commissions & DAC
4. S/P & Charges
5. FG & Financier
6. Synthèse
7. Contrôles

## États visuels
- Automatique
- Modifié manuellement
- Verrouillé

## Logique métier
Aucune formule métier n'a été modifiée par la refonte UX. Les moteurs `prime_engine.py`, `claims_engine.py` et `expense_engine.py` restent la source des calculs.
