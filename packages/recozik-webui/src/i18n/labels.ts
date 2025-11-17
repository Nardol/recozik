import { MessageKey } from "./messages";

export const FEATURE_LABELS: Record<string, MessageKey> = {
  identify: "feature.identify",
  identify_batch: "feature.identify_batch",
  rename: "feature.rename",
  audd: "feature.audd",
  musicbrainz_enrich: "feature.musicbrainz_enrich",
};

export const ROLE_LABELS: Record<string, MessageKey> = {
  admin: "role.admin",
  operator: "role.operator",
  readonly: "role.readonly",
};

export const QUOTA_LABELS: Record<string, MessageKey> = {
  acoustid_lookup: "quota.acoustid_lookup",
  musicbrainz_enrich: "quota.musicbrainz_enrich",
  audd_standard_lookup: "quota.audd_standard_lookup",
};
