import { useTranslation } from "react-i18next";

/**
 * Plugin strings live in public/locale/en.json under the `radsmart__` prefix;
 * the English text is also the default, so a missing key still reads well.
 */
export function useT() {
  const { t } = useTranslation();
  return (key: string, english: string, values?: Record<string, string | number>) =>
    t(`radsmart__${key}`, { defaultValue: english, ...values });
}
