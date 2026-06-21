import axios from "axios";

const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const client = axios.create({
  baseURL: apiBaseUrl ? `${apiBaseUrl}/api` : "/api",
  timeout: 12000,
});

export const api = {
  health: () => client.get("/health").then((r) => r.data),
  city: () => client.get("/city").then((r) => r.data),
  corridors: () => client.get("/corridors").then((r) => r.data),
  corridorState: () => client.get("/corridors/state").then((r) => r.data),
  corridorFingerprint: (name) =>
    client
      .get(`/corridors/${encodeURIComponent(name)}/fingerprint`)
      .then((r) => r.data),
  stations: () => client.get("/stations").then((r) => r.data),
  cascade: () => client.get("/cascade").then((r) => r.data),
  audit: () => client.get("/audit").then((r) => r.data),
  fingerprint: () => client.get("/fingerprint").then((r) => r.data),
  validation: () => client.get("/validation").then((r) => r.data),
  backtest: () => client.get("/backtest").then((r) => r.data),
  semantic: () => client.get("/semantic").then((r) => r.data),
  severity: () => client.get("/severity").then((r) => r.data),
  replay: (date) =>
    client.get("/replay", { params: { date } }).then((r) => r.data),
  simulate: (payload) =>
    client.post("/simulate", payload).then((r) => r.data),
  copilot: (query) =>
    client.post("/copilot/query", { query }).then((r) => r.data),
  geocode: (query) =>
    axios
      .get("https://nominatim.openstreetmap.org/search", {
        params: {
          q: query,
          format: "json",
          limit: 5,
          addressdetails: 1,
        },
      })
      .then((r) => r.data),
};
