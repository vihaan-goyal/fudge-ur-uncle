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
  profile: {
    promiseScoreLabel: "Promise",
    yeaVotesLabel: "Yea votes",
    raisedLabel: "Raised",
    tiles: {
      funding: { label: "Funding breakdown", fallbackSub: "View details", topPrefix: "Top: " },
      voting: { label: "Voting record", sub: (n) => `${n} recent votes` },
      stances: { label: "Voting positions", sub: "AI stance analysis" },
      timeline: { label: "Activity timeline", sub: "Recent events" },
      contact: { label: "Contact / take action", fallbackSub: "Reach out" },
    },
  },
  takeAction: {
    title: "Take action",
    subtitle: "Every contact is logged by their office.",
    callLabel: "Call their office",
    callFallback: "No phone available",
    contactFormLabel: "Contact form",
    contactFormSub: "Official contact page",
    websiteLabel: "Visit their website",
    websiteFallback: "No website available",
    scriptTitle: "Call script template",
    scriptBody: (name) =>
      `"Hi, I'm a constituent from [zip]. I'm calling about [bill]. I urge ${name} to vote [YES/NO] because [reason]. Thank you."`,
  },
  contact: {
    title: "Contact your reps",
    callBtn: "Call",
    websiteBtn: "Website",
    callAria: (name) => `Call ${name}`,
    websiteAria: (name) => `Visit ${name}'s website`,
  },
  learnToVote: {
    title: "Voting guide",
    resourcesTitle: "Resources",
    yourStateTitle: (state) => `Your state: ${state || "—"}`,
    genericNote:
      "Pick your state in Settings to see local deadlines and ID rules. The resources above work nationwide.",
    sourceNote:
      "Rules change — always confirm on your state's official site before you head to the polls.",
    rows: {
      register: "Register to vote",
      polling: "Find your polling place",
      deadline: "Registration deadline",
      id: "ID requirements",
      hours: "Polling hours",
      official: "Official state voting site",
    },
    resources: [
      { label: "Register to vote", url: "https://vote.gov" },
      { label: "Find your polling place", url: "https://www.vote.org/polling-place-locator/" },
      { label: "Absentee / mail-in ballot", url: "https://www.vote.org/absentee-ballot/" },
      { label: "Check voter registration", url: "https://www.vote.org/am-i-registered-to-vote/" },
    ],
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
  assistant: {
    pillLabel: "Ask",
    title: "Civics helper",
    subtitle: "Ask anything about how this works",
    placeholder: "Type your question…",
    sending: "Thinking…",
    send: "Send",
    close: "Close",
    error: "Couldn't reach the helper. Try again in a moment.",
    emptyState: "Ask me about a bill, your reps, or how Congress works.",
    suggestions: [
      "How does a bill become law?",
      "What does my rep actually do?",
      "Why do donations matter?",
    ],
    contextChip: {
      profile: (name) => (name ? `Asking about ${name}` : "Asking about this rep"),
      state_profile: (name) => (name ? `Asking about ${name}` : "Asking about this rep"),
      event: "Asking about this hearing",
      bill: "Asking about this bill",
      learn_to_vote: (state) => (state ? `Voting in ${state}` : "Asking about voting"),
      dashboard: "On your dashboard",
    },
    disclaimer: "AI-generated — verify important details on the official source.",
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

// State-specific voting facts for the Learn-to-Vote screen. Covers the 5
// jurisdictions the backend tracks today (CT, NY, NJ, CA, MA). Rules change
// frequently — always link to the state's official site as the source of
// truth, and surface the disclaimer (`learnToVote.sourceNote`) below the
// card. Adding a new state: append an entry and the screen picks it up.
export const STATE_VOTING_GUIDE = {
  CT: {
    name: "Connecticut",
    registerUrl: "https://voterregistration.ct.gov",
    pollingPlaceUrl: "https://portaldir.ct.gov/sots/LookUp.aspx",
    officialUrl: "https://portal.ct.gov/sots/elections",
    registrationDeadline: "7 days before Election Day, or in person on Election Day with proof of residence",
    idRequired: "ID requested but not required — you can sign an affidavit if you don't have one",
    pollingHours: "6 AM – 8 PM",
  },
  NY: {
    name: "New York",
    registerUrl: "https://elections.ny.gov/register-vote",
    pollingPlaceUrl: "https://voterlookup.elections.ny.gov",
    officialUrl: "https://elections.ny.gov",
    registrationDeadline: "Postmarked at least 10 days before Election Day",
    idRequired: "No ID required at the polls unless you're a first-time voter who registered by mail without ID",
    pollingHours: "6 AM – 9 PM",
  },
  NJ: {
    name: "New Jersey",
    registerUrl: "https://nj.gov/state/elections/voter-registration.shtml",
    pollingPlaceUrl: "https://voter.svrs.nj.gov/polling-place-search",
    officialUrl: "https://nj.gov/state/elections",
    registrationDeadline: "21 days before Election Day",
    idRequired: "First-time voters need ID or proof of residence — returning voters don't",
    pollingHours: "6 AM – 8 PM",
  },
  CA: {
    name: "California",
    registerUrl: "https://registertovote.ca.gov",
    pollingPlaceUrl: "https://www.sos.ca.gov/elections/polling-place",
    officialUrl: "https://www.sos.ca.gov/elections",
    registrationDeadline: "15 days before Election Day, or same-day conditional voting at any polling location",
    idRequired: "Generally none — first-time voters who registered by mail without ID will be asked for one",
    pollingHours: "7 AM – 8 PM",
  },
  MA: {
    name: "Massachusetts",
    registerUrl: "https://www.sec.state.ma.us/divisions/elections/voter-resources/online-voter-registration.htm",
    pollingPlaceUrl: "https://www.sec.state.ma.us/wheredoivotema/bal/myelectioninfo.aspx",
    officialUrl: "https://www.sec.state.ma.us/divisions/elections",
    registrationDeadline: "10 days before Election Day",
    idRequired: "Usually not asked, but bring one — inactive voters and some mail-in registrants may be checked",
    pollingHours: "7 AM – 8 PM (some towns open earlier)",
  },
};
