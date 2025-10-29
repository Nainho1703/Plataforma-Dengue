#!/usr/bin/env python
# coding: utf-8

# In[2]:


import pandas as pd
import numpy as np
from shapely import wkt
from pyproj import CRS
import geopandas as gpd
from scipy.spatial import cKDTree
import sqlite3
from datetime import date
from shapely.geometry import shape
import os
pd.set_option('display.max_columns', None) 
pd.set_option('display.width', None) 

ruta_excel = r"data\raw\casos_procesados\casos_direccion_real.xlsx"
df0 = pd.read_excel(ruta_excel)

# df_casos=df0.drop(["DIRECCION"],axis=1)
df0.head()

df0=df0.loc[~((df0["DIRECCION"].isnull())&(~df0["WKT"].isnull()))]
df00=df0[["DIRECCION","lon","lat","WKT"]].drop_duplicates()
df00.head()


# In[6]:


ruta_excel = r"data\raw\casos_raw\notificaciones dengue Villa María 23-24.xlsx"

df_0 = pd.read_excel(ruta_excel)

ruta_excel = r"data\raw\casos_raw\Notificaciones dengue Villa María 24-25.xlsx"

df_1 = pd.read_excel(ruta_excel)

df_f=pd.concat([df_0,df_1])
df_f["DIRECCION"]=df_f["calle_domicilio"]+" "+df_f["numero_domicilio"]+", Villa María, Córdoba"

df_f.head()


# In[28]:


df_f["fis"]


# In[30]:


# 1. Asegúrate de tener tu DataFrame cargado como df_f
#    y que tiene las columnas 'fis' y 'fecha_apertura'  #fis fecha inicio de sintomas

df_f['fis'] = pd.to_datetime(df_f['fis'], dayfirst=True, errors='coerce')
df_f['fecha_apertura'] = pd.to_datetime(df_f['fecha_apertura'], dayfirst=True, errors='coerce')

# 2. Calcula la diferencia en días
df_f['diff_apertura_fis'] = (df_f['fecha_apertura'] - df_f['fis']).dt.days
df_f['diff_apertura_fis']=df_f['diff_apertura_fis'].fillna(-1)
df_f.loc[(df_f['diff_apertura_fis'].astype(int)<0)|(df_f['diff_apertura_fis'].astype(int)>10),'fis']=pd.NaT   # si es mas de 10 días se pone como que no hubo

df_f['fis'] = pd.to_datetime(df_f['fis'], dayfirst=True, errors='coerce')
df_f['fecha_apertura'] = pd.to_datetime(df_f['fecha_apertura'], dayfirst=True, errors='coerce')

# 3. Calcular diff original (en días) y guardar copia
df_f['diff_apertura_fis'] = (df_f['fecha_apertura'] - df_f['fis']).dt.days
diff_orig = df_f['diff_apertura_fis'].copy()

# 4. Estadísticas antes de la imputación
mean_orig = diff_orig.mean()
std_orig  = diff_orig.std()

print(f"Antes de imputar: media = {mean_orig:.2f} días, std = {std_orig:.2f} días")

# 5. Imputar los fis faltantes muestreando de la distribución empírica
diffs      = df_f.loc[df_f['fis'].notnull(), 'diff_apertura_fis']
mask_null  = df_f['fis'].isnull()
n_null     = mask_null.sum()

np.random.seed(42)
sampled   = diffs.sample(n=n_null, replace=True).values
df_f.loc[mask_null, 'fis'] = (
    df_f.loc[mask_null, 'fecha_apertura']
    - pd.to_timedelta(sampled, unit='d')
)

# 6. Recalcular diff después de la imputación
df_f['diff_apertura_fis'] = (df_f['fecha_apertura'] - df_f['fis']).dt.days
diff_new = df_f['diff_apertura_fis']

# 7. Estadísticas después de la imputación
mean_new = diff_new.mean()
std_new  = diff_new.std()

print(f"Después de imputar: media = {mean_new:.2f} días, std = {std_new:.2f} días")
print(f"Diferencia en media: {mean_new - mean_orig:+.2f} días")
print(f"Diferencia en std:   {std_new  - std_orig:+.2f} días")


# In[31]:


# 3. Parámetros de incubación (sin ajuste por edad/sexo)
mu_base = 5.0   # días de incubación promedio
sigma   = 2.0   # desviación estándar

# 5. Muestreamos el periodo de incubación para cada fila
np.random.seed(42)
# Genera un array de incubaciones
incubaciones = np.random.normal(loc=mu_base, scale=sigma, size=len(df_f))
# Redondea y fuerza un mínimo de 3 días
incubaciones = np.round(incubaciones)
incubaciones = np.clip(incubaciones, 3, None)  # valores <3 pasan a 3

df_f['dias_incub'] = incubaciones.astype(int)

