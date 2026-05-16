import { useState, useEffect } from "react";
import { api, auth, SAMPLE } from "./api.js";
import { groupAlerts } from "./groupAlerts.js";
import { COPY, friendlyCategory, friendlyCategoryInline, STATE_VOTING_GUIDE } from "./copy.js";

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
  EVENT_DETAIL: "event_detail",
  LEARN_TO_VOTE: "learn_to_vote",
  SETTINGS: "settings",
  ALERTS: "alerts",
  STATE_REPS: "state_reps",
  STATE_REP_PROFILE: "state_rep_profile",
  STATE_REP_VOTING: "state_rep_voting",
  STATE_REP_STANCES: "state_rep_stances",
  STATE_REP_PROMISES: "state_rep_promises",
  STATE_REP_ALERTS: "state_rep_alerts",
  ASSISTANT: "assistant",
};

const font = "'IBM Plex Mono', 'Courier New', monospace";
const fontSans = "'IBM Plex Sans', 'Helvetica Neue', sans-serif";

// True when the page is launched as an installed PWA (Add to Home Screen on
// iOS, "Install app" on Android). The host OS already provides a status bar
// and chrome in that mode, so the simulated "9:41 / FUDGE UR UNCLE / 100%"
// bar plus the dev-only Backend Status panel become noise. We hide them.
const isPWA = () =>
  typeof window !== "undefined" &&
  ((window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
    window.navigator.standalone === true);
const _IS_PWA_AT_BOOT = isPWA();

// Module-level CSS injection for keyframes used by motion-light surfaces
// (Coming-up skeleton shimmer, row entry fade, soonest-vote dot pulse).
// Idempotent — guarded against HMR / repeated imports.
if (typeof document !== "undefined" && !document.getElementById("fuu-anim-styles")) {
  const _animEl = document.createElement("style");
  _animEl.id = "fuu-anim-styles";
  _animEl.textContent = `
    @keyframes fuu-shimmer {
      0%   { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }
    @keyframes fuu-fade-up {
      from { opacity: 0; transform: translateY(8px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
      }
    }
    @keyframes fuu-soft-pulse {
      0%, 100% { opacity: 0.5; transform: scale(1); }
      50%      { opacity: 1;   transform: scale(1.4); }
    }
    @keyframes fuu-slide-up {
      from { transform: translateY(100%); }
      to   { transform: translateY(0); }
    }
    @keyframes fuu-fade-in {
      from { opacity: 0; }
      to   { opacity: 1; }
    }
    /* Global press feedback — fires on :active for any native button or
       role=button element that doesn't already drive its own JS-tracked
       transform. Elements that DO (ComingUpCard, RepCardShell,
       QuickActionButton) set transform inline, which wins over this rule. */
    button:active, [role="button"]:active {
      transform: translateY(1px);
    }
    button, [role="button"] {
      transition: transform 0.14s cubic-bezier(0.16, 1, 0.3, 1);
    }
  `;
  document.head.appendChild(_animEl);
}

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
  accent: "rgb(231 122 27)",    // orange main color
  accentDim: "rgba(231,122,27,0.1)",

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
  // Phone-shaped container. In a browser we draw the iPhone-16-ish frame
  // (393×852, rounded, bordered) for the prototype look; when the app is
  // launched as an installed PWA we drop the chrome and fill the viewport.
  phone: _IS_PWA_AT_BOOT
    ? {
        // 100% (not 100vw/vh) so we size to #root, which body has already
        // shrunk to the safe area via env(safe-area-inset-*) padding.
        // Using vw/vh here would overflow back into the dynamic-island and
        // home-indicator zones and squish the content's proportions.
        width: "100%", height: "100%",
        background: colors.bg, position: "relative",
        overflow: "hidden", fontFamily: fontSans,
        color: colors.text, fontSize: 13,
      }
    : {
        width: 393, height: 852, borderRadius: 40,
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
    fontSize: 20, fontWeight: 700, fontFamily: fontSans,
    color: colors.text, margin: 0, letterSpacing: -0.2,
  },
  headerSub: {
    fontSize: 12, color: colors.textMuted, marginTop: 3,
    fontFamily: fontSans,
  },
  body: {
    padding: "12px 20px", overflowY: "auto", flex: 1,
    // Flow-in on every screen mount — fades + 8px settle so navigating
    // between screens feels physical instead of a hard cut.
    animation: "fuu-fade-up 0.32s cubic-bezier(0.16, 1, 0.3, 1) both",
  },
  navBar: {
    height: 56, display: "flex", borderTop: `1px solid ${colors.border}`,
    background: colors.surface, position: "absolute", bottom: 0,
    left: 0, right: 0,
  },
  // Floating civics-helper pill. position: fixed (not absolute) because each
  // screen owns its own `s.phone` wrapper — anchoring to one specific phone
  // frame would mean injecting into every screen. Fixed pins to the viewport,
  // which in PWA mode IS the phone screen, and in browser dev mode lives at
  // the window corner (dev-only — real users only see PWA). The safe-area
  // env() picks up iOS home-indicator height when installed.
  assistantPill: {
    position: "fixed",
    right: 16,
    bottom: "calc(72px + env(safe-area-inset-bottom, 0px))",
    height: 44,
    padding: "0 18px",
    borderRadius: 22,
    background: colors.accent,
    color: "#fff",
    fontFamily: fontSans,
    fontSize: 14,
    fontWeight: 600,
    border: "none",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    gap: 6,
    boxShadow: "0 6px 18px -10px rgba(231, 122, 27, 0.55), 0 1px 3px rgba(0, 0, 0, 0.08)",
    zIndex: 50,
  },
  navItem: (active) => ({
    flex: 1, display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center", gap: 3,
    fontSize: 10, fontFamily: fontSans, fontWeight: 500, cursor: "pointer",
    color: active ? colors.accent : colors.textMuted,
    background: "none", border: "none", padding: 0,
    transition: "color 0.15s",
  }),
  btn: (variant = "primary") => ({
    width: "100%", padding: "12px 16px", border: "none",
    borderRadius: 10, fontFamily: fontSans, fontSize: 13,
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
    border: `1px solid ${colors.border}`, borderRadius: 10,
    color: colors.text, fontFamily: fontSans, fontSize: 13,
    outline: "none", boxSizing: "border-box",
  },
  chip: (selected) => ({
    padding: "8px 14px", borderRadius: 20, fontSize: 12,
    fontFamily: fontSans, cursor: "pointer",
    transition: "all 0.15s", fontWeight: selected ? 600 : 500,
    background: selected ? colors.accentDim : colors.surfaceLight,
    color: selected ? colors.accent : colors.textMuted,
    border: `1px solid ${selected ? colors.accent : colors.border}`,
  }),
  card: {
    background: colors.surfaceLight, borderRadius: 14,
    border: `1px solid ${colors.border}`, padding: "14px",
    marginBottom: 10,
  },
  badge: (color) => ({
    display: "inline-block", padding: "2px 8px", borderRadius: 6,
    fontSize: 11, fontFamily: fontSans, fontWeight: 600,
    background: color === "green" ? colors.greenDim : color === "red" ? colors.redDim : color === "yellow" ? colors.yellowDim : colors.blueDim,
    color: color === "green" ? colors.green : color === "red" ? colors.red : color === "yellow" ? colors.yellow : colors.blue,
  }),
  backBtn: {
    background: "none", border: "none", color: colors.accent,
    fontFamily: fontSans, fontSize: 13, fontWeight: 500, cursor: "pointer",
    padding: "4px 0", marginBottom: 8, display: "flex",
    alignItems: "center", gap: 4,
  },
  section: { marginBottom: 16 },
  // Friendlier section heading — used on screens aimed at new voters (the
  // dashboard, mostly). Sentence-case sans, no terminal-style uppercase.
  sectionTitleFriendly: {
    fontSize: 14, fontWeight: 600, fontFamily: fontSans,
    color: colors.text, marginBottom: 10,
  },
  // App-wide section title — was mono uppercase letter-spaced ("terminal"
  // look) but the whole-app warm pass dropped that for sentence-case sans.
  // copy.js labels were sentence-cased in the same pass so existing
  // ALL-CAPS strings now render as natural-case headings.
  sectionTitle: {
    fontSize: 13, fontWeight: 600, fontFamily: fontSans,
    color: colors.text, marginBottom: 10,
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
    sparkle: <svg {...p}><path d="M12 3l1.9 5.1 5.1 1.9-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 14l.7 1.9 1.9.7-1.9.7-.7 1.9-.7-1.9-1.9-.7 1.9-.7z"/></svg>,
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

const StatusBar = ({ offline }) => {
  if (isPWA()) return null;
  return (
    <div style={s.statusBar}>
      <span>9:41</span>
      <span style={{ fontSize: 9, letterSpacing: 0.5, display: "flex", alignItems: "center", gap: 4 }}>
        {offline && <span style={{ color: colors.yellow }}>OFFLINE</span>}
        FUDGE UR UNCLE
      </span>
      <span>100%</span>
    </div>
  );
};

const BackButton = ({ onClick, label = "Back" }) => (
  <button style={s.backBtn} onClick={onClick}>
    <Icon type="back" size={14} /> {label}
  </button>
);

const NavBar = ({ active, onNav }) => {
  const items = [
    { id: SCREENS.DASHBOARD, icon: "home", label: "Home" },
    { id: SCREENS.ALERTS, icon: "bell", label: "Alerts" },
    { id: SCREENS.EVENTS, icon: "calendar", label: "Events" },
    { id: SCREENS.ASSISTANT, icon: "sparkle", label: "Mamu" },
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
    <div style={{ fontSize: 11, color: colors.textMuted }}>{label}</div>
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
  </div>
);

// Flow-in wrapper. Fires the `fuu-fade-up` animation on mount — drop into
// any branch that renders only after async data arrives so the content
// settles in instead of popping. For lists, pass `delay = i * 60` to
// stagger. `style` is merged onto the wrapper so callers can preserve
// surrounding layout (gridColumn, marginBottom, etc.).
const FadeIn = ({ children, delay = 0, duration = 300, style }) => (
  <div style={{
    animation: `fuu-fade-up ${duration}ms cubic-bezier(0.16, 1, 0.3, 1) both`,
    animationDelay: `${delay}ms`,
    ...style,
  }}>
    {children}
  </div>
);

// Civics-helper chat. Now a full-screen tab (not a modal sheet) so the
// conversation is a first-class destination instead of a transient overlay.
// Chat state is lifted to App so navigating away and back doesn't wipe the
// thread; `context` is whatever the user was looking at right before they
// entered the tab (set via the pill or the lastNonAssistantScreen tracker).
const AssistantScreen = ({
  onNav, offline,
  context,
  messages, setMessages,
  input, setInput,
  sending, setSending,
  errorMsg, setErrorMsg,
  onClearChat,
  isGuest,
}) => {
  const submit = async (overrideText) => {
    const text = (overrideText ?? input).trim();
    if (!text || sending) return;
    setErrorMsg("");
    const userMsg = { role: "user", content: text };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput("");
    setSending(true);
    try {
      const res = await api.chatSend({ messages: nextMessages, context });
      if (!res?.reply) throw new Error("empty reply");
      setMessages([...nextMessages, { role: "assistant", content: res.reply }]);
    } catch {
      setErrorMsg(COPY.assistant.error);
    } finally {
      setSending(false);
    }
  };

  const chipText = (() => {
    if (!context) return null;
    const cc = COPY.assistant.contextChip;
    const screen = context.screen;
    if (screen === "profile" || screen === "state_profile") {
      const t = cc[screen];
      return typeof t === "function" ? t(context.rep_name) : t;
    }
    if (screen === "event" || context.event_id) return cc.event;
    if (context.bill_number) return cc.bill;
    if (screen === "learn_to_vote") {
      return typeof cc.learn_to_vote === "function" ? cc.learn_to_vote(context.learn_to_vote_state) : cc.learn_to_vote;
    }
    if (screen === "dashboard") return cc.dashboard;
    return null;
  })();

  // Guest gate — chat hits an auth-required endpoint, so render a sign-up
  // CTA instead of the input. Keeps header + NavBar so the user can
  // navigate away. Temp guest-mode footprint; remove this branch when the
  // feature is pulled.
  if (isGuest) {
    return (
      <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
        <StatusBar offline={offline} />
        <div style={{ ...s.header, paddingTop: 12 }}>
          <h1 style={{ ...s.headerTitle, fontSize: 18 }}>{COPY.assistant.title}</h1>
          <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>{COPY.assistant.subtitle}</div>
        </div>
        <div style={{ ...s.body, paddingBottom: 70 }}>
          <div style={{ ...s.card, textAlign: "center", padding: 18 }}>
            <div style={{ fontSize: 28, marginBottom: 6 }} aria-hidden="true">✨</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: colors.text, marginBottom: 6 }}>Sign up to chat with Mamu</div>
            <div style={{ fontSize: 12, color: colors.textMuted, lineHeight: 1.45, marginBottom: 14 }}>
              Mamu can break down a bill, a rep, or how the system works. Create an account to save your chats and personalize the feed.
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button style={{ ...s.btn("primary"), flex: 1 }} onClick={() => onNav(SCREENS.CREATE_ACCOUNT)}>Sign Up</button>
              <button style={{ ...s.btn("outline"), flex: 1 }} onClick={() => onNav(SCREENS.LOGIN)}>Log In</button>
            </div>
          </div>
        </div>
        <NavBar active={SCREENS.ASSISTANT} onNav={onNav} />
      </div>
    );
  }

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.header, paddingTop: 12, display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <div>
          <h1 style={{ ...s.headerTitle, fontSize: 18 }}>{COPY.assistant.title}</h1>
          <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>{COPY.assistant.subtitle}</div>
        </div>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={onClearChat}
            style={{ background: "none", border: "none", color: colors.textMuted, fontFamily: fontSans, fontSize: 12, cursor: "pointer", padding: "4px 0", flexShrink: 0 }}
          >Clear</button>
        )}
      </div>
      {/* Chat body — flex column so the input row sticks above the nav bar
          while the message list fills the remaining space. paddingBottom
          leaves room for the 56px NavBar. */}
      <div style={{ ...s.body, padding: 0, display: "flex", flexDirection: "column", paddingBottom: 56 }}>
        {chipText && (
          <div style={{ padding: "10px 20px 0" }}>
            <span style={{ display: "inline-block", background: colors.accentDim, color: colors.accent, padding: "3px 9px", borderRadius: 11, fontSize: 11, fontWeight: 600 }}>{chipText}</span>
          </div>
        )}

        {/* Message list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "12px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
          {messages.length === 0 && !sending && !errorMsg && (
            <div>
              <div style={{ color: colors.textMuted, fontSize: 12, marginBottom: 10 }}>{COPY.assistant.emptyState}</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {COPY.assistant.suggestions.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => submit(q)}
                    style={{ textAlign: "left", padding: "9px 12px", background: colors.surfaceLight, border: `1px solid ${colors.border}`, borderRadius: 10, fontFamily: fontSans, fontSize: 12, color: colors.text, cursor: "pointer" }}
                  >{q}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <FadeIn key={i} duration={240} delay={i === messages.length - 1 ? 60 : 0}
              style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
              <div style={{
                background: m.role === "user" ? colors.accent : colors.surfaceLight,
                color: m.role === "user" ? "#fff" : colors.text,
                padding: "8px 12px", borderRadius: 12,
                maxWidth: "85%", fontSize: 13, lineHeight: 1.45,
                whiteSpace: "pre-wrap",
                boxShadow: m.role === "assistant" ? `inset 0 0 0 1px ${colors.border}` : "none",
              }}>{m.content}</div>
            </FadeIn>
          ))}
          {sending && (
            <div style={{ alignSelf: "flex-start", color: colors.textMuted, fontSize: 12, padding: "4px 4px" }}>{COPY.assistant.sending}</div>
          )}
          {errorMsg && (
            <FadeIn duration={240} style={{ display: "flex", justifyContent: "flex-start" }}>
              <div style={{
                background: colors.surfaceLight,
                color: colors.red,
                padding: "8px 12px", borderRadius: 12,
                maxWidth: "85%", fontSize: 13, lineHeight: 1.45,
                boxShadow: `inset 0 0 0 1px ${colors.redDim}`,
              }}>{errorMsg}</div>
            </FadeIn>
          )}
        </div>

        {/* Input row + disclaimer */}
        <div style={{ borderTop: `1px solid ${colors.border}`, background: colors.surface }}>
          <div style={{ display: "flex", gap: 8, padding: "10px 20px 8px" }}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
              placeholder={COPY.assistant.placeholder}
              disabled={sending}
              style={{
                flex: 1, padding: "10px 12px", borderRadius: 10,
                border: `1px solid ${colors.border}`, fontFamily: fontSans,
                fontSize: 13, color: colors.text, background: colors.bg,
                outline: "none",
              }}
            />
            <button
              type="button"
              onClick={() => submit()}
              disabled={sending || !input.trim()}
              style={{
                padding: "0 16px", borderRadius: 10, border: "none",
                background: sending || !input.trim() ? colors.borderLight : colors.accent,
                color: "#fff", fontFamily: fontSans, fontWeight: 600, fontSize: 13,
                cursor: sending || !input.trim() ? "default" : "pointer",
              }}
            >{COPY.assistant.send}</button>
          </div>
          <div style={{ padding: "0 20px 10px", fontSize: 10, color: colors.textMuted, textAlign: "center", lineHeight: 1.3 }}>
            {COPY.assistant.disclaimer}
          </div>
        </div>
      </div>
      <NavBar active={SCREENS.ASSISTANT} onNav={onNav} />
    </div>
  );
};

