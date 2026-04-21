import { useState, useEffect } from "react";
import { api, SAMPLE } from "./api.js";

// ============================================================
// CONSTANTS
// ============================================================

const SCREENS = {
  SPLASH: "splash",
  CREATE_ACCOUNT: "create_account",
  LOGIN: "login",
  ISSUE_SELECT: "issue_select",
  DASHBOARD: "dashboard",
  SEARCH: "search",
  POLITICIAN_PROFILE: "politician_profile",
  FUNDING: "funding",
  VOTING_HISTORY: "voting_history",
  PROMISE_SCORING: "promise_scoring",
  TIMELINE: "timeline",
  TAKE_ACTION: "take_action",
  CONTACT_REP: "contact_rep",
  EVENTS: "events",
  LEARN_TO_VOTE: "learn_to_vote",
  SETTINGS: "settings",
  ALERTS: "alerts",
};

const ISSUES = [
  "Healthcare", "Taxes", "Environment", "Immigration",
  "Education", "Housing", "Workers' Rights", "Financial Regulation",
  "Military/Defense", "Gun Policy", "Criminal Justice", "Technology/Privacy",
];

const font = "'IBM Plex Mono', 'Courier New', monospace";
const fontSans = "'IBM Plex Sans', 'Helvetica Neue', sans-serif";

const colors = {
  // Light, airy base — like a crisp morning
  bg: "#fdfbf7",           // warm off-white (softer than pure white)
  surface: "#ffffff",       // clean cards
  surfaceLight: "#f5f1e8",  // subtle cream for raised elements
  border: "#e4dcc8",        // warm sand border
  borderLight: "#d4c8a8",   // slightly stronger for emphasis

  // Readable, warm text
  text: "#1a2744",          // deep navy instead of harsh black
  textMuted: "#5a6b85",     // soft slate-blue

  // Patriotic accent — toned-down, confident red (not alarm-red)
  accent: "#c8102e",        // "Old Glory" red — classic, not scary
  accentDim: "#c8102e1a",   // 10% tint for backgrounds

  // Status colors — warmer, friendlier versions
  green: "#2e8b57",         // sea green, more inviting than neon
  greenDim: "#2e8b5722",
  red: "#c8102e",           // match accent for consistency
  redDim: "#c8102e1a",
  yellow: "#d4a017",        // warm gold instead of harsh yellow
  yellowDim: "#d4a01722",
  blue: "#002868",          // "Old Glory" navy blue
  blueDim: "#00286822",
  purple: "#6b4c9a",        // softer purple

  // Political party colors — classic, readable
  dem: "#002868",           // Old Glory blue
  rep: "#c8102e",           // Old Glory red
};

// ============================================================
// STYLES
// ============================================================

const s = {
  phone: {
    width: 375, height: 812, borderRadius: 40,
    border: `2px solid ${colors.border}`,
    background: colors.bg, position: "relative",
    overflow: "hidden", fontFamily: fontSans,
    color: colors.text, fontSize: 13,
  },
  statusBar: {
    height: 44, display: "flex", alignItems: "center",
    justifyContent: "space-between", padding: "0 24px",
    fontSize: 11, color: colors.textMuted, fontFamily: font,
    flexShrink: 0,
  },
  header: {
    padding: "0 20px 12px", borderBottom: `1px solid ${colors.border}`,
    flexShrink: 0,
  },
  headerTitle: {
    fontSize: 20, fontWeight: 700, fontFamily: font,
    color: colors.text, margin: 0,
  },
  headerSub: {
    fontSize: 11, color: colors.textMuted, marginTop: 2,
  },
  body: {
    padding: "12px 20px", overflowY: "auto", flex: 1,
  },
  navBar: {
    height: 56, display: "flex", borderTop: `1px solid ${colors.border}`,
    background: colors.surface, position: "absolute", bottom: 0,
    left: 0, right: 0,
  },
  navItem: (active) => ({
    flex: 1, display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center", gap: 3,
    fontSize: 9, fontFamily: font, cursor: "pointer",
    color: active ? colors.accent : colors.textMuted,
    background: "none", border: "none", padding: 0,
    transition: "color 0.15s",
  }),
  btn: (variant = "primary") => ({
    width: "100%", padding: "12px 16px", border: "none",
    borderRadius: 8, fontFamily: font, fontSize: 13,
    fontWeight: 600, cursor: "pointer", textAlign: "center",
    transition: "all 0.15s",
    ...(variant === "primary" ? {
      background: colors.accent, color: "#fff",
    } : variant === "outline" ? {
      background: "transparent", color: colors.accent,
      border: `1.5px solid ${colors.accent}`,
    } : {
      background: colors.surfaceLight, color: colors.text,
      border: `1px solid ${colors.border}`,
    }),
  }),
  input: {
    width: "100%", padding: "10px 12px", background: colors.surfaceLight,
    border: `1px solid ${colors.border}`, borderRadius: 8,
    color: colors.text, fontFamily: font, fontSize: 13,
    outline: "none", boxSizing: "border-box",
  },
  chip: (selected) => ({
    padding: "8px 14px", borderRadius: 20, fontSize: 12,
    fontFamily: font, cursor: "pointer",
    transition: "all 0.15s", fontWeight: selected ? 600 : 400,
    background: selected ? colors.accentDim : colors.surfaceLight,
    color: selected ? colors.accent : colors.textMuted,
    border: `1px solid ${selected ? colors.accent : colors.border}`,
  }),
  card: {
    background: colors.surfaceLight, borderRadius: 10,
    border: `1px solid ${colors.border}`, padding: "14px",
    marginBottom: 10,
  },
  badge: (color) => ({
    display: "inline-block", padding: "2px 8px", borderRadius: 4,
    fontSize: 10, fontFamily: font, fontWeight: 600,
    background: color === "green" ? colors.greenDim : color === "red" ? colors.redDim : color === "yellow" ? colors.yellowDim : colors.blueDim,
    color: color === "green" ? colors.green : color === "red" ? colors.red : color === "yellow" ? colors.yellow : colors.blue,
  }),
  backBtn: {
    background: "none", border: "none", color: colors.accent,
    fontFamily: font, fontSize: 12, cursor: "pointer",
    padding: "4px 0", marginBottom: 8, display: "flex",
    alignItems: "center", gap: 4,
  },
  section: { marginBottom: 16 },
  sectionTitle: {
    fontSize: 11, fontWeight: 700, fontFamily: font,
    color: colors.textMuted, textTransform: "uppercase",
    letterSpacing: 1.2, marginBottom: 8,
  },
  divider: { height: 1, background: colors.border, margin: "12px 0" },
};

// ============================================================
// UTILITIES
// ============================================================

