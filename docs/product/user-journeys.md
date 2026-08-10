# User Journeys

Status: draft

## Primary Journey

### 1. Choose a reference game

Player searches by title and selects one unambiguous Steam game. Search results expose enough identity to avoid similarly named games. Keyboard and touch interactions receive equal support.

Success: player reaches intent editing with correct seed and without account creation.

### 2. Clarify valued qualities

Product presents a short, plain-language summary of candidate qualities. Player selects what mattered and can change emphasis across mechanics, narrative, vibe, and structure or loop. Detailed concepts remain collapsed until requested.

Success: player can explain what choices mean without knowing retrieval terminology.

### 3. Inspect recommendations

Product returns ranked games with concise match reasons, meaningful metadata, and visible confidence degradation where applicable. Result order stays stable for unchanged intent and build.

Success: player identifies at least one plausible game and understands why it appeared.

### 4. Audit a result

Player opens contribution details for a result. Product separates positive factors, negative factors, filters, evidence, and non-semantic priors. Claims do not exceed available evidence.

Success: player can distinguish semantic fit from quality or popularity policy.

### 5. Refine intent

Player changes a lane weight, concept inclusion, or exclusion. Product preserves seed and remaining choices, then reranks with clear loading and error states.

Success: player can predict direction of change and observe a coherent result update.

### 6. Continue elsewhere

Player opens Steam or shares stable intent where URL size and privacy permit.

Success: destination and shared state match selected game and normalized intent.

## Sparse-Evidence Journey

When seed or candidate evidence is incomplete:

1. Product identifies reduced confidence without implying low game quality.
2. Unsupported controls are unavailable or clearly marked.
3. Retrieval may use documented fallback mode.
4. Explanations use safe metadata-level language rather than unsupported semantic claims.
5. Player can still inspect results or choose another seed.

## No-Result Journey

When exclusions or narrow intent remove all candidates:

1. Product states which constraint class caused exhaustion where known.
2. No hidden relaxation changes intent.
3. Player receives direct controls to remove an exclusion or broaden emphasis.
4. Original intent remains recoverable.

## Failure Journey

For timeout, incompatible build, invalid request, or unavailable service:

1. Product distinguishes corrective input errors from retryable service errors.
2. Existing intent remains intact.
3. Error copy avoids exposing internal details.
4. Retry does not duplicate feedback or mutate intent.

## Responsive Behavior

Mobile flow uses one primary task per view region and keeps result reasons available without hover. Desktop may place intent and results side by side but preserves reading and keyboard order. Neither layout hides required actions behind pointer-only interaction.

## Research Questions

- Which plain-language descriptions best distinguish four semantic lanes?
- How many initial choices produce useful control without stalling progress?
- Do contribution values improve trust, or do ranked factors communicate better?
- When does an advanced control become necessary rather than distracting?
- Which confidence language informs without discouraging exploration?
