from __future__ import annotations
from pathlib import Path
import math
import pandas as pd
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter

RATE_HINTS = ("rate", "ratio", "sp_", "cession", "recovery")
BRANCHES = ["Automobile","Santé","Accident corporel","Incendie","BDM - Construction","RC - RC Déc","RD","Transport"]
EN_BRANCHES = ["Motor","Health","Worker injury","Fire","Engineering","Liability","Miscellaneous","Transport"]
CORPORATE_BRANCHES = ["Accident corporel","Incendie","BDM - Construction","RC - RC Déc","RD","Transport"]
CPC_GROUPS = {
    "INCENDIE": ["Incendie"],
    "AUTO": ["Automobile"],
    "RD": ["Accident corporel","BDM - Construction","RD"],
    "RC": ["RC - RC Déc"],
    "TRANS": ["Transport"],
    "SANTE": ["Santé"],
}
FR_MONTHS = {1:"Janvier",2:"Février",3:"Mars",4:"Avril",5:"Mai",6:"Juin",7:"Juillet",8:"Août",9:"Septembre",10:"Octobre",11:"Novembre",12:"Décembre"}

DIRECT_LABELS = {
7:'Primes Emises',8:'PAP Ouverture',9:'PAP Clôture',10:'PANE Ouverture',11:'PANE Clôture',12:"Chiffre d'Affaire",
14:'Sinistres payés Per.',15:'Sinistres payés Ant.',16:'Sinistres Payés net des recours',18:'Commisions',
20:'REC Ouverture',21:'REC Clôture',22:'Variation de REC CIMA 72%',24:'REC Ouverture',25:'REC Clôture',26:'Variation de REC prorata',
28:'DAC Ouv',29:'DAC Clo',30:'Var DAC',32:'REC Ouverture',33:'REC Clôture',34:'Variation des FAR 28%',
36:'IBNR Ouverture',37:'IBNR Clôture',38:'Variation de IBNR CIMA',41:'IBNR BE Per.',42:'IBNR BE Ant.',43:'Variation de IBNR BE',
45:'SAP hors chargement Per.',46:'SAP hors chargement Ant.',47:'Recours Per.',48:'Recours Per.Anté',49:'SAP net de recours hors chargement',
51:'Chargement de Gestion IBNR et SAP',52:'        IBNR ouverture',53:'        IBNR cloture',54:'        SAP exercice courant',55:'        SAP exercices antérieurs',
57:'IBNR BE',58:'        Ouverture',59:'        Clôture Per.',60:'        Clôture Ant.',61:'Variation Per.',62:'Variation Ant.',
64:'SAP hors chargement',65:'        Ouverture',66:'        Clôture Per.',67:'        Clôture Ant.',68:'Variation Per.',69:'Variation Ant.',
71:'SAP hors chargement',72:'        ULAE Ouverture',73:'        ULAE Clôture',74:'Variation Per.',75:'Chargement SAP',76:'        Ouverture',77:'        Clôture Per.',78:'        Clôture Ant.',79:'Variation chargement Per.',80:'Variation chargement Ant.',
82:'Chargement SAP',83:'        Ouverture',84:'        Clôture Per.',85:'        Clôture Ant.',86:'Variation chargement Per.',87:'Variation chargement Ant.',89:'Variation chargement Per.(SAP+IBNR)',90:'Variation chargement Ant.(SAP+IBNR)',93:'Contrôle',109:'DAC OUV REC 100%',110:'DAC CLO REC 100%'
}
# Transparent percentage block inspired by pd.xlsx.  The values shown here are
# percentages actually applied by the new driver-based engine.
DIRECT_LABELS.update({
    131:'%',132:' ',133:'Paramètre',134:'Primes Emises',135:'PAP Ouverture',136:'PAP Clôture',137:'PANE Ouverture',138:'PANE Clôture',
    139:'Sinistres payés Per.',140:'Sinistres payés Ant.',141:'Commission / primes',142:'REC Ouverture',143:'REC Clôture / primes',
    144:'SAP clôture Per. (calculé)',145:'SAP clôture Ant. (calculé)',146:'Recours Per.',147:'Recours Ant.',148:'SAP ouverture (fixe)',
    149:'Part IBNR Per.',150:'Part IBNR Ant.',151:'Charge sinistres Per.',152:'Charge sinistres Ant.'
})