# 6. Calcula la fecha estimada de picadura
df_f['fecha_picadura_estimada'] = df_f['fis'] - pd.to_timedelta(df_f['dias_incub'], unit='D')

# 7. Recalcula diff_apertura_fis para ver stats tras la estimación
df_f['diff_apertura_fis'] = (df_f['fecha_apertura'] - df_f['fis']).dt.days
mean_new = df_f['diff_apertura_fis'].mean()
std_new  = df_f['diff_apertura_fis'].std()
print(f"Después de estimar picadura: media diff = {mean_new:.2f} d, std = {std_new:.2f} d")
print(f"Cambio en media = {mean_new - mean_orig:+.2f} d, cambio en std = {std_new - std_orig:+.2f} d")
df_f2=df_f[["DIRECCION","ideventocaso","sexo","edad_diagnostico","fecha_picadura_estimada","fecha_apertura","fis"]]
aj=pd.merge(df_f2,df00,on=["DIRECCION"],how="left") # traigo la información 

aj.loc[~aj["WKT"].isnull()]

df_casos=aj.copy()
df_casos.head()


# In[32]:


# agg=df_casos.copy()
# agg["AUX"]=1
# agg2=agg.loc[(agg["fecha_picadura_estimada"]<"2024-04-04")&(agg["fecha_picadura_estimada"]>"2024-03-30")]

# pd.pivot_table(agg2,index=["fecha_picadura_estimada","fecha_apertura"],values="AUX",aggfunc="count")

# pd.pivot_table(agg,index=["fecha_picadura_estimada"],values="AUX",aggfunc="sum").sort_values("AUX")

# pd.pivot_table(agg,index=["fecha_apertura"],values="AUX",aggfunc="sum").sort_values("AUX")[-30:]

# # agg.to_excel("ok.xlsx")


# In[33]:


# 3) Crea la columna geometry con prioridad: WKT → Point(lon,lat) → None
def make_geom(row):
    # Si hay WKT no nulo, intenta parsearlo
    if pd.notna(row.get("WKT")):
        try:
            return wkt.loads(row["WKT"])
        except Exception:
            pass

    return None

df_casos["geometry"] = df_casos.apply(make_geom, axis=1)

# # 4) Pasa a GeoDataFrame, dejando fuera los que no tienen geometry
gdf_casos = gpd.GeoDataFrame(
    df_casos[df_casos["geometry"].notna()].copy(),
    geometry="geometry",
    crs="EPSG:4326"
)

# 5) Carga y prepara tu río igual que antes...
df_rio = pd.read_csv(r"data\external\infra y mov\infraestructura\rio-ctalamochita-2021.csv", sep=";")


df_rio["geometry"] = df_rio["WKT"].apply(wkt.loads)
gdf_rio = gpd.GeoDataFrame(df_rio, geometry="geometry", crs="EPSG:4326")
rio_union = gdf_rio.geometry.unary_union

# 6) Proyecta a métrico y calcula distancias solo donde falten
utm21s        = CRS.from_epsg(32721)
gdf_casos_utm = gdf_casos.to_crs(utm21s)
rio_utm       = gpd.GeoSeries([rio_union], crs="EPSG:4326").to_crs(utm21s).iloc[0]

# Crea o rellena distancia_rio
if "distancia_rio" not in gdf_casos_utm.columns:
    gdf_casos_utm["distancia_rio"] = pd.NA

mask = gdf_casos_utm["distancia_rio"].isna()
gdf_casos_utm.loc[mask, "distancia_rio"] = (
    gdf_casos_utm.loc[mask, "geometry"].distance(rio_utm)
)

# 7) Devolver a EPSG:4326 si lo necesitas y guarda/usa el resultado
gdf_result = gdf_casos_utm.to_crs("EPSG:4326")


gdf_result.head()


# In[34]:


# 1️⃣ Carga ambas capas
gdf_osm = gpd.read_file(r"data\interm\parques_villa_maria.geojson").to_crs(epsg=4326)
df_of = pd.read_csv(r"data\external\infra y mov\infraestructura\espacios-verdes-2021.csv", sep=";")
df_of["geometry"] = df_of["WKT"].apply(wkt.loads)
gdf_of = gpd.GeoDataFrame(df_of, geometry="geometry", crs="EPSG:4326")

# 2️⃣ Suma (concat) y exporta GeoJSON de todas las áreas
gdf_union = pd.concat([gdf_osm, gdf_of], ignore_index=True)
gdf_union = gdf_union[gdf_union.geometry.notna()]
gdf_union.to_file(r"data\interm\areas_verdes_union.geojson", driver="GeoJSON")

