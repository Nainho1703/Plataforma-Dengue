#!/usr/bin/env python
# coding: utf-8

# In[1]:


import sqlite3
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
import time
import difflib
import overpy
import warnings
import numpy as np
import unicodedata

warnings.filterwarnings("ignore")


def esta_en_villa_maria(lat, lon):
    return (-33 <= lat <= -29) and (-65 <= lon <= -63)

geolocator = Nominatim(user_agent="vm_dengue_mapper", timeout=20)
# Función con backoff progresivo y control de errores
def geocode_direccion(direccion, max_retries=5):
    delay = 2
    for intento in range(1, max_retries + 1):
        try:
            # print(f"[BUSCANDO] {direccion} (intento {intento})")
            time.sleep(delay)
            return geolocator.geocode(direccion)
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            print(f"[REINTENTO] {direccion} → {str(e)}")
            time.sleep(delay)
            delay *= 2  # Exponencial: 2, 4, 8...
        except Exception as e:
            print(f"[FALLO FATAL] {direccion} → {str(e)}")
            break
    return None



# — Obtención de la lista de calles con Overpass —
api = overpy.Overpass()
query = """
area["boundary"="administrative"]["name"="Villa María"]["admin_level"="8"]->.searchArea;
way["highway"]["name"](area.searchArea);
out;
"""
result = api.query(query)
calles = sorted({ way.tags["name"] for way in result.ways if "name" in way.tags })
import unicodedata
def normalize(texto: str) -> str:
    """
    Quita acentos y otros diacríticos, pero preserva la ñ, y convierte a mayúsculas.
    """
    # 1. Descomponer en NFKD (“ñ” para ñ, “á” para á, etc.)
    nfkd = unicodedata.normalize('NFKD', texto)
    out_chars = []
    prev = None

    for c in nfkd:
        if unicodedata.combining(c):
            # Sólo dejamos la tilde (~) si va sobre una 'n' o 'N'
            if c == '\u0303' and prev and prev.lower() == 'n':
                out_chars.append(c)
            # resto de diacríticos los descartamos
        else:
            out_chars.append(c)
            prev = c

    # 2. Unir, pasar a mayúsculas y recomponer (NFC) para que 'N'+~ vuelva a ser 'Ñ'
    result = ''.join(out_chars).upper()
    return unicodedata.normalize('NFC', result)

def buscar_calle_similar(texto, lista_calles, n=5, cutoff=0.6):
    # Normalizamos lista de calles
    originales = lista_calles
    normalized_calles = [normalize(c) for c in originales]
    target = normalize(texto)
    # Buscamos coincidencias en la forma normalizada
    matches = difflib.get_close_matches(target, normalized_calles, n=n, cutoff=cutoff)
    # Reconstruimos los nombres con acento original
    return [ originales[normalized_calles.index(m)] for m in matches ]

def procesar_coordenadas(df, lon_col='lon', lat_col='lat', wkt_col='WKT'):
    # 1. Detectar filas donde 'lon' contiene dos valores separados por coma
    mask = df[lon_col].astype(str).str.contains(',', na=False)

    # 2. Si no hay ninguna fila con coma, devolvemos el df sin cambios
    if not mask.any():
        return df

    # 3. Split y renombrado de columnas temporales


    split = (
        df.loc[mask, lon_col]
          .astype(str)
          .str.split(',', expand=True)
          .rename(columns={0: lat_col, 1: lon_col})
    )

    # 4. Limpiar espacios y convertir a float
    split[lat_col] = split[lat_col].str.replace('"','').str.strip().astype(float)
    split[lon_col] = split[lon_col].str.replace('"','').str.strip().astype(float)

    # 5. Asignar de vuelta al df original
    df.loc[mask, lat_col] = split[lat_col]
    df.loc[mask, lon_col] = split[lon_col]

    # 6. Generar la columna WKT
    df[wkt_col] = df.apply(
        lambda row: f"POINT({row[lon_col]} {row[lat_col]})"
                    if pd.notna(row[lon_col]) and pd.notna(row[lat_col])
                    else pd.NA,
        axis=1
    )

    return df
