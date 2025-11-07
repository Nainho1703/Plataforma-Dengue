#!/usr/bin/env python
# coding: utf-8

# In[3]:


# pip install requests beautifulsoup4 pandas geopandas rapidfuzz folium shapely

import re, time, json, csv
import requests
import pandas as pd
import geopandas as gpd
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode
from shapely.geometry import Point, LineString
import folium
from rapidfuzz import fuzz, process

HEADERS = {"User-Agent": "vm-scraper/1.0 (contact: you@example.com)"}

# ---------- 1) SCRAPE: paradas + horarios + recorrido textual ----------
def parse_transbus(url: str):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # a) paradas + horarios (tabla)
    stops = []
    # la tabla suele tener 'Paradas' en un h2/h3 justo arriba
    paradas_header = soup.find(lambda tag: tag.name in ["h2","h3"] and "Paradas" in tag.get_text(strip=True))
    tabla = paradas_header.find_next("table") if paradas_header else soup.find("table")
    if tabla:
        for tr in tabla.select("tbody tr"):
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if not tds:
                continue
            nombre = tds[0]
            # el resto son horarios (normaliza 06.20 -> 06:20)
            times = []
            for t in tds[1:]:
                t = re.sub(r"(\d{1,2})[.:h](\d{2})", r"\1:\2", t)
                if re.match(r"^\d{1,2}:\d{2}$", t):
                    times.append(t)
            stops.append({"stop_name": nombre, "times": times})

    # b) recorrido (bloque de texto)
    recorrido_text = ""
    rec_header = soup.find(lambda tag: tag.name in ["h2","h3"] and "Recorrido" in tag.get_text(strip=True))
    if rec_header:
        # toma hasta el próximo encabezado o párrafo grande
        nxt = rec_header.find_next(lambda tag: tag.name in ["p","div","ul"])
        if nxt:
            recorrido_text = nxt.get_text(" ", strip=True)

    # dividir recorrido por guiones / puntos y limpiar
    recorrido_list = [seg.strip(" .–—-") for seg in re.split(r"\s*[-–—]\s*", recorrido_text) if seg.strip()]

    return {"stops": stops, "recorrido_text": recorrido_text, "recorrido_list": recorrido_list}






# pip install requests beautifulsoup4 pandas geopandas folium shapely rapidfuzz

import re, time, json, pandas as pd, geopandas as gpd
from bs4 import BeautifulSoup
from shapely.geometry import Point, LineString
import requests, folium
from urllib.parse import urlencode

UA = {"User-Agent": "vm-bus/1.0"}

def parse_transbus(url: str):
    s = BeautifulSoup(requests.get(url, headers=UA, timeout=30).text, "html.parser")

    # tabla Paradas
    paradas_hdr = s.find(lambda t: t.name in ["h2","h3"] and "Paradas" in t.get_text(strip=True))
    table = paradas_hdr.find_next("table") if paradas_hdr else s.find("table")
    stops = []
    if table:
        for tr in table.select("tbody tr"):
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if not tds: continue
            name = tds[0]
            times = []
            for t in tds[1:]:
                t = re.sub(r"(\d{1,2})[.:h](\d{2})", r"\1:\2", t)
                if re.fullmatch(r"\d{1,2}:\d{2}", t): times.append(t)
            stops.append({"stop_name": name, "times": times})

    # recorrido textual
    rec_hdr = s.find(lambda t: t.name in ["h2","h3"] and "Recorrido" in t.get_text(strip=True))
    rec_txt = rec_hdr.find_next(["p","div","ul"]).get_text(" ", strip=True) if rec_hdr else ""
    rec_list = [seg.strip(" .–—-") for seg in re.split(r"\s*[-–—]\s*", rec_txt) if seg.strip()]
    return stops, rec_txt, rec_list

def geocode_nominatim(q, hint="Villa María, Córdoba, Argentina"):
    url = "https://nominatim.openstreetmap.org/search?" + urlencode(
        {"q": f"{q}, {hint}", "format":"jsonv2", "limit":1})
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    j = r.json()
    return (float(j[0]["lat"]), float(j[0]["lon"])) if j else None

