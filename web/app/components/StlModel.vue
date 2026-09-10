<template>
  <TresMesh ref="meshRef">
    <TresMeshStandardMaterial :color="'#e0e0e0'" :roughness="0.5" :metalness="0.1" side="DoubleSide" />
  </TresMesh>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'
import * as THREE from 'three'

const props = defineProps({
  url: {
    type: String,
    required: true
  }
})

const meshRef = ref(null)
let currentGeometry = null

const loadModel = () => {
  if (!props.url || !meshRef.value) return
  
  const loader = new STLLoader()
  loader.load(props.url, (geometry) => {
    // Dispose previous geometry if exists
    if (currentGeometry) {
      currentGeometry.dispose()
    }
    
    currentGeometry = geometry
    
    // Center the geometry
    geometry.computeBoundingBox()
    geometry.center()
    
    // Compute vertex normals for smooth shading
    geometry.computeVertexNormals()
    
    if (meshRef.value) {
      meshRef.value.geometry = geometry
      
      // Auto-scale to fit view
      const boundingBox = geometry.boundingBox
      const size = new THREE.Vector3()
      boundingBox.getSize(size)
      const maxDim = Math.max(size.x, size.y, size.z)
      const scale = 50 / maxDim
      meshRef.value.scale.set(scale, scale, scale)
    }
  })
}

watch(() => props.url, loadModel)
onMounted(loadModel)

onUnmounted(() => {
  if (currentGeometry) {
    currentGeometry.dispose()
  }
})
</script>
