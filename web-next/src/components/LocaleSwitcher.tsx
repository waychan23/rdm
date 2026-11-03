import Select from "@atlaskit/select";
import { useTranslation } from "react-i18next";

import { apiLocale, setLocale, type Locale } from "../i18n";

interface LocaleOption {
  label: string;
  value: Locale;
}

const WIDTH = 128;

/** Topbar language switch; persists to localStorage and refetches data. */
export default function LocaleSwitcher() {
  const { t } = useTranslation("common");
  const options: LocaleOption[] = [
    { label: t("locale.zhCN"), value: "zh-CN" },
    { label: t("locale.en"), value: "en" },
  ];
  const current = options.find((option) => option.value === apiLocale()) ?? options[0];
  return (
    <div style={{ width: WIDTH }}>
      <Select<LocaleOption>
        options={options}
        value={current}
        onChange={(option) => {
          if (option) void setLocale(option.value);
        }}
        spacing="compact"
        appearance="subtle"
        isSearchable={false}
        label={t("locale.label")}
        testId="locale-switcher"
        menuPortalTarget={document.body}
        menuPosition="fixed"
      />
    </div>
  );
}
