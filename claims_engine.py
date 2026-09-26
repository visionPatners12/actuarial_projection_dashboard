from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from prime_engine import BRANCHES, MONTHS

SP_SETTING_COLS = [
    "Branche", "Mode", "Départ (%)", "Atterrissage (%)",
    "Marge baisse (pts)", "Marge hausse (pts)",
]


def _num(v, default=np.nan):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
            return default
        x = float(str(v).replace(" ", "").replace(",", "."))
        return x if np.isfinite(x) else default
    except Exception:
        return default


def blank_sp_settings(default_start=np.nan, default_end=np.nan) -> pd.DataFrame:
    return pd.DataFrame([
        [b, "Linéaire", default_start, default_end, 5.0, 5.0] for b in BRANCHES
    ], columns=SP_SETTING_COLS)


def blank_month_matrix(value=np.nan) -> pd.DataFrame:
    d = {"Mois": MONTHS}
    for b in BRANCHES:
        d[b] = [value] * 12
    return pd.DataFrame(d)


def blank_portfolio_manual() -> pd.DataFrame:
    return pd.DataFrame({
        "Mois": MONTHS,
        "S/P exercice cible (%)": [np.nan] * 12,
        "S/P global cible (%)": [np.nan] * 12,
    })


def _setting_row(settings, branch: str) -> pd.Series:
    d = pd.DataFrame(settings).copy()
    if "Branche" in d.columns:
        m = d[d["Branche"].astype(str).str.strip() == branch]
        if not m.empty:
            return m.iloc[0]
    return pd.Series(dtype=object)


def _matrix_col(df, branch: str) -> np.ndarray:
    d = pd.DataFrame(df).copy()
    if branch not in d.columns:
        return np.full(12, np.nan)
    vals = [_num(v) for v in d[branch].tolist()[:12]]
    if len(vals) < 12:
        vals += [np.nan] * (12 - len(vals))
    return np.asarray(vals, dtype=float)


def build_sp_path(settings, manual, branch: str, default_start: float = 60.0, default_end: float = 60.0):
    """Return baseline, low, high, hard_mask for a branch.

    - Fixe: constant at Atterrissage (or Départ/default if missing).
    - Linéaire: interpolation Départ -> Atterrissage.
    - Manuel: linear fallback; monthly manual values can override any mode.
    - Margins define the portfolio optimizer's admissible band.
    - A manual monthly value is a hard constraint (low=high=value).
    """
    r = _setting_row(settings, branch)
    mode = str(r.get("Mode", "Linéaire") or "Linéaire").strip().lower()
    start = _num(r.get("Départ (%)"), default_start)
    end = _num(r.get("Atterrissage (%)"), default_end)
    if not np.isfinite(start): start = default_start
    if not np.isfinite(end): end = start if np.isfinite(start) else default_end
    md = max(0.0, _num(r.get("Marge baisse (pts)"), 0.0))
    mu = max(0.0, _num(r.get("Marge hausse (pts)"), 0.0))

    if mode.startswith("fix"):
        value = end if np.isfinite(end) else start
        base = np.full(12, value, dtype=float)
    else:
        base = np.linspace(start, end, 12)

    lo = base - md
    hi = base + mu
    # Exercise/global S/P can technically become negative because of reserve releases,
    # so we do not impose an artificial zero floor here.
    man = _matrix_col(manual, branch)
    hard = np.zeros(12, dtype=bool)
    for i, v in enumerate(man):
        if np.isfinite(v):
            base[i] = v
            lo[i] = v
            hi[i] = v
            hard[i] = True
    return base, lo, hi, hard


