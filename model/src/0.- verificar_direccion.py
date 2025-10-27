#!/usr/bin/env python
# coding: utf-8

# -----------------------------------------------------------
# Verificación y geocodificación de direcciones (parametrizable)
# -----------------------------------------------------------

import argparse
from dataclasses import dataclass
from typing import Optional, Tuple
import warnings
warnings.filterwarnings("ignore")

import time
import re
import difflib
import unicodedata

import pandas as pd
import numpy as np

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
import overpy


# =======================
# CLI / CONFIG
# =======================

@dataclass
class CityConfig:
    city: str
    province: str
    country: str
    admin_level: int = 8
    bbox: Optional[Tuple[float, float, float, float]] = None  # (lat_min, lat_max, lon_min, lon_max)
    ua: str = "geo_mapper_cli"
    timeout: int = 20

    def full_name(self) -> str:
        return f"{self.city}, {self.province}, {self.country}"


def parse_bbox(s: Optional[str]) -> Optional[tuple]:
    if not s:
        return None
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox debe ser 'lat_min,lat_max,lon_min,lon_max'")
    return tuple(map(float, parts))


def get_args():
    ap = argparse.ArgumentParser(description="Verificación y geocodificación de direcciones parametrizable")

    # Ciudad / área
    ap.add_argument("--city", default="Villa María")
    ap.add_argument("--province", default="Córdoba")
    ap.add_argument("--country", default="Argentina")
    ap.add_argument("--admin-level", type=int, default=8)
    ap.add_argument("--bbox", help="lat_min,lat_max,lon_min,lon_max (opcional)")
    ap.add_argument("--skip-bbox-lookup", action="store_true", help="No consultar bbox a Nominatim (usa --bbox si querés)")

    # Geocoder
    ap.add_argument("--ua", default="vm_dengue_mapper")     # user-agent para Nominatim
    ap.add_argument("--timeout", type=int, default=20)

    # Entradas / salidas por defecto (podés cambiarlas acá o desde CLI)
    ap.add_argument("--in-xlsx", default=r"data\raw\No utiles\notificaciones dengue Villa María 23-24.xlsx")
    ap.add_argument("--in-xlsx-2", default=r"data\raw\No utiles\Notificaciones dengue Villa María 24-25.xlsx")
    ap.add_argument("--in-casos-ok",  default=r"data\raw\casos_procesados\casos_direccion_real.xlsx")
    ap.add_argument("--out-casos-ok", default=r"data\raw\casos_procesados\casos_direccion_real.xlsx")
    ap.add_argument("--in-dir", default=r"data\raw\casos_raw",
                    help="Carpeta con .xlsx de casos (lee todos)")
    # Columnas
    ap.add_argument("--col-calle", default="calle_domicilio")
    ap.add_argument("--col-num", default="numero_domicilio")
    ap.add_argument("--col-clasif", default="clasificacion_manual")
    ap.add_argument("--col-dir", default="DIRECCION")

    return ap.parse_args()

from pathlib import Path
import sys

def _abs(p): return Path(p).expanduser().resolve()
def _must_exist(p, flag):
    if not p.exists():
        print(f"[ERROR] No existe {flag}: {p}\ncwd={Path.cwd()}")
        sys.exit(2)
    return p

def build_cfg(args) -> CityConfig:
    return CityConfig(
        city=args.city,
        province=args.province,
        country=args.country,
        admin_level=args.admin_level,
        bbox=parse_bbox(args.bbox),
        ua=args.ua,
        timeout=args.timeout,
    )


# =======================
# Helpers OSM / Geocoder
# =======================

def ensure_bbox(cfg: CityConfig, geolocator: Nominatim) -> CityConfig:
    """Completa bbox con Nominatim si no se pasó por CLI y no se pidió saltar."""
    if cfg.bbox is not None or geolocator is None:
        return cfg
    loc = geolocator.geocode(cfg.full_name())
    if loc and isinstance(loc.raw, dict) and "boundingbox" in loc.raw:
        bb = loc.raw["boundingbox"]  # [lat_min, lat_max, lon_min, lon_max] (strings)
        cfg.bbox = (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))
    return cfg


def dentro_de_ciudad(lat: float, lon: float, cfg: CityConfig) -> bool:
    """Chequeo simple por bounding box del área configurada."""
    if not cfg.bbox:
        return True
    lat_min, lat_max, lon_min, lon_max = cfg.bbox
    return (lat_min <= lat <= lat_max) and (lon_min <= lon <= lon_max)


