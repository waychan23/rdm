import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { useParams, useSearchParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Lozenge from "@atlaskit/lozenge";
import { RadioGroup } from "@atlaskit/radio";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";

import { cardBorder } from "../components/cardBorder";
import { apiLocale } from "../i18n";
import type { OrgUser } from "../types";

interface ConsentInfo {
  client: { client_id: string; client_name: string | null };
  scopes: string[];
  selectable_users: OrgUser[];
}

const styles = cssMap({
  wrap: {
     minHeight: "100vh",
     display: "flex",
     alignItems: "center",
     justifyContent: "center",
     backgroundColor: "var(--ds-surface-sunken)",
     padding: "var(--ds-space-300)",
  },
  actions: {
    justifyContent: "flex-end"
  },
  card: {
     width: "440px",
     maxWidth: "100%",
     padding: "var(--ds-space-300)",
     backgroundColor: "var(--ds-surface)",
     borderRadius: "var(--ds-radius-small)",
     boxShadow: "var(--ds-shadow-raised)",
  },
});

// Consent is authenticated by the one-shot capability key in the URL (§17);
// it must not use the Bearer-injecting api client.
async function consentFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { "Accept-Language": apiLocale(), ...(init?.headers ?? {}) },
  });
  const payload = await res.json();
  if (!res.ok) {
     throw new Error(payload?.error?.message ?? `HTTP ${res.status}`);
  }
  return payload.data as T;
}

export default function ConsentPage() {
  const { t } = useTranslation("auth");
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const key = params.get("key") ?? "";
  const [info, setInfo] = useState<ConsentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [userId, setUserId] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
     void (async () => {
       try {
         const data = await consentFetch<ConsentInfo>(
           `/oauth/consent/${id}?key=${encodeURIComponent(key)}`,
         );
         setInfo(data);
         setUserId(
           data.selectable_users.find((u) => u.type === "human")?.id ??
             data.selectable_users[0]?.id ??
             "",
         );
       } catch (e) {
         setError((e as Error).message);
       }
     })();
  }, [id, key]);

  const decide = async (allow: boolean) => {
     if (loading) return;
     setLoading(true);
     try {
       const body = allow
         ? { decision: "allow", act_as_user_id: userId }
         : { decision: "deny" };
       const result = await consentFetch<{ redirect_to: string }>(
         `/oauth/consent/${id}/decision?key=${encodeURIComponent(key)}`,
         {
           method: "POST",
           headers: { "Content-Type": "application/json" },
           body: JSON.stringify(body),
         },
       );
       window.location.assign(result.redirect_to);
     } catch (e) {
       setError((e as Error).message);
       setLoading(false);
     }
  };

  return (
     <Box xcss={styles.wrap} testId="page-consent">
       <Box xcss={styles.card} style={cardBorder}>
         {error ? (
           <Stack space="space.200" testId="consent-error">
             <Heading size="large" as="h1">{t("consent.error.title")}</Heading>
             <Text>{error}</Text>
             <Text size="small" color="color.text.subtlest">
               {t("consent.error.hint")}
             </Text>
           </Stack>
         ) : !info ? (
           <Inline space="space.150" alignBlock="center" testId="consent-loading">
             <Spinner size="small" />
             <Text color="color.text.subtlest">{t("consent.loading")}</Text>
           </Inline>
         ) : (
           <Stack space="space.200" testId="consent-form">
             <Heading size="large" as="h1">{t("consent.title")}</Heading>
             <Text>
               <Trans
                 ns="auth"
                 i18nKey="consent.request"
                 values={{
                   client: info.client.client_name || info.client.client_id,
                   scopes: info.scopes.join(" "),
                 }}
                 components={{ bold: <Text weight="bold">{""}</Text> }}
               />
             </Text>
             {info.selectable_users.length > 0 && (
               <Stack space="space.100">
                 <Text size="small" color="color.text.subtlest">
                    {t("consent.identityPrompt")}
                 </Text>
                 <RadioGroup
                   options={info.selectable_users.map((u) => ({
                     name: "consent-user",
                     value: u.id,
                     label: (
                       <Inline space="space.100" alignBlock="center">
                         <span>{u.name}</span>
                         <Lozenge appearance={u.type === "agent" ? "warning" : "default"}>
                           {u.type}
                         </Lozenge>
                         {u.manager_user_id && (
                           <Text size="small" color="color.text.subtlest">
                              {t("consent.managedByHuman")}
                           </Text>
                         )}
                       </Inline>
                     ),
                   }))}
                   value={userId}
                   onChange={(e) => setUserId(e.currentTarget.value)}
                 />
               </Stack>
             )}
             <Inline space="space.100" xcss={styles.actions}>
               <Button testId="consent-deny" onClick={() => decide(false)} isLoading={loading}>
                 {t("consent.deny")}
               </Button>
               <Button
                 appearance="primary"
                 testId="consent-allow"
                 onClick={() => decide(true)}
                 isLoading={loading}
               >
                 {t("consent.allow")}
               </Button>
             </Inline>
           </Stack>
         )}
       </Box>
     </Box>
  );
}
