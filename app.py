from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple

import gradio as gr
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from openpyxl import load_workbook

from prime_engine import BRANCHES, MONTHS, project_branch
from claims_engine import (
    SP_SETTING_COLS, blank_sp_settings, blank_portfolio_manual,
    build_portfolio_target, optimize_sp_matrix, calculate_claims_and_result, portfolio_metrics,
)
from expense_engine import (
    FG_COMPONENTS, PF_REVENUES, PF_CHARGES, RATE_COLS as FG_RATE_COLS,
    blank_component_table, blank_rate_settings as blank_fg_rate_settings,
    project_expenses, portfolio_expense_metrics,
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "hypotheses_projection_v5.xlsx"

THEME = gr.themes.Soft(primary_hue="emerald", neutral_hue="slate", radius_size="lg")
CSS = """
:root{--navy:#17365D;--green:#0C7A63;--green-soft:#EEF7F4;--bg:#F5F7FA;--line:#DCE4EA;--text:#233545;--muted:#66788A}
.gradio-container{max-width:1680px!important;margin:0 auto;background:var(--bg)!important;color:var(--text)}
#hero{background:#fff;border:1px solid var(--line);border-left:5px solid var(--green);border-radius:16px;padding:18px 22px;margin:12px 0 10px;box-shadow:0 2px 10px rgba(23,54,93,.035)}
#hero h1{font-size:25px;margin:0 0 4px;color:var(--navy);font-weight:750}#hero p{margin:0;color:var(--muted);font-size:13px}
#prime-toolbar{background:#fff;border:1px solid var(--line);border-radius:14px;padding:8px 10px;position:sticky;top:6px;z-index:30;box-shadow:0 4px 16px rgba(23,54,93,.06)}
#persistent-kpis{position:sticky;top:82px;z-index:25;background:rgba(245,247,250,.96);backdrop-filter:blur(8px);padding:7px 0 9px}
.kpi,.sp-kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:10px 12px;min-height:68px;box-shadow:0 1px 4px rgba(23,54,93,.025)}
.kpi span,.sp-kpi span{font-size:11px;color:var(--muted);font-weight:650;text-transform:uppercase;letter-spacing:.025em}.kpi b,.sp-kpi b{font-size:18px;color:var(--navy);font-weight:750}
.card{background:#fff!important;border:1px solid var(--line)!important;border-radius:14px!important;padding:10px!important;box-shadow:none!important}
.section-title h3{color:var(--navy)!important;margin:0 0 3px!important;font-size:18px!important}.muted{font-size:12.5px;color:var(--muted);margin-top:0!important}.flow-note{font-size:12px;color:#5B6F82;margin:4px 0 8px}
.workspace{background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px 14px;box-shadow:0 2px 10px rgba(23,54,93,.035)}
.context-legend{font-size:11px;color:var(--muted);padding:2px 4px 8px}.context-legend .badge{display:inline-block;padding:3px 7px;border-radius:999px;margin-right:5px;border:1px solid var(--line);background:#fff}.context-legend .auto{border-color:#BFD9D2}.context-legend .manual{border-color:#E4C978}.context-legend .lock{border-color:#B7C0CB}
.matrix table,.rate-settings table,.prime-result table{font-size:11.5px!important}.prime-editor table,.sp-editor table{font-size:12.5px!important}.matrix th,.matrix td,.prime-result th,.prime-result td{white-space:nowrap!important}.prime-editor td,.prime-editor th,.sp-editor td,.sp-editor th{padding:7px 9px!important}
.prime-editor,.sp-editor{border:1px solid #D4DEE6!important;border-radius:12px!important;overflow:hidden!important}.prime-editor input,.sp-editor input{background:#FFFDF3!important}
button.primary{font-weight:720!important}.gr-button-secondary{border-color:#CAD5DE!important}
.compact-grid{max-height:540px;overflow:auto}.decision-note{border-left:3px solid var(--green);background:var(--green-soft);padding:8px 10px;border-radius:8px;font-size:12px;color:#385B55}
footer{display:none!important}
"""

BRANCH_COLS = BRANCHES
MONTH_GRID_COLS = ["Mois"] + BRANCHES
RATE_SETTING_COLS = ["Branche", "Mode", "Départ (%)", "Atterrissage (%)", "Marge baisse (pts)", "Marge hausse (pts)"]
ANCHOR_COLS = [
    "Branche",
    "Départ Direct (facultatif)", "Atterrissage Direct",
    "Départ Réassurance (facultatif)", "Atterrissage Réassurance",
    "REC ouverture Direct CIMA 72%",
    "REC ouverture Réass Local CIMA",
    "REC ouverture Réass IFRS 100%",
]

COMMISSION_ANCHOR_COLS = [
    "Branche",
    "Commission Direct départ", "Commission Direct atterrissage",
    "Commission Réass départ", "Commission Réass atterrissage",
    "DAC Ouv Direct IFRS", "DAC Clo Direct IFRS",
    "REC Ouv prorata Direct IFRS", "REC Clo prorata Direct IFRS",
    "DAC Ouv Réass IFRS", "DAC Clo Réass IFRS",
    "REC Ouv 100% Réass IFRS", "REC Clo 100% Réass IFRS",
]


def blank_month_matrix(value=np.nan) -> pd.DataFrame:
    d = {"Mois": MONTHS}
    for b in BRANCHES:
        d[b] = [value] * 12
    return pd.DataFrame(d)


def blank_history() -> pd.DataFrame:
    return blank_month_matrix(np.nan)


def blank_anchors() -> pd.DataFrame:
    d = {c: [] for c in ANCHOR_COLS}
    for b in BRANCHES:
        d["Branche"].append(b)
        for c in ANCHOR_COLS[1:]:
            d[c].append(np.nan)
    return pd.DataFrame(d)


def blank_commission_anchors() -> pd.DataFrame:
    d = {c: [] for c in COMMISSION_ANCHOR_COLS}
    for b in BRANCHES:
        d["Branche"].append(b)
        for c in COMMISSION_ANCHOR_COLS[1:]:
            d[c].append(np.nan)
    return pd.DataFrame(d)


def default_rate_settings(kind: str) -> pd.DataFrame:
    rows = []
    default_mode = "Fixe" if kind in {"commission", "dac"} else "Linéaire"
    for b in BRANCHES:
        rows.append([b, default_mode, np.nan, np.nan, 2.0, 2.0])
    return pd.DataFrame(rows, columns=RATE_SETTING_COLS)


def _num(v, default=np.nan):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
            return default
        x = float(str(v).replace(" ", "").replace(",", "."))
        return x if np.isfinite(x) else default
    except Exception:
        return default


def _matrix_col(df, branch: str) -> np.ndarray:
    d = pd.DataFrame(df).copy()
    if branch not in d.columns:
        return np.full(12, np.nan)
    vals = [_num(v) for v in d[branch].tolist()[:12]]
    if len(vals) < 12:
        vals += [np.nan] * (12 - len(vals))
    return np.asarray(vals, dtype=float)


def _anchor_row(df, branch: str) -> pd.Series:
    d = pd.DataFrame(df).copy()
    if "Branche" in d.columns:
        m = d[d["Branche"].astype(str).str.strip() == branch]
        if not m.empty:
            return m.iloc[0]
    return pd.Series(dtype=object)


def _setting_row(df, branch: str) -> pd.Series:
    d = pd.DataFrame(df).copy()
    if "Branche" in d.columns:
        m = d[d["Branche"].astype(str).str.strip() == branch]
        if not m.empty:
            return m.iloc[0]
    return pd.Series(dtype=object)


def _rate_config(settings, historical, manual, branch: str, implied_start=None, implied_end=None) -> Dict:
    r = _setting_row(settings, branch)
    mode = str(r.get("Mode", "Linéaire") or "Linéaire")
    start = _num(r.get("Départ (%)"))
    end = _num(r.get("Atterrissage (%)"))
    if implied_start is not None and not np.isfinite(start):
        start = float(implied_start)
    if implied_end is not None and not np.isfinite(end):
        end = float(implied_end)
    fixed = end
    return {
        "mode": mode,
        "fixed": fixed,
        "start": start,
        "end": end,
        "historical": _matrix_col(historical, branch),
        "manual": _matrix_col(manual, branch),
        "margin_down": max(0.0, _num(r.get("Marge baisse (pts)"), 0.0)),
        "margin_up": max(0.0, _num(r.get("Marge hausse (pts)"), 0.0)),
    }


def _month_matrix_from_results(results: Dict[str, pd.DataFrame], column: str) -> pd.DataFrame:
    out = {"Mois": MONTHS}
    for b in BRANCHES:
        t = results[b]
        out[b] = t[column].tolist() if column in t.columns else [np.nan] * 12
    return pd.DataFrame(out)


def _fmt_currency(v):
    if v is None or not np.isfinite(_num(v)):
        return "—"
    x = _num(v, 0.0)
    ax = abs(x)
    if ax >= 1e9:
        return f"{x/1e9:,.2f} Md".replace(",", " ")
    if ax >= 1e6:
        return f"{x/1e6:,.1f} M".replace(",", " ")
    return f"{x:,.0f}".replace(",", " ")


def _summary_html(results: Dict[str, pd.DataFrame], view: str) -> str:
    gross = sum(float(results[b]["Prime brute"].iloc[-1]) for b in BRANCHES)
    ceded = sum(float(results[b]["Prime réassurance"].iloc[-1]) for b in BRANCHES)
    net = gross - ceded
    earned_col = "Prime acquise nette IFRS" if view == "IFRS" else "Prime acquise nette Local"
    earned = sum(float(results[b][earned_col].iloc[-1]) for b in BRANCHES)
    rate = 100 * ceded / gross if abs(gross) > 1e-12 else 0.0
    return f"""
    <div style='display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:10px'>
      <div class='kpi'><span>Prime brute</span><br><b>{_fmt_currency(gross)}</b></div>
      <div class='kpi'><span>Prime réassurance</span><br><b>{_fmt_currency(ceded)}</b></div>
      <div class='kpi'><span>Prime nette</span><br><b>{_fmt_currency(net)}</b></div>
      <div class='kpi'><span>Taux de cession</span><br><b>{rate:.1f}%</b></div>
      <div class='kpi'><span>Prime acquise nette {view}</span><br><b>{_fmt_currency(earned)}</b></div>
    </div>"""


def _branch_kpi_html(results: Dict[str, pd.DataFrame], anchors, branch: str, view: str) -> str:
    b = branch if branch in BRANCHES else BRANCHES[0]
    t = results[b]
    ar = _anchor_row(anchors, b)
    gross_target = _num(ar.get("Atterrissage Direct"), np.nan)
    reass_target = _num(ar.get("Atterrissage Réassurance"), np.nan)
    earned_col = "Prime acquise nette IFRS" if view == "IFRS" else "Prime acquise nette Local"
    cession_dec = float(t["Taux cession (%)"].iloc[-1])
    gross_dec = float(t["Prime brute"].iloc[-1])
    reass_dec = float(t["Prime réassurance"].iloc[-1])
    earned_dec = float(t[earned_col].iloc[-1])
    target_g = _fmt_currency(gross_target) if np.isfinite(gross_target) else "—"
    target_r = _fmt_currency(reass_target) if np.isfinite(reass_target) else "—"
    return f"""
    <div style='display:grid;grid-template-columns:repeat(6,minmax(130px,1fr));gap:8px'>
      <div class='kpi'><span>Branche</span><br><b>{b}</b></div>
      <div class='kpi'><span>Cible Direct</span><br><b>{target_g}</b></div>
      <div class='kpi'><span>Projection Direct</span><br><b>{_fmt_currency(gross_dec)}</b></div>
      <div class='kpi'><span>Cible Réass</span><br><b>{target_r}</b></div>
      <div class='kpi'><span>Cession Déc.</span><br><b>{cession_dec:.2f}%</b></div>
      <div class='kpi'><span>Prime acquise nette {view}</span><br><b>{_fmt_currency(earned_dec)}</b></div>
    </div>"""


def _branch_editor_table(results: Dict[str, pd.DataFrame], branch: str, view: str) -> pd.DataFrame:
    b = branch if branch in BRANCHES else BRANCHES[0]
    t = results[b]
    reass_rate_col = "Taux variation REC Réass IFRS (%)" if view == "IFRS" else "Taux variation REC Réass Local (%)"
    return pd.DataFrame({
        "Mois": MONTHS,
        "Prime brute": t["Prime brute"].to_numpy(float),
        "Taux cession (%)": t["Taux cession (%)"].to_numpy(float),
        "Taux REC Direct (%)": t["Taux variation REC Direct (%)"].to_numpy(float),
        "Taux REC Réass (%)": t[reass_rate_col].to_numpy(float),
    })


def _branch_result_table(results: Dict[str, pd.DataFrame], branch: str, view: str) -> pd.DataFrame:
    b = branch if branch in BRANCHES else BRANCHES[0]
    t = results[b]
    if view == "IFRS":
        d_earned = "Prime acquise Direct IFRS"
        r_earned = "Prime acquise Réass IFRS"
        n_earned = "Prime acquise nette IFRS"
    else:
        d_earned = "Prime acquise Direct Local"
        r_earned = "Prime acquise Réass Local"
        n_earned = "Prime acquise nette Local"
    return pd.DataFrame({
        "Mois": MONTHS,
        "Prime Réassurance": t["Prime réassurance"].to_numpy(float),
        "Prime nette": t["Prime nette"].to_numpy(float),
        "Prime acquise Direct": t[d_earned].to_numpy(float),
        "Prime acquise Réass": t[r_earned].to_numpy(float),
        "Prime acquise nette": t[n_earned].to_numpy(float),
    })


def _ratio_pct(num, den):
    n = _num(num, np.nan)
    d = _num(den, np.nan)
    if not np.isfinite(n) or not np.isfinite(d) or abs(d) <= 1e-12:
        return np.nan
    return 100.0 * n / d


def _commission_summary_html(results: Dict[str, pd.DataFrame], view: str) -> str:
    dcomm = sum(float(results[b]["Commission Direct"].iloc[-1]) for b in BRANCHES)
    rcomm = sum(float(results[b]["Commission Réassurance"].iloc[-1]) for b in BRANCHES)
    if view == "IFRS":
        net_comm = sum(float(results[b]["Commission nette CPC IFRS"].iloc[-1]) for b in BRANCHES)
        net_earned = sum(float(results[b]["Prime acquise nette IFRS"].iloc[-1]) for b in BRANCHES)
        var_dac = sum(float(results[b]["Variation DAC Direct IFRS"].iloc[-1]) for b in BRANCHES)
    else:
        net_comm = sum(float(results[b]["Commission nette CPC Local"].iloc[-1]) for b in BRANCHES)
        net_earned = sum(float(results[b]["Prime acquise nette Local"].iloc[-1]) for b in BRANCHES)
        var_dac = 0.0
    cpc_rate = 100.0 * net_comm / net_earned if abs(net_earned) > 1e-12 else np.nan
    rate_txt = "—" if not np.isfinite(cpc_rate) else f"{cpc_rate:.2f}%"
    return f"""
    <div style='display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:10px'>
      <div class='kpi'><span>Commission Direct</span><br><b>{_fmt_currency(dcomm)}</b></div>
      <div class='kpi'><span>Commission Réassurance</span><br><b>{_fmt_currency(rcomm)}</b></div>
      <div class='kpi'><span>Variation DAC Direct</span><br><b>{_fmt_currency(var_dac) if view=='IFRS' else '—'}</b></div>
      <div class='kpi'><span>Commission nette CPC</span><br><b>{_fmt_currency(net_comm)}</b></div>
      <div class='kpi'><span>Taux commission CPC · {view}</span><br><b>{rate_txt}</b></div>
    </div>"""



def _commission_branch_table(results: Dict[str, pd.DataFrame], branch: str, view: str) -> pd.DataFrame:
    b = branch if branch in BRANCHES else BRANCHES[0]
    t = results[b]
    data = {
        "Mois": MONTHS,
        "Taux commission Direct (%)": t["Taux commission Direct (%)"].to_numpy(float),
        "Commission Direct": t["Commission Direct"].to_numpy(float),
        "Taux récupération Réass (%)": t["Taux récupération commission Réassurance (%)"].to_numpy(float),
        "Commission Réassurance": t["Commission Réassurance"].to_numpy(float),
        "Taux commission CPC (%)": t["Taux commission CPC IFRS (%)" if view == "IFRS" else "Taux commission CPC Local (%)"].to_numpy(float),
    }
    if view == "IFRS":
        data["Taux DAC Direct (%)"] = t["Taux DAC Direct IFRS (%)"].to_numpy(float)
        data["Variation DAC Direct"] = t["Variation DAC Direct IFRS"].to_numpy(float)
        data["Taux DAC Réass (%)"] = t["Taux DAC Réassurance IFRS (%)"].to_numpy(float)
        data["Variation DAC Réass"] = t["Variation DAC Réassurance IFRS"].to_numpy(float)
    return pd.DataFrame(data)

def run_projection(
    hist_n3, hist_n2, hist_n1, anchors,
    gross_manual,
    cession_settings, cession_hist, cession_manual,
    rec_direct_settings, rec_direct_hist, rec_direct_manual,
    rec_reass_local_settings, rec_reass_local_hist, rec_reass_local_manual,
    rec_reass_ifrs_settings, rec_reass_ifrs_hist, rec_reass_ifrs_manual,
    view, selected_branch,
    commission_anchors=None,
    direct_commission_settings=None, direct_commission_manual=None,
    reass_commission_settings=None, reass_commission_manual=None,
    direct_dac_settings=None, direct_dac_manual=None,
    reass_dac_settings=None, reass_dac_manual=None,
):
    histories = [pd.DataFrame(hist_n3), pd.DataFrame(hist_n2), pd.DataFrame(hist_n1)]
    results: Dict[str, pd.DataFrame] = {}
    diags: List[str] = []
    empty_rates = blank_month_matrix()
    if commission_anchors is None:
        commission_anchors = blank_commission_anchors()
    if direct_commission_settings is None: direct_commission_settings = default_rate_settings("commission")
    if reass_commission_settings is None: reass_commission_settings = default_rate_settings("commission")
    if direct_dac_settings is None: direct_dac_settings = default_rate_settings("dac")
    if reass_dac_settings is None: reass_dac_settings = default_rate_settings("dac")
    if direct_commission_manual is None: direct_commission_manual = blank_month_matrix()
    if reass_commission_manual is None: reass_commission_manual = blank_month_matrix()
    if direct_dac_manual is None: direct_dac_manual = blank_month_matrix()
    if reass_dac_manual is None: reass_dac_manual = blank_month_matrix()

    for b in BRANCHES:
        h = []
        for hd in histories:
            a = _matrix_col(hd, b)
            if np.isfinite(a).sum() >= 2:
                h.append(a)
        ar = _anchor_row(anchors, b)
        car = _anchor_row(commission_anchors, b)
        gross_landing = _num(ar.get("Atterrissage Direct"), np.nan)
        reass_landing = _num(ar.get("Atterrissage Réassurance"), np.nan)
        if not np.isfinite(gross_landing):
            gross_landing = np.nan
            for hh in reversed(h):
                if np.isfinite(hh[-1]):
                    gross_landing = hh[-1]
                    break
            if not np.isfinite(gross_landing):
                gross_landing = 0.0
        gross_departure = _num(ar.get("Départ Direct (facultatif)"), np.nan)
        reass_departure = _num(ar.get("Départ Réassurance (facultatif)"), np.nan)
        if not np.isfinite(gross_departure):
            gross_departure = None
        if not np.isfinite(reass_departure):
            reass_departure = None

        anchors_map = {}
        manual_g = _matrix_col(gross_manual, b)
        for i, v in enumerate(manual_g):
            if np.isfinite(v):
                anchors_map[i] = float(v)

        implied = 100 * reass_landing / gross_landing if np.isfinite(reass_landing) and gross_landing else 0.0
        cconf = _rate_config(cession_settings, cession_hist, cession_manual, b, implied_end=implied)
        rdconf = _rate_config(rec_direct_settings, rec_direct_hist, rec_direct_manual, b)
        rlconf = _rate_config(rec_reass_local_settings, rec_reass_local_hist, rec_reass_local_manual, b)
        riconf = _rate_config(rec_reass_ifrs_settings, rec_reass_ifrs_hist, rec_reass_ifrs_manual, b)

        dcomm_start = _ratio_pct(car.get("Commission Direct départ"), gross_departure)
        dcomm_end = _ratio_pct(car.get("Commission Direct atterrissage"), gross_landing)
        # La Réassurance dépend de la commission Direct : le paramètre piloté est
        # le taux de récupération de commission Réassurance.
        rcomm_start = _ratio_pct(car.get("Commission Réass départ"), car.get("Commission Direct départ"))
        rcomm_end = _ratio_pct(car.get("Commission Réass atterrissage"), car.get("Commission Direct atterrissage"))
        # Taux effectif sur prime cédée uniquement pour la logique DAC / contrôle.
        rcomm_effective_start = _ratio_pct(car.get("Commission Réass départ"), reass_departure)
        rcomm_effective_end = _ratio_pct(car.get("Commission Réass atterrissage"), reass_landing)
        ddac_start = _ratio_pct(car.get("DAC Ouv Direct IFRS"), car.get("REC Ouv prorata Direct IFRS"))
        ddac_end = _ratio_pct(car.get("DAC Clo Direct IFRS"), car.get("REC Clo prorata Direct IFRS"))
        rdac_start = _ratio_pct(car.get("DAC Ouv Réass IFRS"), car.get("REC Ouv 100% Réass IFRS"))
        rdac_end = _ratio_pct(car.get("DAC Clo Réass IFRS"), car.get("REC Clo 100% Réass IFRS"))
        # Le DAC Réassurance reste fondé sur le taux de commission effectif sur prime cédée.
        if not np.isfinite(rdac_start): rdac_start = rcomm_effective_start
        if not np.isfinite(rdac_end): rdac_end = rcomm_effective_end

        dcconf = _rate_config(direct_commission_settings, empty_rates, direct_commission_manual, b,
                              implied_start=dcomm_start if np.isfinite(dcomm_start) else None,
                              implied_end=dcomm_end if np.isfinite(dcomm_end) else None)
        rcconf = _rate_config(reass_commission_settings, empty_rates, reass_commission_manual, b,
                              implied_start=rcomm_start if np.isfinite(rcomm_start) else None,
                              implied_end=rcomm_end if np.isfinite(rcomm_end) else None)
        ddconf = _rate_config(direct_dac_settings, empty_rates, direct_dac_manual, b,
                              implied_start=ddac_start if np.isfinite(ddac_start) else None,
                              implied_end=ddac_end if np.isfinite(ddac_end) else None)
        rdcconf = _rate_config(reass_dac_settings, empty_rates, reass_dac_manual, b,
                               implied_start=rdac_start if np.isfinite(rdac_start) else None,
                               implied_end=rdac_end if np.isfinite(rdac_end) else None)

        res = project_branch(
            histories_gross=h,
            gross_landing=float(gross_landing),
            reass_landing=None if not np.isfinite(reass_landing) else float(reass_landing),
            gross_departure=gross_departure,
            gross_manual_anchors=anchors_map,
            cession_config=cconf,
            rec_direct_config=rdconf,
            rec_reass_local_config=rlconf,
            rec_reass_ifrs_config=riconf,
            rec_open_direct_cima72=_num(ar.get("REC ouverture Direct CIMA 72%"), 0.0),
            rec_open_reass_cima72=_num(ar.get("REC ouverture Réass Local CIMA"), 0.0),
            rec_open_reass_ifrs100=_num(ar.get("REC ouverture Réass IFRS 100%"), 0.0),
            direct_commission_config=dcconf,
            reass_commission_config=rcconf,
            direct_dac_config=ddconf,
            reass_dac_config=rdcconf,
            dac_open_direct_ifrs=_num(car.get("DAC Ouv Direct IFRS"), np.nan),
            dac_open_reass_ifrs=_num(car.get("DAC Ouv Réass IFRS"), np.nan),
        )
        results[b] = res.table
        for x in res.diagnostics["Diagnostic"].tolist():
            if x != "Aucune incohérence détectée":
                diags.append(f"{b} — {x}")

    gross = _month_matrix_from_results(results, "Prime brute")
    cession = _month_matrix_from_results(results, "Taux cession (%)")
    ceded = _month_matrix_from_results(results, "Prime réassurance")
    net = _month_matrix_from_results(results, "Prime nette")

    if view == "IFRS":
        direct_var = _month_matrix_from_results(results, "Variation REC Direct prorata")
        direct_close = _month_matrix_from_results(results, "REC clôture Direct prorata")
        direct_earned = _month_matrix_from_results(results, "Prime acquise Direct IFRS")
        reass_rate = _month_matrix_from_results(results, "Taux variation REC Réass IFRS (%)")
        reass_var = _month_matrix_from_results(results, "Variation REC Réass IFRS 100%")
        reass_close = _month_matrix_from_results(results, "REC clôture Réass IFRS 100%")
        reass_earned = _month_matrix_from_results(results, "Prime acquise Réass IFRS")
        net_earned = _month_matrix_from_results(results, "Prime acquise nette IFRS")
        cpc_comm_rate = _month_matrix_from_results(results, "Taux commission CPC IFRS (%)")
        rec_label = "REC Réassurance IFRS 100%"
    else:
        direct_var = _month_matrix_from_results(results, "Variation REC Direct CIMA 72%")
        direct_close = _month_matrix_from_results(results, "REC clôture Direct CIMA 72%")
        direct_earned = _month_matrix_from_results(results, "Prime acquise Direct Local")
        reass_rate = _month_matrix_from_results(results, "Taux variation REC Réass Local (%)")
        reass_var = _month_matrix_from_results(results, "Variation REC Réass Local")
        reass_close = _month_matrix_from_results(results, "REC clôture Réass Local")
        reass_earned = _month_matrix_from_results(results, "Prime acquise Réass Local")
        net_earned = _month_matrix_from_results(results, "Prime acquise nette Local")
        cpc_comm_rate = _month_matrix_from_results(results, "Taux commission CPC Local (%)")
        rec_label = "REC Réassurance Local CIMA"

    rd_rate = _month_matrix_from_results(results, "Taux variation REC Direct (%)")

    landing_rows = []
    commission_landing_rows = []
    for bb in BRANCHES:
        ar = _anchor_row(anchors, bb)
        car = _anchor_row(commission_anchors, bb)
        gd = _num(ar.get("Atterrissage Direct"), np.nan)
        rr = _num(ar.get("Atterrissage Réassurance"), np.nan)
        implied = 100.0 * rr / gd if np.isfinite(gd) and abs(gd) > 1e-12 and np.isfinite(rr) else np.nan
        applied = float(results[bb]["Taux cession (%)"].iloc[-1])
        ceded_dec = float(results[bb]["Prime réassurance"].iloc[-1])
        gap = ceded_dec - rr if np.isfinite(rr) else np.nan
        landing_rows.append({
            "Branche": bb,
            "Atterrissage Direct": gd,
            "Atterrissage Réassurance": rr,
            "Taux cession implicite (%)": implied,
            "Taux Décembre appliqué (%)": applied,
            "Écart Réassurance": gap,
        })
        commission_landing_rows.append({
            "Branche": bb,
            "Taux Direct départ (%)": _ratio_pct(car.get("Commission Direct départ"), ar.get("Départ Direct (facultatif)")),
            "Taux Direct atterrissage (%)": _ratio_pct(car.get("Commission Direct atterrissage"), gd),
            "Taux récupération Réass départ (%)": _ratio_pct(car.get("Commission Réass départ"), car.get("Commission Direct départ")),
            "Taux récupération Réass atterrissage (%)": _ratio_pct(car.get("Commission Réass atterrissage"), car.get("Commission Direct atterrissage")),
            "Taux commission Réass effectif atterrissage (%)": _ratio_pct(car.get("Commission Réass atterrissage"), rr),
            "Taux DAC Direct atterrissage (%)": _ratio_pct(car.get("DAC Clo Direct IFRS"), car.get("REC Clo prorata Direct IFRS")),
            "Taux DAC Réass atterrissage (%)": _ratio_pct(car.get("DAC Clo Réass IFRS"), car.get("REC Clo 100% Réass IFRS")),
            f"Taux CPC Décembre {view} (%)": float(results[bb]["Taux commission CPC IFRS (%)" if view=="IFRS" else "Taux commission CPC Local (%)"].iloc[-1]),
        })
    landing_summary = pd.DataFrame(landing_rows)
    commission_landing_summary = pd.DataFrame(commission_landing_rows)

    b = selected_branch if selected_branch in BRANCHES else BRANCHES[0]
    fig = go.Figure()
    hist_names = ["N-3", "N-2", "N-1"]
    for name, hd in zip(hist_names, histories):
        vals = _matrix_col(hd, b)
        if np.isfinite(vals).sum() >= 2:
            fig.add_trace(go.Scatter(x=MONTHS, y=vals, mode="lines+markers", name=name, line=dict(width=1.6)))
    t = results[b]
    fig.add_trace(go.Scatter(x=MONTHS, y=t["Prime brute"], mode="lines+markers", name="N · Prime brute", line=dict(width=4)))
    fig.add_trace(go.Scatter(x=MONTHS, y=t["Prime réassurance"], mode="lines+markers", name="N · Réassurance", line=dict(width=2.5)))
    fig.add_trace(go.Scatter(x=MONTHS, y=t["Prime nette"], mode="lines+markers", name="N · Nette", line=dict(width=2.5)))
    fig.update_layout(
        title=f"{b} · historique et projection des primes",
        height=430, margin=dict(l=20,r=20,t=60,b=30),
        legend=dict(orientation="h", y=-0.18), hovermode="x unified",
        yaxis_title="FCFA cumulés", xaxis_title=None, paper_bgcolor="white", plot_bgcolor="white",
    )

    commission_fig = go.Figure()
    commission_fig.add_trace(go.Scatter(x=MONTHS, y=t["Taux commission Direct (%)"], mode="lines+markers", name="Commission Direct", line=dict(width=3)))
    commission_fig.add_trace(go.Scatter(x=MONTHS, y=t["Taux récupération commission Réassurance (%)"], mode="lines+markers", name="Récupération commission Réass", line=dict(width=3)))
    commission_fig.add_trace(go.Scatter(x=MONTHS, y=t["Taux commission CPC IFRS (%)" if view=="IFRS" else "Taux commission CPC Local (%)"], mode="lines+markers", name=f"Taux CPC net · {view}", line=dict(width=4)))
    if view == "IFRS":
        commission_fig.add_trace(go.Scatter(x=MONTHS, y=t["Taux DAC Direct IFRS (%)"], mode="lines+markers", name="DAC Direct", line=dict(width=2)))
        commission_fig.add_trace(go.Scatter(x=MONTHS, y=t["Taux DAC Réassurance IFRS (%)"], mode="lines+markers", name="DAC Réass", line=dict(width=2)))
    commission_fig.update_layout(
        title=f"{b} · commission Direct, récupération Réassurance et taux CPC",
        height=420, margin=dict(l=20,r=20,t=60,b=30),
        legend=dict(orientation="h", y=-0.2), hovermode="x unified",
        yaxis_title="%", xaxis_title=None, paper_bgcolor="white", plot_bgcolor="white",
    )

    dcomm_rate = _month_matrix_from_results(results, "Taux commission Direct (%)")
    dcomm = _month_matrix_from_results(results, "Commission Direct")
    rcomm_rate = _month_matrix_from_results(results, "Taux récupération commission Réassurance (%)")
    rcomm = _month_matrix_from_results(results, "Commission Réassurance")
    ddac_rate = _month_matrix_from_results(results, "Taux DAC Direct IFRS (%)")
    ddac_open = _month_matrix_from_results(results, "DAC ouverture Direct IFRS")
    ddac_close = _month_matrix_from_results(results, "DAC clôture Direct IFRS")
    ddac_var = _month_matrix_from_results(results, "Variation DAC Direct IFRS")
    rdac_rate = _month_matrix_from_results(results, "Taux DAC Réassurance IFRS (%)")
    rdac_open = _month_matrix_from_results(results, "DAC ouverture Réassurance IFRS")
    rdac_close = _month_matrix_from_results(results, "DAC clôture Réassurance IFRS")
    rdac_var = _month_matrix_from_results(results, "Variation DAC Réassurance IFRS")

    diag_df = pd.DataFrame({"Diagnostic": diags[:250] if diags else ["Aucune incohérence détectée"]})
    return (
        _summary_html(results, view), landing_summary, fig,
        gross, cession, ceded, net,
        rd_rate, direct_var, direct_close, direct_earned,
        reass_rate, reass_var, reass_close, reass_earned, net_earned,
        _commission_summary_html(results, view), commission_landing_summary, commission_fig,
        dcomm_rate, dcomm, rcomm_rate, rcomm, cpc_comm_rate,
        ddac_rate, ddac_open, ddac_close, ddac_var,
        rdac_rate, rdac_open, rdac_close, rdac_var,
        diag_df,
        f"Vue {view} · Direct : {'REC prorata issue de la REC CIMA 72% / 72%' if view=='IFRS' else 'REC CIMA 72%'} · Réassurance : {rec_label}",
        _branch_kpi_html(results, anchors, b, view),
        _branch_editor_table(results, b, view),
        _branch_editor_table(results, b, view),
        _branch_result_table(results, b, view),
        _commission_branch_table(results, b, view),
    )



def _ensure_month_grid(df) -> pd.DataFrame:
    d = pd.DataFrame(df).copy()
    if "Mois" not in d.columns:
        d.insert(0, "Mois", MONTHS[:len(d)])
    if len(d) < 12:
        for _ in range(12-len(d)):
            d.loc[len(d)] = [MONTHS[len(d)]] + [np.nan]*(len(d.columns)-1)
    return d.iloc[:12].reset_index(drop=True)


def _numeric_branch_frame(df) -> pd.DataFrame:
    d = _ensure_month_grid(df)
    out = pd.DataFrame(index=range(12))
    for b in BRANCHES:
        out[b] = [_num(v, 0.0) for v in (d[b].tolist() if b in d.columns else [0.0]*12)]
    return out


def _sp_matrix_with_months(values: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame(values).copy().reset_index(drop=True)
    d.insert(0, "Mois", MONTHS)
    return d


def _sp_summary_html(portfolio: pd.DataFrame, branch_table: pd.DataFrame, month: str, branch: str, view: str) -> str:
    idx = MONTHS.index(month) if month in MONTHS else 11
    p = portfolio.iloc[idx]
    b = branch_table.iloc[idx]
    prior = _num(b.get("Charge antérieurs"), 0.0)
    prior_label = "Boni antérieurs" if prior < 0 else "Mali antérieurs"
    prior_value = abs(prior)
    return f"""
    <div style='display:grid;grid-template-columns:repeat(7,minmax(130px,1fr));gap:9px'>
      <div class='sp-kpi'><span>Mois</span><br><b>{month}</b></div>
      <div class='sp-kpi'><span>S/P exercice portefeuille</span><br><b>{_num(p.get('S/P exercice portefeuille (%)'),0):.2f}%</b></div>
      <div class='sp-kpi'><span>S/P global portefeuille</span><br><b>{_num(p.get('S/P global portefeuille (%)'),0):.2f}%</b></div>
      <div class='sp-kpi'><span>Charge globale portefeuille</span><br><b>{_fmt_currency(p.get('Charge globale'))}</b></div>
      <div class='sp-kpi'><span>Résultat technique avant FG</span><br><b>{_fmt_currency(p.get('Résultat technique avant FG'))}</b></div>
      <div class='sp-kpi'><span>{branch} · {prior_label}</span><br><b>{_fmt_currency(prior_value)}</b></div>
      <div class='sp-kpi'><span>Marge technique · {view}</span><br><b>{_num(p.get('Marge technique avant FG (%)'),0):.2f}%</b></div>
    </div>"""


def _sp_branch_table(sp_ex, sp_global, charge_ex, charge_prior, charge_global, result, branch: str) -> pd.DataFrame:
    b = branch if branch in BRANCHES else BRANCHES[0]
    return pd.DataFrame({
        "Mois": MONTHS,
        "S/P exercice (%)": pd.DataFrame(sp_ex)[b].to_numpy(float),
        "S/P global (%)": pd.DataFrame(sp_global)[b].to_numpy(float),
        "Charge exercice": pd.DataFrame(charge_ex)[b].to_numpy(float),
        "Charge antérieurs": pd.DataFrame(charge_prior)[b].to_numpy(float),
        "Charge globale": pd.DataFrame(charge_global)[b].to_numpy(float),
        "Résultat technique avant FG": pd.DataFrame(result)[b].to_numpy(float),
    })


def _sp_editor_table(sp_ex, sp_global, branch: str) -> pd.DataFrame:
    b = branch if branch in BRANCHES else BRANCHES[0]
    return pd.DataFrame({
        "Mois": MONTHS,
        "S/P exercice (%)": pd.DataFrame(sp_ex)[b].to_numpy(float),
        "S/P global (%)": pd.DataFrame(sp_global)[b].to_numpy(float),
    })


def run_sp_projection(
    earned_grid, direct_commission_grid, reass_commission_grid, direct_dac_var_grid, view, selected_branch, sp_month,
    sp_ex_settings, sp_global_settings, sp_ex_manual, sp_global_manual, locked_branches,
    portfolio_mode, portfolio_ex_start, portfolio_ex_end, portfolio_global_start, portfolio_global_end, portfolio_manual,
):
    earned = _numeric_branch_frame(earned_grid)
    dcomm = _numeric_branch_frame(direct_commission_grid)
    rcomm = _numeric_branch_frame(reass_commission_grid)
    ddac = _numeric_branch_frame(direct_dac_var_grid)
    commission_net = dcomm-rcomm if view != "IFRS" else dcomm+ddac-rcomm

    pex_target = build_portfolio_target(portfolio_mode, portfolio_ex_start, portfolio_ex_end, portfolio_manual, "S/P exercice cible (%)")
    pgl_target = build_portfolio_target(portfolio_mode, portfolio_global_start, portfolio_global_end, portfolio_manual, "S/P global cible (%)")

    sp_ex, ex_lo, ex_hi, ex_ach, d1 = optimize_sp_matrix(
        earned, sp_ex_settings, sp_ex_manual, locked_branches or [], pex_target, 0.0, 0.0
    )
    sp_gl, gl_lo, gl_hi, gl_ach, d2 = optimize_sp_matrix(
        earned, sp_global_settings, sp_global_manual, locked_branches or [], pgl_target, 0.0, 0.0
    )
    charge_ex, charge_prior, charge_global, result = calculate_claims_and_result(earned, commission_net, sp_ex, sp_gl)
    portfolio = portfolio_metrics(earned, charge_ex, charge_global, commission_net, result)

    b = selected_branch if selected_branch in BRANCHES else BRANCHES[0]
    branch_table = _sp_branch_table(sp_ex,sp_gl,charge_ex,charge_prior,charge_global,result,b)
    editor = _sp_editor_table(sp_ex,sp_gl,b)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=MONTHS,y=sp_ex[b],mode="lines+markers",name="S/P exercice",line=dict(width=3)))
    fig.add_trace(go.Scatter(x=MONTHS,y=sp_gl[b],mode="lines+markers",name="S/P global",line=dict(width=3)))
    fig.add_trace(go.Scatter(x=MONTHS,y=ex_lo[b],mode="lines",name="Borne basse exercice",line=dict(width=1,dash="dot"),opacity=.45))
    fig.add_trace(go.Scatter(x=MONTHS,y=ex_hi[b],mode="lines",name="Borne haute exercice",line=dict(width=1,dash="dot"),opacity=.45,fill="tonexty"))
    if np.isfinite(pex_target).any():
        fig.add_trace(go.Scatter(x=MONTHS,y=pex_target,mode="lines",name="Cible portefeuille exercice",line=dict(width=2,dash="dash")))
    if np.isfinite(pgl_target).any():
        fig.add_trace(go.Scatter(x=MONTHS,y=pgl_target,mode="lines",name="Cible portefeuille global",line=dict(width=2,dash="dash")))
    fig.add_trace(go.Bar(x=MONTHS,y=result[b],name="Résultat technique",yaxis="y2",opacity=.22))
    fig.update_layout(
        title=f"{b} · S/P, bande autorisée et résultat technique",height=440,
        margin=dict(l=20,r=20,t=55,b=30),hovermode="x unified",
        yaxis=dict(title="S/P (%)"),
        yaxis2=dict(title="Résultat technique",overlaying="y",side="right",showgrid=False),
        legend=dict(orientation="h",y=1.12),
    )
    diag = pd.DataFrame({"Diagnostic": (d1+d2)[:200] if (d1+d2) else ["Cibles et plages cohérentes"]})
    return (
        _sp_summary_html(portfolio,branch_table,sp_month,b,view), fig, branch_table,
        _sp_matrix_with_months(sp_ex), _sp_matrix_with_months(sp_gl),
        _sp_matrix_with_months(charge_ex), _sp_matrix_with_months(charge_prior),
        _sp_matrix_with_months(charge_global), _sp_matrix_with_months(result), portfolio, diag,
        editor, editor.copy(),
    )


