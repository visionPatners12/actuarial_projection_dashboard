# Projection technique par pourcentages — Direct / Réassurance / CPC

Cette version remodule le moteur autour des blocs **%** inspirés de `pd.xlsx`.

## Principe

### Direct
Les valeurs futures sont pilotées par deux familles de pourcentages :

1. **Progression mensuelle**  
   `Valeur M = Valeur M-1 × (1 + x%)`

   Appliqué notamment à :
   - primes émises ;
   - charges de sinistres exercice / antérieurs ;
   - sinistres payés exercice / antérieurs ;
   - recours.

2. **Taux appliqué à une base**
   - `Commission = Primes émises × taux commission`
   - `REC clôture = Primes émises × taux REC`
   - la part IBNR répartit les provisions de clôture entre SAP et IBNR.

La charge sinistre reste réconciliée par :

`Charge = Paiements - Recours + SAP clôture + IBNR clôture - SAP ouverture - IBNR ouverture`

### Réassurance
La réassurance est volontairement simple et transparente :

- `Primes cédées = Primes Direct × taux de cession`
- `Sinistres récupérés = Charge sinistre Direct × taux de récupération`
- `Commission réassurance = Primes cédées × taux de commission réassurance`

Les provisions récupérables sont reconstituées de manière à respecter la charge récupérée et les ouvertures fixes.

## Hyp Direct / Hyp Reass

Chaque hypothèse possède :

- **Base %** : issue de l'historique lorsque disponible ;
- **Ajustement manuel** : `+/- Y` points de pourcentage ;
- **Ajustement cible** : calcul automatique facultatif lorsqu'une cible de fin d'année est saisie ;
- **% appliqué** = Base + Ajustement manuel + Ajustement cible.

Dans le dashboard, les champs sont en **points de pourcentage** : `5` signifie `5 %`, `+2` signifie `+2 points`.

## Cibles

La feuille / l'onglet **Cibles** est optionnel. Une cellule vide ne contraint pas le moteur.

Pour Direct, on peut notamment fixer par branche et par année :
- primes début / fin d'année ;
- charges de sinistres début / fin ;
- sinistres payés début / fin ;
- recours début / fin ;
- commission de fin ;
- REC de fin.

Pour la Réassurance :
- primes cédées début / fin ;
- sinistres récupérés début / fin ;
- commission de réassurance de fin.

Une cible de fin d'année génère un ajustement transparent dans Hyp Direct / Hyp Reass.

## Règles structurelles

- les ouvertures sont fixes pendant tout l'exercice ;
- PAP et PANE ouverture/clôture restent fixes dans l'exercice ;
- au changement d'année, la clôture de décembre alimente la nouvelle ouverture ;
- la prime acquise cumulée ne peut pas diminuer ;
- aucune provision négative n'est générée ;
- le CPC est calculé à partir de Direct + Réassurance, jamais projeté indépendamment ;
- frais généraux et produits financiers restent hors moteur à ce stade.

## Export Excel

L'export contient uniquement les feuilles utiles :

1. `Hyp Direct`
2. `Hyp Reass`
3. `Cibles`
4. `Direct Local`
5. `Reass Local`
6. `CPC SAZ`

Dans `Direct Local` et `Reass Local`, les anciens blocs « Progression » sont renommés **%** et affichent les taux réellement appliqués par branche à partir de février.

## Lancement local

### Windows
Double-cliquer sur `run_windows.bat`.

### Mac / Linux
```bash
chmod +x run_mac_linux.sh
./run_mac_linux.sh
```

Puis ouvrir `http://127.0.0.1:7860`.

## Render

Le projet contient `render.yaml` et utilise automatiquement le port `$PORT` fourni par Render.

1. décompresser le ZIP ;
2. envoyer tous les fichiers dans un dépôt GitHub ;
3. dans Render : **New > Blueprint** ;
4. sélectionner le dépôt ;
5. déployer le Blueprint.

## Tests inclus

- `python test_engine.py`
- `python test_export.py`

Ils vérifient notamment :
- ajustements manuels ;
- atterrissage sur cible ;
- taux de cession / récupération ;
- ouvertures fixes ;
- PAP/PANE fixes ;
- prime acquise monotone ;
- identité de charge ;
- rollover annuel ;
- nombre exact de blocs exportés dans Direct Local / Reass Local / CPC SAZ.
