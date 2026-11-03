const mailbox = {
  title: {
    default: "Mailbox",
    withProject: "Mailbox · {{project}}",
  },
  folder: {
    inbox: "Inbox",
    archived: "Archived",
    sent: "Sent",
  },
  sort: {
    newest: "Newest first",
    oldest: "Oldest first",
  },
  view: {
    flat: "Flat",
    thread: "Threads",
  },
  filters: {
    unreadOnly: "Unread only",
  },
  actions: {
    markRead: "Mark read",
    markSelectedRead: "Mark read",
    archive: "Archive",
    unarchive: "Move to inbox",
    delete: "Delete",
    reply: "Reply",
    loadMore: "Load more",
    compose: "Compose",
    groups: "Group mailboxes",
    createGroup: "Create group mailbox",
    cancel: "Cancel",
    send: "Send",
    close: "Close",
  },
  fields: {
    recipients: "Recipients",
    subject: "Subject",
    body: "Body (Markdown)",
    groupName: "Name",
    members: "Members",
  },
  placeholders: {
    allProjects: "All projects",
    allIdentities: "All identities",
    search: "Search subject/body",
    selectRecipients: "Select members/groups, or type an external email",
    selectMembers: "Select members",
  },
  empty: {
    header: "No messages",
    description: "New messages will appear here.",
  },
  message: {
    recipients: "To: {{names}}",
    refs: "Related: ",
  },
  thread: {
    count: "{{count}} in thread",
    expand: "Expand",
    collapse: "Collapse",
  },
  owner: {
    mine: "My mailbox",
    agent: "{{name}} (agent)",
    unknown: "Unknown identity",
  },
  identity: {
    me: "Me ({{name}})",
    agent: "{{name}} (agent)",
  },
  compose: {
    replyTitle: "Reply",
    newTitle: "New message",
    externalHint:
      "Type a full email address to send to an external mailbox (an admin must configure SMTP in Email settings first).",
    createExternal: "Send to {{email}}",
  },
  group: {
    title: "Group mailboxes",
    description:
      "A group mailbox delivers to several members at once; each member still receives their own copy.",
    none: "No group mailboxes yet",
    noMembers: "No members",
    option: "{{name}} (group mailbox)",
  },
  notify: {
    markFailed: "Failed to mark as read",
    archived: "Archived",
    unarchived: "Moved to inbox",
    archiveFailed: "Failed to archive",
    deleted: "Deleted",
    deleteFailed: "Failed to delete",
    loadGroupsFailed: "Failed to load group mailboxes",
    selectProject: "Select a project at the top first",
    selectProjectToSend: "Select a project at the top before sending",
    groupNameRequired: "Group mailbox name is required",
    groupCreated: "Group mailbox created",
    createFailed: "Failed to create",
    recipientsRequired: "Recipients, subject and body are required",
    replied: "Replied",
    sent: "Sent",
    sendFailed: "Failed to send",
  },
  listSeparator: ", ",
};

export default mailbox;