def apply_sp_branch_editor(editor, reference, branch, ex_manual, global_manual):
    ed = pd.DataFrame(editor).copy(); ref = pd.DataFrame(reference).copy()
    em = pd.DataFrame(ex_manual).copy(); gm = pd.DataFrame(global_manual).copy()
    if branch not in BRANCHES or len(ed)<12 or len(ref)<12:
        return em,gm
    def changed(a,b):
        aa,bb=_num(a,np.nan),_num(b,np.nan)
        if np.isfinite(aa)!=np.isfinite(bb): return True
        if not np.isfinite(aa): return False
        return abs(aa-bb)>1e-8
    for i in range(12):
        for col,target in [("S/P exercice (%)",em),("S/P global (%)",gm)]:
            if col in ed.columns and col in ref.columns and changed(ed.iloc[i][col],ref.iloc[i][col]):
                v=_num(ed.iloc[i][col],np.nan)
                target.loc[i,branch]=v if np.isfinite(v) else np.nan
    return em,gm


def reset_sp_branch(branch, ex_manual, global_manual):
    em=pd.DataFrame(ex_manual).copy(); gm=pd.DataFrame(global_manual).copy()
    if branch in BRANCHES:
        em.loc[:,branch]=np.nan; gm.loc[:,branch]=np.nan
    return em,gm

