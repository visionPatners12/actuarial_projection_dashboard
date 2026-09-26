from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

BRANCHES = [
    "Automobile", "Santé", "Accident corporel", "Incendie",
    "BDM - Construction", "RC - RC Déc", "RD", "Transport",
]
MONTHS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


@dataclass
class ProjectionResult:
    table: pd.DataFrame
    diagnostics: pd.DataFrame
    historical_profile: np.ndarray


def _finite(v, default=np.nan):
    try:
        x = float(v)
        return x if np.isfinite(x) else default
    except Exception:
        return default


def _as12(values: Optional[Sequence[float]]) -> np.ndarray:
    if values is None:
        return np.full(12, np.nan, dtype=float)
    a = np.asarray(list(values), dtype=float).reshape(-1)
    if len(a) < 12:
        a = np.r_[a, np.full(12-len(a), np.nan)]
    return a[:12]


def _clean_ytd(ytd: Sequence[float]) -> Tuple[np.ndarray, List[str]]:
    """Nettoie une série YTD uniquement pour construire le profil historique.

    Les données originales ne sont jamais modifiées dans l'interface. Pour le profil,
    les trous sont interpolés et les baisses cumulées sont neutralisées afin qu'une
    anomalie de saisie ne crée pas un poids mensuel négatif.
    """
    a = _as12(ytd)
    diags: List[str] = []
    s = pd.Series(a, dtype=float)
    if s.notna().sum() == 0:
        return np.full(12, np.nan), ["Historique vide"]
    s = s.interpolate(limit_direction="both")
    arr = s.to_numpy(float)
    if np.any(np.diff(arr) < -1e-9):
        diags.append("Historique cumulatif décroissant : baisses neutralisées pour estimer le profil")
        arr = np.maximum.accumulate(arr)
    if arr[-1] <= 0:
        diags.append("Atterrissage historique nul ou négatif")
        return np.full(12, np.nan), diags
    return arr, diags


def robust_increment_profile(histories: Sequence[Sequence[float]]) -> Tuple[np.ndarray, List[str]]:
    """Profil mensuel robuste, sans pondération arbitraire N-1/N-2/N-3.

    Chaque année est transformée en parts d'incréments mensuels. La médiane mois par
    mois est utilisée puis renormalisée. Avec une seule année, son profil est repris.
    """
    shares = []
    diags: List[str] = []
    for k, h in enumerate(histories):
        arr, d = _clean_ytd(h)
        diags += [f"Historique {k+1}: {x}" for x in d]
        if np.isnan(arr).all():
            continue
        inc = np.diff(np.r_[0.0, arr])
        inc = np.clip(inc, 0.0, None)
        total = inc.sum()
        if total > 1e-12:
            shares.append(inc / total)
    if not shares:
        return np.full(12, 1/12), diags + ["Aucun profil exploitable : profil uniforme utilisé"]
    m = np.nanmedian(np.vstack(shares), axis=0)
    m = np.clip(m, 0.0, None)
    if m.sum() <= 1e-12:
        m = np.full(12, 1/12)
    else:
        m = m / m.sum()
    return m, diags


