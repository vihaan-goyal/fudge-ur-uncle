// Centralized user-facing strings. Lets us tone-swap the whole app from a
// single place — currently leaning "friendly to new voters / immigrants"
// rather than the original "accountability watchdog" framing. If we ever
// add a noob/pro flag, this becomes the swap point.
//
// Deeper screens (alerts, events, profiles) still use the all-caps
// "terminal" aesthetic for section labels — centralizing those here too
// so the swap point covers the whole app, not just the dashboard.

export const COPY = {
  dashboard: {
    // Header — personalised greeting. Uses the user's first name when we
    // have one, falls back to a generic friendly opener for anonymous /
    // pre-signin states.
    greeting: (name) => {
      const first = name?.trim().split(/\s+/)[0];
      return first ? `Hey ${first}` : "Hi there";
    },
    greetingSub: (state) =>
      state ? `Here's what's happening in ${state}` : "Here's what's happening",
    // Personalised variant — when the user has issues selected, fold them
    // into the subline so they see the feed reflects their picks.
    greetingSubWithIssues: (state, issueLabels) => {
      const issues = issueLabels.join(", ").toLowerCase();
      return state
        ? `Here's what's happening in ${state} around ${issues}`
        : `Here's what's happening around ${issues}`;
    },
    repsSectionTitle: "Your reps",
    comingUpTitle: "Coming up",
    comingUpSubtitle: "Your reps are voting on",
    comingUpEmpty: "Nothing scheduled yet — check back soon.",
    comingUpRelative: (days) =>
      days <= 0 ? "today" : days === 1 ? "in 1 day" : `in ${days} days`,
    quickActionsTitle: "Start here",
    quickActions: {
      contactRep: "Reach your rep",
      votingGuide: "How to vote",
      events: "What's happening locally",
      followMoney: "Who funds them",
      stateReps: "Your state lawmakers",
    },
  },
  events: {
    listTitle: "Federal committee hearings",
    listSubtitle: "U.S. Congress · upcoming meetings",
    offlineBadge: "Offline — sample data",
    offlineBody: "Could not reach the server. Showing example events.",
    emptyList: "No upcoming events found.",
    backLabel: "Events",
    noEventSelected: "No event selected.",
    aiSummaryLabel: "AI summary",
    aiSummaryLoading: "Generating summary...",
    aiSummaryEmpty: "Summary unavailable.",
    scheduleLabel: "Schedule",
    scheduleDate: "Date",
    scheduleTime: "Time",
    schedulePlace: "Place",
    committeesLabel: (n) => (n > 1 ? "Committees" : "Committee"),
    witnessesLabel: "Witnesses",
    legislationLabel: "Legislation",
    newsLabel: "News coverage",
    newsLoading: "Finding related article...",
    newsEmpty: "No recent coverage found.",
  },
  alerts: {
    title: "Alerts",
    subtitle: "Donation + vote correlations",
    chipAll: "All",
    chipUrgent: "Urgent only",
    urgentBadge: "Urgent",
    offlineBadge: "Showing sample alerts (backend offline)",
    loading: "Loading alerts...",
    emptyHint: "No alerts right now. Run the pipeline:",
    viewRepButton: "View Rep",
    moreBills: (k) => `(+${k} more)`,
    // State variant
    stateSubtitle: "Industry donations × upcoming state votes",
    stateLoading: "Loading alerts…",
    stateEmptyTitle: "No alerts for this legislator yet.",
    stateEmptyHint: "Run the state ingestion pipeline:",
    stateFallbackName: "State Legislator",
    stateFooterNote:
      "State alerts use FTM industry aggregates and Legiscan engrossed-bill statuses. Scores typically run lower than federal alerts because aggregate data carries less per-donation signal.",
  },
  settings: {
    accountTitle: "Account",
    locationTitle: "Location",
    issuesTitle: "Issues you care about",
    issuesHint: "We'll prioritize upcoming votes in these areas. Pick up to 5.",
    issuesSaving: "Saving...",
    issuesSaved: "Saved",
    issuesSaveError: "Couldn't save",
    issuesCounter: (n, max) => `${n}/${max} selected`,
  },
  // Plain-language category labels (used by the "coming up" feed). Sentence-
  // case so they read well as standalone chips. Falls back to a humanized
  // version of the raw key when missing.
  categories: {
    healthcare: "Healthcare",
    environment: "Environment",
    economy: "Economy",
    defense: "Defense",
    infrastructure: "Infrastructure",
    technology: "Tech policy",
    labor: "Workers' rights",
    agriculture: "Agriculture",
    housing: "Housing",
    education: "Education",
    immigration: "Immigration",
    firearms: "Gun policy",
    elections: "Elections",
    foreign_policy: "Foreign policy",
  },
};

export const friendlyCategory = (raw) => {
  if (!raw) return "Upcoming bill";
  if (COPY.categories[raw]) return COPY.categories[raw];
  const humanized = raw.replace(/_/g, " ");
  return humanized.charAt(0).toUpperCase() + humanized.slice(1);
};

// Inline variant — lowercased for mid-sentence use ("5 upcoming foreign
// policy bills"). Falls back to "" when raw is missing so the surrounding
// sentence still parses.
export const friendlyCategoryInline = (raw) => {
  if (!raw) return "";
  const label = COPY.categories[raw] || raw.replace(/_/g, " ");
  return label.toLowerCase();
};
