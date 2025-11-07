# -*- coding: utf-8 -*-
# Auto-added by exporter: force UTF-8 stdout/stderr when running as .py
import os, sys
try:
    # Python 3.7+: reconfigure disponible en la mayoría de builds
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    else:
        # Fallback: envolver buffers (evita fallar en Jupyter donde no hay .buffer)
        import io
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    # Nunca romper el script por temas de encoding
    pass

#!/usr/bin/env python
# coding: utf-8

# Corroborar si este es mas rapido al no seleccionar días separados

# In[1]:


# from pathlib import Path
# import sqlite3
# BASE_DIR = Path().resolve()  

# DB_PATH = BASE_DIR.parent / "backend" / "data" / "mi_base_de_datos5.db"

# conn = sqlite3.connect(DB_PATH)

# # 2) Lée los últimos 20 registros (ordenados por fecha decreciente)
# df_clima = pd.read_sql_query("""
#     SELECT *
#       FROM climate_test
#      ORDER BY date
# """, conn)

# conn.close()
# df_clima


# In[2]:


# DB_PATH = BASE_DIR.parent / "backend" / "data" / "mi_base_de_datos5.db"

# conn = sqlite3.connect(DB_PATH)

# cur = conn.cursor()
# cur.executescript("""
# CREATE INDEX IF NOT EXISTS idx_ct_dll  ON climate_test(date, latitude, longitude);
# CREATE INDEX IF NOT EXISTS idx_wxt_dll ON climate_wxt2(date, latitude, longitude);
# """)

# # update: reemplaza solo con valores no nulos de climate_wxt
# cur.executescript("""
# UPDATE climate_test AS t
# SET
#   t2m_min = COALESCE((
#       SELECT w.t2m_min
#       FROM climate_wxt2 w
#       WHERE w.date = t.date
#         AND w.latitude  = t.latitude
#         AND w.longitude = t.longitude
#   ), t.t2m_min),
#   t2m_max = COALESCE((
#       SELECT w.t2m_max
#       FROM climate_wxt2 w
#       WHERE w.date = t.date
#         AND w.latitude  = t.latitude
#         AND w.longitude = t.longitude
#   ), t.t2m_max),
#   ws10 = COALESCE((
#       SELECT w.ws10
#       FROM climate_wxt2 w
#       WHERE w.date = t.date
#         AND w.latitude  = t.latitude
#         AND w.longitude = t.longitude
#   ), t.ws10)
# WHERE EXISTS (
#   SELECT 1 FROM climate_wxt2 w
#   WHERE w.date = t.date
#     AND w.latitude  = t.latitude
#     AND w.longitude = t.longitude
# );
# """)
# conn.commit()


# In[3]:


# import cdsapi



# TMP_DIR   = "Clima\\tmp_test20d"
# CDS_URL   = 'https://cds.climate.copernicus.eu/api'
# CDS_KEY   = 'd9af180c-f7f8-4a2e-8029-09018fb8c920'
# c = cdsapi.Client(url=CDS_URL, key=CDS_KEY)
# # bbox = [N, W, S, E] en grados; ajusta a tu zona
# BBOX = [-31.9, -63.5, -32.6, -63.0]  # aprox VM y alrededores

# c.retrieve(
#     'reanalysis-era5-land',
#     {
#         'variable': [
#             '2m_temperature','2m_dewpoint_temperature',
#             'total_precipitation','10m_u_component_of_wind','10m_v_component_of_wind'
#         ],
#         'year': ['2025'],     # o un rango
#         'month': ['01'],
#         'day': [f'{d:02d}' for d in range(1,32)],
#         'time': [f'{h:02d}:00' for h in range(24)],  # horario
#         'area': BBOX,    # N, W, S, E
#         'format': 'netcdf',
#     },
#     'era5land_vm_2024_2025.nc'
# )


# In[ ]:





# In[4]:


import os, cdsapi, calendar, time
import xarray as xr
import pandas as pd

import os, cdsapi, calendar, time, datetime as dt
import xarray as xr
import pandas as pd

