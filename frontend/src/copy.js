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
    repsSectionTitle: "Your reps",
    comingUpTitle: "Coming up",
    comingUpSubtitle: "Your reps are voting on",
    comingUpEmpty: "Nothing scheduled yet — check back soon.",
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
    listTitle: "Federal Committee Hearings",
    listSubtitle: "U.S. Congress · upcoming meetings",
    offlineBadge: "OFFLINE — SAMPLE DATA",
    offlineBody: "Could not reach the server. Showing example events.",
    emptyList: "No upcoming events found.",
    backLabel: "Events",
    noEventSelected: "No event selected.",
    aiSummaryLabel: "AI SUMMARY",
    aiSummaryLoading: "Generating summary...",
    aiSummaryEmpty: "Summary unavailable.",
    scheduleLabel: "SCHEDULE",
    scheduleDate: "Date",
    scheduleTime: "Time",
    schedulePlace: "Place",
    committeesLabel: (n) => (n > 1 ? "COMMITTEES" : "COMMITTEE"),
    witnessesLabel: "WITNESSES",
    legislationLabel: "LEGISLATION",
    newsLabel: "NEWS COVERAGE",
    newsLoading: "Finding related article...",
    newsEmpty: "No recent coverage found.",
  },
  alerts: {
    title: "Alerts",
    subtitle: "Donation + vote correlations",
    chipAll: "All",
    chipUrgent: "Urgent only",
    urgentBadge: "URGENT",
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