const fmt = (n) => {
  if (!n) return "$0";
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n}`;
};

// ============================================================
// SMALL COMPONENTS
// ============================================================

const Icon = ({ type, size = 18, color = "currentColor" }) => {
  const p = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: color, strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };
  const icons = {
    home: <svg {...p}><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>,
    search: <svg {...p}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>,
    bell: <svg {...p}><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>,
    settings: <svg {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>,
    back: <svg {...p}><polyline points="15 18 9 12 15 6"/></svg>,
    phone: <svg {...p}><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6A19.79 19.79 0 012.12 4.18 2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg>,
    mail: <svg {...p}><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>,
    calendar: <svg {...p}><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>,
    dollar: <svg {...p}><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>,
    vote: <svg {...p}><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>,
    alert: <svg {...p}><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
    star: <svg {...p}><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>,
    clock: <svg {...p}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>,
    megaphone: <svg {...p}><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>,
    wifi: <svg {...p}><path d="M5 12.55a11 11 0 0114.08 0"/><path d="M1.42 9a16 16 0 0121.16 0"/><path d="M8.53 16.11a6 6 0 016.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>,
  };
  return icons[type] || null;
};

const ProgressBar = ({ value, max = 100, color = colors.accent, height = 6 }) => (
  <div style={{ width: "100%", height, background: colors.border, borderRadius: height / 2, overflow: "hidden" }}>
    <div style={{ width: `${Math.min(100, (value / max) * 100)}%`, height: "100%", background: color, borderRadius: height / 2, transition: "width 0.5s ease" }} />
  </div>
);

const PartyBadge = ({ party }) => (
  <span style={{ display: "inline-block", width: 20, height: 20, borderRadius: "50%", background: party === "D" ? colors.dem : party === "R" ? colors.rep : colors.textMuted, color: "#fff", fontSize: 11, fontWeight: 700, fontFamily: font, textAlign: "center", lineHeight: "20px" }}>
    {party}
  </span>
);

const Avatar = ({ name, size = 48, party }) => {
  const bg = party === "D" ? colors.dem : party === "R" ? colors.rep : colors.accent;
  const initial = (name || "?").split(" ").pop()[0] || "?";
  return (
    <div style={{ width: size, height: size, borderRadius: "50%", background: `linear-gradient(135deg, ${bg}44, ${bg}22)`, border: `2px solid ${bg}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: size * 0.38, fontWeight: 700, fontFamily: font, color: bg, flexShrink: 0 }}>
      {initial}
    </div>
  );
};

const StatusBar = ({ offline }) => (
  <div style={s.statusBar}>
    <span>9:41</span>
    <span style={{ fontSize: 9, letterSpacing: 0.5, display: "flex", alignItems: "center", gap: 4 }}>
      {offline && <span style={{ color: colors.yellow }}>OFFLINE</span>}
      FUDGE UR UNCLE
    </span>
    <span>100%</span>
  </div>
);

const BackButton = ({ onClick, label = "Back" }) => (
  <button style={s.backBtn} onClick={onClick}>
    <Icon type="back" size={14} /> {label}
  </button>
);

const NavBar = ({ active, onNav }) => {
  const items = [
    { id: SCREENS.DASHBOARD, icon: "home", label: "Home" },
    { id: SCREENS.SEARCH, icon: "search", label: "Search" },
    { id: SCREENS.ALERTS, icon: "bell", label: "Alerts" },
    { id: SCREENS.EVENTS, icon: "calendar", label: "Events" },
    { id: SCREENS.SETTINGS, icon: "settings", label: "Settings" },
  ];
  return (
    <div style={s.navBar}>
      {items.map((it) => (
        <button key={it.id} style={s.navItem(active === it.id)} onClick={() => onNav(it.id)}>
          <Icon type={it.icon} size={18} />
          <span>{it.label}</span>
        </button>
      ))}
    </div>
  );
};

const Loading = ({ label = "Loading..." }) => (
  <div style={{ padding: 40, textAlign: "center" }}>
    <div style={{ width: 24, height: 24, border: `2px solid ${colors.border}`, borderTopColor: colors.accent, borderRadius: "50%", margin: "0 auto 12px", animation: "spin 0.8s linear infinite" }} />
    <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: font }}>{label}</div>
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </div>
);

const ErrorBanner = ({ error, onRetry }) => (
  <div style={{ ...s.card, background: colors.redDim, borderColor: colors.red + "44" }}>
    <div style={{ fontSize: 12, fontWeight: 600, color: colors.red, marginBottom: 4 }}>
      Connection problem
    </div>
    <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 8 }}>
      {error}
    </div>
    {onRetry && (
      <button style={{ ...s.btn("outline"), padding: "6px 12px", fontSize: 11, width: "auto", color: colors.red, borderColor: colors.red }} onClick={onRetry}>
        Retry
      </button>
    )}
  </div>
);

// ============================================================
// CUSTOM HOOKS
// ============================================================

/** Fetch data from API with loading, error, and fallback support. */
function useApi(fetchFn, deps = [], fallback = null) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [offline, setOffline] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    setOffline(false);
    try {
      const result = await fetchFn();
      setData(result);
    } catch (err) {
      console.warn("API error, using fallback:", err.message);
      if (fallback !== null) {
        setData(fallback);
        setOffline(true);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error, offline, reload: load };
}

// ============================================================
// SCREENS
// ============================================================

// 1. SPLASH
const SplashScreen = ({ onNav, offline }) => (
  <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
    <StatusBar offline={offline} />
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "0 40px", textAlign: "center" }}>
      <div style={{ fontSize: 42, fontWeight: 800, fontFamily: font, lineHeight: 1.1, marginBottom: 8 }}>
        <span style={{ color: colors.accent }}>FUDGE</span>
        <br />
        <span style={{ color: colors.text }}>UR UNCLE</span>
      </div>
      <p style={{ color: colors.textMuted, fontSize: 13, lineHeight: 1.5, marginBottom: 40, fontFamily: font }}>
        Hold your politicians accountable.<br />Follow the money. Take action.
      </p>
      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 12 }}>
        <button style={s.btn("primary")} onClick={() => onNav(SCREENS.CREATE_ACCOUNT)}>Create Account</button>
        <button style={s.btn("outline")} onClick={() => onNav(SCREENS.LOGIN)}>Log In</button>
      </div>
    </div>
    <div style={{ padding: "20px 40px 40px", textAlign: "center", fontSize: 10, color: colors.textMuted, fontFamily: font }}>
      Democracy requires participation.
    </div>
  </div>
);

