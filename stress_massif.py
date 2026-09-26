"""Campagne de stress reproductible du moteur.

Usage : python stress_massif.py
"""
from prime_engine import stress_random

if __name__ == '__main__':
    r = stress_random(seed=20260926, scenarios=5000)
    failures = int((~r['ok']).sum())
    print(f"Scénarios primes exécutés : {len(r):,}")
    print(f"Échecs : {failures}")
    if failures:
        print(r.loc[~r['ok']].head(20).to_string(index=False))
        raise SystemExit(1)
    print("Stress test primes : OK")
