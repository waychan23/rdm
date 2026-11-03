// Atlaskit components consult `@atlaskit/platform-feature-flags` while
// rendering. Without a resolver it falls back to the feature-gate JS client,
// which is uninitialized in this app and logs:
//   "Client must be initialized before using this method"
// for gates such as `platform_increased-contrast-themes`.
//
// rdm uses no Atlaskit feature gates, so resolve every gate to false. This is
// the same global `setBooleanFeatureFlagResolver` writes; setting it directly
// avoids depending on a transitive package just for one call.
//
// One exception — `platform_design_system_team_portal_logic_r18_fix`: the
// legacy portal appends its container during render but removes it from the
// effect cleanup. StrictMode's dev double-invoke runs that cleanup without a
// second render, so the container stays detached and every ModalDialog renders
// into nothing until an unrelated re-render re-appends it (dialogs look tens of
// seconds late). The gated implementation creates the container inside the
// effect and is StrictMode-safe, so enable it in every environment (RDM-132).

const ENABLED_GATES = new Set(["platform_design_system_team_portal_logic_r18_fix"]);

type PlatformFeatureFlagsGlobal = {
  __PLATFORM_FEATURE_FLAGS__?: {
    booleanResolver?: (key: string) => boolean;
  };
};

const target = globalThis as typeof globalThis & PlatformFeatureFlagsGlobal;
target.__PLATFORM_FEATURE_FLAGS__ = {
  ...(target.__PLATFORM_FEATURE_FLAGS__ ?? {}),
  booleanResolver: (key) => ENABLED_GATES.has(key),
};

export {};