def apply_point_override(matrix, branch, month, value):
    d = pd.DataFrame(matrix).copy()
    if d.empty or branch not in d.columns or month not in MONTHS:
        return d
    idx = MONTHS.index(month)
    d.loc[idx, branch] = np.nan if not np.isfinite(_num(value)) else float(_num(value))
    return d


def clear_point_override(matrix, branch, month):
    return apply_point_override(matrix, branch, month, np.nan)


def apply_branch_table(editor, reference, branch, view, gross_m, cession_m, rec_direct_m, rec_local_m, rec_ifrs_m):
    """Applique seulement les cellules réellement modifiées dans le tableau compact.

    Une cellule vidée supprime l'override correspondant. Les cellules inchangées
    conservent l'état précédent, ce qui permet d'afficher les valeurs calculées
    sans transformer tout le tableau en contraintes manuelles.
    """
    ed = pd.DataFrame(editor).copy()
    ref = pd.DataFrame(reference).copy()
    if branch not in BRANCHES or len(ed) < 12 or len(ref) < 12:
        return gross_m, cession_m, rec_direct_m, rec_local_m, rec_ifrs_m

    mappings = [
        ("Prime brute", gross_m),
        ("Taux cession (%)", cession_m),
        ("Taux REC Direct (%)", rec_direct_m),
    ]
    out = [pd.DataFrame(x).copy() for _, x in mappings]
    rl = pd.DataFrame(rec_local_m).copy()
    ri = pd.DataFrame(rec_ifrs_m).copy()

    def changed(a, b):
        aa, bb = _num(a, np.nan), _num(b, np.nan)
        if not np.isfinite(aa) and not np.isfinite(bb): return False
        if np.isfinite(aa) != np.isfinite(bb): return True
        return abs(aa-bb) > max(1e-7, abs(bb)*1e-10)

    for i in range(12):
        for j, (col, _) in enumerate(mappings):
            if col not in ed.columns or col not in ref.columns: continue
            if changed(ed.iloc[i][col], ref.iloc[i][col]):
                v = _num(ed.iloc[i][col], np.nan)
                out[j].loc[i, branch] = v if np.isfinite(v) else np.nan
        col = "Taux REC Réass (%)"
        if col in ed.columns and col in ref.columns and changed(ed.iloc[i][col], ref.iloc[i][col]):
            v = _num(ed.iloc[i][col], np.nan)
            target = ri if view == "IFRS" else rl
            target.loc[i, branch] = v if np.isfinite(v) else np.nan
    return out[0], out[1], out[2], rl, ri