def geocode_intersection_op(street1, street2, area_name="Villa María"):
    query = f"""
    area["boundary"="administrative"]["name"="{area_name}"]->.a;
    way(area.a)["highway"]["name"="{street1}"]->.w1;
    way(area.a)["highway"]["name"="{street2}"]->.w2;
    node(w1.w2)->.n;
    out body n 1;
    """
    try:
        res = api.query(query)
        if res.nodes:
            n = res.nodes[0]
            return float(n.lat), float(n.lon)
    except Exception:
        pass
    return None
def is_intersection(addr):
    a = addr.lower()
    return " y " in a or " esq. " in a or " esq " in a

def split_intersection(addr):
    low = addr.lower()
    if " y " in low:
        parts = low.split(" y ", 1)
    elif " esq. " in low:
        parts = low.split(" esq. ", 1)
    else:
        parts = low.split(" esq ", 1)
    print(parts)
    return parts[0].strip().capitalize(), parts[1].strip().capitalize()

import numpy as np
import re


def asignar_location(location,df,idx,dir_raw,mensaje=0):
    lat = location.latitude
    lon = location.longitude

    if not esta_en_villa_maria(lat, lon):
        print(f"[ERROR GEO] Coordenadas fuera de Villa María: {dir_raw} → Lat: {lat}, Lon: {lon}")


    wkt = f"POINT({lon} {lat})"
    df.at[idx, 'lat'] = lat
    df.at[idx, 'lon'] = lon
    df.at[idx, 'WKT'] = wkt
    if mensaje==1:
        print(f"[ENCONTRADA] Dirección 2: {dir_raw} → Lat: {lat}, Lon: {lon}")
    else:
        print(f"[ENCONTRADA] Dirección: {dir_raw} → Lat: {lat}, Lon: {lon}")
    return df
def evaluar_direccion(df,columna_direccion="DIRECCION"):

    # Inicializar geocoder

    if "lon" not in df.columns:
        df["lon"]=np.nan
    # Filas con lon vacía
    faltantes = df[df['lon'].isna()].copy()

    # Si no hay una columna de dirección clara, asumimos una posible:

    contador=0

    reemplazos={'TTE.':'TENIENTE','INT':'INTENDENTE',"MEJICO":"MEXICO",'Antonio Hosch':'Enrique Antonio Hoch','Enrique A. Hoch':'Enrique Antonio Hoch',
                'T. PEÑA':"INTENDENTE PEÑA","EEUU":"ESTADOS UNIDOS",'BV ALVEAR':'Boulevard Marcelo T. de Alvear','CTDA. ': ""}
    for idx, row in faltantes.iterrows():
        contador += 1
        dir_raw = row[columna_direccion]
        print(contador)
        dir_raw=dir_raw.upper()
        if not isinstance(dir_raw, str) or dir_raw.strip() == "" \
        or "ZONA RURAL" in dir_raw.upper() \
        or "NO HAY" in dir_raw.upper() or "SIN D" in dir_raw.upper() or "NO SE E" in dir_raw.upper() or r"S/D" in dir_raw.upper() \
        or r"NO TIENE" in dir_raw.upper():
            continue

        for k, v in reemplazos.items():
            if k in dir_raw:
                dir_raw = dir_raw.replace(k, v, 1)  # solo el primero que aparezca


        base = dir_raw + ", Villa María, Córdoba, Argentina"

        location = geocode_direccion(base)

        if location:
            df=asignar_location(location,df,idx,dir_raw)



        else:
            # Extraemos el nombre bruto de la calle
            street = dir_raw.split(',')[0].strip()

            similares = buscar_calle_similar(street, calles, n=5, cutoff=0.6)               


            if similares:
                for calle in similares:
                    intento = f"{calle}, Villa María, Córdoba, Argentina"
                    loc2 = geocode_direccion(intento)
                    if loc2 and esta_en_villa_maria(loc2.latitude, loc2.longitude):
                        df.at[idx, 'lat'] = loc2.latitude
                        df.at[idx, 'lon'] = loc2.longitude
                        df.at[idx, 'WKT'] = f"POINT({loc2.longitude} {loc2.latitude})"
                        print(f"[ENCONTRADA POR SIMILARIDAD] {street} → {calle}: {intento} con LON {loc2.longitude} y LAT {loc2.latitude}")
                        break

                    # 2) Si no hubo match y es posible esquina, lo intentamos por Overpass

            elif is_intersection(dir_raw):
                print("Intersección",dir_raw)
                street1, street2 = split_intersection(dir_raw)
                location = geocode_direccion(street2)
                if location:
                    df=asignar_location(location,df,idx,street2)
                else:
                    inter = geocode_intersection_op(re.sub(r'\d+', '', street1), re.sub(r'\d+', '', street2))
                    print(inter,street1, street2)
                    if inter and esta_en_villa_maria(*inter):
                        lat, lon = inter
                        df.at[idx, 'lat'], df.at[idx, 'lon'] = lat, lon
                        df.at[idx, 'WKT'] = f"POINT({lon} {lat})"
                        print(f"[ENCONTRADA POR INTERSECCION] {street} → {inter}: con LON {loc2.longitude} y LAT {loc2.latitude}")
                        continue


            else:
                print(f"[NO ENCONTRADA] Ninguna similar válida para '{street}'")

    return(df)






