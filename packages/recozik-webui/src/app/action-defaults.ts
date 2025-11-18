import type { LoginState, UploadState } from "./action-types";

export const DEFAULT_LOGIN_STATE: LoginState = {
  status: "idle",
  message: "",
};

export const DEFAULT_UPLOAD_STATE: UploadState = {
  status: "idle",
  code: undefined,
  message: "",
  job: null,
};
