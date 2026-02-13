export const getWsUrl = () => {
  let envUrl = import.meta.env.VITE_WS_URL || import.meta.env.VITE_API_URL;
  
  if (envUrl) {
    // 1. Convert http/https to ws/wss if needed
    envUrl = envUrl.replace(/^http/, 'ws');
    
    // 2. Ensure it ends with /ws
    if (!envUrl.endsWith('/ws')) {
      // Remove trailing slash if exists before appending /ws
      envUrl = envUrl.replace(/\/$/, '') + '/ws';
    }
    return envUrl;
  }
  
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
};

export const getApiBase = () => {
  const wsUrl = getWsUrl();
  // If it's the current host (no env var), return empty string for relative paths
  if (!import.meta.env.VITE_WS_URL && !import.meta.env.VITE_API_URL) {
    return '';
  }
  // Convert wss://.../ws to https://...
  return wsUrl.replace(/^ws/, 'http').replace(/\/ws$/, '');
};

export const WS_URL = getWsUrl();
export const API_BASE = getApiBase();