REASS_LABELS = {
7:'Primes Emises',8:'PAP Ouverture',9:'PAP Clôture',10:'PANE Ouverture',11:'PANE Clôture',12:"Chiffre d'Affaire",14:'Sinistres payés Per.',15:'Sinistres payés Ant.',16:'Sinistres Payés net des recours',18:'Commisions',20:'REC Ouverture',21:'REC Clôture',22:'Variation de REC CIMA',24:'REC Ouverture',25:'REC Clôture',26:'Variation de REC prorata',30:'Variation de REC100%',32:'DAC Ouv',33:'DAC Clo',34:'Var DAC',36:'IBNR Ouverture',37:'IBNR Clôture',38:'Variation de IBNR CIMA',40:'IBNR BE Per.',41:'IBNR BE Ant.',42:'Variation de IBNR BE',44:'SAP hors chargement Per.',45:'SAP hors chargement Ant.',46:'SAP hors chargement',48:'Chargement de Gestion IBNR et SAP',49:'        IBNR exercice courant',50:'        IBNR exercices antérieurs',51:'        SAP exercice courant',52:'        SAP exercices antérieurs',54:'IBNR BE',55:'        Ouverture',56:'        Clôture Per.',57:'        Clôture Ant.',58:'Variation Per.',59:'Variation Ant.',61:'SAP hors chargement',62:'        Ouverture',63:'        Clôture Per.',64:'        Clôture Ant.',65:'Variation Per.',66:'Variation Ant.',68:'SAP hors chargement',69:'        ULAE Ouverture',70:'        ULAE Clôture',71:'Variation Per.',72:'Chargement SAP',73:'        Ouverture',74:'        Clôture Per.',75:'        Clôture Ant.',76:'Variation chargement Per.',77:'Variation chargement Ant.',79:'Contrôle',81:'DAC OUV REC 100%',82:'DAC CLO REC 100%',87:'Progression par branche Réass',88:'\u00a0',89:'Facteur de dev.',90:'Primes Emises',91:'PAP Ouverture',92:'PAP Clôture',93:'PANE Ouverture',94:'PANE Clôture',95:'Sinistres payés Per.',96:'Sinistres payés Ant.',97:'Commision',98:'REC Ouverture',99:'REC Clôture',100:'REC Ouverture 100%',101:'REC Clôture 100%',102:'SAP hors chargement Per.',103:'SAP hors chargement Ant.',104:'Recours Per.',105:'Recours Per.Anté',106:'    SAP    Ouverture'
}
REASS_LABELS.update({87:'% Réassurance',107:'IBNR récupérable Per.',108:'IBNR récupérable Ant.'})

CPC_LABELS = {
4:'BRUT',5:'Primes Emises',6:'Variation primes non acquises',7:'Primes acquises',9:"Sinistres réglés de l'exercice",10:'Variation de provision pour sinistres de exercices',11:"Charges de sinistres de l'exercice",12:'Sinistres réglés sur exercices antérieurs',13:'Variation de provision pour sinistres sur exercices antérieurs',14:'Charges de sinistres sur exercice antérieur',15:'Charge de sinistres globale',17:'Commissions',18:'DAC',19:'Commissions',21:'Masse Salariale',22:'Charges Externes',23:'Management fees',24:'Dépenses de Formation',25:'Dépenses IT (hors amortissements)',26:'Dépenses de communications',27:'Travaux, fournitures et services',28:'Autres charges externes',29:'Charges administratives – Frais d’audit',30:'Dotations / reprises aux amortissements et provisions',31:'Frais préliminaires',32:'Equipement',33:'Logiciels',34:'Matériel Informatique',35:'Matériel de transport',36:'Autres produits opératinnelles',37:'Autres  charges opérationnels',38:'Dotations sur créances intermédiaires',39:'Autres Impôts et Taxes',40:'Frais de contrôle',41:'Frais généraux',43:'Résultat Technique brute',45:'Ratios Bruts',46:"           S/P de l'exercice",47:'           S/P global',48:'          taux commissions',49:'         taux Frais généraux',50:'           S/P combiné',52:'REASSURANCE',53:'Primes cédées',54:'Variation primes non acquises',55:'Primes acquises',57:"Sinistres Réglés de l'exercice",58:"Variation de provision pour sinistres de l'exercice",59:"Charges de sinistres de l'exercice",60:'Sinistres Réglés sur exercices antérieurs',61:'Variation de provision pour sinistres sur exercices antérieurs',62:'Charges de sinistres sur exercice antérieur',63:'Charge de sinistres globale',65:'Commissions',66:'DAC',67:'Commissions',69:'Résultat Technique Réassurance',71:'Ratios ',72:'           Taux de cessions primes',73:'           Taux de récupération des sinistres',75:'NET',76:'Primes émises',77:'Variations primes non acquises',78:'Primes acquises',80:"Sinistres réglées de l'exercice",81:"Provisions pour sinistres de l'exercice",82:"Charges de sinistres de l'exercice",83:'Sinistres réglés sur exercices antérieurs',84:'Variation de provision pour sinistres sur exercices antérieurs',85:"Charges de sinistres de l'exercice antérieur",86:'Charges de sinistres globales',88:'Commissions',89:'DAC',90:'Commissions',92:'Masse Salariale',93:'Charges Externes',94:'Frais Marketing',95:'Frais de gestion',96:'Frais informatique',97:'Char. Immeuble',98:'Frais de conseil',99:'Frais de contrôle',100:'Assis tech',101:'Dotations / reprises aux amortissements et provisions',102:'frs ets',103:'c a r',104:'log',105:'imbl',106:'mat transp',107:'aut mat',108:'mat inf',109:'Dotations sur créances intermédiaires',110:'Impôts et Taxes',111:'Autres Charges',112:'Frais généraux',114:'Résultat technique net',116:'Ratios Nets',117:"           S/P de l'exercice",118:'           S/P global',119:'          taux commissions',120:'         taux Frais généraux',121:'           Ratio combiné',124:'Produits Financiers',125:'REV IMB',126:'prdt cession immo',127:'revenu actions',128:'revenu obligation',129:'TRESO & EQUIV',130:'frais de gestion des placement',131:'vnc des actifs cedées',132:'dot déprec autres placmt fin',133:'amort imble placement',134:'Charges financières',135:'Résultat financier net',137:'Autres produits opératinnelles',139:'Autres  charges opérationnels',140:'Provision fiscale',141:'charges HE',142:'Produit HE',143:'Résultat non technique net',144:'Impôt sur les sociétés',146:'Résultat Net Après Impôt',148:"RESULTAT D'EXPLOITATION",149:"2,2% CHIFFRS D'AFFAIRES",150:'33% RESULTAT AVANT IMPOT'
}