# 3️⃣ Carga tus casos y reproyecta todo a UTM21S para metros
# gdf_casos = gpd.read_file("casos_con_distancia.csv")  # asumiendo CSV previo con geometry
gdf_casos=gdf_result.copy()
gdf_casos = gdf_casos.set_geometry("geometry").set_crs(epsg=4326)
utm21s = 32721
gdf_casos_utm = gdf_casos.to_crs(epsg=utm21s)
gdf_union_utm = gdf_union.to_crs(epsg=utm21s)

# 4️⃣ Calcula distancia al área verde más próxima (union de todo)
union_geom = gdf_union_utm.geometry.unary_union
gdf_casos_utm["distancia_verde_m"] = gdf_casos_utm.geometry.apply(lambda pt: pt.distance(union_geom))

gdf_union_utm["area_m2"] = gdf_union_utm.geometry.area
gdf_union_utm = gdf_union_utm.sort_values("area_m2", ascending=False).reset_index(drop=True)
gdf_top10 = gdf_union_utm.head(10).copy()
top10_geoms = list(gdf_top10.geometry)
gdf_casos_utm["distancia_grande_m"] = gdf_casos_utm.geometry.apply(
    lambda pt: min(pt.distance(poly) for poly in top10_geoms)
)



# 6️⃣ Guarda resultados
gdf_casos_utm.to_file("data\interm\casos_con_distancias.geojson", driver="GeoJSON")

gdf_casos_utm.head()


# In[35]:


import geopandas as gpd
import matplotlib.pyplot as plt


import geopandas as gpd

# 1) Carga la capa de Municercas
gdf_municerca = gpd.read_file(r"data\external\infra y mov/Capa de Municercas/NuevaDistribucion2024.shp")

casos_proj = gdf_casos_utm.to_crs(gdf_municerca.crs)

casos_con_municerca = gpd.sjoin(
    casos_proj,
    gdf_municerca[['Nombre','geometry']],
    how='left',
    predicate='within'
).drop(columns=['index_right'])


# 2) Reproyecta tus casos al mismo CRS de Municercas
casos_proj = gdf_casos_utm.to_crs(gdf_municerca.crs)


casos_con_muni = (
    gpd.sjoin(
        casos_proj,
        gdf_municerca[['Nombre','geometry']],
        how='left',
        predicate='within'
    )
    .rename(columns={'Nombre':'municerca'})
    .drop(columns=['index_right'])
)

# 4) Inspecciona el resultado
print(casos_con_muni[['lon','lat','municerca']].head())

# 5) Grafica: polígonos + etiquetas + puntos coloreados por municerca
fig, ax = plt.subplots(figsize=(12, 10))

# 5a) Contornos
gdf_municerca.plot(ax=ax, facecolor='none', edgecolor='blue', linewidth=1)

# 5b) Etiquetas en centroides
for _, row in gdf_municerca.iterrows():
    cx, cy = row.geometry.centroid.xy
    ax.text(cx[0], cy[0],
            row['Nombre'],
            ha='center', va='center',
            fontsize=9, fontweight='bold')

# 5c) Casos coloreados por municerca
casos_con_muni.plot(
    column='municerca',
    ax=ax,
    markersize=25,
    alpha=0.7,
    legend=True,
    legend_kwds={'title':'Municerca'}
)

# 6) Centrar y ajustar límites al bounding‐box de las municercas
minx, miny, maxx, maxy = gdf_municerca.total_bounds
dx, dy = (maxx-minx)*0.05, (maxy-miny)*0.05
ax.set_xlim(minx-dx, maxx+dx)
ax.set_ylim(miny-dy, maxy+dy)

ax.set_aspect('equal')
ax.set_axis_off()
plt.tight_layout()
plt.show()




# In[36]:


gdf_municerca['geometry_centroid'] = gdf_municerca.geometry.centroid
gdf_municerca['lon_centroid'] = gdf_municerca.geometry_centroid.x
gdf_municerca['lat_centroid'] = gdf_municerca.geometry_centroid.y

gdf_municerca

import geopandas as gpd

gdf_municerca_geo = gdf_municerca.to_crs(epsg=4326)

gdf_municerca_geo['geometry_centroid'] = gdf_municerca_geo.geometry.centroid

gdf_municerca_geo['longitude'] = gdf_municerca_geo.geometry_centroid.x
gdf_municerca_geo['latitude'] = gdf_municerca_geo.geometry_centroid.y

df_centroids = gdf_municerca_geo[['Nombre','longitude','latitude']]
df_centroids.columns=["municerca",'longitude','latitude']


# In[37]:


# 1) Abre la conexión
from pathlib import Path
import sqlite3
import pandas as pd
BASE_DIR = Path().resolve()  

DB_PATH = BASE_DIR.parent / "backend" / "data" / "mi_base_de_datos5.db"

conn = sqlite3.connect(DB_PATH)

# 2) Lée los últimos 20 registros (ordenados por fecha decreciente)
df_clima = pd.read_sql_query("""
    SELECT *
      FROM climate_data
     ORDER BY time
""", conn)