def build_address(raw: str, cfg: CityConfig) -> str:
    """'CALLE NUM, Ciudad, Provincia, País' para la ciudad activa."""
    return f"{raw}, {cfg.city}, {cfg.province}, {cfg.country}"


def overpass_calles(cfg: CityConfig, api: overpy.Overpass) -> list:
    """Devuelve lista de nombres de calles en el área seleccionada (Overpass)."""
    q = f"""
    area["boundary"="administrative"]["name"="{cfg.city}"]["admin_level"="{cfg.admin_level}"]->.a;
    way(area.a)["highway"]["name"];
    out;
    """
    res = api.query(q)
    return sorted({w.tags["name"] for w in res.ways if "name" in w.tags})


def geocode_intersection_op(street1: str, street2: str, cfg: CityConfig, api: overpy.Overpass):
    """Coord de intersección entre dos calles dentro del área admin."""
    q = f"""
    area["boundary"="administrative"]["name"="{cfg.city}"]["admin_level"="{cfg.admin_level}"]->.a;
    way(area.a)["highway"]["name"="{street1}"]->.w1;
    way(area.a)["highway"]["name"="{street2}"]->.w2;
    node(w1.w2)->.n;
    out body n 1;
    """
    try:
        r = api.query(q)
        if r.nodes:
            n = r.nodes[0]
            return float(n.lat), float(n.lon)
    except Exception:
        pass
    return None


# =======================
# Normalización de texto / matching de calles
# =======================

def normalize(texto: str) -> str:
    """
    Quita acentos y otros diacríticos pero preserva la ñ. Devuelve en mayúsculas.
    """
    nfkd = unicodedata.normalize('NFKD', texto)
    out = []
    prev = None
    for c in nfkd:
        if unicodedata.combining(c):
            if c == '\u0303' and prev and prev.lower() == 'n':  # tilde sobre n -> conserva (ñ)
                out.append(c)
        else:
            out.append(c)
            prev = c
    result = ''.join(out).upper()
    return unicodedata.normalize('NFC', result)


def buscar_calle_similar(texto: str, lista_calles: list, n=5, cutoff=0.6) -> list:
    originales = lista_calles
    normalized_calles = [normalize(c) for c in originales]
    target = normalize(texto)
    matches = difflib.get_close_matches(target, normalized_calles, n=n, cutoff=cutoff)
    return [originales[normalized_calles.index(m)] for m in matches]


def is_intersection(addr: str) -> bool:
    a = addr.lower()
    return " y " in a or " esq. " in a or " esq " in a


def split_intersection(addr: str):
    low = addr.lower()
    if " y " in low:
        parts = low.split(" y ", 1)
    elif " esq. " in low:
        parts = low.split(" esq. ", 1)
    else:
        parts = low.split(" esq ", 1)
    return parts[0].strip().capitalize(), parts[1].strip().capitalize()


# =======================
# Geocoding
# =======================

def geocode_direccion(direccion: str, geolocator: Nominatim, max_retries=5, base_delay=2):
    delay = base_delay
    for intento in range(1, max_retries + 1):
        try:
            time.sleep(delay)
            return geolocator.geocode(direccion)
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            print(f"[REINTENTO] {direccion} → {str(e)}")
            time.sleep(delay)
            delay = min(delay * 2, 30)  # backoff con tope
        except Exception as e:
            print(f"[FALLO FATAL] {direccion} → {str(e)}")
            break
    return None


# =======================
# Limpieza lon/lat en strings (si venían invertidos)
# =======================

def procesar_coordenadas(df, lon_col='lon', lat_col='lat', wkt_col='WKT'):
    mask = df[lon_col].astype(str).str.contains(',', na=False)
    if not mask.any():
        return df

    split = (
        df.loc[mask, lon_col]
          .astype(str)
          .str.split(',', expand=True)
          .rename(columns={0: lat_col, 1: lon_col})
    )
    split[lat_col] = split[lat_col].str.replace('"','').str.strip().astype(float)
    split[lon_col] = split[lon_col].str.replace('"','').str.strip().astype(float)

    df.loc[mask, lat_col] = split[lat_col]
    df.loc[mask, lon_col] = split[lon_col]

    df[wkt_col] = df.apply(
        lambda r: f"POINT({r[lon_col]} {r[lat_col]})" if pd.notna(r[lon_col]) and pd.notna(r[lat_col]) else pd.NA,
        axis=1
    )
    return df


# =======================
# Asignación de resultados y core
# =======================

