from __future__ import annotations
from pathlib import Path
import math
import pandas as pd
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

from exporter import (
    BRANCHES, EN_BRANCHES, CORPORATE_BRANCHES, CPC_GROUPS,
    DIRECT_LABELS, REASS_LABELS, CPC_LABELS, FR_MONTHS,
    DARK, LIGHT, PALE, GREY, GOLD, BLACK, WHITE,
)

DIRECT_METRICS = [
    "Primes Emises","Charge sinistres Per.","Charge sinistres Ant.",
    "Sinistres payés Per.","Sinistres payés Ant.","Recours Per.","Recours Ant.",
    "Taux commission / primes","Taux REC clôture / primes",
    "Part IBNR Per. / provisions","Part IBNR Ant. / provisions",
]
REASS_METRICS = ["Taux cession primes","Taux récupération sinistres","Taux REC réassurance / primes cédées","Taux commission réassurance"]
RATE_METRICS = {
    "Taux commission / primes","Taux REC clôture / primes",
    "Part IBNR Per. / provisions","Part IBNR Ant. / provisions",
    "Taux cession primes","Taux récupération sinistres","Taux REC réassurance / primes cédées","Taux commission réassurance",
}

ANCHOR_FIELDS = [
    ("gwp_ytd","Primes émises / CA"),
    ("paid_current_ytd","Sinistres payés Per."),
    ("paid_prior_ytd","Sinistres payés Ant."),
    ("recourse_current_ytd","Recours Per."),
    ("recourse_prior_ytd","Recours Ant."),
    ("pap_open","PAP ouverture"),("pap_close","PAP clôture"),
    ("pane_open","PANE ouverture"),("pane_close","PANE clôture"),
    ("upr_open","REC ouverture"),
    ("case_open_current","SAP ouverture Per."),("case_open_prior","SAP ouverture Ant."),
    ("ibnr_open_current","IBNR ouverture Per."),("ibnr_open_prior","IBNR ouverture Ant."),
    ("incurred_current_ytd","Charge sinistres Per."),("incurred_prior_ytd","Charge sinistres Ant."),
]

TARGET_DIRECT_HEADERS = {
    "year":"Année", "branch":"Branche",
    "gwp_start":"Primes émises — Début", "gwp_end":"Primes émises — Fin",
    "incurred_current_start":"Charge sinistres exercice — Début", "incurred_current_end":"Charge sinistres exercice — Fin",
    "incurred_prior_start":"Charge sinistres antérieurs — Début", "incurred_prior_end":"Charge sinistres antérieurs — Fin",
    "paid_current_start":"Sinistres payés exercice — Début", "paid_current_end":"Sinistres payés exercice — Fin",
    "paid_prior_start":"Sinistres payés antérieurs — Début", "paid_prior_end":"Sinistres payés antérieurs — Fin",
    "recourse_current_start":"Recours exercice — Début", "recourse_current_end":"Recours exercice — Fin",
    "recourse_prior_start":"Recours antérieurs — Début", "recourse_prior_end":"Recours antérieurs — Fin",
    "commission_end":"Commissions — Fin", "upr_close_end":"REC clôture — Fin",
}
TARGET_REASS_HEADERS = {
    "year":"Année", "branch":"Branche",
    "ceded_premium_start":"Primes cédées — Début", "ceded_premium_end":"Primes cédées — Fin",
    "recovered_incurred_start":"Sinistres récupérés — Début", "recovered_incurred_end":"Sinistres récupérés — Fin",
    "reass_commission_end":"Commission de réassurance — Fin",
}

SOFT_BLUE='DCEEF8'; SOFT_ORANGE='F8CBAD'; SOFT_YELLOW='FFF2CC'; SOFT_GREEN='E2F0D9'; SOFT_PURPLE='D9B2D9'; SOFT_PEACH='FCE4D6'; HEADER_BLUE='2F75B5'



def _safe(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else 0.0
    except Exception:
        return 0.0


def _abs(addr: str) -> str:
    # A1 -> $A$1
    import re
    m=re.match(r"([A-Z]+)(\d+)$",addr)
    return f"${m.group(1)}${m.group(2)}" if m else addr


def _q(sheet: str, addr: str) -> str:
    return f"'{sheet}'!{_abs(addr)}"


def _periods(df):
    if df is None or len(df)==0: return []
    d=pd.DataFrame(df).copy(); d['period']=pd.to_datetime(d['period'])
    return sorted(d['period'].drop_duplicates().tolist())


def _rows_for_period(df, period):
    d=pd.DataFrame(df).copy(); d['period']=pd.to_datetime(d['period'])
    x=d[d['period']==pd.Timestamp(period)]
    return {r['branch']:r for _,r in x.iterrows()}


def _direct_start(i):
    return 2 if i==0 else 1+12*i


def _reass_start(i):
    return 2+12*i


def _cpc_start(i):
    return 4 if i==0 else 32+27*(i-1)


def _setup_local_sheet(ws, labels, title, note, max_row):
    ws.sheet_view.showGridLines=False; ws.freeze_panes='B7'; ws.column_dimensions['A'].width=39
    ws['A1']=title; ws['A1'].font=Font(bold=True,size=12,color=WHITE); ws['A1'].fill=PatternFill('solid',fgColor=DARK)
    ws['A2']=note; ws['A2'].font=Font(italic=True,color='6B7280'); ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=10)
    ws['A4']='Local GAAP'; ws['A5']='F CFA'
    for r,label in labels.items(): ws.cell(r,1,label)
    ws.cell(max_row,1,' ')
    for r in range(1,max_row+1): ws.cell(r,1).alignment=Alignment(vertical='center')
    for r in [7,14,18,20,36,41,45,51,57,64,71,75,82,93,109,131] if max_row>=131 else [7,14,18,20,36,40,44,48,54,61,68,72,79,87]:
        if r<=max_row:
            ws.cell(r,1).font=Font(bold=True)
            ws.cell(r,1).fill=PatternFill('solid',fgColor=PALE)


