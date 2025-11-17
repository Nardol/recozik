import "server-only";

import { serverFetch } from "./api";
import type { WhoAmI } from "../api";

export async function serverFetchWhoami(token: string): Promise<WhoAmI> {
  return serverFetch("/whoami", token);
}