def osrm_route(lonlat_list):  # [(lon,lat),...]
    if len(lonlat_list) < 2: return None
    p = ";".join([f"{x:.6f},{y:.6f}" for x,y in lonlat_list])
    r = requests.get(f"https://router.project-osrm.org/route/v1/driving/{p}?overview=full&geometries=geojson",
                     headers=UA, timeout=30)
    j = r.json()
    if not j.get("routes"): return None
    coords = j["routes"][0]["geometry"]["coordinates"]
    return LineString([(x,y) for x,y in coords])

URL = "https://www.trans-bus.com.ar/recorridos/linea-h1-rojo/"  # <- cambia acá

stops, rec_txt, rec_list = parse_transbus(URL)
print("paradas:", len(stops))

# geocode
rows = []
for s in stops:
    latlon = geocode_nominatim(s["stop_name"]); time.sleep(1)
    if latlon: rows.append({**s, "lat": latlon[0], "lon": latlon[1]})
df = pd.DataFrame(rows)
gdf = gpd.GeoDataFrame(df, geometry=[Point(xy[1], xy[0]) for xy in zip(df["lat"], df["lon"])], crs=4326)

# export
gdf.drop(columns="geometry").to_csv("paradas.csv", index=False)
gdf.to_file("paradas.geojson", driver="GeoJSON")
open("recorrido.txt","w",encoding="utf-8").write(rec_txt)

# ruta OSRM (aprox.)
route = osrm_route([(p.x, p.y) for p in gdf.geometry])

# mapa
m = folium.Map(location=[gdf.geometry.y.mean(), gdf.geometry.x.mean()], zoom_start=13)
for _, r in gdf.iterrows():
    folium.CircleMarker([r.geometry.y, r.geometry.x], radius=5, fill=True,
                        tooltip=f'{r["stop_name"]}\n{", ".join((r["times"] or [])[:6])}').add_to(m)
if route:
    folium.GeoJson(gpd.GeoSeries([route], crs=4326).__geo_interface__,
                   name="Ruta", style_function=lambda f: {"weight":5, "opacity":0.9}).add_to(m)
folium.LayerControl().add_to(m)
m.save("linea.html")
print("OK -> paradas.csv / paradas.geojson / recorrido.txt / linea.html")


# In[21]:


import requests
from bs4 import BeautifulSoup
import pandas as pd

url = "https://www.trans-bus.com.ar/recorridos/linea-h1-rojo/"



def scrapear_horarios(url):
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()

    # intenta lxml, si no existe usa html.parser
    for parser in ("lxml", "html.parser"):
        try:
            soup = BeautifulSoup(r.text, parser)
            break
        except Exception:
            continue

    table = soup.select_one("table.tabla-horarios")
    assert table, "No encontré <table class='tabla-horarios'>"

    # headers
    ths = table.select("thead th")
    headers = [th.get_text(strip=True) for th in ths] or \
            [c.get_text(strip=True) for c in table.select("tr:first-child th, tr:first-child td")]

    # rows
    rows = []
    for tr in table.select("tbody tr") or table.select("tr")[1:]:
        cells = [td.get_text(strip=True) for td in tr.select("td, th")]
        if any(cells):
            rows.append(cells[:len(headers)])
    try:

        df0 = pd.DataFrame(rows, columns=headers[:len(rows[0])])

        df=df0.copy()
        df=df.rename(columns={"":"X"})
        df=df.drop("X",axis=1)
        df


        # 1) Guarda los nombres actuales
        old_cols = df.columns.tolist()

        # 2) Renombra columnas: Paraderos, B1..Bn
        new_cols = ['Paraderos'] + [f'B{i}' for i in range(1, len(old_cols))]
        df.columns = new_cols

        # 3) Inserta como primera fila los nombres antiguos, ya alineados a los nuevos
        header_row = pd.DataFrame([old_cols], columns=new_cols)
        df = pd.concat([header_row, df], ignore_index=True)
    except:
        df=pd.DataFrame()
        print("error")
    return(df)