def _write_hyp_sheet(ws, hyp, title, direct=None, kind='direct'):
    """Write inputs and return formula reference maps.
    Inputs are hardcoded by design; Applied % is always an Excel formula.
    For Direct, annual/first-period anchors are also written as editable inputs.
    """
    ws.sheet_view.showGridLines=False
    ws['A1']=title; ws['A1'].font=Font(bold=True,size=14,color=WHITE); ws['A1'].fill=PatternFill('solid',fgColor=DARK)
    ws['A2']='Bleu = input modifiable. Vert = ajustement cible calculé. % appliqué = Base + Ajustement manuel + Ajustement cible (formule Excel).'
    ws['A2'].font=Font(italic=True,color='64748B')
    anchor_map={}
    r0=4
    if kind=='direct' and direct is not None and len(direct):
        d=pd.DataFrame(direct).copy(); d['period']=pd.to_datetime(d['period'])
        ws.cell(r0,1,'ANCRAGES — premier mois sélectionné de chaque exercice')
        ws.cell(r0,1).font=Font(bold=True,color=WHITE); ws.cell(r0,1).fill=PatternFill('solid',fgColor=DARK)
        headers=['Année','Période','Branche']+[label for _,label in ANCHOR_FIELDS]
        for j,h in enumerate(headers,1):
            c=ws.cell(r0+1,j,h); c.font=Font(bold=True); c.fill=PatternFill('solid',fgColor=LIGHT); c.alignment=Alignment(horizontal='center',wrap_text=True)
        rr=r0+2
        for year in sorted(d['period'].dt.year.unique()):
            yd=d[d['period'].dt.year==year]
            first=yd['period'].min(); rows=yd[yd['period']==first]
            for b in BRANCHES:
                x=rows[rows['branch']==b]
                if x.empty: continue
                z=x.iloc[0]
                ws.cell(rr,1,int(year)); ws.cell(rr,2,str(pd.Period(first,freq='M'))); ws.cell(rr,3,b)
                for j,(field,_) in enumerate(ANCHOR_FIELDS,4):
                    cell=ws.cell(rr,j,_safe(z.get(field)))
                    cell.font=Font(color='1D4ED8'); cell.number_format='#,##0;[Red](#,##0);-'
                    anchor_map[(int(year),b,field)]=cell.coordinate
                rr+=1
        r0=rr+2

    h=pd.DataFrame(hyp).copy()
    hyp_map={}
    if h.empty:
        return hyp_map,anchor_map
    periods=sorted(h['period'].astype(str).unique())
    for per in periods:
        ph=h[h['period'].astype(str)==per]
        ws.cell(r0,1,per); ws.cell(r0,1).font=Font(bold=True,color=WHITE); ws.cell(r0,1).fill=PatternFill('solid',fgColor=DARK)
        headers=['Paramètre']
        for b in BRANCHES: headers += [f'{b} Base %',f'{b} +/- pts',f'{b} Target adj.',f'{b} % appliqué']
        for j,x in enumerate(headers,1):
            c=ws.cell(r0+1,j,x); c.font=Font(bold=True); c.fill=PatternFill('solid',fgColor=LIGHT); c.alignment=Alignment(horizontal='center',wrap_text=True)
        metrics=list(dict.fromkeys(ph['metric'].tolist()))
        for i,m in enumerate(metrics):
            rr=r0+2+i; ws.cell(rr,1,m)
            for bi,b in enumerate(BRANCHES):
                x=ph[(ph['branch']==b)&(ph['metric']==m)]
                if x.empty: continue
                z=x.iloc[0]; c=2+bi*4
                base=ws.cell(rr,c,_safe(z.get('base_pct'))/100.0); manual=ws.cell(rr,c+1,_safe(z.get('adjustment_pts'))/100.0); target=ws.cell(rr,c+2,_safe(z.get('target_adjustment_pts'))/100.0)
                applied=ws.cell(rr,c+3); applied.value=f"=SUM({base.coordinate}:{target.coordinate})"
                for cc in [base,manual,target,applied]: cc.number_format='0.00%'
                base.font=Font(color='1D4ED8'); manual.font=Font(color='1D4ED8'); target.font=Font(color='15803D'); applied.font=Font(color=BLACK,bold=True)
                hyp_map[(per,b,m)]=applied.coordinate
        r0 += len(metrics)+4
    ws.freeze_panes=f'D{max(4, r0-len(metrics)-3)}'
    ws.column_dimensions['A'].width=34
    for c in range(2,34): ws.column_dimensions[get_column_letter(c)].width=12.5
    return hyp_map,anchor_map


def _write_targets_sheet(ws, cibles_direct, cibles_reass):
    ws.sheet_view.showGridLines=False
    ws['A1']='Cibles optionnelles'; ws['A1'].font=Font(bold=True,size=14,color=WHITE); ws['A1'].fill=PatternFill('solid',fgColor=DARK)
    ws['A2']='Entrées optionnelles. Renseignez une valeur de début, de fin, les deux, ou laissez vide. Les cibles servent à calculer les ajustements d’atterrissage ; le classeur reste pilotable via les pourcentages de Hyp Direct / Hyp Reass.'
    ws['A2'].font=Font(italic=True,color='64748B')
    r=4
    for title,df,mapping in [('Direct',cibles_direct,TARGET_DIRECT_HEADERS),('Réassurance',cibles_reass,TARGET_REASS_HEADERS)]:
        ws.cell(r,1,title); ws.cell(r,1).font=Font(bold=True,color=WHITE); ws.cell(r,1).fill=PatternFill('solid',fgColor=DARK); r+=1
        d=pd.DataFrame(df).copy(); cols=list(d.columns)
        for j,cname in enumerate(cols,1):
            label=mapping.get(cname,cname)
            c=ws.cell(r,j,label); c.font=Font(bold=True,color='17365D'); c.fill=PatternFill('solid',fgColor=LIGHT); c.alignment=Alignment(horizontal='center',wrap_text=True)
        for _,row in d.iterrows():
            r+=1
            for j,cname in enumerate(cols,1):
                v=row[cname]; cell=ws.cell(r,j,None if pd.isna(v) else v)
                if j>2:
                    cell.font=Font(color='0000FF'); cell.fill=PatternFill('solid',fgColor='FFFDF2'); cell.number_format='#,##0;[Red](#,##0);-'
        r+=3
    for c in range(1,ws.max_column+1): ws.column_dimensions[get_column_letter(c)].width=24 if c>2 else 16


def _hformula(hyp_map, period, branch, metric, sheet):
    key=(str(pd.Period(period,freq='M')),branch,metric)
    addr=hyp_map.get(key)
    return _q(sheet,addr) if addr else '0'


def _aformula(anchor_map, year, branch, field):
    addr=anchor_map.get((int(year),branch,field))
    return _q('Hyp Direct',addr) if addr else '0'


def _set_amount_totals(ws,start,row):
    corp_cols=[start+BRANCHES.index(b) for b in CORPORATE_BRANCHES]
    branch_cols=[start+i for i in range(8)]
    corp='+'.join(f'{get_column_letter(c)}{row}' for c in corp_cols)
    glob='+'.join(f'{get_column_letter(c)}{row}' for c in branch_cols)
    ws.cell(row,start+8,f'={corp}' if corp else '=0')
    ws.cell(row,start+9,f'={glob}' if glob else '=0')
    ws.cell(row,start+8).number_format='#,##0;[Red](#,##0);-'; ws.cell(row,start+9).number_format='#,##0;[Red](#,##0);-'


