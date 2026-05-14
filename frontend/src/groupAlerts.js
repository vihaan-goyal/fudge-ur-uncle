// Collapse alerts that share (actor, industry, category) into a single card.
// The pipeline writes one row per (donation x vote) pair, so a donor with N
// bills in the same category produces N identical-looking headlines. Group
// here so the user sees one card with the bills rolled up.
//
// Alerts missing industry/category (notably the SAMPLE.alerts offline shape)
// fall back to a per-id solo key so they render unchanged.
export function groupAlerts(alerts) {
  if (!alerts) return [];
  const groups = new Map();
  for (const a of alerts) {
    const industry = a.donation?.industry;
    const category = a.vote?.category;
    const key = (industry && category)
      ? `${a.actor_id ?? a.bioguide_id ?? ""}|${industry}|${category}`
      : `__solo__${a.id}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(a);
  }
  const out = [];
  for (const group of groups.values()) {
    group.sort((x, y) => (y.score ?? 0) - (x.score ?? 0));
    const lead = group[0];
    out.push({
      ...lead,
      bills: group.map((a) => a.vote).filter(Boolean),
      groupSize: group.length,
    });
  }
  out.sort((x, y) => (y.score ?? 0) - (x.score ?? 0));
  return out;
}