DARK='17365D'; LIGHT='D9EAF7'; PALE='EAF2F8'; GREY='D9E1F2'; GOLD='FFF2CC'; BLACK='000000'; WHITE='FFFFFF'


def _safe(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else 0.0
    except Exception:
        return 0.0


def _write_df(ws, df: pd.DataFrame, input_sheet=False):
    if df is None: df = pd.DataFrame()
    data = df.copy()
    for c in data.columns:
        if pd.api.types.is_datetime64_any_dtype(data[c]): data[c] = data[c].dt.strftime('%Y-%m-%d')
    ws.append(list(data.columns))
    for row in data.itertuples(index=False, name=None): ws.append([None if pd.isna(v) else v for v in row])
    dark=PatternFill('solid',fgColor=DARK); input_fill=PatternFill('solid',fgColor=GOLD); thin=Side(style='thin',color=GREY)
    for cell in ws[1]: cell.fill=dark; cell.font=Font(color=WHITE,bold=True); cell.alignment=Alignment(horizontal='center')
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border=Border(bottom=thin)
            if input_sheet and isinstance(cell.value,(int,float)): cell.font=Font(color='0000FF'); cell.fill=input_fill
            elif isinstance(cell.value,(int,float)): cell.font=Font(color=BLACK)
    for idx,col in enumerate(data.columns,1):
        vals=[len(str(v)) for v in data[col].head(50).fillna('')]
        ws.column_dimensions[get_column_letter(idx)].width=max(12,min(34,max([len(str(col))]+vals)+2))
        if any(h in str(col).lower() for h in RATE_HINTS):
            for cell in ws[get_column_letter(idx)][1:]: cell.number_format='0.0%'
        elif pd.api.types.is_numeric_dtype(data[col]):
            for cell in ws[get_column_letter(idx)][1:]: cell.number_format='#,##0;[Red](#,##0);-'
    ws.freeze_panes='A2'; ws.sheet_view.showGridLines=False


def _periods(df):
    if df is None or len(df)==0: return []
    return sorted(pd.to_datetime(df['period']).dt.to_period('M').unique())


def _rows_for_period(df, period):
    p=pd.Period(period,freq='M')
    d=df[pd.to_datetime(df['period']).dt.to_period('M')==p]
    return {str(r['branch']):r for _,r in d.iterrows()}


def _aggregate(rows, field, members):
    return sum(_safe(rows.get(b,{}).get(field,0.0) if hasattr(rows.get(b,{}),'get') else 0.0) for b in members)


def _direct_value(r, row):
    if r is None: return 0.0
    open_ibnr=_safe(r.get('ibnr_open_current'))+_safe(r.get('ibnr_open_prior'))
    close_ibnr=_safe(r.get('ibnr_close_current'))+_safe(r.get('ibnr_close_prior'))
    open_case=_safe(r.get('case_open_current'))+_safe(r.get('case_open_prior'))
    close_case=_safe(r.get('case_close_current'))+_safe(r.get('case_close_prior'))
    vals={
        7:_safe(r.get('gwp_ytd')),8:_safe(r.get('pap_open')),9:_safe(r.get('pap_close')),10:_safe(r.get('pane_open')),11:_safe(r.get('pane_close')),12:_safe(r.get('revenue')),
        14:_safe(r.get('paid_current_ytd')),15:_safe(r.get('paid_prior_ytd')),16:_safe(r.get('paid_current_ytd'))+_safe(r.get('paid_prior_ytd'))-_safe(r.get('recourse_current_ytd'))-_safe(r.get('recourse_prior_ytd')),18:_safe(r.get('commission_ytd')),
        20:_safe(r.get('upr_open')),21:_safe(r.get('upr_close')),22:_safe(r.get('upr_close'))-_safe(r.get('upr_open')),
        36:open_ibnr,37:close_ibnr,38:close_ibnr-open_ibnr,41:_safe(r.get('ibnr_close_current')),42:_safe(r.get('ibnr_close_prior')),43:close_ibnr-open_ibnr,
        45:_safe(r.get('case_close_current')),46:_safe(r.get('case_close_prior')),47:_safe(r.get('recourse_current_ytd')),48:_safe(r.get('recourse_prior_ytd')),49:close_case,
        58:open_ibnr,59:_safe(r.get('ibnr_close_current')),60:_safe(r.get('ibnr_close_prior')),61:_safe(r.get('ibnr_close_current'))-_safe(r.get('ibnr_open_current')),62:_safe(r.get('ibnr_close_prior'))-_safe(r.get('ibnr_open_prior')),
        65:open_case,66:_safe(r.get('case_close_current')),67:_safe(r.get('case_close_prior')),68:_safe(r.get('case_close_current'))-_safe(r.get('case_open_current')),69:_safe(r.get('case_close_prior'))-_safe(r.get('case_open_prior')),
        93:0.0,109:0.0,110:0.0,
    }
    return vals.get(row,0.0)


def _reass_value(r,row):
    if r is None: return 0.0
    oi=_safe(r.get('recoverable_ibnr_open_current'))+_safe(r.get('recoverable_ibnr_open_prior'))
    ci=_safe(r.get('recoverable_ibnr_close_current'))+_safe(r.get('recoverable_ibnr_close_prior'))
    oc=_safe(r.get('recoverable_case_open_current'))+_safe(r.get('recoverable_case_open_prior'))
    cc=_safe(r.get('recoverable_case_close_current'))+_safe(r.get('recoverable_case_close_prior'))
    vals={7:_safe(r.get('ceded_premium_ytd')),12:_safe(r.get('ceded_premium_ytd')),14:_safe(r.get('recovered_paid_current_ytd')),15:_safe(r.get('recovered_paid_prior_ytd')),16:_safe(r.get('recovered_paid_current_ytd'))+_safe(r.get('recovered_paid_prior_ytd')),18:_safe(r.get('reass_commission_ytd')),20:_safe(r.get('ceded_upr_open')),21:_safe(r.get('ceded_upr_close')),22:_safe(r.get('ceded_upr_close'))-_safe(r.get('ceded_upr_open')),36:oi,37:ci,38:ci-oi,40:_safe(r.get('recoverable_ibnr_close_current')),41:_safe(r.get('recoverable_ibnr_close_prior')),42:ci-oi,44:_safe(r.get('recoverable_case_close_current')),45:_safe(r.get('recoverable_case_close_prior')),46:cc,55:oi,56:_safe(r.get('recoverable_ibnr_close_current')),57:_safe(r.get('recoverable_ibnr_close_prior')),58:_safe(r.get('recoverable_ibnr_close_current'))-_safe(r.get('recoverable_ibnr_open_current')),59:_safe(r.get('recoverable_ibnr_close_prior'))-_safe(r.get('recoverable_ibnr_open_prior')),62:oc,63:_safe(r.get('recoverable_case_close_current')),64:_safe(r.get('recoverable_case_close_prior')),65:_safe(r.get('recoverable_case_close_current'))-_safe(r.get('recoverable_case_open_current')),66:_safe(r.get('recoverable_case_close_prior'))-_safe(r.get('recoverable_case_open_prior')),79:0.0,81:0.0,82:0.0}
    return vals.get(row,0.0)


def _setup_local_sheet(ws, labels, title, note, max_row):
    ws.sheet_view.showGridLines=False; ws.freeze_panes='B7'; ws.column_dimensions['A'].width=40
    ws['A1']=title; ws['A1'].font=Font(bold=True,size=12,color=WHITE); ws['A1'].fill=PatternFill('solid',fgColor=DARK)
    ws['A2']=note; ws['A2'].font=Font(italic=True,color='7F6000'); ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=10)
    ws['A4']='Local GAAP'; ws['A5']='F CFA'
    for r,label in labels.items(): ws.cell(r,1,label)
    ws.cell(max_row,1,' ')  # materialise legacy sheet height
    for r in range(1,max_row+1):
        ws.cell(r,1).alignment=Alignment(vertical='center')
    for r in [7,14,18,20,36,41,45,51,57,64,71,75,82,93,109]:
        if r<=max_row:
            ws.cell(r,1).font=Font(bold=True)
            ws.cell(r,1).fill=PatternFill('solid',fgColor=PALE)