// 2. CREATE ACCOUNT
const CreateAccountScreen = ({ onNav, onSetState, offline }) => {
  const [state, setStateVal] = useState("CT");
  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingTop: 20 }}>
        <BackButton onClick={() => onNav(SCREENS.SPLASH)} />
        <h2 style={{ ...s.headerTitle, marginBottom: 4 }}>Create Account</h2>
        <p style={{ color: colors.textMuted, fontSize: 12, marginBottom: 20, marginTop: 0 }}>Your data stays yours. We never sell it.</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={{ fontSize: 11, fontFamily: font, color: colors.textMuted, display: "block", marginBottom: 4 }}>Full Name</label>
            <input style={s.input} placeholder="Jane Doe" />
          </div>
          <div>
            <label style={{ fontSize: 11, fontFamily: font, color: colors.textMuted, display: "block", marginBottom: 4 }}>Email</label>
            <input style={s.input} placeholder="jane@example.com" />
          </div>
          <div>
            <label style={{ fontSize: 11, fontFamily: font, color: colors.textMuted, display: "block", marginBottom: 4 }}>State (2-letter)</label>
            <input style={s.input} placeholder="CT" value={state} onChange={(e) => setStateVal(e.target.value.toUpperCase().slice(0, 2))} maxLength={2} />
            <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 4, fontFamily: font }}>
              We use this to find your representatives
            </div>
          </div>
          <div style={s.divider} />
          <label style={{ fontSize: 11, fontFamily: font, color: colors.textMuted, display: "block", marginBottom: 4 }}>Password</label>
          <input style={s.input} type="password" placeholder="Min 8 characters" />
          <button style={{ ...s.btn("primary"), marginTop: 8 }} onClick={() => { onSetState(state); onNav(SCREENS.ISSUE_SELECT); }}>Continue</button>
        </div>
      </div>
    </div>
  );
};

// 3. LOGIN
const LoginScreen = ({ onNav, offline }) => (
  <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
    <StatusBar offline={offline} />
    <div style={{ ...s.body, paddingTop: 20 }}>
      <BackButton onClick={() => onNav(SCREENS.SPLASH)} />
      <h2 style={{ ...s.headerTitle, marginBottom: 20 }}>Welcome Back</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <label style={{ fontSize: 11, fontFamily: font, color: colors.textMuted, display: "block", marginBottom: 4 }}>Email</label>
          <input style={s.input} placeholder="jane@example.com" />
        </div>
        <div>
          <label style={{ fontSize: 11, fontFamily: font, color: colors.textMuted, display: "block", marginBottom: 4 }}>Password</label>
          <input style={s.input} type="password" placeholder="Enter password" />
        </div>
        <button style={{ ...s.btn("primary"), marginTop: 8 }} onClick={() => onNav(SCREENS.DASHBOARD)}>Log In</button>
      </div>
    </div>
  </div>
);

// 4. ISSUE SELECT
const IssueSelectScreen = ({ onNav, offline }) => {
  const [selected, setSelected] = useState(["Healthcare", "Environment"]);
  const toggle = (issue) => {
    if (selected.includes(issue)) setSelected(selected.filter((i) => i !== issue));
    else if (selected.length < 5) setSelected([...selected, issue]);
  };
  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingTop: 12 }}>
        <h2 style={{ ...s.headerTitle, marginBottom: 4 }}>What Issues Matter Most?</h2>
        <p style={{ color: colors.textMuted, fontSize: 12, marginTop: 0, marginBottom: 16 }}>Select up to 5. This filters your alerts and feed.</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 24 }}>
          {ISSUES.map((issue) => (
            <button key={issue} style={s.chip(selected.includes(issue))} onClick={() => toggle(issue)}>
              {issue}
            </button>
          ))}
        </div>
        <div style={{ fontSize: 12, color: colors.textMuted, fontFamily: font, marginBottom: 12 }}>{selected.length}/5 selected</div>
        <button style={s.btn("primary")} onClick={() => onNav(SCREENS.DASHBOARD)}>
          Done - Show Me My Reps
        </button>
      </div>
    </div>
  );
};

// 5. DASHBOARD - WIRED TO BACKEND
// Subtle shimmer component for loading funding numbers
const Shimmer = ({ width = 40 }) => (
  <span
    style={{
      display: "inline-block",
      width,
      height: 16,
      borderRadius: 4,
      background: `linear-gradient(90deg, ${colors.border} 0%, ${colors.borderLight} 50%, ${colors.border} 100%)`,
      backgroundSize: "200% 100%",
      animation: "shimmer 1.3s ease-in-out infinite",
      verticalAlign: "middle",
    }}
  />
);

// Self-fetching rep card - loads its own funding on mount
const RepCard = ({ rep, onClick }) => {
  const [funding, setFunding] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let cancelled = false;
    api
      .getRepFundingLite(rep.bioguide_id)
      .then((data) => {
        if (cancelled) return;
        if (data?.has_data) {
          setFunding(data);
          setStatus("ready");
        } else {
          setStatus("none");
        }
      })
      .catch(() => {
        if (!cancelled) setStatus("none");
      });
    return () => {
      cancelled = true;
    };
  }, [rep.bioguide_id]);

  const renderValue = (value, color) => {
    if (status === "loading") return <Shimmer />;
    if (status === "none") return <span style={{ color: colors.textMuted, fontFamily: font, fontSize: 14 }}>—</span>;
    return (
      <span style={{ fontSize: 16, fontWeight: 700, fontFamily: font, color: color || colors.text }}>
        {fmt(value)}
      </span>
    );
  };

  return (
    <div style={{ ...s.card, cursor: "pointer" }} onClick={onClick}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Avatar name={rep.name} party={rep.party} />
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontWeight: 600, fontSize: 14 }}>{rep.name}</span>
            <PartyBadge party={rep.party} />
          </div>
          <div style={{ fontSize: 11, color: colors.textMuted }}>
            {rep.chamber} · {rep.district}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 16, marginTop: 10 }}>
        <div>
          <div style={{ fontSize: 10, color: colors.textMuted, fontFamily: font }}>Raised</div>
          {renderValue(funding?.total_raised, colors.accent)}
        </div>
        <div>
          <div style={{ fontSize: 10, color: colors.textMuted, fontFamily: font }}>PAC $</div>
          {renderValue(funding?.pac_total)}
        </div>
        <div>
          <div style={{ fontSize: 10, color: colors.textMuted, fontFamily: font }}>Small $</div>
          {renderValue(funding?.small_donor_total)}
        </div>
      </div>
    </div>
  );
};