conn.close()
# df_clima["longitude"]=df_clima["longitude"]-0.25



df_clima=df_clima.rename(columns={'time':'date'})



# In[38]:


df_clima2=df_clima.copy()
df_clima2["date"]=pd.to_datetime(df_clima2["date"])
df_clima2["dia"]=df_clima2["date"].dt.day
df_clima2["mes"]=df_clima2["date"].dt.month
clim_cols=["tp","t2m","d2m","t2m_min","t2m_max"]
prom_weather=pd.DataFrame(pd.pivot_table(df_clima2,index=["dia","mes"],values=clim_cols,aggfunc="mean").to_records())

df_clima2=pd.merge(df_clima2,prom_weather,on=["dia","mes"],how="left")
df_clima2.head()


# In[39]:


clim_cols_anom=[]
for ss in clim_cols:
    df_clima2[ss+"_anom"]=df_clima2[ss+"_x"]-df_clima2[ss+"_y"]
    df_clima2=df_clima2.rename(columns={ss+"_x":ss})
    df_clima2.drop(ss+"_y",axis=1,inplace=True)
    clim_cols_anom.append(ss+"_anom")


df_clima2.head()


# In[49]:


import numpy as np
import pandas as pd
import geopandas as gpd

def centroids_from_shp(shp_path, name_col='Nombre'):
    gdf = gpd.read_file(shp_path).to_crs(epsg=4326)
    gdf['centroid'] = gdf.geometry.centroid
    out = gdf[[name_col, 'centroid']].copy()
    out['lat'] = out['centroid'].y
    out['lon'] = out['centroid'].x
    out = out.drop(columns='centroid').rename(columns={name_col:'municerca'})
    return out

def bilinear_interp_point(lat, lon, lat0, dlat, lon0, dlon, F):
    """
    Interpola en (lat,lon) a partir de malla regular:
      lat(i) = lat0 + i*dlat, lon(j) = lon0 + j*dlon
      F[i,j] es el valor en la grilla.
    Devuelve valor interpolado y los (i,j) usados.
    """
    # índices flotantes
    i_f = (lat - lat0)/dlat
    j_f = (lon - lon0)/dlon
    i0 = int(np.floor(i_f)); i1 = i0 + 1
    j0 = int(np.floor(j_f)); j1 = j0 + 1

    # pesos
    wi = i_f - i0    # fracción en lat
    wj = j_f - j0    # fracción en lon

    # contornos seguros
    if i0 < 0 or j0 < 0 or i1 >= F.shape[0] or j1 >= F.shape[1]:
        return np.nan

    f00 = F[i0, j0]; f01 = F[i0, j1]
    f10 = F[i1, j0]; f11 = F[i1, j1]
    # bilinear
    f0 = f00*(1-wj) + f01*wj
    f1 = f10*(1-wj) + f11*wj
    return f0*(1-wi) + f1*wi

def bilinear_for_dates(df_grid, df_centroids, var='t2m', date_col='fecha', lat_name='latitude', lon_name='longitude',
                       lat0=-90.0, dlat=0.5, lon0=-180.0, dlon=0.5):
    """
    df_grid: DataFrame con columnas [fecha, lat, lon, var]
             (lat/lon pegadas a la grilla 0.5°)
    df_centroids: DataFrame con [municerca, lat, lon] (centroides)
    Devuelve DataFrame con [municerca, fecha, var_bilinear]
    """
    out = []
    for fecha, df_d in df_grid.groupby(date_col):
        # pivot a matriz de la grilla para ese día
        # asumimos lat/lon exactos de la malla
        P = df_d.pivot(index=lat_name, columns=lon_name, values=var).sort_index(ascending=True)
        lats = P.index.to_numpy()
        lons = P.columns.to_numpy()
        # si conoces lat0/dlat/lon0/dlon exactos, puedes usarlos; si no, los infieres:
        lat0_i, dlat_i = lats.min(), np.diff(lats).mean()
        lon0_i, dlon_i = lons.min(), np.diff(lons).mean()
        F = P.to_numpy()

        for _, r in df_centroids.iterrows():
            v = bilinear_interp_point(r['lat'], r['lon'], lat0_i, dlat_i, lon0_i, dlon_i, F)
            out.append((r['municerca'], fecha, v))
    return pd.DataFrame(out, columns=['municerca', date_col, f'{var}_bilin'])


centros = centroids_from_shp("data/external/infra y mov/Capa de Municercas/NuevaDistribucion2024.shp",
                             name_col='Nombre')