def _hyp_rows_for_period(hyp, period):
    if hyp is None or len(hyp)==0: return {}
    h=pd.DataFrame(hyp).copy(); p=str(pd.Period(period,freq='M'))
    h=h[h['period'].astype(str)==p]
    return {(str(r['branch']),str(r['metric'])):r for _,r in h.iterrows()}


def _hyp_applied(hmap, branch, metric):
    r=hmap.get((branch,metric))
    return None if r is None else _safe(r.get('applied_pct'))/100.0


def _derived_progression(curr, prev, field):
    if curr is None or prev is None: return None
    a=_safe(prev.get(field)); b=_safe(curr.get(field))
    if abs(a)<1e-9: return None
    return b/a-1.0


def _populate_local(ws, df, kind='direct', applied_hyp=None):
    periods=_periods(df); max_row=215 if kind=='direct' else 108
    labels=DIRECT_LABELS if kind=='direct' else REASS_LABELS
    note=('Moteur piloté par %. Ouvertures annuelles fixes; PAP/PANE fixes; prime acquise monotone. '
          'Direct: progression des flux + taux commission/REC. Réassurance: taux de cession primes + taux de récupération sinistres.')
    _setup_local_sheet(ws,labels,'Projection '+('Direct Local' if kind=='direct' else 'Reass Local'),note,max_row)
    for i,p in enumerate(periods):
        start=(2 if i==0 else 13+12*(i-1)) if kind=='direct' else 2+12*i
        rows=_rows_for_period(df,p); prevrows=_rows_for_period(df,periods[i-1]) if i>0 and periods[i-1].year==p.year else {}
        hmap=_hyp_rows_for_period(applied_hyp,p)
        ws.cell(4,start,'SanlamAllianz LIC Tool'); ws.cell(4,start+4,f"{FR_MONTHS[p.month]} {p.year}")
        for k,(en,fr) in enumerate(zip(EN_BRANCHES,BRANCHES)):
            ws.cell(5,start+k,en); ws.cell(6,start+k,fr)
        ws.cell(6,start+8,'Corporate'); ws.cell(6,start+9,'Global')
        for c in range(start,start+10):
            ws.cell(5,c).font=Font(bold=True,color=WHITE); ws.cell(5,c).fill=PatternFill('solid',fgColor=DARK); ws.cell(5,c).alignment=Alignment(horizontal='center')
            ws.cell(6,c).font=Font(bold=True); ws.cell(6,c).fill=PatternFill('solid',fgColor=LIGHT); ws.cell(6,c).alignment=Alignment(horizontal='center',wrap_text=True)
            ws.column_dimensions[get_column_letter(c)].width=16
        ws.column_dimensions[get_column_letter(start+10)].width=2.5; ws.column_dimensions[get_column_letter(start+11)].width=2.5
        ws.cell(6,start+10,' '); ws.cell(6,start+11,' ')
        value_fn=_direct_value if kind=='direct' else _reass_value
        # Financial block. Percentage rows are filled separately below.
        pct_rows=set(range(131,153)) if kind=='direct' else set(range(87,109))
        for row in labels:
            if row in pct_rows: continue
            branch_vals=[]
            for k,b in enumerate(BRANCHES):
                v=value_fn(rows.get(b),row); branch_vals.append(v); ws.cell(row,start+k,v)
            corp=sum(branch_vals[BRANCHES.index(b)] for b in CORPORATE_BRANCHES); glob=sum(branch_vals)
            ws.cell(row,start+8,corp); ws.cell(row,start+9,glob)
            for c in range(start,start+10): ws.cell(row,c).number_format='#,##0;[Red](#,##0);-'

        if kind=='direct':
            ws.cell(131,start,'%'); ws.cell(133,start,'Paramètre')
            row_metric={134:'Primes Emises',139:'Sinistres payés Per.',140:'Sinistres payés Ant.',141:'Taux commission / primes',143:'Taux REC clôture / primes',146:'Recours Per.',147:'Recours Ant.',149:'Part IBNR Per. / provisions',150:'Part IBNR Ant. / provisions',151:'Charge sinistres Per.',152:'Charge sinistres Ant.'}
            for k,b in enumerate(BRANCHES):
                c=start+k
                # January is an annual YTD reset/start; pd.xlsx starts the progression logic from February.
                if p.month!=1:
                    for rr,metric in row_metric.items():
                        v=_hyp_applied(hmap,b,metric); ws.cell(rr,c,v if v is not None else None)
                    ws.cell(144,c,_derived_progression(rows.get(b),prevrows.get(b),'case_close_current'))
                    ws.cell(145,c,_derived_progression(rows.get(b),prevrows.get(b),'case_close_prior'))
                for rr in [135,136,137,138,142,148]: ws.cell(rr,c,0.0)
                for rr in range(134,153): ws.cell(rr,c).number_format='0.0%'
            # Corporate/global percentages are weighted/aggregate realised indicators where meaningful.
            for c in [start+8,start+9]:
                ws.cell(131,c,'%');
                for rr in range(134,153): ws.cell(rr,c).number_format='0.0%'
        else:
            ws.cell(87,start,'% Réassurance'); ws.cell(89,start,'Paramètre')
            row_metric={90:'Taux cession primes',95:'Taux récupération sinistres',96:'Taux récupération sinistres',97:'Taux commission réassurance',99:'Taux cession primes',100:'Taux cession primes',101:'Taux cession primes',102:'Taux récupération sinistres',103:'Taux récupération sinistres',107:'Taux récupération sinistres',108:'Taux récupération sinistres'}
            for k,b in enumerate(BRANCHES):
                c=start+k
                if p.month!=1:
                    for rr,metric in row_metric.items():
                        v=_hyp_applied(hmap,b,metric); ws.cell(rr,c,v if v is not None else None)
                for rr in [91,92,93,94,98,106]: ws.cell(rr,c,0.0)
                for rr in range(90,109): ws.cell(rr,c).number_format='0.0%'
    return periods