// 5. DASHBOARD - WIRED TO BACKEND (streaming)
const DashboardScreen = ({ onNav, onSelectPolitician, userState }) => {
  const { data, loading, error, offline, reload } = useApi(
    () => api.getRepsByState(userState || "CT"),
    [userState],
    { representatives: [], state: userState || "CT", count: 0 }
  );

  const reps = data?.representatives || [];

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <style>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
      <div style={s.header}>
        <h1 style={{ ...s.headerTitle, fontSize: 18 }}>Your Representatives</h1>
        <p style={s.headerSub}>
          State: {userState || "CT"} {offline && "(backend offline)"}
        </p>
      </div>
      <div style={{ ...s.body, paddingBottom: 70 }}>
        {/* Urgent Alert Banner */}
        <div style={{ ...s.card, background: colors.redDim, borderColor: colors.red + "44", marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
            <Icon type="alert" size={16} color={colors.red} />
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: colors.red, marginBottom: 4 }}>URGENT</div>
              <div style={{ fontSize: 12, lineHeight: 1.4 }}>{SAMPLE.alerts[0].text}</div>
              <button style={{ ...s.btn("outline"), marginTop: 8, padding: "6px 12px", fontSize: 11, width: "auto", color: colors.red, borderColor: colors.red }} onClick={() => onNav(SCREENS.ALERTS)}>
                See All Alerts
              </button>
            </div>
          </div>
        </div>

        {loading && <Loading label="Fetching your representatives..." />}
        {error && <ErrorBanner error={error} onRetry={reload} />}

        {!loading && !error && reps.length === 0 && (
          <div style={{ ...s.card, textAlign: "center" }}>
            <div style={{ fontSize: 12, color: colors.textMuted }}>
              No representatives found for {userState}. Try another state in Settings.
            </div>
          </div>
        )}

        {!loading && !error && reps.length > 0 && (
          <div style={s.section}>
            <div style={s.sectionTitle}>Your Officials ({reps.length})</div>
            {reps.map((rep) => (
              <RepCard
                key={rep.bioguide_id}
                rep={rep}
                onClick={() => onSelectPolitician(rep.bioguide_id)}
              />
            ))}
          </div>
        )}

        <div style={s.section}>
          <div style={s.sectionTitle}>Quick Actions</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {[
              { icon: "phone", label: "Contact Rep", screen: SCREENS.CONTACT_REP },
              { icon: "vote", label: "Voting Guide", screen: SCREENS.LEARN_TO_VOTE },
              { icon: "calendar", label: "Local Events", screen: SCREENS.EVENTS },
              { icon: "dollar", label: "Follow Money", screen: SCREENS.SEARCH },
            ].map((a) => (
              <button key={a.label} style={{ ...s.card, cursor: "pointer", display: "flex", alignItems: "center", gap: 8, marginBottom: 0 }} onClick={() => onNav(a.screen)}>
                <Icon type={a.icon} size={16} color={colors.accent} />
                <span style={{ fontSize: 12, fontFamily: font }}>{a.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
      <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
    </div>
  );
};

// 6. SEARCH - WIRED TO BACKEND
const SearchScreen = ({ onNav, onSelectPolitician }) => {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  const { data, loading, offline } = useApi(
    async () => {
      if (!debounced || debounced.length < 2) return { results: [] };
      return await api.searchReps(debounced);
    },
    [debounced],
    { results: query.length >= 2 ? SAMPLE.reps.filter((r) => r.name.toLowerCase().includes(query.toLowerCase())) : [] }
  );

  const results = data?.results || [];

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={s.header}>
        <h1 style={{ ...s.headerTitle, fontSize: 18 }}>Search</h1>
      </div>
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <input style={{ ...s.input, marginBottom: 14 }} placeholder="Search by name..." value={query} onChange={(e) => setQuery(e.target.value)} />
        {query.length < 2 && (
          <p style={{ fontSize: 11, color: colors.textMuted, fontFamily: font }}>Type at least 2 characters to search.</p>
        )}
        {query.length >= 2 && loading && <Loading label="Searching..." />}
        {query.length >= 2 && !loading && results.length === 0 && (
          <p style={{ fontSize: 11, color: colors.textMuted, fontFamily: font }}>No results found.</p>
        )}
        {results.length > 0 && (
          <>
            <div style={s.sectionTitle}>Results ({results.length})</div>
            {results.map((p) => (
              <div key={p.bioguide_id} style={{ ...s.card, cursor: "pointer", display: "flex", alignItems: "center", gap: 12 }} onClick={() => onSelectPolitician(p.bioguide_id)}>
                <Avatar name={p.name} size={36} party={p.party} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{p.name} <PartyBadge party={p.party} /></div>
                  <div style={{ fontSize: 11, color: colors.textMuted }}>{p.chamber} · {p.district}</div>
                </div>
                <Icon type="back" size={14} color={colors.textMuted} />
              </div>
            ))}
          </>
        )}
      </div>
      <NavBar active={SCREENS.SEARCH} onNav={onNav} />
    </div>
  );
};

// 7. POLITICIAN PROFILE - WIRED TO BACKEND
const PoliticianProfileScreen = ({ onNav, bioguideId, onSetProfileData }) => {
  const { data, loading, error, offline, reload } = useApi(
    () => api.getProfile(bioguideId),
    [bioguideId],
    SAMPLE.profile
  );

  useEffect(() => {
    if (data) onSetProfileData(data);
  }, [data, onSetProfileData]);

  if (loading) {
    return (
      <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
        <StatusBar offline={offline} />
        <div style={{ ...s.body }}>
          <BackButton onClick={() => onNav(SCREENS.DASHBOARD)} label="Dashboard" />
          <Loading label="Loading profile..." />
        </div>
        <NavBar active={SCREENS.SEARCH} onNav={onNav} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
        <StatusBar offline={offline} />
        <div style={{ ...s.body }}>
          <BackButton onClick={() => onNav(SCREENS.DASHBOARD)} />
          <ErrorBanner error={error} onRetry={reload} />
        </div>
        <NavBar active={SCREENS.SEARCH} onNav={onNav} />
      </div>
    );
  }

  const p = data.profile;
  const f = data.funding;
  const v = data.votes;

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.DASHBOARD)} label="Dashboard" />
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 16 }}>
          <Avatar name={p.name} size={56} party={p.party} />
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>{p.name}</h2>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
              <PartyBadge party={p.party} />
              <span style={{ fontSize: 12, color: colors.textMuted }}>{p.chamber} · {p.district}</span>
            </div>
            {p.office && <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 2 }}>{p.office}</div>}
          </div>
        </div>

        {/* Score Cards */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 14 }}>
          <div style={{ ...s.card, textAlign: "center", marginBottom: 0 }}>
            <div style={{ fontSize: 22, fontWeight: 800, fontFamily: font, color: colors.textMuted }}>
              {data.promise_score ?? "—"}
            </div>
            <div style={{ fontSize: 9, color: colors.textMuted, fontFamily: font }}>PROMISE</div>
          </div>
          <div style={{ ...s.card, textAlign: "center", marginBottom: 0 }}>
            <div style={{ fontSize: 22, fontWeight: 800, fontFamily: font, color: colors.green }}>
              {v.yea_count}<span style={{ color: colors.textMuted, fontSize: 14 }}>/{v.total_tracked}</span>
            </div>
            <div style={{ fontSize: 9, color: colors.textMuted, fontFamily: font }}>YEA VOTES</div>
          </div>
          <div style={{ ...s.card, textAlign: "center", marginBottom: 0 }}>
            <div style={{ fontSize: 22, fontWeight: 800, fontFamily: font, color: colors.accent }}>
              {fmt(f.total_raised)}
            </div>
            <div style={{ fontSize: 9, color: colors.textMuted, fontFamily: font }}>RAISED</div>
          </div>
        </div>

        {/* Navigation Tiles */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {[
            { icon: "dollar", label: "Funding Breakdown", sub: f.top_industries?.length ? `Top: ${f.top_industries[0].industry}` : "View details", screen: SCREENS.FUNDING },
            { icon: "vote", label: "Voting Record", sub: `${v.total_tracked} recent votes`, screen: SCREENS.VOTING_HISTORY },
            { icon: "star", label: "Promise Scorecard", sub: "Coming soon", screen: SCREENS.PROMISE_SCORING },
            { icon: "clock", label: "Activity Timeline", sub: "Recent events", screen: SCREENS.TIMELINE },
            { icon: "phone", label: "Contact / Take Action", sub: p.phone || "Reach out", screen: SCREENS.TAKE_ACTION },
          ].map((item) => (
            <div key={item.label} style={{ ...s.card, cursor: "pointer", display: "flex", alignItems: "center", gap: 12, marginBottom: 0 }} onClick={() => onNav(item.screen)}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: colors.accentDim, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <Icon type={item.icon} size={16} color={colors.accent} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{item.label}</div>
                <div style={{ fontSize: 11, color: colors.textMuted }}>{item.sub}</div>
              </div>
              <span style={{ color: colors.textMuted, transform: "rotate(180deg)", display: "inline-block" }}>
                <Icon type="back" size={14} />
              </span>
            </div>
          ))}
        </div>
      </div>
      <NavBar active={SCREENS.SEARCH} onNav={onNav} />
    </div>
  );
};

