<template>
  <div class="app-container">
    <!-- Header -->
    <header class="app-header glass-panel">
      <div class="logo">
        <div class="logo-icon"></div>
        <h1>AuriMold</h1>
      </div>
      <div class="status-badge">
        <span class="status-dot"></span>
        Status: Ready
      </div>
    </header>

    <main class="app-main">
      <NuxtPage />
    </main>
  </div>
</template>

<style scoped>
.app-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 64px;
  margin: 16px;
  border-radius: 16px;
  z-index: 10;
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  width: 24px;
  height: 24px;
  background: linear-gradient(135deg, var(--accent-color), #8b5cf6);
  border-radius: 6px;
}

.logo h1 {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0;
  letter-spacing: -0.5px;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.03);
  padding: 6px 12px;
  border-radius: 20px;
  border: 1px solid var(--border-color);
}

.status-dot {
  width: 8px;
  height: 8px;
  background: var(--success-color);
  border-radius: 50%;
  box-shadow: 0 0 8px var(--success-color);
}

.app-main {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
  margin: 0 16px 16px 16px;
}
</style>
