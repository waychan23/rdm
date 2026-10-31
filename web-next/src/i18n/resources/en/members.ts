const members = {
  page: {
    title: "Members · {{projectKey}}",
    addMember: "Add member",
  },
  agent: {
    auto: "Auto",
    disabled: "Disabled",
    inherited: "Inherits project permissions from their human",
    status: {
      enabled: "Enabled",
      disabled: "Disabled",
    },
  },
  empty: {
    header: "This project has no members yet",
    description: "Use “Add member” in the top-right corner to bring organization users into the project.",
  },
  table: {
    aria: "Project members",
    name: "Name",
    type: "Type",
    roles: "Project roles",
    webhook: "Webhook",
    active: "Active",
    actions: "Actions",
  },
  ownerBadge: "Project owner",
  member: {
    roles: "Roles",
    remove: "Remove",
    status: {
      enabled: "Enabled",
      disabled: "Disabled",
    },
  },
  removeDialog: {
    title: "Remove from project",
    confirm: "Remove",
    body: "Remove {{name}} from the project? {{extra}}",
    extra: "Their {{count}} agent(s) will also be removed from the project.",
  },
  errors: {
    addFailed: "Failed to add member",
    saveFailed: "Failed to save",
    removeFailed: "Failed to remove member",
  },
  notices: {
    saved: "Saved",
  },
  addDialog: {
    title: "Add project member",
    userLabel: "Organization user",
    userHint: "Agents owned by this user join the project automatically; agents cannot be added on their own.",
    userPlaceholder: "Select an organization human user",
    roleLabel: "Project roles",
    roleHint: "The project owner can only be changed via “Transfer project owner”, not granted or removed here.",
    rolePlaceholder: "Select project roles",
    cancel: "Cancel",
    add: "Add",
  },
  editDialog: {
    title: "Project roles · {{name}}",
    fixedRole: "Fixed role",
    rolePlaceholder: "Select project roles",
    ownerHintLocked: "The project owner role cannot be edited here; use “Transfer project owner” instead.",
    ownerHintOther: "The project owner role is not set here; transfer it on the project settings page.",
    cancel: "Cancel",
    save: "Save",
  },
};

export default members;