def asignar_location(location, df, idx, dir_raw, cfg: CityConfig, mensaje=0):
    lat = location.latitude
    lon = location.longitude
    if not dentro_de_ciudad(lat, lon, cfg):
        print(f"[ERROR GEO] Coordenadas fuera de {cfg.full_name()}: {dir_raw} → ({lat}, {lon})")
    df.at[idx, 'lat'] = lat
    df.at[idx, 'lon'] = lon
    df.at[idx, 'WKT'] = f"POINT({lon} {lat})"
    if mensaje == 1:
        print(f"[ENCONTRADA] (2) {dir_raw} → ({lat}, {lon})")
    else:
        print(f"[ENCONTRADA] {dir_raw} → ({lat}, {lon})")
    return df


def evaluar_direccion(df, cfg: CityConfig, geolocator: Nominatim, api: overpy.Overpass,
                      calles: list, columna_direccion="DIRECCION"):

    if "lon" not in df.columns:
        df["lon"] = np.nan
    if "lat" not in df.columns:
        df["lat"] = np.nan
    if "WKT" not in df.columns:
        df["WKT"] = pd.NA

    faltantes = df[df['lon'].isna()].copy()

    reemplazos = {
        'TTE.': 'TENIENTE',
        'INT': 'INTENDENTE',
        "MEJICO": "MEXICO",
        'Antonio Hosch': 'Enrique Antonio Hoch',
        'Enrique A. Hoch': 'Enrique Antonio Hoch',
        'T. PEÑA': "INTENDENTE PEÑA",
        "EEUU": "ESTADOS UNIDOS",
        'BV ALVEAR': 'Boulevard Marcelo T. de Alvear',
        'CTDA. ': ""
    }

    contador = 0
    for idx, row in faltantes.iterrows():
        contador += 1
        dir_raw = row[columna_direccion]

        if not isinstance(dir_raw, str):
            continue
        dir_raw = dir_raw.strip()
        if dir_raw == "":
            continue

        u = dir_raw.upper()
        if ("ZONA RURAL" in u) or ("NO HAY" in u) or ("SIN D" in u) or ("NO SE E" in u) or ("S/D" in u) or ("NO TIENE" in u):
            continue

        # normaliza reemplazos comunes
        for k, v in reemplazos.items():
            if k in u:
                u = u.replace(k, v, 1)

        # 1) intento directo
        base = build_address(u, cfg)
        location = geocode_direccion(base, geolocator)

        if location:
            df = asignar_location(location, df, idx, u, cfg)
            continue

        # 2) similaridad de calle
        street = u.split(',')[0].strip()
        similares = buscar_calle_similar(street, calles, n=5, cutoff=0.6)
        if similares:
            for calle in similares:
                intento = build_address(calle, cfg)
                loc2 = geocode_direccion(intento, geolocator)
                if loc2 and dentro_de_ciudad(loc2.latitude, loc2.longitude, cfg):
                    df = asignar_location(loc2, df, idx, calle, cfg, mensaje=1)
                    break
            else:
                # 3) intersecciones si aplica y no hubo match por similaridad
                if is_intersection(u):
                    s1, s2 = split_intersection(u)
                    # limpieza mínima de números para overpass (calle, sin altura)
                    s1c = re.sub(r'\d+', '', s1).strip()
                    s2c = re.sub(r'\d+', '', s2).strip()
                    inter = geocode_intersection_op(s1c, s2c, cfg, api)
                    if inter and dentro_de_ciudad(*inter, cfg):
                        lat, lon = inter
                        df.at[idx, 'lat'] = lat
                        df.at[idx, 'lon'] = lon
                        df.at[idx, 'WKT'] = f"POINT({lon} {lat})"
                        print(f"[ENCONTRADA POR INTERSECCIÓN] {u} → ({lat}, {lon})")
                    else:
                        print(f"[NO ENCONTRADA] Intersección sin resultados: {u}")
                else:
                    print(f"[NO ENCONTRADA] Sin similar válida: '{street}'")
        else:
            # 3) intersección si no hubo similares
            if is_intersection(u):
                s1, s2 = split_intersection(u)
                s1c = re.sub(r'\d+', '', s1).strip()
                s2c = re.sub(r'\d+', '', s2).strip()
                inter = geocode_intersection_op(s1c, s2c, cfg, api)
                if inter and dentro_de_ciudad(*inter, cfg):
                    lat, lon = inter
                    df.at[idx, 'lat'] = lat
                    df.at[idx, 'lon'] = lon
                    df.at[idx, 'WKT'] = f"POINT({lon} {lat})"
                    print(f"[ENCONTRADA POR INTERSECCIÓN] {u} → ({lat}, {lon})")
                else:
                    print(f"[NO ENCONTRADA] Intersección sin resultados: {u}")
            else:
                print(f"[NO ENCONTRADA] Ninguna similar válida para '{street}'")

    return df


