/**
 * Fudge Ur Uncle - API Client
 * =============================
 * Talks to the FastAPI backend. Uses Vite's proxy so requests to /api
 * are forwarded to http://localhost:8000 in development.
 *
 * In production you can set VITE_API_BASE to point at your deployed backend.
 */

const API_BASE = import.meta.env.VITE_API_BASE || "";
const TOKEN_KEY = "fuu_token";
const USER_KEY = "fuu_user";

export const auth = {
  getToken: () => localStorage.getItem(TOKEN_KEY),
  getUser: () => {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch { return null; }
  },
  setSession: (token, user) => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

// Lightweight fetch wrapper with timeout + JSON parsing
async function apiRequest(path, { method = "GET", body, timeout = 45000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  const token = auth.getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        if (j && j.detail) detail = j.detail;
      } catch { /* ignore */ }
      // If the server rejected our token, drop it so the UI can re-prompt
      // for login instead of looping forever on stale credentials. We only
      // clear when the request was authenticated — an unauthenticated 401
      // (signup-conflict edge case) shouldn't blow away an unrelated token.
      if (res.status === 401 && token) {
        auth.clear();
      }
      const err = new Error(`API ${res.status}: ${detail}`);
      err.status = res.status;
      err.detail = detail;
      throw err;
    }
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

// ---- Endpoint wrappers ----

export const api = {
  health: () => apiRequest("/api/health"),

  signup: ({ email, password, name, state }) =>
    apiRequest("/api/auth/signup", { method: "POST", body: { email, password, name, state } }),

  login: ({ email, password }) =>
    apiRequest("/api/auth/login", { method: "POST", body: { email, password } }),

  logout: () => apiRequest("/api/auth/logout", { method: "POST" }),

  me: () => apiRequest("/api/auth/me"),

  updateMe: ({ name, state, issues, eligibility, notify_alerts }) =>
    apiRequest("/api/auth/me", { method: "PATCH", body: { name, state, issues, eligibility, notify_alerts } }),

  deleteAccount: (password) =>
    apiRequest("/api/auth/me", { method: "DELETE", body: { password } }),

  verifyEmail: (token) =>
    apiRequest("/api/auth/verify-email", { method: "POST", body: { token } }),

  resendVerification: () =>
    apiRequest("/api/auth/resend-verification", { method: "POST" }),

  forgotPassword: (email) =>
    apiRequest("/api/auth/forgot-password", { method: "POST", body: { email } }),

  resetPassword: (token, password) =>
    apiRequest("/api/auth/reset-password", { method: "POST", body: { token, password } }),

  getRepsByState: (state) =>
    apiRequest(`/api/reps/by-state/${encodeURIComponent(state)}`),

  getStateRepsByState: (state) =>
    apiRequest(`/api/state-reps/by-state/${encodeURIComponent(state)}`),

  getStateRep: (peopleId) =>
    apiRequest(`/api/state-reps/${encodeURIComponent(peopleId)}`),

  getStateRepVotes: (peopleId, limit = 20) =>
    apiRequest(`/api/state-reps/${encodeURIComponent(peopleId)}/votes?limit=${limit}`),

  getStateRepStances: (peopleId) =>
    apiRequest(`/api/state-reps/${encodeURIComponent(peopleId)}/stances`),

  getStateRepPromises: (peopleId) =>
    apiRequest(`/api/state-reps/${encodeURIComponent(peopleId)}/promises`, { timeout: 90000 }),

  getRepFundingLite: (bioguideId) =>
    apiRequest(`/api/reps/${encodeURIComponent(bioguideId)}/funding-lite`),

  searchReps: (query) =>
    apiRequest(`/api/reps/search?q=${encodeURIComponent(query)}`),

  searchUnified: (query, state) => {
    const params = new URLSearchParams({ q: query });
    if (state) params.set("state", state);
    return apiRequest(`/api/search/unified?${params}`);
  },

  getProfile: (bioguideId) =>
    apiRequest(`/api/profile/${encodeURIComponent(bioguideId)}`),

  getFunding: (bioguideId) =>
    apiRequest(`/api/funding/${encodeURIComponent(bioguideId)}`),

  getFundingIndustries: (bioguideId, limit = 15) =>
    apiRequest(
      `/api/funding/${encodeURIComponent(bioguideId)}/industries?limit=${limit}`
    ),

  getVotes: (bioguideId, category, limit = 20) => {
    const params = new URLSearchParams({ limit });
    if (category) params.set("category", category);
    return apiRequest(
      `/api/votes/${encodeURIComponent(bioguideId)}?${params}`
    );
  },

  searchBills: (query, limit = 20) =>
    apiRequest(
      `/api/bills/search?q=${encodeURIComponent(query)}&limit=${limit}`
    ),

  getBill: (congress, billType, billNumber) =>
    apiRequest(`/api/bills/${congress}/${billType}/${billNumber}`),

   getAlerts: ({ urgentOnly = false, limit = 20, actorType, actorId } = {}) => {
      const params = new URLSearchParams({ limit });
      if (urgentOnly) params.set("urgent_only", "true");
      if (actorType) params.set("actor_type", actorType);
      if (actorId) params.set("actor_id", actorId);
      return apiRequest(`/api/alerts?${params}`);
    },

    getUpcomingVotes: ({ state, categories, limit = 6 } = {}) => {
      const params = new URLSearchParams({ limit });
      if (state) params.set("state", state);
      if (categories?.length) params.set("categories", categories.join(","));
      return apiRequest(`/api/upcoming-votes?${params}`);
    },

    getAlertsForRep: (bioguideId, limit = 20) =>
      apiRequest(`/api/alerts/by-rep/${encodeURIComponent(bioguideId)}?limit=${limit}`),

    getAlertsForStateRep: (peopleId, limit = 20) =>
      apiRequest(`/api/alerts/by-actor/state/${encodeURIComponent(peopleId)}?limit=${limit}`),

  getEvents: (state, limit = 20) => {
    const params = new URLSearchParams({ limit });
    if (state) params.set("state", state);
    return apiRequest(`/api/events?${params}`);
  },

  getEventArticle: (title) =>
    apiRequest(`/api/events/article?q=${encodeURIComponent(title)}`),

  getStances: (bioguideId) =>
    apiRequest(`/api/profile/${encodeURIComponent(bioguideId)}/stances`),

  getPromises: (bioguideId) =>
    apiRequest(`/api/profile/${encodeURIComponent(bioguideId)}/promises`, { timeout: 90000 }),

  getEventSummary: (event) => {
    const params = new URLSearchParams({ title: event.title || "" });
    if (event.chamber) params.set("chamber", event.chamber);
    if (event.meeting_type) params.set("meeting_type", event.meeting_type);
    if (event.committees?.[0]) params.set("committee", event.committees[0]);
    if (event.bills?.length) params.set("bills", event.bills.map((b) => b.bill).join(", "));
    return apiRequest(`/api/events/summary?${params}`);
  },

  chatSend: ({ messages, context }) =>
    apiRequest("/api/assistant/chat", { method: "POST", body: { messages, context: context || null } }),
};

// ---- Sample data fallback (used if backend is unreachable) ----

export const SAMPLE = {
  reps: [
    {
      bioguide_id: "M001169",
      name: "Christopher Murphy",
      first_name: "Chris",
      last_name: "Murphy",
      party: "D",
      party_full: "Democrat",
      state: "CT",
      district: "CT",
      chamber: "Senate",
      phone: "202-224-4041",
      website: "https://www.murphy.senate.gov",
      office: "136 Hart Senate Office Building",
      funding: {
        total_raised: 27450000,
        pac_total: 4200000,
        small_donor_total: 8100000,
      },
    },
    {
      bioguide_id: "B001277",
      name: "Richard Blumenthal",
      first_name: "Richard",
      last_name: "Blumenthal",
      party: "D",
      party_full: "Democrat",
      state: "CT",
      district: "CT",
      chamber: "Senate",
      phone: "202-224-2823",
      website: "https://www.blumenthal.senate.gov",
      office: "706 Hart Senate Office Building",
      funding: null,
    },
    {
      bioguide_id: "H001047",
      name: "James A. Himes",
      first_name: "Jim",
      last_name: "Himes",
      party: "D",
      party_full: "Democrat",
      state: "CT",
      district: "CT-4",
      chamber: "House",
      phone: "202-225-5541",
      website: "https://himes.house.gov",
      office: "1227 Longworth House Office Building",
      funding: { total_raised: 5800000, pac_total: 1600000, small_donor_total: 1200000 },
    },
  ],

  profile: {
    profile: {
      bioguide_id: "M001169",
      name: "Christopher Murphy",
      party: "D",
      state: "CT",
      district: "CT",
      chamber: "Senate",
      phone: "202-224-4041",
      website: "https://www.murphy.senate.gov",
      office: "136 Hart Senate Office Building",
    },
    funding: {
      total_raised: 27450000,
      total_funding: 29100000,
      pac_total: 4200000,
      individual_total: 18900000,
      small_donor_total: 8100000,
      top_industries: [
        { industry: "Securities & Investment", total_attributed: 1450000 },
        { industry: "Lawyers/Law Firms", total_attributed: 1280000 },
        { industry: "Health Professionals", total_attributed: 980000 },
        { industry: "Education", total_attributed: 720000 },
        { industry: "Real Estate", total_attributed: 650000 },
      ],
      top_donors: [
        { name: "Yale University", total: 245000, type: "individual_employer" },
        { name: "Cigna Corp", total: 85000, type: "pac" },
        { name: "United Technologies", total: 72000, type: "pac" },
        { name: "Travelers Companies", total: 55000, type: "pac" },
      ],
    },
    votes: {
      recent: [
        { bill: "S.1821", title: "Infrastructure Investment Reauthorization Act", date: "2026-04-10", member_vote: "Yea", result: "Passed", category: "infrastructure" },
        { bill: "S.1190", title: "Clean Air Standards Modernization Act", date: "2026-03-28", member_vote: "Nay", result: "Failed", category: "environment" },
        { bill: "S.872", title: "Prescription Drug Pricing Reform Act", date: "2026-03-15", member_vote: "Nay", result: "Passed", category: "healthcare" },
        { bill: "S.441", title: "Social Security Stabilization Act", date: "2026-02-20", member_vote: "Yea", result: "Passed", category: "economy" },
        { bill: "S.203", title: "Federal Minimum Wage Adjustment Act", date: "2026-02-05", member_vote: "Nay", result: "Failed", category: "economy" },
      ],
      total_tracked: 5,
      yea_count: 2,
      nay_count: 3,
    },
    sponsored_bills: [],
    promise_score: null,
    contact: {
      phone: "202-224-4041",
      website: "https://www.murphy.senate.gov",
      office: "136 Hart Senate Office Building",
    },
  },

  stateReps: [
    { people_id: 9001, name: "Martin M. Looney", party: "D", role: "Sen", district: "SD-11", state: "CT", chamber: "Senate" },
    { people_id: 9002, name: "Matt Ritter", party: "D", role: "Rep", district: "HD-1", state: "CT", chamber: "House" },
    { people_id: 9003, name: "Vincent Candelora", party: "R", role: "Rep", district: "HD-86", state: "CT", chamber: "House" },
  ],

  events: [
    { id: 1, title: "Town Hall: Sen. Murphy on Healthcare", date: "Apr 22, 2026", time: "6:00 PM", location: "Hartford City Hall", type: "town_hall" },
    { id: 2, title: "City Council: Zoning Vote", date: "Apr 25, 2026", time: "7:00 PM", location: "Council Chambers", type: "council" },
    { id: 3, title: "Voter Registration Drive", date: "May 1, 2026", time: "10:00 AM", location: "Public Library", type: "registration" },
    { id: 4, title: "Budget Hearing - School District", date: "May 5, 2026", time: "5:30 PM", location: "Board of Ed", type: "hearing" },
  ],

  alerts: [
    { id: 1, text: "Your representative received $75k from oil PACs this week. A climate bill vote is tomorrow.", action: "Call Now", urgent: true, time: "2 hours ago" },
    { id: 2, text: "City council is voting on zoning changes affecting your district. Meeting starts at 6pm.", action: "Get Details", urgent: true, time: "5 hours ago" },
    { id: 3, text: "Sen. Murphy missed 3 votes this month - below his average attendance.", action: "View Record", urgent: false, time: "1 day ago" },
    { id: 4, text: "New campaign finance filing shows shift in donor composition.", action: "See Funding", urgent: false, time: "2 days ago" },
  ],

  // Shape mirrors GET /api/alerts/by-actor/state/{people_id}, used when the
  // backend is unreachable so StateRepAlertsScreen still renders something.
  stateAlerts: [
    {
      id: 9001,
      urgent: true,
      headline: "$45,000 from Public Sector Unions PACs · education vote in 3 days",
      body: "Public Sector Unions PACs (lifetime $45k) → SB00222 (education) on the floor.",
      score: 0.86,
      signals: { T: 1.0, V: 1.0, D: 0.74, R: 0.5, A: 0.5, N: 0.4 },
      donation: { amount: 45000, industry: "public_sector_unions" },
      vote: { bill_number: "SB00222", category: "education" },
      time: "sample data",
    },
    {
      id: 9002,
      urgent: true,
      headline: "$22,000 from Pharmaceuticals PACs · healthcare vote in 1 day",
      body: "Pharmaceuticals & Health Products PACs (lifetime $22k) → SB00429 (healthcare).",
      score: 0.82,
      signals: { T: 1.0, V: 1.0, D: 0.61, R: 0.5, A: 0.5, N: 0.3 },
      donation: { amount: 22000, industry: "pharmaceuticals" },
      vote: { bill_number: "SB00429", category: "healthcare" },
      time: "sample data",
    },
    {
      id: 9003,
      urgent: false,
      headline: "$18,000 from Oil & Gas PACs · environment vote in 7 days",
      body: "Oil & Gas PACs (lifetime $18k) → SB00148 (environment).",
      score: 0.55,
      signals: { T: 1.0, V: 0.7, D: 0.45, R: 0.5, A: 0.5, N: 0.2 },
      donation: { amount: 18000, industry: "oil_gas" },
      vote: { bill_number: "SB00148", category: "environment" },
      time: "sample data",
    },
  ],
};
