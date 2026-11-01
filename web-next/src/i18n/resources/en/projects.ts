const projects = {
  list: {
    title: "Projects",
    create: "New project",
    createFailed: "Couldn't create project",
    loadFailed: "Couldn't load projects",
    loadFailedDescription: "The project list couldn't be loaded. Refresh the page and try again.",
    empty: "No accessible projects yet",
    emptyCanCreate:
      "Click \"New project\" in the top right to create your first project. You'll become its project manager.",
    emptyNoPermission:
      "Ask an Org Owner or project director to create a project and add you as a member.",
  },
  status: {
    archived: "Archived",
    active: "Active",
  },
  badge: {
    projectManager: "Project manager",
  },
  create: {
    title: "New project",
    key: "Key",
    name: "Name",
    description: "Description",
    cancel: "Cancel",
    submit: "Create",
  },
  overview: {
    title: "{{key}} overview",
    go: {
      board: "Board",
      backlog: "Work items",
      sprints: "Sprints",
      mailbox: "Mailbox",
    },
    stats: {
      total: "All work items",
      open: "Open",
      mine: "My open items",
      members: "Members",
    },
    byKind: "By type",
    byStatus: "By status",
    activeSprint: "Active sprint · {{name}}",
    activeSprintTotal: "{{total}} items",
  },
  backlog: {
    title: "Work items",
    view: {
      flat: "Flat",
      tree: "Tree",
    },
    create: "New",
    filter: {
      status: "Status",
      completion: "Completion",
      completed: "Completed",
      uncompleted: "Open",
      assignee: "Assignee",
      reviewer: "Reviewer",
      search: "Search title or review comment",
      mine: "Mine",
    },
    loadFailed: "Couldn't load work items",
    loadFailedDescription:
      "The work item list couldn't be loaded. Adjust the filters or refresh the page and try again.",
    empty: "No work items match",
    emptyDescription: "Adjust the filters, or click \"New\" to create one.",
    treeTruncated:
      "The tree view loads at most {{limit}} work items. Narrow the filters to see the full hierarchy.",
    rootCount: "{{n}} top-level",
  },
  board: {
    title: "Board",
    showTerminal: "Show terminal columns",
    empty: "No workflow columns for this type",
    stepRequiredTitle: "Use the work item detail to run this step",
    stepRequiredBody:
      "Moving {{id}} from {{from}} to {{to}} requires choosing a named step or adding a note.",
    transitionFailed: "Transition failed",
    transitionFailedBlocking: "{{message}} (blocked by: {{blocking}})",
  },
  workspaces: {
    title: "Workspaces · {{key}}",
    create: "Register workspace",
    saveSuccess: "Saved",
    saveFailed: "Couldn't save workspace",
    saveRetry: "Try again in a moment",
    deleteFailed: "Couldn't delete workspace",
    empty: "No workspaces yet",
    emptyDescription:
      "Register repositories, docs, or design resources so the team can jump to them quickly.",
    tableLabel: "Workspaces",
    col: {
      name: "Name",
      kind: "Type",
      location: "Location",
      actions: "Actions",
    },
    edit: "Edit",
    delete: "Delete",
    form: {
      editTitle: "Edit workspace",
      createTitle: "Register workspace",
      name: "Name",
      kind: "Type",
      location: "Location",
      locationHint:
        "Optional. Supports http(s), git SSH, mount paths, s3://, and other formats.",
      locationPlaceholder: "Optional, e.g. https://… / git@github.com:org/repo.git",
      description: "Description",
      cancel: "Cancel",
      save: "Save",
    },
    deleteConfirm: {
      title: "Confirm deletion",
      body: "Delete this workspace? It can be restored from the soft delete.",
      cancel: "Cancel",
      confirm: "Delete",
    },
  },
  search: {
    title: "Search",
    placeholder: "Search work items, comments, messages, and artifacts",
    submit: "Search",
    hint: "Enter keywords to search",
    hintDescription: "Supports substring and multi-keyword search.",
    empty: "No matches",
    emptyDescription: "Nothing related to \"{{query}}\" was found.",
  },
};

export default projects;