# 2) df_grid: algo como [fecha, lat, lon, t2m]
# 3) interpolo
df_clima1=pd.DataFrame()
for c in clim_cols+clim_cols_anom:   # p.ej. ['t2m','d2m','tp','t2m_min','t2m_max','ws10']
    aux = bilinear_for_dates(
        df_grid=df_clima2, 
        df_centroids=centros,
        var=c,                      # <-- usa la variable correcta
        date_col='date',
        lat_name='latitude',
        lon_name='longitude'
    )
    # renombra de "{var}_bilin" -> "{var}" para no duplicar nombres raros
    aux = aux.rename(columns={f'{c}_bilin': c})

    if df_clima1.empty:
        df_clima1 = aux
    else:
        df_clima1 = df_clima1.merge(aux, on=['municerca','date'], how='outer')
df_clima1.sort_values(by=["date","municerca"])[:30]
df_clima1.to_csv("data\processed\clima_processed.csv",index=False)


# In[41]:


df_clima_=df_clima1.copy()
df_clima_=df_clima_.rename(columns={'date':'fecha_picadura_estimada'})


# In[42]:


casos_con_muni2=pd.merge(casos_con_muni,df_clima_,on=["municerca","fecha_picadura_estimada"],how="left")

cols=list(casos_con_muni2.columns)


cols.remove("municerca")
casos_con_muni2=casos_con_muni2[["municerca"]+cols]


# In[43]:


# df_clima2["date"]=df_clima2["date"].astype(str)
# casos_con_muni2["fecha_picadura_estimada"]=casos_con_muni2["fecha_picadura_estimada"].astype(str)
# for c in ["longitude","latitude"]:
#     casos_con_muni2[c]=casos_con_muni2[c].astype(float)
#     df_clima2[c]=df_clima2[c].astype(float)

# df_casos_d=pd.merge(casos_con_muni2,df_clima2,left_on=["fecha_picadura_estimada","longitude","latitude"],right_on=["date","longitude","latitude"],how="left")

# df_casos_d["fecha_picadura_estimada"] = pd.to_datetime(df_casos_d["fecha_picadura_estimada"], format="%Y-%m-%d", errors="coerce")

# # 1) Mes numérico (1–12)
# df_casos_d["mes"] = df_casos_d["fecha_picadura_estimada"].dt.month


# df_casos_d.head()


# In[ ]:


casos_con_muni2 = casos_con_muni2.sort_values('fecha_picadura_estimada')
casos_con_muni2['fecha'] = pd.to_datetime(casos_con_muni2['fecha_picadura_estimada'])

def add_bucket(df, date_agrup: str):
    df = df.copy()

    if not pd.api.types.is_datetime64_any_dtype(df['fecha']):
        df['fecha'] = pd.to_datetime(df['fecha'])

    if date_agrup in ('7D', 'W', 'semanal'):  # semanal anclada a lunes
        start = df['fecha'].dt.to_period('W-MON').dt.to_timestamp(how='start')
        df['fecha_agg'] = start.dt.strftime('%Y-%m-%d')

    elif date_agrup in ('1D', 'D', 'diario'):  # semanal anclada a lunes

        df['fecha_agg'] = df['fecha'].astype(str)


    elif date_agrup in ('14D','2W'):
        anchor = df['fecha'].min().normalize()
        # ancla -> floor de 14 días -> vuelve a fechas reales
        start = (df['fecha'] - anchor).dt.floor('14D') + anchor
        df['fecha_agg'] = start.dt.strftime('%Y-%m-%d')  # etiqueta con el inicio del bin
    elif date_agrup in ('MS','M','mensual'):
        df['fecha_agg'] = df['fecha'].dt.to_period('M').astype(str)
    else:
        # genérico: intenta usar alias de pandas (ej. '14D','2W','QS','Q', etc.)
        df['fecha_agg'] = df['fecha'].dt.to_period(date_agrup).astype(str)
    return df



def agrup_datos(casos_con_muni2,grilla,date_agrup,target):


    sacar = ["DIRECCION",'ideventocaso',"WKT","geometry","fecha_picadura_estimada",'date','fecha_agg','fecha','fecha_apertura',"fis"]

    bset = set(sacar)                     # para membership O(1)
    res = [x for x in cols if x not in bset]

    casos_con_muni2['sexo'] = casos_con_muni2['sexo'].replace({'M': 1, 'F': 0})
    casos_con_muni2.loc[:, res] = casos_con_muni2.loc[:, res].astype("float64")

    casos_con_muni2 = add_bucket(casos_con_muni2, date_agrup)


    if grilla=="MUN":
        l_agrupacion=["municerca","fecha_agg"]    
        # prep columnas y codificación
    else:
        l_agrupacion=["fecha_agg"]
    casos_con_muni2 = casos_con_muni2[cols+l_agrupacion].copy()
    # agregados: medias + conteo de casos
    g = casos_con_muni2.groupby(l_agrupacion)


    means = g[res].mean().reset_index()
    counts = g.size().rename('casos').reset_index()

    casos_agg = means.merge(counts, on=l_agrupacion).sort_values(l_agrupacion)


    # df_full3=casos_agg.loc[(casos_agg["latitude"]<-31.2)&(casos_agg["longitude"]>-63.4)]
    df_mundosano=pd.read_excel(r"data\external\Indicadores sociodemograficos\Indicadores_MundoSano.xlsx")
    df_mundosano["municerca"]=df_mundosano["municerca"].str.upper()

    if grilla=="MUN":



        casos_muni_ms=pd.merge(casos_agg,df_mundosano,on=["municerca"],how="left")
        if target=="INC":
            casos_muni_ms['casos_#']=casos_muni_ms['casos'].copy()

            casos_muni_ms['casos']=(casos_muni_ms['casos_#']/casos_muni_ms['Estimación poblacional'])*10000

    else:

        if target=="INC":
            casos_agg['casos_#']=casos_agg['casos'].copy()
            total_pob=df_mundosano['Estimación poblacional'].sum()
            casos_agg['casos']=(casos_agg['casos_#']/total_pob)*10000
        casos_muni_ms=casos_agg.copy()

    return(casos_muni_ms)