def _group_metric(rows, members, getter):
    return sum(getter(rows.get(b)) for b in members)


def _gross_metrics(r):
    if r is None: return {k:0.0 for k in ['written','var_upr','earned','paid_cur','prov_cur','inc_cur','paid_pr','prov_pr','inc_pr','inc','comm']}
    paid_cur=max(0.0,_safe(r.get('paid_current_ytd'))-_safe(r.get('recourse_current_ytd')))
    paid_pr=max(0.0,_safe(r.get('paid_prior_ytd'))-_safe(r.get('recourse_prior_ytd')))
    prov_cur=(_safe(r.get('case_close_current'))+_safe(r.get('ibnr_close_current')))-(_safe(r.get('case_open_current'))+_safe(r.get('ibnr_open_current')))
    prov_pr=(_safe(r.get('case_close_prior'))+_safe(r.get('ibnr_close_prior')))-(_safe(r.get('case_open_prior'))+_safe(r.get('ibnr_open_prior')))
    return {'written':_safe(r.get('gwp_ytd')),'var_upr':_safe(r.get('upr_open'))-_safe(r.get('upr_close')),'earned':_safe(r.get('earned_premium_ytd')),'paid_cur':paid_cur,'prov_cur':prov_cur,'inc_cur':_safe(r.get('incurred_current_ytd')),'paid_pr':paid_pr,'prov_pr':prov_pr,'inc_pr':_safe(r.get('incurred_prior_ytd')),'inc':_safe(r.get('incurred_current_ytd'))+_safe(r.get('incurred_prior_ytd')),'comm':_safe(r.get('commission_ytd'))+_safe(r.get('dac_variation')),'comm_base':_safe(r.get('commission_ytd')),'dac':_safe(r.get('dac_variation'))}


