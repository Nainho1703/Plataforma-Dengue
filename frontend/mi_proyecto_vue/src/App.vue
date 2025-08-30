<template>
  <div>
    <!-- Agregar caso -->
    <a href="#" @click.prevent="showForm = !showForm" class="add-link">
      {{ showForm ? 'Cancelar' : 'Agregar caso' }}
    </a>
    <CaseForm v-if="showForm" @case-created="onCaseCreated" />

    <div v-else>
      <!-- Selector de tabla -->
      <h1>Selecciona una tabla</h1>
      <select v-model="selectedTable" @change="fetchTableData">
        <option v-for="t in tables" :key="t" :value="t">{{ t }}</option>
      </select>

      <!-- Raw vs Mensual -->
      <div v-if="rows.length" style="margin:1em 0;">
        <label>
          <input type="radio" value="monthly" v-model="viewMode" /> Agrupado por mes
        </label>
        <label style="margin-left:1em;">
          <input type="radio" value="raw" v-model="viewMode" /> Mostrar todo
        </label>
      </div>

      <!-- Slider mensual -->
      <div v-if="viewMode==='monthly' && monthlyGroups.length" class="month-slider">
        <button @click="prevMonth" :disabled="monthIndex===0">←</button>
        <span>{{ monthlyGroups[monthIndex].monthYear }}</span>
        <button @click="nextMonth" :disabled="monthIndex===monthlyGroups.length-1">→</button>
      </div>

      <!-- Buscador -->
      <div class="search-container" v-if="displayedRows.length">
        <input
          v-model="searchTerm"
          type="text"
          placeholder="Buscar nombre, DNI, dirección..."
        />
      </div>
      <!-- Mapa -->
      <l-map
        style="height:500px; width:100%;"
        :zoom="12"
        :center="mapCenter"
      >
        <l-tile-layer :url="tileLayerUrl" />
        <l-feature-group>
          <template v-for="item in shapesForDisplay" :key="item._uid">
            <l-marker
              v-if="item.type==='Point'"
              :lat-lng="item.coords"
            />
            <template v-else-if="item.coords">
              <template v-for="(seg,i) in item.coords" :key="`${item._uid}-${i}`">
                <l-polygon v-if="item.type==='Polygon'" :lat-lngs="seg" />
                <l-polyline v-else :lat-lngs="seg" />
              </template>
            </template>
          </template>
        </l-feature-group>
      </l-map>
      <!-- Tabla -->
      <div v-if="filteredRows.length" style="margin:20px 0;">
        <h2>Registros de {{ selectedTable }}</h2>
        <table>
          <thead>
            <tr>
              <th v-for="col in columns" :key="col">{{ col }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in paginatedRows" :key="row._uid">
              <td v-for="col in columns" :key="col">{{ row[col] }}</td>
            </tr>
          </tbody>
        </table>

        <!-- Paginación -->
        <div class="pagination">
          <button @click="prevPage" :disabled="currentPage===1">Anterior</button>
          <span>Página {{ currentPage }} / {{ totalPages }}</span>
          <button @click="nextPage" :disabled="currentPage===totalPages">Siguiente</button>
        </div>
      </div>
      <p v-else>No hay registros que mostrar.</p>


    </div>
  </div>
</template>

<script>
import axios from "axios";
import "leaflet/dist/leaflet.css";
import {
  LMap,
  LTileLayer,
  LFeatureGroup,
  LPolygon,
  LPolyline,
  LMarker
} from "@vue-leaflet/vue-leaflet";
import dayjs from "dayjs";
import CaseForm from "./components/CaseForm.vue";

export default {
  components: {
    LMap, LTileLayer, LFeatureGroup,
    LPolygon, LPolyline, LMarker,
    CaseForm
  },
  data() {
    return {
      tables: [],
      selectedTable: null,
      rows: [],            // Todos los registros crudos
      columns: [],         // Cabeceras de tabla
      shapes: [],          // Geometrías WKT→Leaflet
      showForm: false,

      // Vista raw vs mensual
      viewMode: "monthly",
      monthlyGroups: [],   // [{ monthYear:"2025-06", rows:[…] }]
      monthIndex: 0,

      // Paginación y búsqueda
      currentPage: 1,
      pageSize: 50,
      searchTerm: "",

      // Mapa
      tileLayerUrl: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      mapCenter: [-32.40751, -63.24016]
    };
  },
  computed: {
    // Filas según raw/monthly
    displayedRows() {
      if (this.viewMode === "raw") return this.rows;
      if (!this.monthlyGroups.length) return [];
      return this.monthlyGroups[this.monthIndex].rows;
    },
    // Filtrado de búsqueda
    filteredRows() {
      if (!this.searchTerm) return this.displayedRows;
      const t = this.searchTerm.toLowerCase();
      return this.displayedRows.filter(r =>
        this.columns.some(c =>
          String(r[c] || "").toLowerCase().includes(t)
        )
      );
    },
    totalPages() {
      return Math.max(1,
        Math.ceil(this.filteredRows.length / this.pageSize)
      );
    },
    paginatedRows() {
      const start = (this.currentPage - 1) * this.pageSize;
      return this.filteredRows.slice(start, start + this.pageSize);
    },
    // Shapes que corresponden a `displayedRows`
    shapesForDisplay() {
      const uids = new Set(this.displayedRows.map(r => r._uid));
      return this.shapes
        .filter(s => uids.has(s._uid))
        .filter(s => {
          // Si es un punto, comprobar que no sea NaN
          if (s.type === 'Point') {
            const [lat, lng] = s.coords;
            return !isNaN(lat) && !isNaN(lng);
          }
          // Para polígonos/lineas podrías hacer validaciones similares si quieres
          return true;
        });
    }
  },
  watch: {
    // Reset page al cambiar búsqueda o tabla o mes
    searchTerm() { this.currentPage = 1; },
    selectedTable() { this.currentPage = 1; },
    monthIndex() { this.currentPage = 1; },
    viewMode(val) {
      if (val === "monthly") this.monthIndex = 0;
    }
  },
  mounted() {
    this.fetchTables();
  },
  methods: {
    async fetchTables() {
      const res = await axios.get("http://localhost:8000/tables");
      this.tables = res.data.tables;
    },
    async fetchTableData() {
      if (!this.selectedTable) return;
      const res = await axios.get(`http://localhost:8000/table/${this.selectedTable}`);
      const data = Array.isArray(res.data) ? res.data : res.data.data || [];

      // Añadimos un UID para enlazar filas→shapes
      this.rows = data.map((r,i) => ({ ...r, _uid: `${this.selectedTable}-${i}` }));
      this.columns = this.rows.length ? Object.keys(this.rows[0]) : [];

      // Agrupar por mes-año
      const groups = {};
      this.rows.forEach(r => {
        const dt = dayjs(r["Fechas notificados"]);
        const key = dt.isValid() ? dt.format("YYYY-MM") : "sin-fecha";
        if (!groups[key]) groups[key] = [];
        groups[key].push(r);
      });
      this.monthlyGroups = Object.entries(groups)
        .sort((a,b)=>a[0].localeCompare(b[0]))
        .map(([monthYear, rows]) => ({ monthYear, rows }));

      // Parse WKT → Shapes
      this.shapes = this.rows
        .map(r => {
          const wkt = r.WKT || r.wkt;
          if (!wkt) return null;
          // POINT
          if (wkt.startsWith("POINT")) {
            const [lon,lat] = wkt.slice(6,-1).split(/\s+/).map(Number);
            return { _uid: r._uid, type:"Point", coords:[lat,lon] };
          }
          // MULTIPOLYGON
          if (wkt.startsWith("MULTIPOLYGON")) {
            const inner = wkt.replace(/^MULTIPOLYGON\s*\(\(\(/,"").replace(/\)\)\)$/,"");
            const coords = inner.split(")),((")
              .map(poly=>poly.split("),(")
                .map(ring=>ring.split(",")
                  .map(pt=>{ 
                    const [lng,lat]=pt.trim().split(/\s+/).map(Number);
                    return [lat,lng];
                  })
                )
              );
            return { _uid: r._uid, type:"Polygon", coords };
          }
          // MULTILINESTRING
          if (wkt.startsWith("MULTILINESTRING")) {
            const inner = wkt.replace(/^MULTILINESTRING\s*\(\(/,"").replace(/\)\)$/,"");
            const coords = inner.split("),(")
              .map(seg=>seg.split(",")
                .map(pt=>{ 
                  const [lng,lat]=pt.trim().split(/\s+/).map(Number);
                  return [lat,lng];
                })
              );
            return { _uid: r._uid, type:"LineString", coords };
          }
          return null;
        })
        .filter(x=>x);
    },

    // Navegación de meses
    prevMonth() {
      if (this.monthIndex>0) this.monthIndex--;
    },
    nextMonth() {
      if (this.monthIndex<this.monthlyGroups.length-1) this.monthIndex++;
    },

    // Paginación
    prevPage() {
      if (this.currentPage>1) this.currentPage--;
    },
    nextPage() {
      if (this.currentPage<this.totalPages) this.currentPage++;
    },

    // Se dispara tras crear un caso
    onCaseCreated(newId) {
      this.showForm = false;
      this.fetchTableData();
      this.$nextTick(()=>{
        alert(`Caso creado con ID ${newId}`);
      });
    }
  }
};
</script>

<style scoped>
.add-link {
  color: #3498db; cursor: pointer;
  margin-bottom: 10px; display: inline-block;
}
.add-link:hover { text-decoration: underline; }

table { border-collapse: collapse; width:100%; }
th, td { padding:4px; border:1px solid #ccc; text-align:left; }

.month-slider {
  margin: 10px 0;
  display: flex; align-items: center;
}
.month-slider button {
  padding: 4px 8px; margin: 0 8px;
}

.search-container {
  margin: 1em 0;
}

.pagination {
  margin-top: 0.5em;
}
.pagination button {
  margin: 0 4px;
}
</style>