def reset_branch_overrides(branch, gross_m, cession_m, rec_direct_m, rec_local_m, rec_ifrs_m):
    mats = [pd.DataFrame(x).copy() for x in [gross_m, cession_m, rec_direct_m, rec_local_m, rec_ifrs_m]]
    if branch in BRANCHES:
        for m in mats:
            if branch in m.columns:
                m.loc[:, branch] = np.nan
    return tuple(mats)


def _sheet_matrix(ws, marker: str, percent: bool = False) -> pd.DataFrame:
    # Find exact marker in column A, header is next row, 12 months below.
    row = None
    for r in range(1, ws.max_row + 1):
        if str(ws.cell(r, 1).value or "").strip() == marker:
            row = r
            break
    if row is None:
        return blank_month_matrix()
    hdr = row + 1
    out = {"Mois": MONTHS}
    for j, b in enumerate(BRANCHES, start=2):
        vals = []
        for i in range(12):
            v = ws.cell(hdr + 1 + i, j).value
            if percent and v is not None:
                try:
                    v = float(v) * 100.0
                except Exception:
                    txt = str(v).strip()
                    if txt.endswith("%"):
                        try: v = float(txt[:-1].replace(",","."))
                        except Exception: pass
            vals.append(v)
        out[b] = vals
    return pd.DataFrame(out)