CDS_URL   = 'https://cds.climate.copernicus.eu/api'
CDS_KEY   = 'd9af180c-f7f8-4a2e-8029-09018fb8c920'
c = cdsapi.Client(url=CDS_URL, key=CDS_KEY)


# --- Área (VM +- ~0.1°) ---
BBOX = [-32.3, -63.3, -32.5, -63.1]  # [N, W, S, E]

# --- Variables en 2 grupos para bajar coste por request ---
VAR_GROUPS = [
    ['2m_temperature','2m_dewpoint_temperature','total_precipitation'],

]

OUTDIR = 'data\climate_data'
os.makedirs(OUTDIR, exist_ok=True)

# === Rango temporal ===
START_YEAR = 2021
today = dt.date.today()
END_YEAR  = today.year         # p.ej. 2025
END_MONTH = today.month        # p.ej. 9

def days_in_month_limited(year: int, month: int):
    """Lista de días válidos del mes. Si es el mes actual, corta en 'hoy'."""
    ndays = calendar.monthrange(year, month)[1]
    last_day = ndays
    if year == today.year and month == today.month:
        last_day = min(last_day, today.day)
    return [f'{d:02d}' for d in range(1, last_day + 1)]

def months_for_year(year: int):
    """Meses válidos para ese año (si es el actual: 1..mes_actual)."""
    if year < END_YEAR:
        return list(range(1, 13))
    if year == END_YEAR:
        return list(range(1, END_MONTH + 1))
    return []  # por si acaso

def retrieve_month(year, month, variables, bbox=BBOX, outdir=OUTDIR, tag='grp', retries=3):
    yyyy, mm = f'{year:04d}', f'{month:02d}'
    target = os.path.join(outdir, f'era5land_{yyyy}_{mm}_{tag}.nc')
    if os.path.exists(target):
        print(f'→ Ya existe {target}, salto.')
        return target

    days = days_in_month_limited(year, month)
    if not days:
        print(f'→ Sin días válidos para {yyyy}-{mm}, salto.')
        return None

    req = {
        'product_type': 'reanalysis',
        'format': 'netcdf',
        'variable': variables,
        'year': [yyyy],
        'month': [mm],
        'day': days,
        'time': [f'{h:02d}:00' for h in range(24)],
        'area': bbox,        # [N, W, S, E]
    }
    for attempt in range(retries):
        try:
            print(f"Descargando {yyyy}-{mm} [{tag}] (días={len(days)})…")
            c.retrieve('reanalysis-era5-land', req, target)
            print(f"✔ Guardado {target} ({os.path.getsize(target):,} bytes)")
            return target
        except Exception as e:
            print(f"  ⚠ intento {attempt+1}/{retries} falló: {e}")
            if attempt == retries - 1:
                raise
            time.sleep(15 * (attempt + 1))
    return None

# === 1) Descarga (por mes y grupo) ===
files = []
for y in range(START_YEAR, END_YEAR + 1):
    for m in months_for_year(y):
        for gi, group in enumerate(VAR_GROUPS):
            f = retrieve_month(y, m, group, tag=f'g{gi}')
            if f is not None:
                files.append(f)



# In[5]:


import os, zipfile
import xarray as xr

MAGIC = {
    b'CDF': 'netcdf3',
    b'\x89HDF\r\n\x1a\n': 'netcdf4',
    b'GRIB': 'grib',
    b'PK\x03\x04': 'zip',
    b'<!DOCTYP': 'html',
    b'<html': 'html',
    b'{': 'json',
}

def sniff_kind(path, nbytes=16):
    with open(path, 'rb') as f:
        head = f.read(nbytes)
    for sig, kind in MAGIC.items():
        if head.startswith(sig):
            return kind
    return 'unknown'

