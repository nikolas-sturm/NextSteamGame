import { describe, expect, it } from "vitest";

import type { Intent } from "@/models/recommendation";

import { decodeIntent, encodeIntent } from "./share";

const intent: Intent = {
  lanes: { mechanics: 75, narrative: 55, vibe: 80, loop: 45 },
  exclude: ["grind", "combat"],
  include: ["wonder", "calm"],
  text: "quiet mystery",
  limit: 12,
  seeds: [
    {
      id: 20,
      title: "B",
      year: 2002,
      descriptor: "",
      steamUrl: "https://example.test/20",
      imageUrl: null,
      weight: 0.8,
    },
    {
      id: 10,
      title: "A",
      year: 2001,
      descriptor: "",
      steamUrl: "https://example.test/10",
      imageUrl: null,
      weight: 1.2,
    },
  ],
};

describe("shared intent", () => {
  it("encodes stably", () => {
    expect(encodeIntent(intent)).toBe(
      "seeds=10%3A1.2%2C20%3A0.8&weights=75%2C55%2C80%2C45&include=calm%2Cwonder&exclude=combat%2Cgrind&text=quiet+mystery&limit=12",
    );
  });

  it("restores seed IDs, weights, and controls", () => {
    const decoded = decodeIntent(new URLSearchParams(encodeIntent(intent)), { ...intent, seeds: [] });
    expect(decoded.seeds.map(({ id, weight }) => ({ id, weight }))).toEqual([
      { id: 10, weight: 1.2 },
      { id: 20, weight: 0.8 },
    ]);
    expect(decoded.lanes).toEqual(intent.lanes);
    expect(decoded.include).toEqual(["calm", "wonder"]);
    expect(decoded.exclude).toEqual(["combat", "grind"]);
    expect(decoded.text).toBe(intent.text);
    expect(decoded.limit).toBe(intent.limit);
  });
});
