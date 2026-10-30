import { test as base, expect, type BrowserContext, type Page } from "@playwright/test";

import { Api } from "./api";
import {
  loadContext,
  storageStateFor,
  type E2EContext,
  type UserName,
} from "./context";

interface Fixtures {
  app: E2EContext;
  api: Api;
  /** Open a separate browser session logged in as one of the seeded humans. */
  asUser: (name: UserName) => Promise<Page>;
}

export const test = base.extend<Fixtures>({
  // Default session for every spec is the org owner (project owner).
  context: async ({ browser }, use) => {
    const context = await browser.newContext({
      storageState: storageStateFor("owner"),
      viewport: { width: 1600, height: 900 },
    });
    await use(context);
    await context.close();
  },
  page: async ({ context }, use) => {
    const page = await context.newPage();
    await use(page);
  },
  app: async ({}, use) => {
    await use(loadContext());
  },
  api: async ({ app }, use) => {
    await use(new Api(app));
  },
  asUser: async ({ browser }, use) => {
    const contexts: BrowserContext[] = [];
    const open = async (name: UserName): Promise<Page> => {
      const context = await browser.newContext({
        storageState: storageStateFor(name),
        viewport: { width: 1600, height: 900 },
      });
      contexts.push(context);
      return context.newPage();
    };
    await use(open);
    await Promise.all(contexts.map((context) => context.close()));
  },
});

export { expect };
