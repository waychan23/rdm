const emailSettings = {
  title: "Email settings",
  subtitle:
    "Configure the SMTP server and sender used for outbound email. Organization owners and user managers only; the password is stored encrypted and never returned.",
  sections: {
    server: "SMTP server",
    sender: "Sender",
    test: "Send a test message",
  },
  fields: {
    enabled: "Enable outbound email",
    smtpHost: "SMTP host",
    smtpPort: "Port",
    security: "Security",
    username: "Username",
    password: "Password",
    fromAddress: "Sender address",
    fromName: "Sender name",
    testTo: "Test recipient",
  },
  security: {
    none: "None",
    starttls: "STARTTLS",
    ssl: "SSL/TLS",
  },
  password: {
    saved: "A password is saved; leave blank to keep it",
    empty: "No password set",
    set: "Enter a new password",
    clear: "Clear the saved password",
  },
  hint: "When sending mail, recipients that look like email addresses are delivered through this server; project members and groups still use the in-app mailbox.",
  actions: {
    save: "Save",
    saving: "Saving…",
    test: "Send test message",
    testing: "Sending…",
  },
  notify: {
    saved: "Email settings saved",
    saveFailed: "Save failed",
    loadFailed: "Failed to load",
    testSent: "Test message sent to {{to}}",
    testFailed: "Test message failed",
  },
};

export default emailSettings;
