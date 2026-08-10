# Domain Glossary

Status: draft

| Term | Definition |
| --- | --- |
| Game ID | Stable product identity backed by a Steam appid. |
| Build ID | Identity of one complete, immutable published dataset and runtime artifact set. |
| Model ID | Exact model family, revision, instruction, dimension, dtype, and relevant runtime configuration. |
| Seed | Game selected as positive reference for recommendation intent. |
| Intent | Normalized collection of seeds, lane weights, included concepts, excluded concepts, and optional future text. |
| Semantic lane | Independently represented aspect of game identity: mechanics, narrative, vibe, or structure and gameplay loop. |
| Mechanics | Actions, systems, interactions, and rule-driven challenges central to play. |
| Narrative | Story form, themes, character relationships, choices, and delivery structure. |
| Vibe | Emotional tone, sensory character, pacing feel, and experiential atmosphere. |
| Structure and loop | Repeated activity cycle, progression cadence, run or session shape, and long-term organization. |
| Identity concept | Canonical concept that captures a meaningful part of game identity beyond broad storefront genre. |
| Niche anchor | Rare or unusually specific concept whose presence can strongly distinguish relevant candidates. |
| Genre spine | Broad structural genre compatibility signal used as context, not sole evidence of fit. |
| Candidate | Game admitted by retrieval for online scoring. |
| Candidate edge | Offline source-to-candidate relation containing retrieval provenance and features needed by online scoring. |
| Contribution | Named, numeric effect of one scoring policy on final score. |
| Filter | Explicit rule that removes a candidate instead of changing score. |
| Evidence ID | Stable reference connecting a claim or concept to retained upstream evidence. |
| Retrieval mode | Candidate source used for request, such as static graph, dynamic vector search, or sparse fallback. |
| Reduced confidence | Declared condition where evidence or candidate coverage limits certainty without asserting poor game quality. |
| Canonicalization | Reviewed process that maps interpreted concepts into a versioned ontology while preserving lineage. |
| Artifact schema version | Version governing binary and tabular build formats. |
| API compatibility version | Version declaring which service contract can consume a published build. |