casos_con_muni2['fecha'].unique()


# In[45]:


# ---------- 1) Features base ----------
def add_case_windows(df):
    df = df.sort_values(['municerca','fecha_agg']).copy()
    # sumas 2,3,4 semanas previas, sin fuga
    for n in (2,3,4):
        df[f'casos_sum_{n}w'] = (df.groupby('municerca')['casos']
                                   .transform(lambda s: s.shift(1).rolling(n, min_periods=n).sum()))
    # lags
    for lag in (1,2,3,4):
        df[f'casos_lag_{lag}'] = df.groupby('municerca')['casos'].shift(lag)
    # media móvil 4w sin fuga
    df['casos_ma_4'] = (df.groupby('municerca')['casos']
                          .transform(lambda s: s.shift(1).rolling(4, min_periods=4).mean()))
    # mes desde ISO week
    # df['mes'] = pd.to_datetime(df['fecha_agg'] + "-1", format="%G-W%V-%u").dt.month
    return df

import re

def add_climate_rolls(
    df,
    clim_prefixes=('t2m','d2m','tp','t2m_min','t2m_max'),
    wins=(1,2),
    sum_prefixes=('tp',),              # prefijos que además llevan rolling SUM
):
    """
    Crea rolling means (y opcionalmente sums) para TODA columna cuyo nombre
    empiece por alguno de los prefijos indicados. Evita columnas ya agregadas.
    """
    df = df.sort_values(['municerca','fecha_agg']).copy()
    created = []

    # patrón para excluir columnas ya agregadas (p.ej. t2m_mean_1w, tp_sum_2w)
    _already_agg = re.compile(r'_(mean|sum)_[0-9]+w$')

    # columnas candidata: empiezan con alguno de los prefijos y NO son ya agregadas
    base_cols = [c for c in df.columns
                 if any(c.startswith(p) for p in clim_prefixes)
                 and not _already_agg.search(c)]

    # genera rolling features por grupo (municerca), con shift(1) para no fugar
    for col in base_cols:
        for w in wins:
            mcol = f'{col}_mean_{w}w'
            df[mcol] = (df.groupby('municerca')[col]
                          .transform(lambda s: s.shift(1).rolling(w, min_periods=w).mean()))
            created.append(mcol)

            # si el prefijo de la columna está en sum_prefixes -> también SUM
            if any(col.startswith(p) for p in sum_prefixes):
                scol = f'{col}_sum_{w}w'
                df[scol] = (df.groupby('municerca')[col]
                              .transform(lambda s: s.shift(1).rolling(w, min_periods=w).sum()))
                created.append(scol)

    return df, created


def enforce_unique_time(df, keys=('municerca','fecha_agg')):
    df = df.copy()
    # quick debug: ver duplicados
    dup = df.duplicated(list(keys), keep=False)
    if dup.any():
        # Agrega por keys: numéricas -> mean (o sum si corresponde), no numéricas -> first
        num_cols = df.select_dtypes(include='number').columns.difference(keys)
        agg = {c: 'mean' for c in num_cols}
        # si preferís SUM para 'casos' y acumulados, cámbialo aquí:
        for c in [c for c in num_cols if c.startswith(('casos','vec_','t2','t_min','t_max','wind','tp','d2m'))]:
            agg[c] = 'mean'  # o 'sum' si tu definición lo requiere

        keep_first = [c for c in df.columns if c not in num_cols and c not in keys]
        for c in keep_first: agg[c] = 'first'

        df = (df.groupby(list(keys), as_index=False)
                .agg(agg)
                .sort_values(list(keys)))
    return df