def build_portfolio_target(mode: str, start: Optional[float], end: Optional[float], manual, column: str) -> np.ndarray:
    mode_l = str(mode or "Libre").strip().lower()
    if mode_l.startswith("lib"):
        return np.full(12, np.nan)
    s = _num(start, np.nan)
    e = _num(end, np.nan)
    if not np.isfinite(s) and np.isfinite(e): s = e
    if not np.isfinite(e) and np.isfinite(s): e = s
    if not np.isfinite(s) and not np.isfinite(e):
        base = np.full(12, np.nan)
    elif mode_l.startswith("fix"):
        base = np.full(12, e, dtype=float)
    else:
        base = np.linspace(s, e, 12)
    if mode_l.startswith("man"):
        # Manual mode can still use start/end as fallback.
        pass
    d = pd.DataFrame(manual).copy()
    if column in d.columns:
        vals = [_num(v) for v in d[column].tolist()[:12]]
        vals += [np.nan] * max(0, 12-len(vals))
        for i, v in enumerate(vals[:12]):
            if np.isfinite(v): base[i] = v
    return base


def _bounded_hyperplane_projection(base, lo, hi, coeff, target, tol=1e-9):
    """Minimize 1/2||x-base||² subject to coeff·x=target and lo<=x<=hi.

    Uses the KKT solution x=clip(base-lambda*coeff, lo, hi) and bisection.
    Returns x, achieved, feasible_exact.
    """
    b = np.asarray(base, dtype=float)
    l = np.asarray(lo, dtype=float)
    h = np.asarray(hi, dtype=float)
    a = np.asarray(coeff, dtype=float)
    finite = np.isfinite(b) & np.isfinite(l) & np.isfinite(h) & np.isfinite(a)
    if not finite.any():
        return b.copy(), np.nan, False
    b = np.where(finite, b, 0.0)
    l = np.where(finite, l, b)
    h = np.where(finite, h, b)
    a = np.where(finite, a, 0.0)

    # Feasible interval for a·x, accounting for sign of coefficients.
    xmin = np.where(a >= 0, l, h)
    xmax = np.where(a >= 0, h, l)
    min_val = float(np.dot(a, xmin))
    max_val = float(np.dot(a, xmax))
    tgt = float(np.clip(target, min_val, max_val))
    exact = abs(tgt-target) <= max(tol, abs(target)*1e-10)

    if abs(max_val-min_val) <= tol:
        x = np.clip(b, l, h)
        return x, float(np.dot(a, x)), exact and abs(float(np.dot(a,x))-target) <= tol

    def f(lam):
        return float(np.dot(a, np.clip(b - lam*a, l, h)))

    # f is monotonically decreasing. Expand until target is bracketed.
    left, right = -1.0, 1.0
    fl, fr = f(left), f(right)
    for _ in range(80):
        if fl >= tgt >= fr:
            break
        if fl < tgt:
            left *= 2.0
            fl = f(left)
        if fr > tgt:
            right *= 2.0
            fr = f(right)
    for _ in range(100):
        mid = (left+right)/2.0
        fm = f(mid)
        if fm > tgt:
            left = mid
        else:
            right = mid
    lam = (left+right)/2.0
    x = np.clip(b-lam*a, l, h)
    return x, float(np.dot(a,x)), exact


def optimize_sp_matrix(
    earned: pd.DataFrame,
    settings,
    manual,
    locked_branches: Sequence[str],
    portfolio_target: Sequence[float],
    default_start: float = 60.0,
    default_end: float = 60.0,
):
    """Build and optionally optimize monthly S/P by branch against portfolio target."""
    e = pd.DataFrame(earned).copy()
    locked = set(locked_branches or [])
    base = np.zeros((12, len(BRANCHES)))
    lo = np.zeros_like(base)
    hi = np.zeros_like(base)
    hard = np.zeros_like(base, dtype=bool)
    for j,b in enumerate(BRANCHES):
        base[:,j], lo[:,j], hi[:,j], hard[:,j] = build_sp_path(settings, manual, b, default_start, default_end)
        if b in locked:
            lo[:,j] = base[:,j]
            hi[:,j] = base[:,j]
    out = base.copy()
    diags = []
    targets = np.asarray(list(portfolio_target), dtype=float)
    if len(targets) < 12: targets = np.r_[targets, np.full(12-len(targets), np.nan)]
    targets = targets[:12]
    achieved = np.full(12, np.nan)

    for i in range(12):
        earn = np.asarray([_num(e.loc[i,b], 0.0) if b in e.columns and i < len(e) else 0.0 for b in BRANCHES], dtype=float)
        total = float(earn.sum())
        if abs(total) <= 1e-12:
            achieved[i] = np.nan
            if np.isfinite(targets[i]): diags.append(f"{MONTHS[i]} : prime acquise nette portefeuille nulle, cible S/P non appliquée")
            continue
        if not np.isfinite(targets[i]):
            achieved[i] = float(np.dot(earn, out[i]) / total)
            continue
        # Normalize to make the Lagrange multiplier numerically stable.
        scale = max(float(np.abs(earn).sum()), 1.0)
        coeff = earn/scale
        target_charge_norm = (targets[i]/100.0 * total)/scale
        # x is in percent, so the hyperplane target in percent-units is *100.
        target_percent_norm = target_charge_norm*100.0
        x, got, exact = _bounded_hyperplane_projection(base[i], lo[i], hi[i], coeff, target_percent_norm)
        out[i] = x
        achieved[i] = float(np.dot(earn, x)/total)
        if not exact:
            diags.append(
                f"{MONTHS[i]} : cible portefeuille {targets[i]:.2f}% hors plage réalisable ; "
                f"meilleur niveau {achieved[i]:.2f}%"
            )
    return pd.DataFrame(out, columns=BRANCHES), pd.DataFrame(lo, columns=BRANCHES), pd.DataFrame(hi, columns=BRANCHES), achieved, diags


