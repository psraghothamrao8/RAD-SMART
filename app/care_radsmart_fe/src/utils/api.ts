const STAFF_TOKEN_KEY = "care_access_token";
const BASE_PATH = "/api/care_radsmart";

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, data: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

function readErrorMessage(status: number, data: unknown) {
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    const detail = record.detail ?? record.non_field_errors;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && typeof detail[0] === "string") return detail[0];
    const first = Object.entries(record)[0];
    if (first) {
      const [field, value] = first;
      const text = Array.isArray(value) ? value[0] : value;
      if (typeof text === "string") return `${field.replace(/_/g, " ")}: ${text}`;
    }
  }
  if (Array.isArray(data) && typeof data[0] === "string") return data[0];
  return `Request failed with status ${status}`;
}

export async function request<T>(
  endpoint: string,
  method: Method = "GET",
  body?: unknown,
  queryParams?: Record<string, string | number | boolean | undefined | null>,
): Promise<T> {
  let url = `${window.CARE_API_URL}${BASE_PATH}${endpoint}`;
  if (queryParams) {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(queryParams)) {
      if (value !== undefined && value !== null && value !== "") search.append(key, String(value));
    }
    const qs = search.toString();
    if (qs) url += `?${qs}`;
  }
  const token = localStorage.getItem(STAFF_TOKEN_KEY);
  const response = await fetch(url, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) throw new ApiError(response.status, data, readErrorMessage(response.status, data));
  return data as T;
}

