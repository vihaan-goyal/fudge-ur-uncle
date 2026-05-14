// Centralized user-facing strings. Lets us tone-swap the whole app from a
// single place — currently leaning "friendly to new voters / immigrants"
// rather than the original "accountability watchdog" framing. If we ever
// add a noob/pro flag, this becomes the swap point.

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
