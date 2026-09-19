"""Treatment-duration prediction (machine minutes, an operational quantity).

Two predictors share one interface:
  * LookupPredictor - day-1 mode from the problem statement: predefined average
    durations per technique and first/subsequent fraction.
  * QuantileGBMPredictor - learns from session logs (check-in, room entry,
    last beam, exit timestamps) and returns P50 and P80 minutes, so the
    scheduler can plan with uncertainty instead of a single average.

This predicts how long the machine is occupied. It never interprets clinical
data or recommends anything clinical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

FEATURES = ["technique", "site", "first", "mobility", "imaging", "elderly",
            "inpatient", "machine", "age", "n_accessories"]
CATEGORICAL = ["technique", "site", "mobility", "imaging", "machine"]


def _frame(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["first"] = (df["fraction_no"] == 1).astype(int)
    df["n_accessories"] = df["accessories"].apply(len)
    df["elderly"] = df["elderly"].astype(int)
    df["inpatient"] = df["inpatient"].astype(int)
    return df


class LookupPredictor:
    name = "Lookup table (averages)"

    def fit(self, rows):
        df = _frame(rows)
        g = df.groupby(["technique", "first"])["duration"]
        self.table = {k: (v.mean(), v.quantile(0.5), v.quantile(0.8)) for k, v in g}
        self.fallback = (df["duration"].mean(), df["duration"].median(), df["duration"].quantile(0.8))
        return self

    def lookup(self, technique: str, first: bool):
        return self.table.get((technique, int(first)), self.fallback)

    def _get(self, p):
        return self.lookup(p.technique, p.fraction_no == 1)

    def p50(self, p):
        return self._get(p)[0]          # the problem statement's "average duration"

    def p80(self, p):
        return self._get(p)[2]


class QuantileGBMPredictor:
    name = "Quantile gradient boosting"

    def fit(self, rows, seed: int = 0):
        df = _frame(rows)
        self.categories = {c: sorted(df[c].unique()) for c in CATEGORICAL}
        X = self._encode(df)
        mask = [f in CATEGORICAL for f in FEATURES]
        self.models = {}
        for q in (0.5, 0.8):
            m = HistGradientBoostingRegressor(loss="quantile", quantile=q, max_iter=300,
                                              learning_rate=0.08, max_leaf_nodes=31,
                                              categorical_features=mask, random_state=seed)
            m.fit(X, df["duration"].values)
            self.models[q] = m
        return self

    def _encode(self, df: pd.DataFrame) -> np.ndarray:
        X = pd.DataFrame(index=df.index)
        for f in FEATURES:
            if f in CATEGORICAL:
                lut = {v: i for i, v in enumerate(self.categories[f])}
                X[f] = df[f].map(lut).fillna(-1).astype(int)
            else:
                X[f] = df[f].astype(float)
        return X.values

    def predict_frame(self, rows, q: float) -> np.ndarray:
        return self.models[q].predict(self._encode(_frame(rows)))

    def _one(self, p, q):
        return float(self.predict_many([p], q)[0])

    def predict_many(self, patients, q: float) -> np.ndarray:
        rows = []
        for p in patients:
            row = p.to_dict()
            row["duration"] = 0.0
            rows.append(row)
        return self.predict_frame(rows, q)

    def p50(self, p):
        return self._one(p, 0.5)

    def p80(self, p):
        return self._one(p, 0.8)


def evaluate(predictors, test_rows) -> dict:
    """Accuracy of each predictor on held-out sessions."""
    df = _frame(test_rows)
    y = df["duration"].values
    out = {}
    for pr in predictors:
        if isinstance(pr, QuantileGBMPredictor):
            p50 = pr.predict_frame(test_rows, 0.5)
            p80 = pr.predict_frame(test_rows, 0.8)
        else:
            vals = [pr.lookup(r["technique"], r["fraction_no"] == 1) for r in test_rows]
            p50 = np.array([v[0] for v in vals])
            p80 = np.array([v[2] for v in vals])
        err = p50 - y
        out[pr.name] = {
            "mae_min": float(np.mean(np.abs(err))),
            "within_2min_pct": float(np.mean(np.abs(err) <= 2) * 100),
            "within_3min_pct": float(np.mean(np.abs(err) <= 3) * 100),
            "p80_coverage_pct": float(np.mean(y <= p80) * 100),
            "errors": err,
        }
    return out