/** A binary response (a voice note) as an object URL; the caller revokes it. */
export async function requestBlobUrl(endpoint: string, queryParams?: Record<string, string>): Promise<string> {
  const qs = queryParams ? `?${new URLSearchParams(queryParams)}` : "";
  const token = localStorage.getItem(STAFF_TOKEN_KEY);
  const response = await fetch(`${window.CARE_API_URL}${BASE_PATH}${endpoint}${qs}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(response.status, data, readErrorMessage(response.status, data));
  }
  return URL.createObjectURL(await response.blob());
}

// ------------------------------------------------------------------ types
export interface Option {
  code: string;
  label: string;
}

export interface ChecklistItem {
  key: string;
  label: string;
  auto?: string;
  fields?: string[];
}

export interface MachineInfo {
  id: string;
  code: string;
  name: string;
  status: "online" | "offline";
  status_since?: string;
  expected_back?: string | null;
  note?: string;
  sessions?: number;
  new_starts?: number;
  after_17?: number;
  last_end?: string;
  booked_min?: number;
  new_start_room_min?: number;
}

export interface Config {
  enabled: boolean;
  demo: boolean;
  today: string;
  now: number;
  techniques: (Option & { complex: boolean; accessories: string[]; machines: string[]; fractions: [number, number] })[];
  sites: Option[];
  patterns: Option[];
  mobility: Option[];
  imaging: Option[];
  gap_categories: { code: number; label: string }[];
  languages: string[];
  checklist: { hard: ChecklistItem[]; soft: ChecklistItem[]; always: string[] };
  actions: Record<string, string>;
  day: {
    start: number;
    regular_end: number;
    hard_end: number;
    new_start_latest_end: number;
    new_start_reserve_min: number;
    downtime_short_max_min: number;
    blocks: { start: number; end: number; label: string }[];
    urgent_holds: { machine: string; start: number; minutes: number }[];
  };
  machines: MachineInfo[];
  /** Sarvam AI is connected: translations, voice notes and plain-language explanations. */
  sarvam?: boolean;
  /** A Telegram bot is set up (demonstrations): messages can be sent from the server. */
  telegram?: boolean;
  permissions?: {
    can_view_radsmart: boolean;
    can_operate_radsmart: boolean;
    can_approve_radsmart_course: boolean;
  };
}

export interface SessionRow {
  id: string;
  course: string;
  patient: string;
  patient_name: string;
  hospital_number: string;
  age: number;
  diagnosis: string;
  technique: string;
  fraction: number;
  fractions: number;
  kind: "new_start" | "routine" | "moved" | "added";
  machine: string;
  start: number;
  time: string;
  planned_start: number;
  planned_time: string;
  moved_today: boolean;
  report: string;
  minutes: number;
  status: "scheduled" | "arrived" | "in_room" | "done" | "sent_home" | "postponed" | "missed" | "cancelled";
  arrived_at: string | null;
  in_room_at: string | null;
  out_at: string | null;
  flags: string[];
  language: string;
  gap_category: number;
  note: string;
  demo: boolean;
  date?: string;
}

export interface Check {
  rules_checked: number;
  violations: string[];
  sessions_checked: number;
  unplanned: string[];
}

export interface DayView {
  date: string;
  sessions: SessionRow[];
  machines: MachineInfo[];
  check: Check;
  counts: Record<string, number>;
  approval: { status: string; by: string | null; at: string | null } | null;
}

export interface Slot {
  machine: string;
  machine_name: string;
  start: number;
  time: string;
  minutes: number;
  report?: string;
  date?: string;
  note?: string;
}

export interface Proposal {
  ok: boolean;
  problem: string | null;
  start_date: string;
  end_date: string | null;
  treatment_days: number;
  report_lead_min: number;
  reasons: string[];
  first: Slot | null;
  standing: Slot | null;
  standing2: Slot | null;
  alternatives: Slot[];
  from_date?: string;
  wanted?: string;
}

export interface Course {
  id: string;
  patient: string;
  patient_name: string;
  hospital_number: string;
  diagnosis: string;
  total_dose_gy: string;
  fractions: number;
  pattern: string;
  technique: string;
  technique_label: string;
  site: string;
  mobility: string;
  imaging: string;
  machines: string[];
  checklist: Record<string, boolean>;
  preferred_time: string | null;
  earliest_start: string | null;
  latest_end: string | null;
  gap_category: number;
  language: string;
  start_date: string;
  status: "draft" | "approved" | "completed" | "cancelled";
  approved_by: string | null;
  approved_at: string | null;
  proposal: Proposal | Record<string, never>;
  first: Partial<Slot>;
  slots: { from: string; machine: string; start: number; start2: number | null }[];
  minutes: number;
  dates: string[];
  note: string;
  demo: boolean;
  flags: string[];
  sessions_done: number;
}

export type CourseInput = Partial<Omit<Course, "id" | "status" | "flags">> & { facility: string; patient: string };

export interface TriageAction {
  id: string;
  patient_name: string;
  hospital_number: string;
  fraction: number;
  fractions: number;
  time: string;
  report: string;
  flags: string[];
  language: string;
  gap_category: number;
  kind: string;
  action: string;
  label: string;
  new_start: number | null;
  new_time: string | null;
  new_report: string | null;
  present: boolean;
  why: string;
  message: string | null;
}

export interface TriageProposal {
  machine: string;
  machine_name: string;
  date: string;
  fault_start: number;
  fault_time: string;
  expected_minutes: number;
  restart: string | null;
  back_today: boolean;
  rule: string;
  allowed_end: string;
  minutes_to_free: number;
  overtime_min: number;
  counts: Record<string, number>;
  already_treated: number;
  actions: TriageAction[];
  check: Check | null;
  solve_seconds: number;
}

export interface Triage {
  id: string;
  machine: string;
  date: string;
  fault_start: number;
  expected_minutes: number;
  proposal: TriageProposal;
  status: "proposed" | "approved" | "rejected" | "superseded";
  decided_by: string | null;
  decided_at: string | null;
  note: string;
  created_date: string;
}

export interface SlotRequest {
  id: string;
  course: string;
  patient_name: string;
  hospital_number: string;
  current: string | null;
  from_date: string;
  wanted: string;
  reason: string;
  proposal: Proposal;
  status: "proposed" | "approved" | "rejected";
  decided_by: string | null;
}

export interface Insights {
  from: string;
  to: string;
  sessions_timed: number;
  wait_median: number | null;
  wait_p90: number | null;
  within_15_pct: number | null;
  late_60_pct: number | null;
  session_minutes_median: number | null;
  sent_home: number;
  postponed: number;
  added: number;
  by_day: { date: string; n: number; wait_median: number; wait_p90: number; within_15_pct: number }[];
  kpi: { name: string; baseline_min: number; target_min: number; baseline_source: string };
}

export interface Message {
  id: string;
  course: string;
  patient_name: string;
  hospital_number: string;
  date: string;
  kind: "course" | "slot" | "breakdown";
  action: string;
  language: string;
  text: string;
  local_text: string;
  local_status: "pending" | "ok" | "english" | "failed";
  local_note: string;
  status: "to_send" | "sent" | "cancelled";
  sent_by: string | null;
  sent_at: string | null;
  voice: boolean;
  link: string;
  whatsapp: string;
  /** "telegram" when the server sent it there. */
  channel: string;
  /** The patient linked Telegram: the server can send this message there. */
  telegram: boolean;
  created_date: string;
}

export interface PatientReply {
  id: string;
  course: string;
  patient_name: string;
  hospital_number: string;
  session: string | null;
  time: string | null;
  kind: "on_way" | "late" | "not_today" | "other_time";
  label: string;
  minutes: number | null;
  wanted: string | null;
  reason: string;
  slot_request: string | null;
  slot_request_status: SlotRequest["status"] | null;
  status: "open" | "done";
  handled_by: string | null;
  channel: "page" | "telegram";
  created_date: string;
}

export type MessageStep = "sent" | "cancel" | "translate" | "send-telegram";

export interface PatientLink {
  url: string;
  code: string;
  qr: string;
  whatsapp: string;
  /** The bot link (empty without Telegram), its QR code, and whether the patient opened it. */
  telegram: string;
  telegram_qr: string;
  telegram_linked: boolean;
}

export interface Explanation {
  text: string;
  source: string;
  note: string;
  language: string;
  local_text: string | null;
  local_note: string;
}

export interface PatientHit {
  id: string;
  name: string;
  gender: string;
  age: number;
}

// --------------------------------------------------------------- endpoints
export const API = {
  config: (facility?: string) => request<Config>("/config/", "GET", undefined, { facility }),
  day: (facility: string, date?: string) => request<DayView>("/day/", "GET", undefined, { facility, date }),
  approveDay: (facility: string, date: string) => request<{ status: string; check: Check }>("/day/", "POST", { facility, date }),
  machineStatus: (id: string, body: { status: "online" | "offline"; expected_minutes?: number; note?: string; time?: string }) =>
    request<{ machine: MachineInfo; triage: Triage | null }>(`/machines/${id}/status/`, "POST", body),
  session: (id: string, step: "arrive" | "room" | "done" | "undo" | "send-home", note?: string) =>
    request<SessionRow>(`/sessions/${id}/${step}/`, "POST", note ? { note } : {}),
  courses: (facility: string, params: { status?: string; q?: string; patient?: string } = {}) =>
    request<Course[]>("/courses/", "GET", undefined, { facility, ...params }),
  course: (facility: string, id: string) => request<Course>(`/courses/${id}/`, "GET", undefined, { facility }),
  createCourse: (body: CourseInput) => request<Course>("/courses/", "POST", body, { facility: body.facility }),
  updateCourse: (facility: string, id: string, body: Partial<CourseInput>) =>
    request<Course>(`/courses/${id}/`, "PATCH", body, { facility }),
  propose: (facility: string, id: string, start_date?: string, earliest = true) =>
    request<Proposal>(`/courses/${id}/propose/`, "POST", { start_date, earliest }, { facility }),
  approve: (facility: string, id: string, proposal: Proposal, chosen_time?: string) =>
    request<Course>(`/courses/${id}/approve/`, "POST", { proposal, chosen_time }, { facility }),
  cancel: (facility: string, id: string) => request<Course>(`/courses/${id}/cancel/`, "POST", {}, { facility }),
  courseSessions: (facility: string, id: string) =>
    request<SessionRow[]>(`/courses/${id}/sessions/`, "GET", undefined, { facility }),
  slotRequest: (facility: string, id: string, body: { from_date: string; wanted: string; reason?: string }) =>
    request<SlotRequest>(`/courses/${id}/slot-request/`, "POST", body, { facility }),
  slotRequests: (facility: string, status?: string) =>
    request<SlotRequest[]>("/slot-requests/", "GET", undefined, { facility, status }),
  decideSlot: (facility: string, id: string, decision: "approve" | "reject", time?: string) =>
    request<SlotRequest>(`/slot-requests/${id}/${decision}/`, "POST", { time }, { facility }),
  triages: (facility: string, date?: string) => request<Triage[]>("/triage/", "GET", undefined, { facility, date }),
  retriage: (facility: string, machine: string, expected_minutes: number, time?: string) =>
    request<Triage>("/triage/", "POST", { facility, machine, expected_minutes, time }),
  decideTriage: (facility: string, id: string, decision: "approve" | "reject", note?: string) =>
    request<Triage>(`/triage/${id}/${decision}/`, "POST", { note }, { facility }),
  insights: (facility: string, from?: string, to?: string) =>
    request<Insights>("/insights/", "GET", undefined, { facility, from, to }),
  patients: (facility: string, q: string, id?: string) => request<PatientHit[]>("/patients/", "GET", undefined, { facility, q, id }),
  messages: (facility: string, params: { date?: string; course?: string; status?: string } = {}) =>
    request<Message[]>("/messages/", "GET", undefined, { facility, ...params }),
  messageStep: (id: string, step: MessageStep) => request<Message>(`/messages/${id}/${step}/`, "POST", {}),
  messageAudio: (id: string, english = false) => requestBlobUrl(`/messages/${id}/audio/`, english ? { lang: "en" } : undefined),
  replies: (facility: string, date?: string, status?: string) =>
    request<PatientReply[]>("/replies/", "GET", undefined, { facility, date, status }),
  replyDone: (id: string) => request<PatientReply>(`/replies/${id}/done/`, "POST", {}),
  checkIn: (facility: string, code: string) => request<SessionRow & { already: boolean }>("/checkin/", "POST", { facility, code }),
  patientLink: (facility: string, id: string) =>
    request<PatientLink>(`/courses/${id}/patient-link/`, "GET", undefined, { facility }),
  explain: (facility: string, id: string, body: { proposal?: Proposal; chosen_time?: string; language?: string }) =>
    request<Explanation>(`/courses/${id}/explain/`, "POST", body, { facility }),
  seedDemo: (facility: string, census: number, time?: string) =>
    request<Record<string, unknown>>("/demo/seed/", "POST", { facility, census, time }),
};