def _project_from_profile(
    profile: Sequence[float],
    landing: float,
    departure: Optional[float] = None,
    anchors: Optional[Mapping[int, float]] = None,
) -> Tuple[np.ndarray, List[str]]:
    """Projette un cumul YTD en respectant exactement les ancres et l'atterrissage.

    anchors utilise des indices 0..11. Entre deux ancres, l'écart est réparti selon
    le profil historique des incréments. Toute ancre incompatible est bornée pour
    conserver une série cumulative non décroissante.
    """
    w = np.asarray(profile, dtype=float)
    w = np.clip(w, 0.0, None)
    if w.sum() <= 1e-12:
        w[:] = 1/12
    else:
        w /= w.sum()
    target = max(0.0, _finite(landing, 0.0))
    pts: Dict[int, float] = {}
    if departure is not None and np.isfinite(_finite(departure)):
        pts[0] = max(0.0, _finite(departure, 0.0))
    if anchors:
        for k, v in anchors.items():
            if 0 <= int(k) <= 11 and np.isfinite(_finite(v)):
                pts[int(k)] = max(0.0, _finite(v, 0.0))
    pts[11] = target

    diags: List[str] = []
    ordered = sorted(pts.items())
    # Clamp anchors sequentially so they are monotone and cannot exceed landing.
    last = 0.0
    fixed: List[Tuple[int, float]] = []
    for month, val in ordered:
        bounded = min(target, max(last, val)) if month < 11 else target
        if abs(bounded-val) > 1e-6:
            diags.append(f"Ancre {MONTHS[month]} bornée de {val:,.0f} à {bounded:,.0f} pour préserver le cumul")
        fixed.append((month, bounded))
        last = bounded

    out = np.zeros(12, dtype=float)
    prev_m = -1
    prev_v = 0.0
    for m, v in fixed:
        seg = np.arange(prev_m+1, m+1)
        delta = max(0.0, v-prev_v)
        sw = w[seg]
        if sw.sum() <= 1e-12:
            sw = np.full(len(seg), 1/len(seg))
        else:
            sw = sw/sw.sum()
        inc = delta*sw
        vals = prev_v + np.cumsum(inc)
        out[seg] = vals
        out[m] = v
        prev_m, prev_v = m, v
    # Defensive monotonicity / exact landing.
    out = np.maximum.accumulate(out)
    out[-1] = target
    return out, diags