// Placeholder layout that mirrors the profile screen's actual shape so the
// loading state doesn't feel like a blank page. Used by both federal and state
// profile screens — pass the number of score cards and nav tiles to match the
// real screen's grid.
const ProfileSkeleton = ({ scoreCount = 3, tileCount = 5 }) => (
  <div>
    <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 16 }}>
      <Shimmer width={56} height={56} borderRadius="50%" />
      <div style={{ flex: 1 }}>
        <Shimmer width={140} height={18} style={{ display: "block", marginBottom: 8 }} />
        <Shimmer width={90} height={12} style={{ display: "block", marginBottom: 4 }} />
        <Shimmer width={120} height={10} style={{ display: "block" }} />
      </div>
    </div>
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${scoreCount}, 1fr)`, gap: 8, marginBottom: 14 }}>
      {Array.from({ length: scoreCount }).map((_, i) => (
        <div key={i} style={{ ...s.card, textAlign: "center", marginBottom: 0 }}>
          <Shimmer width={48} height={22} style={{ display: "block", margin: "0 auto 6px" }} />
          <Shimmer width={40} height={9} style={{ display: "block", margin: "0 auto" }} />
        </div>
      ))}
    </div>
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {Array.from({ length: tileCount }).map((_, i) => (
        <div key={i} style={{ ...s.card, display: "flex", alignItems: "center", gap: 12, marginBottom: 0 }}>
          <Shimmer width={36} height={36} borderRadius={8} />
          <div style={{ flex: 1 }}>
            <Shimmer width={120} height={13} style={{ display: "block", marginBottom: 6 }} />
            <Shimmer width={80} height={11} style={{ display: "block" }} />
          </div>
        </div>
      ))}
    </div>
  </div>
);

// Card-row placeholder for list-style screens (state legislators, events).
// `leading` controls the left affordance: an avatar circle, a calendar date
// chip, etc.
const ListRowSkeleton = ({ count = 5, leading = "circle" }) => {
  const leadingNode =
    leading === "circle" ? <Shimmer width={36} height={36} borderRadius="50%" /> :
    leading === "square" ? <Shimmer width={44} height={44} borderRadius={8} /> :
    null;
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ ...s.card, display: "flex", alignItems: "center", gap: 12 }}>
          {leadingNode}
          <div style={{ flex: 1 }}>
            <Shimmer width={140} height={13} style={{ display: "block", marginBottom: 6 }} />
            <Shimmer width={90} height={11} style={{ display: "block" }} />
          </div>
        </div>
      ))}
    </>
  );
};

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
      <p style={{ color: colors.textMuted, fontSize: 13, lineHeight: 1.5, marginBottom: 40 }}>
        Hold your politicians accountable.<br />Follow the money. Take action.
      </p>
      <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 12 }}>
        <button style={s.btn("primary")} onClick={() => onNav(SCREENS.CREATE_ACCOUNT)}>Create Account</button>
        <button style={s.btn("outline")} onClick={() => onNav(SCREENS.LOGIN)}>Log In</button>
      </div>
    </div>
    <div style={{ padding: "20px 40px 40px", textAlign: "center", fontSize: 10, color: colors.textMuted }}>
      Democracy requires participation.
    </div>
  </div>
);

// 2. CREATE ACCOUNT
const CreateAccountScreen = ({ onNav, onSignedIn, offline }) => {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [state, setStateVal] = useState("CT");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setError(null);
    if (!name.trim()) return setError("Name is required");
    if (!email.trim()) return setError("Email is required");
    if (password.length < 8) return setError("Password must be at least 8 characters");
    setSubmitting(true);
    try {
      const res = await api.signup({ email: email.trim(), password, name: name.trim(), state });
      auth.setSession(res.token, res.user);
      onSignedIn(res.user);
      onNav(SCREENS.ISSUE_SELECT);
    } catch (e) {
      setError(e.detail || e.message || "Signup failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingTop: 20 }}>
        <BackButton onClick={() => onNav(SCREENS.SPLASH)} />
        <h2 style={{ ...s.headerTitle, marginBottom: 4 }}>Create Account</h2>
        <p style={{ color: colors.textMuted, fontSize: 12, marginBottom: 20, marginTop: 0 }}>Your data stays yours. We never sell it.</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={{ fontSize: 11, color: colors.textMuted, display: "block", marginBottom: 4 }}>Full Name</label>
            <input style={s.input} placeholder="Jane Doe" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: colors.textMuted, display: "block", marginBottom: 4 }}>Email</label>
            <input style={s.input} placeholder="jane@example.com" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: colors.textMuted, display: "block", marginBottom: 4 }}>State (2-letter)</label>
            <input style={s.input} placeholder="CT" value={state} onChange={(e) => setStateVal(e.target.value.toUpperCase().slice(0, 2))} maxLength={2} />
            <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 4 }}>
              We use this to find your representatives
            </div>
          </div>
          <div style={s.divider} />
          <label style={{ fontSize: 11, color: colors.textMuted, display: "block", marginBottom: 4 }}>Password</label>
          <input style={s.input} type="password" autoComplete="new-password" placeholder="Min 8 characters" value={password} onChange={(e) => setPassword(e.target.value)} />
          {error && (
            <div style={{ fontSize: 11, color: colors.red }}>{error}</div>
          )}
          <button style={{ ...s.btn("primary"), marginTop: 8, opacity: submitting ? 0.6 : 1 }} disabled={submitting} onClick={submit}>
            {submitting ? "Creating..." : "Continue"}
          </button>
          <div style={{ textAlign: "center", fontSize: 11, color: colors.textMuted }}>
            Already have an account?{" "}
            <span style={{ color: colors.accent, cursor: "pointer" }} onClick={() => onNav(SCREENS.LOGIN)}>Log in</span>
          </div>
        </div>
      </div>
    </div>
  );
};

// 3. LOGIN
const LoginScreen = ({ onNav, onSignedIn, offline, onEnterGuest }) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setError(null);
    if (!email.trim() || !password) return setError("Email and password required");
    setSubmitting(true);
    try {
      const res = await api.login({ email: email.trim(), password });
      auth.setSession(res.token, res.user);
      onSignedIn(res.user);
      onNav(SCREENS.DASHBOARD);
    } catch (e) {
      setError(e.detail || e.message || "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingTop: 20 }}>
        <BackButton onClick={() => onNav(SCREENS.SPLASH)} />
        <h2 style={{ ...s.headerTitle, marginBottom: 20 }}>Welcome Back</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={{ fontSize: 11, color: colors.textMuted, display: "block", marginBottom: 4 }}>Email</label>
            <input style={s.input} placeholder="jane@example.com" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
          </div>
          <div>
            <label style={{ fontSize: 11, color: colors.textMuted, display: "block", marginBottom: 4 }}>Password</label>
            <input style={s.input} type="password" autoComplete="current-password" placeholder="Enter password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
          </div>
          {error && (
            <div style={{ fontSize: 11, color: colors.red }}>{error}</div>
          )}
          <button style={{ ...s.btn("primary"), marginTop: 8, opacity: submitting ? 0.6 : 1 }} disabled={submitting} onClick={submit}>
            {submitting ? "Logging in..." : "Log In"}
          </button>
          <div style={{ textAlign: "center", fontSize: 11, color: colors.textMuted }}>
            New here?{" "}
            <span style={{ color: colors.accent, cursor: "pointer" }} onClick={() => onNav(SCREENS.CREATE_ACCOUNT)}>Create an account</span>
          </div>
          {/* Temporary guest mode — handy for handing the phone to someone
              for a quick demo. User asked for this to be easy to remove
              later; the link + onEnterGuest prop are the whole footprint. */}
          {onEnterGuest && (
            <div style={{ textAlign: "center", fontSize: 11, color: colors.textMuted, fontFamily: fontSans, marginTop: 4 }}>
              Just looking?{" "}
              <span style={{ color: colors.accent, cursor: "pointer", textDecoration: "underline" }} onClick={onEnterGuest}>Continue as guest</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// 4. ISSUE SELECT
const IssueSelectScreen = ({ onNav, offline, currentUser, onSaveIssues }) => {
  // Seed from stored issues, but drop legacy display-string values
  // ("Healthcare") that don't match a category key — they came from an
  // earlier storage format and would render as a chip nobody can toggle.
  const stored = (currentUser?.issues || []).filter((k) => COPY.categories[k]).slice(0, 5);
  const [selected, setSelected] = useState(stored);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const atMax = selected.length >= 5;
  const atMin = selected.length === 0;
  const toggle = (key) => {
    if (selected.includes(key)) setSelected(selected.filter((i) => i !== key));
    else if (!atMax) setSelected([...selected, key]);
  };

  const done = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await onSaveIssues(selected);
      onNav(SCREENS.DASHBOARD);
    } catch (e) {
      setError(e.detail || e.message || "Could not save");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingTop: 12 }}>
        <h2 style={{ ...s.headerTitle, marginBottom: 4 }}>What Issues Matter Most?</h2>
        <p style={{ color: colors.textMuted, fontSize: 12, marginTop: 0, marginBottom: 16 }}>Select up to 5. This filters your alerts and feed.</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 24 }}>
          {Object.keys(COPY.categories).map((key) => (
            <button key={key} style={s.chip(selected.includes(key))} onClick={() => toggle(key)}>
              {friendlyCategory(key)}
            </button>
          ))}
        </div>
        <div style={{ fontSize: 12, color: atMax ? colors.accent : colors.textMuted, marginBottom: 12 }}>
          {selected.length}/5 selected{atMax ? " · deselect one to choose another" : ""}
        </div>
        {error && (
          <div style={{ fontSize: 11, color: colors.red, marginBottom: 8 }}>{error}</div>
        )}
        <button
          style={{ ...s.btn("primary"), opacity: submitting || atMin ? 0.6 : 1 }}
          disabled={submitting || atMin}
          onClick={done}
        >
          {submitting ? "Saving..." : atMin ? "Pick at least one to continue" : "Done - Show Me My Reps"}
        </button>
      </div>
    </div>
  );
};

// 5. DASHBOARD - WIRED TO BACKEND
// Subtle shimmer component for loading funding numbers and skeleton placeholders.
// Carries its own @keyframes so it animates anywhere it renders, not just under
// the Dashboard.
const Shimmer = ({ width = 40, height = 16, borderRadius = 4, style }) => (
  <>
    <style>{`@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }`}</style>
    <span
      style={{
        display: "inline-block",
        width,
        height,
        borderRadius,
        background: `linear-gradient(90deg, ${colors.border} 0%, ${colors.borderLight} 50%, ${colors.border} 100%)`,
        backgroundSize: "200% 100%",
        animation: "shimmer 1.3s ease-in-out infinite",
        verticalAlign: "middle",
        ...style,
      }}
    />
  </>
);

// Self-fetching rep card - loads its own funding on mount
// Warm-treatment quick-action button used on the dashboard. Each instance
// owns its own pressed state so the tactile transform only fires on the
// tapped tile, not the whole grid. `span` makes a single tile occupy both
// columns — used for the trailing odd action so the grid doesn't dangle.
const QuickActionButton = ({ icon, label, onClick, span }) => {
  const [pressed, setPressed] = useState(false);
  const press = {
    onPointerDown: () => setPressed(true),
    onPointerUp: () => setPressed(false),
    onPointerLeave: () => setPressed(false),
    onPointerCancel: () => setPressed(false),
  };
  return (
    <button
      type="button"
      onClick={onClick}
      {...press}
      style={{
        gridColumn: span ? "1 / -1" : "auto",
        cursor: "pointer",
        display: "flex", alignItems: "center", gap: 10,
        padding: "12px 14px",
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: 14,
        color: colors.text,
        fontFamily: fontSans,
        fontSize: 13, fontWeight: 500,
        textAlign: "left",
        boxShadow: pressed
          ? "0 1px 0 rgba(231,122,27,0.05)"
          : "0 6px 16px -12px rgba(231,122,27,0.18), 0 1px 0 rgba(231,122,27,0.04)",
        transform: pressed ? "translateY(1px)" : "translateY(0)",
        transition: "transform 0.16s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.16s cubic-bezier(0.16, 1, 0.3, 1)",
      }}
    >
      <span aria-hidden="true" style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: 30, height: 30, borderRadius: 999,
        background: colors.accentDim,
        flexShrink: 0,
      }}>
        <Icon type={icon} size={16} color={colors.accent} />
      </span>
      <span>{label}</span>
    </button>
  );
};

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
    <RepCardShell onClick={onClick}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Avatar name={rep.name} party={rep.party} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontWeight: 600, fontSize: 14, fontFamily: fontSans, color: colors.text }}>{rep.name}</span>
            <PartyBadge party={rep.party} />
          </div>
          <div style={{ fontSize: 12, color: colors.textMuted, fontFamily: fontSans, marginTop: 2 }}>
            {rep.chamber} · {rep.district}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 18, marginTop: 12 }}>
        <div>
          <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans }}>Raised</div>
          {renderValue(funding?.total_raised, colors.accent)}
        </div>
        <div>
          <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans }}>PAC $</div>
          {renderValue(funding?.pac_total)}
        </div>
        <div>
          <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans }}>Small $</div>
          {renderValue(funding?.small_donor_total)}
        </div>
      </div>
    </RepCardShell>
  );
};

// Outer button for RepCard — split out so the press-state lives on the
// container (the inner RepCard body uses an effect hook for funding fetch,
// and we don't want a second state to muddy that). White surface with a
// warm-tinted diffusion shadow matches ComingUpCard / QuickActionButton.
const RepCardShell = ({ onClick, children }) => {
  const [pressed, setPressed] = useState(false);
  const press = {
    onPointerDown: () => setPressed(true),
    onPointerUp: () => setPressed(false),
    onPointerLeave: () => setPressed(false),
    onPointerCancel: () => setPressed(false),
  };
  return (
    <button
      type="button"
      onClick={onClick}
      {...press}
      style={{
        width: "100%", textAlign: "left", cursor: "pointer",
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: 16,
        padding: "14px 16px",
        marginBottom: 10,
        color: colors.text, fontFamily: fontSans,
        boxShadow: pressed
          ? "0 1px 0 rgba(231,122,27,0.05)"
          : "0 6px 18px -10px rgba(231,122,27,0.13), 0 1px 0 rgba(231,122,27,0.05)",
        transform: pressed ? "translateY(1px)" : "translateY(0)",
        transition: "transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.18s cubic-bezier(0.16, 1, 0.3, 1)",
      }}
    >
      {children}
    </button>
  );
};

// "Coming up" — the dashboard's read-path on /api/upcoming-votes. The whole
// strip is one tap target into the alerts feed. Hierarchy comes from a
// leading accent rail on the soonest row (when imminent), 1px hairline
// dividers instead of per-row card pillows, and a sans/mono pairing —
// category in sans, bill number + relative time in mono. The card sits on
// the warm bg with a low-contrast, accent-tinted diffusion shadow rather
// than the generic surface-light pillow that the rest of the dashboard
// uses (per skill rule: cards only when elevation communicates hierarchy).
const SkeletonBar = ({ width = "60%", height = 9, style }) => (
  <span style={{
    display: "inline-block", width, height,
    borderRadius: 3,
    background: `linear-gradient(90deg, ${colors.surfaceLight} 0%, ${colors.border} 50%, ${colors.surfaceLight} 100%)`,
    backgroundSize: "200% 100%",
    animation: "fuu-shimmer 1.6s ease-in-out infinite",
    ...style,
  }} />
);

const ComingUpRow = ({ row, index, isFirst, onClick }) => {
  const days = row.days_until;
  const imminent = typeof days === "number" && days <= 3;
  const label = friendlyCategory(row.category);
  const subParts = [];
  if (typeof days === "number") subParts.push(COPY.dashboard.comingUpRelative(days));
  if (row.chamber) subParts.push(`${row.chamber} floor`);

  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        position: "relative",
        display: "block",
        width: "100%",
        textAlign: "left",
        cursor: "pointer",
        padding: "13px 16px",
        border: "none",
        borderTop: isFirst ? "none" : `1px solid ${colors.border}`,
        background: imminent && isFirst ? colors.accentDim : "transparent",
        color: "inherit",
        fontFamily: "inherit",
        opacity: 0,
        animation: "fuu-fade-up 0.24s cubic-bezier(0.16, 1, 0.3, 1) both",
        animationDelay: `${80 + index * 95}ms`,
      }}
    >
      <div style={{
        display: "flex", alignItems: "baseline",
        justifyContent: "space-between", gap: 12,
      }}>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 8,
          fontSize: 14, fontWeight: 600, fontFamily: fontSans,
          color: colors.text, minWidth: 0,
        }}>
          {imminent && (
            <span
              aria-hidden="true"
              style={{
                display: "inline-block", width: 7, height: 7, borderRadius: 999,
                background: colors.accent, flexShrink: 0,
                animation: "fuu-soft-pulse 2.4s ease-in-out infinite",
              }}
            />
          )}
          <span style={{
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>{label}</span>
        </span>
        {row.bill_number && (
          <span style={{
            fontSize: 11, color: colors.textMuted, fontFamily: font,
            fontWeight: 500, flexShrink: 0,
          }}>
            {row.bill_number}
          </span>
        )}
      </div>
      {subParts.length > 0 && (
        <div style={{
          fontSize: 12, color: colors.textMuted, fontFamily: fontSans,
          marginTop: 3,
        }}>
          {subParts.join(" · ")}
        </div>
      )}
    </button>
  );
};

const ComingUpSkeleton = () => (
  <>
    {[0, 1, 2].map((i) => (
      <div key={i} style={{
        padding: "11px 14px",
        borderTop: i === 0 ? "none" : `1px solid ${colors.border}`,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
          <SkeletonBar width="55%" />
          <SkeletonBar width="22%" />
        </div>
        <SkeletonBar width="40%" style={{ marginTop: 7 }} />
      </div>
    ))}
  </>
);

const ComingUpEmpty = () => (
  <div style={{
    padding: "22px 16px",
    display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 6,
  }}>
    <Icon type="clock" size={20} color={colors.accent} />
    <div style={{
      fontSize: 14, fontWeight: 600, fontFamily: fontSans,
      color: colors.text, marginTop: 4,
    }}>
      {COPY.dashboard.comingUpEmpty}
    </div>
    <div style={{
      fontSize: 12, color: colors.textMuted, fontFamily: fontSans,
    }}>
      Tap to explore recent activity.
    </div>
  </div>
);

const ComingUpCard = ({ upcoming, loading, onOpen }) => {
  return (
    <div style={s.section}>
      <div style={{ ...s.sectionTitleFriendly, marginBottom: 4 }}>
        {COPY.dashboard.comingUpTitle}
      </div>
      {/* Caption sits outside the card (labels-outside rule) and uses sans
          rather than mono-uppercase so it reads as conversation, not a
          terminal label. */}
      <div style={{
        fontSize: 12, color: colors.textMuted, fontFamily: fontSans,
        marginBottom: 10,
      }}>
        {COPY.dashboard.comingUpSubtitle}
      </div>

      <div
        style={{
          background: colors.surface,
          border: `1px solid ${colors.border}`,
          borderRadius: 16,
          color: colors.text, fontFamily: fontSans,
          overflow: "hidden",
          // Accent-tinted, low-contrast diffusion shadow — lifts the strip
          // off the cream bg without the AI "neon glow" tell. Per-row press
          // feedback comes from the global button:active rule in fuu-anim-styles.
          boxShadow:
            "0 6px 18px -10px rgba(231,122,27,0.13), 0 1px 0 rgba(231,122,27,0.05)",
        }}
      >
        {loading ? (
          <ComingUpSkeleton />
        ) : upcoming.length === 0 ? (
          <button
            type="button"
            onClick={onOpen}
            style={{
              display: "block", width: "100%", textAlign: "left",
              background: "transparent", border: "none", padding: 0, margin: 0,
              color: "inherit", fontFamily: "inherit", cursor: "pointer",
            }}
          >
            <ComingUpEmpty />
          </button>
        ) : (
          upcoming.map((u, i) => (
            <ComingUpRow
              key={u.id}
              row={u}
              index={i}
              isFirst={i === 0}
              onClick={onOpen}
            />
          ))
        )}
      </div>
    </div>
  );
};

// 5. DASHBOARD - WIRED TO BACKEND (streaming)
const DashboardScreen = ({ onNav, onSelectPolitician, userState, currentUser, userIssues }) => {
  const { data, loading, error, offline, reload } = useApi(
    () => api.getRepsByState(userState || "CT"),
    [userState],
    { representatives: [], state: userState || "CT", count: 0 }
  );

  // "Coming up" feed — dedicated /api/upcoming-votes endpoint reads
  // scheduled_votes directly, so unlike /api/alerts each bill appears once.
  // Personalised by user's stored issues (sent via auth header by the
  // optionally-authenticated endpoint); explicit prop pass keeps the deps
  // array honest so the fetch refires when preferences change.
  const personalIssues = (userIssues || [])
    .filter((k) => k && COPY.categories[k]);
  const personalKey = personalIssues.join(",");
  const { data: upcomingData, loading: upcomingLoading, offline: upcomingOffline } = useApi(
    () => api.getUpcomingVotes({
      state: userState,
      categories: personalIssues.length ? personalIssues : undefined,
      limit: 6,
    }),
    [userState, personalKey],
    { votes: [] }
  );

  const reps = data?.representatives || [];
  const isOffline = offline || upcomingOffline;

  // Offline fallback: synthesize vote rows from SAMPLE.alerts so the render
  // path only sees one model. days_until omitted because sample data has no
  // real schedule — the relative-time line will skip when null.
  const upcoming = upcomingData?.votes?.length
    ? upcomingData.votes.slice(0, 3)
    : (isOffline
        ? SAMPLE.alerts
            .filter((a) => a.vote)
            .slice(0, 3)
            .map((a) => ({
              id: a.id,
              bill_number: a.vote.bill_number,
              category: a.vote.category,
              days_until: null,
            }))
        : []);

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingTop: 16, paddingBottom: 70 }}>
        {/* Greeting lives inside the scrollable body (not in a fixed
            header band) so it scrolls away with the content rather than
            sticking at the top. Search icon sits top-right since Search
            lost its bottom-nav slot to the Ask tab — globally reachable
            via this affordance instead. */}
        <div style={{ marginBottom: 20, display: "flex", alignItems: "flex-start", gap: 12 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h1 style={{ ...s.headerTitle, fontSize: 24, fontWeight: 700, fontFamily: fontSans, textTransform: "none", letterSpacing: -0.2, margin: 0, color: colors.text }}>
              {COPY.dashboard.greeting(currentUser?.name)}
            </h1>
            <p style={{ fontSize: 13, color: colors.textMuted, fontFamily: fontSans, marginTop: 4, marginBottom: 0, lineHeight: 1.4 }}>
              {personalIssues.length > 0
                ? COPY.dashboard.greetingSubWithIssues(userState || "CT", personalIssues.map(friendlyCategory))
                : COPY.dashboard.greetingSub(userState || "CT")} {offline && "· offline"}
            </p>
          </div>
          <button
            type="button"
            onClick={() => onNav(SCREENS.SEARCH)}
            aria-label="Search"
            style={{
              width: 40, height: 40, borderRadius: "50%",
              background: colors.surface, border: `1px solid ${colors.border}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              cursor: "pointer", color: colors.text, flexShrink: 0,
              marginTop: 4,
            }}
          >
            <Icon type="search" size={18} />
          </button>
        </div>

        {/* Quick Actions first — action-first onboarding for new voters: the
            verbs you can take are the most useful starting point. The
            trailing odd action spans both columns so the grid lands on a
            balanced silhouette instead of a dangling tile. */}
        <div style={s.section}>
          <div style={s.sectionTitleFriendly}>{COPY.dashboard.quickActionsTitle}</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            {(() => {
              const actions = [
                { icon: "phone", label: COPY.dashboard.quickActions.contactRep, screen: SCREENS.CONTACT_REP },
                { icon: "vote", label: COPY.dashboard.quickActions.votingGuide, screen: SCREENS.LEARN_TO_VOTE },
                { icon: "calendar", label: COPY.dashboard.quickActions.events, screen: SCREENS.EVENTS },
                { icon: "dollar", label: COPY.dashboard.quickActions.followMoney, screen: SCREENS.SEARCH },
                { icon: "home", label: COPY.dashboard.quickActions.stateReps, screen: SCREENS.STATE_REPS },
              ];
              return actions.map((a, i) => (
                <QuickActionButton
                  key={a.label}
                  icon={a.icon}
                  label={a.label}
                  onClick={() => onNav(a.screen)}
                  span={i === actions.length - 1 && actions.length % 2 === 1}
                />
              ));
            })()}
          </div>
        </div>

        <ComingUpCard
          upcoming={upcoming}
          loading={upcomingLoading && upcoming.length === 0}
          onOpen={() => onNav(SCREENS.ALERTS)}
        />


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
            <div style={s.sectionTitleFriendly}>{COPY.dashboard.repsSectionTitle}</div>
            {reps.map((rep, i) => (
              <FadeIn key={rep.bioguide_id} delay={Math.min(i * 130, 780)}>
                <RepCard
                  rep={rep}
                  onClick={() => onSelectPolitician(rep.bioguide_id)}
                />
              </FadeIn>
            ))}
          </div>
        )}

      </div>
      <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
    </div>
  );
};

