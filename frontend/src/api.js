/**
 * Fudge Ur Uncle - API Client
 * =============================
 * Talks to the FastAPI backend. Uses Vite's proxy so requests to /api
 * are forwarded to http://localhost:8000 in development.
 *
 * In production you can set VITE_API_BASE to point at your deployed backend.
 */

const API_BASE = import.meta.env.VITE_API_BASE || "";

// Lightweight fetch wrapper with timeout + JSON parsing
async function apiRequest(path, { method = "GET", body, timeout = 45000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`API ${res.status}: ${text || res.statusText}`);
    }
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

// ---- Endpoint wrappers ----

export const api = {
  health: () => apiRequest("/api/health"),

  getRepsByState: (state) =>
    apiRequest(`/api/reps/by-state/${encodeURIComponent(state)}`),

  getRepFundingLite: (bioguideId) =>
    apiRequest(`/api/reps/${encodeURIComponent(bioguideId)}/funding-lite`),

  searchReps: (query) =>
    apiRequest(`/api/reps/search?q=${encodeURIComponent(query)}`),

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

   getAlerts: ({ urgentOnly = false, limit = 20 } = {}) => {
      const params = new URLSearchParams({ limit });
      if (urgentOnly) params.set("urgent_only", "true");
      return apiRequest(`/api/alerts?${params}`);
    },

    getAlertsForRep: (bioguideId, limit = 20) =>
      apiRequest(`/api/alerts/by-rep/${encodeURIComponent(bioguideId)}?limit=${limit}`),

  getEvents: (state, limit = 20) => {
    const params = new URLSearchParams({ limit });
    if (state) params.set("state", state);
    return apiRequest(`/api/events?${params}`);
  },

  getEventArticle: (title) =>
    apiRequest(`/api/events/article?q=${encodeURIComponent(title)}`),

  getEventSummary: (event) => {
    const params = new URLSearchParams({ title: event.title || "" });
    if (event.chamber) params.set("chamber", event.chamber);
    if (event.meeting_type) params.set("meeting_type", event.meeting_type);
    if (event.committees?.[0]) params.set("committee", event.committees[0]);
    if (event.bills?.length) params.set("bills", event.bills.map((b) => b.bill).join(", "));
    return apiRequest(`/api/events/summary?${params}`);
  },
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
};
