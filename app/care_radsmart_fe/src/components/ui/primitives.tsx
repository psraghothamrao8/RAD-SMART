import { AlertTriangle, CheckCircle2, Info, Loader2, XCircle } from "lucide-react";
import type { ComponentProps, PropsWithChildren, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/** Small building blocks styled like CARE's own cards, inputs and pills. */

export function Card({ className, children, title, action }: PropsWithChildren<{ className?: string; title?: ReactNode; action?: ReactNode }>) {
  return (
    <section className={cn("rounded-lg border border-gray-200 bg-white shadow-xs", className)}>
      {(title || action) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

const TONES = {
  gray: "bg-gray-100 text-gray-700 border-gray-200",
  green: "bg-primary-100 text-primary-800 border-primary-200",
  amber: "bg-warning-100 text-warning-900 border-warning-200",
  red: "bg-danger-100 text-danger-800 border-danger-200",
  violet: "bg-alert-100 text-alert-800 border-alert-200",
  blue: "bg-sky-100 text-sky-800 border-sky-200",
} as const;
export type Tone = keyof typeof TONES;

export function Badge({ tone = "gray", children, className, title }: PropsWithChildren<{ tone?: Tone; className?: string; title?: string }>) {
  return (
    <span
      title={title}
      className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium", TONES[tone], className)}
    >
      {children}
    </span>
  );
}

export function Field({ label, hint, children, className }: PropsWithChildren<{ label: ReactNode; hint?: ReactNode; className?: string }>) {
  return (
    <label className={cn("flex flex-col gap-1 text-sm", className)}>
      <span className="font-medium text-gray-800">{label}</span>
      {children}
      {hint && <span className="text-xs text-gray-500">{hint}</span>}
    </label>
  );
}

const control =
  "h-9 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900 shadow-xs focus:border-primary-500 focus:outline-hidden focus:ring-2 focus:ring-primary-500/20 disabled:bg-gray-50 disabled:text-gray-500";

export function Input(props: ComponentProps<"input">) {
  return <input {...props} className={cn(control, props.className)} />;
}

export function Select({ children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={cn(control, "pr-8", props.className)}>
      {children}
    </select>
  );
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn(control, "h-auto min-h-16 py-2", props.className)} />;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-gray-500">
      <Loader2 className="size-4 animate-spin" />
      {label}
    </div>
  );
}

const NOTICE = {
  info: { cls: "border-sky-200 bg-sky-50 text-sky-900", icon: Info },
  ok: { cls: "border-primary-200 bg-primary-50 text-primary-900", icon: CheckCircle2 },
  warn: { cls: "border-warning-300 bg-warning-50 text-warning-900", icon: AlertTriangle },
  error: { cls: "border-danger-200 bg-danger-50 text-danger-900", icon: XCircle },
} as const;

export function Notice({ kind = "info", title, children, action }: PropsWithChildren<{ kind?: keyof typeof NOTICE; title?: ReactNode; action?: ReactNode }>) {
  const { cls, icon: Icon } = NOTICE[kind];
  return (
    <div className={cn("flex flex-wrap items-start gap-x-3 gap-y-2 rounded-lg border px-4 py-3 text-sm", cls)} role={kind === "error" ? "alert" : "status"}>
      <Icon className="mt-0.5 size-4 shrink-0" />
      {/* On a phone the action drops below the text instead of squeezing it into a column. */}
      <div className="min-w-0 flex-1 basis-[calc(100%-1.75rem)] sm:basis-0">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn(title && "mt-0.5")}>{children}</div>}
      </div>
      {action && <div className="ml-7 shrink-0 sm:ml-0">{action}</div>}
    </div>
  );
}

export function Stat({ label, value, sub, tone }: { label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: "good" | "bad" }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
      <p className="text-xs font-medium text-gray-500">{label}</p>
      <p className={cn("mt-1 text-2xl font-semibold tabular-nums text-gray-900", tone === "good" && "text-primary-700", tone === "bad" && "text-danger-700")}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-500">{sub}</p>}
    </div>
  );
}

export function Empty({ children }: PropsWithChildren) {
  return <p className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">{children}</p>;
}

/** `stack`: below md the rows become cards (the row lays out its own cells) instead of a table that scrolls sideways. */
export function Table({ head, children, className, stack }: PropsWithChildren<{ head: ReactNode[]; className?: string; stack?: boolean }>) {
  return (
    <div className={cn("overflow-x-auto rounded-lg border border-gray-200", stack && "max-md:overflow-visible max-md:border-0", className)}>
      <table className={cn("w-full min-w-max text-left text-sm", stack && "max-md:block max-md:min-w-0")}>
        <thead className={cn("bg-gray-50 text-xs font-medium text-gray-600", stack && "max-md:hidden")}>
          <tr>
            {head.map((h, i) => (
              <th key={i} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className={cn("divide-y divide-gray-100 bg-white", stack && "max-md:flex max-md:flex-col max-md:gap-2 max-md:divide-y-0 max-md:bg-transparent")}>
          {children}
        </tbody>
      </table>
    </div>
  );
}