// 6. SEARCH - WIRED TO BACKEND
const SearchScreen = ({ onNav, onSelectPolitician, onSelectStateRep, userState }) => {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  const { data, loading, offline } = useApi(
    async () => {
      if (!debounced || debounced.length < 2) return { results: [] };
      return await api.searchUnified(debounced, userState);
    },
    [debounced, userState],
    {
      results: query.length >= 2
        ? [
            ...SAMPLE.reps
              .filter((r) => r.name.toLowerCase().includes(query.toLowerCase()))
              .map((r) => ({ ...r, level: "federal" })),
            ...SAMPLE.stateReps
              .filter((r) => (!userState || r.state === userState)
                && r.name.toLowerCase().includes(query.toLowerCase()))
              .map((r) => ({ ...r, level: "state" })),
          ]
        : [],
    }
  );

  const results = data?.results || [];

  const handleClick = (p) => {
    if (p.level === "state") onSelectStateRep?.(p.people_id);
    else onSelectPolitician?.(p.bioguide_id);
  };

  const levelBadge = (level) => (
    <span style={{
      fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4, marginLeft: 6,
      background: level === "state" ? "rgba(110, 168, 254, 0.15)" : "rgba(255, 200, 87, 0.15)",
      color: level === "state" ? "#6ea8fe" : colors.yellow,
      letterSpacing: 0.5,
    }}>
      {level === "state" ? "STATE" : "FEDERAL"}
    </span>
  );

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={s.header}>
        <BackButton onClick={() => onNav(SCREENS.DASHBOARD)} />
        <h1 style={{ ...s.headerTitle, fontSize: 18 }}>Search</h1>
      </div>
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <input style={{ ...s.input, marginBottom: 14 }} placeholder="Search federal + state by name..." value={query} onChange={(e) => setQuery(e.target.value)} autoFocus />
        {query.length < 2 && (
          <p style={{ fontSize: 11, color: colors.textMuted }}>
            Type at least 2 characters to search.
            {userState && <> State results limited to {userState}.</>}
          </p>
        )}
        {query.length >= 2 && loading && <Loading label="Searching..." />}
        {query.length >= 2 && !loading && results.length === 0 && (
          <p style={{ fontSize: 11, color: colors.textMuted }}>No results found.</p>
        )}
        {results.length > 0 && (
          <>
            <div style={s.sectionTitle}>Results ({results.length})</div>
            {results.map((p, i) => {
              const id = p.level === "state" ? `s-${p.people_id}` : `f-${p.bioguide_id}`;
              return (
                <FadeIn key={id} delay={Math.min(i * 55, 495)}>
                  <div style={{ ...s.card, cursor: "pointer", display: "flex", alignItems: "center", gap: 12 }} onClick={() => handleClick(p)}>
                    <Avatar name={p.name} size={36} party={p.party} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>
                        {p.name} <PartyBadge party={p.party} />{levelBadge(p.level)}
                      </div>
                      <div style={{ fontSize: 11, color: colors.textMuted }}>{p.chamber} · {p.district}</div>
                    </div>
                    <Icon type="back" size={14} color={colors.textMuted} />
                  </div>
                </FadeIn>
              );
            })}
          </>
        )}
      </div>
      <NavBar active={SCREENS.SEARCH} onNav={onNav} />
    </div>
  );
};

