from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from app.database.connection import get_db
from app.models.entities import Course, Teacher, Unit, Topic, Section, TeacherConstraint, Assessment, User, CourseMember
from app.schemas.schemas import (
    CourseCreate, CourseOut, ConfirmCurriculumRequest, CurriculumGraphResponse,
    CourseOptimizationResponse, NextClassOptimizationResponse,
    LessonPlanOut, LessonPlanUpdate, AssessmentCreate, AssessmentOut,
    RecordAssessmentResultsRequest, CourseAnalyticsResponse, SessionLogIn
)
from app.nlp.deterministic import nlp_provider
from app.services.curriculum_service import curriculum_service
from app.services.analytics_service import analytics_service
from app.services.lesson_plan_service import lesson_plan_service
from app.services.assessment_service import assessment_service
from app.services.session_service import session_service
from app.services.artifact_service import artifact_service
from app.optimization.time_allocator import time_allocator
from app.optimization.class_optimizer import class_optimizer

from app.auth.security import get_current_user, get_current_teacher, get_accessible_course, course_role, limit_uploads

# Every route requires a valid bearer token; /{course_id} routes additionally resolve the
# course through get_accessible_course (owner or admin, otherwise 404).
router = APIRouter(prefix="/courses", tags=["Courses & Optimization"], dependencies=[Depends(get_current_user)])

MAX_SYLLABUS_BYTES = 5 * 1024 * 1024
ALLOWED_SYLLABUS_SUFFIXES = (".pdf", ".txt", ".md", ".text", ".markdown")

@router.get("", response_model=List[CourseOut])
def list_courses(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Courses the user owns, then courses shared with them (co-teacher or viewer)."""
    query = db.query(Course)
    if current_user.role != "admin":
        shared = (
            db.query(CourseMember.course_id).join(Teacher, CourseMember.teacher_id == Teacher.id)
            .filter(Teacher.user_id == current_user.id)
        )
        owned = db.query(Course.id).join(Teacher).filter(Teacher.user_id == current_user.id)
        query = query.filter(or_(Course.id.in_(owned), Course.id.in_(shared)))
    courses = query.order_by(Course.created_at).all()
    results = []
    for c in courses:
        u_count = len(c.units)
        t_count = sum(len(u.topics) for u in c.units)
        c_count = sum(sum(len(t.concepts) for t in u.topics) for u in c.units)
        results.append(CourseOut(
            id=c.id,
            code=c.code,
            title=c.title,
            semester=c.semester,
            academic_year=c.academic_year,
            total_classes=c.total_classes,
            period_duration=c.period_duration,
            total_available_minutes=c.total_available_minutes,
            teacher_name=c.teacher.user.full_name if (c.teacher and c.teacher.user) else "Faculty",
            section_name=c.sections[0].name if c.sections else "Default Section",
            units_count=u_count,
            topics_count=t_count,
            concepts_count=c_count,
            my_role=course_role(db, c, current_user),
            created_at=c.created_at
        ))
    order = {"owner": 0, "admin": 0, "co_teacher": 1, "viewer": 2}
    return sorted(results, key=lambda r: order.get(r.my_role, 3))

@router.post("", response_model=CourseOut)
def create_course(
    payload: CourseCreate,
    teacher: Optional[Teacher] = Depends(get_current_teacher),
    db: Session = Depends(get_db)
):
    if not teacher:
        raise HTTPException(status_code=403, detail="Only teachers can create courses")

    # Derive academic_year from semester when not supplied.
    # "Fall YYYY" → "YYYY-(YYYY+1)";  "Spring YYYY" → "(YYYY-1)-YYYY"
    def _derive_academic_year(semester_str: str) -> str:
        parts = semester_str.split()
        for part in parts:
            if part.isdigit() and len(part) == 4:
                y = int(part)
                if semester_str.lower().startswith("spring"):
                    return f"{y - 1}-{y}"
                return f"{y}-{y + 1}"
        return semester_str  # fallback: store the semester string itself

    academic_year = payload.academic_year or _derive_academic_year(payload.semester)

    course = Course(
        teacher_id=teacher.id,
        code=payload.code,
        title=payload.title,
        semester=payload.semester,
        academic_year=academic_year,
        total_classes=payload.total_classes,
        period_duration=payload.period_duration,
        start_date=payload.start_date,
        end_date=payload.end_date
    )
    db.add(course)
    db.flush()

    section = Section(
        course_id=course.id,
        name=payload.section_name,
        student_count=payload.student_count
    )
    db.add(section)

    c_vals = payload.constraints
    constraint = TeacherConstraint(
        course_id=course.id,
        max_lecture_ratio=c_vals.max_lecture_ratio if c_vals else 0.40,
        min_practice_ratio=c_vals.min_practice_ratio if c_vals else 0.35,
        revision_threshold_score=c_vals.revision_threshold_score if c_vals else 60.0,
        default_revision_minutes=c_vals.default_revision_minutes if c_vals else 10
    )
    db.add(constraint)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="You already have a course with this code in this semester") from exc
    db.refresh(course)

    return CourseOut(
        id=course.id,
        code=course.code,
        title=course.title,
        semester=course.semester,
        academic_year=course.academic_year,
        total_classes=course.total_classes,
        period_duration=course.period_duration,
        total_available_minutes=course.total_available_minutes,
        teacher_name=teacher.user.full_name if teacher.user else "Faculty",
        section_name=section.name,
        units_count=0,
        topics_count=0,
        concepts_count=0,
        created_at=course.created_at
    )

@router.get("/{course_id}", response_model=CourseOut)
def get_course(c: Course = Depends(get_accessible_course), current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    u_count = len(c.units)
    t_count = sum(len(u.topics) for u in c.units)
    c_count = sum(sum(len(t.concepts) for t in u.topics) for u in c.units)

    return CourseOut(
        id=c.id,
        code=c.code,
        title=c.title,
        semester=c.semester,
        academic_year=c.academic_year,
        total_classes=c.total_classes,
        period_duration=c.period_duration,
        total_available_minutes=c.total_available_minutes,
        teacher_name=c.teacher.user.full_name if (c.teacher and c.teacher.user) else "Faculty",
        section_name=c.sections[0].name if c.sections else None,
        units_count=u_count,
        topics_count=t_count,
        concepts_count=c_count,
        my_role=course_role(db, c, current_user),
        created_at=c.created_at
    )

# -------------------------------------------------------------
# Curriculum & Knowledge Graph
# -------------------------------------------------------------
async def read_syllabus_upload(file: UploadFile) -> bytes:
    """Bounded read with an extension allow-list; rejects oversized or unexpected files."""
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()

    has_valid_suffix = any(filename.endswith(s) for s in ALLOWED_SYLLABUS_SUFFIXES)
    is_pdf_type = "pdf" in content_type or filename.endswith(".pdf")
    is_text_type = any(t in content_type for t in ["text", "plain", "markdown"]) or any(filename.endswith(s) for s in [".txt", ".md", ".text", ".markdown"])

    if not (has_valid_suffix or is_pdf_type or is_text_type):
        raise HTTPException(status_code=415, detail="Syllabus must be a .pdf, .txt or .md file")

    content = await file.read(MAX_SYLLABUS_BYTES + 1)
    if len(content) > MAX_SYLLABUS_BYTES:
        raise HTTPException(status_code=413, detail="Syllabus file exceeds the 5 MB limit")

    if (filename.endswith(".pdf") or is_pdf_type) and b"%PDF" not in content[:1024]:
        raise HTTPException(status_code=415, detail="File is not a valid PDF")

    return content


@router.post("/{course_id}/syllabus", dependencies=[Depends(limit_uploads)])
async def upload_course_syllabus(
    course_id: str,
    file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None),
    course: Course = Depends(get_accessible_course),
    db: Session = Depends(get_db)
):
    curriculum = None
    try:
        if file:
            content_bytes = await read_syllabus_upload(file)
            filename = (file.filename or "").lower()
            content_type = (file.content_type or "").lower()
            if filename.endswith(".pdf") or "pdf" in content_type or b"%PDF" in content_bytes[:1024]:
                curriculum = nlp_provider.extract_from_pdf(content_bytes)
            else:
                try:
                    text = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text = content_bytes.decode("latin-1", errors="ignore")
                curriculum = nlp_provider.extract_from_text(text)
        elif raw_text and raw_text.strip():
            curriculum = nlp_provider.extract_from_text(raw_text.strip())
        else:
            raise HTTPException(status_code=400, detail="No syllabus content provided. Please upload a PDF or paste text.")
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve)) from ve
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Syllabus extraction failed: {str(e)}") from e

    # Automatically confirm and persist directly to this course
    confirm_payload = ConfirmCurriculumRequest(
        course_name=course.title,
        course_code=course.code,
        units=curriculum.units,
        outcomes=curriculum.outcomes
    )
    artifact_service.record_extraction(curriculum, course_id=course_id, extracted_by=course.teacher.user_id)
    curriculum_service.confirm_and_persist(db, course_id, confirm_payload)
    time_allocator.optimize_course_time(db, course_id)

    return {
        "status": "success",
        "message": f"Successfully extracted and linked {len(curriculum.units)} units and {len(curriculum.outcomes)} outcomes to {course.code}",
        "curriculum": curriculum,
        "course_id": course_id
    }

@router.post("/{course_id}/curriculum/confirm")
def confirm_curriculum(course_id: str, payload: ConfirmCurriculumRequest, db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    result = curriculum_service.confirm_and_persist(db, course_id, payload)
    # Automatically run optimizer to update allocations
    time_allocator.optimize_course_time(db, course_id)
    return result

@router.get("/{course_id}/graph", response_model=CurriculumGraphResponse)
def get_curriculum_graph(course_id: str, db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    return curriculum_service.get_graph(db, course_id)

@router.get("/{course_id}/graph/versions")
def list_graph_versions(course_id: str, _: Course = Depends(get_accessible_course)):
    """Curriculum graph snapshots stored in MongoDB, newest first."""
    return artifact_service.list_graph_versions(course_id)

@router.get("/{course_id}/graph/diff")
def diff_graph_versions(course_id: str, from_version: int, to_version: int, _: Course = Depends(get_accessible_course)):
    return artifact_service.diff_graph_versions(course_id, from_version, to_version)

# -------------------------------------------------------------
# Optimization Endpoints
# -------------------------------------------------------------
@router.post("/{course_id}/optimize", response_model=CourseOptimizationResponse)
def run_course_optimization(course_id: str, db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    return time_allocator.optimize_course_time(db, course_id)

@router.get("/{course_id}/optimization", response_model=CourseOptimizationResponse)
def get_course_optimization(course_id: str, db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    # A GET must not change data: compute the allocation without persisting it
    return time_allocator.optimize_course_time(db, course_id, persist=False)

@router.post("/{course_id}/optimize-next-class", response_model=NextClassOptimizationResponse)
def optimize_next_class(course_id: str, session_number: Optional[int] = None, db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    return class_optimizer.optimize_next_class(db, course_id, session_number=session_number)

# -------------------------------------------------------------
# Lesson Plans
# -------------------------------------------------------------
@router.post("/{course_id}/lesson-plans/generate", response_model=LessonPlanOut)
def generate_lesson_plan(course_id: str, payload: Dict[str, Any], db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    topic_in_course = (
        db.query(Topic.id).join(Unit)
        .filter(Topic.id == payload.get("topic_id"), Unit.course_id == course_id)
        .first()
    )
    if not topic_in_course:
        raise HTTPException(status_code=404, detail="Topic not found in this course")
    session_num = payload.get("session_number", 15)
    return lesson_plan_service.generate_plan(db, course_id, session_num, payload)

@router.get("/{course_id}/lesson-plans", response_model=List[LessonPlanOut])
def list_course_lesson_plans(
    course_id: str,
    session_number: Optional[int] = None,
    unit_id: Optional[str] = None,
    topic_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: Course = Depends(get_accessible_course)
):
    return lesson_plan_service.list_plans(
        db, course_id, session_number=session_number, unit_id=unit_id, topic_id=topic_id, status=status
    )

@router.patch("/{course_id}/lesson-plans/{session_number}", response_model=LessonPlanOut)
def review_lesson_plan(
    course_id: str,
    session_number: int,
    payload: LessonPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: Course = Depends(get_accessible_course),
):
    """Accept / edit / reject a recommended plan. Stale expected_version -> 409."""
    return lesson_plan_service.update_plan(db, course_id, session_number, payload, current_user.id)

@router.get("/{course_id}/lesson-plans/{session_number}/history")
def lesson_plan_history(course_id: str, session_number: int, db: Session = Depends(get_db),
                        _: Course = Depends(get_accessible_course)):
    """Every saved version of the plan (MongoDB), newest first, with who changed it."""
    return artifact_service.lesson_plan_history(db, course_id, session_number)

@router.get("/{course_id}/lesson-plans/{session_number}/diff")
def lesson_plan_diff(course_id: str, session_number: int, from_version: int, to_version: int,
                     db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    return artifact_service.diff_lesson_plan_versions(db, course_id, session_number, from_version, to_version)

# -------------------------------------------------------------
# Class Sessions (timetable + post-class record)
# -------------------------------------------------------------
@router.get("/{course_id}/sessions")
def list_sessions(course_id: str, db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    return session_service.list_sessions(db, course_id)

@router.post("/{course_id}/sessions/{session_number}/log")
def log_session(course_id: str, session_number: int, payload: SessionLogIn,
                db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    """Record a taught class. A second record for the same session -> 409."""
    return session_service.log_session(db, course_id, session_number, payload)

# -------------------------------------------------------------
# Assessments & Continuous Feedback
# -------------------------------------------------------------
@router.get("/{course_id}/assessments")
def list_assessments(course_id: str, db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    assessments = db.query(Assessment).filter(Assessment.course_id == course_id).all()
    results = []
    for a in assessments:
        results.append({
            "id": a.id,
            "title": a.title,
            "assessment_type": a.assessment_type,
            "max_marks": a.max_marks,
            "scheduled_date": a.scheduled_date,
            "status": a.status,
            "questions_count": len(a.questions),
            "performances": [
                {
                    "concept_id": p.concept_id,
                    "concept_name": p.concept.name if p.concept else "",
                    "average_score": p.average_score,
                    "weakness_flag": p.weakness_flag,
                    "common_errors": p.common_errors
                } for p in a.performances
            ]
        })
    return results

@router.post("/{course_id}/assessments", response_model=AssessmentOut)
def create_assessment(course_id: str, payload: AssessmentCreate, db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    return assessment_service.create_assessment(db, course_id, payload)

@router.post("/{course_id}/assessments/{assessment_id}/results")
def record_assessment_results(course_id: str, assessment_id: str, payload: RecordAssessmentResultsRequest, db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    # The assessment must belong to the course in the URL, or a teacher could write
    # into another course's assessment through their own course's path
    if not db.query(Assessment.id).filter(Assessment.id == assessment_id, Assessment.course_id == course_id).first():
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment_service.record_results(db, assessment_id, payload)

# -------------------------------------------------------------
# Analytics & Alerts
# -------------------------------------------------------------
@router.get("/{course_id}/analytics", response_model=CourseAnalyticsResponse)
def get_analytics(course_id: str, db: Session = Depends(get_db), _: Course = Depends(get_accessible_course)):
    return analytics_service.get_course_analytics(db, course_id)
