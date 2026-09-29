export interface Course {
  id: string;
  code: string;
  title: string;
  semester: string;
  academic_year: string;
  total_classes: number;
  period_duration: number;
  total_available_minutes: number;
  teacher_name?: string;
  section_name?: string;
  units_count: number;
  topics_count: number;
  concepts_count: number;
  my_role: "owner" | "admin" | "co_teacher" | "viewer";
  created_at?: string;
}

export interface OutcomeDraft {
  code: string;
  description: string;
  bloom_level: string;
}

export interface ConceptDraft {
  id?: string;
  name: string;
  description?: string;
  difficulty: number;
  importance: number;
  concept_type: string;
  prerequisites: string[];
  bloom_level?: string;
}

export interface TopicDraft {
  id?: string;
  title: string;
  description?: string;
  estimated_minutes: number;
  concepts: ConceptDraft[];
}

export interface UnitDraft {
  id?: string;
  unit_number: number;
  title: string;
  description?: string;
  topics: TopicDraft[];
}

export interface ExtractedCurriculum {
  course_name: string;
  course_code: string;
  semester?: string;
  academic_year?: string;
  suggested_total_classes?: number;
  suggested_period_duration?: number;
  outcomes: OutcomeDraft[];
  units: UnitDraft[];
  confidence_score: number;
  extraction_notes: string[];
}

export interface GraphNode {
  id: string;
  name: string;
  topic_id: string;
  topic_title: string;
  unit_number: number;
  difficulty: number;
  importance: number;
  concept_type: string;
  status: "mastered" | "weak" | "bottleneck" | "pending" | "moderate";
  avg_score?: number;
  downstream_count: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship_type: string;
}

export interface CurriculumGraph {
  course_id: string;
  course_title: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  bottlenecks: string[];
}

export interface TopicAllocation {
  topic_id: string;
  unit_number: number;
  topic_title: string;
  estimated_minutes: number;
  allocated_minutes: number;
  priority_score: number;
  recommended_periods: number;
  reason_codes: string[];
  explanation: string;
  key_concepts: string[];
}

export interface CourseOptimization {
  course_id: string;
  total_available_minutes: number;
  total_allocated_minutes: number;
  revision_budget_minutes: number;
  assessment_budget_minutes: number;
  unallocated_buffer_minutes: number;
  time_pressure_status: "healthy" | "balanced" | "high_pressure";
  topic_allocations: TopicAllocation[];
  formula_explanation: { model?: string; invariant?: string; weights?: Record<string, number>; [key: string]: unknown };
}

export interface PeriodPhase {
  phase_name: string;
  duration_minutes: number;
  method_name: string;
  activity_description: string;
  concept_ref?: string;
}

export interface NextClassPlan {
  session_number: number;
  topic_id: string;
  topic_title: string;
  unit_number: number;
  period_duration: number;
  target_concepts: string[];
  revision_needed: boolean;
  revision_minutes: number;
  revision_concept?: string;
  revision_reason?: string;
  recommended_methods: string[];
  phases: PeriodPhase[];
  total_phase_minutes: number;
  why_explanation: string;
  learning_gain_prediction: number;
}

export interface LessonPlan {
  id: string;
  session_id: string;
  session_number: number;
  topic_id: string;
  topic_title: string;
  title: string;
  status: string;
  teacher_overridden: boolean;
  phases: PeriodPhase[];
  learning_objectives: string[];
  worked_examples: string[];
  active_exercises: string[];
  misconceptions: string[];
  assessment_questions: string[];
  resources: LessonResource[];
  version: number;
  created_at?: string;
}

export type ResourceKind = "slides" | "video" | "link" | "dataset" | "code" | "formula";

export interface LessonResource {
  kind: ResourceKind;
  title: string;
  url?: string | null;
  content?: string | null;
  language?: string | null;
}

