import type { components, operations } from "./generated";

export type GameDto = components["schemas"]["Game"];
export type SearchResponseDto = components["schemas"]["GameSearchResponse"];
export type RecommendRequestDto = components["schemas"]["RecommendationRequest"];
export type RecommendationDto = components["schemas"]["Recommendation"];
export type RecommendResponseDto = components["schemas"]["RecommendationResponse"];
export type ApiErrorDto = components["schemas"]["ErrorResponse"];
export type SearchQueryDto = operations["searchGames"]["parameters"]["query"];
