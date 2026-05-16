// Centralized user-facing strings. Lets us tone-swap the whole app from a
// single place — currently leaning "friendly to new voters / immigrants"
// rather than the original "accountability watchdog" framing. If we ever
// add a noob/pro flag, this becomes the swap point.
//
// Deeper screens (alerts, events, profiles) still use the all-caps
// "terminal" aesthetic for section labels — centralizing those here too
// so the swap point covers the whole app, not just the dashboard.

export const COPY = {
  auth: {
    splash: {
      subtitle: "Hold your politicians accountable.\nFollow the money. Take action.",
      primaryCta: "Create account",
      secondaryCta: "Log in",
      footer: "Democracy requires participation.",
    },
    createAccount: {
      title: "Create account",
      subtitle: "Your data stays yours. We never sell it.",
      nameLabel: "Full name",
      emailLabel: "Email",
      stateLabel: "State (2-letter)",
      stateHelper: "We use this to find your representatives",
      passwordLabel: "Password",
      submitIdle: "Continue",
      submitBusy: "Creating…",
      haveAccountPrompt: "Already have an account?",
      haveAccountLink: "Log in",
    },
    login: {
      title: "Welcome back",
      emailLabel: "Email",
      passwordLabel: "Password",
      submitIdle: "Log in",
      submitBusy: "Logging in…",
      newHerePrompt: "New here?",
      newHereLink: "Create an account",
      guestPrompt: "Just looking?",
      guestLink: "Continue as guest",
    },
  },
  onboarding: {
    title: "What issues matter most?",
    subtitle: "Select up to 5. This filters your alerts and feed.",
    selectionCounter: (n, max) => `${n}/${max} selected`,
    atMaxNote: " · deselect one to choose another",
    saveBtnIdle: "Done — show me my reps",
    saveBtnBusy: "Saving…",
    saveBtnAtMin: "Pick at least one to continue",
  },
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
    votingHistory: {
      title: "Voting record",
      chipAll: "All",
      emptyFilter: "No votes match this filter.",
    },
    promiseScoring: {
      title: "Voting positions",
      subtitle: "AI-analyzed from actual votes and sponsored legislation",
      analyzingLoad: "Analyzing voting record…",
      scrapingLoad: "Scraping official site…",
      aiKeyMissingTitle: "OpenAI key not configured",
      aiKeyMissingBody: "Add OPENAI_API_KEY to backend/.env to enable AI stance analysis.",
      promisesSection: "Stated promises vs voting record",
      promisesEmpty: "No public promises found. We tried the rep's official site, Wikipedia, and Ballotpedia — none had enough stated-position text to extract.",
      promisesSourceNotePre: "Promises extracted from ",
      promisesSourceNotePost: ", scored against recent votes by GPT-4o-mini.",
      keyPositions: (n) => `Key positions (${n})`,
      scoresNote: "Scores reflect voting record consistency, not campaign promises. Analysis powered by GPT-4o-mini.",
      notEnoughData: "Not enough voting data to analyze positions yet.",
      loadError: "Could not load stance analysis. Try again later.",
    },
    timeline: {
      title: "Activity timeline",
      empty: "No recent activity tracked.",
    },
  },
  stateProfile: {
    tiles: {
      voting:   { label: "Voting record",    sub: "Recent roll-call votes" },
      stances:  { label: "Voting positions", sub: "AI stance analysis" },
      promises: { label: "Stated promises",  sub: "Site-scraped positions vs. votes" },
      alerts:   { label: "Alerts",           sub: "Donor industry × upcoming votes" },
    },
    recentSponsored: "Recent sponsored bills",
    voting: {
      title: "Voting record",
      subtitle: "Recent roll calls on sponsored legislation",
      loading: "Pulling roll calls…",
      empty: "No roll-call votes found on this legislator's recent sponsored bills. State-level votes aren't always recorded by Legiscan — this can be normal.",
    },
    stances: {
      title: "Voting positions",
      subtitle: "AI-analyzed from actual votes and sponsored legislation",
      loading: "Analyzing voting record…",
      aiKeyMissingTitle: "OpenAI key not configured",
      aiKeyMissingBody: "Add OPENAI_API_KEY to backend/.env to enable AI stance analysis.",
      keyPositions: (n) => `Key positions (${n})`,
      scoresNote: "Scores reflect voting record consistency, not campaign promises. Analysis powered by GPT-4o-mini.",
      notEnoughData: "Not enough voting data to analyze positions yet. State-level vote records are thinner than federal.",
    },
    promises: {
      title: "Stated promises",
      subtitle: "Site-scraped positions scored against voting record",
      loading: "Scraping public bio and scoring…",
      aiKeyMissingTitle: "OpenAI key not configured",
      aiKeyMissingBody: "Add OPENAI_API_KEY to backend/.env to enable promise scoring.",
      notScraped: "No public bio page with enough policy text was found. We checked Ballotpedia and Wikipedia — state legislators often don't publish stated positions online.",
      empty: "Bio page was readable but no clear stated positions were extracted.",
      sourceNotePre: "Promises extracted from ",
      sourceNotePost: ", scored against recent votes by GPT-4o-mini.",
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
    pillLabel: "Mamu",
    title: "Mamu",
    subtitle: "Your civics-savvy Mamu — ask anything",
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

// Plain-language definitions for civics jargon that appears on screen.
// Wrapped by <TermTip term="..."> in App.jsx — dotted underline on the term,
// tap to read the definition. Keep entries short (1–2 sentences) and avoid
// defining jargon with more jargon. Adding a term: add an entry here, then
// wrap the matching label or word in App.jsx.
export const GLOSSARY = {
  pac: {
    label: "PAC",
    body: "Political Action Committee — a group that pools money to back candidates. Often funded by an industry, union, or company employees.",
  },
  small_donor: {
    label: "Small-donor",
    body: "Contributions of $200 or less, usually from individual supporters rather than companies or PACs.",
  },
  industry: {
    label: "Industry",
    body: "A category we use to group donors — pharma, oil & gas, tech — so you can see whose money is moving alongside a vote.",
  },
  yea: {
    label: "Yea",
    body: "A 'yes' vote on a bill or motion. The official wording legislatures use when calling the roll.",
  },
  nay: {
    label: "Nay",
    body: "A 'no' vote on a bill or motion.",
  },
  roll_call: {
    label: "Roll-call vote",
    body: "A vote where every legislator's individual yes/no is recorded by name. That's how we hold them accountable on a specific bill.",
  },
  sponsor: {
    label: "Sponsor",
    body: "The legislator who formally introduces a bill. They lead the push to get it passed.",
  },
  engrossed: {
    label: "Engrossed",
    body: "A state bill that has passed one chamber and is moving to the other — close to becoming law, but not there yet.",
  },
  chamber: {
    label: "Chamber",
    body: "One of the two halves of a legislature. In Congress: the House and the Senate. Most states work the same way.",
  },
};