// 8. FUNDING - USES PROFILE DATA
const FundingScreen = ({ onNav, profileData }) => {
  const p = profileData?.profile || SAMPLE.profile.profile;
  const f = profileData?.funding || SAMPLE.profile.funding;
  const industries = f.top_industries || [];
  const donors = f.top_donors || [];
  const maxInd = industries.length ? Math.max(...industries.map((i) => i.total_attributed)) : 1;

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.POLITICIAN_PROFILE)} label={p.name} />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 2 }}>Funding</h2>
        <p style={{ color: colors.textMuted, fontSize: 11, marginTop: 0, fontFamily: font }}>Campaign finance from FEC filings</p>

        <div style={{ ...s.card, textAlign: "center", marginBottom: 16 }}>
          <div style={{ fontSize: 10, color: colors.textMuted, fontFamily: font }}>TOTAL RAISED</div>
          <div style={{ fontSize: 28, fontWeight: 800, fontFamily: font, color: colors.accent }}>{fmt(f.total_raised)}</div>
          <div style={{ display: "flex", justifyContent: "center", gap: 20, marginTop: 8 }}>
            <div>
              <span style={{ fontSize: 14, fontWeight: 700, fontFamily: font }}>{fmt(f.pac_total)}</span>
              <div style={{ fontSize: 9, color: colors.textMuted }}>PAC</div>
            </div>
            <div>
              <span style={{ fontSize: 14, fontWeight: 700, fontFamily: font }}>{fmt(f.individual_total)}</span>
              <div style={{ fontSize: 9, color: colors.textMuted }}>Individual</div>
            </div>
            <div>
              <span style={{ fontSize: 14, fontWeight: 700, fontFamily: font }}>{fmt(f.small_donor_total)}</span>
              <div style={{ fontSize: 9, color: colors.textMuted }}>Small $</div>
            </div>
          </div>
        </div>

        {industries.length > 0 && (
          <div style={s.section}>
            <div style={s.sectionTitle}>Top Industries</div>
            {industries.map((ind, i) => (
              <div key={i} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 3 }}>
                  <span>{ind.industry}</span>
                  <span style={{ fontFamily: font, color: colors.accent }}>{fmt(ind.total_attributed)}</span>
                </div>
                <ProgressBar value={ind.total_attributed} max={maxInd} color={colors.accent} />
              </div>
            ))}
          </div>
        )}

        {donors.length > 0 && (
          <div style={s.section}>
            <div style={s.sectionTitle}>Top Donors</div>
            {donors.map((d, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: i < donors.length - 1 ? `1px solid ${colors.border}` : "none" }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 500 }}>{d.name}</div>
                  <span style={s.badge(d.type === "pac" ? "yellow" : "blue")}>{d.type}</span>
                </div>
                <span style={{ fontFamily: font, fontWeight: 600, fontSize: 13 }}>{fmt(d.total)}</span>
              </div>
            ))}
          </div>
        )}

        <p style={{ fontSize: 10, color: colors.textMuted, fontFamily: font }}>Source: OpenFEC & WhoBoughtMyRep. Updated regularly.</p>
      </div>
      <NavBar active={SCREENS.SEARCH} onNav={onNav} />
    </div>
  );
};

// 9. VOTING HISTORY - USES PROFILE DATA
const VotingHistoryScreen = ({ onNav, profileData }) => {
  const p = profileData?.profile || SAMPLE.profile.profile;
  const votes = profileData?.votes?.recent || [];
  const [filter, setFilter] = useState("all");
  const cats = ["all", ...new Set(votes.map((v) => v.category).filter(Boolean))];
  const filtered = filter === "all" ? votes : votes.filter((v) => v.category === filter);

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.POLITICIAN_PROFILE)} label={p.name} />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 12 }}>Voting Record</h2>
        {cats.length > 1 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            {cats.map((c) => (
              <button key={c} style={s.chip(filter === c)} onClick={() => setFilter(c)}>
                {c === "all" ? "All" : c.charAt(0).toUpperCase() + c.slice(1)}
              </button>
            ))}
          </div>
        )}
        {filtered.length === 0 && (
          <p style={{ fontSize: 11, color: colors.textMuted, fontFamily: font }}>No votes match this filter.</p>
        )}
        {filtered.map((v, i) => (
          <div key={i} style={{ display: "flex", gap: 12, marginBottom: 12, position: "relative", paddingLeft: 16 }}>
            <div style={{ position: "absolute", left: 0, top: 6, width: 8, height: 8, borderRadius: "50%", background: v.member_vote === "Yea" ? colors.green : colors.red }} />
            {i < filtered.length - 1 && <div style={{ position: "absolute", left: 3.5, top: 16, width: 1, height: "calc(100% + 4px)", background: colors.border }} />}
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={s.badge(v.member_vote === "Yea" ? "green" : "red")}>{(v.member_vote || "?").toUpperCase()}</span>
                <span style={{ fontSize: 10, color: colors.textMuted, fontFamily: font }}>{v.date}</span>
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>{v.title}</div>
              <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: font }}>{v.bill} · {v.category || "general"}</div>
            </div>
          </div>
        ))}
      </div>
      <NavBar active={SCREENS.SEARCH} onNav={onNav} />
    </div>
  );
};

