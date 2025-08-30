<template>
  <form @submit.prevent="submitCase" class="case-form">
    <div>
      <label for="fecha">Fecha notificado:</label>
      <input
        id="fecha"
        v-model="newCase.fechas_notificados"
        type="datetime-local"
        required
      />
    </div>
    <div>
      <label for="nombre">Apellido y Nombre:</label>
      <input
        id="nombre"
        v-model="newCase.apellido_y_nombre"
        type="text"
        required
      />
    </div>
    <div>
      <label for="dni">DNI:</label>
      <input id="dni" v-model="newCase.dni" type="text" required />
    </div>
    <div>
      <label for="direccion">Dirección:</label>
      <input
        id="direccion"
        v-model="newCase.direccion"
        type="text"
        required
      />
    </div>
    <div>
      <label for="barrio">Barrio:</label>
      <input id="barrio" v-model="newCase.barrio" type="text" required />
    </div>
    <div>
      <label for="telefono">Teléfono:</label>
      <input id="telefono" v-model="newCase.telefono" type="tel" required />
    </div>
    <button type="submit">Guardar caso</button>
  </form>
</template>

<script>
import axios from 'axios';

export default {
  name: 'CaseForm',
  data() {
    return {
      newCase: {
        fechas_notificados: '',
        apellido_y_nombre: '',
        dni: '',
        direccion: '',
        barrio: '',
        telefono: ''
      }
    };
  },
  methods: {
    async submitCase() {
      console.log("📤 submitCase disparado", this.newCase);
      try {
        const payload = {
          ...this.newCase,
          // convierte a formato ISO esperado por el backend
          fechas_notificados: this.newCase.fechas_notificados.replace('T', ' ') + ':00'
        };
        const res = await axios.post('http://localhost:8000/casos_dengue', payload);
        this.$emit('case-created', res.data.id);
        // reset del formulario
        this.newCase = {
          fechas_notificados: '',
          apellido_y_nombre: '',
          dni: '',
          direccion: '',
          barrio: '',
          telefono: ''
        };
      } catch (e) {
        console.error('Error al crear caso:', e);
        alert('Error al guardar el caso: ' + (e.response?.data?.detail || e.message));
      }
    }
  }
};
</script>

<style scoped>
.case-form {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 20px;
}
.case-form label {
  font-weight: bold;
}
.case-form input {
  width: 100%;
}
.case-form button {
  grid-column: span 2;
  padding: 8px 12px;
  background-color: #3498db;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.case-form button:hover {
  background-color: #2980b9;
}
</style>