def _style_local_block(ws,start,kind='direct'):
    # Softer interpretation of the pd.xlsx visual language.
    for c in range(start,start+10):
        ws.cell(4,c).fill=PatternFill('solid',fgColor=DARK); ws.cell(4,c).font=Font(color=WHITE,bold=True)
        ws.cell(5,c).fill=PatternFill('solid',fgColor=DARK); ws.cell(5,c).font=Font(color=WHITE,bold=True)
        ws.cell(6,c).fill=PatternFill('solid',fgColor=HEADER_BLUE); ws.cell(6,c).font=Font(color=WHITE,bold=True)
    if kind=='direct':
        row_styles={
            12:SOFT_BLUE,14:SOFT_ORANGE,16:SOFT_BLUE,18:SOFT_BLUE,22:SOFT_BLUE,
            36:SOFT_YELLOW,37:SOFT_ORANGE,38:SOFT_BLUE,41:SOFT_YELLOW,42:SOFT_ORANGE,
            45:SOFT_YELLOW,46:SOFT_YELLOW,49:SOFT_BLUE,51:PALE,57:PALE,64:PALE,71:PALE,75:PALE,82:PALE,93:PALE,
            131:DARK,133:LIGHT,
        }
    else:
        row_styles={
            12:SOFT_BLUE,14:SOFT_ORANGE,16:SOFT_BLUE,18:SOFT_BLUE,22:SOFT_BLUE,
            36:SOFT_YELLOW,37:SOFT_ORANGE,38:SOFT_BLUE,40:SOFT_YELLOW,41:SOFT_ORANGE,
            44:SOFT_YELLOW,45:SOFT_YELLOW,46:SOFT_BLUE,48:PALE,54:PALE,61:PALE,68:PALE,72:PALE,79:PALE,87:DARK,89:LIGHT,
        }
    for r,fill in row_styles.items():
        for c in range(start,start+10):
            ws.cell(r,c).fill=PatternFill('solid',fgColor=fill)
            if fill==DARK: ws.cell(r,c).font=Font(color=WHITE,bold=True)
            elif r in [12,16,18,22,38,46,49]: ws.cell(r,c).font=Font(bold=True)

def _populate_direct_formula(ws,direct,hyp_map,anchor_map):
    periods=_periods(direct)
    note='V2 formule: les inputs résident dans Hyp Direct. Les montants, variations, provisions et totaux de Direct Local sont des formules Excel.'
    _setup_local_sheet(ws,DIRECT_LABELS,'Projection Direct Local — V2 formules',note,215)
    # Scratch rows are intentionally hidden; they keep charge/provision identities transparent without adding another sheet.
    calc_labels={160:'[calc] Charge Per. réelle',161:'[calc] Charge Ant. réelle',162:'[calc] Provision clôture Per.',163:'[calc] Provision clôture Ant.',164:'[calc] IBNR ouverture Per.',165:'[calc] IBNR ouverture Ant.',166:'[calc] SAP ouverture Per.',167:'[calc] SAP ouverture Ant.',168:'[calc] Part IBNR Per.',169:'[calc] Part IBNR Ant.',170:'[calc] Charge Per. souhaitée',171:'[calc] Charge Ant. souhaitée'}
    for r,l in calc_labels.items(): ws.cell(r,1,l); ws.row_dimensions[r].hidden=True
    first_index_by_year={}
    for i,p in enumerate(periods): first_index_by_year.setdefault(p.year,i)
    for i,p in enumerate(periods):
        start=_direct_start(i); is_year_first=(first_index_by_year[p.year]==i); prev_start=_direct_start(i-1) if i>0 else None
        ws.cell(4,start,'SanlamAllianz LIC Tool'); ws.cell(4,start+4,f'{FR_MONTHS[p.month]} {p.year}')
        for k,(en,fr) in enumerate(zip(EN_BRANCHES,BRANCHES)):
            ws.cell(5,start+k,en); ws.cell(6,start+k,fr)
        ws.cell(6,start+8,'Corporate'); ws.cell(6,start+9,'Global')
        for c in range(start,start+10):
            ws.cell(5,c).font=Font(bold=True,color=WHITE); ws.cell(5,c).fill=PatternFill('solid',fgColor=DARK); ws.cell(5,c).alignment=Alignment(horizontal='center')
            ws.cell(6,c).font=Font(bold=True); ws.cell(6,c).fill=PatternFill('solid',fgColor=LIGHT); ws.cell(6,c).alignment=Alignment(horizontal='center',wrap_text=True); ws.column_dimensions[get_column_letter(c)].width=15
        ws.column_dimensions[get_column_letter(start+10)].width=2.5; ws.column_dimensions[get_column_letter(start+11)].width=2.5
        for k,b in enumerate(BRANCHES):
            c=start+k; col=get_column_letter(c); prev_col=get_column_letter(prev_start+k) if prev_start else None
            # Fixed annual openings / anchors.
            for row,field in [(8,'pap_open'),(9,'pap_close'),(10,'pane_open'),(11,'pane_close'),(20,'upr_open')]:
                ws.cell(row,c,f'={_aformula(anchor_map,p.year,b,field)}')
            ws.cell(164,c,f'={_aformula(anchor_map,p.year,b,"ibnr_open_current")}')
            ws.cell(165,c,f'={_aformula(anchor_map,p.year,b,"ibnr_open_prior")}')
            ws.cell(166,c,f'={_aformula(anchor_map,p.year,b,"case_open_current")}')
            ws.cell(167,c,f'={_aformula(anchor_map,p.year,b,"case_open_prior")}')
            # Progression-driven YTD lines.
            if is_year_first:
                ws.cell(7,c,f'={_aformula(anchor_map,p.year,b,"gwp_ytd")}')
                ws.cell(14,c,f'={_aformula(anchor_map,p.year,b,"paid_current_ytd")}')
                ws.cell(15,c,f'={_aformula(anchor_map,p.year,b,"paid_prior_ytd")}')
                ws.cell(47,c,f'={_aformula(anchor_map,p.year,b,"recourse_current_ytd")}')
                ws.cell(48,c,f'={_aformula(anchor_map,p.year,b,"recourse_prior_ytd")}')
                ws.cell(170,c,f'={_aformula(anchor_map,p.year,b,"incurred_current_ytd")}')
                ws.cell(171,c,f'={_aformula(anchor_map,p.year,b,"incurred_prior_ytd")}')
            else:
                ws.cell(7,c,f'={prev_col}7*(1+{_hformula(hyp_map,p,b,"Primes Emises","Hyp Direct")})')
                ws.cell(14,c,f'={prev_col}14*(1+{_hformula(hyp_map,p,b,"Sinistres payés Per.","Hyp Direct")})')
                ws.cell(15,c,f'={prev_col}15*(1+{_hformula(hyp_map,p,b,"Sinistres payés Ant.","Hyp Direct")})')
                ws.cell(47,c,f'={prev_col}47*(1+{_hformula(hyp_map,p,b,"Recours Per.","Hyp Direct")})')
                ws.cell(48,c,f'={prev_col}48*(1+{_hformula(hyp_map,p,b,"Recours Ant.","Hyp Direct")})')
                ws.cell(170,c,f'={prev_col}160*(1+{_hformula(hyp_map,p,b,"Charge sinistres Per.","Hyp Direct")})')
                ws.cell(171,c,f'={prev_col}161*(1+{_hformula(hyp_map,p,b,"Charge sinistres Ant.","Hyp Direct")})')
            # Business formulas.
            ws.cell(12,c,f'={col}7-{col}8+{col}9-{col}10+{col}11')
            ws.cell(16,c,f'=MAX(0,{col}14-{col}47)+MAX(0,{col}15-{col}48)')
            ws.cell(18,c,f'={col}7*{_hformula(hyp_map,p,b,"Taux commission / primes","Hyp Direct")}')
            if is_year_first:
                ws.cell(21,c,f'=MAX(0,MIN({col}7*{_hformula(hyp_map,p,b,"Taux REC clôture / primes","Hyp Direct")},{col}7+{col}20))')
            else:
                prev_earned=f'({prev_col}7+{prev_col}20-{prev_col}21)'
                ws.cell(21,c,f'=MAX(0,MIN({col}7*{_hformula(hyp_map,p,b,"Taux REC clôture / primes","Hyp Direct")},{col}7+{col}20-{prev_earned}))')
            ws.cell(22,c,f'={col}21-{col}20')
            ws.cell(24,c,f'=IFERROR({col}20/72%,0)'); ws.cell(25,c,f'=IFERROR({col}21/72%,0)'); ws.cell(26,c,f'={col}25-{col}24')
            ws.cell(28,c,'=0'); ws.cell(29,c,'=0'); ws.cell(30,c,f'={col}28-{col}29')
            ws.cell(32,c,f'={col}24-{col}20'); ws.cell(33,c,f'={col}25-{col}21'); ws.cell(34,c,f'={col}33-{col}32')
            # Provision engine: desired incurred charge -> non-negative closing provision -> realised incurred charge.
            ws.cell(168,c,f'={_hformula(hyp_map,p,b,"Part IBNR Per. / provisions","Hyp Direct")}')
            ws.cell(169,c,f'={_hformula(hyp_map,p,b,"Part IBNR Ant. / provisions","Hyp Direct")}')
            ws.cell(162,c,f'=MAX(0,{col}164+{col}166+{col}170-MAX(0,{col}14-{col}47))')
            ws.cell(163,c,f'=MAX(0,{col}165+{col}167+{col}171-MAX(0,{col}15-{col}48))')
            ws.cell(160,c,f'=MAX(0,{col}14-{col}47)+{col}45+{col}41-{col}166-{col}164')
            ws.cell(161,c,f'=MAX(0,{col}15-{col}48)+{col}46+{col}42-{col}167-{col}165')
            ws.cell(41,c,f'={col}162*{col}168'); ws.cell(42,c,f'={col}163*{col}169')
            ws.cell(45,c,f'={col}162-{col}41'); ws.cell(46,c,f'={col}163-{col}42')
            ws.cell(36,c,f'={col}164+{col}165'); ws.cell(37,c,f'={col}41+{col}42'); ws.cell(38,c,f'={col}37-{col}36')
            ws.cell(43,c,f'={col}38'); ws.cell(49,c,f'={col}45+{col}46')
            for rr in [51,52,53,54,55]: ws.cell(rr,c,'=0')
            ws.cell(57,c,f'={col}37'); ws.cell(58,c,f'={col}36'); ws.cell(59,c,f'={col}41'); ws.cell(60,c,f'={col}42'); ws.cell(61,c,f'={col}41-{col}164'); ws.cell(62,c,f'={col}42-{col}165')
            ws.cell(64,c,f'={col}45+{col}46'); ws.cell(65,c,f'={col}166+{col}167'); ws.cell(66,c,f'={col}45'); ws.cell(67,c,f'={col}46'); ws.cell(68,c,f'={col}45-{col}166'); ws.cell(69,c,f'={col}46-{col}167')
            for rr in range(71,91): ws.cell(rr,c,'=0')
            ws.cell(93,c,f'={col}160-(MAX(0,{col}14-{col}47)+{col}41+{col}45-{col}164-{col}166)')
            ws.cell(109,c,'=0'); ws.cell(110,c,'=0')
            # Visible % block links directly to Hyp Direct.
            ws.cell(131,c,'%')
            row_metric={134:'Primes Emises',139:'Sinistres payés Per.',140:'Sinistres payés Ant.',141:'Taux commission / primes',143:'Taux REC clôture / primes',146:'Recours Per.',147:'Recours Ant.',149:'Part IBNR Per. / provisions',150:'Part IBNR Ant. / provisions',151:'Charge sinistres Per.',152:'Charge sinistres Ant.'}
            for rr,m in row_metric.items():
                if is_year_first and m in {'Primes Emises','Sinistres payés Per.','Sinistres payés Ant.','Recours Per.','Recours Ant.','Charge sinistres Per.','Charge sinistres Ant.'}:
                    ws.cell(rr,c,'=0')
                else:
                    ws.cell(rr,c,f'={_hformula(hyp_map,p,b,m,"Hyp Direct")}')
            for rr in [135,136,137,138,142,148]: ws.cell(rr,c,'=0')
            if is_year_first:
                ws.cell(144,c,'=0'); ws.cell(145,c,'=0')
            else:
                ws.cell(144,c,f'=IFERROR({col}45/{prev_col}45-1,0)'); ws.cell(145,c,f'=IFERROR({col}46/{prev_col}46-1,0)')
            # Number formats.
            for rr in list(DIRECT_LABELS.keys())+list(calc_labels):
                if rr in range(131,153): ws.cell(rr,c).number_format='0.0%'
                else: ws.cell(rr,c).number_format='#,##0;[Red](#,##0);-'
        # Corporate / Global formulas.
        amount_rows=[r for r in DIRECT_LABELS if r not in range(131,153)] + list(calc_labels)
        for row in amount_rows: _set_amount_totals(ws,start,row)
        for row in range(134,153):
            corp_refs=[f'{get_column_letter(start+BRANCHES.index(b))}{row}' for b in CORPORATE_BRANCHES]
            all_refs=[f'{get_column_letter(start+j)}{row}' for j in range(8)]
            ws.cell(row,start+8,f'=IFERROR(AVERAGE({",".join(corp_refs)}),0)'); ws.cell(row,start+9,f'=IFERROR(AVERAGE({",".join(all_refs)}),0)')
            ws.cell(row,start+8).number_format='0.0%'; ws.cell(row,start+9).number_format='0.0%'
        _style_local_block(ws,start,'direct')
    return periods