// Synthesize a profile-shaped fallback for an arbitrary bioguide_id when the
// backend is unreachable. Without this, every offline profile rendered as
// Murphy regardless of which card was tapped.
function makeOfflineProfile(bioguideId) {
  if (bioguideId === SAMPLE.profile.profile.bioguide_id) return SAMPLE.profile;
  const rep = SAMPLE.reps.find((r) => r.bioguide_id === bioguideId);
  if (!rep) return null;
  return {
    profile: {
      bioguide_id: rep.bioguide_id,
      name: rep.name,
      party: rep.party,
      state: rep.state,
      district: rep.district,
      chamber: rep.chamber,
      phone: rep.phone,
      website: rep.website,
      office: rep.office,
    },
    funding: {
      total_raised: rep.funding?.total_raised || 0,
      total_funding: 0,
      pac_total: rep.funding?.pac_total || 0,
      small_donor_total: rep.funding?.small_donor_total || 0,
      individual_total: 0,
      top_industries: [],
      top_donors: [],
    },
    votes: { recent: [], total_tracked: 0, yea_count: 0, nay_count: 0 },
    sponsored_bills: [],
    promise_score: null,
    contact: {
      phone: rep.phone || "",
      website: rep.website || "",
      office: rep.office || "",
      contact_form: "",
    },
  };
}

// 7. POLITICIAN PROFILE - WIRED TO BACKEND
const PoliticianProfileScreen = ({ onNav, bioguideId, onSetProfileData }) => {
  const { data, loading, error, offline, reload } = useApi(
    () => api.getProfile(bioguideId),
    [bioguideId],
    makeOfflineProfile(bioguideId)
  );

  useEffect(() => {
    if (data) onSetProfileData(data);
  }, [data, onSetProfileData]);

  if (loading) {
    return (
      <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
        <StatusBar offline={offline} />
        <div style={{ ...s.body, paddingBottom: 70 }}>
          <BackButton onClick={() => onNav(SCREENS.DASHBOARD)} label="Dashboard" />
          <ProfileSkeleton scoreCount={3} tileCount={5} />
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

        {/* Score Cards — cascade left-to-right so the eye reads the row as
            a deliberate reveal instead of three values popping in together. */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 14 }}>
          <FadeIn delay={0}>
            <div style={{ ...s.card, textAlign: "center", marginBottom: 0 }}>
              <div style={{ fontSize: 22, fontWeight: 800, fontFamily: font, color: colors.textMuted }}>
                {data.promise_score ?? "—"}
              </div>
              <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans, marginTop: 2 }}>{COPY.profile.promiseScoreLabel}</div>
            </div>
          </FadeIn>
          <FadeIn delay={90}>
            <div style={{ ...s.card, textAlign: "center", marginBottom: 0 }}>
              <div style={{ fontSize: 22, fontWeight: 800, fontFamily: font, color: colors.green }}>
                {v.yea_count}<span style={{ color: colors.textMuted, fontSize: 14 }}>/{v.total_tracked}</span>
              </div>
              <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans, marginTop: 2 }}>{COPY.profile.yeaVotesLabel}</div>
            </div>
          </FadeIn>
          <FadeIn delay={180}>
            <div style={{ ...s.card, textAlign: "center", marginBottom: 0 }}>
              <div style={{ fontSize: 22, fontWeight: 800, fontFamily: font, color: colors.accent }}>
                {fmt(f.total_raised)}
              </div>
              <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans, marginTop: 2 }}>{COPY.profile.raisedLabel}</div>
            </div>
          </FadeIn>
        </div>

        {/* Navigation Tiles — cascade top-to-bottom starting after the score
            row's cascade so the page reads as a two-stage reveal. */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {[
            { icon: "dollar", label: COPY.profile.tiles.funding.label, sub: f.top_industries?.length ? `${COPY.profile.tiles.funding.topPrefix}${f.top_industries[0].industry}` : COPY.profile.tiles.funding.fallbackSub, screen: SCREENS.FUNDING },
            { icon: "vote", label: COPY.profile.tiles.voting.label, sub: COPY.profile.tiles.voting.sub(v.total_tracked), screen: SCREENS.VOTING_HISTORY },
            { icon: "star", label: COPY.profile.tiles.stances.label, sub: COPY.profile.tiles.stances.sub, screen: SCREENS.PROMISE_SCORING },
            { icon: "clock", label: COPY.profile.tiles.timeline.label, sub: COPY.profile.tiles.timeline.sub, screen: SCREENS.TIMELINE },
            { icon: "phone", label: COPY.profile.tiles.contact.label, sub: p.phone || COPY.profile.tiles.contact.fallbackSub, screen: SCREENS.TAKE_ACTION },
          ].map((item, i) => (
            <FadeIn key={item.label} delay={240 + i * 110}>
              <button
                type="button"
                onClick={() => onNav(item.screen)}
                style={{
                  ...s.card,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  marginBottom: 0,
                  width: "100%",
                  textAlign: "left",
                  font: "inherit",
                  color: "inherit",
                }}
              >
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
              </button>
            </FadeIn>
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
        <p style={{ color: colors.textMuted, fontSize: 11, marginTop: 0 }}>Campaign finance from FEC filings</p>

        <div style={{ ...s.card, textAlign: "center", marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans }}>Total raised</div>
          <div style={{ fontSize: 28, fontWeight: 800, fontFamily: font, color: colors.accent }}>{fmt(f.total_raised)}</div>
          <div style={{ display: "flex", justifyContent: "center", gap: 20, marginTop: 8 }}>
            <div>
              <span style={{ fontSize: 14, fontWeight: 700, fontFamily: font }}>{fmt(f.pac_total)}</span>
              <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans }}>PAC</div>
            </div>
            <div>
              <span style={{ fontSize: 14, fontWeight: 700, fontFamily: font }}>{fmt(f.individual_total)}</span>
              <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans }}>Individual</div>
            </div>
            <div>
              <span style={{ fontSize: 14, fontWeight: 700, fontFamily: font }}>{fmt(f.small_donor_total)}</span>
              <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans }}>Small $</div>
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

        <p style={{ fontSize: 10, color: colors.textMuted }}>Source: OpenFEC (FEC filings). Top donors aggregated by employer using same methodology as OpenSecrets.</p>
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
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 12 }}>{COPY.profile.votingHistory.title}</h2>
        {cats.length > 1 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            {cats.map((c) => (
              <button key={c} style={s.chip(filter === c)} onClick={() => setFilter(c)}>
                {c === "all" ? COPY.profile.votingHistory.chipAll : friendlyCategory(c)}
              </button>
            ))}
          </div>
        )}
        {filtered.length === 0 && (
          <p style={{ fontSize: 11, color: colors.textMuted }}>{COPY.profile.votingHistory.emptyFilter}</p>
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
              <div style={{ fontSize: 11, color: colors.textMuted }}>{v.bill} · {friendlyCategoryInline(v.category) || "general"}</div>
            </div>
          </div>
        ))}
      </div>
      <NavBar active={SCREENS.SEARCH} onNav={onNav} />
    </div>
  );
};

// 10. STANCE ANALYSIS - AI-powered voting position analysis
const SCORE_STYLE = {
  CONSISTENT:   { bg: colors.greenDim,  border: colors.green  + "55", color: colors.green  },
  INCONSISTENT: { bg: colors.redDim,    border: colors.red    + "55", color: colors.red    },
  MIXED:        { bg: colors.yellowDim, border: colors.yellow + "55", color: colors.yellow },
  PENDING:      { bg: colors.blueDim,   border: colors.blue   + "55", color: colors.textMuted },
};

const PROMISE_STYLE = {
  KEPT:    { bg: colors.greenDim,  border: colors.green  + "55", color: colors.green  },
  BROKEN:  { bg: colors.redDim,    border: colors.red    + "55", color: colors.red    },
  PARTIAL: { bg: colors.yellowDim, border: colors.yellow + "55", color: colors.yellow },
  UNCLEAR: { bg: colors.blueDim,   border: colors.blue   + "55", color: colors.textMuted },
};

const PROMISE_RUNG_STYLE = {
  primary:     { label: "Official site",                 color: colors.green },
  noscript:    { label: "Official site (SPA fallback)",  color: colors.green },
  wikipedia:   { label: "Wikipedia",                     color: colors.blue  },
  ballotpedia: { label: "Ballotpedia",                   color: colors.blue  },
};

