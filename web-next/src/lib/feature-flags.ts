// Atlaskit components consult `@atlaskit/platform-feature-flags` while
// rendering. Without a resolver it falls back to the feature-gate JS client,
// which is uninitialized in this app and logs:
//   "Client must be initialized before using this method"
// for gates such as `platform_increased-contrast-themes`.
//
// rdm uses no Atlaskit feature gates, so resolve every gate to false. This is
// the same global `setBooleanFeatureFlagResolver` writes; setting it directly
// avoids depending on a transitive package just for one call.

type PlatformFeatureFlagsGlobal = {
  __PLATFORM_FEATURE_FLAGS__?: {
    booleanResolver?: (key: string) => boolean;
  };
};

const target = globalThis as typeof globalThis & PlatformFeatureFlagsGlobal;
target.__PLATFORM_FEATURE_FLAGS__ = {
  ...(target.__PLATFORM_FEATURE_FLAGS__ ?? {}),
  booleanResolver: () => false,
};

export {};