def _populate_reass_formula(ws,direct,reass,hyp_map):
    periods=_periods(direct)
    note='V2 formule: Réassurance = taux de cession des primes + taux de récupération des sinistres + commission de réassurance. Toutes les lignes modélisées sont des formules liées à Direct Local.'
    _setup_local_sheet(ws,REASS_LABELS,'Projection Reass Local — V2 formules',note,108)
    first_index_by_year={}
    for i,p in enumerate(periods): first_index_by_year.setdefault(p.year,i)
    for i,p in enumerate(periods):
        start=_reass_start(i); dstart=_direct_start(i); year_first=first_index_by_year[p.year]; jan_period=periods[year_first]
        ws.cell(4,start,'SanlamAllianz LIC Tool'); ws.cell(4,start+4,f'{FR_MONTHS[p.month]} {p.year}')
        for k,(en,fr) in enumerate(zip(EN_BRANCHES,BRANCHES)):
            ws.cell(5,start+k,en); ws.cell(6,start+k,fr)
        ws.cell(6,start+8,'Corporate'); ws.cell(6,start+9,'Global')
        for c in range(start,start+10):
            ws.cell(5,c).font=Font(bold=True,color=WHITE); ws.cell(5,c).fill=PatternFill('solid',fgColor=DARK); ws.cell(6,c).font=Font(bold=True); ws.cell(6,c).fill=PatternFill('solid',fgColor=LIGHT); ws.column_dimensions[get_column_letter(c)].width=15
        for k,b in enumerate(BRANCHES):
            c=start+k; col=get_column_letter(c); dc=get_column_letter(dstart+k)
            cess=_hformula(hyp_map,p,b,'Taux cession primes','Hyp Reass'); rec=_hformula(hyp_map,p,b,'Taux récupération sinistres','Hyp Reass'); recupr=_hformula(hyp_map,p,b,'Taux REC réassurance / primes cédées','Hyp Reass'); comm=_hformula(hyp_map,p,b,'Taux commission réassurance','Hyp Reass')
            annual_cess=_hformula(hyp_map,jan_period,b,'Taux cession primes','Hyp Reass'); annual_rec=_hformula(hyp_map,jan_period,b,'Taux récupération sinistres','Hyp Reass'); annual_recupr=_hformula(hyp_map,jan_period,b,'Taux REC réassurance / primes cédées','Hyp Reass')
            # Premiums and simple fixed PAP/PANE.
            ws.cell(7,c,f"='Direct Local'!{dc}7*{cess}")
            for rr in [8,9,10,11]: ws.cell(rr,c,'=0')
            ws.cell(12,c,f'={col}7-{col}8+{col}9-{col}10+{col}11')
            # Paid recoveries based on Direct paid net of recourse.
            ws.cell(14,c,f"=MAX(0,'Direct Local'!{dc}14-'Direct Local'!{dc}47)*{rec}")
            ws.cell(15,c,f"=MAX(0,'Direct Local'!{dc}15-'Direct Local'!{dc}48)*{rec}")
            ws.cell(16,c,f'={col}14+{col}15')
            ws.cell(18,c,f'={col}7*{comm}')
            # REC Réassurance indépendante de la REC Direct : base = primes cédées.
            # L'ouverture reste fixe dans l'exercice ; la clôture = primes cédées × taux REC Réassurance.
            if i==year_first:
                ws.cell(20,c,f'={col}7*{annual_recupr}')
            else:
                prev_start=_reass_start(i-1); prev_col=get_column_letter(prev_start+k)
                ws.cell(20,c,f'={prev_col}21')
            ws.cell(21,c,f'={col}7*{recupr}')
            ws.cell(22,c,f'={col}21-{col}20')
            ws.cell(24,c,f'=IFERROR({col}20/72%,0)'); ws.cell(25,c,f'=IFERROR({col}21/72%,0)'); ws.cell(26,c,f'={col}25-{col}24')
            ws.cell(30,c,f'={col}25-{col}24'); ws.cell(32,c,'=0'); ws.cell(33,c,'=0'); ws.cell(34,c,'=0')
            # Recoverable IBNR / SAP. Openings fixed at first-period recovery rate of the year.
            ws.cell(36,c,f"='Direct Local'!{dc}36*{annual_rec}")
            ws.cell(40,c,f"='Direct Local'!{dc}41*{rec}"); ws.cell(41,c,f"='Direct Local'!{dc}42*{rec}")
            ws.cell(37,c,f'={col}40+{col}41'); ws.cell(38,c,f'={col}37-{col}36'); ws.cell(42,c,f'={col}38')
            ws.cell(44,c,f"='Direct Local'!{dc}45*{rec}"); ws.cell(45,c,f"='Direct Local'!{dc}46*{rec}"); ws.cell(46,c,f'={col}44+{col}45')
            for rr in [48,49,50,51,52]: ws.cell(rr,c,'=0')
            ws.cell(54,c,f'={col}37'); ws.cell(55,c,f'={col}36'); ws.cell(56,c,f'={col}40'); ws.cell(57,c,f'={col}41'); ws.cell(58,c,f'={col}56'); ws.cell(59,c,f'={col}57-{col}55')
            ws.cell(61,c,f'={col}44+{col}45'); ws.cell(62,c,f"='Direct Local'!{dc}65*{annual_rec}"); ws.cell(63,c,f'={col}44'); ws.cell(64,c,f'={col}45'); ws.cell(65,c,f'={col}63'); ws.cell(66,c,f'={col}64-{col}62')
            for rr in range(68,80): ws.cell(rr,c,'=0')
            ws.cell(81,c,'=0'); ws.cell(82,c,'=0')
            # % block.
            ws.cell(87,c,'% Réassurance')
            mapping={90:'Taux cession primes',95:'Taux récupération sinistres',96:'Taux récupération sinistres',97:'Taux commission réassurance',99:'Taux cession primes',100:'Taux REC réassurance / primes cédées',101:'Taux REC réassurance / primes cédées',102:'Taux récupération sinistres',103:'Taux récupération sinistres',107:'Taux récupération sinistres',108:'Taux récupération sinistres'}
            for rr,m in mapping.items(): ws.cell(rr,c,f'={_hformula(hyp_map,p,b,m,"Hyp Reass")}')
            for rr in [91,92,93,94,98,104,105,106]: ws.cell(rr,c,'=0')
            for rr in REASS_LABELS:
                ws.cell(rr,c).number_format='0.0%' if rr>=87 else '#,##0;[Red](#,##0);-'
        amount_rows=[r for r in REASS_LABELS if r<87]
        for row in amount_rows: _set_amount_totals(ws,start,row)
        for row in range(90,109):
            corp_refs=[f'{get_column_letter(start+BRANCHES.index(b))}{row}' for b in CORPORATE_BRANCHES]
            all_refs=[f'{get_column_letter(start+j)}{row}' for j in range(8)]
            ws.cell(row,start+8,f'=IFERROR(AVERAGE({",".join(corp_refs)}),0)'); ws.cell(row,start+9,f'=IFERROR(AVERAGE({",".join(all_refs)}),0)'); ws.cell(row,start+8).number_format='0.0%'; ws.cell(row,start+9).number_format='0.0%'
        _style_local_block(ws,start,'reass')
    return periods