const PromiseScoringScreen = ({ onNav, bioguideId, profileData }) => {
  const p = profileData?.profile || SAMPLE.profile.profile;
  const id = bioguideId || p.bioguide_id;

  const { data, loading, offline } = useApi(
    () => id ? api.getStances(id) : Promise.resolve(null),
    [id],
    null
  );

  const { data: promiseData, loading: promiseLoading } = useApi(
    () => id ? api.getPromises(id) : Promise.resolve(null),
    [id],
    null
  );

  const stances = data?.stances || null;
  const aiAvailable = data?.ai_available ?? true;
  const promises = promiseData?.promises || null;
  const promiseSourceUrl = promiseData?.source_url || p.website || "";
  const promiseSourceRung = promiseData?.source_rung || null;

  const renderStanceCard = (stance, i) => {
    const score = stance.score || "PENDING";
    const st = SCORE_STYLE[score] || SCORE_STYLE.PENDING;
    return (
      <div key={i} style={{ ...s.card, marginBottom: 10, borderColor: st.border, background: st.bg }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <div style={{ fontWeight: 700, fontSize: 13 }}>{stance.topic}</div>
          <div style={{
            fontSize: 9, fontWeight: 700, fontFamily: font, letterSpacing: 0.8,
            color: st.color, background: colors.surface,
            border: `1px solid ${st.border}`, borderRadius: 4, padding: "2px 6px",
          }}>{score}</div>
        </div>
        <div style={{ fontSize: 12, lineHeight: 1.5, marginBottom: 6 }}>{stance.stance}</div>
        {stance.evidence && (
          <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.4, borderTop: `1px solid ${colors.border}`, paddingTop: 6 }}>
            {stance.evidence}
          </div>
        )}
      </div>
    );
  };

  const renderPromiseCard = (promise, i) => {
    const status = promise.status || "UNCLEAR";
    const st = PROMISE_STYLE[status] || PROMISE_STYLE.UNCLEAR;
    return (
      <div key={i} style={{ ...s.card, marginBottom: 10, borderColor: st.border, background: st.bg }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <div style={{ fontWeight: 700, fontSize: 13 }}>{promise.topic}</div>
          <div style={{
            fontSize: 9, fontWeight: 700, fontFamily: font, letterSpacing: 0.8,
            color: st.color, background: colors.surface,
            border: `1px solid ${st.border}`, borderRadius: 4, padding: "2px 6px",
          }}>{status}</div>
        </div>
        <div style={{ fontSize: 12, lineHeight: 1.5, marginBottom: 6 }}>{promise.promise}</div>
        {promise.evidence && (
          <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.4, borderTop: `1px solid ${colors.border}`, paddingTop: 6 }}>
            {promise.evidence}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.POLITICIAN_PROFILE)} label={p.name} />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 4 }}>{COPY.profile.promiseScoring.title}</h2>
        <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 14 }}>
          {COPY.profile.promiseScoring.subtitle}
        </div>

        {loading && <Loading label={COPY.profile.promiseScoring.analyzingLoad} />}

        {!loading && !aiAvailable && (
          <div style={{ ...s.card, background: colors.yellowDim, borderColor: colors.yellow + "44" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: colors.yellow, marginBottom: 6 }}>{COPY.profile.promiseScoring.aiKeyMissingTitle}</div>
            <div style={{ fontSize: 12, lineHeight: 1.5 }}>{COPY.profile.promiseScoring.aiKeyMissingBody}</div>
          </div>
        )}

        {!loading && aiAvailable && (
          <>
            <div style={s.sectionTitle}>{COPY.profile.promiseScoring.promisesSection}</div>
            {promiseLoading && <Loading label={COPY.profile.promiseScoring.scrapingLoad} />}
            {!promiseLoading && promises && promises.length > 0 && (
              <>
                {promises.map(renderPromiseCard)}
                {promiseSourceUrl && (
                  <div style={{ fontSize: 10, color: colors.textMuted, marginBottom: 16, lineHeight: 1.5, display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                    {PROMISE_RUNG_STYLE[promiseSourceRung] && (
                      <span style={{
                        fontSize: 9, fontWeight: 700, fontFamily: font, letterSpacing: 0.5,
                        color: PROMISE_RUNG_STYLE[promiseSourceRung].color,
                        background: colors.surface,
                        border: `1px solid ${PROMISE_RUNG_STYLE[promiseSourceRung].color}66`,
                        borderRadius: 4, padding: "2px 6px",
                      }}>{PROMISE_RUNG_STYLE[promiseSourceRung].label}</span>
                    )}
                    <span>
                      {COPY.profile.promiseScoring.promisesSourceNotePre}
                      <a href={promiseSourceUrl} target="_blank" rel="noreferrer" style={{ color: colors.accent }}>
                        {promiseSourceUrl.replace(/^https?:\/\//, "")}
                      </a>
                      {COPY.profile.promiseScoring.promisesSourceNotePost}
                    </span>
                  </div>
                )}
              </>
            )}
            {!promiseLoading && (!promises || promises.length === 0) && (
              <div style={{ ...s.card, marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: colors.textMuted }}>{COPY.profile.promiseScoring.promisesEmpty}</div>
              </div>
            )}
          </>
        )}

        {!loading && aiAvailable && stances && stances.length > 0 && (
          <>
            <div style={s.sectionTitle}>{COPY.profile.promiseScoring.keyPositions(stances.length)}</div>
            {stances.map(renderStanceCard)}
            <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 8, lineHeight: 1.5 }}>
              {COPY.profile.promiseScoring.scoresNote}
            </div>
          </>
        )}

        {!loading && aiAvailable && stances && stances.length === 0 && (
          <div style={{ ...s.card }}>
            <div style={{ fontSize: 12, color: colors.textMuted }}>{COPY.profile.promiseScoring.notEnoughData}</div>
          </div>
        )}

        {!loading && aiAvailable && !stances && !offline && (
          <div style={{ ...s.card }}>
            <div style={{ fontSize: 12, color: colors.textMuted }}>{COPY.profile.promiseScoring.loadError}</div>
          </div>
        )}
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
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 12 }}>{COPY.profile.timeline.title}</h2>
        {events.length === 0 && <p style={{ fontSize: 11, color: colors.textMuted }}>{COPY.profile.timeline.empty}</p>}
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
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 4 }}>{COPY.takeAction.title}</h2>
        <p style={{ color: colors.textMuted, fontSize: 11, marginTop: 0, marginBottom: 14 }}>{COPY.takeAction.subtitle}</p>

        {[
          { icon: "phone", label: COPY.takeAction.callLabel, sub: contact.phone || COPY.takeAction.callFallback, color: colors.green, action: contact.phone ? `tel:${contact.phone}` : null },
          { icon: "mail", label: COPY.takeAction.contactFormLabel, sub: COPY.takeAction.contactFormSub, color: colors.blue, action: contact.contact_form || contact.website },
          { icon: "megaphone", label: COPY.takeAction.websiteLabel, sub: contact.website || COPY.takeAction.websiteFallback, color: colors.purple, action: contact.website },
        ].map((m, i) => {
          const cardInner = (
            <div style={{ ...s.card, cursor: m.action ? "pointer" : "not-allowed", display: "flex", alignItems: "center", gap: 12, opacity: m.action ? 1 : 0.5 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: m.color + "22", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <Icon type={m.icon} size={18} color={m.color} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{m.label}</div>
                <div style={{ fontSize: 11, color: colors.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.sub}</div>
              </div>
            </div>
          );
          if (m.action) {
            return (
              <a key={i} href={m.action} target="_blank" rel="noreferrer" aria-label={m.label} style={{ textDecoration: "none", color: "inherit", display: "block" }}>
                {cardInner}
              </a>
            );
          }
          return (
            <div key={i} role="group" aria-disabled="true" aria-label={`${m.label} — not available`} style={{ display: "block" }}>
              {cardInner}
            </div>
          );
        })}

        <div style={s.divider} />

        <div style={s.section}>
          <div style={s.sectionTitle}>{COPY.takeAction.scriptTitle}</div>
          <div style={{ ...s.card, background: colors.accentDim, borderColor: colors.accent + "33" }}>
            <div style={{ fontSize: 12, lineHeight: 1.6 }}>
              {COPY.takeAction.scriptBody(p.name)}
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
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 12 }}>{COPY.contact.title}</h2>
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
                  <button
                    aria-label={COPY.contact.callAria(p.name)}
                    title={`Call ${p.phone}`}
                    style={{ ...s.btn("outline"), padding: "6px", fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center", gap: 4, width: "100%" }}
                  >
                    <Icon type="phone" size={12} /> {COPY.contact.callBtn}
                  </button>
                </a>
              )}
              {p.website && (
                <a href={p.website} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>
                  <button
                    aria-label={COPY.contact.websiteAria(p.name)}
                    title={p.website}
                    style={{ ...s.btn("outline"), padding: "6px", fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center", gap: 4, width: "100%" }}
                  >
                    <Icon type="mail" size={12} /> {COPY.contact.websiteBtn}
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

// 14. EVENT DETAIL
const EventDetailScreen = ({ onNav, event }) => {
  const { data: articleData, loading: articleLoading } = useApi(
    () => api.getEventArticle(event?.title || ""),
    [event?.title],
    { article: null }
  );
  const article = articleData?.article;

  const { data: summaryData, loading: summaryLoading } = useApi(
    () => api.getEventSummary(event || {}),
    [event?.title],
    { summary: null }
  );
  const summary = summaryData?.summary;

  if (!event) {
    return (
      <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
        <StatusBar />
        <div style={s.body}>
          <BackButton onClick={() => onNav(SCREENS.EVENTS)} label={COPY.events.backLabel} />
          <div style={s.card}><div style={{ fontSize: 12, color: colors.textMuted }}>{COPY.events.noEventSelected}</div></div>
        </div>
        <NavBar active={SCREENS.EVENTS} onNav={onNav} />
      </div>
    );
  }

  const chamberColor = event.chamber === "Senate" ? colors.accent : colors.blue;

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={s.header}>
        <BackButton onClick={() => onNav(SCREENS.EVENTS)} label={COPY.events.backLabel} />
        <h1 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 2 }}>{`${event.chamber || ""} ${event.meeting_type || "Meeting"}`.trim()}</h1>
        {event.congress && (
          <p style={s.headerSub}>{event.congress}th Congress</p>
        )}
      </div>
      <div style={{ ...s.body, paddingBottom: 70 }}>

        <div style={{ ...s.card, marginBottom: 10 }}>
          {event.chamber && (
            <div style={{ display: "inline-block", background: chamberColor + "22", color: chamberColor, fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 4, marginBottom: 8, fontFamily: font }}>
              {event.chamber.toUpperCase()}
            </div>
          )}
          <div style={{ fontWeight: 700, fontSize: 14, lineHeight: 1.4 }}>{event.title}</div>
        </div>

        {/* AI Summary */}
        <div style={{ ...s.card, marginBottom: 10, borderLeft: `3px solid ${colors.accent}44` }}>
          <div style={{ fontSize: 10, color: colors.accent, fontWeight: 700, marginBottom: 6, fontFamily: font, letterSpacing: "0.05em" }}>{COPY.events.aiSummaryLabel}</div>
          {summaryLoading && (
            <div style={{ fontSize: 12, color: colors.textMuted }}>{COPY.events.aiSummaryLoading}</div>
          )}
          {!summaryLoading && summary && (
            <div style={{ fontSize: 13, color: colors.text, lineHeight: 1.6 }}>{summary}</div>
          )}
          {!summaryLoading && !summary && (
            <div style={{ fontSize: 12, color: colors.textMuted }}>{COPY.events.aiSummaryEmpty}</div>
          )}
        </div>

        <div style={{ ...s.card, marginBottom: 10 }}>
          <div style={{ fontSize: 11, color: colors.textMuted, fontWeight: 600, marginBottom: 8 }}>{COPY.events.scheduleLabel}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ fontSize: 11, color: colors.textMuted, width: 48, flexShrink: 0 }}>{COPY.events.scheduleDate}</span>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{event.date}</span>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ fontSize: 11, color: colors.textMuted, width: 48, flexShrink: 0 }}>{COPY.events.scheduleTime}</span>
              <span style={{ fontSize: 13 }}>{event.time}</span>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <span style={{ fontSize: 11, color: colors.textMuted, width: 48, flexShrink: 0 }}>{COPY.events.schedulePlace}</span>
              <span style={{ fontSize: 13 }}>{event.location}</span>
            </div>
          </div>
        </div>

        {event.committees?.length > 0 && (
          <div style={{ ...s.card, marginBottom: 10 }}>
            <div style={{ fontSize: 11, color: colors.textMuted, fontWeight: 600, marginBottom: 8 }}>
              {COPY.events.committeesLabel(event.committees.length)}
            </div>
            {event.committees.map((name, i) => (
              <div key={i} style={{ fontSize: 13, color: colors.text, lineHeight: 1.5 }}>{name}</div>
            ))}
          </div>
        )}

        {event.witnesses?.length > 0 && (
          <div style={{ ...s.card, marginBottom: 10 }}>
            <div style={{ fontSize: 11, color: colors.textMuted, fontWeight: 600, marginBottom: 8 }}>{COPY.events.witnessesLabel}</div>
            {event.witnesses.map((w, i) => (
              <div key={i} style={{ marginBottom: i < event.witnesses.length - 1 ? 8 : 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{w.name}</div>
                {w.organization && <div style={{ fontSize: 11, color: colors.textMuted }}>{w.organization}</div>}
              </div>
            ))}
          </div>
        )}

        {/* Bills being considered */}
        {event.bills?.length > 0 && (
          <div style={{ ...s.card, marginBottom: 10 }}>
            <div style={{ fontSize: 11, color: colors.textMuted, fontWeight: 600, marginBottom: 8 }}>{COPY.events.legislationLabel}</div>
            {event.bills.map((b, i) => (
              <a key={i} href={b.url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none", display: "block", marginBottom: i < event.bills.length - 1 ? 10 : 0 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: colors.accent, fontFamily: font, marginBottom: 2 }}>{b.bill}</div>
                <div style={{ fontSize: 12, color: colors.text, lineHeight: 1.4 }}>{b.title}</div>
              </a>
            ))}
          </div>
        )}

        {/* Related news article */}
        <div style={{ ...s.card, marginBottom: 10 }}>
          <div style={{ fontSize: 11, color: colors.textMuted, fontWeight: 600, marginBottom: 8 }}>{COPY.events.newsLabel}</div>
          {articleLoading && <div style={{ fontSize: 12, color: colors.textMuted }}>{COPY.events.newsLoading}</div>}
          {!articleLoading && !article && (
            <div style={{ fontSize: 12, color: colors.textMuted }}>{COPY.events.newsEmpty}</div>
          )}
          {!articleLoading && article && (
            <a href={article.url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: "none", display: "block" }}>
              <div style={{ fontSize: 10, color: colors.textMuted, marginBottom: 4 }}>
                {article.section}{article.date ? ` · ${article.date}` : ""}
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, color: colors.accent, lineHeight: 1.4, marginBottom: article.snippet ? 4 : 0 }}>
                {article.title}
              </div>
              {article.snippet && (
                <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.4 }}
                  dangerouslySetInnerHTML={{ __html: article.snippet }} />
              )}
            </a>
          )}
        </div>

      </div>
      <NavBar active={SCREENS.EVENTS} onNav={onNav} />
    </div>
  );
};

// 14b. EVENTS
const EventsScreen = ({ onNav, userState, onSelectEvent }) => {
  const { data, loading, error, offline, reload } = useApi(
    () => api.getEvents(userState),
    [userState],
    { events: SAMPLE.events, count: SAMPLE.events.length, state: userState }
  );

  const events = data?.events || [];
  const typeColors = { town_hall: colors.purple, council: colors.blue, registration: colors.green, hearing: colors.yellow };

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={s.header}>
        <h1 style={{ ...s.headerTitle, fontSize: 18 }}>{COPY.events.listTitle}</h1>
        <p style={s.headerSub}>{COPY.events.listSubtitle}</p>
      </div>
      <div style={{ ...s.body, paddingBottom: 70 }}>
        {offline && (
          <div style={{ ...s.card, background: colors.yellowDim, borderColor: colors.yellow + "44", marginBottom: 14 }}>
            <div style={{ fontSize: 11, color: colors.yellow, fontWeight: 600, marginBottom: 4 }}>{COPY.events.offlineBadge}</div>
            <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.4 }}>
              {COPY.events.offlineBody}
            </div>
          </div>
        )}
        {loading && <ListRowSkeleton count={5} leading="square" />}
        {error && <ErrorBanner error={error} onRetry={reload} />}
        {!loading && !error && events.length === 0 && (
          <div style={s.card}>
            <div style={{ fontSize: 12, color: colors.textMuted }}>{COPY.events.emptyList}</div>
          </div>
        )}
        {!loading && !error && events.map((ev, i) => (
          <FadeIn key={ev.id} delay={Math.min(i * 70, 630)}>
            <button
              type="button"
              onClick={() => onSelectEvent?.(ev)}
              style={{
                ...s.card,
                cursor: "pointer",
                width: "100%",
                textAlign: "left",
                font: "inherit",
                color: "inherit",
              }}
            >
              <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                <div style={{ width: 44, minHeight: 44, borderRadius: 8, background: (typeColors[ev.type] || colors.accent) + "22", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flexShrink: 0, padding: "4px 0" }}>
                  <div style={{ fontSize: 14, fontWeight: 800, fontFamily: font, color: typeColors[ev.type] || colors.accent }}>{(ev.date?.split(" ")?.[1] ?? "").replace(",", "")}</div>
                  <div style={{ fontSize: 9, fontFamily: font, color: typeColors[ev.type] || colors.accent }}>{ev.date?.split(" ")?.[0] ?? ""}</div>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontWeight: 600, fontSize: 13, marginBottom: 2,
                    display: "-webkit-box", WebkitBoxOrient: "vertical",
                    WebkitLineClamp: 3, overflow: "hidden", lineHeight: 1.35,
                    wordBreak: "break-word",
                  }}>{ev.title}</div>
                  <div style={{ fontSize: 11, color: colors.textMuted }}>{ev.time} · {ev.location}</div>
                </div>
              </div>
            </button>
          </FadeIn>
        ))}
      </div>
      <NavBar active={SCREENS.EVENTS} onNav={onNav} />
    </div>
  );
};

// 15. LEARN TO VOTE
const LearnToVoteScreen = ({ onNav, userState }) => {
  const stateKey = (userState || "").toUpperCase();
  const guide = STATE_VOTING_GUIDE[stateKey];
  const stateLabel = guide?.name || stateKey || "—";
  const rows = COPY.learnToVote.rows;

  const stateFacts = guide && [
    { label: rows.deadline, value: guide.registrationDeadline },
    { label: rows.id, value: guide.idRequired },
    { label: rows.hours, value: guide.pollingHours },
  ];

  const stateLinks = guide && [
    { label: rows.register, url: guide.registerUrl },
    { label: rows.polling, url: guide.pollingPlaceUrl },
    { label: rows.official, url: guide.officialUrl },
  ];

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.DASHBOARD)} label="Dashboard" />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 12 }}>{COPY.learnToVote.title}</h2>

        <div style={s.section}>
          <div style={s.sectionTitle}>{COPY.learnToVote.yourStateTitle(stateLabel)}</div>
          {guide ? (
            <>
              <div style={{ ...s.card, marginBottom: 8 }}>
                {stateFacts.map((row, i) => (
                  <div
                    key={row.label}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 2,
                      paddingTop: i === 0 ? 0 : 10,
                      paddingBottom: i === stateFacts.length - 1 ? 0 : 10,
                      borderBottom: i < stateFacts.length - 1 ? `1px solid ${colors.border}` : "none",
                    }}
                  >
                    <span style={{ fontSize: 11, color: colors.textMuted, fontWeight: 600 }}>{row.label}</span>
                    <span style={{ fontSize: 13, lineHeight: 1.4 }}>{row.value}</span>
                  </div>
                ))}
              </div>
              {stateLinks.map((r) => (
                <a key={r.url} href={r.url} target="_blank" rel="noreferrer" style={{ textDecoration: "none", color: "inherit" }}>
                  <div style={{ ...s.card, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ fontSize: 13 }}>{r.label}</span>
                    <span style={{ color: colors.textMuted, transform: "rotate(180deg)", display: "inline-block" }}>
                      <Icon type="back" size={14} />
                    </span>
                  </div>
                </a>
              ))}
              <p style={{ fontSize: 10, color: colors.textMuted, marginTop: 8 }}>
                {COPY.learnToVote.sourceNote}
              </p>
            </>
          ) : (
            <div style={s.card}>
              <div style={{ fontSize: 12, lineHeight: 1.5 }}>{COPY.learnToVote.genericNote}</div>
            </div>
          )}
        </div>

        <div style={s.section}>
          <div style={s.sectionTitle}>{COPY.learnToVote.resourcesTitle}</div>
          {COPY.learnToVote.resources.map((r) => (
            <a key={r.url} href={r.url} target="_blank" rel="noreferrer" style={{ textDecoration: "none", color: "inherit" }}>
              <div style={{ ...s.card, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontSize: 13 }}>{r.label}</span>
                <span style={{ color: colors.textMuted, transform: "rotate(180deg)", display: "inline-block" }}>
                  <Icon type="back" size={14} />
                </span>
              </div>
            </a>
          ))}
        </div>
      </div>
      <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
    </div>
  );
};

