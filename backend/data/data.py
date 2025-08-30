from fastapi import FastAPI
import sqlite3
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
db_path = "mi_base_de_datos5.db"

def get_table_names():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables

def get_table_data(table_name):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(columns, row)) for row in rows]

@app.get("/tables")
def list_tables():
    return {"tables": get_table_names()}

@app.get("/table/{table_name}")
def read_table(table_name: str):
    if table_name not in get_table_names():
        return {"error": "Table not found"}
    return get_table_data(table_name)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
from datetime import datetime
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter


db_path = "mi_base_de_datos5.db"

# Geocoder global
geolocator = Nominatim(user_agent="dengue_app", timeout=10)
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)

class DengueCase(BaseModel):
    fechas_notificados: str
    apellido_y_nombre: str
    dni: str
    direccion: str
    barrio: str
    telefono: str

@app.post("/casos_dengue")
def create_caso(case: DengueCase):
    # 1) Validar fecha
    try:
        datetime.fromisoformat(case.fechas_notificados)
    except ValueError:
        raise HTTPException(400, "Formato de fecha inválido")

    # 2) Geocodificar dirección (añade contexto si lo necesitas)
    query = f"{case.direccion}, Villa María, Córdoba, Argentina"
    loc = geocode(query)
    if loc:
        lat, lon = loc.latitude, loc.longitude
        wkt = f"POINT({lon} {lat})"
    else:
        lat = lon = None
        wkt = None

    # 3) Insertar en la BD
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO casos_dengue
          ([Fechas notificados],
           [APELLIDO Y NOMBRE],
           DNI,
           [DIRECCION],
           [BARRIO],
           [TELEFONO],
           lat,
           lon,
           WKT)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        case.fechas_notificados,
        case.apellido_y_nombre,
        case.dni,
        case.direccion,
        case.barrio,
        case.telefono,
        lat,
        lon,
        wkt
    ))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    return {"status": "ok", "id": new_id, "lat": lat, "lon": lon, "WKT": wkt}