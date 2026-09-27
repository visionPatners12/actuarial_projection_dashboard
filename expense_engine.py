from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple
import numpy as np
import pandas as pd

from prime_engine import BRANCHES, MONTHS, rate_curve

FG_COMPONENTS = [
    "Masse Salariale", "Charges Externes", "Frais Marketing", "Frais de gestion",
    "Frais informatique", "Char. Immeuble", "Frais de conseil", "Frais de contrôle",
    "Assis tech", "Dotations / reprises aux amortissements et provisions", "frs ets",
    "c a r", "log", "imbl", "mat transp", "aut mat", "mat inf",
    "Dotations sur créances intermédiaires", "Impôts et Taxes", "Autres Charges",
]
PF_REVENUES = ["REV IMB", "prdt cession immo", "revenu actions", "revenu obligation", "TRESO & EQUIV"]
PF_CHARGES = ["frais de gestion des placement", "vnc des actifs cedées", "dot déprec autres placmt fin", "amort imble placement"]
RATE_COLS = ["Branche","Mode","Départ (%)","Atterrissage (%)","Marge baisse (pts)","Marge hausse (pts)"]


def _num(v, default=np.nan):
    try:
        if v is None or (isinstance(v,float) and np.isnan(v)) or str(v).strip()=="":
            return default
        x=float(str(v).replace(" ","").replace(",","."))
        return x if np.isfinite(x) else default
    except Exception:
        return default


def blank_component_table(lines: Sequence[str]) -> pd.DataFrame:
    d={"Ligne": list(lines)}
    for b in BRANCHES:
        d[b]=[np.nan]*len(lines)
    return pd.DataFrame(d)


def blank_rate_settings() -> pd.DataFrame:
    return pd.DataFrame([[b,"Montants",np.nan,np.nan,2.0,2.0] for b in BRANCHES], columns=RATE_COLS)


def blank_month_matrix(value=np.nan) -> pd.DataFrame:
    d={"Mois":MONTHS}
    for b in BRANCHES: d[b]=[value]*12
    return pd.DataFrame(d)


def _component_value(df, line: str, branch: str):
    d=pd.DataFrame(df).copy()
    if "Ligne" not in d.columns or branch not in d.columns:
        return np.nan
    m=d[d["Ligne"].astype(str).str.strip()==line]
    if m.empty: return np.nan
    return _num(m.iloc[0][branch], np.nan)


def _linear_cumulative(start, end):
    s=_num(start,np.nan); e=_num(end,np.nan)
    if not np.isfinite(s) and not np.isfinite(e):
        return np.zeros(12,float)
    if not np.isfinite(e): e=s
    if not np.isfinite(s): s=e/12.0
    return np.linspace(s,e,12)


def _monthly_override(df, branch):
    d=pd.DataFrame(df).copy()
    if branch not in d.columns: return np.full(12,np.nan)
    vals=[_num(v,np.nan) for v in d[branch].tolist()[:12]]
    vals += [np.nan]*max(0,12-len(vals))
    return np.asarray(vals[:12],float)


def _setting_row(settings, branch):
    d=pd.DataFrame(settings).copy()
    if "Branche" in d.columns:
        m=d[d["Branche"].astype(str).str.strip()==branch]
        if not m.empty: return m.iloc[0]
    return pd.Series(dtype=object)