# ---------- 2) Matriz de vecinos y feature vecinal ----------
def build_adjacency(shp_path, name_col='Nombre'):
    gdf = gpd.read_file(shp_path).to_crs(epsg=4326)
    gdf['geometry'] = gdf.geometry.buffer(0)  # sanea
    nbrs = gpd.sjoin(gdf[[name_col,'geometry']], gdf[[name_col,'geometry']], how="inner", predicate="intersects")
    nbrs = nbrs.query(f"{name_col}_left != {name_col}_right")
    adj = pd.crosstab(nbrs[f'{name_col}_left'], nbrs[f'{name_col}_right']).astype(int)
    zonas = gdf[name_col].tolist()
    adj = adj.reindex(index=zonas, columns=zonas, fill_value=0)
    adj.index.name = adj.columns.name = 'municerca'
    return adj.rename_axis(index='municerca', columns='municerca')

def neighbor_feature(df, adj, base_col='casos_sum_3w'):
    # Si no hay vecinos (una sola zona), devuelve columna en 0
    if df['municerca'].nunique() <= 1:
        out = df.copy()
        out['Vecinos_total'] = 0.0
        return out

    # --- prepara serie base (lag sin fuga) y colapsa duplicados ---
    tmp = (df.sort_values(['municerca','fecha_agg'])
             .loc[:, ['municerca','fecha_agg', base_col]]
             .dropna(subset=[base_col]))

    # lag t-1 del base_col dentro de cada zona
    tmp[base_col + '_lag1'] = (tmp.groupby('municerca')[base_col]
                                  .shift(1))

    # colapsa a UNA fila por (fecha_agg, municerca) para el pivot
    tmp = (tmp.groupby(['fecha_agg','municerca'], as_index=False)
              .agg({base_col + '_lag1': 'first'}))

    # --- pivot tolerante (si aún hubiera duplicados, toma el primero) ---
    P = (tmp.pivot_table(index='fecha_agg', columns='municerca',
                         values=base_col + '_lag1', aggfunc='first')
           .reindex(columns=adj.index)  # alinea orden de zonas
           .fillna(0.0))

    # re-alinea adyacencia
    A = adj.reindex(index=P.columns, columns=P.columns, fill_value=0)

    # suma vecinal = P · A^T
    NV = P.values @ A.T
    nv = (pd.DataFrame(NV, index=P.index, columns=P.columns)
            .stack().rename('Vecinos_total').reset_index()
            .rename(columns={'level_1': 'municerca'}))

    # merge back
    out = df.merge(nv, on=['fecha_agg','municerca'], how='left')
    return out

def neighbor_lag_features(df, adj, base_col='casos',
                          lags=(1,2,3), sums=(2,3),
                          prefix='vec'):
    """
    Crea features vecinales:
      - {prefix}_lagL  = suma en vecinos del 'base_col' con lag L
      - {prefix}_sum_w = suma en vecinos del 'base_col' acumulada w semanas (shift(1) sin fuga)
    Requiere df con ['municerca','fecha_agg', base_col] y 'adj' con índices/columnas = nombres de municerca.
    """
    if df['municerca'].nunique() <= 1:
        # sin vecinos: devuelve columnas en cero
        out = df.copy()
        for L in lags:
            out[f'{prefix}_lag{L}'] = 0.0
        for w in sums:
            out[f'{prefix}_sum_{w}w'] = 0.0
        return out

    tmp = df.sort_values(['municerca','fecha_agg']).copy()

    # 1) matriz semanas x zonas del base_col
    P = (tmp.pivot(index='fecha_agg', columns='municerca', values=base_col)
           .reindex(columns=adj.index)  # alinea el orden de zonas
           .fillna(0.0))

    # 2) Alinea adyacencia a columnas de P
    A = adj.reindex(index=P.columns, columns=P.columns, fill_value=0)

    # 3) Lags vecinales: (P.shift(L)) @ A^T
    vec_dfs = []
    for L in lags:
        NV = P.shift(L).dot(A.T)  # semanas x zonas
        s = (NV.stack().rename(f'{prefix}_lag{L}')
               .rename_axis(index=['fecha_agg','municerca'])
               .reset_index())
        vec_dfs.append(s)

    # 4) Acumulados vecinales w: (P.shift(1).rolling(w).sum()) @ A^T (sin fuga)
    R = P.shift(1)  # t-1
    for w in sums:
        S = R.rolling(w, min_periods=w).sum()
        NV = S.dot(A.T)
        s = (NV.stack().rename(f'{prefix}_sum_{w}w')
               .rename_axis(index=['fecha_agg','municerca'])
               .reset_index())
        vec_dfs.append(s)

    # 5) merge al df original
    out = df.merge(pd.concat(vec_dfs, ignore_index=True),
                   on=['fecha_agg','municerca'], how='left')
    return out