# =======================
# MAIN
# =======================

if __name__ == "__main__":
    args = get_args()


    from pathlib import Path
    import sys

    # Raíz del proyecto = carpeta "model/"
    ROOT = Path(__file__).resolve().parent.parent   # .../model

    def _abs_from_root(p):
        p = Path(p)
        return p if p.is_absolute() else (ROOT / p).resolve()

    def _must_exist(p: Path, flag: str) -> Path:
        if not p.exists():
            print(f"[ERROR] No existe {flag}: {p}\n  cwd={Path.cwd()}\n  ROOT={ROOT}")
            sys.exit(2)
        return p

    CFG = build_cfg(args)

    # Inicializa clientes
    geolocator = Nominatim(user_agent=CFG.ua, timeout=CFG.timeout)
    api = overpy.Overpass()

    # Completa bbox si no vino por CLI y no se pidió saltarla
    if not args.skip_bbox_lookup and CFG.bbox is None:
        CFG = ensure_bbox(CFG, geolocator)

    # --- Carga de datos fuente ---
    # --- Carga de datos fuente ---
    in_dir = _abs_from_root(args.in_dir)
    if not in_dir.exists():
        print(f"[ERROR] --in-dir no existe: {in_dir}\n  cwd={Path.cwd()}\n  ROOT={ROOT}")
        sys.exit(2)

    files = sorted([p for p in in_dir.glob("*.xlsx") if p.is_file()])
    if not files:
        print(f"[ERROR] No hay .xlsx en {in_dir}")
        sys.exit(2)

    print("[INFO] Leyendo .xlsx desde carpeta:", in_dir)
    for p in files:
        print("  -", p.name)
    dfs = [pd.read_excel(p) for p in files]
    df_casos = pd.concat(dfs, ignore_index=True)

    # Maestro (ya corregidos) y salida
    p_ok    = _must_exist(_abs_from_root(args.in_casos_ok), "in-casos-ok")
    out_path = _abs_from_root(args.out_casos_ok)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    casos_correctos = pd.read_excel(p_ok)

    # --- pipeline ---
    cols_utiles = ['sexo', 'edad_diagnostico', args.col_calle, args.col_num, 'fecha_apertura', args.col_clasif]
    df_casos = df_casos[cols_utiles].copy()

    df_casos_conf = df_casos.loc[
        (df_casos[args.col_clasif].astype(str).str.contains("confirmado", case=False, na=False)) |
        (df_casos[args.col_clasif].astype(str).str.contains("Caso de Dengue en brote con laboratorio", case=False, na=False))
    ].copy()

    df_casos_conf[args.col_dir] = (
        df_casos_conf[args.col_calle].fillna('') + " " + df_casos_conf[args.col_num].fillna('')
    )

    # Filas a revisar (las que no están ya geocodificadas en el maestro)
    df_sacar = pd.merge(
        df_casos_conf,
        casos_correctos[[args.col_dir, "WKT"]],
        left_on=args.col_dir,
        right_on=args.col_dir,
        how="left"
    )
    ya_ok    = list(casos_correctos.loc[~casos_correctos["WKT"].isnull(), args.col_dir])
    df_revisar = df_casos_conf.loc[~df_casos_conf[args.col_dir].isin(ya_ok)]

    # Callejero
    try:
        calles = overpass_calles(CFG, api)
    except Exception as e:
        print(f"[WARN] Falló Overpass para '{CFG.city}': {e}. Continuo sin callejero (solo geocoder).")
        calles = []

    # Geocodificación
    df2 = evaluar_direccion(df_revisar, CFG, geolocator, api, calles, columna_direccion=args.col_dir)

    # Merge final y guardado
    df_ok    = df2.loc[~df2["lon"].isnull()].copy()
    df_final = pd.concat([casos_correctos, df_ok], ignore_index=True)
    df_final.to_excel(out_path, index=False)

    print(f"[OK] Ciudad: {CFG.full_name()}  | admin_level={CFG.admin_level}  | bbox={CFG.bbox}")
    print(f"[OK] Guardado: {out_path}  (total filas: {len(df_final)})")