# In[42]:


# pip install requests beautifulsoup4 lxml geopandas shapely folium pandas

import re, json, requests, pandas as pd, geopandas as gpd, folium
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from shapely.geometry import Point, LineString
from lxml import etree

UA = {"User-Agent": "mymaps-scraper/1.0"}

def get_mid_from_page(page_url: str) -> str:
    """Busca el iframe de My Maps y extrae 'mid'."""
    html = requests.get(page_url, headers=UA, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")
    iframe = soup.find("iframe", src=re.compile(r"/maps/d/embed"))
    if not iframe:
        raise ValueError("iframe de My Maps no encontrado")
    q = parse_qs(urlparse(iframe["src"]).query)
    if "mid" not in q:
        raise ValueError("no se encontró parámetro 'mid' en el iframe")
    return q["mid"][0]

def download_kml(mid_or_page: str) -> bytes:
    """Acepta un mid o una URL de página; devuelve KML en bytes."""
    if mid_or_page.startswith("http"):
        mid = get_mid_from_page(mid_or_page)
    else:
        mid = mid_or_page
    kml_url = f"https://www.google.com/maps/d/kml?mid={mid}&forcekml=1"
    r = requests.get(kml_url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.content

def parse_kml(kml_bytes: bytes):
    """Devuelve dos GeoDataFrames: puntos (paradas) y líneas (recorridos)."""
    ns = {
        "kml": "http://www.opengis.net/kml/2.2",
        "gx": "http://www.google.com/kml/ext/2.2",
        "atom": "http://www.w3.org/2005/Atom",
    }
    root = etree.fromstring(kml_bytes)

    def text(el, path):  # helper
        x = el.find(path, ns)
        return x.text if x is not None and x.text is not None else None

    pts, lns = [], []
    for pm in root.findall(".//kml:Placemark", ns):
        name = text(pm, "kml:name")
        desc = text(pm, "kml:description")  # suele traer HTML con observaciones
        # ExtendedData → dict
        attrs = {}
        for data in pm.findall(".//kml:ExtendedData/kml:Data", ns):
            k = data.get("name")
            v = text(data, "kml:value")
            if k:
                attrs[k] = v

        # geometry
        point = pm.find(".//kml:Point/kml:coordinates", ns)
        lines = pm.findall(".//kml:LineString/kml:coordinates", ns)

        if point is not None:
            lon, lat, *_ = [float(x) for x in point.text.strip().split(",")]
            pts.append({"name": name, "description": desc, **attrs, "geometry": Point(lon, lat)})
        elif lines:
            coords = []
            for seg in lines:
                for trip in seg.text.strip().split():
                    lon, lat, *_ = [float(x) for x in trip.split(",")]
                    coords.append((lon, lat))
            if coords:
                lns.append({"name": name, "description": desc, **attrs, "geometry": LineString(coords)})

    gdf_pts = gpd.GeoDataFrame(pts, geometry="geometry", crs="EPSG:4326") if pts else gpd.GeoDataFrame(columns=["geometry"], crs=4326)
    gdf_lns = gpd.GeoDataFrame(lns, geometry="geometry", crs="EPSG:4326") if lns else gpd.GeoDataFrame(columns=["geometry"], crs=4326)
    return gdf_pts, gdf_lns

def export_and_map(gdf_pts, gdf_lns, prefix="mymaps"):
    if len(gdf_pts): 
        gdf_pts.to_file(f"data\external\infra y mov\paradas\{prefix}_paradas.geojson", driver="GeoJSON")
        gdf_pts.drop(columns="geometry").to_csv(f"{prefix}_paradas.csv", index=False)
    # if len(gdf_lns):
    #     gdf_lns.to_file(f"{prefix}_lineas.geojson", driver="GeoJSON")

    # # Folium
    # center = [-32.41, -63.24]
    # if len(gdf_pts):
    #     center = [gdf_pts.geometry.y.mean(), gdf_pts.geometry.x.mean()]
    # elif len(gdf_lns):
    #     center = [gdf_lns.geometry.representative_point().y.mean(),
    #               gdf_lns.geometry.representative_point().x.mean()]
    # m = folium.Map(location=center, zoom_start=13, control_scale=True)
    # if len(gdf_lns):
    #     folium.GeoJson(
    #         gdf_lns.__geo_interface__,
    #         name="Recorrido",
    #         style_function=lambda f: {"weight": 5, "opacity": 0.9}
    #     ).add_to(m)
    # if len(gdf_pts):
    #     for _, r in gdf_pts.iterrows():
    #         obs = (r.get("description") or "").strip()
    #         folium.CircleMarker(
    #             [r.geometry.y, r.geometry.x], radius=5, fill=True,
    #             tooltip=r.get("name", "Parada"),
    #             popup=obs[:800]  # observaciones/HTML (recortado)
    #         ).add_to(m)
    # folium.LayerControl().add_to(m)
    # m.save(f"{prefix}_mapa.html")
    # return f"{prefix}_mapa.html"

# =============== USO ===============
# 1) Si tenés la página que incrusta My Maps (la de tu screenshot):
PAGE_URL = "https://www.trans-bus.com.ar/recorridos/linea-g1-gris-16b/"  # <- poné la tuya

# 2) O, si ya sabés el MID directo:
# MID = "1AbCdEFgHiJkLMNOPqrStuVWxyz12345"

lineas_link=pd.read_excel('data\external\infra y mov\lineas_link.xlsx')
for i in lineas_link.index:
    url=lineas_link.iloc[i]["Link"]
    linea=lineas_link.iloc[i]["Linea"]

    # dic_horarios[linea]=scrapear_horarios(url)
    try:
        kml = download_kml(url)   # o download_kml(MID)
        pts, lns = parse_kml(kml)
        html = export_and_map(pts, lns, prefix="linea_"+str(linea))
        print("Listo:",
            len(pts), "paradas |",
            len(lns), "tramos de línea |",
            "mapa ->", html)
        print(i,linea,"Exito")
    except:
        print(i,linea,"Error")


# In[45]:


# pip install geopandas shapely pandas numpy rapidfuzz folium fiona

from pathlib import Path
import re, numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge
from rapidfuzz import process, fuzz
import folium

# ====== RUTAS (cambiá a tus paths) ======
DIR_PARADAS = Path(r"data\external\infra y mov\paradas omnibus")   # carpeta con paradas_*.shp/geojson o un único SHP
DIR_LINEAS  = Path(r"data\external\infra y mov\lineas")            # carpeta con linea_*.shp/geojson (trazas)
FILE_ZONAS  = Path(r"data\external\infra y mov\Capa de Municercas\NuevaDistribucion2024.shp")  # SHP de zonas

# ====== helpers ======
def read_all_vectors(folder: Path, patterns=("*.shp","*.geojson")) -> gpd.GeoDataFrame:
    parts=[]
    for pat in patterns:
        for f in folder.glob(pat):
            g = gpd.read_file(f)
            g["__src__"] = f.stem
            parts.append(g)
    if not parts:
        raise FileNotFoundError(f"no encontré vectores en {folder}")
    gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)
    if gdf.crs is None: gdf.set_crs(4326, inplace=True)
    else: gdf = gdf.to_crs(4326)
    return gdf

def read_one_vector(path: Path) -> gpd.GeoDataFrame:
    g = gpd.read_file(path)
    if g.crs is None: g.set_crs(4326, inplace=True)
    else: g = g.to_crs(4326)
    return g

def pick_col(gdf, regexes):
    for rx in regexes:
        for c in gdf.columns:
            if re.search(rx, c, re.I): return c
    return None

def normalize_key(s):
    s = str(s)
    s = s.lower()
    s = s.replace("línea","linea").replace(" ", "_")
    s = re.sub(r"[^a-z0-9_]+","", s)
    s = re.sub(r"^linea_?","", s)   # deja solo el identificador
    return s

def merge_line_geom(g):
    geom = g.unary_union
    if isinstance(geom, (MultiLineString,)):
        try: return linemerge(geom)
        except Exception: return LineString([pt for ln in geom for pt in ln.coords])
    return geom

def order_stops_along(line_geom, stops_gdf):
    mvals = [line_geom.project(p) for p in stops_gdf.geometry]
    dists = [p.distance(line_geom) for p in stops_gdf.geometry]
    out = stops_gdf.copy()
    out["m"] = mvals
    out["dist_to_line"] = dists
    return out.sort_values("m")

# ====== 1) leer datos ======
stops = read_all_vectors(DIR_PARADAS)                         # todos los puntos
zones = read_one_vector(FILE_ZONAS)
lines = read_all_vectors(DIR_LINEAS, patterns=("*.shp","*.geojson"))

# detectar columnas
col_line_stops = pick_col(stops, [r"^linea$", r"route|line|servicio|grupo"])
if col_line_stops is None:
    # intenta inferir desde nombre de archivo
    stops["linea"] = stops["__src__"].str.extract(r"(linea_[^._]+)", expand=False).fillna(stops["__src__"])
    col_line_stops = "linea"
else:
    stops["linea"] = stops[col_line_stops].astype(str)

# para líneas (si traen columna de línea)
col_line_lines = pick_col(lines, [r"^linea$", r"route|line|servicio"])
if col_line_lines is None:
    lines["linea"] = lines["__src__"].str.extract(r"(linea_[^._]+)", expand=False).fillna(lines["__src__"])
else:
    lines["linea"] = lines[col_line_lines].astype(str)

# normalizar claves para matcheo
stops["__k__"] = stops["linea"].apply(normalize_key)
lines["__k__"] = lines["linea"].apply(normalize_key)

# decidir campo de nombre de zona
# --- leer zonas y usar SIEMPRE la etiqueta "Nombre" ---
zones = read_one_vector(FILE_ZONAS)

# normalizo encabezados por si vienen con espacios
zones.columns = [str(c).strip() for c in zones.columns]

if "Nombre" not in zones.columns:
    raise KeyError(f'El shapefile no tiene la columna "Nombre". Columnas: {list(zones.columns)}')

# renombro a 'zona', limpio y uno geometrias duplicadas (mismo nombre)
zones = zones.rename(columns={"Nombre": "zona"})[["zona", "geometry"]]
zones["zona"] = zones["zona"].astype(str).str.strip()

# si hay varias features con el mismo nombre de zona -> disolver
zones = zones.dissolve(by="zona", as_index=False)

# ====== 2) OD por línea ======
pairs = []

# index de líneas por clave normalizada (puede haber varias features por línea)
dict_lines = {k: g for k, g in lines.groupby("__k__")}

for k, gstop in stops.groupby("__k__"):
    # seleccionar traza correspondiente (fuzzy si no hay clave exacta)
    if k in dict_lines:
        gline = dict_lines[k]
    else:
        cand, score, idx = process.extractOne(k, list(dict_lines.keys()), scorer=fuzz.WRatio)
        if score < 70:  # muy distinto -> skip
            print(f"[WARN] sin traza para '{k}'")
            continue
        gline = dict_lines[cand]

    # unificar traza y ordenar paradas
    line_geom = merge_line_geom(gline)
    gstop = gstop[gstop.geometry.notna()].copy()
    if gstop.empty: continue
    gstop = order_stops_along(line_geom, gstop)

    # asignar zona (within -> fallback intersects)
    sjoin = gpd.sjoin(gstop, zones, how="left", predicate="within")
    if sjoin["zona"].isna().mean() > 0.3:
        sjoin = gpd.sjoin(gstop, zones, how="left", predicate="intersects")

    # peso por frecuencia: si existe 'times' cuenta horarios, sino 1
    if "times" in sjoin.columns:
        def _count(x):
            if isinstance(x, list): return len(x)
            if isinstance(x, str): return len(re.findall(r"\d{1,2}:\d{2}", x))
            return np.nan
        base_w = float(pd.Series(sjoin["times"]).apply(_count).dropna().median() or 1.0)
    else:
        base_w = 1.0

    # pares OD consecutivos (omitimos zona idéntica)
    s = sjoin.reset_index(drop=True)
    for i in range(len(s)-1):
        o, d = s.loc[i,"zona"], s.loc[i+1,"zona"]
        if pd.isna(o) or pd.isna(d) or o == d: 
            continue
        pairs.append({"o": o, "d": d, "w": base_w, "linea": s.loc[i,"linea"]})

if not pairs:
    raise SystemExit("No se generaron pares OD (revisá columnas/paths).")

od = pd.DataFrame(pairs).groupby(["o","d"], as_index=False)["w"].sum()

# ====== 3) matrices ======
Z = sorted(set(od["o"]).union(set(od["d"])))
M = pd.DataFrame(0.0, index=Z, columns=Z)
for _, r in od.iterrows():
    M.loc[r["o"], r["d"]] += r["w"]

row_sum = M.sum(axis=1).replace(0, np.nan)
P = M.div(row_sum, axis=0).fillna(0.0)

# prob de quedarse (ajustá)
p_stay = 0.2
P = (1 - p_stay) * P
np.fill_diagonal(P.values, np.diag(P.values) + p_stay)

# ====== 4) export ======
od.to_csv("od_pairs.csv", index=False)
M.to_csv("mobility_matrix.csv")
P.to_csv("mobility_prob_matrix.csv")
print("OK -> od_pairs.csv / mobility_matrix.csv / mobility_prob_matrix.csv")

# ====== 5) mapa de chequeo (opcional) ======
m = folium.Map(location=[-32.41, -63.24], zoom_start=12, control_scale=True)
folium.GeoJson(zones.__geo_interface__, name="Zonas").add_to(m)
folium.GeoJson(lines.__geo_interface__, name="Trazas", 
               style_function=lambda f: {"weight":4, "opacity":0.7}).add_to(m)
folium.GeoJson(stops.__geo_interface__, name="Paradas",
               marker=folium.CircleMarker(radius=3, fill=True)).add_to(m)
folium.LayerControl().add_to(m)
m.save("mapa.html")


# In[ ]:


# import geopandas as gpd

# base = "https://mapa.villamaria.gob.ar/geoserver/wfs"
# layers = [
#     "linea_12","linea_13","linea_14","linea_15","linea_16","linea_16_b",
#     "linea_17","linea_17_b","linea_19","linea_20","linea_102","linea_103","linea_104"
# ]

# for lyr in layers:
#     url = (f"{base}?service=WFS&version=1.1.0&request=GetFeature"
#            f"&typeName=transporte:{lyr}&outputFormat=application/json&srsName=EPSG:4326")
#     gdf = gpd.read_file(url)
#     gdf.to_file(f"data\external\infra y mov\movilidad\{lyr}.geojson", driver="GeoJSON")    # GeoJSON
#     # gdf.to_file(f"{lyr}.shp")                        # Shapefile (si querés)
# import geopandas as gpd
# import pandas as pd

# BASE = "https://mapa.villamaria.gob.ar/geoserver/wfs"
# params = {
#     "service": "WFS",
#     "version": "1.1.0",
#     "request": "GetFeature",
#     "typeName": "transporte:paradas_omnibus",
#     "outputFormat": "application/json",
#     "srsName": "EPSG:4326",
# }

# url = BASE + "?" + "&".join(f"{k}={v}" for k, v in params.items())

# gdf = gpd.read_file(url)           # descarga y parsea GeoJSON
# gdf.to_file("paradas_omnibus.geojson", driver="GeoJSON")
# gdf.to_file("paradas_omnibus.shp") # opcional: Shapefile

# # Si querés un CSV simple con lat/lon:
# df = pd.DataFrame(gdf.drop(columns="geometry"))
# df["lon"] = gdf.geometry.x
# df["lat"] = gdf.geometry.y
# df.to_csv("paradas_omnibus.csv", index=False)

# print(gdf.head(), "\nGuardado GeoJSON/CSV/SHAPE.")

# # pip install geopandas folium pandas shapely rtree
# from pathlib import Path
# import geopandas as gpd
# import folium

# # --- RUTAS (ajustá si difieren) ---
# p_lineas  = Path(r"data\external\infra y mov\lineas")
# p_paradas = Path(r"data\external\infra y mov\paradas omnibus")

# # --- Cargar TODO ---
# def read_any_vector(p):
#     gdf = gpd.read_file(p)
#     if gdf.crs is None:
#         # asume WGS84 si viene vacío
#         gdf.set_crs(4326, inplace=True)
#     else:
#         gdf = gdf.to_crs(4326)
#     return gdf

# # líneas (todos los .geojson de la carpeta)
# gdfs_lineas = []
# for f in sorted(p_lineas.glob("*.geojson")):
#     g = read_any_vector(f)
#     g["source_file"] = f.stem
#     gdfs_lineas.append(g)

# # paradas (geojson/shp)
# gdfs_paradas = []
# for pat in ["*.geojson", "*.shp"]:
#     for f in sorted(p_paradas.glob(pat)):
#         g = read_any_vector(f)
#         g["source_file"] = f.stem
#         gdfs_paradas.append(g)

# lineas  = gpd.GeoDataFrame(pd.concat(gdfs_lineas, ignore_index=True), crs=4326) if gdfs_lineas else gpd.GeoDataFrame()
# paradas = gpd.GeoDataFrame(pd.concat(gdfs_paradas, ignore_index=True), crs=4326) if gdfs_paradas else gpd.GeoDataFrame()

# # --- Centro del mapa ---
# bounds = None
# if len(lineas) and not lineas.empty:
#     bounds = lineas.total_bounds  # minx, miny, maxx, maxy
# elif len(paradas) and not paradas.empty:
#     bounds = paradas.total_bounds
# center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2] if bounds is not None else [-32.41, -63.24]

# # --- Mapa Folium ---
# m = folium.Map(location=center, zoom_start=13, control_scale=True, tiles="OpenStreetMap")

# # capas de líneas por archivo
# palette = [
#     "#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd",
#     "#8c564b","#e377c2","#7f7f7f","#bcbd22","#17becf"
# ]
# def color_for(i): return palette[i % len(palette)]

# for i, (fname, g) in enumerate(lineas.groupby("source_file")):
#     gj = g.__geo_interface__
#     folium.GeoJson(
#         gj,
#         name=f"Línea: {fname}",
#         style_function=lambda _feat, c=color_for(i): {"color": c, "weight": 4, "opacity": 0.9},
#         tooltip=folium.features.GeoJsonTooltip(
#             fields=[c for c in g.columns if c not in ("geometry")][:10], aliases=None
#         ),
#     ).add_to(m)

# # capa de paradas (cluster opcional)
# if len(paradas):
#     fg = folium.FeatureGroup(name="Paradas de ómnibus", show=True)
#     for _, row in paradas.iterrows():
#         geom = row.geometry
#         if geom is None or geom.is_empty: continue
#         if geom.geom_type == "Point":
#             folium.CircleMarker(
#                 location=[geom.y, geom.x],
#                 radius=4, fill=True, fill_opacity=0.9, opacity=0.9
#             ).add_to(fg)
#     fg.add_to(m)

# folium.LayerControl(collapsed=False).add_to(m)
# m.save("mapa_transporte.html")
# print("Mapa listo -> mapa_transporte.html")

# # --- Exportar combinados (útiles para GIS) ---
# if len(lineas):
#     lineas.to_file("todas_lineas.geojson", driver="GeoJSON")
# if len(paradas):
#     paradas.to_file("todas_paradas.geojson", driver="GeoJSON")
# print("Exportado GeoJSON combinado.")