// 16. ALERTS - Wired to backend
const AlertsScreen = ({ onNav, onSelectPolitician }) => {
  const [alerts, setAlerts] = useState(null);
  const [error, setError] = useState(null);
  const [urgentOnly, setUrgentOnly] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setAlerts(null);
    setError(null);
    api
      .getAlerts({ urgentOnly })
      .then((data) => {
        if (!cancelled) setAlerts(data.alerts || []);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e.message || "Failed to load alerts");
          setAlerts(SAMPLE.alerts); // graceful fallback to existing sample
        }
      });
    return () => {
      cancelled = true;
    };
  }, [urgentOnly]);

  const isReal = alerts && !error;

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={s.header}>
        <h1 style={{ ...s.headerTitle, fontSize: 18 }}>{COPY.alerts.title}</h1>
        <p style={s.headerSub}>{COPY.alerts.subtitle}</p>
      </div>
      <div style={{ ...s.body, paddingBottom: 70 }}>
        {/* Filter toggle */}
        <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
          <button
            style={s.chip(!urgentOnly)}
            onClick={() => setUrgentOnly(false)}
          >
            {COPY.alerts.chipAll}
          </button>
          <button
            style={s.chip(urgentOnly)}
            onClick={() => setUrgentOnly(true)}
          >
            {COPY.alerts.chipUrgent}
          </button>
        </div>

        {error && (
          <div style={{ ...s.card, background: colors.yellowDim, borderColor: colors.yellow + "44", marginBottom: 14 }}>
            <div style={{ fontSize: 11, color: colors.yellow, fontWeight: 600, marginBottom: 4 }}>
              {COPY.alerts.offlineBadge}
            </div>
            <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.4 }}>
              {error}
            </div>
          </div>
        )}

        {alerts === null && <Loading label={COPY.alerts.loading} />}

        {alerts && alerts.length === 0 && (
          <div style={s.card}>
            <div style={{ fontSize: 13 }}>
              {COPY.alerts.emptyHint}{" "}
              <code style={{ fontFamily: font, color: colors.accent }}>
                python -m backend.alerts.pipeline
              </code>
            </div>
          </div>
        )}

        {alerts && groupAlerts(alerts).map((a, idx) => {
          // Real alerts have richer shape than SAMPLE.alerts
          const isUrgent = a.urgent !== undefined ? a.urgent : (a.score ?? 0) > 0.6;
          const headline = a.headline || a.text;
          const time = a.time || "recently";
          const bills = a.bills || [];
          const grouped = (a.groupSize || 1) > 1;
          return (
            <FadeIn key={a.id} delay={Math.min(idx * 70, 630)}>
            <div
              style={{
                ...s.card,
                borderColor: isUrgent ? colors.red + "44" : colors.border,
                background: isUrgent ? colors.redDim : colors.surface,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                {isUrgent && <span style={s.badge("red")}>{COPY.alerts.urgentBadge}</span>}
                <span style={{ fontSize: 10, color: colors.textMuted, fontFamily: font, marginLeft: "auto" }}>
                  {time}
                </span>
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, lineHeight: 1.35 }}>
                {headline}
              </div>
              {grouped ? (
                <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.45, marginBottom: 8 }}>
                  <div style={{ marginBottom: 6 }}>
                    {a.groupSize} upcoming {friendlyCategoryInline(a.vote?.category)} bills
                    {a.donation?.amount ? ` · $${Number(a.donation.amount).toLocaleString()} lifetime` : ""}
                  </div>
                  {bills.slice(0, 3).map((v, i) => (
                    <div key={i} style={{ marginLeft: 2, marginBottom: 2 }}>
                      ▸ <span style={{ fontFamily: font }}>{v.bill_number}</span>
                      {v.title ? `  ${v.title.length > 60 ? v.title.slice(0, 57) + "…" : v.title}` : ""}
                    </div>
                  ))}
                  {bills.length > 3 && (
                    <div style={{ marginLeft: 2, marginTop: 2, fontStyle: "italic" }}>
                      {COPY.alerts.moreBills(bills.length - 3)}
                    </div>
                  )}
                </div>
              ) : (
                a.body && (
                  <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.45, marginBottom: 8 }}>
                    {a.body}
                  </div>
                )
              )}
              {isReal && a.score !== undefined && (
                <div style={{ fontSize: 10, color: colors.textMuted, fontFamily: font }}>
                  score: {a.score.toFixed(2)} {a.signals?.T !== undefined && (
                    <span style={{ marginLeft: 8 }}>
                      T={a.signals.T.toFixed(2)} V={a.signals.V.toFixed(2)} D={a.signals.D.toFixed(2)} R={a.signals.R.toFixed(2)} A={a.signals.A.toFixed(2)} N={a.signals.N.toFixed(2)}
                    </span>
                  )}
                </div>
              )}
              {a.bioguide_id && onSelectPolitician && (
                <button
                  style={{ ...s.btn("outline"), padding: "6px 10px", fontSize: 11, marginTop: 10, width: "auto" }}
                  onClick={() => onSelectPolitician(a.bioguide_id)}
                >
                  {COPY.alerts.viewRepButton}
                </button>
              )}
            </div>
            </FadeIn>
          );
        })}
      </div>
      <NavBar active={SCREENS.ALERTS} onNav={onNav} />
    </div>
  );
}

// 17. SETTINGS
const SettingsScreen = ({ onNav, userState, onSaveState, currentUser, userIssues, onSaveIssues, onSignOut, onDeleteAccount }) => {
  const [editState, setEditState] = useState(userState || "CT");
  const [backendStatus, setBackendStatus] = useState(null);
  const [saveStatus, setSaveStatus] = useState(null);
  // Issues editor — seeds from the userIssues prop (already filtered to keys),
  // ignoring legacy display-string values that don't match a category key.
  const [selectedIssues, setSelectedIssues] = useState(
    () => (userIssues || []).filter((k) => COPY.categories[k])
  );
  const [issuesStatus, setIssuesStatus] = useState(null);
  const ISSUES_MAX = 5;
  const atMaxIssues = selectedIssues.length >= ISSUES_MAX;
  const toggleIssue = (key) => {
    setIssuesStatus(null);
    if (selectedIssues.includes(key)) {
      setSelectedIssues(selectedIssues.filter((k) => k !== key));
    } else if (!atMaxIssues) {
      setSelectedIssues([...selectedIssues, key]);
    }
  };
  const saveIssues = async () => {
    setIssuesStatus({ saving: true });
    try {
      await onSaveIssues(selectedIssues);
      setIssuesStatus({ ok: true, msg: COPY.settings.issuesSaved });
    } catch (e) {
      setIssuesStatus({ ok: false, msg: e.detail || e.message || COPY.settings.issuesSaveError });
    }
  };

  useEffect(() => {
    api.health()
      .then((d) => setBackendStatus({ ok: true, data: d }))
      .catch((e) => setBackendStatus({ ok: false, error: e.message }));
  }, []);

  const save = async () => {
    if (editState.length !== 2) {
      setSaveStatus({ ok: false, msg: "Use a 2-letter state code" });
      return;
    }
    setSaveStatus({ saving: true });
    try {
      await onSaveState(editState);
      setSaveStatus({ ok: true, msg: "Saved" });
    } catch (e) {
      setSaveStatus({ ok: false, msg: e.detail || e.message || "Could not save" });
    }
  };

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={s.header}>
        <h1 style={{ ...s.headerTitle, fontSize: 18 }}>Settings</h1>
      </div>
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <div style={s.section}>
          <div style={s.sectionTitle}>Account</div>
          {currentUser?.is_guest ? (
            <div style={s.card}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>Browsing as guest</div>
              <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 2, lineHeight: 1.4 }}>
                Your state + issues are saved on this device only. Sign up to chat with Mamu and persist your preferences.
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <button style={{ ...s.btn("primary"), flex: 1 }} onClick={() => onNav(SCREENS.CREATE_ACCOUNT)}>Sign Up</button>
                <button style={{ ...s.btn("outline"), flex: 1 }} onClick={() => onNav(SCREENS.LOGIN)}>Log In</button>
              </div>
              <button style={{ ...s.btn("outline"), marginTop: 8 }} onClick={onSignOut}>Exit guest mode</button>
            </div>
          ) : currentUser ? (
            <div style={s.card}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>{currentUser.name}</div>
              <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 2 }}>{currentUser.email}</div>
              <button style={{ ...s.btn("outline"), marginTop: 12 }} onClick={onSignOut}>Sign Out</button>
              <button
                style={{ ...s.btn("outline"), marginTop: 8, borderColor: colors.red, color: colors.red }}
                onClick={onDeleteAccount}
              >
                Delete Account
              </button>
            </div>
          ) : (
            <div style={s.card}>
              <div style={{ fontSize: 12, color: colors.textMuted, marginBottom: 10 }}>You're not signed in. Sign in to save your state and issue preferences.</div>
              <div style={{ display: "flex", gap: 8 }}>
                <button style={{ ...s.btn("primary"), flex: 1 }} onClick={() => onNav(SCREENS.LOGIN)}>Log In</button>
                <button style={{ ...s.btn("outline"), flex: 1 }} onClick={() => onNav(SCREENS.CREATE_ACCOUNT)}>Sign Up</button>
              </div>
            </div>
          )}
        </div>

        <div style={s.section}>
          <div style={s.sectionTitle}>Location</div>
          <div style={s.card}>
            <label style={{ fontSize: 11, color: colors.textMuted, display: "block", marginBottom: 4 }}>Your State (2-letter)</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input style={{ ...s.input, flex: 1 }} value={editState} onChange={(e) => { setEditState(e.target.value.toUpperCase().slice(0, 2)); setSaveStatus(null); }} maxLength={2} />
              <button style={{ ...s.btn("primary"), width: "auto", padding: "10px 16px", opacity: saveStatus?.saving ? 0.6 : 1 }} disabled={saveStatus?.saving} onClick={save}>
                {saveStatus?.saving ? "..." : "Save"}
              </button>
            </div>
            {saveStatus && !saveStatus.saving && (
              <div style={{ fontSize: 11, marginTop: 6, color: saveStatus.ok ? colors.green : colors.red }}>
                {saveStatus.msg}
              </div>
            )}
          </div>
        </div>

        <div style={s.section}>
          <div style={s.sectionTitle}>{COPY.settings.issuesTitle}</div>
          <div style={s.card}>
            <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans, marginBottom: 10 }}>
              {COPY.settings.issuesHint}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
              {Object.keys(COPY.categories).map((key) => (
                <button key={key} style={s.chip(selectedIssues.includes(key))} onClick={() => toggleIssue(key)}>
                  {friendlyCategory(key)}
                </button>
              ))}
            </div>
            <div style={{ fontSize: 11, color: atMaxIssues ? colors.accent : colors.textMuted, marginBottom: 10 }}>
              {COPY.settings.issuesCounter(selectedIssues.length, ISSUES_MAX)}
            </div>
            {issuesStatus && !issuesStatus.saving && (
              <div style={{ fontSize: 11, marginBottom: 8, color: issuesStatus.ok ? colors.green : colors.red }}>
                {issuesStatus.msg}
              </div>
            )}
            <button
              style={{ ...s.btn("primary"), opacity: issuesStatus?.saving ? 0.6 : 1 }}
              disabled={issuesStatus?.saving}
              onClick={saveIssues}
            >
              {issuesStatus?.saving ? COPY.settings.issuesSaving : "Save"}
            </button>
          </div>
        </div>

        {!isPWA() && (
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
        )}

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
// STATE LEGISLATORS (Legiscan)
// ============================================================

const StateRepsScreen = ({ onNav, userState, onSelectStateRep }) => {
  const { data, loading, error, offline, reload } = useApi(
    () => api.getStateRepsByState(userState || "CT"),
    [userState],
    { representatives: SAMPLE.stateReps, state: userState || "CT", count: SAMPLE.stateReps.length, source: "sample" }
  );

  const reps = data?.representatives || [];
  const source = data?.source || "sample";

  const senate = reps.filter((r) => r.chamber === "Senate");
  const house = reps.filter((r) => r.chamber === "House");
  const other = reps.filter((r) => r.chamber !== "Senate" && r.chamber !== "House");

  const renderCard = (r, i) => (
    <FadeIn key={r.people_id} delay={Math.min(i * 55, 495)}>
      <div
        style={{ ...s.card, display: "flex", alignItems: "center", gap: 12, marginBottom: 8, cursor: "pointer" }}
        onClick={() => onSelectStateRep?.(r.people_id)}
      >
        <Avatar name={r.name} size={36} party={r.party} />
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontWeight: 600, fontSize: 13 }}>{r.name}</span>
            <PartyBadge party={r.party} />
          </div>
          <div style={{ fontSize: 11, color: colors.textMuted }}>
            {r.chamber || r.role} · {r.district}
          </div>
        </div>
        <span style={{ color: colors.textMuted, transform: "rotate(180deg)", display: "inline-block" }}>
          <Icon type="back" size={14} />
        </span>
      </div>
    </FadeIn>
  );

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={s.header}>
        <h1 style={{ ...s.headerTitle, fontSize: 18 }}>State Legislators</h1>
        <p style={s.headerSub}>
          {userState || "CT"} · {reps.length} members
          {source === "sample" && " · sample data"}
        </p>
      </div>
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.DASHBOARD)} label="Dashboard" />
        {loading && <ListRowSkeleton count={6} leading="circle" />}
        {error && <ErrorBanner error={error} onRetry={reload} />}
        {!loading && !error && reps.length === 0 && (
          <div style={{ ...s.card, textAlign: "center" }}>
            <div style={{ fontSize: 12, color: colors.textMuted }}>
              No state legislators found for {userState}. Set LEGISCAN_API_KEY in the backend .env to pull real data.
            </div>
          </div>
        )}
        {!loading && !error && senate.length > 0 && (
          <div style={s.section}>
            <div style={s.sectionTitle}>State Senate ({senate.length})</div>
            {senate.map(renderCard)}
          </div>
        )}
        {!loading && !error && house.length > 0 && (
          <div style={s.section}>
            <div style={s.sectionTitle}>State House ({house.length})</div>
            {house.map(renderCard)}
          </div>
        )}
        {!loading && !error && other.length > 0 && (
          <div style={s.section}>
            <div style={s.sectionTitle}>Other ({other.length})</div>
            {other.map(renderCard)}
          </div>
        )}
      </div>
      <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
    </div>
  );
};

// ------------------------------------------------------------
// STATE LEGISLATOR DETAIL — mirrors federal profile flow
// ------------------------------------------------------------

const StateRepProfileScreen = ({ onNav, peopleId, onSetStateRepData }) => {
  const { data, loading, error, offline, reload } = useApi(
    () => peopleId ? api.getStateRep(peopleId) : Promise.resolve(null),
    [peopleId],
    null
  );

  useEffect(() => {
    if (data) onSetStateRepData(data);
  }, [data, onSetStateRepData]);

  if (!peopleId) {
    return (
      <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
        <StatusBar />
        <div style={{ ...s.body }}>
          <BackButton onClick={() => onNav(SCREENS.STATE_REPS)} label="State Reps" />
          <div style={{ ...s.card }}>
            <div style={{ fontSize: 12, color: colors.textMuted }}>
              Pick a state legislator from the State Reps screen first.
            </div>
          </div>
        </div>
        <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
        <StatusBar offline={offline} />
        <div style={{ ...s.body, paddingBottom: 70 }}>
          <BackButton onClick={() => onNav(SCREENS.STATE_REPS)} label="State Reps" />
          <ProfileSkeleton scoreCount={2} tileCount={4} />
        </div>
        <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
        <StatusBar offline={offline} />
        <div style={{ ...s.body }}>
          <BackButton onClick={() => onNav(SCREENS.STATE_REPS)} label="State Reps" />
          <ErrorBanner error={error || "Legislator not found"} onRetry={reload} />
        </div>
        <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
      </div>
    );
  }

  const sponsoredCount = (data.sponsored_bills || []).length;

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.STATE_REPS)} label="State Reps" />
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 16 }}>
          <Avatar name={data.name} size={56} party={data.party} />
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>{data.name}</h2>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
              <PartyBadge party={data.party} />
              <span style={{ fontSize: 12, color: colors.textMuted }}>
                {data.chamber || data.role} · {data.district}
              </span>
            </div>
            <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 2 }}>
              {data.state} State Legislature
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
          <div style={{ ...s.card, textAlign: "center", marginBottom: 0 }}>
            <div style={{ fontSize: 22, fontWeight: 800, fontFamily: font, color: colors.accent }}>
              {sponsoredCount}
            </div>
            <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans, marginTop: 2 }}>Sponsored bills</div>
          </div>
          <div style={{ ...s.card, textAlign: "center", marginBottom: 0 }}>
            <div style={{ fontSize: 22, fontWeight: 800, fontFamily: font, color: colors.blue }}>
              {data.chamber || "—"}
            </div>
            <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: fontSans, marginTop: 2 }}>Chamber</div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {[
            { icon: "vote",      ...COPY.stateProfile.tiles.voting,   screen: SCREENS.STATE_REP_VOTING },
            { icon: "star",      ...COPY.stateProfile.tiles.stances,  screen: SCREENS.STATE_REP_STANCES },
            { icon: "megaphone", ...COPY.stateProfile.tiles.promises, screen: SCREENS.STATE_REP_PROMISES },
            { icon: "alert",     ...COPY.stateProfile.tiles.alerts,   screen: SCREENS.STATE_REP_ALERTS },
          ].map((item) => (
            <div
              key={item.label}
              style={{ ...s.card, cursor: "pointer", display: "flex", alignItems: "center", gap: 12, marginBottom: 0 }}
              onClick={() => onNav(item.screen)}
            >
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

        {sponsoredCount > 0 && (
          <div style={s.section}>
            <div style={s.sectionTitle}>{COPY.stateProfile.recentSponsored}</div>
            {(data.sponsored_bills || []).slice(0, 5).map((b, i) => (
              <div key={i} style={{ padding: "8px 0", borderBottom: `1px solid ${colors.border}` }}>
                <div style={{ fontSize: 12, fontWeight: 600 }}>{b.number}</div>
                <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.4 }}>{b.title}</div>
                {b.status && <span style={s.badge("blue")}>{b.status}</span>}
              </div>
            ))}
          </div>
        )}
      </div>
      <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
    </div>
  );
};