def _sum_refs(sheet,start,row,members):
    cols=[start+BRANCHES.index(b) for b in members]
    refs=[f"'{sheet}'!{get_column_letter(c)}{row}" for c in cols]
    return '+'.join(refs) if refs else '0'


def _sum_expr(exprs):
    return '+'.join(exprs) if exprs else '0'


def _populate_cpc_formula(ws,direct):
    periods=_periods(direct); ws.sheet_view.showGridLines=False; ws.freeze_panes='D5'; ws.column_dimensions['B'].width=47
    ws['A1']='CONSOLIDATION '; ws['B1']='Local GAAP'; ws['B2']='Projection technique — V2 formules'
    ws['A3']='Note'; ws['B3']='CPC entièrement calculé par formules depuis Direct Local et Reass Local. Frais généraux et produits financiers restent hors moteur.'
    for r,label in CPC_LABELS.items(): ws.cell(r,2,label)
    for r in [4,45,52,71,75,116,124,148]: ws.cell(r,2).font=Font(bold=True,color=WHITE); ws.cell(r,2).fill=PatternFill('solid',fgColor=DARK)
    ws.cell(244,1,' ')
    for i,p in enumerate(periods):
        start=_cpc_start(i); ds=_direct_start(i); rs=_reass_start(i); prev=_cpc_start(i-1) if i>0 else None
        ws.merge_cells(start_row=1,start_column=start,end_row=1,end_column=start+6); ws.cell(1,start,f'{FR_MONTHS[p.month]} {p.year}'); ws.cell(1,start).font=Font(bold=True,size=11); ws.cell(1,start).alignment=Alignment(horizontal='center')
        headers=['CONSOLIDATION ','INCENDIE','AUTO','RD','RC','TRANS','SANTE','VAR N/N-1','VAR ABS','VAR N/Forecast ','VAR %']
        for k,h in enumerate(headers):
            c=ws.cell(2,start+k,h); c.font=Font(bold=True,color=WHITE); c.fill=PatternFill('solid',fgColor=DARK); c.alignment=Alignment(horizontal='center',wrap_text=True); ws.column_dimensions[get_column_letter(start+k)].width=14.5
        group_defs=[('CONSOLIDATION ',BRANCHES)]+list(CPC_GROUPS.items())
        for gi,(_,members) in enumerate(group_defs):
            c=start+gi; col=get_column_letter(c)
            # Gross formulas.
            w=_sum_refs('Direct Local',ds,7,members); uo=_sum_refs('Direct Local',ds,20,members); uc=_sum_refs('Direct Local',ds,21,members)
            paidc=_sum_expr([f"('Direct Local'!{get_column_letter(ds+BRANCHES.index(b))}14-'Direct Local'!{get_column_letter(ds+BRANCHES.index(b))}47)" for b in members])
            paidp=_sum_expr([f"('Direct Local'!{get_column_letter(ds+BRANCHES.index(b))}15-'Direct Local'!{get_column_letter(ds+BRANCHES.index(b))}48)" for b in members])
            provc=_sum_expr([f"('Direct Local'!{get_column_letter(ds+BRANCHES.index(b))}162-'Direct Local'!{get_column_letter(ds+BRANCHES.index(b))}164-'Direct Local'!{get_column_letter(ds+BRANCHES.index(b))}166)" for b in members])
            provp=_sum_expr([f"('Direct Local'!{get_column_letter(ds+BRANCHES.index(b))}163-'Direct Local'!{get_column_letter(ds+BRANCHES.index(b))}165-'Direct Local'!{get_column_letter(ds+BRANCHES.index(b))}167)" for b in members])
            comm=_sum_refs('Direct Local',ds,18,members)
            ws.cell(5,c,f'={w}'); ws.cell(6,c,f'=({uo})-({uc})'); ws.cell(7,c,f'={col}5+{col}6')
            ws.cell(9,c,f'=-({paidc})'); ws.cell(10,c,f'=-({provc})'); ws.cell(11,c,f'={col}9+{col}10')
            ws.cell(12,c,f'=-({paidp})'); ws.cell(13,c,f'=-({provp})'); ws.cell(14,c,f'={col}12+{col}13'); ws.cell(15,c,f'={col}11+{col}14')
            ws.cell(17,c,f'=-({comm})'); ws.cell(18,c,'=0'); ws.cell(19,c,f'={col}17+{col}18')
            for rr in range(21,42): ws.cell(rr,c,'=0')
            ws.cell(43,c,f'={col}7+{col}15+{col}19+{col}41')
            ws.cell(46,c,f'=IFERROR(-{col}11/{col}7,0)'); ws.cell(47,c,f'=IFERROR(-{col}15/{col}7,0)'); ws.cell(48,c,f'=IFERROR(-{col}19/{col}7,0)'); ws.cell(49,c,'=0'); ws.cell(50,c,f'={col}47+{col}48+{col}49')
            # Reinsurance formulas.
            rw=_sum_refs('Reass Local',rs,7,members); ruo=_sum_refs('Reass Local',rs,20,members); ruc=_sum_refs('Reass Local',rs,21,members)
            rpaidc=_sum_refs('Reass Local',rs,14,members); rpaidp=_sum_refs('Reass Local',rs,15,members)
            rprovc=_sum_expr([f"('Reass Local'!{get_column_letter(rs+BRANCHES.index(b))}40+'Reass Local'!{get_column_letter(rs+BRANCHES.index(b))}44)" for b in members])
            rprovp=_sum_expr([f"('Reass Local'!{get_column_letter(rs+BRANCHES.index(b))}41+'Reass Local'!{get_column_letter(rs+BRANCHES.index(b))}45-'Reass Local'!{get_column_letter(rs+BRANCHES.index(b))}36-'Reass Local'!{get_column_letter(rs+BRANCHES.index(b))}62)" for b in members])
            rcomm=_sum_refs('Reass Local',rs,18,members)
            ws.cell(53,c,f'=-({rw})'); ws.cell(54,c,f'=({ruc})-({ruo})'); ws.cell(55,c,f'={col}53+{col}54')
            ws.cell(57,c,f'={rpaidc}'); ws.cell(58,c,f'={rprovc}'); ws.cell(59,c,f'={col}57+{col}58')
            ws.cell(60,c,f'={rpaidp}'); ws.cell(61,c,f'={rprovp}'); ws.cell(62,c,f'={col}60+{col}61'); ws.cell(63,c,f'={col}59+{col}62')
            ws.cell(65,c,f'={rcomm}'); ws.cell(66,c,'=0'); ws.cell(67,c,f'={col}65+{col}66'); ws.cell(69,c,f'={col}55+{col}63+{col}67')
            ws.cell(72,c,f'=IFERROR(-{col}53/{col}5,0)'); ws.cell(73,c,f'=IFERROR({col}63/(-{col}15),0)')
            # Net formulas.
            ws.cell(76,c,f'={col}5+{col}53'); ws.cell(77,c,f'={col}6+{col}54'); ws.cell(78,c,f'={col}7+{col}55')
            ws.cell(80,c,f'={col}9+{col}57'); ws.cell(81,c,f'={col}10+{col}58'); ws.cell(82,c,f'={col}11+{col}59')
            ws.cell(83,c,f'={col}12+{col}60'); ws.cell(84,c,f'={col}13+{col}61'); ws.cell(85,c,f'={col}14+{col}62'); ws.cell(86,c,f'={col}15+{col}63')
            ws.cell(88,c,f'={col}17+{col}65'); ws.cell(89,c,'=0'); ws.cell(90,c,f'={col}88+{col}89')
            for rr in range(92,113): ws.cell(rr,c,'=0')
            ws.cell(114,c,f'={col}78+{col}86+{col}90+{col}112')
            ws.cell(117,c,f'=IFERROR(-{col}82/{col}78,0)'); ws.cell(118,c,f'=IFERROR(-{col}86/{col}78,0)'); ws.cell(119,c,f'=IFERROR(-{col}90/{col}78,0)'); ws.cell(120,c,'=0'); ws.cell(121,c,f'={col}118+{col}119+{col}120')
            for rr in range(124,145): ws.cell(rr,c,'=0')
            ws.cell(135,c,'=0'); ws.cell(143,c,'=0'); ws.cell(144,c,'=0'); ws.cell(146,c,f'={col}114'); ws.cell(148,c,f'={col}114'); ws.cell(149,c,'=0'); ws.cell(150,c,'=0')
            for rr in list(CPC_LABELS.keys()): ws.cell(rr,c).number_format='0.0%' if rr in [46,47,48,49,50,72,73,117,118,119,120,121] else '#,##0;[Red](#,##0);-'
        # Comparison columns: formula-driven vs previous selected period (consolidated amounts).
        if prev is not None:
            curcol=get_column_letter(start); prevcol=get_column_letter(prev)
            for rr in [5,6,7,15,19,43,53,55,63,67,69,76,78,86,90,114,146]:
                ws.cell(rr,start+7,f'=IFERROR(({curcol}{rr}-{prevcol}{rr})/ABS({prevcol}{rr}),0)'); ws.cell(rr,start+8,f'={curcol}{rr}-{prevcol}{rr}')
                ws.cell(rr,start+7).number_format='0.0%'; ws.cell(rr,start+8).number_format='#,##0;[Red](#,##0);-'
        else:
            for rr in [5,6,7,15,19,43,53,55,63,67,69,76,78,86,90,114,146]: ws.cell(rr,start+7,'=0'); ws.cell(rr,start+8,'=0')
        for rr in [5,6,7,15,19,43,53,55,63,67,69,76,78,86,90,114,146]: ws.cell(rr,start+9,'=0'); ws.cell(rr,start+10,'=0')
        # pd.xlsx-inspired but softer CPC styling.
        for cc in range(start,start+11):
            ws.cell(2,cc).fill=PatternFill('solid',fgColor=SOFT_PURPLE); ws.cell(2,cc).font=Font(bold=True,color='17365D')
        for rr in [4,52,75]:
            for cc in range(start,start+7): ws.cell(rr,cc).fill=PatternFill('solid',fgColor=SOFT_PEACH); ws.cell(rr,cc).font=Font(bold=True)
        for rr in [7,11,14,15,19,41,55,59,62,63,67,78,82,85,86,90,112]:
            for cc in range(start,start+7): ws.cell(rr,cc).fill=PatternFill('solid',fgColor=SOFT_BLUE); ws.cell(rr,cc).font=Font(bold=True)
        for rr in [43,69,114,146,148]:
            for cc in range(start,start+7): ws.cell(rr,cc).fill=PatternFill('solid',fgColor=SOFT_GREEN); ws.cell(rr,cc).font=Font(bold=True)
        for rr in [45,71,116]:
            for cc in range(start,start+7): ws.cell(rr,cc).fill=PatternFill('solid',fgColor=PALE); ws.cell(rr,cc).font=Font(bold=True)
        for c in range(start+11,start+27): ws.column_dimensions[get_column_letter(c)].width=2.2
        ws.cell(2,start+25,' ')
    return periods



