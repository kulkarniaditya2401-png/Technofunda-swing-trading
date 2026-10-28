
/**
 * TechnoFunda runtime configuration.
 *
 * Automatically fetches public Supabase credentials
 * from the FastAPI backend.
 *
 * If FastAPI is hosted separately, enter its HTTPS URL
 * in API_BASE_URL below.
 *
 * NEVER put a Supabase secret or service-role key here.
 */

window.API_BASE_URL = window.API_BASE_URL || "";

window.SUPABASE_CONFIG = {
  url: "",
  anonKey: "",
  ready: false,
  error: null
};

window.SUPABASE_CONFIG_READY = (async () => {
  try {
    const base = window.API_BASE_URL.replace(/\/$/, "");

    const response = await fetch(
      `${base}/api/public-config`,
      {
        cache: "no-store"
      }
    );

    if (!response.ok) {
      throw new Error(
        `Config endpoint HTTP ${response.status}`
      );
    }

    const data = await response.json();

    if (!data.url || !data.anonKey) {
      throw new Error(
        "Missing public Supabase URL/key"
      );
    }

    Object.assign(window.SUPABASE_CONFIG, {
      url: data.url,
      anonKey: data.anonKey,
      ready: true,
      error: null
    });

  } catch (err) {
    window.SUPABASE_CONFIG.error = err.message;

    console.error(
      "[Config] Failed to load Supabase public configuration:",
      err
    );
  }

  return window.SUPABASE_CONFIG;
})();