# In[8]:


# if 'df_casos_conf' not in locals():   # existe en el scope local

#     ruta_excel = r"data\raw\No utiles\notificaciones dengue Villa María 23-24.xlsx"
#     df0 = pd.read_excel(ruta_excel)

#     ruta_excel = r"data\raw\No utiles\Notificaciones dengue Villa María 24-25.xlsx"
#     df1 = pd.read_excel(ruta_excel)
#     df_casos=pd.concat([df0,df1])

#     cols_utiles=['sexo',"edad_diagnostico","calle_domicilio","numero_domicilio","fecha_apertura",'clasificacion_manual']
#     df_casos=df_casos[cols_utiles]

#     # df=procesar_coordenadas(df)
#     df_casos_conf=df_casos.loc[(df_casos["clasificacion_manual"].str.contains("confirmado"))|
#                             (df_casos["clasificacion_manual"].str.contains("Caso de Dengue en brote con laboratorio"))]

#     df_casos_conf["DIRECCION"]=df_casos_conf["calle_domicilio"]+" "+df_casos_conf["numero_domicilio"]+", Villa María, Córdoba"
#     df_casos_conf=df_casos_conf.drop(["calle_domicilio","numero_domicilio","clasificacion_manual"],axis=1)
#     df_casos_conf.head()


from pathlib import Path
import pandas as pd

from pathlib import Path
import pandas as pd

from pathlib import Path
import pandas as pd

