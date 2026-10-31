const auth = {
  login: {
    title: "Sign in to rd-manager",
    username: "Username",
    usernamePlaceholder: "Enter username",
    password: "Password",
    remember: "Remember me (stay signed in for 7 days)",
    submit: "Sign in",
    bootstrapHint:
      "On first deployment, use the bootstrap-url in the service startup log to set the Org Owner password. If you forget it, run rdm account recover-owner on the deployment host to regenerate it.",
    redirecting: "Redirecting to sign in…",
    failed: "Sign-in failed",
  },
  callback: {
    title: "Sign-in not completed",
    retry: "Sign in again",
    completing: "Completing sign-in…",
    errors: {
      missingCode: "The authorization code or state is missing.",
      invalidCallback: "The sign-in callback is invalid. Please try again.",
    },
  },
  setPassword: {
    missingTicket: {
      title: "Invalid link",
      body: "The ticket parameter is missing. Ask an administrator for a new password setup link.",
    },
    checking: "Validating link…",
    checkFailed: {
      title: "Couldn't validate the link",
      body: "There was a network or service error. Please try again later.",
    },
    retry: "Retry",
    form: {
      title: "Set a password",
      hint: "Password must be 8–128 characters. Keep it safe.",
      newPassword: "New password",
      confirmPassword: "Confirm new password",
      submit: "Save",
    },
    invalid: {
      consumed: {
        title: "This link is no longer valid",
        body: "The link has already been used or was invalidated when it was regenerated.",
      },
      expired: {
        title: "This link has expired",
        body: "The password setup link is no longer valid.",
      },
      userMissing: {
        title: "Invalid link",
        body: "The user associated with this link is no longer available.",
      },
      notFound: {
        title: "Invalid link",
        body: "The link does not exist or has been replaced.",
      },
      nextStep: {
        bootstrap:
          "Check the bootstrap-url in the service startup log, or ask an administrator to run rdm account recover-owner to regenerate it.",
        fallback: "Ask an administrator for a new password setup link and try again.",
      },
    },
    done: {
      title: "Password set",
      successTitle: "Done",
      successBody: "You can now sign in with your new password.",
      gotoLogin: "Go to sign in",
    },
    errors: {
      mismatch: "The passwords don't match.",
      failed: "Couldn't set the password",
    },
  },
  consent: {
    error: {
      title: "Authorization unavailable",
      hint: "The authorization link expires in 10 minutes and can only be used once. Please start the sign-in again from your terminal.",
    },
    loading: "Loading authorization request…",
    title: "Authorize access to rdm",
    request:
      "Application <bold>{{client}}</bold> is requesting access to your rdm workspace (scope: {{scopes}}).",
    identityPrompt: "Authorize as",
    managedByHuman: "Managed by a human account",
    deny: "Deny",
    allow: "Allow",
  },
};

export default auth;
