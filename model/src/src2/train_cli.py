# model/src/train_cli.py
import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Any

import pandas as pd
import yaml

# ────────────────────────────────────────────────────────────────────────────────
# Tu módulo core con las funciones reales
# Debe definir: models (dict), load_data(...), eval_models(...), eval_h_level(...)
from modelo_ import models, load_data, eval_models, eval_h_level
# ────────────────────────────────────────────────────────────────────────────────


# -------------------------- Utils --------------------------
def _split_csv(arg: str) -> List[str]:
    return [s.strip() for s in arg.split(",") if s.strip()]

def _select_models(models_dict: Dict[str, Any], names: List[str]) -> Dict[str, Any]:
    if names == ["all"]:
        return models_dict
    missing = [n for n in names if n not in models_dict]
    if missing:
        raise ValueError(f"Modelos no encontrados: {missing}\nDisponibles: {list(models_dict.keys())}")
    return {k: models_dict[k] for k in names}

def _select_features(features_dict: Dict[str, Any], names: List[str]) -> List[str]:
    if names == ["all"]:
        return list(features_dict.keys())
    out: List[str] = []
    for pat in names:
        if pat.startswith("re:"):
            rx = re.compile(pat[3:])
            out.extend([k for k in features_dict.keys() if rx.search(k)])
        elif pat in features_dict:
            out.append(pat)
    if not out:
        raise ValueError(
            f"No se encontraron feature sets para {names}. "
            f"Disponibles: {list(features_dict.keys())}"
        )
    # sin duplicados preservando orden
    seen = set(); dedup = []
    for k in out:
        if k not in seen:
            dedup.append(k); seen.add(k)
    return dedup

def _ensure_dirs(outdir: Path):
    (outdir / "train_test").mkdir(parents=True, exist_ok=True)
    (outdir / "figs").mkdir(parents=True, exist_ok=True)

# ----------------------- Core runner -----------------------
def run(grids: List[str],
        dates: List[str],
        targets: List[str],
        model_names: List[str],
        feature_names: List[str],
        horizons: List[int],
        outdir: Path):

    _ensure_dirs(outdir)
    selected_models = _select_models(models, model_names)

    all_rows = []
    for t in targets:
        for g in grids:
            for d in dates:
                df_model, features_dict, splits = load_data(g, d, t)
                feat_labels = _select_features(features_dict, feature_names)

                for flabel in feat_labels:
                    print(f"\n▶ grid={g} | dates={d} | target={t} | features={flabel}")

                    # Evalúa todos los modelos seleccionados y elige el mejor
                    df_results, best_model = eval_models(
                        df_model, features_dict[flabel], selected_models, target='casos', splits=splits
                    )
                    df_results = df_results.round(4)
                    (outdir / "train_test" / f"metrics_train_{g}_{d}_{t}__{flabel}.csv").write_text(
                        df_results.to_csv(index=False), encoding="utf-8"
                    )

                    for h in horizons:
                        sum_h, folds_h, last_h, _ = eval_h_level(
                            df_model, features_dict[flabel], best_model, h=h, m_season=52
                        )
                        pre = outdir / f"{t}__{g}__{d}__{flabel}__h{h}"
                        folds_h.to_csv(pre.with_suffix("").as_posix() + "__folds.csv", index=False)
                        sum_h.to_csv(pre.with_suffix("").as_posix() + "__summary.csv", index=False)

                        row = {
                            "target": t, "grid": g, "dates": d, "features": flabel, "h": h,
                            "model": df_results.iloc[0].get('Modelo', 'best')  # o ajusta a tu columna
                        }
                        for col in ["RMSE_model", "MAE_macro_model", "R2_model",
                                    "RMSE_naive_last", "R2_naive_last",
                                    "RMSE_naive_seas", "R2_naive_seas",
                                    "gain_vs_naive_last"]:
                            if col in sum_h.columns:
                                row[col] = float(sum_h[col].iloc[0])
                        all_rows.append(row)

    metrics_df = pd.DataFrame(all_rows)
    metrics_df.to_csv(outdir / "metrics.csv", index=False)
    print(f"\n✅ Listo: {outdir / 'metrics.csv'} (filas: {len(metrics_df)})")


# ----------------------- Config / CLI ----------------------
def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def merge_cfg(base: dict, override: dict) -> dict:
    """Sobrescribe claves de base con override (solo 1er nivel)."""
    out = dict(base)
    for k, v in override.items():
        if v is not None:
            out[k] = v
    return out

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Entrenamiento parametrizable (modelos, grillas, fechas, targets, features, horizontes)."
    )
    p.add_argument("--config", help="Ruta a YAML de configuración (opcional).")
    p.add_argument("--models", help="Modelos por nombre separados por coma (o 'all'). Ej: XGB-tuned,HGBR-MSE")
    p.add_argument("--grids", help="Grillas separadas por coma. Ej: MUN,VM,1KM")
    p.add_argument("--dates", help="Agregaciones temporales. Ej: 14D,7D,MS")
    p.add_argument("--targets", help="Targets separados por coma. Ej: COUNT,INC")
    p.add_argument("--features", help="Feature sets por nombre o regex con prefijo 're:'. Ej: 'all' o 're:Vecinos|Clima'")
    p.add_argument("--horizons", help="Horizontes separados por coma. Ej: 1,2,3,4")
    p.add_argument("--outdir", help="Carpeta de salida. Por defecto: results")
    return p

def main():
    parser = build_parser()
    args = parser.parse_args()

    # Defaults
    cfg = {
        "models": ["all"],
        "grids": ["MUN"],
        "dates": ["14D"],
        "targets": ["COUNT"],
        "features": ["all"],
        "horizons": [1, 2, 3, 4],
        "outdir": "model\\results",
    }

    # YAML
    if args.config:
        y = load_yaml(Path(args.config))
        # normalizamos listas que vengan como string
        def _norm(k, default):
            if k in y and isinstance(y[k], str):
                y[k] = _split_csv(y[k])
            elif k in y and y[k] is None:
                y[k] = default
        for k, default in cfg.items():
            _norm(k, default)
        cfg = merge_cfg(cfg, y)

    # Flags (sobrescriben YAML)
    if args.models:   cfg["models"]   = _split_csv(args.models)
    if args.grids:    cfg["grids"]    = _split_csv(args.grids)
    if args.dates:    cfg["dates"]    = _split_csv(args.dates)
    if args.targets:  cfg["targets"]  = _split_csv(args.targets)
    if args.features: cfg["features"] = _split_csv(args.features)
    if args.horizons: cfg["horizons"] = [int(h) for h in _split_csv(args.horizons)]
    if args.outdir:   cfg["outdir"]   = args.outdir

    # Ejecutar
    try:
        run(
            grids=cfg["grids"],
            dates=cfg["dates"],
            targets=cfg["targets"],
            model_names=cfg["models"],
            feature_names=cfg["features"],
            horizons=cfg["horizons"],
            outdir=Path(cfg["outdir"]),
        )
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        raise

if __name__ == "__main__":
    main()