def _find_block_value(ws, block_title: str, line_label: str, branch: str, occurrence: int = 1):
    title_row = None
    for r in range(1, ws.max_row + 1):
        if str(ws.cell(r,1).value or "").strip() == block_title:
            title_row = r
            break
    if title_row is None:
        return np.nan
    # block ends at next all-caps title in col A or 120 rows later.
    header_row = title_row + 1
    headers = [str(ws.cell(header_row, c).value or "").strip() for c in range(1, 12)]
    try:
        branch_col = headers.index(branch) + 1
    except ValueError:
        return np.nan
    count = 0
    for r in range(header_row + 1, min(ws.max_row, title_row + 120) + 1):
        a = str(ws.cell(r,1).value or "").strip()
        b = str(ws.cell(r,2).value or "").strip()
        if r > header_row + 1 and a and a.upper() == a and "—" in a:
            break
        if b == line_label:
            count += 1
            if count == occurrence:
                return ws.cell(r, branch_col).value
    return np.nan



def _expense_component_block(ws, block_title: str, lines):
    out = blank_component_table(lines)
    title_row = None
    for r in range(1, ws.max_row + 1):
        if str(ws.cell(r, 1).value or "").strip() == block_title:
            title_row = r
            break
    if title_row is None:
        return out
    header_row = title_row + 1
    headers = [str(ws.cell(header_row, c).value or "").strip() for c in range(1, 10)]
    branch_cols = {}
    for b in BRANCHES:
        if b in headers:
            branch_cols[b] = headers.index(b) + 1
    wanted = {str(x).strip(): i for i, x in enumerate(lines)}
    for r in range(header_row + 1, min(ws.max_row, title_row + 80) + 1):
        label = str(ws.cell(r, 1).value or "").strip()
        if label in wanted:
            idx = wanted[label]
            for b, c in branch_cols.items():
                out.loc[idx, b] = ws.cell(r, c).value
    return out


def _with_months(df: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame(df).copy()
    d.insert(0, "Mois", MONTHS)
    return d


def _fg_persistent_html(portfolio: pd.DataFrame, fg_rate: pd.DataFrame, result_after_fg: pd.DataFrame,
                        financial_net: pd.DataFrame, result_after_fin: pd.DataFrame,
                        branch: str, month: str, view: str) -> str:
    b = branch if branch in BRANCHES else BRANCHES[0]
    i = MONTHS.index(month) if month in MONTHS else 11
    p = pd.DataFrame(portfolio)
    if p.empty or i >= len(p):
        return "<div class='kpi'>En attente de calcul</div>"
    br_rate = _num(pd.DataFrame(fg_rate).loc[i, b], np.nan)
    port_rate = _num(p.loc[i, "Taux FG portefeuille (%)"], np.nan)
    br_after = _num(pd.DataFrame(result_after_fg).loc[i, b], 0.0)
    br_fin = _num(pd.DataFrame(financial_net).loc[i, b], 0.0)
    br_final = _num(pd.DataFrame(result_after_fin).loc[i, b], 0.0)
    return f"""
    <div id='persistent-kpis'>
      <div style='display:grid;grid-template-columns:repeat(6,minmax(135px,1fr));gap:8px'>
        <div class='kpi'><span>Contexte</span><br><b>{b} · {month}</b><br><small>{view}</small></div>
        <div class='kpi'><span>Taux FG · branche</span><br><b>{br_rate:.2f}%</b></div>
        <div class='kpi'><span>Taux FG · portefeuille</span><br><b>{port_rate:.2f}%</b></div>
        <div class='kpi'><span>Résultat après FG</span><br><b>{_fmt_currency(br_after)}</b></div>
        <div class='kpi'><span>Résultat financier net</span><br><b>{_fmt_currency(br_fin)}</b></div>
        <div class='kpi'><span>Résultat après financier</span><br><b>{_fmt_currency(br_final)}</b></div>
      </div>
    </div>"""


def _fg_summary_html(portfolio: pd.DataFrame, branch: str, month: str, view: str) -> str:
    p = pd.DataFrame(portfolio)
    i = MONTHS.index(month) if month in MONTHS else 11
    if p.empty or i >= len(p):
        return ""
    r = p.iloc[i]
    return f"""
    <div style='display:grid;grid-template-columns:repeat(6,minmax(140px,1fr));gap:9px'>
      <div class='kpi'><span>Prime acquise nette</span><br><b>{_fmt_currency(r['Prime acquise nette'])}</b></div>
      <div class='kpi'><span>Frais généraux</span><br><b>{_fmt_currency(r['Frais généraux'])}</b></div>
      <div class='kpi'><span>Taux FG</span><br><b>{r['Taux FG portefeuille (%)']:.2f}%</b></div>
      <div class='kpi'><span>Résultat après FG</span><br><b>{_fmt_currency(r['Résultat technique après FG'])}</b></div>
      <div class='kpi'><span>Résultat financier net</span><br><b>{_fmt_currency(r['Résultat financier net'])}</b></div>
      <div class='kpi'><span>Résultat final</span><br><b>{_fmt_currency(r['Résultat après financier'])}</b></div>
    </div>"""


def run_fg_projection(
    earned_grid, technical_result_grid, selected_branch, selected_month, view,
    fg_start, fg_end, fg_rate_settings, fg_rate_manual,
    pf_start, pf_end, pf_product_manual, pf_charge_manual,
):
    earned = _numeric_branch_frame(earned_grid)
    before = _numeric_branch_frame(technical_result_grid)
    projected = project_expenses(
        earned, pd.DataFrame(fg_start), pd.DataFrame(fg_end), pd.DataFrame(fg_rate_settings), pd.DataFrame(fg_rate_manual),
        pd.DataFrame(pf_start), pd.DataFrame(pf_end), pd.DataFrame(pf_product_manual), pd.DataFrame(pf_charge_manual), before,
    )
    portfolio = portfolio_expense_metrics(earned, before, projected)
    b = selected_branch if selected_branch in BRANCHES else BRANCHES[0]
    i = MONTHS.index(selected_month) if selected_month in MONTHS else 11

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=MONTHS, y=projected["fg_rate"][b], mode="lines+markers", name="Taux FG (%)", line=dict(width=3)))
    fig.add_trace(go.Bar(x=MONTHS, y=projected["fg_total"][b], name="Frais généraux", yaxis="y2", opacity=.25))
    fig.add_trace(go.Scatter(x=MONTHS, y=projected["result_after_fg"][b], mode="lines", name="Résultat après FG", yaxis="y2", line=dict(width=2)))
    fig.add_trace(go.Scatter(x=MONTHS, y=projected["result_after_financial"][b], mode="lines+markers", name="Résultat après financier", yaxis="y2", line=dict(width=3)))
    fig.update_layout(
        title=f"{b} · Frais généraux, financier et résultat", height=420, hovermode="x unified",
        margin=dict(l=20,r=20,t=55,b=30), yaxis=dict(title="Taux FG (%)"),
        yaxis2=dict(title="Montants", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.13),
    )

    diag = pd.DataFrame({"Diagnostic": projected["diagnostics"][:200] if projected["diagnostics"] else ["Projection FG et financier cohérente"]})
    # compact selected-branch table
    branch_table = pd.DataFrame({
        "Mois": MONTHS,
        "Frais généraux": projected["fg_total"][b].to_numpy(float),
        "Taux FG (%)": projected["fg_rate"][b].to_numpy(float),
        "Résultat après FG": projected["result_after_fg"][b].to_numpy(float),
        "Produits financiers": projected["financial_products"][b].to_numpy(float),
        "Charges financières": projected["financial_charges"][b].to_numpy(float),
        "Résultat financier net": projected["financial_net"][b].to_numpy(float),
        "Résultat après financier": projected["result_after_financial"][b].to_numpy(float),
    })
    return (
        _fg_persistent_html(portfolio, projected["fg_rate"], projected["result_after_fg"], projected["financial_net"], projected["result_after_financial"], b, selected_month, view),
        _fg_summary_html(portfolio, b, selected_month, view), fig, branch_table,
        _with_months(projected["fg_rate"]), _with_months(projected["fg_total"]), _with_months(projected["result_after_fg"]),
        _with_months(projected["financial_products"]), _with_months(projected["financial_charges"]), _with_months(projected["financial_net"]),
        _with_months(projected["result_after_financial"]), portfolio, diag,
    )

