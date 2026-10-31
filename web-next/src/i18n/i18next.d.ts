import "i18next";

import type { Resources } from "./resources/zh-CN";

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "common";
    resources: Resources;
  }
}
