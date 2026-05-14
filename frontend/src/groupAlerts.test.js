import { describe, expect, it } from "vitest";
import { groupAlerts } from "./groupAlerts.js";

// Minimal helper so test cases stay readable. Mirrors the alert shape the
// backend `/api/alerts` endpoint actually returns — see backend/alerts/scoring.py.
function alert({
  id,
  actor_id = "TEST_REP",
  bioguide_id,
  industry = "oil_gas",
  category = "environment",
  bill_number = "S.1",
  score = 0.5,
  ...rest
}) {
  return {
    id,
    actor_id,
    bioguide_id,
    score,
    donation: industry ? { industry, amount: 1000 } : undefined,
    vote: category ? { bill_number, category, title: `Bill ${bill_number}` } : undefined,
    ...rest,
  };
}

describe("groupAlerts", () => {
  it("returns [] for null / undefined / empty", () => {
    expect(groupAlerts(null)).toEqual([]);
    expect(groupAlerts(undefined)).toEqual([]);
    expect(groupAlerts([])).toEqual([]);
  });

  it("wraps a single full-shape alert with groupSize 1 and a one-bill list", () => {
    const out = groupAlerts([alert({ id: 1, score: 0.7 })]);
    expect(out).toHaveLength(1);
    expect(out[0].groupSize).toBe(1);
    expect(out[0].bills).toHaveLength(1);
    expect(out[0].bills[0].bill_number).toBe("S.1");
    expect(out[0].score).toBe(0.7);
  });

  it("rolls up alerts that share (actor_id, industry, category)", () => {
    const out = groupAlerts([
      alert({ id: 1, bill_number: "S.1", score: 0.4 }),
      alert({ id: 2, bill_number: "S.2", score: 0.8 }),  // higher -> becomes lead
      alert({ id: 3, bill_number: "S.3", score: 0.6 }),
    ]);
    expect(out).toHaveLength(1);
    const g = out[0];
    expect(g.groupSize).toBe(3);
    expect(g.id).toBe(2);                // lead is the highest-scored alert
    expect(g.score).toBe(0.8);
    // Bills ordered by score desc within the group.
    expect(g.bills.map((b) => b.bill_number)).toEqual(["S.2", "S.3", "S.1"]);
  });

  it("does not merge across different actor_ids", () => {
    const out = groupAlerts([
      alert({ id: 1, actor_id: "REP_A", bill_number: "S.1", score: 0.5 }),
      alert({ id: 2, actor_id: "REP_B", bill_number: "S.1", score: 0.5 }),
    ]);
    expect(out).toHaveLength(2);
    expect(out.every((g) => g.groupSize === 1)).toBe(true);
  });

  it("does not merge across different industries or categories", () => {
    const out = groupAlerts([
      alert({ id: 1, industry: "oil_gas", category: "environment" }),
      alert({ id: 2, industry: "oil_gas", category: "infrastructure" }),
      alert({ id: 3, industry: "pharmaceuticals", category: "healthcare" }),
    ]);
    expect(out).toHaveLength(3);
  });

  it("uses bioguide_id as the key fallback when actor_id is missing", () => {
    // Two alerts with no actor_id but the same bioguide_id + industry + category
    // must still collapse into one group. Covers older alert shapes the backend
    // still emits for federal-only flows.
    const out = groupAlerts([
      alert({ id: 1, actor_id: undefined, bioguide_id: "M001169", bill_number: "S.1" }),
      alert({ id: 2, actor_id: undefined, bioguide_id: "M001169", bill_number: "S.2" }),
    ]);
    expect(out).toHaveLength(1);
    expect(out[0].groupSize).toBe(2);
  });

  it("keeps SAMPLE.alerts-style entries (no donation/vote) as solo groups", () => {
    // SAMPLE.alerts in api.js ships with denormalized fields (no nested
    // donation/vote), so the grouper falls back to keying by id and each
    // alert renders standalone.
    const out = groupAlerts([
      { id: 11, actor_id: "X", score: 0.9, headline: "Sample 1" },
      { id: 12, actor_id: "X", score: 0.7, headline: "Sample 2" },
    ]);
    expect(out).toHaveLength(2);
    expect(out.every((g) => g.groupSize === 1)).toBe(true);
    // Solo entries shouldn't gain phantom bills.
    expect(out[0].bills).toEqual([]);
    expect(out[1].bills).toEqual([]);
    // Top-level output is still sorted by score desc.
    expect(out.map((g) => g.id)).toEqual([11, 12]);
  });

  it("orders the returned groups by score desc", () => {
    const out = groupAlerts([
      alert({ id: 1, actor_id: "REP_A", score: 0.3 }),
      alert({ id: 2, actor_id: "REP_B", score: 0.9 }),
      alert({ id: 3, actor_id: "REP_C", score: 0.6 }),
    ]);
    expect(out.map((g) => g.id)).toEqual([2, 3, 1]);
  });

  it("treats missing score as 0 when sorting", () => {
    // Defensive: an alert lacking a score field should sink to the bottom
    // rather than corrupting the sort with NaN. Built without the helper
    // because the helper's destructure default would supply a score.
    const noScore = {
      id: 1,
      actor_id: "REP_A",
      donation: { industry: "oil_gas" },
      vote: { bill_number: "S.1", category: "environment" },
    };
    const out = groupAlerts([noScore, alert({ id: 2, actor_id: "REP_B", score: 0.4 })]);
    expect(out[0].id).toBe(2);
  });
});