def _reass_metrics(r):
    if r is None: return {k:0.0 for k in ['written','var_upr','earned','paid_cur','prov_cur','inc_cur','paid_pr','prov_pr','inc_pr','inc','comm']}
    prov_cur=(_safe(r.get('recoverable_case_close_current'))+_safe(r.get('recoverable_ibnr_close_current')))-(_safe(r.get('recoverable_case_open_current'))+_safe(r.get('recoverable_ibnr_open_current')))
    prov_pr=(_safe(r.get('recoverable_case_close_prior'))+_safe(r.get('recoverable_ibnr_close_prior')))-(_safe(r.get('recoverable_case_open_prior'))+_safe(r.get('recoverable_ibnr_open_prior')))
    return {'written':_safe(r.get('ceded_premium_ytd')),'var_upr':_safe(r.get('ceded_upr_close'))-_safe(r.get('ceded_upr_open')),'earned':_safe(r.get('ceded_earned_premium_ytd')),'paid_cur':_safe(r.get('recovered_paid_current_ytd')),'prov_cur':prov_cur,'inc_cur':_safe(r.get('recovered_incurred_current_ytd')),'paid_pr':_safe(r.get('recovered_paid_prior_ytd')),'prov_pr':prov_pr,'inc_pr':_safe(r.get('recovered_incurred_prior_ytd')),'inc':_safe(r.get('recovered_incurred_current_ytd'))+_safe(r.get('recovered_incurred_prior_ytd')),'comm':_safe(r.get('reass_commission_ytd'))-_safe(r.get('dac_variation')),'comm_base':_safe(r.get('reass_commission_ytd')),'dac':_safe(r.get('dac_variation'))}


def _sum_metrics(rows,members,fn):
    keys=['written','var_upr','earned','paid_cur','prov_cur','inc_cur','paid_pr','prov_pr','inc_pr','inc','comm','comm_base','dac']
    out={k:0.0 for k in keys}
    for b in members:
        m=fn(rows.get(b))
        for k in keys: out[k]+=m[k]
    return out


def _cpc_values(g,r):
    # CPC sign convention: premiums positive; gross claims/commissions negative; reinsurance recoveries/commissions positive.
    v={}
    v[5]=g['written']; v[6]=g['var_upr']; v[7]=g['earned']
    v[9]=-g['paid_cur']; v[10]=-g['prov_cur']; v[11]=-g['inc_cur']
    v[12]=-g['paid_pr']; v[13]=-g['prov_pr']; v[14]=-g['inc_pr']; v[15]=-g['inc']
    v[17]=-g.get('comm_base',g['comm']); v[18]=-g.get('dac',0.0); v[19]=v[17]+v[18]
    for rr in range(21,42): v[rr]=0.0
    v[43]=v[7]+v[15]+v[19]+v[41]
    v[46]=g['inc_cur']/g['earned'] if abs(g['earned'])>1e-9 else 0.0
    v[47]=g['inc']/g['earned'] if abs(g['earned'])>1e-9 else 0.0
    v[48]=g['comm']/g['earned'] if abs(g['earned'])>1e-9 else 0.0
    v[49]=0.0; v[50]=v[47]+v[48]+v[49]
    v[53]=-r['written']; v[54]=r['var_upr']; v[55]=-r['earned']
    v[57]=r['paid_cur']; v[58]=r['prov_cur']; v[59]=r['inc_cur']
    v[60]=r['paid_pr']; v[61]=r['prov_pr']; v[62]=r['inc_pr']; v[63]=r['inc']
    v[65]=r.get('comm_base',r['comm']); v[66]=-r.get('dac',0.0); v[67]=v[65]+v[66]; v[69]=v[55]+v[63]+v[67]
    v[72]=r['written']/g['written'] if abs(g['written'])>1e-9 else 0.0
    v[73]=r['inc']/g['inc'] if abs(g['inc'])>1e-9 else 0.0
    v[76]=v[5]+v[53]; v[77]=v[6]+v[54]; v[78]=v[7]+v[55]
    v[80]=v[9]+v[57]; v[81]=v[10]+v[58]; v[82]=v[11]+v[59]
    v[83]=v[12]+v[60]; v[84]=v[13]+v[61]; v[85]=v[14]+v[62]; v[86]=v[15]+v[63]
    v[88]=v[17]+v[65]; v[89]=v[18]+v[66]; v[90]=v[88]+v[89]
    for rr in range(92,113): v[rr]=0.0
    v[114]=v[78]+v[86]+v[90]+v[112]
    v[117]=(-v[82]/v[78]) if abs(v[78])>1e-9 else 0.0
    v[118]=(-v[86]/v[78]) if abs(v[78])>1e-9 else 0.0
    v[119]=(-v[90]/v[78]) if abs(v[78])>1e-9 else 0.0
    v[120]=0.0; v[121]=v[118]+v[119]+v[120]
    for rr in range(124,145): v[rr]=0.0
    v[135]=0.0; v[143]=0.0; v[144]=0.0; v[146]=v[114]
    v[148]=v[114]; v[149]=0.022*v[5]; v[150]=0.33*v[114]
    return v