def cargar_casos_confirmados(
    dirpath_real="data/raw/casos_raw",        # carpeta con datos reales
    dirpath_samples="data/raw/samples",       # carpeta con SAMPLES (toda la carpeta)
    ciudad="Villa María, Córdoba",
    usecols=('sexo','edad_diagnostico','calle_domicilio','numero_domicilio','fecha_apertura','clasificacion_manual'),
    confirm_patterns=("confirmado", "caso de dengue en brote con laboratorio"),
):
    """
    1) Busca TODOS los archivos en 'dirpath_real' (xlsx/csv).
    2) Si no hay, busca TODOS los archivos en 'dirpath_samples' (xlsx/csv).
       (No un archivo llamado 'sample': recorre toda la carpeta y subcarpetas).
    3) Concatena, filtra confirmados y arma DIRECCION.
    4) Devuelve (DataFrame, etiqueta) con etiqueta ∈ {'real','_sample'}.
    """

    exts_ok = {".csv", ".xlsx", ".xls", ".xlsm"}

    def list_all_files(base_dir: str):
        base = Path(base_dir)
        if not base.exists():
            return []
        # rglob para recorrer subcarpetas; filtra por extensión válida y descarta temporales
        files = [
            p for p in base.rglob("*")
            if p.is_file()
            and p.suffix.lower() in exts_ok
            and not p.name.startswith("~$")      # evita archivos temporales de Excel
        ]
        # orden estable por ruta
        return sorted(files, key=lambda p: str(p).lower())

    def read_any(files):
        dfs = []
        for f in files:
            suff = f.suffix.lower()
            if suff in {".xlsx", ".xls", ".xlsm"}:
                df = pd.read_excel(
                    f,
                    sheet_name=0,
                    usecols=list(usecols),
                    engine="openpyxl",
                    dtype={"numero_domicilio": "string"},
                )
            elif suff == ".csv":
                df = pd.read_csv(
                    f,
                    usecols=list(usecols),
                    dtype={"numero_domicilio": "string"},
                    encoding="utf-8"
                )
            else:
                continue
            dfs.append(df)
        return dfs

    # -------- intenta reales primero --------
    files_real = list_all_files(dirpath_real)
    etiqueta = None
    dfs = []

    if files_real:
        dfs = read_any(files_real)
        etiqueta = "real"
    else:
        files_samples = list_all_files(dirpath_samples)
        if not files_samples:
            raise FileNotFoundError(
                "No se encontraron archivos válidos.\n"
                f"- Reales en: {Path(dirpath_real).resolve()}\n"
                f"- Samples en: {Path(dirpath_samples).resolve()}\n"
                "Se aceptan: CSV, XLSX, XLS, XLSM (se recorren todas las subcarpetas)."
            )
        dfs = read_any(files_samples)
        etiqueta = "sample"

    df_all = pd.concat(dfs, ignore_index=True)

    # -------- filtro confirmados --------
    clasif = df_all["clasificacion_manual"].fillna("").astype(str).str.casefold()
    mask = pd.Series(False, index=df_all.index)
    for pat in confirm_patterns:
        mask |= clasif.str.contains(str(pat).casefold())
    df = df_all.loc[mask, list(usecols)].copy()

    # -------- DIRECCION --------
    df["calle_domicilio"] = df["calle_domicilio"].fillna("").astype("string").str.strip()
    df["numero_domicilio"] = df["numero_domicilio"].fillna("").astype("string").str.strip()
    df["DIRECCION"] = (
        (df["calle_domicilio"] + " " + df["numero_domicilio"])
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        + (", " + ciudad)
    )

    df["etiqueta"] = etiqueta
    df.drop(columns=["calle_domicilio", "numero_domicilio", "clasificacion_manual"], inplace=True)
    return df, etiqueta


# ejemplo:
df_casos_conf,label = cargar_casos_confirmados()
df_casos_conf.head()

print(f'utilizando_{label}')

ruta_excel_cc = rf"data\raw\casos_procesados\casos_direccion_{label}.xlsx"
casos_correctos = pd.read_excel(ruta_excel_cc)



df_sacar=pd.merge(df_casos_conf,casos_correctos[["DIRECCION","WKT"]],on="DIRECCION",how="left")   
lista=list(casos_correctos.loc[~casos_correctos["WKT"].isnull(),"DIRECCION"]) # aqui obtenemos los que WKT vacio, es decir que tengan una dirección con  lon, lat 
df_revisar=df_casos_conf.loc[~df_casos_conf["DIRECCION"].isin(lista)]
vacios=df_casos_conf.loc[df_casos_conf["DIRECCION"].isnull()]
print("A confirmar",len(lista),"casos")
df2=evaluar_direccion(df_revisar)
df2


# In[ ]:


df44=df2.loc[~df2["lon"].isnull()]

df_final=pd.concat([casos_correctos,df44]).reset_index(drop=True)
df_final.to_excel(ruta_excel_cc, index=False)


# In[ ]:


import winsound

# Beep sencillo: frecuencia 1 kHz durante 500 ms

def hacer_sonido():
    winsound.Beep(1000, 1300)

hacer_sonido()


# In[ ]:


import overpy

api = overpy.Overpass()
query = """
area["boundary"="administrative"]["name"="Villa María"]["admin_level"="8"]->.searchArea;
way["highway"]["name"](area.searchArea);
out;
"""
result = api.query(query)

# extraer nombres únicos
calles_villa_maria = sorted({ way.tags["name"] for way in result.ways if "name" in way.tags })


# In[ ]:


api = overpy.Overpass()
query = """
area["boundary"="administrative"]["name"="Villa Nueva"]["admin_level"="8"]->.searchArea;
way["highway"]["name"](area.searchArea);
out;
"""
result = api.query(query)

# extraer nombres únicos
calles_villa_nueva = sorted({ way.tags["name"] for way in result.ways if "name" in way.tags })

