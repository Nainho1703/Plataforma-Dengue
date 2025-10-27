# Fuentes de datos y licencias

Este documento describe las fuentes de datos utilizadas en el proyecto **Plataforma Dengue – Villa María (AR)** y cómo se procesan para los modelos de **predicción de brotes**.

---

## 1) Variables climáticas – Copernicus Climate Data Store (ERA5-Land)

- **Dataset**: `reanalysis-era5-land` (horario)
- **Proveedor**: Copernicus Climate Change Service (C3S), Climate Data Store (CDS)
- **Variables descargadas** (nombres oficiales de CDS):
  - `2m_temperature` (temperatura 2 m)
  - `2m_dewpoint_temperature` (temperatura punto de rocío 2 m)
  - `total_precipitation` (precipitación total)
  - `10m_u_component_of_wind` (componente U del viento a 10 m)
  - `10m_v_component_of_wind` (componente V del viento a 10 m)
- **Cobertura temporal local**: 2021–2025 (enero 2021–septiembre 2025)
- **Resolución temporal**: 1 hora (agregada a **semanal** para el modelado)
- **Extensión espacial** (bbox aproximada a Villa María y alrededores): `[-31.9, -63.5, -32.6, -63.0]` (N, W, S, E)
- **Formato**: NetCDF (`.nc`)
- **Licencia**: Licencia del Climate Data Store (Copernicus). Requiere **atribución** a C3S/ECMWF.
- **Notas de preprocesamiento**:
  - Conversión a unidades comunes y **agregación semanal (ISO week)**.
  - Cálculo de **rezagos** climáticos `L1–L8` semanas.
  - Derivación de indicadores: acumulados semanales de precipitación, medias y extremos térmicos, módulo y dirección del viento, etc.
  - Control de calidad: descarte de horas faltantes y *regridding* si aplica.

> Fuente operacional y código de descarga en `notebooks/0.- act_clima.ipynb`. Los archivos locales están en `model/climate_data/era5land_YYYY_MM_*.nc`.

---

## 2) Casos de dengue – SNVS (Argentina)

- **Dataset**: Registros de casos del **Sistema Nacional de Vigilancia de la Salud (SNVS)**.
- **Proveedor**: Ministerio de Salud de la Nación Argentina.
- **Cobertura**: casos notificados para Villa María y área de influencia (fechas y variables según disponibilidad).
- **Resolución temporal**: diaria; se **agrega a semanal** (ISO) para el modelado de brote.
- **Licencia/uso**: sujeta a **términos y confidencialidad** del SNVS. No publicar **PII**; trabajar con **agregaciones** y/o datos anonimizados.
- **Notas de preprocesamiento**:
  - Limpieza de duplicados/inconsistencias.
  - Geocodificación/validación básica de domicilios (si aplica); en producción usar **barrios/áreas** agregadas.
  - Derivación de **incidencia** semanal, indicadores de brote (umbral), *nowcasting* si aplica.
- **Ubicación en repo**: `model/data/raw/` y `model/results/` (salidas agregadas).

---

## 3) Variables socio-demográficas – Centro Estadístico de Villa María

- **Proveedor**: Centro Estadístico / Municipalidad de Villa María.
- **Tablas** (ejemplos):
  - Indicadores socio-demográficos (pobreza, hacinamiento, etc.).
  - Población (2010, 2022) por barrio/área.
  - Infraestructura y movilidad (capas vectoriales y CSV).
- **Resolución espacial**: barrio/sector censal (según disponibilidad).
- **Resolución temporal**: cortes por año/periodo (2010, 2022, etc.).
- **Licencia**: según términos municipales; verificar condiciones de uso y **atribución**.
- **Notas de preprocesamiento**:
  - Normalización de nombres de barrios/IDs espaciales.
  - *Joins* espaciales a geometrías oficiales (departamentos, radios, etc.).
  - Generación de *features* estáticas (densidad poblacional, cobertura de servicios, etc.).
- **Ubicación en repo**: `model/data/Indicadores sociodemograficos/`, `model/data/Poblacion 2010 2022/`, `model/data/infra y mov/`.

---

## 4) Integración y frecuencia analítica

- **Unidad temporal de modelado**: **semanal** (ISO).
- **Unidad espacial**: municipio/barrios agregados (evitar microdatos sensibles).
- **Rezagados**: clima `L1–L8` semanas; opcionalmente rezagos de incidencia.
- **Normalización**: *standard scaling* o por percentiles; documentar en el *pipeline*.
- **Salidas**:
  - `model/results/metrics.csv`
  - `model/results/figs/*.png`
  - `model/results/predicciones_h/*summary.csv`

---

## 5) Citas recomendadas (ver `docs/paper/references.bib`)

- Muñoz‑Sabater et al., 2021 — ERA5‑Land.
- Hersbach et al., 2020 — ERA5 global reanalysis.
- Chen & Guestrin, 2016 — XGBoost.
- Breiman, 2001 — Random Forests.
- Bhatt et al., 2013 — Carga global de dengue.
