
/**
 * TechnoFunda Swing Trading Dashboard
 * Frontend Runtime Configuration
 *
 * Supabase credentials are loaded automatically
 * from the FastAPI backend's .env file.
 *
 * IMPORTANT:
 * - Never expose SUPABASE_SERVICE_ROLE_KEY.
 * - Only the public Supabase URL and publishable/anon key
 *   should be returned to the browser.
 * - FastAPI must be deployed and publicly accessible.
 */

(function () {
  "use strict";

  // Set this to your deployed FastAPI backend HTTPS URL.
  //
  // Example:
  // "https://technofunda-backend.onrender.com"
  //
  // Leave empty ONLY when frontend and backend
  // share the same origin or an API proxy is configured.

  window.API_BASE_URL = window.API_BASE_URL || "";

  window.SUPABASE_CONFIG = {
    url: "",
    anonKey: "",
    ready: false,
    error: null
  };

  async function loadSupabaseConfig() {
    try {
      const base = window.API_BASE_URL.replace(/\/+$/, "");

      const endpoint = `${base}/api/public-config`;

      console.log(
        "[TechnoFunda] Loading Supabase configuration..."
      );

      const response = await fetch(endpoint, {
        method: "GET",
        cache: "no-store",
        headers: {
          "Accept": "application/json"
        }
      });

      if (!response.ok) {
        throw new Error(
          `Backend configuration request failed: HTTP ${response.status}`
        );
      }

      const data = await response.json();

      const url = String(data.url || "").trim();

      const anonKey = String(data.anonKey || "").trim();

      if (!url || !anonKey) {
        throw new Error(
          "Backend did not return Supabase URL and public key."
        );
      }

      if (!/^https:\/\/[^/]+\.supabase\.co\/?$/.test(url)) {
        throw new Error(
          "Invalid Supabase project URL returned by backend."
        );
      }

      Object.assign(window.SUPABASE_CONFIG, {
        url: url.replace(/\/+$/, ""),
        anonKey: anonKey,
        ready: true,
        error: null
      });

      console.log(
        "[TechnoFunda] Supabase configuration loaded successfully."
      );

    } catch (error) {
      Object.assign(window.SUPABASE_CONFIG, {
        url: "",
        anonKey: "",
        ready: false,
        error: error.message
      });

      console.error(
        "[TechnoFunda] Failed to load Supabase configuration:",
        error
      );
    }

    return window.SUPABASE_CONFIG;
  }

  window.SUPABASE_CONFIG_READY = loadSupabaseConfig();

})();
