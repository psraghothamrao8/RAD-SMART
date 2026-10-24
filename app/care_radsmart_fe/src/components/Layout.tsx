import { Activity, CalendarClock, ClipboardPlus, ListChecks, MessageCircle, ScanLine, Wrench } from "lucide-react";
import type { PropsWithChildren, ReactNode } from "react";
import { Link, usePath } from "raviger";

import { Badge, Notice, Spinner } from "@/components/ui/primitives";
import { useT } from "@/lib/i18n";
import { useConfig } from "@/lib/useConfig";
import { cn } from "@/lib/utils";
import type { Config } from "@/utils/api";

import Page from "./Page";

/** Every RAD-SMART page: a header, the section tabs and the page body. */
export default function Layout({
  facilityId,
  title,
  actions,
  children,
}: {
  facilityId: string;
  title: ReactNode;
  actions?: ReactNode;
  children: (config: Config) => ReactNode;
}) {
  const tr = useT();
  const path = usePath() ?? "";
  const { data: config, isLoading, error } = useConfig(facilityId);
  const base = `/facility/${facilityId}/radsmart`;
  const tabs = [
    { href: base, label: tr("tab_today", "Today"), icon: CalendarClock, active: path === base },
    { href: `${base}/courses`, label: tr("tab_courses", "Courses"), icon: ListChecks, active: path.startsWith(`${base}/courses`) && !path.endsWith("/new") },
    { href: `${base}/courses/new`, label: tr("tab_new", "New course"), icon: ClipboardPlus, active: path.endsWith("/courses/new") },
    { href: `${base}/breakdown`, label: tr("tab_breakdown", "Breakdown"), icon: Wrench, active: path.startsWith(`${base}/breakdown`) },
    { href: `${base}/messages`, label: tr("tab_messages", "Messages"), icon: MessageCircle, active: path.startsWith(`${base}/messages`) },
    { href: `${base}/checkin`, label: tr("tab_checkin", "Check-in"), icon: ScanLine, active: path.startsWith(`${base}/checkin`) },
    { href: `${base}/insights`, label: tr("tab_insights", "Insights"), icon: Activity, active: path.startsWith(`${base}/insights`) },
  ];
  return (
    <Page>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 p-4 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-primary-700">RAD-SMART</p>
            <h1 className="text-xl font-semibold text-gray-900">{title}</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {config?.sarvam && (
              <Badge tone="blue" title={tr("sarvam_hint", "Translations, voice notes and plain-language explanations")}>
                {tr("sarvam_on", "Sarvam AI on")}
              </Badge>
            )}
            {config?.demo && (
              <Badge tone="violet" title={tr("demo_hint", "This server shows synthetic patients only")}>
                {tr("demo", "Demonstration data")}
              </Badge>
            )}
            {actions}
          </div>
        </div>
        <nav className="-mx-1 flex gap-1 overflow-x-auto border-b border-gray-200 px-1" aria-label="RAD-SMART">
          {tabs.map(({ href, label, icon: Icon, active }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium",
                active ? "border-primary-700 text-primary-800" : "border-transparent text-gray-600 hover:text-gray-900",
              )}
            >
              <Icon className="size-4" />
              {label}
            </Link>
          ))}
        </nav>
        {isLoading && <Spinner label={tr("loading", "Loading…")} />}
        {error && <Notice kind="error" title={tr("load_failed", "RAD-SMART could not be reached")}>{String((error as Error).message)}</Notice>}
        {config && !config.permissions?.can_view_radsmart && (
          <Notice kind="warn">{tr("no_access", "You do not have access to RAD-SMART in this facility.")}</Notice>
        )}
        {config && config.permissions?.can_view_radsmart && children(config)}
      </div>
    </Page>
  );
}

export function PageLink({ href, children, className }: PropsWithChildren<{ href: string; className?: string }>) {
  return (
    <Link href={href} className={cn("font-medium text-primary-700 hover:underline", className)}>
      {children}
    </Link>
  );
}