export interface AssessmentItem {
  id: string;
  title: string;
  assessment_type: string;
  max_marks: number;
  scheduled_date?: string;
  status: string;
  questions_count: number;
  performances: Array<{
    concept_id: string;
    concept_name: string;
    average_score: number;
    weakness_flag: boolean;
    common_errors?: string;
  }>;
}

export interface AlertItem {
  id: string;
  severity: "danger" | "warning" | "info" | "success";
  title: string;
  message: string;
  action_label?: string;
  action_route?: string;
}

export interface CourseAnalytics {
  course_id: string;
  progress_percentage: number;
  completed_sessions: number;
  total_sessions: number;
  planned_minutes: number;
  actual_minutes_taught: number;
  remaining_minutes: number;
  concept_health: {
    strong: number;
    moderate: number;
    weak: number;
    bottleneck: number;
  };
  teaching_method_effectiveness: Array<{
    method_name: string;
    category: string;
    concept_type: string;
    baseline_score: number;
    post_score: number;
    observed_gain: number;
    sessions_tracked: number;
  }>;
  alerts: AlertItem[];
}

export interface TableColumn {
  name: string;
  type: string;
  primary_key: boolean;
  foreign_key?: string;
  nullable: boolean;
}

export interface TableSchemaInfo {
  table_name: string;
  description: string;
  row_count: number;
  normal_form: string;
  columns: TableColumn[];
}

export interface QueryDemoResult {
  query_id: string;
  title: string;
  category: string;
  sql: string;
  purpose: string;
  sql_features: string[];
  requires?: string | null;
  params: Record<string, unknown>;
  row_count: number;
  columns: string[];
  rows: Record<string, unknown>[];
  execution_time_ms: number;
}

// ── Auth ───────────────────────────────────────────
export interface SessionUserResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
}

// ── Lesson plan review & history (optimistic locking, MongoDB versions) ──
export interface LessonPlanReview {
  expected_version: number;
  status?: "approved" | "rejected" | "modified";
  phases?: PeriodPhase[];
  learning_objectives?: string[];
  worked_examples?: string[];
  active_exercises?: string[];
  misconceptions?: string[];
  assessment_questions?: string[];
  resources?: LessonResource[];
  change_note?: string;
}

export interface LessonPlanVersion {
  version: number;
  document_id: string;
  parent_document_id: string | null;
  change_note: string | null;
  edited_by: string;
  edited_at: string;
  is_current: boolean;
}

export interface LessonPlanDiff {
  from_version: number;
  to_version: number;
  phases: { index: number; change: "added" | "removed" | "modified"; phase: string; fields?: Record<string, { from: unknown; to: unknown }> }[];
  content: Record<string, { added: string[]; removed: string[] }>;
  change_note: string | null;
}

// ── Sessions (timetable + post-class record) ──
export interface ClassSessionItem {
  id: string;
  session_number: number;
  scheduled_date: string | null;
  duration_minutes: number;
  status: "scheduled" | "in_progress" | "completed" | "cancelled";
  topic_id: string | null;
  topic_title: string | null;
  unit_number: number | null;
  lesson_plan_status: string | null;
  lesson_plan_version: number | null;
  logged: {
    method_name: string | null;
    actual_minutes: number;
    student_engagement_rating: number;
    completion_rate: number;
    teacher_notes: string | null;
    conducted_at: string;
  } | null;
}

export interface SessionLogInput {
  method_id?: string | null;
  actual_minutes: number;
  student_engagement_rating?: number;
  completion_rate?: number;
  teacher_notes?: string;
  topic_completed?: boolean;
  carry_over?: boolean;
}

export interface SessionLogResult {
  carried_over: { to_session: number | null; dropped_topic: string | null; plans_removed: number } | null;
  session_number: number;
  status: string;
  teaching_session_id: string;
  topic_title: string | null;
  topic_status: string | null;
  lesson_plan_status: string | null;
}

export interface TeachingMethodItem {
  id: string;
  name: string;
  category: string;
  description: string | null;
}