def _write_ifrs_passage_sheet(ws, ifrs_params=None, ratio_targets_ifrs=None):
    p=pd.DataFrame(ifrs_params).copy() if ifrs_params is not None else pd.DataFrame()
    pmap={str(x.get('Branche')):x for _,x in p.iterrows()} if len(p) else {}
    rt=pd.DataFrame(ratio_targets_ifrs).copy() if ratio_targets_ifrs is not None else pd.DataFrame()
    ws.sheet_view.showGridLines=False; ws.freeze_panes='B5'; ws.column_dimensions['A'].width=42
    ws['A1']='PASSAGE IFRS — AUTOMATIQUE'; ws['A1'].font=Font(bold=True,size=14,color=WHITE); ws['A1'].fill=PatternFill('solid',fgColor=DARK); ws.merge_cells('A1:I1')
    ws['A2']='Aucune saisie IFRS complémentaire : IBNR estimé depuis le Local ; DAC et REC Réassurance IFRS calculés depuis le Local. Les cibles S/P IFRS peuvent recalibrer l’IBNR.'
    ws['A2'].font=Font(italic=True,color='64748B'); ws.merge_cells('A2:I2')
    ws['A4']='Paramètre'
    for i,b in enumerate(BRANCHES,2): ws.cell(4,i,b)
    for c in range(1,10): ws.cell(4,c).fill=PatternFill('solid',fgColor=LIGHT); ws.cell(4,c).font=Font(bold=True,color='17365D'); ws.cell(4,c).alignment=Alignment(horizontal='center',wrap_text=True)
    ws['A5']='Coefficient IBNR IFRS / Local'
    cellmap={b:{} for b in BRANCHES}
    for i,b in enumerate(BRANCHES,2):
        row=pmap.get(b,pd.Series(dtype=object)); v=float(row.get('ibnr_factor',1.0)) if len(row) else 1.0
        ws.cell(5,i,v); ws.cell(5,i).number_format='0.0%'; ws.cell(5,i).font=Font(color='000000',bold=True); ws.column_dimensions[get_column_letter(i)].width=17
        cellmap[b]['ibnr_factor']=ws.cell(5,i).coordinate
    ws['A7']='Règles de calcul'; ws['B7']='IBNR IFRS = IBNR Local × coefficient, sauf recalage nécessaire pour atteindre une cible S/P IFRS. DAC Direct = REC 100% × taux de commission Direct. REC Réassurance IFRS = REC Réassurance Local / 72%. DAC Réassurance = REC 100% × taux de commission de réassurance.'; ws.merge_cells('B7:I8'); ws['B7'].alignment=Alignment(wrap_text=True,vertical='top'); ws['B7'].font=Font(italic=True,color='64748B')

    target_map={}
    if not rt.empty:
        ws['A10']='CIBLES S/P IFRS UTILISÉES'; ws['A10'].font=Font(bold=True,color=WHITE); ws['A10'].fill=PatternFill('solid',fgColor=DARK); ws.merge_cells('A10:I10')
        row=11
        for per in sorted(rt['period'].astype(str).unique()):
            ws.cell(row,1,per); ws.cell(row,1).font=Font(bold=True,color='17365D')
            row+=1
            ws.cell(row,1,'S/P exercice')
            ws.cell(row+1,1,'S/P global')
            for bi,b in enumerate(BRANCHES,2):
                m=rt[(rt['period'].astype(str)==per)&(rt['branch'].astype(str)==b)]
                ex=None if m.empty or pd.isna(m.iloc[-1].get('sp_exercice')) else float(m.iloc[-1].get('sp_exercice'))/100.0
                gl=None if m.empty or pd.isna(m.iloc[-1].get('sp_global')) else float(m.iloc[-1].get('sp_global'))/100.0
                if ex is not None: ws.cell(row,bi,ex)
                if gl is not None: ws.cell(row+1,bi,gl)
                ws.cell(row,bi).number_format='0.0%'; ws.cell(row+1,bi).number_format='0.0%'
                target_map[(per,b,'sp_exercice')]=ws.cell(row,bi).coordinate
                target_map[(per,b,'sp_global')]=ws.cell(row+1,bi).coordinate
            row+=3
    return cellmap,target_map