// 10. PROMISE SCORING - Placeholder (backend feature)
const PromiseScoringScreen = ({ onNav, profileData }) => {
  const p = profileData?.profile || SAMPLE.profile.profile;
  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.POLITICIAN_PROFILE)} label={p.name} />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 12 }}>Promise Scorecard</h2>
        <div style={{ ...s.card, background: colors.yellowDim, borderColor: colors.yellow + "44" }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: colors.yellow, marginBottom: 6 }}>Coming Soon</div>
          <div style={{ fontSize: 12, lineHeight: 1.5 }}>
            Promise tracking requires curating campaign statements and cross-referencing them with votes. We're building this database now.
          </div>
        </div>
        <div style={{ ...s.card, marginTop: 12 }}>
          <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: font, marginBottom: 6 }}>METHODOLOGY</div>
          <div style={{ fontSize: 12, lineHeight: 1.5 }}>
            Promises will be sourced from campaign speeches, websites, and ads, then cross-referenced against actual votes from Congress.gov. Each promise gets scored as KEPT, BROKEN, PARTIAL, or PENDING.
          </div>
        </div>
      </div>
      <NavBar active={SCREENS.SEARCH} onNav={onNav} />
    </div>
  );
};

// 11. TIMELINE - Uses sponsored bills + votes from backend
const TimelineScreen = ({ onNav, profileData }) => {
  const p = profileData?.profile || SAMPLE.profile.profile;
  const votes = profileData?.votes?.recent || [];
  const sponsored = profileData?.sponsored_bills || [];

  // Build a combined timeline
  const events = [
    ...votes.map((v) => ({ date: v.date, type: "voting", text: `Voted ${v.member_vote?.toUpperCase()} on ${v.title}` })),
    ...sponsored.map((b) => ({ date: b.introduced_date, type: "sponsored", text: `Sponsored ${b.number}: ${b.title}` })),
  ].filter((e) => e.date).sort((a, b) => b.date.localeCompare(a.date));

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.POLITICIAN_PROFILE)} label={p.name} />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 12 }}>Activity Timeline</h2>
        {events.length === 0 && <p style={{ fontSize: 11, color: colors.textMuted }}>No recent activity tracked.</p>}
        {events.map((ev, i) => (
          <div key={i} style={{ display: "flex", gap: 12, marginBottom: 14, paddingLeft: 16, position: "relative" }}>
            <div style={{ position: "absolute", left: 0, top: 4, width: 10, height: 10, borderRadius: "50%", background: colors.surfaceLight, border: `2px solid ${ev.type === "voting" ? colors.blue : colors.green}` }} />
            {i < events.length - 1 && <div style={{ position: "absolute", left: 4.5, top: 16, width: 1, height: "calc(100% + 2px)", background: colors.border }} />}
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={s.badge(ev.type === "voting" ? "blue" : "green")}>{ev.type}</span>
                <span style={{ fontSize: 10, color: colors.textMuted, fontFamily: font }}>{ev.date}</span>
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.4 }}>{ev.text}</div>
            </div>
          </div>
        ))}
      </div>
      <NavBar active={SCREENS.SEARCH} onNav={onNav} />
    </div>
  );
};

