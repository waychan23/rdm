const systemSettings = {
  title: "System settings",
  subtitle: "Organization-wide settings that apply to every project.",
  hint: "The Web frontend origin decides which site opens work item links in agent messages and emails. Link origin priority: project .rdm/project.json > user ~/.rdm/config.json > this organization setting > default (MCP server origin).",
  sections: {
    webOrigin: "Web frontend origin",
  },
  fields: {
    webOrigin: "Web frontend origin",
    webOriginHint:
      "Decides which site opens work item links in agent messages and emails. Leave empty to use the default origin.",
    webOriginPlaceholder: "e.g. https://rdm.example.com",
    fallback: "Current default origin: {{origin}}",
  },
  actions: {
    save: "Save",
    saving: "Saving…",
    useCurrentOrigin: "Use current page origin",
  },
  notify: {
    saved: "System settings saved.",
    saveFailed: "Failed to save system settings",
  },
};

export default systemSettings;