const StateRepVotingScreen = ({ onNav, peopleId, stateRepData }) => {
  const name = stateRepData?.name || "State Legislator";
  const { data, loading, offline } = useApi(
    () => peopleId ? api.getStateRepVotes(peopleId) : Promise.resolve(null),
    [peopleId],
    null
  );

  const votes = data?.votes || [];
  const [filter, setFilter] = useState("all");
  const cats = ["all", ...new Set(votes.map((v) => v.category).filter(Boolean))];
  const filtered = filter === "all" ? votes : votes.filter((v) => v.category === filter);

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.STATE_REP_PROFILE)} label={name} />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 4 }}>{COPY.stateProfile.voting.title}</h2>
        <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 12 }}>
          {COPY.stateProfile.voting.subtitle}
        </div>

        {loading && <Loading label={COPY.stateProfile.voting.loading} />}

        {!loading && cats.length > 1 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            {cats.map((c) => (
              <button key={c} style={s.chip(filter === c)} onClick={() => setFilter(c)}>
                {c === "all" ? COPY.profile.votingHistory.chipAll : friendlyCategory(c)}
              </button>
            ))}
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <div style={{ ...s.card }}>
            <div style={{ fontSize: 12, color: colors.textMuted, lineHeight: 1.5 }}>
              {COPY.stateProfile.voting.empty}
            </div>
          </div>
        )}

        {!loading && filtered.map((v, i) => (
          <div key={i} style={{ display: "flex", gap: 12, marginBottom: 12, position: "relative", paddingLeft: 16 }}>
            <div style={{ position: "absolute", left: 0, top: 6, width: 8, height: 8, borderRadius: "50%", background: v.member_vote === "Yea" ? colors.green : colors.red }} />
            {i < filtered.length - 1 && <div style={{ position: "absolute", left: 3.5, top: 16, width: 1, height: "calc(100% + 4px)", background: colors.border }} />}
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={s.badge(v.member_vote === "Yea" ? "green" : "red")}>{(v.member_vote || "?").toUpperCase()}</span>
                <span style={{ fontSize: 10, color: colors.textMuted, fontFamily: font }}>{v.date}</span>
              </div>
              <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>{v.title}</div>
              {v.category && <div style={{ fontSize: 11, color: colors.textMuted }}>{friendlyCategoryInline(v.category)}</div>}
            </div>
          </div>
        ))}
      </div>
      <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
    </div>
  );
};

const StateRepStancesScreen = ({ onNav, peopleId, stateRepData }) => {
  const name = stateRepData?.name || "State Legislator";
  const { data, loading, offline } = useApi(
    () => peopleId ? api.getStateRepStances(peopleId) : Promise.resolve(null),
    [peopleId],
    null
  );

  const stances = data?.stances || null;
  const aiAvailable = data?.ai_available ?? true;

  const renderStanceCard = (stance, i) => {
    const score = stance.score || "PENDING";
    const st = SCORE_STYLE[score] || SCORE_STYLE.PENDING;
    return (
      <div key={i} style={{ ...s.card, marginBottom: 10, borderColor: st.border, background: st.bg }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <div style={{ fontWeight: 700, fontSize: 13 }}>{stance.topic}</div>
          <div style={{
            fontSize: 9, fontWeight: 700, fontFamily: font, letterSpacing: 0.8,
            color: st.color, background: colors.surface,
            border: `1px solid ${st.border}`, borderRadius: 4, padding: "2px 6px",
          }}>{score}</div>
        </div>
        <div style={{ fontSize: 12, lineHeight: 1.5, marginBottom: 6 }}>{stance.stance}</div>
        {stance.evidence && (
          <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.4, borderTop: `1px solid ${colors.border}`, paddingTop: 6 }}>
            {stance.evidence}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.STATE_REP_PROFILE)} label={name} />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 4 }}>{COPY.stateProfile.stances.title}</h2>
        <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 14 }}>
          {COPY.stateProfile.stances.subtitle}
        </div>

        {loading && <Loading label={COPY.stateProfile.stances.loading} />}

        {!loading && !aiAvailable && (
          <div style={{ ...s.card, background: colors.yellowDim, borderColor: colors.yellow + "44" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: colors.yellow, marginBottom: 6 }}>{COPY.stateProfile.stances.aiKeyMissingTitle}</div>
            <div style={{ fontSize: 12, lineHeight: 1.5 }}>{COPY.stateProfile.stances.aiKeyMissingBody}</div>
          </div>
        )}

        {!loading && aiAvailable && stances && stances.length > 0 && (
          <>
            <div style={s.sectionTitle}>{COPY.stateProfile.stances.keyPositions(stances.length)}</div>
            {stances.map(renderStanceCard)}
            <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 8, lineHeight: 1.5 }}>
              {COPY.stateProfile.stances.scoresNote}
            </div>
          </>
        )}

        {!loading && aiAvailable && (!stances || stances.length === 0) && (
          <div style={{ ...s.card }}>
            <div style={{ fontSize: 12, color: colors.textMuted }}>
              {COPY.stateProfile.stances.notEnoughData}
            </div>
          </div>
        )}
      </div>
      <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
    </div>
  );
};

const StateRepPromisesScreen = ({ onNav, peopleId, stateRepData }) => {
  const name = stateRepData?.name || "State Legislator";
  const { data, loading, offline } = useApi(
    () => peopleId ? api.getStateRepPromises(peopleId) : Promise.resolve(null),
    [peopleId],
    null
  );

  const promises = data?.promises || null;
  const aiAvailable = data?.ai_available ?? true;
  const scraped = data?.scraped ?? false;
  const sourceUrl = data?.source_url || "";
  const sourceRung = data?.source_rung || null;
  const sourceChip = (() => {
    if (sourceRung === "primary" && /ballotpedia\.org/i.test(sourceUrl)) {
      return { label: "Official bio (Ballotpedia)", color: colors.blue };
    }
    return PROMISE_RUNG_STYLE[sourceRung] || null;
  })();

  const renderPromiseCard = (promise, i) => {
    const status = promise.status || "UNCLEAR";
    const st = PROMISE_STYLE[status] || PROMISE_STYLE.UNCLEAR;
    return (
      <div key={i} style={{ ...s.card, marginBottom: 10, borderColor: st.border, background: st.bg }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
          <div style={{ fontWeight: 700, fontSize: 13 }}>{promise.topic}</div>
          <div style={{
            fontSize: 9, fontWeight: 700, fontFamily: font, letterSpacing: 0.8,
            color: st.color, background: colors.surface,
            border: `1px solid ${st.border}`, borderRadius: 4, padding: "2px 6px",
          }}>{status}</div>
        </div>
        <div style={{ fontSize: 12, lineHeight: 1.5, marginBottom: 6 }}>{promise.promise}</div>
        {promise.evidence && (
          <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.4, borderTop: `1px solid ${colors.border}`, paddingTop: 6 }}>
            {promise.evidence}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar offline={offline} />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.STATE_REP_PROFILE)} label={name} />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 4 }}>{COPY.stateProfile.promises.title}</h2>
        <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 14 }}>
          {COPY.stateProfile.promises.subtitle}
        </div>

        {loading && <Loading label={COPY.stateProfile.promises.loading} />}

        {!loading && !aiAvailable && (
          <div style={{ ...s.card, background: colors.yellowDim, borderColor: colors.yellow + "44" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: colors.yellow, marginBottom: 6 }}>{COPY.stateProfile.promises.aiKeyMissingTitle}</div>
            <div style={{ fontSize: 12, lineHeight: 1.5 }}>{COPY.stateProfile.promises.aiKeyMissingBody}</div>
          </div>
        )}

        {!loading && aiAvailable && !scraped && (
          <div style={{ ...s.card }}>
            <div style={{ fontSize: 12, color: colors.textMuted, lineHeight: 1.5 }}>
              {COPY.stateProfile.promises.notScraped}
            </div>
          </div>
        )}

        {!loading && aiAvailable && scraped && promises && promises.length > 0 && (
          <>
            {promises.map(renderPromiseCard)}
            {sourceUrl && (
              <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 8, lineHeight: 1.5, display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                {sourceChip && (
                  <span style={{
                    fontSize: 9, fontWeight: 700, fontFamily: font, letterSpacing: 0.5,
                    color: sourceChip.color,
                    background: colors.surface,
                    border: `1px solid ${sourceChip.color}66`,
                    borderRadius: 4, padding: "2px 6px",
                  }}>{sourceChip.label}</span>
                )}
                <span>
                  {COPY.stateProfile.promises.sourceNotePre}
                  <a href={sourceUrl} target="_blank" rel="noreferrer" style={{ color: colors.accent }}>
                    {sourceUrl.replace(/^https?:\/\//, "")}
                  </a>
                  {COPY.stateProfile.promises.sourceNotePost}
                </span>
              </div>
            )}
          </>
        )}

        {!loading && aiAvailable && scraped && (!promises || promises.length === 0) && (
          <div style={{ ...s.card }}>
            <div style={{ fontSize: 12, color: colors.textMuted }}>
              {COPY.stateProfile.promises.empty}
            </div>
          </div>
        )}
      </div>
      <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
    </div>
  );
};

