import { useMutation, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { navigate, useQueryParams } from "raviger";
import { toast } from "sonner";

import Layout from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Badge, Card, Field, Input, Notice, Select, TextArea } from "@/components/ui/primitives";
import { addDays, workingDay } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { API, ApiError, type Band, type ChecklistItem, type Config, type PatientHit } from "@/utils/api";

export default function CourseNew({ facilityId }: { facilityId: string }) {
  const tr = useT();
  return (
    <Layout facilityId={facilityId} title={tr("new_title", "New radiotherapy course")}>
      {(config) =>
        config.permissions?.can_approve_radsmart_course ? (
          <CourseForm facilityId={facilityId} config={config} />
        ) : (
          <Notice kind="warn">{tr("doctor_only", "Only a doctor of this facility can enter a course.")}</Notice>
        )
      }
    </Layout>
  );
}

interface FormState {
  hospital_number: string;
  diagnosis: string;
  total_dose_gy: string;
  fractions: string;
  pattern: string;
  technique: string;
  site: string;
  mobility: string;
  imaging: string;
  machines: string[];
  language: string;
  start_date: string;
  checklist: Record<string, boolean>;
  time_band: Band | "";
  earliest_start: string;
  latest_end: string;
  gap_category: number;
  note: string;
}

function CourseForm({ facilityId, config }: { facilityId: string; config: Config }) {
  const tr = useT();
  const [params] = useQueryParams<{ patient?: string }>();
  const [patient, setPatient] = useState<PatientHit | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [f, setF] = useState<FormState>({
    hospital_number: "",
    diagnosis: "",
    total_dose_gy: "",
    fractions: "",
    pattern: "daily",
    technique: "IMRT",
    site: "HN",
    mobility: "walking",
    imaging: "cbct",
    machines: config.machines.map((m) => m.code),
    language: config.languages[0],
    start_date: workingDay(addDays(config.today, 1)),
    checklist: {},
    time_band: "",
    earliest_start: "",
    latest_end: "",
    gap_category: 2,
    note: "",
  });
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((s) => ({ ...s, [k]: v }));

  useQuery({
    queryKey: ["care_radsmart", "patient", facilityId, params.patient],
    queryFn: async () => {
      const hits = await API.patients(facilityId, "", params.patient);
      if (hits[0]) setPatient(hits[0]);
      return hits;
    },
    enabled: !!params.patient && !patient,
  });

  const tech = config.techniques.find((t) => t.code === f.technique);
  const auto: Record<string, boolean> = {
    complex: !!tech?.complex,
    abc: !!tech?.accessories.includes("ABC"),
    breast_board: !!tech?.accessories.includes("BREAST_BOARD"),
    older: (patient?.age ?? 0) >= 70,
  };
  const ticked = (k: string) => auto[k] || !!f.checklist[k];
  const toggle = (k: string) => {
    const on = !f.checklist[k];
    setF((s) => ({
      ...s,
      checklist: { ...s.checklist, [k]: on },
      gap_category: k === "gap_sensitive" ? (on ? 1 : s.gap_category === 1 ? 2 : s.gap_category) : s.gap_category,
    }));
  };

  const create = useMutation({
    mutationFn: () =>
      API.createCourse({
        facility: facilityId,
        patient: patient!.id,
        hospital_number: f.hospital_number.trim(),
        diagnosis: f.diagnosis.trim(),
        total_dose_gy: f.total_dose_gy,
        fractions: Number(f.fractions),
        pattern: f.pattern,
        technique: f.technique,
        site: f.site,
        mobility: f.mobility,
        imaging: f.imaging,
        machines: f.machines,
        language: f.language,
        start_date: f.start_date,
        checklist: Object.fromEntries(
          Object.entries({ ...f.checklist, ...Object.fromEntries(Object.entries(auto).filter(([, v]) => v)) }).filter(([, v]) => v),
        ),
        time_band: f.checklist.preferred ? f.time_band : "",
        earliest_start: f.checklist.time_window ? f.earliest_start || null : null,
        latest_end: f.checklist.time_window ? f.latest_end || null : null,
        gap_category: f.gap_category,
        note: f.note,
      }),
    onSuccess: (c) => {
      toast.success(tr("course_saved", "Course saved: RAD-SMART is proposing slots"));
      navigate(`/facility/${facilityId}/radsmart/courses/${c.id}`);
    },
    onError: (e: Error) => {
      if (e instanceof ApiError && e.data && typeof e.data === "object") {
        const out: Record<string, string> = {};
        for (const [k, v] of Object.entries(e.data as Record<string, unknown>)) out[k] = Array.isArray(v) ? String(v[0]) : String(v);
        setErrors(out);
      }
      toast.error(e.message);
    },
  });

  const missing = !patient || !f.hospital_number.trim() || !f.diagnosis.trim() || !f.total_dose_gy || !f.fractions || f.machines.length === 0;

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        setErrors({});
        if (!missing) create.mutate();
      }}
    >
      <Card title={tr("sec_patient", "Patient")}>
        <PatientPicker facilityId={facilityId} value={patient} onChange={setPatient} />
        {errors.patient && <p className="mt-1 text-xs text-danger-700">{errors.patient}</p>}
      </Card>

      <Card title={tr("sec_prescription", "Prescription")}>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Field label={tr("f_hospital_number", "Hospital number")}>
            <Input value={f.hospital_number} onChange={(e) => set("hospital_number", e.target.value)} required />
            <Err e={errors.hospital_number} />
          </Field>
          <Field label={tr("f_diagnosis", "Diagnosis")} className="lg:col-span-3">
            <Input value={f.diagnosis} onChange={(e) => set("diagnosis", e.target.value)} placeholder={tr("diagnosis_ph", "e.g. Carcinoma cervix, stage IIB")} required />
            <Err e={errors.diagnosis} />
          </Field>
          <Field label={tr("f_dose", "Total dose (Gy)")}>
            <Input type="number" step="0.01" min="0" value={f.total_dose_gy} onChange={(e) => set("total_dose_gy", e.target.value)} required />
            <Err e={errors.total_dose_gy} />
          </Field>
          <Field
            label={tr("f_fractions", "Number of fractions")}
            hint={tech ? tr("fractions_hint", "Usual for {{tech}}: {{lo}}–{{hi}}", { tech: tech.label, lo: tech.fractions[0], hi: tech.fractions[1] }) : undefined}
          >
            <Input type="number" min="1" max="60" value={f.fractions} onChange={(e) => set("fractions", e.target.value)} required />
            <Err e={errors.fractions} />
          </Field>
          <Field label={tr("f_pattern", "Treatment days")} className="lg:col-span-2">
            <Select value={f.pattern} onChange={(e) => set("pattern", e.target.value)}>
              {config.patterns.map((p) => (
                <option key={p.code} value={p.code}>
                  {p.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={tr("f_technique", "Technique")}>
            <Select value={f.technique} onChange={(e) => set("technique", e.target.value)}>
              {config.techniques.map((t) => (
                <option key={t.code} value={t.code}>
                  {t.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={tr("f_site", "Site")}>
            <Select value={f.site} onChange={(e) => set("site", e.target.value)}>
              {config.sites.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={tr("f_imaging", "Imaging")}>
            <Select value={f.imaging} onChange={(e) => set("imaging", e.target.value)}>
              {config.imaging.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={tr("f_mobility", "Mobility")}>
            <Select value={f.mobility} onChange={(e) => set("mobility", e.target.value)}>
              {config.mobility.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={tr("f_machine", "Preferred machine")}>
            <div className="flex flex-wrap gap-3 pt-1.5">
              {config.machines.map((m) => {
                const ok = !tech || tech.machines.includes(m.code);
                return (
                  <label key={m.code} className={cn("flex items-center gap-1.5 text-sm", !ok && "text-gray-400")}>
                    <input
                      type="checkbox"
                      className="size-4 accent-primary-700"
                      disabled={!ok}
                      checked={ok && f.machines.includes(m.code)}
                      onChange={(e) => set("machines", e.target.checked ? [...f.machines, m.code] : f.machines.filter((x) => x !== m.code))}
                    />
                    {m.name}
                  </label>
                );
              })}
            </div>
            <Err e={errors.machines} />
          </Field>
          <Field label={tr("f_language", "Language for messages")}>
            <Select value={f.language} onChange={(e) => set("language", e.target.value)}>
              {config.languages.map((l) => (
                <option key={l}>{l}</option>
              ))}
            </Select>
          </Field>
          <Field label={tr("f_start", "Start on or after")} hint={tr("start_hint", "RAD-SMART finds the first date with room")}>
            <Input type="date" value={f.start_date} min={config.today} onChange={(e) => set("start_date", e.target.value)} />
            <Err e={errors.start_date} />
          </Field>
          <Field label={tr("f_gap", "Gap category (RCR)")}>
            <Select value={f.gap_category} onChange={(e) => set("gap_category", Number(e.target.value))} disabled={!!f.checklist.gap_sensitive}>
              {config.gap_categories.map((g) => (
                <option key={g.code} value={g.code}>
                  {g.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Card>

      <Card title={tr("sec_checklist", "Priority checklist")}>
        <div className="grid gap-6 lg:grid-cols-2">
          <ChecklistGroup
            title={tr("hard", "Hard constraints (always kept)")}
            items={config.checklist.hard}
            ticked={ticked}
            auto={auto}
            onToggle={toggle}
            extra={(it) =>
              it.key === "time_window" && ticked("time_window") ? (
                <div className="mt-2 flex flex-wrap gap-3">
                  <Field label={tr("f_earliest", "Not before")}>
                    <Input type="time" value={f.earliest_start} onChange={(e) => set("earliest_start", e.target.value)} className="w-32" />
                  </Field>
                  <Field label={tr("f_latest", "Finished by")}>
                    <Input type="time" value={f.latest_end} onChange={(e) => set("latest_end", e.target.value)} className="w-32" />
                  </Field>
                  <Err e={errors.earliest_start || errors.latest_end} />
                </div>
              ) : null
            }
          />
          <ChecklistGroup
            title={tr("soft", "Soft goals (met where possible)")}
            items={config.checklist.soft}
            ticked={ticked}
            auto={auto}
            onToggle={toggle}
            extra={(it) =>
              it.key === "preferred" && ticked("preferred") ? (
                <div className="mt-2">
                  <Field label={tr("f_band", "Part of the day")}>
                    <Select value={f.time_band} onChange={(e) => set("time_band", e.target.value as Band | "")} className="w-56">
                      <option value="">{tr("choose", "Choose…")}</option>
                      {config.bands.map((b) => (
                        <option key={b.code} value={b.code}>
                          {b.label}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Err e={errors.time_band} />
                </div>
              ) : null
            }
          />
        </div>
        <div className="mt-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{tr("always", "Always applied")}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {config.checklist.always.map((a) => (
              <Badge key={a}>{a}</Badge>
            ))}
          </div>
        </div>
      </Card>

      <Card title={tr("sec_note", "Note for the team")}>
        <TextArea value={f.note} onChange={(e) => set("note", e.target.value)} rows={2} />
      </Card>

      {Object.keys(errors).length > 0 && errors.non_field_errors && <Notice kind="error">{errors.non_field_errors}</Notice>}
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => history.back()}>
          {tr("cancel", "Cancel")}
        </Button>
        <Button type="submit" disabled={missing || create.isPending}>
          {create.isPending ? tr("saving", "Saving…") : tr("save_propose", "Save and propose slots")}
        </Button>
      </div>
    </form>
  );
}

function Err({ e }: { e?: string }) {
  return e ? <span className="text-xs text-danger-700">{e}</span> : null;
}

function ChecklistGroup({
  title,
  items,
  ticked,
  auto,
  onToggle,
  extra,
}: {
  title: string;
  items: ChecklistItem[];
  ticked: (k: string) => boolean;
  auto: Record<string, boolean>;
  onToggle: (k: string) => void;
  extra: (it: ChecklistItem) => React.ReactNode;
}) {
  return (
    <fieldset>
      <legend className="text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</legend>
      <div className="mt-2 flex flex-col gap-2">
        {items.map((it) => (
          <div key={it.key} className={cn("rounded-md border px-3 py-2", ticked(it.key) ? "border-primary-300 bg-primary-50" : "border-gray-200")}>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-0.5 size-4 accent-primary-700" checked={ticked(it.key)} disabled={!!auto[it.key]} onChange={() => onToggle(it.key)} />
              <span>
                {it.label}
                {it.auto && <span className="block text-xs text-gray-500">{it.auto}</span>}
              </span>
            </label>
            {extra(it)}
          </div>
        ))}
      </div>
    </fieldset>
  );
}

function PatientPicker({ facilityId, value, onChange }: { facilityId: string; value: PatientHit | null; onChange: (p: PatientHit | null) => void }) {
  const tr = useT();
  const [q, setQ] = useState("");
  const hits = useQuery({
    queryKey: ["care_radsmart", "patients", facilityId, q],
    queryFn: () => API.patients(facilityId, q),
    enabled: !value,
  });
  const list = useMemo(() => hits.data ?? [], [hits.data]);
  if (value)
    return (
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-semibold text-gray-900">{value.name}</p>
          <p className="text-xs text-gray-500">
            {value.age} {tr("years_old", "years")} · {value.gender}
          </p>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={() => onChange(null)}>
          {tr("change", "Change")}
        </Button>
      </div>
    );
  return (
    <div className="flex flex-col gap-2">
      <div className="relative max-w-md">
        <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-gray-400" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={tr("search_patient", "Search patients under this facility's care")} className="pl-8" />
      </div>
      <div className="flex max-h-60 flex-col divide-y divide-gray-100 overflow-y-auto rounded-md border border-gray-200">
        {list.map((p) => (
          <button type="button" key={p.id} onClick={() => onChange(p)} className="flex justify-between px-3 py-2 text-left text-sm hover:bg-gray-50">
            <span className="font-medium">{p.name}</span>
            <span className="text-xs text-gray-500">
              {p.age} · {p.gender}
            </span>
          </button>
        ))}
        {!list.length && <p className="px-3 py-2 text-sm text-gray-500">{tr("no_patients", "No patients found")}</p>}
      </div>
    </div>
  );
}