def load_template(file_obj):
    if file_obj is None:
        raise gr.Error("Sélectionnez un fichier Excel.")
    path = file_obj if isinstance(file_obj, str) else getattr(file_obj, "name", file_obj)
    wb = load_workbook(path, data_only=False, read_only=False)

    hist = wb["Historique primes"]
    h3 = _sheet_matrix(hist, "PRIMES ÉMISES CUMULÉES — N-3")
    h2 = _sheet_matrix(hist, "PRIMES ÉMISES CUMULÉES — N-2")
    h1 = _sheet_matrix(hist, "PRIMES ÉMISES CUMULÉES — N-1")

    taux = wb["Taux historiques"]
    c_hist = _sheet_matrix(taux, "TAUX DE CESSION — N-1", percent=True)
    rd_hist = _sheet_matrix(taux, "TAUX VARIATION REC DIRECT CIMA 72% — N-1", percent=True)
    rl_hist = _sheet_matrix(taux, "TAUX VARIATION REC RÉASS LOCAL — N-1", percent=True)
    ri_hist = _sheet_matrix(taux, "TAUX VARIATION REC RÉASS IFRS 100% — N-1", percent=True)

    anc_ws = wb["Ancrages globaux"]
    rows = []
    for b in BRANCHES:
        # First REC occurrence is CIMA in Direct Local / Reass Local.
        d_rec = _find_block_value(anc_ws, "DIRECT LOCAL — DÉPART (FACULTATIF)", "REC Ouverture", b, 1)
        if not np.isfinite(_num(d_rec)): d_rec = _find_block_value(anc_ws, "DIRECT LOCAL — ATTERRISSAGE", "REC Ouverture", b, 1)
        r_rec = _find_block_value(anc_ws, "REASS LOCAL — DÉPART (FACULTATIF)", "REC Ouverture", b, 1)
        if not np.isfinite(_num(r_rec)): r_rec = _find_block_value(anc_ws, "REASS LOCAL — ATTERRISSAGE", "REC Ouverture", b, 1)
        ri_rec = _find_block_value(anc_ws, "REASS IFRS — DÉPART (FACULTATIF)", "REC Ouverture 100%", b, 1)
        if not np.isfinite(_num(ri_rec)): ri_rec = _find_block_value(anc_ws, "REASS IFRS — ATTERRISSAGE", "REC Ouverture 100%", b, 1)
        rows.append({
            "Branche": b,
            "Départ Direct (facultatif)": _find_block_value(anc_ws, "DIRECT LOCAL — DÉPART (FACULTATIF)", "Primes Emises", b, 1),
            "Atterrissage Direct": _find_block_value(anc_ws, "DIRECT LOCAL — ATTERRISSAGE", "Primes Emises", b, 1),
            "Départ Réassurance (facultatif)": _find_block_value(anc_ws, "REASS LOCAL — DÉPART (FACULTATIF)", "Primes Emises", b, 1),
            "Atterrissage Réassurance": _find_block_value(anc_ws, "REASS LOCAL — ATTERRISSAGE", "Primes Emises", b, 1),
            "REC ouverture Direct CIMA 72%": d_rec,
            "REC ouverture Réass Local CIMA": r_rec,
            "REC ouverture Réass IFRS 100%": ri_rec,
        })
    anchors = pd.DataFrame(rows, columns=ANCHOR_COLS)

    commission_rows = []
    for b in BRANCHES:
        commission_rows.append({
            "Branche": b,
            "Commission Direct départ": _find_block_value(anc_ws, "DIRECT LOCAL — DÉPART (FACULTATIF)", "Commisions", b, 1),
            "Commission Direct atterrissage": _find_block_value(anc_ws, "DIRECT LOCAL — ATTERRISSAGE", "Commisions", b, 1),
            "Commission Réass départ": _find_block_value(anc_ws, "REASS LOCAL — DÉPART (FACULTATIF)", "Commisions", b, 1),
            "Commission Réass atterrissage": _find_block_value(anc_ws, "REASS LOCAL — ATTERRISSAGE", "Commisions", b, 1),
            "DAC Ouv Direct IFRS": _find_block_value(anc_ws, "DIRECT IFRS — DÉPART (FACULTATIF)", "DAC Ouv", b, 1),
            "DAC Clo Direct IFRS": _find_block_value(anc_ws, "DIRECT IFRS — ATTERRISSAGE", "DAC Clo", b, 1),
            "REC Ouv prorata Direct IFRS": _find_block_value(anc_ws, "DIRECT IFRS — DÉPART (FACULTATIF)", "REC Ouverture", b, 2),
            "REC Clo prorata Direct IFRS": _find_block_value(anc_ws, "DIRECT IFRS — ATTERRISSAGE", "REC Clôture", b, 2),
            "DAC Ouv Réass IFRS": _find_block_value(anc_ws, "REASS IFRS — DÉPART (FACULTATIF)", "DAC Ouv", b, 1),
            "DAC Clo Réass IFRS": _find_block_value(anc_ws, "REASS IFRS — ATTERRISSAGE", "DAC Clo", b, 1),
            "REC Ouv 100% Réass IFRS": _find_block_value(anc_ws, "REASS IFRS — DÉPART (FACULTATIF)", "REC Ouverture 100%", b, 1),
            "REC Clo 100% Réass IFRS": _find_block_value(anc_ws, "REASS IFRS — ATTERRISSAGE", "REC Clôture 100%", b, 1),
        })
    commission_anchors = pd.DataFrame(commission_rows, columns=COMMISSION_ANCHOR_COLS)

    fg_start = blank_component_table(FG_COMPONENTS)
    fg_end = blank_component_table(FG_COMPONENTS)
    pf_lines = PF_REVENUES + PF_CHARGES
    pf_start = blank_component_table(pf_lines)
    pf_end = blank_component_table(pf_lines)
    if "FG & Produits financiers" in wb.sheetnames:
        ews = wb["FG & Produits financiers"]
        fg_start = _expense_component_block(ews, "FRAIS GÉNÉRAUX — DÉPART (FACULTATIF)", FG_COMPONENTS)
        fg_end = _expense_component_block(ews, "FRAIS GÉNÉRAUX — ATTERRISSAGE", FG_COMPONENTS)
        pf_start = _expense_component_block(ews, "PRODUITS FINANCIERS — DÉPART (FACULTATIF)", pf_lines)
        pf_end = _expense_component_block(ews, "PRODUITS FINANCIERS — ATTERRISSAGE", pf_lines)
    return h3, h2, h1, anchors, commission_anchors, c_hist, rd_hist, rl_hist, ri_hist, fg_start, fg_end, pf_start, pf_end, "Fichier chargé avec succès."


