# -*- coding: utf-8 -*-
"""
Core de modelado para Plataforma Dengue.

Expone:
- models: dict[str, estimator]
- load_data(grid, dates, target) -> (df_model, features_dict, splits)
- eval_models(df_model, feature_cols, models_dict, target, splits) -> (df_results, best_model)
- eval_h_level(df_model, feature_cols, best_model, h: int, m_season: int) -> (summary_df, folds_df, last_df, best_model)
"""

from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.ensemble import HistGradientBoostingRegressor

# xgboost es opcional: si no está instalado, lo salteamos sin romper
try:
    from xgboost import XGBRegressor
    _HAS_XGB = True
except Exception:
    _HAS_XGB = False


# ────────────────────────────────────────────────────────────────────────────────
# 1) MODELOS DISPONIBLES
#    Agregá/ajustá aquí tus modelos y sus hiperparámetros por defecto.
# ────────────────────────────────────────────────────────────────────────────────
models: Dict[str, object] = {}

if _HAS_XGB:
    models["XGB-tuned"] = XGBRegressor(
        n_estimators=600,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.0,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        tree_method="hist",
    )

models["HGBR-MSE"] = HistGradientBoostingRegressor(
    max_depth=6,
    learning_rate=0.05,
    max_iter=500,
    min_samples_leaf=20,
    l2_regularization=0.0,
    random_state=42
)


# ────────────────────────────────────────────────────────────────────────────────
# 2) CARGA DE DATOS Y FEATURES
#    Adaptá este bloque a tu pipeline real. Debe devolver:
#    - df_model: DataFrame con columnas de features + la columna objetivo "casos" (o la que uses)
#    - features_dict: dict[str, list[str]] mapeando nombre-de-conjunto -> columnas de features
#    - splits: objeto de cross-validation (TimeSeriesSplit u otro)
# ────────────────────────────────────────────────────────────────────────────────
@dataclass
class DataBundle:
    df_model: pd.DataFrame
    features_dict: Dict[str, List[str]]
    splits: TimeSeriesSplit

def _default_feature_sets(df: pd.DataFrame) -> Dict[str, List[str]]:
    """Crea un par de feature sets de ejemplo. Cambiá por los tuyos."""
    all_feats = [c for c in df.columns if c not in {"casos", "y", "target"}]
    # ejemplos de agrupación
    return {
        "ALL": all_feats,
        "reducido": [c for c in all_feats if any(k in c.lower() for k in ["temp", "hum", "lag", "rain", "prec"])],
    }

def _default_feature_sets(df: pd.DataFrame) -> Dict[str, List[str]]:
    # usar únicamente columnas numéricas (excluye datetime/objetos)
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    return {
        "ALL": num_cols,
        "reducido": [c for c in num_cols if any(k in c.lower() for k in ["temp", "hum", "lag", "rain", "prec"])],
    }

def load_data(grid: str, dates: str, target: str) -> Tuple[pd.DataFrame, Dict[str, List[str]], TimeSeriesSplit]:
    """
    Cargá tus datos finales listos para modelar.
    *Convención:* la columna objetivo debe llamarse 'casos' (ajusta si usas otro nombre).
    """
    # Ejemplo: intenta leer un parquet consolidado; si no existe, prueba un CSV;
    # si tampoco existe, levanta un ejemplo sintético para que no rompa.
    candidates = [
        Path(f"data/processed/df_model__{grid}__{dates}__{target}.parquet"),
        Path(f"data/processed/df_model__{grid}__{dates}__{target}.csv"),
        Path("data/processed/df_model.parquet"),
        Path("data/processed/df_model.csv"),
    ]
    df = None
    for p in candidates:
        if p.exists():
            if p.suffix == ".parquet":
                df = pd.read_parquet(p)
            else:
                df = pd.read_csv(p)
            break

    if df is None:
        # fallback sintético (para que el CLI funcione aunque aún no generaste datos)
        n = 250
        rng = pd.date_range("2022-01-02", periods=n, freq="W")
        df = pd.DataFrame({
            "fecha": rng,
            "temp_mean": np.sin(np.linspace(0, 10, n))*10 + 20 + np.random.randn(n),
            "rain_sum": np.abs(np.random.randn(n))*10,
            "lag_casos_1": np.r_[np.nan, np.random.poisson(2, n-1)],
        })
        df["casos"] = (0.2*df["temp_mean"] + 0.5*df["rain_sum"] + 0.8*df["lag_casos_1"].fillna(0)
                       + np.random.randn(n)*0.5).clip(0).round(0).astype(int)

    # Asegura índice temporal si lo necesitás
    if "fecha" in df.columns:
        df = df.sort_values("fecha").reset_index(drop=True)
    feat_base = df.drop(columns=[c for c in ["casos", "fecha"] if c in df.columns])
    features_dict = _default_feature_sets(feat_base)
    # features_dict = _default_feature_sets(df.drop(columns=[c for c in ["casos"] if c in df.columns]))
    splits = TimeSeriesSplit(n_splits=5, test_size=max(12, len(df)//10))  # ajustá a tu preferencia

    return df, features_dict, splits


# ────────────────────────────────────────────────────────────────────────────────
# 3) EVALUACIÓN DE MODELOS (CV) Y SELECCIÓN DEL MEJOR
# ────────────────────────────────────────────────────────────────────────────────
def _rmse(y_true, y_pred) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))