const StateRepAlertsScreen = ({ onNav, peopleId, stateRepData }) => {
  const name = stateRepData?.name || COPY.alerts.stateFallbackName;
  const [alerts, setAlerts] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!peopleId) return;
    let cancelled = false;
    setAlerts(null);
    setError(null);
    api.getAlertsForStateRep(peopleId)
      .then((data) => { if (!cancelled) setAlerts(data.alerts || []); })
      .catch((e) => {
        if (!cancelled) {
          setError(e.detail || e.message || "Failed to load alerts");
          setAlerts(SAMPLE.stateAlerts);
        }
      });
    return () => { cancelled = true; };
  }, [peopleId]);

  const isReal = alerts && !error;
  const fmtMoney = (n) => `$${(Number(n) || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

  return (
    <div style={{ ...s.phone, display: "flex", flexDirection: "column" }}>
      <StatusBar />
      <div style={{ ...s.body, paddingBottom: 70 }}>
        <BackButton onClick={() => onNav(SCREENS.STATE_REP_PROFILE)} label={name} />
        <h2 style={{ ...s.headerTitle, fontSize: 16, marginBottom: 4 }}>{COPY.alerts.title}</h2>
        <div style={{ fontSize: 11, color: colors.textMuted, marginBottom: 14 }}>
          {COPY.alerts.stateSubtitle}
        </div>

        {error && (
          <div style={{ ...s.card, background: colors.yellowDim, borderColor: colors.yellow + "44", marginBottom: 14 }}>
            <div style={{ fontSize: 11, color: colors.yellow, fontWeight: 600, marginBottom: 4 }}>
              {COPY.alerts.offlineBadge}
            </div>
            <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.4 }}>{error}</div>
          </div>
        )}

        {alerts === null && <Loading label={COPY.alerts.stateLoading} />}

        {alerts && alerts.length === 0 && !error && (
          <div style={s.card}>
            <div style={{ fontSize: 13 }}>{COPY.alerts.stateEmptyTitle}</div>
            <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 6, lineHeight: 1.5 }}>
              {COPY.alerts.stateEmptyHint}{" "}
              <code style={{ fontFamily: font, color: colors.accent }}>
                python -m backend.alerts.ingest_ftm --state {stateRepData?.state || "CT"}
              </code>{" "}
              then{" "}
              <code style={{ fontFamily: font, color: colors.accent }}>
                python -m backend.alerts.ingest_state_votes --state {stateRepData?.state || "CT"}
              </code>{" "}
              and{" "}
              <code style={{ fontFamily: font, color: colors.accent }}>
                python -m backend.alerts.pipeline
              </code>
              .
            </div>
          </div>
        )}

        {alerts && groupAlerts(alerts).map((a) => {
          const bills = a.bills || [];
          const grouped = (a.groupSize || 1) > 1;
          return (
          <div
            key={a.id}
            style={{
              ...s.card,
              borderColor: a.urgent ? colors.red + "44" : colors.border,
              background: a.urgent ? colors.redDim : colors.surface,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
              {a.urgent && <span style={s.badge("red")}>{COPY.alerts.urgentBadge}</span>}
              <span style={{ fontSize: 10, color: colors.textMuted, fontFamily: font, marginLeft: "auto" }}>
                {a.time || "recently"}
              </span>
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, lineHeight: 1.35 }}>
              {a.headline}
            </div>
            {grouped ? (
              <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.45, marginBottom: 8 }}>
                <div style={{ marginBottom: 6 }}>
                  {a.groupSize} upcoming {friendlyCategoryInline(a.vote?.category)} bills
                  {a.donation?.amount ? ` · ${fmtMoney(a.donation.amount)} lifetime` : ""}
                </div>
                {bills.slice(0, 3).map((v, i) => (
                  <div key={i} style={{ marginLeft: 2, marginBottom: 2 }}>
                    ▸ <span style={{ fontFamily: font }}>{v.bill_number}</span>
                    {v.title ? `  ${v.title.length > 60 ? v.title.slice(0, 57) + "…" : v.title}` : ""}
                  </div>
                ))}
                {bills.length > 3 && (
                  <div style={{ marginLeft: 2, marginTop: 2, fontStyle: "italic" }}>
                    {COPY.alerts.moreBills(bills.length - 3)}
                  </div>
                )}
              </div>
            ) : (
              <>
                {a.body && (
                  <div style={{ fontSize: 11, color: colors.textMuted, lineHeight: 1.45, marginBottom: 8 }}>
                    {a.body}
                  </div>
                )}
                {a.donation && a.vote && (
                  <div style={{ fontSize: 10, color: colors.textMuted, fontFamily: font, marginBottom: 6 }}>
                    {fmtMoney(a.donation.amount)} · {a.donation.industry} → {a.vote.bill_number} ({a.vote.category})
                  </div>
                )}
              </>
            )}
            {a.score !== undefined && (
              <div style={{ fontSize: 10, color: colors.textMuted, fontFamily: font }}>
                score: {a.score.toFixed(2)} {a.signals?.T !== undefined && (
                  <span style={{ marginLeft: 8 }}>
                    T={a.signals.T.toFixed(2)} V={a.signals.V.toFixed(2)} D={a.signals.D.toFixed(2)} R={a.signals.R.toFixed(2)}
                    {a.signals.A !== undefined && ` A=${a.signals.A.toFixed(2)}`}
                    {a.signals.N !== undefined && ` N=${a.signals.N.toFixed(2)}`}
                  </span>
                )}
              </div>
            )}
          </div>
          );
        })}

        {isReal && alerts && alerts.length > 0 && (
          <div style={{ fontSize: 10, color: colors.textMuted, marginTop: 8, lineHeight: 1.5 }}>
            {COPY.alerts.stateFooterNote}
          </div>
        )}
      </div>
      <NavBar active={SCREENS.DASHBOARD} onNav={onNav} />
    </div>
  );
};

// ============================================================
// MAIN APP
// ============================================================

export default function App() {
  const [currentScreen, setCurrentScreen] = useState(SCREENS.SPLASH);
  const [selectedBioguideId, setSelectedBioguideId] = useState("M001169");
  const [userState, setUserState] = useState(() => auth.getUser()?.state || "CT");
  const [currentUser, setCurrentUser] = useState(() => auth.getUser());
  const [userIssues, setUserIssues] = useState(() => auth.getUser()?.issues || ["healthcare", "environment"]);
  const [profileData, setProfileData] = useState(null);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [selectedStatePeopleId, setSelectedStatePeopleId] = useState(null);
  const [stateRepData, setStateRepData] = useState(null);
  const [globalOffline, setGlobalOffline] = useState(false);

  // Civics-helper chat state. Lifted out of the (now-removed) bottom sheet so
  // navigating off the Ask tab and back doesn't wipe the conversation. Reset
  // on logout via handleSignOut.
  const [assistantMessages, setAssistantMessages] = useState([]);
  const [assistantInput, setAssistantInput] = useState("");
  const [assistantSending, setAssistantSending] = useState(false);
  const [assistantError, setAssistantError] = useState("");

  // The screen the user was on right before entering the Ask tab. Drives the
  // assistantContext below so the chatbot still knows "you came from this
  // rep's profile / this event detail" once you've actually switched tabs.
  // Updated on every screen change that isn't ASSISTANT itself.
  const [lastNonAssistantScreen, setLastNonAssistantScreen] = useState(SCREENS.DASHBOARD);
  useEffect(() => {
    if (currentScreen !== SCREENS.ASSISTANT) {
      setLastNonAssistantScreen(currentScreen);
    }
  }, [currentScreen]);

  // Check backend health on load
  useEffect(() => {
    api.health().catch(() => setGlobalOffline(true));
  }, []);

  // Auto-login from stored token; if it's stale, clear and stay on splash
  useEffect(() => {
    if (!auth.getToken()) return;
    api.me()
      .then((res) => {
        setCurrentUser(res.user);
        if (res.user.state) setUserState(res.user.state);
        // Always sync issues from server, even if the server list is empty —
        // otherwise a user who cleared their issues is stuck with the local
        // default forever.
        setUserIssues(res.user.issues || []);
        // Only redirect if the user hasn't already navigated past splash.
        // The me() call is async; without this guard a user who taps a nav
        // pill before it resolves gets yanked back to Dashboard.
        setCurrentScreen((prev) => prev === SCREENS.SPLASH ? SCREENS.DASHBOARD : prev);
      })
      .catch((e) => {
        if (e.status === 401) auth.clear();
      });
  }, []);

  const handleSignedIn = (user) => {
    setCurrentUser(user);
    if (user.state) setUserState(user.state);
    if (user.issues && user.issues.length > 0) setUserIssues(user.issues);
  };

  // Guest mode — anonymous, no auth token, no DB row. Lets a viewer poke
  // around the app for a demo without creating an account. Anything that
  // hits an auth-required endpoint (Mamu chat, saving preferences) is
  // gated client-side. Marked temporary by the user — easy to rip later
  // by deleting handleEnterGuest, the LoginScreen link, and the
  // `is_guest` branches in handleSave*/handleSignOut and AssistantScreen.
  const handleEnterGuest = () => {
    setCurrentUser({
      name: "Guest",
      state: "CT",
      issues: ["healthcare", "environment"],
      is_guest: true,
    });
    setUserState("CT");
    setUserIssues(["healthcare", "environment"]);
    setCurrentScreen(SCREENS.DASHBOARD);
  };

  const handleSaveState = async (newState) => {
    if (currentUser?.is_guest) {
      setUserState(newState);
      setCurrentUser({ ...currentUser, state: newState });
      return;
    }
    if (currentUser && auth.getToken()) {
      const res = await api.updateMe({ state: newState });
      setCurrentUser(res.user);
      auth.setSession(auth.getToken(), res.user);
      setUserState(res.user.state || newState);
    } else {
      setUserState(newState);
    }
  };

  const handleSaveIssues = async (newIssues) => {
    if (currentUser?.is_guest) {
      setUserIssues(newIssues);
      setCurrentUser({ ...currentUser, issues: newIssues });
      return;
    }
    if (currentUser && auth.getToken()) {
      const res = await api.updateMe({ issues: newIssues });
      setCurrentUser(res.user);
      auth.setSession(auth.getToken(), res.user);
      setUserIssues(res.user.issues || newIssues);
    } else {
      setUserIssues(newIssues);
    }
  };

  const handleSignOut = async () => {
    // Guest sign-out is purely local — no token, no /logout call. Real
    // sign-out hits the API to invalidate the session row.
    if (!currentUser?.is_guest) {
      try { await api.logout(); } catch { /* ignore */ }
    }
    auth.clear();
    setCurrentUser(null);
    setUserIssues(["healthcare", "environment"]);
    setAssistantMessages([]);
    setAssistantInput("");
    setAssistantError("");
    setCurrentScreen(SCREENS.SPLASH);
  };

  const handleDeleteAccount = async () => {
    // Guests have nothing to delete — exit straight to splash.
    if (currentUser?.is_guest) {
      handleSignOut();
      return;
    }
    if (!window.confirm("Permanently delete your account? This can't be undone.")) return;
    const password = window.prompt("Confirm your password to delete your account:");
    if (!password) return;
    try {
      await api.deleteAccount(password);
    } catch (e) {
      alert(`Could not delete account: ${e.detail || e.message}`);
      return;
    }
    auth.clear();
    setCurrentUser(null);
    setUserIssues(["healthcare", "environment"]);
    setAssistantMessages([]);
    setAssistantInput("");
    setAssistantError("");
    setCurrentScreen(SCREENS.SPLASH);
  };

  const navigate = (screen) => setCurrentScreen(screen);

  const selectPolitician = (bioguideId) => {
    setSelectedBioguideId(bioguideId);
    setProfileData(null); // clear old data so it refetches
    setCurrentScreen(SCREENS.POLITICIAN_PROFILE);
  };

  const selectStateRep = (peopleId) => {
    setSelectedStatePeopleId(peopleId);
    setStateRepData(null);
    setCurrentScreen(SCREENS.STATE_REP_PROFILE);
  };

  const selectEvent = (ev) => {
    setSelectedEvent(ev);
    setCurrentScreen(SCREENS.EVENT_DETAIL);
  };

  const renderScreen = () => {
    const common = { onNav: navigate, offline: globalOffline };
    switch (currentScreen) {
      case SCREENS.SPLASH: return <SplashScreen {...common} />;
      case SCREENS.CREATE_ACCOUNT: return <CreateAccountScreen {...common} onSignedIn={handleSignedIn} />;
      case SCREENS.LOGIN: return <LoginScreen {...common} onSignedIn={handleSignedIn} onEnterGuest={handleEnterGuest} />;
      case SCREENS.ISSUE_SELECT: return <IssueSelectScreen {...common} currentUser={currentUser} onSaveIssues={handleSaveIssues} />;
      case SCREENS.DASHBOARD: return <DashboardScreen {...common} onSelectPolitician={selectPolitician} userState={userState} currentUser={currentUser} userIssues={userIssues} />;
      case SCREENS.SEARCH: return <SearchScreen {...common} onSelectPolitician={selectPolitician} onSelectStateRep={selectStateRep} userState={userState} />;
      case SCREENS.POLITICIAN_PROFILE: return <PoliticianProfileScreen {...common} bioguideId={selectedBioguideId} onSetProfileData={setProfileData} />;
      case SCREENS.FUNDING: return <FundingScreen {...common} profileData={profileData} />;
      case SCREENS.VOTING_HISTORY: return <VotingHistoryScreen {...common} profileData={profileData} />;
      case SCREENS.PROMISE_SCORING: return <PromiseScoringScreen {...common} bioguideId={selectedBioguideId} profileData={profileData} />;
      case SCREENS.TIMELINE: return <TimelineScreen {...common} profileData={profileData} />;
      case SCREENS.TAKE_ACTION: return <TakeActionScreen {...common} profileData={profileData} />;
      case SCREENS.CONTACT_REP: return <ContactRepScreen {...common} userState={userState} />;
      case SCREENS.EVENTS: return <EventsScreen {...common} userState={userState} onSelectEvent={selectEvent} />;
      case SCREENS.EVENT_DETAIL: return <EventDetailScreen {...common} event={selectedEvent} />;
      case SCREENS.LEARN_TO_VOTE: return <LearnToVoteScreen {...common} userState={userState} />;
      case SCREENS.ALERTS: return <AlertsScreen {...common} onSelectPolitician={selectPolitician} />;
      case SCREENS.STATE_REPS: return <StateRepsScreen {...common} userState={userState} onSelectStateRep={selectStateRep} />;
      case SCREENS.STATE_REP_PROFILE: return <StateRepProfileScreen {...common} peopleId={selectedStatePeopleId} onSetStateRepData={setStateRepData} />;
      case SCREENS.STATE_REP_VOTING: return <StateRepVotingScreen {...common} peopleId={selectedStatePeopleId} stateRepData={stateRepData} />;
      case SCREENS.STATE_REP_STANCES: return <StateRepStancesScreen {...common} peopleId={selectedStatePeopleId} stateRepData={stateRepData} />;
      case SCREENS.STATE_REP_PROMISES: return <StateRepPromisesScreen {...common} peopleId={selectedStatePeopleId} stateRepData={stateRepData} />;
      case SCREENS.STATE_REP_ALERTS: return <StateRepAlertsScreen {...common} peopleId={selectedStatePeopleId} stateRepData={stateRepData} />;
      case SCREENS.SETTINGS: return <SettingsScreen {...common} userState={userState} onSaveState={handleSaveState} currentUser={currentUser} userIssues={userIssues} onSaveIssues={handleSaveIssues} onSignOut={handleSignOut} onDeleteAccount={handleDeleteAccount} />;
      case SCREENS.ASSISTANT: return <AssistantScreen
        {...common}
        context={assistantContext}
        messages={assistantMessages}
        setMessages={setAssistantMessages}
        input={assistantInput}
        setInput={setAssistantInput}
        sending={assistantSending}
        setSending={setAssistantSending}
        errorMsg={assistantError}
        setErrorMsg={setAssistantError}
        onClearChat={() => { setAssistantMessages([]); setAssistantInput(""); setAssistantError(""); }}
        isGuest={currentUser?.is_guest === true}
      />;
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
    [SCREENS.EVENT_DETAIL, "Event Detail"],
    [SCREENS.LEARN_TO_VOTE, "Learn to Vote"],
    [SCREENS.ALERTS, "Alerts"],
    [SCREENS.STATE_REPS, "State Reps"],
    [SCREENS.STATE_REP_PROFILE, "State Profile"],
    [SCREENS.STATE_REP_VOTING, "State Voting"],
    [SCREENS.STATE_REP_STANCES, "State Stances"],
    [SCREENS.STATE_REP_PROMISES, "State Promises"],
    [SCREENS.STATE_REP_ALERTS, "State Alerts"],
    [SCREENS.ASSISTANT, "Mamu"],
    [SCREENS.SETTINGS, "Settings"],
  ];

  // Floating civics-helper pill — visible on every signed-in screen except
  // splash / auth / onboarding (where there's no learning context yet) and
  // the Ask tab itself (would be self-referential). Tapping the pill jumps
  // to the Ask tab; the lastNonAssistantScreen tracker preserves the source
  // screen so the chatbot still knows what the user was looking at.
  const PILL_HIDDEN_ON = new Set([
    SCREENS.SPLASH,
    SCREENS.LOGIN,
    SCREENS.CREATE_ACCOUNT,
    SCREENS.ISSUE_SELECT,
    SCREENS.ASSISTANT,
  ]);
  const showAssistantPill = !!currentUser && !PILL_HIDDEN_ON.has(currentScreen);
  const assistantPillEl = showAssistantPill && (
    <button
      type="button"
      style={s.assistantPill}
      onClick={() => setCurrentScreen(SCREENS.ASSISTANT)}
      aria-label={COPY.assistant.title}
    >
      <span aria-hidden="true">✨</span>
      {COPY.assistant.pillLabel}
    </button>
  );
  // Map the source screen + selected entities into the opaque `context` dict
  // the backend assistant module reads (see backend/api/assistant_chat.py).
  // When on the Ask tab itself, source = lastNonAssistantScreen so context
  // still resolves to the rep/event/etc. the user was just looking at.
  // Sub-screens of a profile (FUNDING/VOTING_HISTORY/TIMELINE/etc.) inherit
  // their parent's rep context so "what does this rep do on healthcare?" works
  // from anywhere inside the profile cluster, not just the landing tile.
  const FEDERAL_PROFILE_SCREENS = new Set([
    SCREENS.POLITICIAN_PROFILE, SCREENS.FUNDING, SCREENS.VOTING_HISTORY,
    SCREENS.PROMISE_SCORING, SCREENS.TIMELINE, SCREENS.TAKE_ACTION,
  ]);
  const STATE_PROFILE_SCREENS = new Set([
    SCREENS.STATE_REP_PROFILE, SCREENS.STATE_REP_VOTING, SCREENS.STATE_REP_STANCES,
    SCREENS.STATE_REP_PROMISES, SCREENS.STATE_REP_ALERTS,
  ]);
  const contextSourceScreen = currentScreen === SCREENS.ASSISTANT
    ? lastNonAssistantScreen
    : currentScreen;
  let assistantContext;
  if (FEDERAL_PROFILE_SCREENS.has(contextSourceScreen) && selectedBioguideId) {
    assistantContext = {
      screen: "profile",
      rep_id: selectedBioguideId,
      rep_name: profileData?.profile?.name || null,
    };
  } else if (STATE_PROFILE_SCREENS.has(contextSourceScreen) && selectedStatePeopleId) {
    assistantContext = {
      screen: "state_profile",
      state_rep_id: selectedStatePeopleId,
      rep_name: stateRepData?.person?.name || stateRepData?.name || null,
    };
  } else if (contextSourceScreen === SCREENS.EVENT_DETAIL && selectedEvent) {
    assistantContext = {
      screen: "event",
      event_title: selectedEvent.title || null,
    };
  } else if (contextSourceScreen === SCREENS.LEARN_TO_VOTE) {
    assistantContext = {
      screen: "learn_to_vote",
      learn_to_vote_state: userState || currentUser?.state || null,
    };
  } else {
    assistantContext = { screen: contextSourceScreen };
  }

  // In PWA mode the app fills the viewport directly — no dev header, no
  // screen-selector pills, no centered phone-frame container. The screen
  // already styles itself for full-bleed via s.phone (which switches to
  // 100vw/100vh in PWA mode).
  if (_IS_PWA_AT_BOOT) {
    return (
      <>
        {renderScreen()}
        {assistantPillEl}
      </>
    );
  }

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
      {assistantPillEl}
    </div>
  );
}
