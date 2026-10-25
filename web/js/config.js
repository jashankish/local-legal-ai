// Build-time configuration.
//
// apiBaseUrl is empty by default, which runs the app in demo mode: the library
// in web/demo/ is searched in the browser and nothing is sent anywhere. Point
// it at a deployed Local Legal AI backend and every page talks to that instead
// — `bash tools/build-site.sh --api-base-url https://legal-ai.example.com`
// rewrites the line below, so no source change is needed to switch.
const API_BASE_URL = "";

// Resolved from this module's own URL, so the app works at the site root, at
// /legal-ai-demo/, or anywhere else, with no absolute paths anywhere.
const BASE_PATH = new URL("../", import.meta.url).href;

export const CONFIG = {
  apiBaseUrl: API_BASE_URL,
  basePath: BASE_PATH,
  repoUrl: "https://github.com/jashankish/local-legal-ai",
};
