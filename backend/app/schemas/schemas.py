from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime

# -------------------------------------------------------------
# Auth Schemas
# -------------------------------------------------------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str
    role: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class RegisterRequest(BaseModel):
    email: EmailStr
    # bcrypt only uses the first 72 bytes; cap well below any abuse size
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=255)
    department: str = Field(min_length=1, max_length=100)
    employee_id: str = Field(min_length=1, max_length=50)
    designation: Optional[str] = Field(default="Assistant Professor", max_length=100)

class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool

# -------------------------------------------------------------
# Course & Setup Wizard Schemas
# -------------------------------------------------------------
class CourseConstraintIn(BaseModel):
    max_lecture_ratio: float = 0.45
    min_practice_ratio: float = 0.35
    revision_threshold_score: float = 60.0
    default_revision_minutes: int = 10

class CourseCreate(BaseModel):
    code: str
    title: str
    semester: str
    # academic_year is optional; if omitted the API derives it from semester (e.g. "Fall 2026" → "2026-2027")
    academic_year: Optional[str] = None
    total_classes: int = 40
    period_duration: int = 55
    section_name: str = "Section A"
    student_count: int = 60
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    constraints: Optional[CourseConstraintIn] = None

class CourseOut(BaseModel):
    id: str
    code: str
    title: str
    semester: str
    academic_year: str
    total_classes: int
    period_duration: int
    total_available_minutes: int
    teacher_name: Optional[str] = None
    section_name: Optional[str] = None
    units_count: int = 0
    topics_count: int = 0
    concepts_count: int = 0
    my_role: str = "owner"  # owner / co_teacher / viewer / admin
    created_at: Optional[datetime] = None

# -------------------------------------------------------------
# Curriculum & Extraction Schemas
# -------------------------------------------------------------
# Same value sets as the CHECK constraints on concepts.concept_type / course_outcomes.bloom_level,
# so bad input is a 422 from the API rather than a constraint error from the database
ConceptType = Literal["conceptual", "procedural", "problem_solving", "practical", "analytical", "revision"]
BloomLevel = Literal["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"]

