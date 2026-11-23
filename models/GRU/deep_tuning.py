import argparse
import warnings
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.base import clone
from sklearn.pipeline import Pipeline
from sklearn.model_selection import RandomizedSearchCV, KFold, cross_val_score
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import (RandomForestRegressor, AdaBoostRegressor, GradientBoostingRegressor,
                               ExtraTreesRegressor, BaggingRegressor)
from sklearn.tree import DecisionTreeRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor
from catboost import CatBoostRegressor

warnings.filterwarnings("ignore")


def concordance_correlation_coefficient(y_true, y_pred):
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    mean_true, mean_pred = y_true.mean(), y_pred.mean()
    var_true, var_pred = y_true.var(), y_pred.var()
    covariance = np.mean((y_true - mean_true) * (y_pred - mean_pred))
    return (2 * covariance) / (var_true + var_pred + (mean_true - mean_pred) ** 2 + 1e-8)


def compute_metrics(y_true, y_pred):
    """4 metrics only: MAE, RMSE, Pearson, CCC."""
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    pearson, _ = pearsonr(y_true, y_pred)
    ccc = concordance_correlation_coefficient(y_true, y_pred)
    return {"MAE": mae, "RMSE": rmse, "Pearson": pearson, "CCC": ccc}


def rank_features_by_pearson(X, y):
    y_arr = np.asarray(y, dtype=float)
    correlations = {}
    for col in X.columns:
        vals = X[col].to_numpy(dtype=float)
        if vals.std() < 1e-10:
            continue
        r, _ = pearsonr(vals, y_arr)
        if np.isfinite(r):
            correlations[col] = r
    df = pd.DataFrame({"pearson": correlations})
    df["abs_pearson"] = df["pearson"].abs()
    return df.sort_values("abs_pearson", ascending=False)


def build_pipelines_demo(seed):
    """Same 9 regressors as classical_regressors.py but with regularized grids
    to fight train-side memorization."""
    return {
        "LinearRegression": (Pipeline([("model", LinearRegression())]), None),
        "RandomForest": (
            Pipeline([("model", RandomForestRegressor(random_state=seed))]),
            {
                "model__n_estimators": [200, 400, 600],
                "model__max_depth": [5, 8, 12],
                "model__min_samples_split": [5, 10, 20],
                "model__min_samples_leaf": [2, 4, 8],
            },
        ),
        "XGBoost": (
            Pipeline([("model", XGBRegressor(random_state=seed, verbosity=0, colsample_bytree=0.8))]),
            {
                "model__n_estimators": [200, 400, 600],
                "model__max_depth": [3, 4, 5],
                "model__learning_rate": [0.01, 0.03, 0.05],
                "model__subsample": [0.7, 0.8],
                "model__reg_alpha": [0.1, 0.5, 1.0],
                "model__reg_lambda": [1.0, 2.0, 3.0],
                "model__min_child_weight": [1, 3, 5],
            },
        ),
        "AdaBoost": (
            Pipeline([("model", AdaBoostRegressor(random_state=seed))]),
            {
                "model__n_estimators": [50, 100, 200, 300],
                "model__learning_rate": [0.01, 0.05, 0.1, 0.5, 1.0],
            },
        ),
        "CatBoost": (
            Pipeline([("model", CatBoostRegressor(verbose=0, random_state=seed))]),
            {
                "model__iterations": [200, 400, 600],
                "model__depth": [4, 6],
                "model__learning_rate": [0.01, 0.03, 0.05],
                "model__l2_leaf_reg": [3, 5, 7],
            },
        ),
        "LightGBM": (
            Pipeline([("model", LGBMRegressor(random_state=seed, verbose=-1))]),
            {
                "model__n_estimators": [200, 400, 600],
                "model__learning_rate": [0.01, 0.03, 0.05],
                "model__num_leaves": [15, 31],
                "model__max_depth": [4, 5, 6],
                "model__min_child_samples": [10, 20, 30],
                "model__reg_alpha": [0.1, 0.5],
                "model__reg_lambda": [1.0, 2.0],
            },
        ),
        "GBM": (
            Pipeline([("model", GradientBoostingRegressor(random_state=seed))]),
            {
                "model__n_estimators": [100, 200, 400],
                "model__learning_rate": [0.01, 0.03, 0.05],
                "model__max_depth": [3, 4, 5],
                "model__min_samples_leaf": [4, 8, 12],
            },
        ),
        "ExtraTrees": (
            Pipeline([("model", ExtraTreesRegressor(random_state=seed))]),
            {
                "model__n_estimators": [200, 400, 600],
                "model__max_depth": [5, 8, 12],
                "model__min_samples_split": [5, 10, 20],
            },
        ),
        "BaggedDT": (
            Pipeline([("model", BaggingRegressor(
                estimator=DecisionTreeRegressor(random_state=seed, max_depth=5),
                random_state=seed))]),
            {
                "model__n_estimators": [50, 100, 200],
                "model__max_samples": [0.6, 0.8],
            },
        ),
    }