def eval_models(df_model: pd.DataFrame,
                feature_cols: List[str],
                models_dict: Dict[str, object],
                target: str = "casos",
                splits: TimeSeriesSplit = None) -> Tuple[pd.DataFrame, object]:
    """
    Hace CV con TimeSeriesSplit y devuelve:
    - DataFrame con métricas por modelo (ordenado por RMSE asc).
    - best_model entrenado en TODO el dataset (para usar luego en eval_h_level).
    """
    if splits is None:
        splits = TimeSeriesSplit(n_splits=5)

    X = df_model[feature_cols].to_numpy()
    y = df_model[target].to_numpy()

    rows = []
    best_key = None
    best_rmse = np.inf

    for name, est in models_dict.items():
        rmses, maes, r2s = [], [], []
        for train_idx, test_idx in splits.split(X):
            Xtr, Xte = X[train_idx], X[test_idx]
            ytr, yte = y[train_idx], y[test_idx]

            m = est
            m.fit(Xtr, ytr)
            pred = m.predict(Xte)

            rmses.append(_rmse(yte, pred))
            maes.append(mean_absolute_error(yte, pred))
            r2s.append(r2_score(yte, pred))

        row = {
            "Modelo": name,
            "RMSE_cv_mean": float(np.mean(rmses)),
            "MAE_cv_mean": float(np.mean(maes)),
            "R2_cv_mean": float(np.mean(r2s)),
        }
        rows.append(row)

        if row["RMSE_cv_mean"] < best_rmse:
            best_rmse = row["RMSE_cv_mean"]
            best_key = name

    df_results = pd.DataFrame(rows).sort_values("RMSE_cv_mean").reset_index(drop=True)

    # Entrena best en todo el dataset
    best_model = models_dict[best_key]
    best_model.fit(X, y)

    # Para compatibilidad con tu train_cli (columna 'RMSE_model' opcional)
    df_results["RMSE_model"] = df_results["RMSE_cv_mean"]

    return df_results, best_model


# ────────────────────────────────────────────────────────────────────────────────
# 4) EVALUACIÓN POR HORIZONTE (H) + BASELINES NAIVE
# ────────────────────────────────────────────────────────────────────────────────
def _naive_last(y: np.ndarray) -> np.ndarray:
    # y[t] predice y[t+1] (shift 1)
    return np.r_[np.nan, y[:-1]]

def _naive_seasonal(y: np.ndarray, m: int) -> np.ndarray:
    # uso el valor de hace 'm' pasos (ej: semanal con estacionalidad anual m=52)
    if len(y) <= m:
        return np.full_like(y, np.nan, dtype=float)
    arr = np.r_[np.full(m, np.nan), y[:-m]]
    return arr

def eval_h_level(df_model: pd.DataFrame,
                 feature_cols: List[str],
                 best_model: object,
                 h: int = 1,
                 m_season: int = 52
                 ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, object]:
    """
    Evalúa un horizonte h simple:
    - crea X(t) y y(t+h), entrena con todo (no CV),
    - compara con naive last y naive seasonal,
    - devuelve (summary_df, folds_df, last_df, best_model)
    """
    target = "casos"
    df = df_model.copy().reset_index(drop=True)

    # Objetivo desplazado h pasos
    df["y_h"] = df[target].shift(-h)
    df = df.dropna(subset=["y_h"]).reset_index(drop=True)

    X = df[feature_cols].to_numpy()
    y = df["y_h"].to_numpy()

    # Entrenamiento en todo el set
    best_model.fit(X, y)
    y_pred = best_model.predict(X)

    # Baselines
    naive_last = _naive_last(df[target].to_numpy())
    naive_seas = _naive_seasonal(df[target].to_numpy(), m=m_season)

    # Métricas
    def _metrics(y_true, y_hat):
        ok = ~np.isnan(y_hat)
        return {
            "RMSE": _rmse(y_true[ok], y_hat[ok]),
            "MAE": mean_absolute_error(y_true[ok], y_hat[ok]),
            "R2": r2_score(y_true[ok], y_hat[ok])
        }

    m_model = _metrics(y, y_pred)
    m_last  = _metrics(y, naive_last[: len(y)])
    m_seas  = _metrics(y, naive_seas[: len(y)])

    summary = pd.DataFrame([{
        "h": h,
        "RMSE_model": m_model["RMSE"],
        "MAE_macro_model": m_model["MAE"],
        "R2_model": m_model["R2"],
        "RMSE_naive_last": m_last["RMSE"],
        "R2_naive_last": m_last["R2"],
        "RMSE_naive_seas": m_seas["RMSE"],
        "R2_naive_seas": m_seas["R2"],
        "gain_vs_naive_last": m_last["RMSE"] - m_model["RMSE"],
    }])

    # folds_df: aquí reportamos “todo como un único fold” para compatibilidad
    folds_df = pd.DataFrame({
        "y_true": y,
        "y_pred": y_pred
    })

    # last_df: útil para trazabilidad
    last_df = df[["fecha"]].copy() if "fecha" in df.columns else pd.DataFrame(index=df.index)
    last_df["y_true"] = y
    last_df["y_pred"] = y_pred

    return summary, folds_df, last_df, best_model