def project_expenses(
    earned: pd.DataFrame,
    fg_start: pd.DataFrame,
    fg_end: pd.DataFrame,
    fg_rate_settings: pd.DataFrame,
    fg_rate_manual: pd.DataFrame,
    pf_start: pd.DataFrame,
    pf_end: pd.DataFrame,
    pf_product_manual: pd.DataFrame,
    pf_charge_manual: pd.DataFrame,
    result_before_fg: pd.DataFrame,
):
    """Projette FG et financier en conservant les signes du CPC.

    FG: les composantes sont interpolées linéairement. En mode Montants, elles restent telles quelles.
    En mode taux, le total FG est recalé sur -prime acquise * taux, en préservant la structure relative.
    Produits/charges financiers: interpolation linéaire, avec override mensuel possible du total.
    """
    e=pd.DataFrame(earned).copy(); rb=pd.DataFrame(result_before_fg).copy()
    fg_total=pd.DataFrame(index=range(12),columns=BRANCHES,dtype=float)
    fg_rate=pd.DataFrame(index=range(12),columns=BRANCHES,dtype=float)
    prod=pd.DataFrame(index=range(12),columns=BRANCHES,dtype=float)
    fin_ch=pd.DataFrame(index=range(12),columns=BRANCHES,dtype=float)
    fin_net=pd.DataFrame(index=range(12),columns=BRANCHES,dtype=float)
    after_fg=pd.DataFrame(index=range(12),columns=BRANCHES,dtype=float)
    after_fin=pd.DataFrame(index=range(12),columns=BRANCHES,dtype=float)
    fg_detail: Dict[str,pd.DataFrame]={}
    pf_detail: Dict[str,pd.DataFrame]={}
    diags: List[str]=[]

    for line in FG_COMPONENTS:
        fg_detail[line]=pd.DataFrame(index=range(12),columns=BRANCHES,dtype=float)
    for line in PF_REVENUES+PF_CHARGES:
        pf_detail[line]=pd.DataFrame(index=range(12),columns=BRANCHES,dtype=float)

    for b in BRANCHES:
        base_lines={line:_linear_cumulative(_component_value(fg_start,line,b),_component_value(fg_end,line,b)) for line in FG_COMPONENTS}
        base_total=np.sum(np.vstack(list(base_lines.values())),axis=0) if base_lines else np.zeros(12)
        ev=np.asarray([_num(v,0.0) for v in e[b]],float) if b in e.columns else np.zeros(12)
        row=_setting_row(fg_rate_settings,b)
        mode=str(row.get("Mode","Montants") or "Montants").strip()
        final_total=base_total.copy()
        if not mode.lower().startswith("mont"):
            implied_start=(-100*base_total[0]/ev[0]) if abs(ev[0])>1e-12 else 0.0
            implied_end=(-100*base_total[-1]/ev[-1]) if abs(ev[-1])>1e-12 else implied_start
            start=_num(row.get("Départ (%)"),implied_start); end=_num(row.get("Atterrissage (%)"),implied_end)
            rates,_,_,d=rate_curve(mode,start=start,end=end,fixed=end,manual=_monthly_override(fg_rate_manual,b),
                                    margin_down=max(0,_num(row.get("Marge baisse (pts)"),0)),
                                    margin_up=max(0,_num(row.get("Marge hausse (pts)"),0)))
            diags += [f"{b} · FG : {x}" for x in d]
            target=-ev*rates/100.0
            for i in range(12):
                if abs(base_total[i])>1e-12:
                    scale=target[i]/base_total[i]
                    for line in FG_COMPONENTS: base_lines[line][i]*=scale
                elif abs(target[i])>1e-9:
                    diags.append(f"{b} · {MONTHS[i]} : taux FG demandé mais base FG nulle")
            final_total=np.sum(np.vstack(list(base_lines.values())),axis=0)
        else:
            manual=_monthly_override(fg_rate_manual,b)
            # En mode Montants, une valeur manuelle de taux peut ponctuellement moduler le mois.
            for i,v in enumerate(manual):
                if np.isfinite(v) and abs(ev[i])>1e-12:
                    target=-ev[i]*v/100.0
                    if abs(base_total[i])>1e-12:
                        scale=target/base_total[i]
                        for line in FG_COMPONENTS: base_lines[line][i]*=scale
                    final_total[i]=target

        for line,arr in base_lines.items(): fg_detail[line][b]=arr
        fg_total[b]=final_total
        fg_rate[b]=np.divide(-final_total,ev,out=np.zeros(12),where=np.abs(ev)>1e-12)*100.0

        # Financial revenues / charges
        rev_lines={line:_linear_cumulative(_component_value(pf_start,line,b),_component_value(pf_end,line,b)) for line in PF_REVENUES}
        ch_lines={line:_linear_cumulative(_component_value(pf_start,line,b),_component_value(pf_end,line,b)) for line in PF_CHARGES}
        rev_total=np.sum(np.vstack(list(rev_lines.values())),axis=0) if rev_lines else np.zeros(12)
        ch_total=np.sum(np.vstack(list(ch_lines.values())),axis=0) if ch_lines else np.zeros(12)
        rev_man=_monthly_override(pf_product_manual,b); ch_man=_monthly_override(pf_charge_manual,b)
        for i,v in enumerate(rev_man):
            if np.isfinite(v):
                if abs(rev_total[i])>1e-12:
                    scale=v/rev_total[i]
                    for line in PF_REVENUES: rev_lines[line][i]*=scale
                rev_total[i]=v
        for i,v in enumerate(ch_man):
            if np.isfinite(v):
                if abs(ch_total[i])>1e-12:
                    scale=v/ch_total[i]
                    for line in PF_CHARGES: ch_lines[line][i]*=scale
                ch_total[i]=v
        for line,arr in rev_lines.items(): pf_detail[line][b]=arr
        for line,arr in ch_lines.items(): pf_detail[line][b]=arr
        prod[b]=rev_total; fin_ch[b]=ch_total; fin_net[b]=rev_total-ch_total
        before=np.asarray([_num(v,0.0) for v in rb[b]],float) if b in rb.columns else np.zeros(12)
        after_fg[b]=before+final_total
        after_fin[b]=after_fg[b]+(rev_total-ch_total)

    return {
        "fg_total":fg_total,"fg_rate":fg_rate,"fg_detail":fg_detail,
        "financial_products":prod,"financial_charges":fin_ch,"financial_net":fin_net,"financial_detail":pf_detail,
        "result_after_fg":after_fg,"result_after_financial":after_fin,
        "diagnostics":diags,
    }


def portfolio_expense_metrics(earned, result_before_fg, projected):
    e=pd.DataFrame(earned); rb=pd.DataFrame(result_before_fg)
    rows=[]
    for i,m in enumerate(MONTHS):
        ep=sum(_num(e.loc[i,b],0.0) for b in BRANCHES)
        fgp=sum(_num(projected["fg_total"].loc[i,b],0.0) for b in BRANCHES)
        fp=sum(_num(projected["financial_products"].loc[i,b],0.0) for b in BRANCHES)
        fc=sum(_num(projected["financial_charges"].loc[i,b],0.0) for b in BRANCHES)
        r0=sum(_num(rb.loc[i,b],0.0) for b in BRANCHES)
        r1=sum(_num(projected["result_after_fg"].loc[i,b],0.0) for b in BRANCHES)
        r2=sum(_num(projected["result_after_financial"].loc[i,b],0.0) for b in BRANCHES)
        rows.append({
            "Mois":m,"Prime acquise nette":ep,
            "Frais généraux":fgp,"Taux FG portefeuille (%)":(-100*fgp/ep if abs(ep)>1e-12 else np.nan),
            "Résultat technique avant FG":r0,"Résultat technique après FG":r1,
            "Produits financiers":fp,"Charges financières":fc,"Résultat financier net":fp-fc,
            "Résultat après financier":r2,
        })
    return pd.DataFrame(rows)