def _populate_cpc(ws,direct,reass):
    periods=_periods(direct); ws.sheet_view.showGridLines=False; ws.freeze_panes='D5'; ws.column_dimensions['B'].width=48
    ws['A1']='CONSOLIDATION '; ws['B1']='IFRS 4'; ws['B2']='Projection technique';
    # Preserve the historical CPC sheet height used by pd.xlsx.
    ws.cell(244,1,' ')
    ws['A3']='Note'; ws['B3']='Frais généraux et produits financiers hors moteur: lignes correspondantes exportées à 0. CPC calculé uniquement à partir de Direct + Réassurance.'
    for r,label in CPC_LABELS.items(): ws.cell(r,2,label)
    for r in [4,45,52,71,75,116,124,148]:
        ws.cell(r,2).font=Font(bold=True,color=WHITE); ws.cell(r,2).fill=PatternFill('solid',fgColor=DARK)
    for i,p in enumerate(periods):
        start=4 if i==0 else 32+27*(i-1)
        drows=_rows_for_period(direct,p); rrows=_rows_for_period(reass,p)
        ws.merge_cells(start_row=1,start_column=start,end_row=1,end_column=start+6)
        ws.cell(1,start,f"{FR_MONTHS[p.month]} {p.year}"); ws.cell(1,start).font=Font(bold=True,size=11); ws.cell(1,start).alignment=Alignment(horizontal='center')
        headers=['CONSOLIDATION ','INCENDIE','AUTO','RD','RC','TRANS','SANTE','VAR N/N-1','VAR ABS','VAR N/Forecast ','VAR %']
        for k,h in enumerate(headers):
            ws.cell(2,start+k,h); ws.cell(2,start+k).font=Font(bold=True,color=WHITE); ws.cell(2,start+k).fill=PatternFill('solid',fgColor=DARK); ws.cell(2,start+k).alignment=Alignment(horizontal='center',wrap_text=True); ws.column_dimensions[get_column_letter(start+k)].width=15
        group_defs=[('CONSOLIDATION ',BRANCHES)]+list(CPC_GROUPS.items())
        for k,(gname,members) in enumerate(group_defs):
            gm=_sum_metrics(drows,members,_gross_metrics); rm=_sum_metrics(rrows,members,_reass_metrics); vals=_cpc_values(gm,rm)
            c=start+k
            for row,val in vals.items():
                ws.cell(row,c,val)
                ws.cell(row,c).number_format='0.0%' if row in [46,47,48,49,50,72,73,117,118,119,120,121] else '#,##0;[Red](#,##0);-'
        # Comparison columns intentionally blank/zero: no N-1 or separate Forecast dataset is generated by the engine.
        for c in range(start+7,start+11):
            for row in [5,6,7,43,46,47,48,49,50,53,55,63,69,72,73,76,78,86,90,114,117,118,119,120,121,146]: ws.cell(row,c,0.0)
        # Leave the remaining legacy-width columns blank so each block keeps the approximate CPC SAZ footprint.
        for c in range(start+11,start+27): ws.column_dimensions[get_column_letter(c)].width=2.2
        # pd.xlsx keeps a wide legacy block; materialise its trailing edge.
        ws.cell(2,start+25,' ')
    return periods