def build_app():
    with gr.Blocks(title="Cockpit actuariel · Projection technique") as demo:
        gr.HTML("""
        <div id='hero'>
          <h1>Cockpit actuariel · Projection technique</h1>
          <p>Piloter les trajectoires techniques, comprendre l'impact et ajuster sans perdre la cohérence Direct / Réassurance / CPC.</p>
        </div>
        """)

        # Contexte unique et persistant : aucun module ne redemande la branche ou le référentiel.
        with gr.Row(elem_id="prime-toolbar"):
            selected_branch = gr.Dropdown(BRANCHES, value=BRANCHES[0], label="Branche", scale=2)
            view = gr.Radio(["Local", "IFRS"], value="Local", label="Référentiel", scale=1)
            selected_month = gr.Dropdown(MONTHS, value=MONTHS[-1], label="Période", scale=1)
            scenario_display = gr.Textbox(value="Scénario ajusté", label="Scénario", interactive=False, scale=1)
            recalc = gr.Button("Actualiser", variant="secondary", scale=1)
        gr.HTML("""
        <div class='context-legend'>
          <span class='badge auto'>Automatique</span>
          <span class='badge manual'>Modifié manuellement</span>
          <span class='badge lock'>Verrouillé</span>
          <span>Les paramètres globaux ci-dessus s'appliquent à tous les onglets.</span>
        </div>
        """)
        persistent_kpis = gr.HTML("<div id='persistent-kpis'><div class='kpi'><span>État</span><br><b>Chargez les hypothèses</b></div></div>")

        # States / données partagées.
        gross_manual = gr.State(blank_month_matrix())
        commission_anchors = gr.State(blank_commission_anchors())

        with gr.Tabs():
            with gr.Tab("Données"):
                gr.Markdown("### Source unique du scénario", elem_classes="section-title")
                gr.Markdown("Chargez les hypothèses une fois : elles alimentent ensuite tous les modules sans ressaisie.", elem_classes="muted")
                with gr.Row():
                    with gr.Column(scale=3, elem_classes="card"):
                        upload = gr.File(label="Importer le fichier d’hypothèses", file_types=[".xlsx"], type="filepath")
                        with gr.Row():
                            load_btn = gr.Button("Charger les données", variant="primary")
                            load_status = gr.Textbox(label="État du chargement", interactive=False)
                    with gr.Column(scale=2, elem_classes="card"):
                        gr.Markdown("**Modèle de saisie**")
                        gr.Markdown("Utilisez le fichier standardisé pour conserver le même ordre de branches et les mêmes ancrages dans tous les modules.", elem_classes="muted")
                        download = gr.DownloadButton("Télécharger le modèle Excel", value=str(TEMPLATE_PATH), variant="secondary")
                with gr.Accordion("Consulter / corriger les données chargées", open=False):
                    with gr.Tabs():
                        with gr.Tab("Historique primes"):
                            with gr.Accordion("N-3", open=False):
                                hist_n3 = gr.Dataframe(value=blank_history(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Primes émises cumulées N-3")
                            with gr.Accordion("N-2", open=False):
                                hist_n2 = gr.Dataframe(value=blank_history(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Primes émises cumulées N-2")
                            with gr.Accordion("N-1", open=True):
                                hist_n1 = gr.Dataframe(value=blank_history(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Primes émises cumulées N-1")
                        with gr.Tab("Ancrages"):
                            anchors = gr.Dataframe(value=blank_anchors(), headers=ANCHOR_COLS, interactive=True, elem_classes="matrix", label="Primes / REC · Départ et atterrissage")
                        with gr.Tab("Frais généraux"):
                            with gr.Row():
                                fg_start = gr.Dataframe(value=blank_component_table(FG_COMPONENTS), interactive=True, elem_classes="matrix", label="Départ")
                                fg_end = gr.Dataframe(value=blank_component_table(FG_COMPONENTS), interactive=True, elem_classes="matrix", label="Atterrissage")
                        with gr.Tab("Financier"):
                            pf_lines = PF_REVENUES + PF_CHARGES
                            with gr.Row():
                                pf_start = gr.Dataframe(value=blank_component_table(pf_lines), interactive=True, elem_classes="matrix", label="Départ")
                                pf_end = gr.Dataframe(value=blank_component_table(pf_lines), interactive=True, elem_classes="matrix", label="Atterrissage")

            with gr.Tab("Primes"):
                gr.Markdown("### Primes · Voir → ajuster → mesurer l'impact", elem_classes="section-title")
                with gr.Tabs():
                    with gr.Tab("Vue branche"):
                        with gr.Column(elem_classes="workspace"):
                            branch_kpis = gr.HTML()
                            chart = gr.Plot(label="Historique & projection")
                            gr.HTML("<div class='decision-note'>Modifiez uniquement les cellules que vous voulez contraindre. Une cellule vidée revient au calcul automatique ; les autres mois restent optimisés.</div>")
                            branch_editor = gr.Dataframe(
                                value=pd.DataFrame({"Mois":MONTHS,"Prime brute":[np.nan]*12,"Taux cession (%)":[np.nan]*12,"Taux REC Direct (%)":[np.nan]*12,"Taux REC Réass (%)":[np.nan]*12}),
                                headers=["Mois","Prime brute","Taux cession (%)","Taux REC Direct (%)","Taux REC Réass (%)"],
                                interactive=True, elem_classes="prime-editor", label="Variables pilotables · 12 mois",
                                row_count=(12,"fixed"), column_count=(5,"fixed"),
                            )
                            branch_reference = gr.State(pd.DataFrame())
                            with gr.Row():
                                apply_branch_edits = gr.Button("Appliquer les changements", variant="primary")
                                reset_branch_edits = gr.Button("Revenir à l'automatique", variant="secondary")
                            branch_result = gr.Dataframe(
                                headers=["Mois","Prime Réassurance","Prime nette","Prime acquise Direct","Prime acquise Réass","Prime acquise nette"],
                                interactive=False, elem_classes="prime-result", label="Résultats recalculés",
                            )
                            reference_note = gr.Markdown()
                    with gr.Tab("Vue portefeuille"):
                        summary = gr.HTML()
                        cession_landing = gr.Dataframe(interactive=False, elem_classes="matrix", label="Atterrissages & taux de cession implicites")
                        with gr.Tabs():
                            with gr.Tab("Brut"):
                                gross_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime brute Direct", elem_classes="matrix")
                            with gr.Tab("Réassurance"):
                                ceded_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime Réassurance", elem_classes="matrix")
                            with gr.Tab("Net"):
                                net_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime nette", elem_classes="matrix")
                            with gr.Tab("Acquise nette"):
                                net_earned_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime acquise nette", elem_classes="matrix")
                        with gr.Accordion("Détail des taux et REC", open=False):
                            cession_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux de cession (%)", elem_classes="matrix")
                            rec_direct_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux REC Direct (%)", elem_classes="matrix")
                            rec_direct_var_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Variation REC Direct", elem_classes="matrix")
                            rec_direct_close_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="REC clôture Direct", elem_classes="matrix")
                            direct_earned_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime acquise Direct", elem_classes="matrix")
                            rec_reass_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux REC Réass (%)", elem_classes="matrix")
                            rec_reass_var_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Variation REC Réass", elem_classes="matrix")
                            rec_reass_close_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="REC clôture Réass", elem_classes="matrix")
                            reass_earned_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Prime acquise Réassurance", elem_classes="matrix")
                    with gr.Tab("Paramètres avancés"):
                        gr.Markdown("Les trajectoires automatiques restent disponibles sans encombrer l'écran de pilotage.", elem_classes="muted")
                        with gr.Accordion("Cession", open=True):
                            cession_settings = gr.Dataframe(value=default_rate_settings("cession"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Règles par branche")
                            with gr.Row():
                                cession_hist = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Taux N-1 (%)")
                                cession_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Ajustements N (%)")
                        with gr.Accordion("REC Direct", open=False):
                            rec_direct_settings = gr.Dataframe(value=default_rate_settings("rec"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Règles REC Direct")
                            with gr.Row():
                                rec_direct_hist = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Taux N-1 (%)")
                                rec_direct_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Ajustements N (%)")
                        with gr.Accordion("REC Réassurance", open=False):
                            with gr.Row():
                                rec_reass_local_settings = gr.Dataframe(value=default_rate_settings("rec"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Local")
                                rec_reass_ifrs_settings = gr.Dataframe(value=default_rate_settings("rec"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="IFRS 100%")
                            with gr.Row():
                                rec_reass_local_hist = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Historique Local (%)")
                                rec_reass_ifrs_hist = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Historique IFRS (%)")
                            with gr.Row():
                                rec_reass_local_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Ajustements Local (%)")
                                rec_reass_ifrs_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Ajustements IFRS (%)")

            with gr.Tab("Commissions & DAC"):
                gr.Markdown("### Commissions & DAC", elem_classes="section-title")
                with gr.Tabs():
                    with gr.Tab("Vue branche"):
                        commission_chart = gr.Plot(label="Commission, récupération Réassurance & taux CPC")
                        commission_branch_table = gr.Dataframe(interactive=False, elem_classes="prime-result", label="Branche sélectionnée · 12 mois")
                        gr.HTML("<div class='decision-note'>Le contexte Branche / Période est celui du bandeau supérieur. La commission Réassurance dépend de la commission Direct via le taux de récupération.</div>")
                        with gr.Row():
                            direct_commission_override = gr.Number(label="Commission Direct · taux (%)", precision=3)
                            reass_commission_override = gr.Number(label="Récupération commission Réass (%)", precision=3)
                        with gr.Row():
                            apply_direct_commission = gr.Button("Appliquer au mois sélectionné", variant="primary")
                            apply_reass_commission = gr.Button("Appliquer récupération", variant="secondary")
                            clear_commission_point = gr.Button("Revenir à l'automatique", variant="secondary")
                        # Alias : aucun sélecteur Branche/Mois dupliqué.
                        commission_point_branch = selected_branch
                        commission_point_month = selected_month
                    with gr.Tab("Vue portefeuille"):
                        commission_summary = gr.HTML()
                        commission_landing = gr.Dataframe(interactive=False, elem_classes="matrix", label="Taux implicites issus des ancrages")
                        with gr.Tabs():
                            with gr.Tab("Taux CPC"):
                                cpc_commission_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux de commission CPC sur prime acquise nette (%)", elem_classes="matrix")
                            with gr.Tab("Direct"):
                                direct_commission_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux commission Direct (%)", elem_classes="matrix")
                                direct_commission_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Commission Direct", elem_classes="matrix")
                            with gr.Tab("Réassurance"):
                                reass_commission_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux récupération commission Réassurance (%)", elem_classes="matrix")
                                reass_commission_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Commission Réassurance", elem_classes="matrix")
                    with gr.Tab("Paramètres avancés"):
                        with gr.Accordion("Trajectoires de commission", open=True):
                            with gr.Row():
                                direct_commission_settings = gr.Dataframe(value=default_rate_settings("commission"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Commission Direct")
                                reass_commission_settings = gr.Dataframe(value=default_rate_settings("commission"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Récupération Réassurance")
                            with gr.Row():
                                direct_commission_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Ajustements Direct (%)")
                                reass_commission_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Ajustements récupération Réass (%)")
                        with gr.Accordion("DAC · IFRS uniquement", open=False):
                            with gr.Row():
                                direct_dac_settings = gr.Dataframe(value=default_rate_settings("dac"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="DAC Direct")
                                reass_dac_settings = gr.Dataframe(value=default_rate_settings("dac"), headers=RATE_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="DAC Réassurance")
                            with gr.Row():
                                direct_dac_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Ajustements DAC Direct (%)")
                                reass_dac_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Ajustements DAC Réass (%)")
                            with gr.Accordion("Détail calculé", open=False):
                                direct_dac_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux DAC Direct IFRS (%)", elem_classes="matrix")
                                reass_dac_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Taux DAC Réass IFRS (%)", elem_classes="matrix")
                                direct_dac_open_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="DAC ouverture Direct IFRS", elem_classes="matrix")
                                direct_dac_close_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="DAC clôture Direct IFRS", elem_classes="matrix")
                                direct_dac_var_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Variation DAC Direct IFRS", elem_classes="matrix")
                                reass_dac_open_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="DAC ouverture Réass IFRS", elem_classes="matrix")
                                reass_dac_close_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="DAC clôture Réass IFRS", elem_classes="matrix")
                                reass_dac_var_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, label="Variation DAC Réass IFRS", elem_classes="matrix")

            with gr.Tab("S/P & Charges"):
                gr.Markdown("### S/P & Charges · piloter la charge, pas les lignes comptables", elem_classes="section-title")
                with gr.Tabs():
                    with gr.Tab("Vue branche"):
                        sp_summary = gr.HTML()
                        sp_chart = gr.Plot(label="S/P, bande autorisée et résultat technique")
                        sp_branch_editor = gr.Dataframe(
                            value=pd.DataFrame({"Mois":MONTHS,"S/P exercice (%)":[np.nan]*12,"S/P global (%)":[np.nan]*12}),
                            headers=["Mois","S/P exercice (%)","S/P global (%)"], interactive=True,
                            row_count=(12,"fixed"), column_count=(3,"fixed"), elem_classes="sp-editor", label="Variables pilotables · branche",
                        )
                        sp_branch_reference = gr.State(pd.DataFrame())
                        with gr.Row():
                            apply_sp_edits = gr.Button("Appliquer les changements", variant="primary")
                            reset_sp_edits = gr.Button("Revenir à l'automatique", variant="secondary")
                        sp_branch_result = gr.Dataframe(
                            headers=["Mois","S/P exercice (%)","S/P global (%)","Charge exercice","Charge antérieurs","Charge globale","Résultat technique avant FG"],
                            interactive=False, elem_classes="prime-result", label="Charges & résultat recalculés",
                        )
                    with gr.Tab("Vue portefeuille"):
                        gr.Markdown("**Objectif portefeuille** · verrouillez les branches à préserver ; l'optimiseur répartit l'effort sur les autres dans leurs plages autorisées.")
                        locked_branches = gr.CheckboxGroup(BRANCHES, label="Branches verrouillées")
                        portfolio_mode = gr.Radio(["Libre","Fixe","Linéaire","Manuel"], value="Libre", label="Mode de cible portefeuille")
                        with gr.Row():
                            portfolio_ex_start = gr.Number(label="S/P exercice départ (%)", precision=3)
                            portfolio_ex_end = gr.Number(label="S/P exercice atterrissage (%)", precision=3)
                            portfolio_global_start = gr.Number(label="S/P global départ (%)", precision=3)
                            portfolio_global_end = gr.Number(label="S/P global atterrissage (%)", precision=3)
                        with gr.Accordion("Cibles mensuelles manuelles", open=False):
                            portfolio_manual = gr.Dataframe(value=blank_portfolio_manual(), headers=["Mois","S/P exercice cible (%)","S/P global cible (%)"], interactive=True, row_count=(12,"fixed"), column_count=(3,"fixed"), label="Cibles mensuelles")
                        sp_portfolio = gr.Dataframe(interactive=False, elem_classes="matrix", label="Cible, niveau atteint & résultat portefeuille")
                        with gr.Accordion("Matrices portefeuille", open=False):
                            sp_ex_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="S/P exercice (%)")
                            sp_global_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="S/P global (%)")
                            charge_ex_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Charge exercice")
                            charge_prior_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Charge antérieurs")
                            charge_global_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Charge globale")
                            technical_result_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Résultat technique avant FG")
                    with gr.Tab("Paramètres avancés"):
                        with gr.Row():
                            sp_ex_settings = gr.Dataframe(value=blank_sp_settings(), headers=SP_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Trajectoire S/P exercice")
                            sp_global_settings = gr.Dataframe(value=blank_sp_settings(), headers=SP_SETTING_COLS, interactive=True, elem_classes="rate-settings", label="Trajectoire S/P global")
                        with gr.Accordion("Ajustements mensuels", open=False):
                            with gr.Row():
                                sp_ex_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="S/P exercice (%)")
                                sp_global_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="S/P global (%)")

            with gr.Tab("FG & Financier"):
                gr.Markdown("### Frais généraux & Financier", elem_classes="section-title")
                with gr.Tabs():
                    with gr.Tab("Vue branche"):
                        fg_summary = gr.HTML()
                        fg_chart = gr.Plot(label="Frais généraux, financier & résultat")
                        fg_branch_table = gr.Dataframe(interactive=False, elem_classes="prime-result", label="Branche sélectionnée · 12 mois")
                    with gr.Tab("Vue portefeuille"):
                        with gr.Tabs():
                            with gr.Tab("Taux FG"):
                                fg_rate_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Taux FG (%)")
                                fg_total_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Frais généraux")
                            with gr.Tab("Résultat"):
                                result_after_fg_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Résultat technique après FG")
                                result_after_fin_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Résultat après financier")
                            with gr.Tab("Financier"):
                                financial_products_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Produits financiers")
                                financial_charges_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Charges financières")
                                financial_net_grid = gr.Dataframe(headers=MONTH_GRID_COLS, interactive=False, elem_classes="matrix", label="Résultat financier net")
                    with gr.Tab("Paramètres avancés"):
                        with gr.Accordion("Pilotage du taux de frais généraux", open=True):
                            fg_rate_settings = gr.Dataframe(value=blank_fg_rate_settings(), headers=FG_RATE_COLS, interactive=True, elem_classes="rate-settings", label="Fixe / Linéaire / Manuel")
                            fg_rate_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Ajustements mensuels du taux FG (%)")
                        with gr.Accordion("Ajustements du financier", open=False):
                            with gr.Row():
                                pf_product_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Produits financiers")
                                pf_charge_manual = gr.Dataframe(value=blank_month_matrix(), headers=MONTH_GRID_COLS, interactive=True, elem_classes="matrix", label="Charges financières")

            with gr.Tab("Synthèse"):
                gr.Markdown("### Vue décisionnelle du portefeuille", elem_classes="section-title")
                gr.Markdown("Une lecture unique après primes, sinistres, commissions, frais généraux et financier. Utilisez les autres onglets pour agir sur les hypothèses.", elem_classes="muted")
                fg_portfolio = gr.Dataframe(interactive=False, elem_classes="matrix", label="Synthèse mensuelle consolidée")

            with gr.Tab("Contrôles"):
                gr.Markdown("### Alertes & diagnostics métier", elem_classes="section-title")
                gr.Markdown("Les écrans métier restent volontairement sobres. Les détails de contrôle sont centralisés ici.", elem_classes="muted")
                with gr.Accordion("Primes / REC / Commissions", open=True):
                    diagnostics = gr.Dataframe(headers=["Diagnostic"], interactive=False)
                with gr.Accordion("S/P & Charges", open=False):
                    sp_diagnostics = gr.Dataframe(headers=["Diagnostic"], interactive=False)
                with gr.Accordion("Frais généraux & Financier", open=False):
                    fg_diagnostics = gr.Dataframe(headers=["Diagnostic"], interactive=False)

        # ---------- calculs ----------
        load_outputs = [hist_n3,hist_n2,hist_n1,anchors,commission_anchors,cession_hist,rec_direct_hist,rec_reass_local_hist,rec_reass_ifrs_hist,fg_start,fg_end,pf_start,pf_end,load_status]
        load_ev = load_btn.click(load_template, inputs=[upload], outputs=load_outputs)

        inputs = [
            hist_n3,hist_n2,hist_n1,anchors,gross_manual,
            cession_settings,cession_hist,cession_manual,
            rec_direct_settings,rec_direct_hist,rec_direct_manual,
            rec_reass_local_settings,rec_reass_local_hist,rec_reass_local_manual,
            rec_reass_ifrs_settings,rec_reass_ifrs_hist,rec_reass_ifrs_manual,
            view,selected_branch,commission_anchors,
            direct_commission_settings,direct_commission_manual,
            reass_commission_settings,reass_commission_manual,
            direct_dac_settings,direct_dac_manual,reass_dac_settings,reass_dac_manual,
        ]
        outputs = [
            summary,cession_landing,chart,gross_grid,cession_grid,ceded_grid,net_grid,
            rec_direct_rate_grid,rec_direct_var_grid,rec_direct_close_grid,direct_earned_grid,
            rec_reass_rate_grid,rec_reass_var_grid,rec_reass_close_grid,reass_earned_grid,net_earned_grid,
            commission_summary,commission_landing,commission_chart,
            direct_commission_rate_grid,direct_commission_grid,reass_commission_rate_grid,reass_commission_grid,cpc_commission_rate_grid,
            direct_dac_rate_grid,direct_dac_open_grid,direct_dac_close_grid,direct_dac_var_grid,
            reass_dac_rate_grid,reass_dac_open_grid,reass_dac_close_grid,reass_dac_var_grid,
            diagnostics,reference_note,branch_kpis,branch_editor,branch_reference,branch_result,commission_branch_table,
        ]
        sp_inputs = [
            net_earned_grid,direct_commission_grid,reass_commission_grid,direct_dac_var_grid,view,selected_branch,selected_month,
            sp_ex_settings,sp_global_settings,sp_ex_manual,sp_global_manual,locked_branches,
            portfolio_mode,portfolio_ex_start,portfolio_ex_end,portfolio_global_start,portfolio_global_end,portfolio_manual,
        ]
        sp_outputs = [
            sp_summary,sp_chart,sp_branch_result,sp_ex_grid,sp_global_grid,charge_ex_grid,charge_prior_grid,
            charge_global_grid,technical_result_grid,sp_portfolio,sp_diagnostics,sp_branch_editor,sp_branch_reference,
        ]
        fg_inputs = [
            net_earned_grid,technical_result_grid,selected_branch,selected_month,view,
            fg_start,fg_end,fg_rate_settings,fg_rate_manual,pf_start,pf_end,pf_product_manual,pf_charge_manual,
        ]
        fg_outputs = [
            persistent_kpis,fg_summary,fg_chart,fg_branch_table,fg_rate_grid,fg_total_grid,result_after_fg_grid,
            financial_products_grid,financial_charges_grid,financial_net_grid,result_after_fin_grid,fg_portfolio,fg_diagnostics,
        ]

        def full_chain(ev):
            return ev.then(run_projection, inputs=inputs, outputs=outputs).then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs).then(run_fg_projection, inputs=fg_inputs, outputs=fg_outputs)
        def sp_chain(ev):
            return ev.then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs).then(run_fg_projection, inputs=fg_inputs, outputs=fg_outputs)

        full_chain(load_ev)
        full_chain(recalc.click(lambda: None, inputs=None, outputs=None))
        full_chain(view.change(lambda: None, inputs=None, outputs=None))
        full_chain(selected_branch.change(lambda: None, inputs=None, outputs=None))
        sp_chain(selected_month.change(lambda: None, inputs=None, outputs=None))

        # Feedback immédiat sur les hypothèses éditées par l'utilisateur.
        # .input limite ces recalculs aux interactions utilisateur et évite les cascades
        # lors du chargement programmatique du classeur.
        for comp in [
            hist_n3,hist_n2,hist_n1,anchors,
            cession_settings,cession_hist,cession_manual,
            rec_direct_settings,rec_direct_hist,rec_direct_manual,
            rec_reass_local_settings,rec_reass_local_hist,rec_reass_local_manual,
            rec_reass_ifrs_settings,rec_reass_ifrs_hist,rec_reass_ifrs_manual,
            direct_commission_settings,direct_commission_manual,
            reass_commission_settings,reass_commission_manual,
            direct_dac_settings,direct_dac_manual,reass_dac_settings,reass_dac_manual,
        ]:
            full_chain(comp.input(lambda: None, inputs=None, outputs=None))

        full_chain(apply_branch_edits.click(
            apply_branch_table,
            [branch_editor,branch_reference,selected_branch,view,gross_manual,cession_manual,rec_direct_manual,rec_reass_local_manual,rec_reass_ifrs_manual],
            [gross_manual,cession_manual,rec_direct_manual,rec_reass_local_manual,rec_reass_ifrs_manual],
        ))
        full_chain(reset_branch_edits.click(
            reset_branch_overrides,
            [selected_branch,gross_manual,cession_manual,rec_direct_manual,rec_reass_local_manual,rec_reass_ifrs_manual],
            [gross_manual,cession_manual,rec_direct_manual,rec_reass_local_manual,rec_reass_ifrs_manual],
        ))

        full_chain(apply_direct_commission.click(apply_point_override, [direct_commission_manual,commission_point_branch,commission_point_month,direct_commission_override], [direct_commission_manual]))
        full_chain(apply_reass_commission.click(apply_point_override, [reass_commission_manual,commission_point_branch,commission_point_month,reass_commission_override], [reass_commission_manual]))
        def clear_comm_point(dc, rc, branch, month):
            return clear_point_override(dc,branch,month), clear_point_override(rc,branch,month)
        full_chain(clear_commission_point.click(clear_comm_point,[direct_commission_manual,reass_commission_manual,commission_point_branch,commission_point_month],[direct_commission_manual,reass_commission_manual]))

        # S/P changes: charges then FG/financial.
        for comp in [locked_branches,portfolio_mode,portfolio_ex_start,portfolio_ex_end,portfolio_global_start,portfolio_global_end,
                     sp_ex_settings,sp_global_settings,portfolio_manual,sp_ex_manual,sp_global_manual]:
            sp_chain(comp.change(lambda: None, inputs=None, outputs=None))
        sp_chain(apply_sp_edits.click(apply_sp_branch_editor,[sp_branch_editor,sp_branch_reference,selected_branch,sp_ex_manual,sp_global_manual],[sp_ex_manual,sp_global_manual]))
        sp_chain(reset_sp_edits.click(reset_sp_branch,[selected_branch,sp_ex_manual,sp_global_manual],[sp_ex_manual,sp_global_manual]))

        # FG / financier ne nécessite pas de recalcul des modules précédents.
        for comp in [fg_start,fg_end,fg_rate_settings,fg_rate_manual,pf_start,pf_end,pf_product_manual,pf_charge_manual]:
            comp.change(run_fg_projection, inputs=fg_inputs, outputs=fg_outputs)

        demo.load(run_projection, inputs=inputs, outputs=outputs).then(run_sp_projection, inputs=sp_inputs, outputs=sp_outputs).then(run_fg_projection, inputs=fg_inputs, outputs=fg_outputs)
    return demo


if __name__ == "__main__":
    app = build_app()
    app.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", "7860")), show_error=True, theme=THEME, css=CSS)