// 12. TAKE ACTION - Uses real contact info from backend
const TakeActionScreen = ({ onNav, profileData }) => {
  const p = profileData?.profile || SAMPLE.profile.profile;
  const contact = profileData?.contact || {};

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.POLITICIAN_PROFILE)} label={p.name} />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 4 }}>Take Action</h2>
        <p style={{ color: colors.textMuted, fontSize: 11, marginTop: 0, marginBottom: 14, fontFamily: font }}>Every contact is logged by their office.</p>

        {[
          { icon: "phone", label: "Call Their Office", sub: contact.phone || "No phone available", color: colors.green, action: contact.phone ? `tel:${contact.phone}` : null },
          { icon: "mail", label: "Contact Form", sub: "Official contact page", color: colors.blue, action: contact.contact_form || contact.website },
          { icon: "megaphone", label: "Visit Their Website", sub: contact.website || "No website available", color: colors.purple, action: contact.website },
        ].map((m, i) => (
          <a key={i} href={m.action || "#"} target="_blank" rel="noreferrer" style={{ textDecoration: "none", color: "inherit", display: "block" }}>
            <div style={{ ...s.card, cursor: m.action ? "pointer" : "not-allowed", display: "flex", alignItems: "center", gap: 12, opacity: m.action ? 1 : 0.5 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: m.color + "22", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <Icon type={m.icon} size={18} color={m.color} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{m.label}</div>
                <div style={{ fontSize: 11, color: colors.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.sub}</div>
              </div>
            </div>
          </a>
        ))}

        <div style={s.divider} />

        <div style={s.section}>
          <div style={s.sectionTitle}>Call Script Template</div>
          <div style={{ ...s.card, background: colors.accentDim, borderColor: colors.accent + "33" }}>
            <div style={{ fontSize: 12, lineHeight: 1.6, fontFamily: font }}>
              "Hi, I'm a constituent from [zip]. I'm calling about [bill]. I urge {p.name} to vote [YES/NO] because [reason]. Thank you."
            </div>
          </div>
        </div>
      </div>
      <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
    </div>
  );
};

// 13. CONTACT ALL REPS
const ContactRepScreen = ({ onNav, userState }) => {
  const { data, loading, offline } = useApi(
    () => api.getRepsByState(userState || "CT"),
    [userState],
    { representatives: SAMPLE.reps }
  );
  const reps = data?.representatives || [];

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.DASHBOARD)} label="Dashboard" />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 12 }}>Contact Your Reps</h2>
        {loading && <Loading />}
        {reps.map((p) => (
          <div key={p.bioguide_id} style={{ ...s.card }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <Avatar name={p.name} size={32} party={p.party} />
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{p.name} <PartyBadge party={p.party} /></div>
                <div style={{ fontSize: 11, color: colors.textMuted }}>{p.chamber} · {p.district}</div>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {p.phone && (
                <a href={`tel:${p.phone}`} style={{ textDecoration: "none" }}>
                  <button style={{ ...s.btn("outline"), padding: "6px", fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center", gap: 4, width: "100%" }}>
                    <Icon type="phone" size={12} /> Call
                  </button>
                </a>
              )}
              {p.website && (
                <a href={p.website} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>
                  <button style={{ ...s.btn("outline"), padding: "6px", fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center", gap: 4, width: "100%" }}>
                    <Icon type="mail" size={12} /> Website
                  </button>
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
      <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
    </div>
  );
};

// 14. EVENTS
const EventsScreen = ({ onNav, userState }) => {
  const events = SAMPLE.events;
  const typeColors = { town_hall: colors.purple, council: colors.blue, registration: colors.green, hearing: colors.yellow };

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={s.header}>
        <h1 style={{ ...s.headerTitle, fontSize: 18 }}>Events Near You</h1>
        <p style={s.headerSub}>{userState || "CT"} · Within 25 miles</p>
      </div>
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <div style={{ ...s.card, background: colors.yellowDim, borderColor: colors.yellow + "44", marginBottom: 14 }}>
          <div style={{ fontSize: 11, color: colors.yellow, fontWeight: 600, marginBottom: 4 }}>SAMPLE DATA</div>
          <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.4 }}>
            Events integration pending - will connect to Democracy Works API or similar.
          </div>
        </div>
        {events.map((ev) => (
          <div key={ev.id} style={{ ...s.card, cursor: "pointer" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
              <div style={{ width: 44, minHeight: 44, borderRadius: 8, background: (typeColors[ev.type] || colors.accent) + "22", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flexShrink: 0, padding: "4px 0" }}>
                <div style={{ fontSize: 14, fontWeight: 800, fontFamily: font, color: typeColors[ev.type] }}>{ev.date.split(" ")[1].replace(",", "")}</div>
                <div style={{ fontSize: 9, fontFamily: font, color: typeColors[ev.type] }}>{ev.date.split(" ")[0]}</div>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>{ev.title}</div>
                <div style={{ fontSize: 11, color: colors.textMuted }}>{ev.time} · {ev.location}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
      <NavBar active={SCREENS.EVENTS} onNav={onNav} />
    </div>
  );
};

// 15. LEARN TO VOTE
const LearnToVoteScreen = ({ onNav, userState }) => (
  <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
    <StatusBar />
    <div style={{ ...s.body, paddingBottom: 70 }}>
      <BackButton onClick={() => onNav(SCREENS.DASHBOARD)} label="Dashboard" />
      <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 12 }}>Voting Guide</h2>

      <div style={s.section}>
        <div style={s.sectionTitle}>Resources</div>
        {[
          { label: "Register to vote", url: "https://vote.gov" },
          { label: "Find your polling place", url: "https://www.vote.org/polling-place-locator/" },
          { label: "Absentee / mail-in ballot", url: "https://www.vote.org/absentee-ballot/" },
          { label: "Check voter registration", url: "https://www.vote.org/am-i-registered-to-vote/" },
        ].map((r, i) => (
          <a key={i} href={r.url} target="_blank" rel="noreferrer" style={{ textDecoration: "none", color: "inherit" }}>
            <div style={{ ...s.card, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontSize: 13 }}>{r.label}</span>
              <span style={{ color: colors.textMuted, transform: "rotate(180deg)", display: "inline-block" }}>
                <Icon type="back" size={14} />
              </span>
            </div>
          </a>
        ))}
      </div>

      <div style={s.section}>
        <div style={s.sectionTitle}>Your State: {userState || "CT"}</div>
        <div style={s.card}>
          <div style={{ fontSize: 12, lineHeight: 1.5 }}>
            Detailed state-specific voting info (deadlines, ID requirements, polling hours) coming soon. For now, use the resources above.
          </div>
        </div>
      </div>
    </div>
    <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
  </div>
);

// 16. ALERTS
const AlertsScreen = ({ onNav }) => (
  <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
    <StatusBar />
    <div style={s.header}>
      <h1 style={{ ...s.headerTitle, fontSize: 18 }}>Alerts</h1>
      <p style={s.headerSub}>Based on your issues & representatives</p>
    </div>
    <div style={{ ...s.body, paddingBottom: 70 }}>
      <div style={{ ...s.card, background: colors.yellowDim, borderColor: colors.yellow + "44", marginBottom: 14 }}>
        <div style={{ fontSize: 11, color: colors.yellow, fontWeight: 600, marginBottom: 4 }}>SAMPLE ALERTS</div>
        <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.4 }}>
          Real alerts will fire when new FEC filings land before scheduled votes, detected by the backend.
        </div>
      </div>
      {SAMPLE.alerts.map((a) => (
        <div key={a.id} style={{ ...s.card, borderColor: a.urgent ? colors.red + "44" : colors.border, background: a.urgent ? colors.redDim : colors.surfaceLight }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
            {a.urgent && <span style={s.badge("red")}>URGENT</span>}
            <span style={{ fontSize: 10, color: colors.textMuted, fontFamily: font, marginLeft: "auto" }}>{a.time}</span>
          </div>
          <div style={{ fontSize: 12, lineHeight: 1.5, marginBottom: 8 }}>{a.text}</div>
          <button style={{ ...s.btn("outline"), padding: "6px 12px", fontSize: 11, width: "auto", ...(a.urgent ? { color: colors.red, borderColor: colors.red } : {}) }}>
            {a.action}
          </button>
        </div>
      ))}
    </div>
    <NavBar active={SCREENS.ALERTS} onNav={onNav} />
  </div>
);

// 17. SETTINGS
const SettingsScreen = ({ onNav, userState, onSetState }) => {
  const [editState, setEditState] = useState(userState || "CT");
  const [backendStatus, setBackendStatus] = useState(null);

  useEffect(() => {
    api.health()
      .then((d) => setBackendStatus({ ok: true, data: d }))
      .catch((e) => setBackendStatus({ ok: false, error: e.message }));
  }, []);

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={s.header}>
        <h1 style={{ ...s.headerTitle, fontSize: 18 }}>Settings</h1>
      </div>
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <div style={s.section}>
          <div style={s.sectionTitle}>Location</div>
          <div style={s.card}>
            <label style={{ fontSize: 11, fontFamily: font, color: colors.textMuted, display: "block", marginBottom: 4 }}>Your State (2-letter)</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input style={{ ...s.input, flex: 1 }} value={editState} onChange={(e) => setEditState(e.target.value.toUpperCase().slice(0, 2))} maxLength={2} />
              <button style={{ ...s.btn("primary"), width: "auto", padding: "10px 16px" }} onClick={() => onSetState(editState)}>Save</button>
            </div>
          </div>
        </div>

        <div style={s.section}>
          <div style={s.sectionTitle}>Backend Status</div>
          <div style={s.card}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Icon type="wifi" size={14} color={backendStatus?.ok ? colors.green : colors.red} />
              <span style={{ fontSize: 13, fontWeight: 600 }}>
                {backendStatus === null ? "Checking..." : backendStatus.ok ? "Connected" : "Offline"}
              </span>
            </div>
            {backendStatus?.ok && (
              <div style={{ fontSize: 10, fontFamily: font, color: colors.textMuted }}>
                <div>API v{backendStatus.data.version}</div>
                <div style={{ marginTop: 4 }}>Keys configured:</div>
                {Object.entries(backendStatus.data.api_keys_configured || {}).map(([k, v]) => (
                  <div key={k} style={{ marginLeft: 8 }}>
                    {v ? "[x]" : "[ ]"} {k}
                  </div>
                ))}
              </div>
            )}
            {!backendStatus?.ok && backendStatus && (
              <div style={{ fontSize: 10, color: colors.textMuted }}>
                Run the backend: <code style={{ fontFamily: font, color: colors.accent }}>python server.py</code>
              </div>
            )}
          </div>
        </div>

        <div style={s.section}>
          <div style={s.sectionTitle}>About</div>
          {["Data Sources", "Privacy Policy", "Open Source"].map((item, i) => (
            <div key={i} style={{ ...s.card, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontSize: 13 }}>{item}</span>
              <span style={{ color: colors.textMuted, transform: "rotate(180deg)", display: "inline-block" }}>
                <Icon type="back" size={14} />
              </span>
            </div>
          ))}
        </div>
      </div>
      <NavBar active={SCREENS.SETTINGS} onNav={onNav} />
    </div>
  );
};

// ============================================================
// MAIN APP
// ============================================================

export default function App() {
  const [currentScreen, setCurrentScreen] = useState(SCREENS.SPLASH);
  const [selectedBioguideId, setSelectedBioguideId] = useState("M001169");
  const [userState, setUserState] = useState("CT");
  const [profileData, setProfileData] = useState(null);
  const [globalOffline, setGlobalOffline] = useState(false);

  // Check backend health on load
  useEffect(() => {
    api.health().catch(() => setGlobalOffline(true));
  }, []);

  const navigate = (screen) => setCurrentScreen(screen);

  const selectPolitician = (bioguideId) => {
    setSelectedBioguideId(bioguideId);
    setProfileData(null); // clear old data so it refetches
    setCurrentScreen(SCREENS.POLITICIAN_PROFILE);
  };

  const renderScreen = () => {
    const common = { onNav: navigate, offline: globalOffline };
    switch (currentScreen) {
      case SCREENS.SPLASH: return <SplashScreen {...common} />;
      case SCREENS.CREATE_ACCOUNT: return <CreateAccountScreen {...common} onSetState={setUserState} />;
      case SCREENS.LOGIN: return <LoginScreen {...common} />;
      case SCREENS.ISSUE_SELECT: return <IssueSelectScreen {...common} />;
      case SCREENS.DASHBOARD: return <DashboardScreen {...common} onSelectPolitician={selectPolitician} userState={userState} />;
      case SCREENS.SEARCH: return <SearchScreen {...common} onSelectPolitician={selectPolitician} />;
      case SCREENS.POLITICIAN_PROFILE: return <PoliticianProfileScreen {...common} bioguideId={selectedBioguideId} onSetProfileData={setProfileData} />;
      case SCREENS.FUNDING: return <FundingScreen {...common} profileData={profileData} />;
      case SCREENS.VOTING_HISTORY: return <VotingHistoryScreen {...common} profileData={profileData} />;
      case SCREENS.PROMISE_SCORING: return <PromiseScoringScreen {...common} profileData={profileData} />;
      case SCREENS.TIMELINE: return <TimelineScreen {...common} profileData={profileData} />;
      case SCREENS.TAKE_ACTION: return <TakeActionScreen {...common} profileData={profileData} />;
      case SCREENS.CONTACT_REP: return <ContactRepScreen {...common} userState={userState} />;
      case SCREENS.EVENTS: return <EventsScreen {...common} userState={userState} />;
      case SCREENS.LEARN_TO_VOTE: return <LearnToVoteScreen {...common} userState={userState} />;
      case SCREENS.ALERTS: return <AlertsScreen {...common} />;
      case SCREENS.SETTINGS: return <SettingsScreen {...common} userState={userState} onSetState={setUserState} />;
      default: return <SplashScreen {...common} />;
    }
  };

  // Screen nav pills for dev
  const allScreens = [
    [SCREENS.SPLASH, "Splash"],
    [SCREENS.CREATE_ACCOUNT, "Create Account"],
    [SCREENS.LOGIN, "Log In"],
    [SCREENS.ISSUE_SELECT, "Issue Select"],
    [SCREENS.DASHBOARD, "Dashboard"],
    [SCREENS.SEARCH, "Search"],
    [SCREENS.POLITICIAN_PROFILE, "Profile"],
    [SCREENS.FUNDING, "Funding"],
    [SCREENS.VOTING_HISTORY, "Voting"],
    [SCREENS.PROMISE_SCORING, "Promises"],
    [SCREENS.TIMELINE, "Timeline"],
    [SCREENS.TAKE_ACTION, "Take Action"],
    [SCREENS.CONTACT_REP, "Contact Reps"],
    [SCREENS.EVENTS, "Events"],
    [SCREENS.LEARN_TO_VOTE, "Learn to Vote"],
    [SCREENS.ALERTS, "Alerts"],
    [SCREENS.SETTINGS, "Settings"],
  ];

  return (
    <div style={{ minHeight: "100vh", background: "#060810", fontFamily: fontSans, color: colors.text }}>
      {/* Top bar */}
      <div style={{ padding: "20px 24px 12px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 20, fontFamily: font, fontWeight: 800 }}>
            <span style={{ color: colors.accent }}>FUDGE UR UNCLE</span>
            <span style={{ color: colors.textMuted, fontWeight: 400, fontSize: 14 }}> — Live Prototype</span>
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: colors.textMuted, fontFamily: font }}>
            Connected to backend at {import.meta.env.VITE_API_BASE || "/api (via Vite proxy)"}
            {globalOffline && <span style={{ color: colors.yellow, marginLeft: 8 }}>• OFFLINE (using sample data)</span>}
          </p>
        </div>
      </div>

      {/* Screen selector pills */}
      <div style={{ padding: "0 24px 16px", overflowX: "auto" }}>
        <div style={{ display: "flex", gap: 6, minWidth: "max-content" }}>
          {allScreens.map(([scr, name], i) => (
            <button
              key={scr}
              onClick={() => setCurrentScreen(scr)}
              style={{
                padding: "6px 12px", borderRadius: 6, border: "none",
                fontSize: 11, fontFamily: font, cursor: "pointer",
                whiteSpace: "nowrap", transition: "all 0.15s",
                background: currentScreen === scr ? colors.accent : colors.surfaceLight,
                color: currentScreen === scr ? "#fff" : colors.textMuted,
                fontWeight: currentScreen === scr ? 700 : 400,
              }}
            >
              {i + 1}. {name}
            </button>
          ))}
        </div>
      </div>

      {/* Phone frame */}
      <div style={{ display: "flex", justifyContent: "center", padding: "10px 20px 40px" }}>
        {renderScreen()}
      </div>
    </div>
  );
}
