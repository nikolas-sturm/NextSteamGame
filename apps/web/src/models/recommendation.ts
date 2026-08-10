export type LaneKey = "mechanics" | "narrative" | "vibe" | "loop";
export type SeedGame = { id:number; title:string; year:number|null; descriptor:string; steamUrl:string; imageUrl:string|null; weight:number };
export type Intent = { seeds:SeedGame[]; lanes:Record<LaneKey,number>; include:string[]; exclude:string[]; text:string; limit:number };
export type Evidence = { lane:LaneKey|null; label:string; contribution:number; sources:Array<{source:string;excerpt:string}> };
export type Recommendation = { id:number; rank:number; title:string; year:number|null; score:number; summary:string; tags:string[]; imageUrl:string|null; steamUrl:string; evidence:Evidence[] };
export type ResultMetadata = { buildId:string; retrievalMode:string; reducedConfidence:boolean; degradationReason:string|null };
