/**
 * TechnoFunda Swing Trading Dashboard
 * Frontend Runtime Configuration
 *
 * Supabase public credentials for live data fetching directly in the browser.
 * Data security is enforced by Supabase Row-Level Security (RLS) policies.
 */

(function () {
  "use strict";

  // Public Supabase project URL and anon/publishable key
  const SUPABASE_URL = "https://trejvbjnfcrjorvxaqud.supabase.co";
  const SUPABASE_ANON_KEY = "sb_publishable_HxWuPJw-abwbsBSsN_j1lw_giMz4OpW";

  // Set this ONLY if you have deployed the FastAPI backend (e.g., Render, Railway)
  // and wish to trigger scans on-demand from the browser.
  // Leave empty for Supabase cloud mode (automated scans via GitHub Actions).
  window.API_BASE_URL = window.API_BASE_URL || "";

  window.SUPABASE_CONFIG = {
    url: SUPABASE_URL,
    anonKey: SUPABASE_ANON_KEY,
    ready: true,
    error: null
  };

  window.SUPABASE_CONFIG_READY = Promise.resolve(window.SUPABASE_CONFIG);

  console.log("[TechnoFunda] Supabase runtime configuration loaded.");
})();
