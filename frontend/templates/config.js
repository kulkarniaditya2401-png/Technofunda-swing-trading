/**
 * TechnoFunda Swing Trading Dashboard
 * Frontend Runtime Configuration
 *
 * Connects directly to Supabase for instant data feeds, and connects to the
 * live Python FastAPI backend on Render.com when configured for on-demand scans.
 */

(function () {
  "use strict";

  // Public Supabase project URL and anon/publishable key
  const SUPABASE_URL = "https://trejvbjnfcrjorvxaqud.supabase.co";
  const SUPABASE_ANON_KEY = "sb_publishable_HxWuPJw-abwbsBSsN_j1lw_giMz4OpW";

  // Check localStorage for saved Render backend URL, or use window.API_BASE_URL
  const storedBackendUrl = (typeof localStorage !== "undefined" && localStorage.getItem("technofunda_backend_url")) || "";
  window.API_BASE_URL = window.API_BASE_URL || storedBackendUrl || "";

  window.SUPABASE_CONFIG = {
    url: SUPABASE_URL,
    anonKey: SUPABASE_ANON_KEY,
    ready: true,
    error: null
  };

  window.SUPABASE_CONFIG_READY = Promise.resolve(window.SUPABASE_CONFIG);

  console.log("[TechnoFunda] Runtime configuration ready. Backend:", window.API_BASE_URL || "Cloud mode (Supabase)");
})();
