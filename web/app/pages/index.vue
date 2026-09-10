<template>
  <div class="dashboard-grid">
    <!-- Left Panel: 3D Viewer -->
    <section class="viewer-section glass-panel">
      <ClientOnly>
        <div class="viewer-container" ref="viewerContainer">
          <div v-if="!meshUrl" class="empty-state">
            <div class="upload-area" @dragover.prevent @drop.prevent="onDrop" @click="$refs.fileInput.click()">
              <input type="file" ref="fileInput" accept=".stl" style="display: none" @change="onFileChange" />
              <div class="upload-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
              </div>
              <p>Arraste e solte o arquivo STL aqui ou <span>clique para selecionar</span></p>
              <p class="upload-hint">Tamanho máximo: 50MB</p>
            </div>
          </div>
          
          <TresCanvas v-else clear-color="#0a0a0c" window-size>
            <TresPerspectiveCamera :position="[100, 100, 100]" :look-at="[0, 0, 0]" />
            <OrbitControls />
            <TresAmbientLight :intensity="0.5" />
            <TresDirectionalLight :position="[10, 10, 10]" :intensity="1" />
            
            <Suspense>
              <StlModel v-if="meshUrl" :url="meshUrl" />
            </Suspense>
            
            <TresGridHelper :args="[200, 20]" />
            <TresAxesHelper :args="[50]" />
          </TresCanvas>
        </div>
      </ClientOnly>
    </section>

    <!-- Right Panel: Parameters & Pipeline -->
    <section class="controls-section glass-panel">
      <div class="tabs">
        <button class="tab active">Parâmetros Clínicos</button>
      </div>
      
      <div class="tab-content">
        <div class="input-group">
          <label class="input-label">Diâmetro do tubo (mm)</label>
          <input type="number" class="input-field" v-model="params.diametro_tubo" step="0.1" min="1.0" max="5.0" />
        </div>
        
        <div class="input-group">
          <label class="input-label">Folga de ajuste (mm)</label>
          <input type="number" class="input-field" v-model="params.folga_ajuste" step="0.1" min="0.0" max="1.0" />
        </div>
        
        <div class="input-group">
          <label class="input-label">Ângulo de inserção (graus)</label>
          <input type="number" class="input-field" v-model="params.angulo_insercao" step="1" min="-45" max="45" />
        </div>
        
        <div class="input-group">
          <label class="input-label">Espessura mínima (mm)</label>
          <input type="number" class="input-field" v-model="params.espessura_minima" step="0.1" min="0.5" max="3.0" />
        </div>
        
        <button class="btn btn-primary process-btn" @click="processMesh" :disabled="!file || processing">
          <svg v-if="processing" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle>
            <path d="M12 2a10 10 0 0 1 10 10"></path>
          </svg>
          <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5 3 19 12 5 21 5 3"></polygon>
          </svg>
          {{ processing ? 'Processando...' : 'Processar Molde' }}
        </button>
      </div>
      
      <div class="pipeline-status">
        <h3 class="section-title">Pipeline</h3>
        <ul class="status-list">
          <li :class="['status-item', { active: currentStep >= 1, completed: currentStep > 1 }]">
            <span class="status-icon">✓</span> Upload do STL
          </li>
          <li :class="['status-item', { active: currentStep >= 2, completed: currentStep > 2 }]">
            <span class="status-icon">○</span> Segmentação e limpeza
          </li>
          <li :class="['status-item', { active: currentStep >= 3, completed: currentStep > 3 }]">
            <span class="status-icon">○</span> Perfuração paramétrica
          </li>
          <li :class="['status-item', { active: currentStep >= 4, completed: currentStep > 4 }]">
            <span class="status-icon">○</span> Validação de segurança
          </li>
          <li :class="['status-item', { active: currentStep >= 5, completed: currentStep > 5 }]">
            <span class="status-icon">○</span> Exportação
          </li>
        </ul>
        
        <div v-if="metrics" class="metrics-card glass-panel" style="margin-top: 16px; padding: 12px;">
          <h4 style="margin: 0 0 8px 0; font-size: 0.85rem; color: var(--text-secondary);">Estatísticas da Malha:</h4>
          <div style="font-size: 0.8rem; display: flex; flex-direction: column; gap: 4px;">
            <div><strong>Vértices:</strong> {{ metrics.num_vertices }}</div>
            <div><strong>Faces:</strong> {{ metrics.num_faces }}</div>
            <div><strong>Watertight:</strong> <span :style="{color: metrics.is_watertight ? 'var(--success-color)' : 'var(--warning-color)'}">{{ metrics.is_watertight ? 'Sim' : 'Não' }}</span></div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'

