# OptiTeach — Change Log & Enhancement Summary

## Branch: `feature/dbms-phases`

---

### 1. Robust Multi-Engine PDF & NLP Syllabus Parser

#### Problem
The previous syllabus parser failed on diverse PDF formats, non-UTF-8 character encodings, and unconventional unit/topic heading formats. Furthermore, topic durations and metadata were rigid.

#### Enhancements
- **Multi-Engine PDF Extraction** (`backend/app/nlp/deterministic.py`):
  - **PyMuPDF (`fitz`)**: High-fidelity text extraction with block/paragraph structure preservation.
  - **pypdf**: Automatic secondary fallback if PyMuPDF encounters rendering anomalies or missing font tables.
  - **Byte-sweep recovery**: Tertiary heuristic extraction for corrupted or non-standard byte streams.
- **Robust Character & Text Sanitization**:
  - Full Unicode NFKC normalization.
  - Automatic de-hyphenation across line wraps (e.g. `opti-\nmization` $\rightarrow$ `optimization`).
  - Bullet standardization for diverse markers (`•`, `–`, `*`, `\t`, numeric enumerations).
- **Flexible 4-Strategy Unit Recognition**:
  - Explicit keyword headers (`UNIT`, `MODULE`, `CHAPTER`, `SECTION`).
  - Numbered units (`1. Relational Model`, `2. Normalization`).
  - Markdown heading syntax (`## Unit 1`, `### Module 2`).
  - Contextual cluster fallback when explicit headings are absent.
- **Dynamic Topic Duration & Pacing Heuristics**:
  - Parses explicit hour definitions in syllabus headers or unit lines (e.g. `Total Hours: 45`, `[8 Hours]`).
  - Dynamically computes topic duration ($\text{Unit Hours} / \text{Topic Count}$) or derives dynamic minutes based on Bloom taxonomy and concept difficulty.
- **Enhanced Course Outcomes & Bloom Taxonomy**:
  - Extracts CO statements using explicit markers (`CO1:`, `Course Outcome 2:`) or structural synthesis.
  - Full Bloom taxonomy verb mapping (`Remember`, `Understand`, `Apply`, `Analyze`, `Evaluate`, `Create`).
- **Flexible File Upload Support** (`backend/app/api/courses.py`, `backend/app/api/syllabus.py`):
  - MIME type and byte-level PDF detection (`b"%PDF"` magic numbers) in addition to file extension checks.
  - Multi-encoding fallback decoding (`utf-8` $\rightarrow$ `latin-1` $\rightarrow$ `replace`).
  - Added support for `.text` and `.markdown` extensions alongside `.pdf`, `.txt`, and `.md`.

---

### 2. Dynamic Metadata & Elimination of Hardcoded Values

#### Problem
Several fields previously defaulted to hardcoded literals (e.g., `"Fall 2026"`, `"2026-2027"`) across the schema, database models, and frontend pages.

#### Enhancements
- **Metadata Extraction in NLP Engine**:
  - `ExtractedCurriculum` now dynamically extracts and surfaces `semester`, `academic_year`, `suggested_total_classes`, and `suggested_period_duration`.
- **Backend Schema & Model**:
  - `backend/app/schemas/schemas.py`: Made `academic_year: Optional[str] = None` in `CourseCreate`.
  - `backend/app/models/entities.py`: Changed `academic_year` from hardcoded default `"2026-2027"` to `nullable=True`.
  - `backend/app/api/courses.py`: Server-side fallback derives academic year dynamically from the `semester` string (e.g., `"Fall 2026"` $\rightarrow$ `"2026-2027"`, `"Spring 2027"` $\rightarrow$ `"2026-2027"`).
- **Frontend Form Defaults**:
  - `frontend/app/upload/page.tsx`:
    - `semester` state initializes dynamically based on current system date (June–Nov: `Fall <Year>`, Dec–May: `Spring <Year>`).
    - `academicYear` state initializes dynamically from the current date.
    - Upon syllabus upload, form fields automatically populate with extracted metadata (`result.semester`, `result.academic_year`, `result.suggested_total_classes`, `result.suggested_period_duration`).
    - Hardcoded fallback values removed from `handleConfirm`.
  - `frontend/app/courses/page.tsx`:
    - `NewCourseDialog` defaults for semester and academic year are dynamically computed from the system calendar instead of static literals.

---

### 3. Frontend Workflow & UX Upgrades

- **Upload Feedback & Diagnostics**:
  - Upload dropzone and button display the uploaded file name during processing.
  - Input field accept criteria expanded to include official MIME types (`application/pdf`, `text/plain`, `text/markdown`).
- **Post-Confirmation Action Hub**:
  - Direct navigation links displayed immediately upon curriculum confirmation:
    - **Open course** (`/courses/{id}`)
    - **View time plan** (`/optimization?courseId={id}`)
    - **Curriculum graph** (`/curriculum?courseId={id}`)
    - **Class calendar** (`/calendar?courseId={id}`)

---

### 4. Verification & Testing

- **New Test Suite**: `backend/tests/test_syllabus_enhancement.py`
  - Tests PyMuPDF PDF extraction and text parsing.
  - Tests bullet point formatting, numbered unit formatting, comma-delimited topics, and Markdown headings.
  - Validates curriculum DAG invariants (topological sort, acyclicity, valid difficulty ratings).
  - Validates API upload endpoints for PDF and TXT syllabus files.
- **Suite Results**:
  - `pytest`: **87 passed**, 41 skipped (PostgreSQL/MongoDB integration tests skipped in local SQLite mode).
  - `ruff`: **0 errors** / checks passed.
  - Frontend ESLint & TypeScript (`tsc --noEmit`): **0 errors**.

---

### 5. Summary of Modified & New Files

| File | Change Type | Description |
|---|---|---|
| `backend/requirements.txt` | Modified | Added `pymupdf>=1.24` dependency |
| `backend/app/nlp/deterministic.py` | Modified | Multi-engine PDF reader, dynamic metadata, flexible parser |
| `backend/app/api/courses.py` | Modified | Byte magic inspection, encoding fallbacks, dynamic academic year |
| `backend/app/api/syllabus.py` | Modified | Robust PDF detection and decoding |
| `backend/app/schemas/schemas.py` | Modified | Added dynamic fields to `ExtractedCurriculum`, made `academic_year` optional |
| `backend/app/models/entities.py` | Modified | Made `academic_year` nullable without hardcoded default |
| `backend/tests/test_syllabus_enhancement.py` | Added | 8 new comprehensive unit and API tests |
| `frontend/lib/types.ts` | Modified | Updated `ExtractedCurriculum` interface with metadata fields |
| `frontend/app/upload/page.tsx` | Modified | Dynamic date defaults, auto-population from NLP result, action links |
| `frontend/app/courses/page.tsx` | Modified | Date-computed default semester and academic year |
| `CHANGELOG.md` | Added | Detailed release notes and modification summary |
