import "server-only";

import { serverFetch } from "./api";
import type { WhoAmI } from "../api";

export async function serverFetchWhoami(): Promise<WhoAmI> {
  return serverFetch("/whoami");
}
