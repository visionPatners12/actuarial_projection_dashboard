# Audit du classeur de référence

AUDIT_PD.csv recense 1 027 lignes des sept onglets de pd.xlsx : libellé,
type proposé, première formule, références d'onglets et erreurs littérales.
Il est régénérable avec python audit_pd.py. La classification est une
proposition de lecture ; les formules du classeur ne pilotent pas le moteur.

## Constats qui influencent la refonte

- Hyp 2027 mélange observations mensuelles, cibles et multiplicateurs.
  La cellule B88 contient une erreur littérale #VALUE!.
- Direct Local contient des erreurs #REF! sur la ligne 127, ainsi que
  des erreurs dans le bloc IBNR des lignes 101–102. Certaines clôtures IBNR
  reprennent l'ouverture ; cela ne constitue pas une méthode de projection.
- Direct Local et Reass Local portent des cumuls et stocks par branche,
  mais plusieurs lignes de variation et de charge doivent être recalculées
  depuis les stocks, paiements et recours pour garantir les identités.
- CPC SAZ Local et CPC SAZ présentent les vues brut, réassurance et net.
  Le nouveau moteur les reconstitue depuis Direct/Réassurance ; il n'optimise
  pas directement leurs lignes de résultat.
- Les onglets Direct et Reass servent de couche IFRS. Les facteurs IBNR,
  REC à 100 % et DAC sont calibrés depuis des observations comparables ou
  demandés en entrée, sans reprendre automatiquement les constantes du
  classeur.

Les colonnes categorie_proposee et nature_proposee de l'inventaire doivent
être confirmées pour tout usage réglementaire ou clôture comptable.