def forward_feature_selection(pipeline, X_train, y_train, pearson_df, fs_cv, fs_step, seed):
    n = len(pearson_df)
    ks = list(range(1, n + 1, fs_step))
    if ks[-1] != n:
        ks.append(n)

    cv = KFold(n_splits=fs_cv, shuffle=True, random_state=seed)
    scores = []
    for k in ks:
        cols = pearson_df.index[:k]
        try:
            s = cross_val_score(clone(pipeline), X_train[cols], y_train,
                                 cv=cv, scoring="neg_root_mean_squared_error", n_jobs=-1)
            scores.append(s.mean())
        except Exception:
            scores.append(-np.inf)

    best_i = int(np.argmax(scores))
    return ks[best_i], -scores[best_i]


def deep_tune_one_combo(states_csv, exercise_class, modality, winner_name,
                        fs_cv=5, fs_step=1, cv=2, n_iter=20, seed=42):
    """Leak-free tune of one (exercise, modality) with its own winner regressor.
    Prints one compact line: best_k + best_params."""
    df = pd.read_csv(states_csv)
    hidden_cols = [c for c in df.columns if c.startswith("hidden_")]

    train_df = df[df["split"] == "train"].reset_index(drop=True)
    val_df   = df[df["split"] == "val"].reset_index(drop=True)
    test_df  = df[df["split"] == "test"].reset_index(drop=True)

    X_train = train_df[hidden_cols]; y_train = train_df["average_score"].to_numpy()
    X_val   = val_df[hidden_cols];   y_val   = val_df["average_score"].to_numpy()
    X_test  = test_df[hidden_cols];  y_test  = test_df["average_score"].to_numpy()

    # feature ranking on TRAIN ONLY
    pearson_df = rank_features_by_pearson(X_train, y_train)

    pipelines = build_pipelines_demo(seed)
    if winner_name not in pipelines:
        raise ValueError(f"Unknown winner '{winner_name}'. Known: {list(pipelines)}")
    pipeline, param_dist = pipelines[winner_name]

    # forward feature selection on TRAIN ONLY
    best_k, _cv_rmse = forward_feature_selection(
        pipeline, X_train, y_train, pearson_df, fs_cv, fs_step, seed
    )
    selected = list(pearson_df.index[:best_k])

    # hyperparameter search on TRAIN ONLY
    X_train_k = X_train[selected]
    if param_dist is None:
        best_pipeline = clone(pipeline).fit(X_train_k, y_train)
        best_params = {}
    else:
        n_splits = max(2, min(cv, len(X_train_k) // 3))
        search = RandomizedSearchCV(
            clone(pipeline), param_distributions=param_dist, n_iter=n_iter,
            scoring="neg_root_mean_squared_error",
            cv=KFold(n_splits=n_splits, shuffle=True, random_state=seed),
            random_state=seed, n_jobs=-1,
        )
        search.fit(X_train_k, y_train)
        best_pipeline = search.best_estimator_
        best_params = search.best_params_

    print(f"[{exercise_class}/{modality}]  winner={winner_name}  best_k={best_k}  best_params={best_params}")

    def eval_split(split_name, split_df, X_split, y_split):
        if len(split_df) == 0:
            return None, None
        X_k = X_split[selected]
        y_pred = best_pipeline.predict(X_k)
        m = compute_metrics(y_split, y_pred)
        preds = [{
            "video_name": split_df["video_name"].iloc[i],
            "exercise_class": exercise_class, "modality": modality,
            "split": split_name,
            "true": float(y_split[i]), "pred": float(y_pred[i]),
        } for i in range(len(split_df))]
        return preds, m

    prediction_rows, metric_rows = [], []
    for split_name, split_df, X_split, y_split in [
        ("train", train_df, X_train, y_train),
        ("val",   val_df,   X_val,   y_val),
        ("test",  test_df,  X_test,  y_test),
    ]:
        preds, m = eval_split(split_name, split_df, X_split, y_split)
        if m is None: continue
        prediction_rows.extend(preds)
        metric_rows.append({
            "exercise_class": exercise_class, "modality": modality,
            "winner": winner_name, "split": split_name, "n": len(split_df), **m,
        })

    predictions_df = pd.DataFrame(prediction_rows)
    metrics_df = pd.DataFrame(metric_rows)
    metrics_df["best_k"] = best_k
    metrics_df["best_params"] = str(best_params)

    predictions_df.to_csv(f"final_predictions_{exercise_class}_{modality}.csv", index=False)
    metrics_df.to_csv(f"final_metrics_{exercise_class}_{modality}.csv", index=False)

    return predictions_df, metrics_df


def deep_tune_all_combos(combo_to_winner,
                          gru_states_pattern="gru_states_{exercise_class}_{modality}.csv",
                          fs_cv=5, fs_step=1, cv=2, n_iter=20, seed=42):
    """combo_to_winner: dict {(exercise_class, modality) -> winner_name}.
    Deep-tunes each combo with its OWN winner (per-combo selection)."""
    all_preds, all_metrics = [], []
    for (exercise_class, modality), winner_name in sorted(combo_to_winner.items()):
        states_csv = gru_states_pattern.format(exercise_class=exercise_class, modality=modality)
        preds, metrics = deep_tune_one_combo(
            states_csv, exercise_class, modality, winner_name,
            fs_cv=fs_cv, fs_step=fs_step, cv=cv, n_iter=n_iter, seed=seed,
        )
        all_preds.append(preds)
        all_metrics.append(metrics)

    combined_preds = pd.concat(all_preds, ignore_index=True)
    combined_metrics = pd.concat(all_metrics, ignore_index=True)
    combined_preds.to_csv("final_predictions_all.csv", index=False)
    combined_metrics.to_csv("final_metrics_all.csv", index=False)

    # summary: test metrics only
    test_only = combined_metrics[combined_metrics["split"] == "test"].copy()
    print("\n" + "=" * 72)
    print("TEST-set metrics — per-combo tuned winners")
    print("=" * 72)
    with pd.option_context("display.width", 200, "display.max_columns", None):
        show_cols = ["exercise_class", "modality", "winner", "n",
                     "MAE", "RMSE", "Pearson", "CCC"]
        print(test_only[show_cols].round(4).to_string(index=False))

    return combined_preds, combined_metrics


if __name__ == "__main__":
    # CLI path kept for standalone use — but pick_best_regressor.py now drives
    # per-combo tuning via deep_tune_all_combos(combo_to_winner=...).
    p = argparse.ArgumentParser()
    p.add_argument("--winner", required=True,
                    help="single winner applied to every combo (legacy mode)")
    p.add_argument("--all-metrics-csv", default="all_classical_metrics.csv")
    p.add_argument("--gru-states-pattern", default="gru_states_{exercise_class}_{modality}.csv")
    p.add_argument("--fs-cv", type=int, default=5)
    p.add_argument("--fs-step", type=int, default=1)
    p.add_argument("--cv", type=int, default=2)
    p.add_argument("--n-iter", type=int, default=20)
    p.add_argument("--seed", type=int, default=42)
    args, _unknown = p.parse_known_args()

    src = pd.read_csv(args.all_metrics_csv)
    combos = src[["exercise_class", "modality"]].drop_duplicates().values.tolist()
    combo_to_winner = {(ex, mod): args.winner for ex, mod in combos}

    deep_tune_all_combos(
        combo_to_winner, args.gru_states_pattern,
        args.fs_cv, args.fs_step, args.cv, args.n_iter, args.seed,
    )
