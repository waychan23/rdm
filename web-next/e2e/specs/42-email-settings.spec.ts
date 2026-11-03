import { createServer, type AddressInfo, type Socket } from "node:net";

import { expect, test } from "../support/fixtures";

// RDM-121/122: system-level SMTP settings in the Web UI, and mailbox sends to
// external email addresses through that server. A tiny in-process SMTP server
// captures the real message the backend delivers.
interface CapturedMail {
  from: string;
  to: string[];
  data: string;
}

async function startSmtpServer(): Promise<{
  port: number;
  messages: CapturedMail[];
  close: () => Promise<void>;
}> {
  const messages: CapturedMail[] = [];
  const server = createServer((socket: Socket) => {
    let buffer = "";
    let inData = false;
    let current: CapturedMail = { from: "", to: [], data: "" };
    socket.write("220 e2e-smtp\r\n");
    socket.on("data", (chunk) => {
      buffer += chunk.toString("utf8");
      for (;;) {
        if (inData) {
          const end = buffer.indexOf("\r\n.\r\n");
          if (end === -1) return;
          current.data = buffer.slice(0, end);
          buffer = buffer.slice(end + 5);
          inData = false;
          messages.push(current);
          socket.write("250 queued\r\n");
          continue;
        }
        const newline = buffer.indexOf("\r\n");
        if (newline === -1) return;
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 2);
        const upper = line.toUpperCase();
        if (upper.startsWith("EHLO")) {
          socket.write("250-e2e-smtp\r\n250 OK\r\n");
        } else if (upper.startsWith("HELO")) {
          socket.write("250 OK\r\n");
        } else if (upper.startsWith("MAIL FROM:")) {
          current = { from: line.slice(10).trim(), to: [], data: "" };
          socket.write("250 OK\r\n");
        } else if (upper.startsWith("RCPT TO:")) {
          current.to.push(line.slice(8).trim());
          socket.write("250 OK\r\n");
        } else if (upper === "DATA") {
          inData = true;
          socket.write("354 End data with <CR><LF>.<CR><LF>\r\n");
        } else if (upper === "QUIT") {
          socket.write("221 Bye\r\n");
          socket.end();
        } else {
          socket.write("250 OK\r\n");
        }
      }
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  return {
    port,
    messages,
    close: () =>
      new Promise<void>((resolve) => {
        server.close(() => resolve());
      }),
  };
}

test("email settings page saves SMTP config and sends to an external address", async ({
  api,
  app,
  page,
  asUser,
}) => {
  const smtp = await startSmtpServer();
  try {
    await page.goto(`${app.baseURL}/email-settings`);
    await expect(page.getByTestId("page-email-settings")).toBeVisible();

    await page.getByLabel("启用外部邮件").check();
    await page.getByTestId("email-settings-host").fill("127.0.0.1");
    await page.getByTestId("email-settings-port").fill(String(smtp.port));
    await page.getByRole("combobox", { name: "加密方式" }).click();
    await page.getByRole("option", { name: "不加密", exact: true }).click();
    await page.getByTestId("email-settings-from-address").fill("rdm@example.com");
    await page.getByTestId("email-settings-from-name").fill("RDM e2e");
    await page.getByTestId("email-settings-save").click();
    await expect(page.getByText("邮件设置已保存")).toBeVisible();

    // The saved configuration survives a reload and never echoes the password.
    await page.reload();
    await expect(page.getByTestId("email-settings-host")).toHaveValue("127.0.0.1");
    await expect(page.getByTestId("email-settings-from-address")).toHaveValue(
      "rdm@example.com",
    );

    const projectKey = await api.createSandboxProject();
    const subject = `external-${Date.now()}`;
    await page.goto(`${app.baseURL}/projects/${projectKey}/mailbox`);
    await page.getByTestId("mailbox-compose-button").click();
    await page.locator("#mail-to").fill("client@example.com");
    await page.locator("#mail-to").press("Enter");
    await page.getByTestId("mailbox-compose-subject").fill(subject);
    await page.getByTestId("mailbox-compose-body").fill("external email body");
    await page.getByTestId("mailbox-compose-submit").click();
    await expect(page.getByTestId("mailbox-compose-dialog")).toHaveCount(0);

    await expect.poll(() => smtp.messages.length).toBe(1);
    const mail = smtp.messages[0];
    expect(mail.from).toContain("rdm@example.com");
    expect(mail.to.join(",")).toContain("client@example.com");
    expect(mail.data).toContain(subject);
    expect(mail.data).toContain("external email body");

    // The sent folder lists the external address next to internal recipients.
    await page.goto(
      `${app.baseURL}/projects/${projectKey}/mailbox?folder=sent&unread_only=false`,
    );
    await expect(page.getByText(subject)).toBeVisible();
    await expect(page.getByText("client@example.com")).toBeVisible();

    // Non-admins are bounced away from the admin-only page.
    const worker = await asUser("alice");
    await worker.goto(`${app.baseURL}/email-settings`);
    await expect(worker).toHaveURL(/\/projects$/);
  } finally {
    await smtp.close();
  }
});
