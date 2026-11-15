/**
 * TechnoFunda Swing Trading Dashboard
 * Frontend Runtime Configuration
 *
 * Connects directly to Supabase for instant real-time data feeds, and connects to the
 * live Python FastAPI backend on Render.com for on-demand live scanning.
 */

(function () {
  "use strict";

  // Public Supabase project URL and anon/publishable key
  const SUPABASE_URL = "https://trejvbjnfcrjorvxaqud.supabase.co";
  const SUPABASE_ANON_KEY = "sb_publishable_HxWuPJw-abwbsBSsN_j1lw_giMz4OpW";

  // Production Render Python backend URL for on-demand live scanning
  const RENDER_BACKEND_URL = "https://technofunda-backend.onrender.com";

  window.API_BASE_URL = RENDER_BACKEND_URL;

  window.SUPABASE_CONFIG = {
    url: SUPABASE_URL,
    anonKey: SUPABASE_ANON_KEY,
    ready: true,
    error: null
  };

  window.SUPABASE_CONFIG_READY = Promise.resolve(window.SUPABASE_CONFIG);

  console.log("[TechnoFunda] Connected to live Python backend:", window.API_BASE_URL);
})();