const fileInput = ref(null)
const file = ref(null)
const meshUrl = ref(null)
const processing = ref(false)
const currentStep = ref(0)
const jobId = ref(null)
const metrics = ref(null)

const params = reactive({
  diametro_tubo: 2.0,
  folga_ajuste: 0.3,
  angulo_insercao: 15.0,
  espessura_minima: 1.2
})

const onFileChange = (e) => {
  const selected = e.target.files[0]
  if (selected && selected.name.endsWith('.stl')) {
    handleFile(selected)
  }
}

const onDrop = (e) => {
  const dropped = e.dataTransfer.files[0]
  if (dropped && dropped.name.endsWith('.stl')) {
    handleFile(dropped)
  }
}

const handleFile = (f) => {
  file.value = f
  if (meshUrl.value) {
    URL.revokeObjectURL(meshUrl.value)
  }
  meshUrl.value = URL.createObjectURL(f)
  currentStep.value = 1
  metrics.value = null
}

const processMesh = async () => {
  if (!file.value) return
  
  processing.value = true
  currentStep.value = 1
  
  const formData = new FormData()
  formData.append('file', file.value)
  
  try {
    // 1. Upload to FastAPI
    const uploadRes = await fetch('http://localhost:8000/api/v1/upload', {
      method: 'POST',
      body: formData
    })
    
    if (!uploadRes.ok) throw new Error('Upload falhou')
    
    const data = await uploadRes.json()
    jobId.value = data.job_id
    currentStep.value = 2
    
    // 2. Poll for status
    pollStatus(data.job_id)
  } catch (error) {
    console.error(error)
    processing.value = false
    alert('Erro: ' + error.message)
  }
}

const pollStatus = (id) => {
  const interval = setInterval(async () => {
    try {
      const res = await fetch(`http://localhost:8000/api/v1/jobs/${id}`)
      if (!res.ok) return
      
      const data = await res.json()
      
      if (data.status === 'completed') {
        clearInterval(interval)
        processing.value = false
        currentStep.value = 5 // Fully complete for Milestone 1 MVP
        metrics.value = data.mesh_metrics
      } else if (data.status === 'failed') {
        clearInterval(interval)
        processing.value = false
        alert('Falha no processamento.')
      }
    } catch (e) {
      console.error(e)
    }
  }, 2000)
}
</script>

<style scoped>
.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 16px;
  width: 100%;
  height: 100%;
}

.viewer-section {
  position: relative;
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.viewer-container {
  flex: 1;
  position: relative;
  width: 100%;
  height: 100%;
}

.empty-state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
  z-index: 10;
}

.upload-area {
  width: 400px;
  height: 300px;
  border: 2px dashed var(--border-color);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  background: rgba(255, 255, 255, 0.02);
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: center;
  padding: 24px;
}

.upload-area:hover {
  border-color: var(--accent-color);
  background: rgba(59, 130, 246, 0.05);
}

.upload-icon {
  color: var(--accent-color);
  background: rgba(59, 130, 246, 0.1);
  padding: 16px;
  border-radius: 50%;
}

.upload-area p {
  margin: 0;
  color: var(--text-primary);
  font-weight: 500;
}

.upload-area p span {
  color: var(--accent-color);
}

.upload-hint {
  font-size: 0.85rem;
  color: var(--text-secondary) !important;
}

.controls-section {
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  overflow-y: auto;
  padding: 24px;
}

.tabs {
  display: flex;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 24px;
}

.tab {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 10px 16px;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
}

.tab.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent-color);
}

.tab-content {
  display: flex;
  flex-direction: column;
}

.process-btn {
  width: 100%;
  margin-top: 16px;
  padding: 12px;
}

.pipeline-status {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--border-color);
}

.section-title {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

.status-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.9rem;
  color: var(--text-secondary);
  opacity: 0.5;
}

.status-item.active {
  opacity: 1;
  color: var(--text-primary);
}

.status-item.completed {
  color: var(--success-color);
  opacity: 1;
}

.status-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.05);
  font-size: 0.75rem;
}

.completed .status-icon {
  background: rgba(16, 185, 129, 0.2);
  color: var(--success-color);
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
