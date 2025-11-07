# Plataforma Dengue – Librerías de Predicción de Brotes (Villa María, AR)

> **Segundo entregable**: librerías funcionales para modelos de análisis y **predicción de brotes de dengue**, dentro del programa multi‑escala para entornos urbanos (caso Villa María, Argentina).

## Contexto
Este trabajo forma parte de un proyecto de 12 meses con tres productos; el **Producto 2** (este repo) implementa las **librerías de modelado y pronóstico** y sirve de base para su integración posterior en la **plataforma final** (Producto 3).

## Objetivo
Proveer **paquetes Python** reutilizables para:
- Ingeniería de datos epidemiológicos/climáticos/ambientales.
- Modelado de riesgo y **predicción de brotes** (nowcasting y forecasting).
- Evaluación de desempeño y utilidades para despliegue.

Con foco en **usuarios técnicos** y preparación para su integración en una plataforma de visualización y alertas.

## Estructura del repositorio

```text
data/
├─ climate_data/
├─ external/
│  ├─ Indicadores sociodemograficos/
│  ├─ Poblacion 2010 2022/
│  └─ infra y mov/
│     ├─ Capa de Municercas/
│     ├─ Capas deptos/
│     ├─ infraestructura/
│     ├─ movilidad/
│     └─ municerca/
├─ interm/
├─ processed/


docs/
└─ paper/

results/
├─ figs/
├─ predicciones_h/
└─ train_test/

src/
├─ 0.- act_clima.py
├─ 0.- verificar_direccion.py
├─ 1.- preprocesar_datos.py
├─ 2.- analisis datos.py
├─ 3.- model_ML.py
└─ 3.- modelo_SEIR.py

0.- act_clima.ipynb
0.- verificar_direccion.ipynb
1.- preprocesar_datos.ipynb
2.- analisis datos.ipynb
3.- model_ML.ipynb
3.- modelo_SEIR.ipynb
```

## 📦 Instalación paso a paso

### 1️⃣ Clonar el repositorio
```bash
git clone https://github.com/Nainho1703/Plataforma-Dengue.git
cd plataforma-dengue
```

### 2  Instalación rápida
#### Windows
```
py -3.11 -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```
#### Linux /MacOS
```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3) Datos (mínimos necesarios)

**Confidencialidad.** Los datos epidemiológicos son provistos de forma **confidencial** exclusivamente para el desarrollo del modelo.

**Ubicación esperada.** Deben almacenarse en: model/data/raw/casos_raw/

y serán procesados desde allí.

**Formato mínimo.** Los archivos (CSV/Parquet) deben contener al menos estas columnas:

- `sexo`
- `edad_diagnostico`
- `calle_domicilio`
- `numero_domicilio`
- `fecha_apertura`
- `clasificacion_manual`

> Nota: `fecha_apertura` debe estar en formato fecha (YYYY-MM-DD o ISO-8601).  
> Los campos de domicilio se usan para geocodificación/normalización.

**Archivos de ejemplo.** Se incluyen datos sintéticos en: model/data/raw/samples/



## Métricas sugeridas
- Clasificación de **semanas con brote/no brote**: *F1*, *Recall@brote*, PR-AUC.
- Riesgo continuo: *MAE/MAPE* por barrio/semana; *CRPS* (probabilístico).
- Utilidad operativa: *lead time* útil, **alertas** vs. falsas alarmas.

## Flujo de trabajo


## ⚙️ Ejecución de scripts

Cada script corresponde a una etapa del flujo:

| Orden | Script | Descripción |
|:------|:----------------------------|:-------------------------------------------------------------|
| 0 | `0.- act_clima.py` | Actualiza y limpia datos climáticos. |
| 0 | `0.- verificar_direccion.py` | Verifica/normaliza direcciones y ubicaciones. |
| 1 | `1.- preprocesar_datos.py` | Limpieza y unión de fuentes de datos crudos. |
| 2 | `2.- analisis_datos.py` | Análisis descriptivo y correlaciones. |
| 3 | `3.- modelo_.py` | Entrenamiento y evaluación de modelos predictivos. |

### 1) Datos -> 2) Limpieza -> 3) Entrenamiento -> 4) Evaluación -> 5) Artefactos
```
python "model/src/0.- act_clima.py"
python "model/src/0.- verificar_direccion.py"
python "model/src/1.- preprocesar_datos.py"
python "model/src/2.- analisis_datos.py"
python "model/src/3.- modelo_.py"
```



## ⚙️ 1️⃣ Uso por argumentos (CLI)

Ejecutá directamente el script con los parámetros que quieras modificar.

### 🔹 Ejemplo básico
```bash
python model/src/modelo_.py --models XGB-tuned,HGBR-MSE --grids MUN --dates 14D,7D --targets COUNT
```

### 🔹 Parámetros disponibles

| Argumento | Descripción | Ejemplo |
|:-----------|:-------------|:----------|
| `--models` | Modelos a entrenar (o `all`) | `--models XGB-tuned,HGBR-MSE` |
| `--grids` | Grillas espaciales | `--grids MUN,VM` |
| `--dates` | Escalas temporales | `--dates 14D,7D,M` |
| `--targets` | Variable objetivo | `--targets COUNT,INC` |
| `--features` | Set de features (por nombre o regex) | `--features re:Vecinos` |
| `--horizons` | Horizontes de predicción | `--horizons 1,2,3,4` |
| `--outdir` | Carpeta de salida | `--outdir results/exp_01` |


### 🔹 Ejemplo completo
```bash
python model/src/train_cli.py \
  --models XGB-tuned,HGBR-MSE \
  --grids MUN,VM \
  --dates 14D \
  --targets COUNT \
  --features re:Vecinos|Clima \
  --horizons 1,2,3 \
  --outdir results/exp_01
```
## ⚙️ Uso mediante archivo YAML

Para reproducir configuraciones completas sin escribir argumentos largos, podés usar un archivo YAML de configuración.

### 🗂️ Archivo de configuración
Ejemplo: `config/train_config.yaml`
```yaml
models: [XGB-tuned, HGBR-MSE]
grids: ["MUN"]
dates: ["14D", "7D"]
targets: ["COUNT","INC"]
features: ["re:Vecinos|Clima"]
horizons: [1, 2, 3, 4]
outdir: results
```

### Ejecución

```bash
python model/src/train_cli.py --config config/train_config.yaml
```

### Mezclando ambos
```bash
python model/src/train_cli.py --config config/train_config.yaml --models XGB-tuned --horizons 1,2
```

## Roadmap de entregables
- **Producto 1 (M3)**: esquema de plataforma con datos e indicadores (base para variables/indicadores de riesgo).
- **Producto 2 (M7)**: **librerías funcionales** (este repo).
- **Producto 3 (M11–M12)**: integración en **plataforma** con visualización, informes y alertas para usuarios no especializados.

## Calidad, solvencia y perfiles
La ejecución requiere experiencia en **Python**, creación de **librerías**, manejo de **repositorios de datos públicos** y trabajo con **datos epidemiológicos/climáticos/ambientales**.

## Contribuir
