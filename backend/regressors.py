"""
Startup check: rebuild the 9 final regressors and prove they match your results.

The tuned regressors were never saved during training, so they are rebuilt from
what was saved, using YOUR deep_tuning.py code (imported, not copied):

  1. <encoder>_states_<code>_<modality>.csv  -> the 256 hidden features per video + split
  2. rank_features_by_pearson() on the TRAIN rows -> keep the top best_k features
  3. build_pipelines_demo(seed=42)[winner] with best_params -> fit on TRAIN rows
  4. predict the TEST rows -> MAE, RMSE, Pearson, CCC must be within the tolerance in settings.py
     (tiny floating-point differences from other library versions are accepted)

The terminal shows one summary line; the per-metric comparison is in logs/startup_check.log.

Passing models are saved to models_cache/<code>.joblib. Later starts load them
and re-run step 4 (a second), rebuilding only if something changed.
"""
import ast
import hashlib
import logging
from importlib import metadata

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone

import settings
from loader import load_module
from routing import EXERCISES, Exercise

log = logging.getLogger("mobiphysio.regressors")

# Per-metric details go ONLY to logs/startup_check.log (not the terminal)
detail = logging.getLogger("mobiphysio.startup_check")
detail.propagate = False
detail.setLevel(logging.INFO)
if not detail.handlers:
    _fh = logging.FileHandler(settings.LOG_DIR / "startup_check.log", mode="w", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    detail.addHandler(_fh)

METRICS = ("MAE", "RMSE", "Pearson", "CCC")
_VERSION_PKGS = ("scikit-learn", "lightgbm", "catboost", "xgboost", "numpy", "pandas", "scipy")


class StartupCheckError(RuntimeError):
    pass


def _versions():
    out = {}
    for p in _VERSION_PKGS:
        try:
            out[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            out[p] = None
    return out


def _file_fingerprint(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _deep_tuning(ex: Exercise):
    return load_module(ex.folder / "deep_tuning.py", f"deep_tuning_{ex.encoder.lower()}", ex.folder)


def _saved_test_row(ex: Exercise):
    """best_k, best_params and full-precision test metrics, from final_metrics_<code>_<mod>.csv."""
    df = pd.read_csv(ex.metrics_csv)
    row = df[df["split"] == "test"].iloc[0]
    if row["winner"] != ex.regressor:
        raise StartupCheckError(
            f"{ex.name}: {ex.metrics_csv.name} says the winner is {row['winner']}, "
            f"but the final choice is {ex.regressor}.")
    return {
        "best_k": int(row["best_k"]),
        "best_params": ast.literal_eval(row["best_params"]),
        "metrics": {m: float(row[m]) for m in METRICS},
    }


def _split(df, hidden_cols):
    train = df[df["split"] == "train"].reset_index(drop=True)
    test = df[df["split"] == "test"].reset_index(drop=True)
    return (train[hidden_cols], train["average_score"].to_numpy(),
            test[hidden_cols], test["average_score"].to_numpy())


def _compare(ex, got, saved):
    """Compares each rebuilt test metric with your saved result.
    Returns (diffs, problems): diffs = {metric: rebuilt - expected} for every metric that
    differs at CHECK_DECIMALS; problems = only those beyond the tolerance."""
    d = settings.CHECK_DECIMALS
    diffs, problems = {}, []
    for m in METRICS:
        expected = saved[m]
        diff = got[m] - expected
        if round(got[m], d) != round(expected, d):
            diffs[m] = diff
        tol = settings.CHECK_TOLERANCE_POINTS if m in ("MAE", "RMSE") else settings.CHECK_TOLERANCE_CORR
        if abs(diff) > tol:
            problems.append(f"{m}: rebuilt {got[m]:.{d}f}, expected {expected:.{d}f} "
                            f"(difference {diff:+.{d}f}, allowed \u00b1{tol})")
    return diffs, problems


def _evaluate(ex, dt, model, selected, X_test, y_test):
    pred = model.predict(X_test[selected])
    return {k: float(v) for k, v in dt.compute_metrics(y_test, pred).items()}


def _rebuild(ex: Exercise, dt, saved, X_train, y_train):
    pearson_df = dt.rank_features_by_pearson(X_train, y_train)          # TRAIN only, as in training
    selected = list(pearson_df.index[:saved["best_k"]])
    pipeline, _grid = dt.build_pipelines_demo(settings.SEED)[ex.regressor]
    model = clone(pipeline).set_params(**saved["best_params"])
    model.fit(X_train[selected], y_train)
    return model, selected


def prepare_one(ex: Exercise, force_rebuild=False):
    dt = _deep_tuning(ex)
    saved = _saved_test_row(ex)
    df = pd.read_csv(ex.states_csv)
    hidden_cols = [c for c in df.columns if c.startswith("hidden_")]
    X_train, y_train, X_test, y_test = _split(df, hidden_cols)

    cache_path = settings.CACHE_DIR / f"{ex.code}.joblib"
    fingerprint = {
        "versions": _versions(),
        "states_csv": _file_fingerprint(ex.states_csv),
        "best_k": saved["best_k"],
        "best_params": saved["best_params"],
    }

    model = selected = None
    source = "rebuilt"
    if cache_path.exists() and not force_rebuild:
        try:
            cached = joblib.load(cache_path)
            if cached.get("fingerprint") == fingerprint:
                model, selected, source = cached["model"], cached["selected"], "cache"
        except Exception as e:  # corrupt cache -> rebuild
            log.warning("%s: cache unreadable (%s), rebuilding", ex.name, e)

    if model is None:
        model, selected = _rebuild(ex, dt, saved, X_train, y_train)

    got = _evaluate(ex, dt, model, selected, X_test, y_test)
    diffs, problems = _compare(ex, got, saved["metrics"])

    if not problems and source == "rebuilt":   # within tolerance -> keep
        joblib.dump({"model": model, "selected": selected, "fingerprint": fingerprint}, cache_path)

    return {
        "exercise": ex,
        "model": model,
        "selected": selected,
        "hidden_cols": hidden_cols,
        "metrics": got,
        "expected": saved["metrics"],
        "diffs": diffs,
        "problems": problems,
        "source": source,
    }


def prepare_all(force_rebuild=False):
    """Returns {code: entry}. Raises StartupCheckError if any exercise misses and STRICT_CHECK is on."""
    results, failures = {}, []
    d = settings.CHECK_DECIMALS
    detail.info("Startup check: rebuilt test metrics vs your saved results (tolerance: MAE/RMSE "
                "\u00b1%s points, Pearson/CCC \u00b1%s)", settings.CHECK_TOLERANCE_POINTS,
                settings.CHECK_TOLERANCE_CORR)
    for code, ex in EXERCISES.items():
        r = prepare_one(ex, force_rebuild)
        results[code] = r
        status = "OUTSIDE TOLERANCE" if r["problems"] else ("small difference" if r["diffs"] else "exact match")
        detail.info("%-18s %-36s %s (%s)", ex.name, ex.model_label, status, r["source"])
        for m in METRICS:
            detail.info("    %-8s rebuilt %9.{0}f   expected %9.{0}f   difference %+.{0}f".format(d),
                        m, r["metrics"][m], r["expected"][m], r["metrics"][m] - r["expected"][m])
        if r["problems"]:
            failures.append(f"{ex.name}: " + "; ".join(r["problems"]))

    exact = sum(1 for r in results.values() if not r["diffs"])
    if failures:
        msg = ("Model check failed for: " + ", ".join(f.split(":")[0] for f in failures)
               + ". Details: logs/startup_check.log")
        detail.info("FAILED:\n  %s", "\n  ".join(failures))
        if settings.STRICT_CHECK:
            raise StartupCheckError(msg)
        log.warning("%s (STRICT_CHECK=0, starting anyway)", msg)
    else:
        log.info("Models checked: all 9 OK (%d exact, %d within tolerance).", exact, 9 - exact)
    return results


def predict(entry, features_256: np.ndarray) -> float:
    """features_256: the encoder's hidden state for one video."""
    X = pd.DataFrame([features_256], columns=entry["hidden_cols"])
    return float(entry["model"].predict(X[entry["selected"]])[0])


if __name__ == "__main__":
    # python regressors.py            -> run the check (uses cache)
    # python regressors.py --rebuild  -> ignore the cache
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        prepare_all(force_rebuild="--rebuild" in sys.argv)
    except StartupCheckError as e:
        print(e)
        sys.exit(1)
    finally:
        print((settings.LOG_DIR / "startup_check.log").read_text(encoding="utf-8"))