class ConceptDraft(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    difficulty: int = Field(default=3, ge=1, le=5)
    importance: int = Field(default=3, ge=1, le=5)
    concept_type: ConceptType = "conceptual"
    prerequisites: List[str] = [] # list of prerequisite concept names or IDs
    bloom_level: Optional[str] = "Understand"

class TopicDraft(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    estimated_minutes: int = 110
    concepts: List[ConceptDraft] = []

class UnitDraft(BaseModel):
    id: Optional[str] = None
    unit_number: int
    title: str
    description: Optional[str] = None
    topics: List[TopicDraft] = []

class OutcomeDraft(BaseModel):
    code: str
    description: str
    bloom_level: BloomLevel = "Understand"

class ExtractedCurriculum(BaseModel):
    course_name: str
    course_code: str
    semester: Optional[str] = None
    academic_year: Optional[str] = None
    suggested_total_classes: Optional[int] = None
    suggested_period_duration: Optional[int] = None
    outcomes: List[OutcomeDraft] = []
    units: List[UnitDraft] = []
    confidence_score: float = 0.92
    extraction_notes: List[str] = []

class ConfirmCurriculumRequest(BaseModel):
    units: List[UnitDraft]
    outcomes: List[OutcomeDraft] = []
    course_name: Optional[str] = None
    course_code: Optional[str] = None

# -------------------------------------------------------------
# Graph Schemas
# -------------------------------------------------------------
class GraphNode(BaseModel):
    id: str
    name: str
    topic_id: str
    topic_title: str
    unit_number: int
    difficulty: int
    importance: int
    concept_type: str
    status: str # "mastered", "weak", "bottleneck", "pending"
    avg_score: Optional[float] = None
    downstream_count: int = 0

class GraphEdge(BaseModel):
    source: str # prerequisite concept id
    target: str # dependent concept id
    relationship_type: str = "prerequisite"

class CurriculumGraphResponse(BaseModel):
    course_id: str
    course_title: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    bottlenecks: List[str] # concept ids with highest downstream count and low scores

# -------------------------------------------------------------
# Optimization Schemas
# -------------------------------------------------------------
class TopicAllocationOut(BaseModel):
    topic_id: str
    unit_number: int
    topic_title: str
    estimated_minutes: int
    allocated_minutes: int
    priority_score: float
    recommended_periods: float
    reason_codes: List[str]
    explanation: str
    key_concepts: List[str]

class CourseOptimizationResponse(BaseModel):
    course_id: str
    total_available_minutes: int
    total_allocated_minutes: int
    revision_budget_minutes: int
    assessment_budget_minutes: int
    unallocated_buffer_minutes: int
    time_pressure_status: str # "healthy", "balanced", "high_pressure"
    topic_allocations: List[TopicAllocationOut]
    formula_explanation: Dict[str, Any]

ResourceKind = Literal["slides", "video", "link", "dataset", "code", "formula"]

class LessonResource(BaseModel):
    """Teaching material attached to a lesson plan. Link-type resources carry a URL;
    code and formula resources carry their text (formulas as LaTeX)."""
    kind: ResourceKind
    title: str = Field(min_length=1, max_length=200)
    url: Optional[str] = Field(default=None, max_length=2000)
    content: Optional[str] = Field(default=None, max_length=20000)
    language: Optional[str] = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def _check_payload(self):
        if self.kind in ("slides", "video", "link", "dataset"):
            if not self.url or not self.url.lower().startswith(("https://", "http://")):
                raise ValueError(f"A {self.kind} resource needs an http(s) link")
        elif not (self.content and self.content.strip()):
            raise ValueError(f"A {self.kind} resource needs its text")
        return self

class PeriodPhase(BaseModel):
    phase_name: str
    duration_minutes: int
    method_name: str
    activity_description: str
    concept_ref: Optional[str] = None

class NextClassOptimizationResponse(BaseModel):
    session_number: int
    topic_id: str
    topic_title: str
    unit_number: int
    period_duration: int
    target_concepts: List[str]
    revision_needed: bool
    revision_minutes: int
    revision_concept: Optional[str] = None
    revision_reason: Optional[str] = None
    recommended_methods: List[str]
    phases: List[PeriodPhase]
    total_phase_minutes: int
    why_explanation: str
    learning_gain_prediction: float

# -------------------------------------------------------------
# Lesson Plan Schemas
# -------------------------------------------------------------
class LessonPlanCreate(BaseModel):
    session_number: int
    topic_id: str
    title: str
    phases: List[PeriodPhase]
    learning_objectives: List[str]
    worked_examples: List[str]
    active_exercises: List[str]
    misconceptions: List[str]
    assessment_questions: List[str]
    teacher_notes: Optional[str] = None

class LessonPlanOut(BaseModel):
    id: str
    session_id: str
    session_number: int
    topic_id: str
    topic_title: str
    title: str
    status: str
    teacher_overridden: bool
    phases: List[PeriodPhase]
    learning_objectives: List[str]
    worked_examples: List[str]
    active_exercises: List[str]
    misconceptions: List[str]
    assessment_questions: List[str]
    resources: List[LessonResource] = []
    version: int = 1
    created_at: Optional[datetime] = None

class SessionLogIn(BaseModel):
    """What the teacher records after a class (Teach -> Record)."""
    method_id: Optional[str] = None
    actual_minutes: int = Field(gt=0, le=300)
    student_engagement_rating: int = Field(default=4, ge=1, le=5)
    completion_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    teacher_notes: Optional[str] = Field(default=None, max_length=2000)
    topic_completed: bool = False
    # The topic ran out of time: teach it again next period and push later periods back one
    carry_over: bool = False

class LessonPlanUpdate(BaseModel):
    """Teacher review of a recommended plan (human-in-the-loop). expected_version is the
    version the client last read; a mismatch means someone else saved in between -> 409."""
    expected_version: int = Field(ge=1)
    status: Optional[Literal["approved", "rejected", "modified"]] = None
    phases: Optional[List[PeriodPhase]] = None
    learning_objectives: Optional[List[str]] = None
    worked_examples: Optional[List[str]] = None
    active_exercises: Optional[List[str]] = None
    misconceptions: Optional[List[str]] = None
    assessment_questions: Optional[List[str]] = None
    resources: Optional[List[LessonResource]] = Field(default=None, max_length=50)
    change_note: Optional[str] = Field(default=None, max_length=500)

# -------------------------------------------------------------
# Assessment & Performance Schemas
# -------------------------------------------------------------
class QuestionIn(BaseModel):
    question_number: int
    max_marks: float
    text: str
    concept_ids: List[str]

class AssessmentCreate(BaseModel):
    title: str
    assessment_type: str # quiz, assignment, midterm, final
    max_marks: float
    scheduled_date: Optional[datetime] = None
    questions: List[QuestionIn] = []

class PerformanceRecordIn(BaseModel):
    concept_id: str
    average_score: float = Field(ge=0.0, le=100.0)
    sample_size: int = Field(default=58, gt=0)
    common_errors: Optional[str] = Field(default=None, max_length=2000)

class RecordAssessmentResultsRequest(BaseModel):
    performances: List[PerformanceRecordIn] = Field(min_length=1)

class AssessmentOut(BaseModel):
    id: str
    title: str
    assessment_type: str
    max_marks: float
    scheduled_date: Optional[datetime] = None
    status: str
    questions_count: int = 0
    concept_averages: Dict[str, float] = {}

# -------------------------------------------------------------
# Analytics & Alerts
# -------------------------------------------------------------
class AlertItem(BaseModel):
    id: str
    severity: str # "danger", "warning", "info", "success"
    title: str
    message: str
    action_label: Optional[str] = None
    action_route: Optional[str] = None

class CourseAnalyticsResponse(BaseModel):
    course_id: str
    progress_percentage: float
    completed_sessions: int
    total_sessions: int
    planned_minutes: int
    actual_minutes_taught: int
    remaining_minutes: int
    concept_health: Dict[str, int] # {"strong": 12, "moderate": 6, "weak": 3, "bottleneck": 1}
    teaching_method_effectiveness: List[Dict[str, Any]]
    alerts: List[AlertItem]

# -------------------------------------------------------------
# DBMS Insights Schemas
# -------------------------------------------------------------
class TableColumnInfo(BaseModel):
    name: str
    type: str
    primary_key: bool
    foreign_key: Optional[str] = None
    nullable: bool
    constraints: List[str] = []

class TableSchemaInfo(BaseModel):
    table_name: str
    description: str
    row_count: int
    normal_form: str
    columns: List[TableColumnInfo]

class QueryDemoResult(BaseModel):
    query_id: str
    title: str
    category: str
    sql: str
    purpose: str
    sql_features: List[str] = []
    requires: Optional[str] = None
    params: Dict[str, Any] = {}
    row_count: int
    columns: List[str]
    rows: List[Dict[str, Any]]
    execution_time_ms: float