def _make_ifrs_direct(wb, periods, cells, target_map=None):
    target_map=target_map or {}
    src=wb['Direct Local']; ws=wb.copy_worksheet(src); ws.title='Direct'
    ws['A1']='Projection Direct — IFRS'; ws['A2']='Toutes les lignes pointent vers Direct Local. IBNR, DAC et ratios IFRS sont recalculés automatiquement.'
    for i,p in enumerate(periods):
        start=_direct_start(i); per=str(pd.Period(p,freq='M'))
        for bi,b in enumerate(BRANCHES):
            c=start+bi; col=get_column_letter(c); ref=f"'Direct Local'!{col}"; cm=cells[b]; cf=f"'Passage IFRS'!{cm['ibnr_factor']}"
            for row in [7,8,9,10,11,12,14,15,16,18,20,21,22,24,25,26,32,33,34,45,46,47,48,49,51,52,53,54,55,64,65,66,67,68,69,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,93,109,110,166,167]:
                ws.cell(row,c,f'={ref}{row}')
            # Ouvertures IFRS dérivées automatiquement du Local.
            ws.cell(164,c,f"=MAX(0,'Direct Local'!{col}164*{cf})")
            ws.cell(165,c,f"=MAX(0,'Direct Local'!{col}165*{cf})")
            earned=f'({col}7+{col}20-{col}21)'
            t_ex=target_map.get((per,b,'sp_exercice')); t_gl=target_map.get((per,b,'sp_global'))
            # Clôture IBNR exercice : facteur Local ou résolution de la cible S/P IFRS.
            if t_ex:
                ws.cell(41,c,f"=IF('Passage IFRS'!{t_ex}=\"\",MAX(0,'Direct Local'!{col}41*{cf}),MAX(0,{earned}*'Passage IFRS'!{t_ex}-MAX(0,{col}14-{col}47)-{col}45+{col}164+{col}166))")
            else:
                ws.cell(41,c,f"=MAX(0,'Direct Local'!{col}41*{cf})")
            ws.cell(160,c,f'=MAX(0,{col}14-{col}47)+{col}45+{col}41-{col}166-{col}164')
            if t_gl:
                ws.cell(42,c,f"=IF('Passage IFRS'!{t_gl}=\"\",MAX(0,'Direct Local'!{col}42*{cf}),MAX(0,{earned}*'Passage IFRS'!{t_gl}-{col}160-MAX(0,{col}15-{col}48)-{col}46+{col}165+{col}167))")
            else:
                ws.cell(42,c,f"=MAX(0,'Direct Local'!{col}42*{cf})")
            ws.cell(161,c,f'=MAX(0,{col}15-{col}48)+{col}46+{col}42-{col}167-{col}165')
            ws.cell(36,c,f'={col}164+{col}165'); ws.cell(37,c,f'={col}41+{col}42'); ws.cell(38,c,f'={col}37-{col}36')
            ws.cell(43,c,f'={col}38'); ws.cell(57,c,f'={col}37'); ws.cell(58,c,f'={col}36'); ws.cell(59,c,f'={col}41'); ws.cell(60,c,f'={col}42'); ws.cell(61,c,f'={col}41-{col}164'); ws.cell(62,c,f'={col}42-{col}165')
            # DAC Direct automatique depuis le Local : REC 100% × taux de commission.
            rate=f"IFERROR('Direct Local'!{col}18/'Direct Local'!{col}7,0)"
            ws.cell(28,c,f"='Direct Local'!{col}24*{rate}")
            ws.cell(29,c,f"='Direct Local'!{col}25*{rate}")
            ws.cell(30,c,f'={col}28-{col}29')
        for row in list(DIRECT_LABELS.keys()):
            if row<131: _set_amount_totals(ws,start,row)
    return ws