def calculate_claims_and_result(
    earned: pd.DataFrame,
    commission_net: pd.DataFrame,
    sp_exercise: pd.DataFrame,
    sp_global: pd.DataFrame,
):
    e = pd.DataFrame(earned).copy()
    c = pd.DataFrame(commission_net).copy()
    sx = pd.DataFrame(sp_exercise).copy()
    sg = pd.DataFrame(sp_global).copy()
    charge_ex = pd.DataFrame(index=range(12), columns=BRANCHES, dtype=float)
    charge_glob = charge_ex.copy()
    charge_ant = charge_ex.copy()
    result = charge_ex.copy()
    for b in BRANCHES:
        ev = np.asarray([_num(v,0.0) for v in e[b]], dtype=float)
        cv = np.asarray([_num(v,0.0) for v in c[b]], dtype=float)
        ex = np.asarray([_num(v,0.0) for v in sx[b]], dtype=float)
        gl = np.asarray([_num(v,0.0) for v in sg[b]], dtype=float)
        ce = ev*ex/100.0
        cg = ev*gl/100.0
        ca = cg-ce
        rt = ev-cg-cv
        charge_ex[b] = ce
        charge_glob[b] = cg
        charge_ant[b] = ca
        result[b] = rt
    return charge_ex, charge_ant, charge_glob, result


def portfolio_metrics(earned, charge_ex, charge_global, commission_net, result):
    e = pd.DataFrame(earned)
    ce = pd.DataFrame(charge_ex)
    cg = pd.DataFrame(charge_global)
    co = pd.DataFrame(commission_net)
    rt = pd.DataFrame(result)
    rows = []
    for i,m in enumerate(MONTHS):
        ep = float(sum(_num(e.loc[i,b],0.0) for b in BRANCHES))
        cep = float(sum(_num(ce.loc[i,b],0.0) for b in BRANCHES))
        cgp = float(sum(_num(cg.loc[i,b],0.0) for b in BRANCHES))
        cop = float(sum(_num(co.loc[i,b],0.0) for b in BRANCHES))
        rtp = float(sum(_num(rt.loc[i,b],0.0) for b in BRANCHES))
        rows.append({
            "Mois":m,
            "Prime acquise nette":ep,
            "S/P exercice portefeuille (%)":100*cep/ep if abs(ep)>1e-12 else np.nan,
            "S/P global portefeuille (%)":100*cgp/ep if abs(ep)>1e-12 else np.nan,
            "Charge exercice":cep,
            "Charge antérieurs":cgp-cep,
            "Charge globale":cgp,
            "Commission nette CPC":cop,
            "Résultat technique avant FG":rtp,
            "Marge technique avant FG (%)":100*rtp/ep if abs(ep)>1e-12 else np.nan,
        })
    return pd.DataFrame(rows)