def rate_curve(
    mode: str,
    fixed: Optional[float] = None,
    start: Optional[float] = None,
    end: Optional[float] = None,
    historical: Optional[Sequence[float]] = None,
    manual: Optional[Sequence[float]] = None,
    margin_down: float = 0.0,
    margin_up: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """Construit une trajectoire de taux en pourcentage.

    Retourne (taux final, borne basse, borne haute, diagnostics).
    Le mode fixe/linéaire donne une base ; une valeur mensuelle manuelle la remplace.
    En mode linéaire, la surcharge est bornée par les marges +/- indiquées.
    """
    mode = (mode or "Linéaire").strip().lower()
    hist = _as12(historical)
    man = _as12(manual)
    valid_hist = hist[np.isfinite(hist)]
    hist_default = float(np.nanmedian(valid_hist)) if len(valid_hist) else 0.0
    end_v = _finite(end, hist[-1] if np.isfinite(hist[-1]) else hist_default)
    start_v = _finite(start, hist[0] if np.isfinite(hist[0]) else end_v)
    fixed_v = _finite(fixed, end_v)

    if mode.startswith("fix"):
        base = np.full(12, fixed_v, dtype=float)
        lo = np.full(12, -np.inf)
        hi = np.full(12, np.inf)
    elif mode.startswith("man"):
        if np.isfinite(hist).any():
            base = pd.Series(hist).interpolate(limit_direction="both").fillna(hist_default).to_numpy(float)
        else:
            base = np.linspace(start_v, end_v, 12)
        lo = np.full(12, -np.inf)
        hi = np.full(12, np.inf)
    else:
        base = np.linspace(start_v, end_v, 12)
        lo = base - max(0.0, _finite(margin_down, 0.0))
        hi = base + max(0.0, _finite(margin_up, 0.0))

    final = base.copy()
    diags: List[str] = []
    for i, v in enumerate(man):
        if not np.isfinite(v):
            continue
        vv = float(v)
        if not mode.startswith("fix") and not mode.startswith("man"):
            bounded = float(np.clip(vv, lo[i], hi[i]))
            if abs(bounded-vv) > 1e-9:
                diags.append(f"{MONTHS[i]} : taux manuel {vv:.2f}% borné à {bounded:.2f}% par la marge")
            vv = bounded
        final[i] = vv
    # Rate can be negative for REC variation, but cession caller will constrain separately.
    return final, lo, hi, diags


def _enforce_ceded_monotone(gross: np.ndarray, rate_pct: np.ndarray) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    proposed = gross*np.clip(rate_pct/100.0, 0.0, 1.5)
    actual = proposed.copy()
    diags = []
    for i in range(12):
        floor = actual[i-1] if i else 0.0
        cap = gross[i]
        bounded = min(cap, max(floor, actual[i]))
        if abs(bounded-actual[i]) > 1e-6:
            diags.append(f"{MONTHS[i]} : prime cédée ajustée pour rester cumulative et ≤ prime brute")
        actual[i] = bounded
    actual_rate = np.divide(actual, gross, out=np.zeros(12), where=np.abs(gross)>1e-12)*100.0
    return actual, actual_rate, diags


def _rec_block(premium_ytd: np.ndarray, opening: float, rate_pct: np.ndarray, label: str) -> Tuple[np.ndarray,np.ndarray,np.ndarray,np.ndarray,List[str]]:
    """REC pilotée par sa VARIATION : variation = prime cumulée × taux.

    clôture = ouverture fixe + variation
    prime acquise YTD = prime YTD + ouverture - clôture = prime YTD - variation
    """
    opening = max(0.0, _finite(opening, 0.0))
    var = premium_ytd*(rate_pct/100.0)
    close = opening + var
    earned = premium_ytd - var
    diags = []
    for i in range(12):
        # REC closing cannot be negative.
        if close[i] < 0:
            var[i] = -opening
            close[i] = 0.0
            earned[i] = premium_ytd[i]-var[i]
            diags.append(f"{label} {MONTHS[i]} : REC clôture bornée à 0")
        # Earned cumulative should not fall.
        if i and earned[i] < earned[i-1]-1e-6:
            max_var = premium_ytd[i]-earned[i-1]
            var[i] = max(-opening, max_var)
            close[i] = opening+var[i]
            earned[i] = premium_ytd[i]-var[i]
            diags.append(f"{label} {MONTHS[i]} : variation REC ajustée pour préserver la prime acquise cumulative")
    actual_rate = np.divide(var, premium_ytd, out=np.zeros(12), where=np.abs(premium_ytd)>1e-12)*100.0
    return var, close, earned, actual_rate, diags


def project_branch(
    histories_gross: Sequence[Sequence[float]],
    gross_landing: float,
    reass_landing: Optional[float],
    gross_departure: Optional[float] = None,
    gross_manual_anchors: Optional[Mapping[int,float]] = None,
    cession_config: Optional[Mapping] = None,
    rec_direct_config: Optional[Mapping] = None,
    rec_reass_local_config: Optional[Mapping] = None,
    rec_reass_ifrs_config: Optional[Mapping] = None,
    rec_open_direct_cima72: float = 0.0,
    rec_open_reass_cima72: float = 0.0,
    rec_open_reass_ifrs100: float = 0.0,
    direct_commission_config: Optional[Mapping] = None,
    reass_commission_config: Optional[Mapping] = None,
    direct_dac_config: Optional[Mapping] = None,
    reass_dac_config: Optional[Mapping] = None,
    dac_open_direct_ifrs: Optional[float] = None,
    dac_open_reass_ifrs: Optional[float] = None,
) -> ProjectionResult:
    profile, pdiag = robust_increment_profile(histories_gross)
    gross, gdiag = _project_from_profile(profile, gross_landing, gross_departure, gross_manual_anchors)

    implied_cession = 0.0
    if gross_landing and reass_landing is not None:
        implied_cession = 100.0*_finite(reass_landing,0.0)/max(_finite(gross_landing,0.0),1e-12)

    cession_config = dict(cession_config or {})
    if cession_config.get("end") is None:
        cession_config["end"] = implied_cession
    if cession_config.get("fixed") is None:
        cession_config["fixed"] = implied_cession
    cession_rate, cess_lo, cess_hi, cdiag = rate_curve(**cession_config)
    ceded, cession_rate_actual, cmon = _enforce_ceded_monotone(gross, cession_rate)
    net = gross-ceded

    rec_direct_config = dict(rec_direct_config or {})
    rec_reass_local_config = dict(rec_reass_local_config or {})
    rec_reass_ifrs_config = dict(rec_reass_ifrs_config or {})
    rd_rate, rd_lo, rd_hi, rddiag = rate_curve(**rec_direct_config)
    rr_rate, rr_lo, rr_hi, rrdiag = rate_curve(**rec_reass_local_config)
    ri_rate, ri_lo, ri_hi, ridiag = rate_curve(**rec_reass_ifrs_config)

    dvar, dclose, dearn, rd_actual, drecdiag = _rec_block(gross, rec_open_direct_cima72, rd_rate, "REC Direct CIMA 72%")
    rvar, rclose, rearn, rr_actual, rrecdiag = _rec_block(ceded, rec_open_reass_cima72, rr_rate, "REC Réassurance Local")

    # Direct IFRS follows pd.xlsx: REC prorata = REC CIMA 72% / 72%.
    direct_ifrs_open = max(0.0, _finite(rec_open_direct_cima72,0.0))/0.72
    direct_ifrs_var = dvar/0.72
    direct_ifrs_close = direct_ifrs_open + direct_ifrs_var
    direct_ifrs_earned = gross-direct_ifrs_var

    # Reass IFRS uses its own REC 100% variation rate, as requested.
    rivar, riclose, riearn, ri_actual, rirecdiag = _rec_block(ceded, rec_open_reass_ifrs100, ri_rate, "REC Réassurance IFRS 100%")

    local_net_earned = dearn-rearn
    ifrs_net_earned = direct_ifrs_earned-riearn

    # Commissions. Le Direct reste piloté par son taux de commission sur prime brute.
    # La Réassurance dépend désormais du Direct :
    # Commission Réassurance = Commission Direct × taux de récupération de commission.
    # Le taux de commission Réassurance / prime cédée devient un indicateur dérivé.
    direct_commission_config = dict(direct_commission_config or {"mode":"Fixe", "fixed":0.0})
    reass_commission_config = dict(reass_commission_config or {"mode":"Fixe", "fixed":0.0})
    if "mode" not in direct_commission_config: direct_commission_config["mode"] = "Fixe"
    if "mode" not in reass_commission_config: reass_commission_config["mode"] = "Fixe"
    dc_rate, dc_lo, dc_hi, dcdiag = rate_curve(**direct_commission_config)
    recovery_rate, rc_lo, rc_hi, rcdiag = rate_curve(**reass_commission_config)
    if np.any(recovery_rate < 0):
        rcdiag.append("Taux de récupération de commission Réassurance négatif : borné à 0%")
        recovery_rate = np.maximum(recovery_rate, 0.0)
    direct_commission = gross * (dc_rate / 100.0)
    reass_commission = direct_commission * (recovery_rate / 100.0)
    reass_effective_rate = np.divide(
        reass_commission, ceded, out=np.zeros(12), where=np.abs(ceded) > 1e-12
    ) * 100.0

    # IFRS DAC follows pd.xlsx: DAC = REC 100% × DAC rate; Var DAC = DAC Ouv - DAC Clo.
    # The opening DAC is kept fixed for the year, consistent with the annual-opening rule.
    direct_dac_config = dict(direct_dac_config or {"mode":"Fixe", "fixed":0.0})
    reass_dac_config = dict(reass_dac_config or {"mode":"Fixe", "fixed":0.0})
    if "mode" not in direct_dac_config: direct_dac_config["mode"] = "Fixe"
    if "mode" not in reass_dac_config: reass_dac_config["mode"] = "Fixe"
    dd_rate, dd_lo, dd_hi, dddiag = rate_curve(**direct_dac_config)
    rr_dac_rate, rr_dac_lo, rr_dac_hi, rrdd = rate_curve(**reass_dac_config)
    dd_open = _finite(dac_open_direct_ifrs, np.nan)
    if not np.isfinite(dd_open):
        dd_open = direct_ifrs_open * (dd_rate[0] / 100.0)
    rdac_open = _finite(dac_open_reass_ifrs, np.nan)
    if not np.isfinite(rdac_open):
        rdac_open = max(0.0, _finite(rec_open_reass_ifrs100, 0.0)) * (rr_dac_rate[0] / 100.0)
    direct_dac_open = np.full(12, dd_open, dtype=float)
    reass_dac_open = np.full(12, rdac_open, dtype=float)
    direct_dac_close = direct_ifrs_close * (dd_rate / 100.0)
    reass_dac_close = riclose * (rr_dac_rate / 100.0)
    direct_var_dac = direct_dac_open - direct_dac_close
    reass_var_dac = reass_dac_open - reass_dac_close

    # CPC net commission identity reconciled from pd.xlsx.
    # Local: Direct commission - Reass commission, over net earned premium.
    # IFRS: Direct commission + Direct Var DAC - Reass commission, over net earned premium.
    cpc_commission_local = direct_commission - reass_commission
    cpc_commission_ifrs = direct_commission + direct_var_dac - reass_commission
    cpc_rate_local = np.divide(cpc_commission_local, local_net_earned, out=np.full(12, np.nan), where=np.abs(local_net_earned)>1e-12) * 100.0
    cpc_rate_ifrs = np.divide(cpc_commission_ifrs, ifrs_net_earned, out=np.full(12, np.nan), where=np.abs(ifrs_net_earned)>1e-12) * 100.0

    table = pd.DataFrame({
        "Mois": MONTHS,
        "Prime brute": gross,
        "Taux cession cible (%)": np.full(12, implied_cession),
        "Taux cession (%)": cession_rate_actual,
        "Prime réassurance": ceded,
        "Prime nette": net,
        "Taux variation REC Direct (%)": rd_actual,
        "Variation REC Direct CIMA 72%": dvar,
        "REC ouverture Direct CIMA 72%": np.full(12, max(0.0,_finite(rec_open_direct_cima72,0.0))),
        "REC clôture Direct CIMA 72%": dclose,
        "Prime acquise Direct Local": dearn,
        "REC ouverture Direct prorata": np.full(12, direct_ifrs_open),
        "REC clôture Direct prorata": direct_ifrs_close,
        "Variation REC Direct prorata": direct_ifrs_var,
        "Prime acquise Direct IFRS": direct_ifrs_earned,
        "Taux variation REC Réass Local (%)": rr_actual,
        "Variation REC Réass Local": rvar,
        "REC ouverture Réass Local": np.full(12,max(0.0,_finite(rec_open_reass_cima72,0.0))),
        "REC clôture Réass Local": rclose,
        "Prime acquise Réass Local": rearn,
        "Taux variation REC Réass IFRS (%)": ri_actual,
        "Variation REC Réass IFRS 100%": rivar,
        "REC ouverture Réass IFRS 100%": np.full(12,max(0.0,_finite(rec_open_reass_ifrs100,0.0))),
        "REC clôture Réass IFRS 100%": riclose,
        "Prime acquise Réass IFRS": riearn,
        "Prime acquise nette Local": local_net_earned,
        "Prime acquise nette IFRS": ifrs_net_earned,
        "Taux commission Direct (%)": dc_rate,
        "Commission Direct": direct_commission,
        "Taux récupération commission Réassurance (%)": recovery_rate,
        "Taux commission Réassurance effectif (%)": reass_effective_rate,
        "Commission Réassurance": reass_commission,
        "Taux DAC Direct IFRS (%)": dd_rate,
        "DAC ouverture Direct IFRS": direct_dac_open,
        "DAC clôture Direct IFRS": direct_dac_close,
        "Variation DAC Direct IFRS": direct_var_dac,
        "Taux DAC Réassurance IFRS (%)": rr_dac_rate,
        "DAC ouverture Réassurance IFRS": reass_dac_open,
        "DAC clôture Réassurance IFRS": reass_dac_close,
        "Variation DAC Réassurance IFRS": reass_var_dac,
        "Commission nette CPC Local": cpc_commission_local,
        "Commission nette CPC IFRS": cpc_commission_ifrs,
        "Taux commission CPC Local (%)": cpc_rate_local,
        "Taux commission CPC IFRS (%)": cpc_rate_ifrs,
    })

    diags = pdiag+gdiag+cdiag+cmon+rddiag+rrdiag+ridiag+dcdiag+rcdiag+dddiag+rrdd+drecdiag+rrecdiag+rirecdiag
    # Landing reconciliation diagnostics.
    if reass_landing is not None:
        gap=ceded[-1]-_finite(reass_landing,0.0)
        if abs(gap) > max(1.0, abs(_finite(reass_landing,0.0))*1e-6):
            diags.append(f"Atterrissage Réassurance : écart de {gap:,.0f} par rapport à la cible, lié au taux de cession retenu")
    if np.any(table["Prime acquise nette Local"].to_numpy()[1:] < table["Prime acquise nette Local"].to_numpy()[:-1]-1e-6):
        diags.append("Prime acquise nette Local décroissante sur au moins un mois")
    if np.any(table["Prime acquise nette IFRS"].to_numpy()[1:] < table["Prime acquise nette IFRS"].to_numpy()[:-1]-1e-6):
        diags.append("Prime acquise nette IFRS décroissante sur au moins un mois")

    diag_df = pd.DataFrame({"Diagnostic": diags}) if diags else pd.DataFrame({"Diagnostic":["Aucune incohérence détectée"]})
    return ProjectionResult(table=table, diagnostics=diag_df, historical_profile=profile)


def stress_random(seed: int = 1234, scenarios: int = 500) -> pd.DataFrame:
    """Stress-test interne du moteur primes."""
    rng=np.random.default_rng(seed)
    rows=[]
    for s in range(int(scenarios)):
        n_hist=int(rng.integers(1,4))
        histories=[]
        for _ in range(n_hist):
            base=rng.uniform(2e8,2e9)
            increments=rng.lognormal(mean=0.0,sigma=0.55,size=12)
            increments=increments/increments.sum()*base
            histories.append(np.cumsum(increments))
        target=float(histories[-1][-1]*rng.uniform(0.7,1.5))
        reass_target=target*rng.uniform(0.05,0.65)
        start=max(0.0,target*rng.uniform(0.02,0.12))
        res=project_branch(
            histories,target,reass_target,start,
            cession_config={"mode":"Linéaire","start":rng.uniform(5,50),"end":100*reass_target/target,"margin_down":5,"margin_up":5},
            rec_direct_config={"mode":"Linéaire","start":rng.uniform(-10,25),"end":rng.uniform(-10,25),"margin_down":5,"margin_up":5},
            rec_reass_local_config={"mode":"Fixe","fixed":rng.uniform(-10,25)},
            rec_reass_ifrs_config={"mode":"Fixe","fixed":rng.uniform(-10,25)},
            rec_open_direct_cima72=rng.uniform(0,0.25*target),
            rec_open_reass_cima72=rng.uniform(0,0.25*reass_target),
            rec_open_reass_ifrs100=rng.uniform(0,0.35*reass_target),
        )
        t=res.table
        ok=(
            abs(t["Prime brute"].iloc[-1]-target)<1e-4
            and np.all(np.diff(t["Prime brute"])>=-1e-6)
            and np.all(np.diff(t["Prime réassurance"])>=-1e-6)
            and np.all(t["Prime réassurance"]<=t["Prime brute"]+1e-6)
            and np.all(t["REC clôture Direct CIMA 72%"]>=-1e-6)
            and np.all(t["REC clôture Réass Local"]>=-1e-6)
            and np.all(t["REC clôture Réass IFRS 100%"]>=-1e-6)
            and np.all(np.diff(t["Prime acquise Direct Local"])>=-1e-6)
            and np.all(np.diff(t["Prime acquise Réass Local"])>=-1e-6)
        )
        rows.append({"scenario":s+1,"hist_years":n_hist,"ok":bool(ok),"diagnostics":len(res.diagnostics)})
    return pd.DataFrame(rows)
