import type { Intent, LaneKey, SeedGame } from "@/models/recommendation";

const keys: LaneKey[] = ["mechanics", "narrative", "vibe", "loop"];

export function encodeIntent(intent: Intent): string {
  const params = new URLSearchParams();
  if (intent.seeds.length) {
    params.set(
      "seeds",
      intent.seeds.map((seed) => `${seed.id}:${seed.weight}`).sort().join(","),
    );
  }
  params.set("weights", keys.map((key) => intent.lanes[key]).join(","));
  if (intent.include.length) params.set("include", [...intent.include].sort().join(","));
  if (intent.exclude.length) params.set("exclude", [...intent.exclude].sort().join(","));
  if (intent.text.trim()) params.set("text", intent.text.trim());
  params.set("limit", String(intent.limit));
  return params.toString();
}

export function decodeIntent(params: URLSearchParams, fallback: Intent): Intent {
  const weights = params.get("weights")?.split(",").map(Number);
  if (
    weights?.length !== keys.length ||
    !weights.every((value) => Number.isFinite(value) && value >= 0 && value <= 100)
  ) {
    return fallback;
  }

  const seeds = (params.get("seeds")?.split(",") ?? [])
    .map((value): SeedGame | null => {
      const [rawId, rawWeight] = value.split(":");
      const id = Number(rawId);
      const weight = Number(rawWeight);
      if (!Number.isInteger(id) || id <= 0 || !Number.isFinite(weight) || weight < 0.1 || weight > 2) {
        return null;
      }
      return {
        id,
        title: `Steam app ${id}`,
        year: null,
        descriptor: "Shared recommendation seed",
        steamUrl: `https://store.steampowered.com/app/${id}`,
        imageUrl: null,
        weight,
      };
    })
    .filter((seed): seed is SeedGame => seed !== null)
    .filter((seed, index, all) => all.findIndex((item) => item.id === seed.id) === index)
    .slice(0, 8);

  return {
    ...fallback,
    seeds,
    lanes: Object.fromEntries(keys.map((key, index) => [key, weights[index]])) as Record<
      LaneKey,
      number
    >,
    include: params.get("include")?.split(",").filter(Boolean).slice(0, 20) ?? [],
    exclude: params.get("exclude")?.split(",").filter(Boolean).slice(0, 20) ?? [],
    text: (params.get("text") ?? "").slice(0, 500),
    limit: Math.min(100, Math.max(1, Number(params.get("limit")) || fallback.limit)),
  };
}