def neighbor_lag_features(df, adj, base_col='casos',
                          lags=(1,2,3,4), sums=(2,3,4),
                          prefix='vec'):
    if df['municerca'].nunique() <= 1:
        out = df.copy()
        for L in lags: out[f'{prefix}_lag{L}'] = 0.0
        for w in sums: out[f'{prefix}_sum_{w}w'] = 0.0
        return out

    tmp = df.sort_values(['municerca','fecha_agg']).copy()

    # matriz semanas x zonas del base_col
    P = (tmp.pivot(index='fecha_agg', columns='municerca', values=base_col)
           .reindex(columns=adj.index)
           .fillna(0.0))
    A = adj.reindex(index=P.columns, columns=P.columns, fill_value=0)

    # helper para convertir matriz -> serie indexada por (fecha_agg, municerca)
    def _stack(M, name):
        return (pd.DataFrame(M, index=P.index, columns=P.columns)
                  .stack().rename(name))

    series = []

    # lags vecinales: (P.shift(L)) @ A^T
    for L in lags:
        NV = P.shift(L).dot(A.T)
        series.append(_stack(NV, f'{prefix}_lag{L}'))

    # acumulados vecinales sin fuga: (P.shift(1).rolling(w).sum()) @ A^T
    R = P.shift(1)
    for w in sums:
        NV = R.rolling(w, min_periods=w).sum().dot(A.T)
        series.append(_stack(NV, f'{prefix}_sum_{w}w'))

    # DataFrame ancho (1 fila por clave)
    V = pd.concat(series, axis=1).reset_index()  # columnas: fecha_agg, municerca, vec_*

    # merge seguro (sin duplicar)
    out = df.merge(V, on=['fecha_agg','municerca'], how='left')
    return out
# ---------- 3) Construcción dataset ----------
def build_dataset(df_raw, grilla, shp_path):
    df = df_raw.copy()
    # NVDI ffill por grupo (no global)

    df = enforce_unique_time(df, keys=('municerca','fecha_agg'))

    df = df.sort_values(['municerca','fecha_agg'])
    # df['NVDI'] = df.groupby('municerca')['NVDI'].ffill()
    # ventanas de casos y clima
    df = add_case_windows(df)
    df, clima_cols = add_climate_rolls(df)


    df.loc[:, clima_cols] = df.loc[:, clima_cols].bfill()



    adj = None
    if grilla == "MUN":
        adj = build_adjacency(shp_path, name_col='Nombre')

        # 1) lags/rollings vecinales basados en 'casos'
        df = neighbor_lag_features(df, adj, base_col='casos',
                                   lags=(1,2,3), sums=(2,3), prefix='vec')

        # 2) (opcional) tu feature previa "Vecinos_total" con sum_3w
        #    si quieres mantener el nombre:
        df = neighbor_feature(df, adj, base_col='casos_sum_3w')
        # o, si prefieres unificar:
        df['Vecinos_total'] = df['vec_sum_3w']

        return df, clima_cols, adj
    else:
        # Sin adyacencia (ej. VM con una sola serie): rellena vecinales en cero
        df['Vecinos_total'] = 0.0
        for L in (1,2,3,4):
            df[f'vec_lag{L}'] = 0.0
        for w in (2,3,4):
            df[f'vec_sum_{w}w'] = 0.0
        return df, clima_cols, ""


def proc_datos(casos_con_muni2,grilla,date_agrup,target):

    casos_muni_ms=agrup_datos(casos_con_muni2,grilla,date_agrup,target)
    casos_muni_ms_=casos_muni_ms.copy()
    if grilla=="VM":
        casos_muni_ms_['municerca'] = 'Villa María (total)'

    df_datos_agg, clima_cols, adj = build_dataset(
        casos_muni_ms_,
        grilla,
        shp_path=r"data/external/infra y mov/Capa de Municercas/NuevaDistribucion2024.shp"

    )
    df_datos_agg.to_csv(r"data\processed\casos_con_municerca"+grilla+"_"+date_agrup+"_"+target+".csv", index=False)


    df_datos_agg.head()
    return(df_datos_agg)


# In[46]:


# === usar ===
# grilla = 'VM'        # Ciudad de villa maría
# grilla = 'MUN'       # municerca
# grilla = '1KM' o '2KM'        # Cuadrados de X KM por X KM

grilla="MUN"
grillas=["MUN"]
# === usar ===
# date_agrup = '7D'        # semanal (ISO)
# date_agrup = '15D'       # quincenal (1–15 / 16–fin)
# date_agrup = 'MS'        # mensual

dates_agrup=["D","7D","14D","MS"]
# date_agrup="14D"

targets=["COUNT","INC"]
for t in targets:
    for g in grillas:
        for d in dates_agrup:
            print(f'funcionando con {g}, {d} y Target {t}')
            df_datos_agg=proc_datos(casos_con_muni2,g,d,t)


# In[48]:


casos_con_muni2.to_csv("data\processed\diario_municerca.csv", index=False)


# In[ ]:


df_datos_agg


# In[ ]:




