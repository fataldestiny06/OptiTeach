import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, BigInteger, Float, Boolean, Text, DateTime, ForeignKey,
    CheckConstraint, UniqueConstraint, Table, Computed, JSON, Index, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database.connection import Base

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)

# -------------------------------------------------------------------
# Association Tables (Many-to-Many Normalized 3NF)
# -------------------------------------------------------------------

concept_outcomes = Table(
    "concept_outcomes",
    Base.metadata,
    Column("concept_id", String(36), ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True),
    Column("outcome_id", String(36), ForeignKey("course_outcomes.id", ondelete="CASCADE"), primary_key=True),
    # The composite PK only serves lookups by its leading column (concept_id); FK side needs its own index
    Index("ix_concept_outcomes_outcome", "outcome_id"),
)

prerequisites = Table(
    "prerequisites",
    Base.metadata,
    Column("concept_id", String(36), ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True),
    Column("prerequisite_id", String(36), ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True),
    CheckConstraint("concept_id != prerequisite_id", name="check_no_self_prerequisite"),
    Index("ix_prerequisites_prerequisite", "prerequisite_id"),
)

# 1NF fix: replaces the former teacher_constraints.preferred_methods_json list column.
# One row per (constraint, method); `rank` keeps the teacher's preference order.
teacher_preferred_methods = Table(
    "teacher_preferred_methods",
    Base.metadata,
    Column("constraint_id", String(36), ForeignKey("teacher_constraints.id", ondelete="CASCADE"), primary_key=True),
    Column("method_id", String(36), ForeignKey("teaching_methods.id", ondelete="CASCADE"), primary_key=True),
    Column("rank", Integer, nullable=False),
    UniqueConstraint("constraint_id", "rank", name="uq_preferred_method_rank"),
    CheckConstraint("rank >= 1", name="check_positive_preference_rank"),
    Index("ix_teacher_preferred_methods_method", "method_id"),
)

question_concepts = Table(
    "question_concepts",
    Base.metadata,
    Column("question_id", String(36), ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True),
    Column("concept_id", String(36), ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True),
    Column("weightage", Float, default=1.0),
    CheckConstraint("weightage > 0", name="check_positive_weightage"),
    Index("ix_question_concepts_concept", "concept_id"),
)

# -------------------------------------------------------------------
# Entity Models
# -------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="teacher") # teacher, admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint("role IN ('teacher', 'admin')", name="check_user_role"),
    )

    teacher_profile = relationship("Teacher", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    department = Column(String(100), nullable=False)
    designation = Column(String(100), default="Assistant Professor")
    employee_id = Column(String(50), unique=True, nullable=False)
    office_location = Column(String(100), nullable=True)

    user = relationship("User", back_populates="teacher_profile")
    courses = relationship("Course", back_populates="teacher", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    teacher_id = Column(String(36), ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True) # e.g. CS302
    title = Column(String(255), nullable=False) # e.g. Database Management Systems
    semester = Column(String(50), nullable=False) # e.g. Fall 2026 / Sem 5
    academic_year = Column(String(20), nullable=True)  # derived server-side from semester
    total_classes = Column(Integer, nullable=False) # e.g. 40
    period_duration = Column(Integer, nullable=False, default=55) # minutes
    # Derived attribute stored as a generated column: the DBMS computes it, so it can
    # never disagree with total_classes/period_duration (no update anomaly).
    total_available_minutes = Column(Integer, Computed("total_classes * period_duration", persisted=True))
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("total_classes > 0", name="check_positive_total_classes"),
        CheckConstraint("period_duration > 0", name="check_positive_period_duration"),
        UniqueConstraint("teacher_id", "code", "semester", name="uq_teacher_course_semester"),
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="check_course_date_order"),
    )

    teacher = relationship("Teacher", back_populates="courses")
    sections = relationship("Section", back_populates="course", cascade="all, delete-orphan")
    constraints = relationship("TeacherConstraint", back_populates="course", uselist=False, cascade="all, delete-orphan")
    members = relationship("CourseMember", back_populates="course", cascade="all, delete-orphan")
    outcomes = relationship("CourseOutcome", back_populates="course", cascade="all, delete-orphan")
    units = relationship("Unit", back_populates="course", order_by="Unit.order_index", cascade="all, delete-orphan")
    class_sessions = relationship("ClassSession", back_populates="course", order_by="ClassSession.session_number", cascade="all, delete-orphan")
    assessments = relationship("Assessment", back_populates="course", order_by="Assessment.scheduled_date", cascade="all, delete-orphan")


class Section(Base):
    __tablename__ = "sections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(50), nullable=False) # e.g. Section A
    room_number = Column(String(50), nullable=True)
    student_count = Column(Integer, default=60)

    __table_args__ = (
        UniqueConstraint("course_id", "name", name="uq_course_section_name"),
        CheckConstraint("student_count > 0", name="check_positive_student_count"),
    )

    course = relationship("Course", back_populates="sections")


class TeacherConstraint(Base):
    __tablename__ = "teacher_constraints"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), unique=True, nullable=False)
    max_lecture_ratio = Column(Float, default=0.45) # Max 45% pure lecture
    min_practice_ratio = Column(Float, default=0.35) # Min 35% practice / worked examples
    revision_threshold_score = Column(Float, default=60.0) # Trigger revision if prereq avg < 60%
    default_revision_minutes = Column(Integer, default=10)
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint("max_lecture_ratio >= 0.0 AND max_lecture_ratio <= 1.0", name="check_max_lecture_ratio_range"),
        CheckConstraint("min_practice_ratio >= 0.0 AND min_practice_ratio <= 1.0", name="check_min_practice_ratio_range"),
        CheckConstraint("revision_threshold_score >= 0.0 AND revision_threshold_score <= 100.0", name="check_revision_threshold_range"),
        CheckConstraint("default_revision_minutes >= 0", name="check_non_negative_revision_minutes"),
    )

    course = relationship("Course", back_populates="constraints")
    preferred_methods = relationship(
        "TeachingMethod",
        secondary=teacher_preferred_methods,
        order_by=teacher_preferred_methods.c.rank,
        viewonly=True
    )


class CourseOutcome(Base):
    __tablename__ = "course_outcomes"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(20), nullable=False) # e.g. CO1, CO2
    description = Column(Text, nullable=False)
    bloom_level = Column(String(50), default="Understand") # Remember, Understand, Apply, Analyze, Evaluate, Create

    __table_args__ = (
        UniqueConstraint("course_id", "code", name="uq_course_outcome_code"),
        CheckConstraint(
            "bloom_level IN ('Remember', 'Understand', 'Apply', 'Analyze', 'Evaluate', 'Create')",
            name="check_bloom_level"
        ),
    )

    course = relationship("Course", back_populates="outcomes")
    concepts = relationship("Concept", secondary=concept_outcomes, back_populates="outcomes")


class Unit(Base):
    __tablename__ = "units"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_number = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("unit_number >= 1", name="check_unit_number_positive"),
        UniqueConstraint("course_id", "unit_number", name="uq_course_unit_number"),
    )

    course = relationship("Course", back_populates="units")
    topics = relationship("Topic", back_populates="unit", order_by="Topic.order_index", cascade="all, delete-orphan")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    unit_id = Column(String(36), ForeignKey("units.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=False)
    estimated_minutes = Column(Integer, default=110) # Base estimated time
    allocated_minutes = Column(Integer, default=0) # Calculated by optimizer
    priority_score = Column(Float, default=0.0) # Calculated by scoring formula
    status = Column(String(50), default="pending") # pending, in_progress, completed

    __table_args__ = (
        CheckConstraint("estimated_minutes > 0", name="check_positive_estimated_minutes"),
        CheckConstraint("allocated_minutes >= 0", name="check_non_negative_allocated_minutes"),
        UniqueConstraint("unit_id", "order_index", name="uq_unit_topic_order"),
        CheckConstraint("status IN ('pending', 'in_progress', 'completed')", name="check_topic_status"),
    )

    unit = relationship("Unit", back_populates="topics")
    concepts = relationship("Concept", back_populates="topic", order_by="Concept.order_index", cascade="all, delete-orphan")
    lesson_plans = relationship("LessonPlan", back_populates="topic")


class Concept(Base):
    __tablename__ = "concepts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    topic_id = Column(String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    difficulty = Column(Integer, default=3) # 1 to 5
    importance = Column(Integer, default=3) # 1 to 5
    concept_type = Column(String(50), default="conceptual") # conceptual, procedural, problem_solving, practical, analytical, revision
    order_index = Column(Integer, default=1)

    __table_args__ = (
        CheckConstraint("difficulty >= 1 AND difficulty <= 5", name="check_difficulty_range"),
        CheckConstraint("importance >= 1 AND importance <= 5", name="check_importance_range"),
        CheckConstraint(
            "concept_type IN ('conceptual', 'procedural', 'problem_solving', 'practical', 'analytical', 'revision')",
            name="check_concept_type"
        ),
    )

    topic = relationship("Topic", back_populates="concepts")
    outcomes = relationship("CourseOutcome", secondary=concept_outcomes, back_populates="concepts")
    
    # Directed Graph: Concepts that THIS concept depends on (prerequisites)
    prerequisites = relationship(
        "Concept",
        secondary=prerequisites,
        primaryjoin=(id == prerequisites.c.concept_id),
        secondaryjoin=(id == prerequisites.c.prerequisite_id),
        backref="dependent_concepts"
    )
    
    performances = relationship("Performance", back_populates="concept", cascade="all, delete-orphan")


class ClassSession(Base):
    __tablename__ = "class_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    session_number = Column(Integer, nullable=False) # Period 1, Period 2 ...
    scheduled_date = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=False, default=55)
    current_topic_id = Column(String(36), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), default="scheduled") # scheduled, in_progress, completed, cancelled

    __table_args__ = (
        CheckConstraint("session_number >= 1", name="check_positive_session_number"),
        CheckConstraint("duration_minutes > 0", name="check_positive_session_duration"),
        UniqueConstraint("course_id", "session_number", name="uq_course_session_number"),
        CheckConstraint("status IN ('scheduled', 'in_progress', 'completed', 'cancelled')", name="check_session_status"),
        Index("ix_class_sessions_current_topic", "current_topic_id"),
        # Partial index: "next scheduled session" lookups only ever touch the upcoming slice
        Index(
            "ix_class_sessions_upcoming", "course_id", "session_number",
            postgresql_where=text("status = 'scheduled'"), sqlite_where=text("status = 'scheduled'")
        ),
    )

    course = relationship("Course", back_populates="class_sessions")
    current_topic = relationship("Topic")
    lesson_plan = relationship("LessonPlan", back_populates="session", uselist=False, cascade="all, delete-orphan")
    teaching_session = relationship("TeachingSession", back_populates="session", uselist=False, cascade="all, delete-orphan")


class TeachingMethod(Base):
    __tablename__ = "teaching_methods"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), unique=True, nullable=False)
    category = Column(String(50), nullable=False) # conceptual, problem_solving, practical, active_learning, revision
    description = Column(Text, nullable=True)
    typical_time_ratio = Column(Float, default=0.25) # Recommended fraction of period

    __table_args__ = (
        CheckConstraint("typical_time_ratio > 0.0 AND typical_time_ratio <= 1.0", name="check_typical_time_ratio_range"),
    )

    teaching_sessions = relationship("TeachingSession", back_populates="method")
    effect_records = relationship("MethodEffectiveness", back_populates="method")


class LessonPlan(Base):
    __tablename__ = "lesson_plans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("class_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    topic_id = Column(String(36), ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    status = Column(String(50), default="draft") # draft, approved, rejected, modified, completed
    mongo_doc_id = Column(String(100), nullable=True) # Pointer to MongoDB rich document
    ai_confidence = Column(Float, default=0.90)
    teacher_overridden = Column(Boolean, default=False)
    # Optimistic concurrency control: every UPDATE is issued as
    # "... WHERE id = :id AND version = :seen" and bumps the version, so a save based on
    # a stale read matches zero rows and is rejected instead of overwriting.
    version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'approved', 'rejected', 'modified', 'completed')", name="check_lesson_plan_status"),
        CheckConstraint("ai_confidence >= 0.0 AND ai_confidence <= 1.0", name="check_ai_confidence_range"),
        CheckConstraint("version >= 1", name="check_lesson_plan_version_positive"),
    )
    __mapper_args__ = {"version_id_col": version}

    session = relationship("ClassSession", back_populates="lesson_plan")
    topic = relationship("Topic", back_populates="lesson_plans")


class TeachingSession(Base):
    __tablename__ = "teaching_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("class_sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    method_id = Column(String(36), ForeignKey("teaching_methods.id", ondelete="SET NULL"), nullable=True)
    actual_minutes = Column(Integer, nullable=False, default=55)
    teacher_notes = Column(Text, nullable=True)
    student_engagement_rating = Column(Integer, default=4) # 1 to 5
    completion_rate = Column(Float, default=1.0) # 0.0 to 1.0
    conducted_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint("actual_minutes > 0", name="check_positive_actual_minutes"),
        CheckConstraint("student_engagement_rating >= 1 AND student_engagement_rating <= 5", name="check_engagement_rating_range"),
        CheckConstraint("completion_rate >= 0.0 AND completion_rate <= 1.0", name="check_completion_rate_range"),
    )

    session = relationship("ClassSession", back_populates="teaching_session")
    method = relationship("TeachingMethod", back_populates="teaching_sessions")


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False) # e.g. Midterm 1, Quiz 2: SQL & Relational Algebra
    assessment_type = Column(String(50), nullable=False) # quiz, assignment, midterm, final
    max_marks = Column(Float, nullable=False, default=25.0)
    scheduled_date = Column(DateTime, nullable=True, index=True)
    status = Column(String(50), default="upcoming") # upcoming, completed
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint("max_marks > 0", name="check_positive_max_marks"),
        CheckConstraint("assessment_type IN ('quiz', 'assignment', 'midterm', 'final')", name="check_assessment_type"),
        CheckConstraint("status IN ('upcoming', 'completed')", name="check_assessment_status"),
    )

    course = relationship("Course", back_populates="assessments")
    questions = relationship("Question", back_populates="assessment", order_by="Question.question_number", cascade="all, delete-orphan")
    performances = relationship("Performance", back_populates="assessment", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    question_number = Column(Integer, nullable=False)
    max_marks = Column(Float, nullable=False)
    text = Column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("question_number >= 1", name="check_positive_question_number"),
        CheckConstraint("max_marks > 0", name="check_positive_question_marks"),
        UniqueConstraint("assessment_id", "question_number", name="uq_assessment_question_num"),
    )

    assessment = relationship("Assessment", back_populates="questions")
    concepts = relationship("Concept", secondary=question_concepts, backref="questions")


class Performance(Base):
    __tablename__ = "performance"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    concept_id = Column(String(36), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True)
    assessment_id = Column(String(36), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    average_score = Column(Float, nullable=False) # e.g. 52.5%
    sample_size = Column(Integer, default=58)
    weakness_flag = Column(Boolean, default=False) # True if score < threshold
    common_errors = Column(Text, nullable=True) # Common student conceptual misunderstandings
    recorded_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint("average_score >= 0.0 AND average_score <= 100.0", name="check_average_score_range"),
        CheckConstraint("sample_size > 0", name="check_positive_sample_size"),
        UniqueConstraint("concept_id", "assessment_id", name="uq_concept_assessment_performance"),
        # Partial index: weakness/revision queries only need flagged rows
        Index("ix_performance_weak", "concept_id", postgresql_where=text("weakness_flag"), sqlite_where=text("weakness_flag")),
    )

    concept = relationship("Concept", back_populates="performances")
    assessment = relationship("Assessment", back_populates="performances")


class MethodEffectiveness(Base):
    __tablename__ = "method_effectiveness"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    method_id = Column(String(36), ForeignKey("teaching_methods.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_type = Column(String(50), nullable=False) # conceptual, problem_solving, practical, etc.
    baseline_score = Column(Float, default=50.0) # Historical cohort pre-assessment
    post_score = Column(Float, default=65.0) # Measured cohort post-assessment
    observed_gain = Column(Float, default=15.0) # post_score - baseline_score
    sample_sessions_count = Column(Integer, default=5)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("sample_sessions_count >= 0", name="check_non_negative_sample_sessions"),
    )

    method = relationship("TeachingMethod", back_populates="effect_records")


class AuditLog(Base):
    """
    Append-only change history. On PostgreSQL it is filled by the fn_audit_row_change()
    trigger (migration 0002), so every write is captured regardless of which client made it.
    """
    __tablename__ = "audit_log"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    table_name = Column(String(63), nullable=False)
    operation = Column(String(6), nullable=False)
    row_id = Column(String(36), nullable=True)
    old_data = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    new_data = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    changed_by = Column(String(36), nullable=True)  # users.id taken from the app.user_id session setting
    changed_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint("operation IN ('INSERT', 'UPDATE', 'DELETE')", name="check_audit_operation"),
        Index("ix_audit_log_table_row", "table_name", "row_id", "changed_at"),
    )


class TxnLabAccount(Base):
    """
    Scratch rows for the Transaction Lab demos (atomicity, isolation levels, lost updates,
    deadlocks). Kept apart from course data so demonstrations never touch real records.
    """
    __tablename__ = "txn_lab_accounts"

    id = Column(String(20), primary_key=True)
    label = Column(String(50), nullable=False)
    balance = Column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("balance >= 0", name="check_non_negative_balance"),
    )


class CourseMember(Base):
    """
    Co-teaching (M:N teachers <-> courses with a role). The owner stays courses.teacher_id;
    members are the other faculty: co_teacher can change the course, viewer can only read.
    PostgreSQL additionally rejects adding the owner as a member (trg_course_member_not_owner).
    """
    __tablename__ = "course_members"

    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    teacher_id = Column(String(36), ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(20), nullable=False)
    added_at = Column(DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint("role IN ('co_teacher', 'viewer')", name="check_course_member_role"),
        Index("ix_course_members_teacher", "teacher_id"),
    )

    course = relationship("Course", back_populates="members")
    teacher = relationship("Teacher")
