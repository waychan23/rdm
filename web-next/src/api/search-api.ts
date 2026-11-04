// Cross-entity search.

import { api } from "../lib/api";
import type { SearchHit } from "../types";
import { encode } from "./query";

export function search(term: string): Promise<SearchHit[]> {
  return api
    .get<SearchHit[]>(`/search?q=${encode(term.trim())}`)
    .then((res) => res.data);
}