def open_cds_file(path, tmpdir=None):
    kind = sniff_kind(path)
    print(f"[sniff] {path} -> {kind}")

    if kind in ('netcdf3','netcdf4'):
        return xr.open_dataset(path, engine='netcdf4')

    if kind == 'grib':
        return xr.open_dataset(path, engine='cfgrib')  # requiere cfgrib/eccodes

    if kind == 'zip':
        if tmpdir is None:
            tmpdir = os.path.join(os.path.dirname(path), "_unzip")
        os.makedirs(tmpdir, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            z.extractall(tmpdir)
            members = z.namelist()
        nc_inside   = [m for m in members if m.lower().endswith('.nc')]
        grib_inside = [m for m in members if m.lower().endswith(('.grib','.grb','.grib2'))]
        if nc_inside:
            return xr.open_dataset(os.path.join(tmpdir, nc_inside[0]), engine='netcdf4')
        if grib_inside:
            return xr.open_dataset(os.path.join(tmpdir, grib_inside[0]), engine='cfgrib')
        raise OSError("ZIP no contiene .nc ni .grib")

    if kind in ('html','json','unknown'):
        with open(path, 'rb') as f:
            txt = f.read(400).decode('utf-8', errors='replace')
        raise OSError(f"El archivo no es NetCDF/GRIB. Primeros bytes:\n{txt[:400]}")



import os, zipfile, uuid, shutil
import xarray as xr

MAGIC = {
    b'CDF': 'netcdf3',
    b'\x89HDF\r\n\x1a\n': 'netcdf4',
    b'GRIB': 'grib',
    b'PK\x03\x04': 'zip',
    b'<!DOCTYP': 'html',
    b'<html': 'html',
    b'{': 'json',
}

def sniff_kind(path, nbytes=16):
    with open(path, 'rb') as f:
        head = f.read(nbytes)
    for sig, kind in MAGIC.items():
        if head.startswith(sig):
            return kind
    return 'unknown'

def open_cds_file(path):
    kind = sniff_kind(path)
    print(f"[sniff] {path} -> {kind}")

    if kind in ('netcdf3', 'netcdf4'):
        ds = xr.open_dataset(path, engine='netcdf4')
        return ds  # cierra con ds.close() cuando termines

    if kind == 'grib':
        ds = xr.open_dataset(path, engine='cfgrib')
        return ds  # cierra con ds.close() cuando termines

    if kind == 'zip':
        base = os.path.splitext(os.path.basename(path))[0]
        tmpdir = os.path.join(os.path.dirname(path), f"_unzip_{base}_{uuid.uuid4().hex}")
        os.makedirs(tmpdir, exist_ok=True)

        # Extraer
        with zipfile.ZipFile(path) as z:
            z.extractall(tmpdir)
            members = z.namelist()

        # Buscar archivo interno
        candidates_nc   = [m for m in members if m.lower().endswith('.nc')]
        candidates_grib = [m for m in members if m.lower().endswith(('.grib', '.grb', '.grib2'))]
        if candidates_nc:
            inner = os.path.join(tmpdir, candidates_nc[0]); engine = 'netcdf4'
        elif candidates_grib:
            inner = os.path.join(tmpdir, candidates_grib[0]); engine = 'cfgrib'
        else:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise OSError("ZIP no contiene .nc ni .grib")

        # Abrir, cargar en memoria y soltar lock
        ds = xr.open_dataset(inner, engine=engine)
        ds.load()  # lee datos a memoria
        shutil.rmtree(tmpdir, ignore_errors=True)  # elimina tmpdir: no hay lock porque ya cargamos
        return ds

    # Si vino HTML/JSON (error del servidor), mostrar primeros bytes
    with open(path, 'rb') as f:
        txt = f.read(400).decode('utf-8', errors='replace')
    raise OSError(f"El archivo no es NetCDF/GRIB. Primeros bytes:\n{txt[:400]}")


def open_file(year,month):
    yyyy, mm = f'{year:04d}', f'{month:02d}'
    # admite que exista solo g0, solo g1, o ambos
    candidates = []

    for g in ['g0']:
        p = os.path.join(OUTDIR, f'era5land_{yyyy}_{mm}_{g}.nc')

        if os.path.exists(p):
            candidates.append(p)
    dss = []
    for path in candidates:
        try:
            ds = open_cds_file(path)  # usa tu función que decide el engine (netcdf4/cfgrib/zip)
            dss.append(ds)

        except Exception as e:
            print(f"[skip] {path}: {e}")


    # print(nc_hourly)

    ds = dss[0].copy()

    # renombra la dimensión de tiempo
    if 'valid_time' in ds.dims:
        ds = ds.rename({'valid_time': 'time'})

    # --- 2) derivar viento y convertir unidades ---
    if {'u10','v10'}.issubset(ds.data_vars):
        ds = ds.assign(ws10=np.hypot(ds['u10'], ds['v10']))  # m/s

    def K_to_C(da): return da - 273.15
    def m_to_mm(da): return da * 1000.0

    if 't2m' in ds: ds['t2m'] = K_to_C(ds['t2m'])
    if 'd2m' in ds: ds['d2m'] = K_to_C(ds['d2m'])

    # --- 3) agregar a diario ---
    # t2m, d2m, ws10: promedio diario; tp: suma diaria (mm/día)
    agg_daily = {}



    # t2m: promedio, mínima y máxima diaria (ya en °C)
    if 't2m' in ds:
        t2m_daily = ds['t2m'].resample(time='1D')
        agg_daily['t2m']     = t2m_daily.mean()
        agg_daily['t2m_min'] = t2m_daily.min()
        agg_daily['t2m_max'] = t2m_daily.max()

    for v in ['t2m','d2m','ws10']:
        if v in ds: agg_daily[v] = ds[v].resample(time='1D').mean()
    if 'tp' in ds:
        tp_daily_m = ds['tp'].resample(time='1D').sum()  # aún en metros
        agg_daily['tp'] = m_to_mm(tp_daily_m)            # ahora mm/día

    ds_day = xr.Dataset(agg_daily).sortby('time')

    # --- 4) a DataFrame "tidy" ---
    df = ds_day.to_dataframe().reset_index()
    df = df.sort_values(['time','latitude','longitude']).reset_index(drop=True)

    return(df)


df_final=pd.DataFrame()
for y in range(START_YEAR, END_YEAR + 1):
    for m in months_for_year(y):
        print(y,m)
        ds = open_file(y,m)
        if ds is not None:
        #     ds1 = xr.open_dataset(ds)
            df_final=pd.concat([df_final,ds])


# In[6]:


df_final.drop("number",axis=1,inplace=True)


# In[7]:


import shutil, os
shutil.rmtree(r"downloads_era5land_0p1_test\_unzip", ignore_errors=True)


# In[8]:


from pathlib import Path
import sqlite3
# from pathlib import Path
# import sqlite3
BASE_DIR = Path().resolve()  

DB_PATH = Path(BASE_DIR).parent / "backend" / "data" / "mi_base_de_datos5.db"

def list_tables(db_path=DB_PATH):
    with sqlite3.connect(db_path) as con:
        cur = con.execute("""
            SELECT name
            FROM sqlite_schema
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        return [r[0] for r in cur.fetchall()]

def ensure_table(df, name="climate_data"):
    # crea la tabla si no existe, usando el schema de df pero sin insertar filas
    with sqlite3.connect(DB_PATH) as con:
        df.head(0).to_sql(name, con, if_exists="append", index=False)

def write_df(df, name="climate_data"):
    # inserta el dataframe (append)
    with sqlite3.connect(DB_PATH) as con:
        df.to_sql(name, con, if_exists="append", index=False, method="multi", chunksize=1000)

# uso
ensure_table(df_final)      # 0) crea "climate_data" si no existe
write_df(df_final)          # 1) mete el dataframe ahí


# In[9]:


def drop_tables(tables, db_path=DB_PATH):
    if not tables:
        return
    with sqlite3.connect(db_path) as con:
        con.execute("PRAGMA foreign_keys=ON")
        for t in tables:
            if t.startswith("sqlite_"):
                continue  # nunca borres internas
            con.execute(f'DROP TABLE IF EXISTS "{t}"')
        con.commit()

# ejemplo:
to_drop = ["climate_test"]
drop_tables(to_drop)
print(list_tables())