def _make_ifrs_reass(wb, periods, cells):
    src=wb['Reass Local']; ws=wb.copy_worksheet(src); ws.title='Reass'
    ws['A1']='Projection Réassurance — IFRS'; ws['A2']='REC 100% et DAC calculés automatiquement depuis Reass Local.'
    for i,p in enumerate(periods):
        start=_reass_start(i)
        for bi,b in enumerate(BRANCHES):
            c=start+bi; col=get_column_letter(c); ref=f"'Reass Local'!{col}"
            for row in [7,8,9,10,11,12,14,15,16,18,20,21,22,24,25,26,36,37,38,40,41,42,44,45,46,48,49,50,51,52,54,55,56,57,58,59,61,62,63,64,65,66,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82]:
                ws.cell(row,c,f'={ref}{row}')
            ws.cell(28,c,f"=IFERROR('Reass Local'!{col}20/72%,0)")
            ws.cell(29,c,f"=IFERROR('Reass Local'!{col}21/72%,0)")
            ws.cell(30,c,f'={col}29-{col}28')
            ws.cell(32,c,f'=IFERROR({col}18/{col}7*{col}28,0)')
            ws.cell(33,c,f'=IFERROR({col}18/{col}7*{col}29,0)')
            ws.cell(34,c,f'={col}32-{col}33')
        for row in [r for r in REASS_LABELS if r<87]: _set_amount_totals(ws,start,row)
    return ws


def _copy_cpc_as_ifrs(wb):
    src=wb['CPC SAZ Local']; ws=wb.copy_worksheet(src); ws.title='CPC SAZ'
    ws['A1']='CONSOLIDATION IFRS'; ws['B1']='IFRS 4'
    for row in ws.iter_rows():
        for cell in row:
            v=cell.value
            if isinstance(v,str) and v.startswith('='):
                cell.value=v.replace("'Direct Local'","'Direct'").replace("'Reass Local'","'Reass'")
    return ws

def export_projection(path, inputs: dict, direct, reass, summary, diagnostics, applied_direct=None, applied_reass=None, ifrs_params=None, ratio_targets_ifrs=None):
    direct=pd.DataFrame(direct).copy(); reass=pd.DataFrame(reass).copy()
    wb=Workbook(); wb.remove(wb.active)
    # Force Excel / LibreOffice to recalculate every formula on open.
    try: wb.calculation = CalcProperties(calcMode='auto', fullCalcOnLoad=True, forceFullCalc=True)
    except Exception: pass
    ws=wb.create_sheet('Hyp Direct'); hdm,anchors=_write_hyp_sheet(ws,pd.DataFrame(applied_direct),'Hyp Direct — V2 inputs & formules',direct=direct,kind='direct')
    ws=wb.create_sheet('Hyp Reass'); hrm,_=_write_hyp_sheet(ws,pd.DataFrame(applied_reass),'Hyp Reass — V2 cession / récupération',kind='reass')
    ws=wb.create_sheet('Cibles'); _write_targets_sheet(ws,inputs.get('cibles_direct'),inputs.get('cibles_reass'))
    ws=wb.create_sheet('Direct Local'); _populate_direct_formula(ws,direct,hdm,anchors)
    ws=wb.create_sheet('Reass Local'); _populate_reass_formula(ws,direct,reass,hrm)
    ws=wb.create_sheet('CPC SAZ Local'); periods=_populate_cpc_formula(ws,direct)
    ws=wb.create_sheet('Passage IFRS'); ifrs_cells,ifrs_targets=_write_ifrs_passage_sheet(ws,ifrs_params,ratio_targets_ifrs)
    _make_ifrs_direct(wb,periods,ifrs_cells,ifrs_targets)
    _make_ifrs_reass(wb,periods,ifrs_cells)
    _copy_cpc_as_ifrs(wb)
    wb.save(path)
    return path