def _write_hyp_sheet(ws, hyp, title):
    ws.sheet_view.showGridLines=False; ws.freeze_panes='D4'
    ws['A1']=title; ws['A1'].font=Font(bold=True,size=13,color=WHITE); ws['A1'].fill=PatternFill('solid',fgColor=DARK)
    ws['A2']='Base % = historique (modifiable). Ajustement manuel = +/- points de pourcentage. Ajustement cible = calcul automatique éventuel. Appliqué = somme des trois.'
    h=pd.DataFrame(hyp).copy()
    if h.empty: return
    periods=sorted(h['period'].astype(str).unique())
    r0=4
    for per in periods:
        ph=h[h['period'].astype(str)==per]
        ws.cell(r0,1,per); ws.cell(r0,1).font=Font(bold=True,color=WHITE); ws.cell(r0,1).fill=PatternFill('solid',fgColor=DARK)
        headers=['Metric']
        for b in BRANCHES: headers += [f'{b} Base %',f'{b} Ajust. pts',f'{b} Ajust. cible',f'{b} Appliqué %']
        for j,x in enumerate(headers,1):
            ws.cell(r0+1,j,x); ws.cell(r0+1,j).font=Font(bold=True); ws.cell(r0+1,j).fill=PatternFill('solid',fgColor=LIGHT); ws.cell(r0+1,j).alignment=Alignment(horizontal='center',wrap_text=True)
        metrics=list(dict.fromkeys(ph['metric'].tolist()))
        for i,m in enumerate(metrics):
            rr=r0+2+i; ws.cell(rr,1,m)
            for bi,b in enumerate(BRANCHES):
                x=ph[(ph['branch']==b)&(ph['metric']==m)]
                if x.empty: continue
                z=x.iloc[0]; c=2+bi*4
                ws.cell(rr,c,_safe(z.get('base_pct'))/100.0); ws.cell(rr,c+1,_safe(z.get('adjustment_pts'))/100.0); ws.cell(rr,c+2,_safe(z.get('target_adjustment_pts'))/100.0); ws.cell(rr,c+3,_safe(z.get('applied_pct'))/100.0)
                for cc in range(c,c+4): ws.cell(rr,cc).number_format='0.00%'
                ws.cell(rr,c).font=Font(color='0000FF'); ws.cell(rr,c+1).font=Font(color='0000FF'); ws.cell(rr,c+2).font=Font(color='008000'); ws.cell(rr,c+3).font=Font(color=BLACK)
        r0 += len(metrics)+4
    ws.column_dimensions['A'].width=34
    for c in range(2,34): ws.column_dimensions[get_column_letter(c)].width=13


def _write_cibles_sheet(ws, cibles_direct, cibles_reass):
    ws.sheet_view.showGridLines=False; ws['A1']='Cibles optionnelles'; ws['A1'].font=Font(bold=True,size=13,color=WHITE); ws['A1'].fill=PatternFill('solid',fgColor=DARK)
    ws['A2']='Les cellules vides ne contraignent pas le moteur. Les cibles de fin d’année peuvent générer automatiquement un ajustement +/-Y dans Hyp Direct / Hyp Reass.'
    r=4
    for title,df in [('Direct',cibles_direct),('Réassurance',cibles_reass)]:
        ws.cell(r,1,title); ws.cell(r,1).font=Font(bold=True,color=WHITE); ws.cell(r,1).fill=PatternFill('solid',fgColor=DARK); r+=1
        d=pd.DataFrame(df).copy(); cols=list(d.columns)
        for j,c in enumerate(cols,1): ws.cell(r,j,c); ws.cell(r,j).font=Font(bold=True); ws.cell(r,j).fill=PatternFill('solid',fgColor=LIGHT)
        for _,row in d.iterrows():
            r+=1
            for j,c in enumerate(cols,1):
                v=row[c]; ws.cell(r,j,None if pd.isna(v) else v)
                if j>2 and isinstance(v,(int,float,np.number)): ws.cell(r,j).font=Font(color='0000FF'); ws.cell(r,j).number_format='#,##0;[Red](#,##0);-'
        r+=3
    for c in range(1,ws.max_column+1): ws.column_dimensions[get_column_letter(c)].width=18 if c>2 else 16

def export_projection(path, inputs: dict, direct, reass, summary, diagnostics, applied_direct=None, applied_reass=None):
    direct=pd.DataFrame(direct).copy(); reass=pd.DataFrame(reass).copy(); summary=pd.DataFrame(summary).copy()
    wb=Workbook(); wb.remove(wb.active)
    # Only the useful production sheets + transparent hypotheses/cibles.
    ws=wb.create_sheet('Hyp Direct'); _write_hyp_sheet(ws,pd.DataFrame(applied_direct),'Hyp Direct — % de base, ajustements et % appliqués')
    ws=wb.create_sheet('Hyp Reass'); _write_hyp_sheet(ws,pd.DataFrame(applied_reass),'Hyp Reass — cession, récupération et commission')
    ws=wb.create_sheet('Cibles'); _write_cibles_sheet(ws,inputs.get('cibles_direct'),inputs.get('cibles_reass'))
    ws=wb.create_sheet('Direct Local'); _populate_local(ws,direct,'direct',applied_direct)
    ws=wb.create_sheet('Reass Local'); _populate_local(ws,reass,'reass',applied_reass)
    ws=wb.create_sheet('CPC SAZ'); _populate_cpc(ws,direct,reass)
    wb.save(path); return path