// ── Curriculum graph snapshots (MongoDB) ──
export interface GraphVersion {
  version: number;
  reason: string;
  stats: { units: number; topics: number; concepts: number; edges: number };
  created_at: string;
}

export interface GraphDiff {
  from_version: number;
  to_version: number;
  concepts_added: string[];
  concepts_removed: string[];
  concepts_changed: { concept: string; changes: Record<string, { from: unknown; to: unknown }> }[];
  prerequisites_added: { prerequisite: string; concept: string }[];
  prerequisites_removed: { prerequisite: string; concept: string }[];
}

// ── DBMS showcase ──
export interface QueryMeta {
  id: string;
  title: string;
  category: string;
  purpose: string;
  sql_features: string[];
  requires?: string | null;
}

export interface DatabaseObjects {
  views: { name: string; kind: string; definition: string }[];
  routines: { name: string; kind: string; arguments: string; returns: string; language: string; security_definer: boolean; definition: string }[];
  triggers: { name: string; table_name: string; function_name: string; definition: string }[];
  policies: { name: string; table_name: string; command: string; roles: string; using_expression: string }[];
  indexes: { name: string; table_name: string; definition: string; is_unique: boolean; is_primary: boolean; is_partial: boolean; scans: number }[];
  roles: { name: string; can_login: boolean; bypass_rls: boolean; table_privileges: string; tables_granted: number }[];
}

export interface ConsoleResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  truncated: boolean;
  execution_time_ms: number;
  executed_as: string;
  scope: string;
}

export interface LabScenario {
  id: string;
  title: string;
}

export interface LabStep {
  step: number;
  txn: string;
  sql: string;
  result: unknown;
  ok: boolean;
  at_ms: number;
}

export interface LabRun {
  timeline: LabStep[];
  isolation_level?: string;
  strategy?: string;
  first_read?: number;
  second_read?: number;
  repeatable?: boolean;
  expected?: number;
  actual?: number;
}

export interface LabResult {
  scenario: string;
  title: string;
  conclusion: string;
  final_balances: Record<string, number>;
  timeline?: LabStep[];
  runs?: LabRun[];
  outcome?: Record<string, string>;
}

export interface AggregationMeta {
  id: string;
  title: string;
  collection: string;
  purpose: string;
  stages: string[];
}

export interface AggregationResult extends AggregationMeta {
  pipeline: Record<string, unknown>[];
  row_count: number;
  rows: Record<string, unknown>[];
}

export interface ConsistencyReport {
  scope: string;
  lesson_plans_checked: number;
  dangling_pointers: { lesson_plan_id: string; missing_document_id: string }[];
  orphan_documents: { document_id: string; course_id: string; reason: string }[];
  orphan_graph_snapshots: { course_id: string }[];
  stale_graph_snapshots: { course_id: string; sql_concepts: number; snapshot_concepts: number | null }[];
  consistent: boolean;
}

// ── Curriculum builder ──
export type ConceptType = "conceptual" | "procedural" | "problem_solving" | "practical" | "analytical" | "revision";

export interface BuilderConcept {
  id: string;
  name: string;
  difficulty: number;
  importance: number;
  concept_type: ConceptType;
  prerequisite_ids: string[];
}

export interface BuilderTopic {
  id: string;
  title: string;
  status: string;
  allocated_minutes: number;
  estimated_minutes: number;
  concepts: BuilderConcept[];
}

export interface BuilderUnit {
  id: string;
  unit_number: number;
  title: string;
  topics: BuilderTopic[];
}

export interface CurriculumStructure {
  course_id: string;
  units: BuilderUnit[];
}

export interface ConceptEditResult {
  concept_id: string;
  topic_id: string;
  allocated_minutes_before: number;
  allocated_minutes_after: number;
}

// ── Co-teaching ──
export type MemberRole = "co_teacher" | "viewer";

export interface CourseMembers {
  owner: { teacher_id: string; name: string; email: string };
  members: { teacher_id: string; name: string; email: string; role: MemberRole; added_at: string }[];
}
