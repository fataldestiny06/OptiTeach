import re
import io
import unicodedata
import logging
from typing import List, Tuple, Optional, Dict
from app.nlp.base import NLPProvider
from app.schemas.schemas import (
    ExtractedCurriculum, UnitDraft, TopicDraft, ConceptDraft, OutcomeDraft,
    ConceptType, BloomLevel
)

logger = logging.getLogger("optiteach.nlp")

# Common Bloom taxonomy verbs mapping
BLOOM_MAPPING: Dict[BloomLevel, List[str]] = {
    "Create": ["design", "construct", "create", "formulate", "build", "develop", "synthesize", "compose", "devise", "originate", "produce"],
    "Evaluate": ["evaluate", "assess", "justify", "critique", "validate", "judge", "rate", "appraise", "defend", "select", "test"],
    "Analyze": ["analyze", "differentiate", "compare", "contrast", "deconstruct", "examine", "normalize", "distinguish", "investigate", "categorize", "dissect", "troubleshoot"],
    "Apply": ["apply", "implement", "calculate", "solve", "execute", "use", "query", "demonstrate", "operate", "illustrate", "manipulate", "write", "show"],
    "Understand": ["explain", "describe", "summarize", "interpret", "classify", "discuss", "identify", "express", "comprehend", "outline"],
    "Remember": ["recall", "list", "define", "name", "state", "recognize", "repeat", "label", "match", "reproduce", "retrieve"]
}

ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10
}

LETTER_MAP = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6
}


class DeterministicNLPProvider(NLPProvider):
    """
    High-fidelity deterministic NLP syllabus extraction engine.
    Extracts units, topics, concepts, outcomes, and prerequisite DAGs
    from PDFs, plain text, and Markdown documents.
    """

    def extract_from_pdf(self, pdf_bytes: bytes) -> ExtractedCurriculum:
        raw_text = ""
        extracted_engine = None

        # 1. Primary engine: PyMuPDF (fitz) - best layout, block, and font handling
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if doc.is_encrypted:
                try:
                    doc.authenticate("")
                except Exception:
                    pass

            page_blocks: List[str] = []
            for page in doc:
                blocks = page.get_text("blocks")
                page_h = page.rect.height
                for b in blocks:
                    # b: (x0, y0, x1, y1, text, block_no, block_type)
                    if len(b) >= 5 and isinstance(b[4], str):
                        b_text = b[4].strip()
                        y0 = b[1]
                        # Filter out isolated page numbering headers/footers
                        if (y0 < 38 or y0 > page_h - 38) and re.match(
                            r"^(?:page\s*\d+(?:\s*(?:of|/)\s*\d+)?|\d+\s*/\s*\d+|\d+)$",
                            b_text,
                            re.IGNORECASE
                        ):
                            continue
                        page_blocks.append(b[4])

            raw_text = "\n".join(page_blocks)
            if raw_text.strip():
                extracted_engine = "PyMuPDF"
        except Exception as e:
            logger.warning(f"PyMuPDF PDF extraction failed: {e}")

        # 2. Secondary engine: pypdf fallback
        if not raw_text.strip() or len(raw_text.strip()) < 30:
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(pdf_bytes))
                if reader.is_encrypted:
                    try:
                        reader.decrypt("")
                    except Exception:
                        pass
                pypdf_lines: List[str] = []
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        pypdf_lines.append(t)
                if pypdf_lines:
                    raw_text = "\n".join(pypdf_lines)
                    extracted_engine = "pypdf"
            except Exception as e2:
                logger.warning(f"pypdf extraction failed: {e2}")

        # 3. Tertiary fallback: ASCII / UTF-8 string sweep if streams are raw
        if not raw_text.strip() or len(raw_text.strip()) < 30:
            try:
                matches = re.findall(rb"[\x20-\x7E\t\r\n]{4,}", pdf_bytes)
                candidate_text = b"\n".join(matches).decode("ascii", errors="ignore")
                if "UNIT" in candidate_text.upper() or "MODULE" in candidate_text.upper():
                    raw_text = candidate_text
                    extracted_engine = "byte-stream"
            except Exception as e3:
                logger.warning(f"Byte sweep fallback failed: {e3}")

        if not raw_text.strip() or len(raw_text.strip()) < 20:
            raise ValueError(
                "Could not extract any readable text from the uploaded PDF document. "
                "The PDF may be a scanned image without an OCR text layer, password-protected, or empty. "
                "Please verify the PDF is searchable or paste the syllabus text directly."
            )

        curriculum = self.extract_from_text(raw_text)
        if extracted_engine:
            curriculum.extraction_notes.insert(0, f"Extracted via {extracted_engine} engine from PDF.")
        return curriculum

    def _sanitize_text(self, text: str) -> str:
        """Normalizes unicode characters, ligatures, dashes, and line breaks."""
        if not text:
            return ""

        # Normalize unicode (NFKC resolves ligatures like 'fi', 'fl', 'ffi')
        text = unicodedata.normalize("NFKC", text)

        # Standardize quotes, dashes, and bullet marks
        text = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]", "-", text)
        text = re.sub(r"[\u2018\u2019\u201A\u201B]", "'", text)
        text = re.sub(r"[\u201C\u201D\u201E\u201F]", '"', text)
        text = re.sub(r"[\u00A0\u2000-\u200B\u202F\u205F\u3000]", " ", text)
        text = re.sub(r"[\u2022\u2023\u25E6\u2043\u2219\u25AA\u25AB]", "•", text)

        # Reconnect hyphenated line-breaks (e.g. 'rela-\ntional' -> 'relational')
        text = re.sub(r"(\b[a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,}\b)", r"\1\2", text)

        # Remove repetitive header/footer artifacts
        text = re.sub(r"(?i)^page\s*\d+\s*(?:of|/)\s*\d+$", "", text, flags=re.MULTILINE)

        # Replace excessive carriage returns and tabs
        text = text.replace("\r", "\n").replace("\t", " ")

        return text.strip()

    def extract_from_text(self, raw_text: str) -> ExtractedCurriculum:
        if not raw_text or not raw_text.strip():
            raise ValueError(
                "No syllabus text provided. Please enter or upload a valid syllabus document."
            )

        clean_text = self._sanitize_text(raw_text)
        notes: List[str] = []
        lines = [line.strip() for line in clean_text.split("\n") if line.strip()]

        # 1. Course Code & Title, Semester, Academic Year Detection
        course_code = None
        course_name = None
        semester = None
        academic_year = None
        suggested_total_classes = None
        suggested_period_duration = 55

        # Inspect first 25 lines for metadata
        for line in lines[:25]:
            # Course Title / Subject Name matching
            t_match = re.search(
                r"(?:Subject\s*Name|Course\s*Name|Course\s*Title|Subject|Course|Paper\s*Title|Paper\s*Name)\s*[:\-]\s*([^\n\r]+)",
                line,
                re.IGNORECASE
            )
            if t_match and not course_name:
                cand = t_match.group(1).strip()
                cand = re.sub(r"^(?:Name|Title)\s*[:\-]?\s*", "", cand, flags=re.IGNORECASE).strip()
                if len(cand) >= 3 and not cand.startswith("http") and not re.match(r"^(?:code|unit|module|chapter|outcome|co\d+)", cand, re.IGNORECASE):
                    course_name = cand

            # Markdown title pattern: # Course Title (CS302) or # Course Title
            md_match = re.search(r"^#\s*([^#\(\n\r]+)(?:\(([A-Za-z0-9\-]+)\))?", line)
            if md_match and not course_name:
                cand_title = md_match.group(1).strip()
                if len(cand_title) >= 3:
                    course_name = cand_title
                    if md_match.group(2) and not course_code:
                        course_code = md_match.group(2).strip().upper()

            # Course Code matching
            c_match = re.search(
                r"(?:Course\s*Code|Subject\s*Code|Code|Paper\s*Code)\s*[:\-]\s*([A-Za-z0-9\-]+)",
                line,
                re.IGNORECASE
            )
            if c_match and not course_code:
                cand_code = c_match.group(1).strip()
                if len(cand_code) >= 2:
                    course_code = cand_code.upper()

            # Semester matching (e.g. Semester: 5, Sem: V, Fall 2026, Spring 2027)
            s_match = re.search(
                r"(?:Semester|Sem|Term)\s*[:\-]?\s*([A-Za-z0-9\s\-]+?)(?=[,\n\r;]|$)",
                line,
                re.IGNORECASE
            )
            if s_match and not semester:
                cand_sem = s_match.group(1).strip()
                if 1 <= len(cand_sem) <= 25 and not re.match(r"^(?:course|code|unit|module)", cand_sem, re.IGNORECASE):
                    if cand_sem.isdigit() or cand_sem.upper() in ROMAN_MAP:
                        semester = f"Semester {cand_sem.upper()}"
                    else:
                        semester = cand_sem

            # Academic year matching (e.g. Academic Year: 2026-2027, Batch 2024-2028, Regulation 2021)
            ay_match = re.search(
                r"(?:Academic\s*Year|Regulation|Batch|Year)\s*[:\-]?\s*([0-9]{4}(?:\s*[\-\/]\s*[0-9]{2,4})?)",
                line,
                re.IGNORECASE
            )
            if ay_match and not academic_year:
                academic_year = ay_match.group(1).replace(" ", "")

            # Total hours or classes matching
            h_match = re.search(
                r"(?:Total\s*(?:Contact\s*)?(?:Hours|Periods|Lectures))\s*[:\-]?\s*(\d+)",
                line,
                re.IGNORECASE
            )
            if h_match and not suggested_total_classes:
                total_hours = int(h_match.group(1))
                if 15 <= total_hours <= 120:
                    suggested_total_classes = total_hours

        # Fallback for Course Code from standard academic patterns (e.g. CS401, 21CS52, AIML302)
        if not course_code:
            code_pattern_match = re.search(r"\b([A-Z]{2,5}\s*\d{3,4}|[0-9]{2}[A-Z]{2,4}[0-9]{2,3})\b", clean_text[:1000])
            if code_pattern_match:
                course_code = code_pattern_match.group(1).replace(" ", "").upper()

        # If course title not found from explicit prefix, inspect first prominent header line
        if not course_name:
            for line in lines[:8]:
                if re.search(r"\b(?:university|college|department|faculty|syllabus|curriculum|semester|scheme|regulation|b\.?e\.?|b\.?tech|m\.?tech)\b", line, re.IGNORECASE):
                    continue
                if re.match(r"^(?:unit|module|chapter|part|section|co\d+|course\s*outcome|hours|period)\b", line, re.IGNORECASE):
                    continue
                cleaned_line = re.sub(r"^[A-Za-z0-9\-]+[:\-]\s*", "", line).strip()
                if 4 <= len(cleaned_line) <= 80:
                    course_name = cleaned_line
                    break

        if not course_name:
            course_name = "Untitled Course"
            notes.append("Course title not explicitly detected in header lines; please verify.")

        if not course_code:
            words = [w for w in re.split(r"[\s&\-_]+", course_name) if w.lower() not in ["and", "of", "the", "in", "to", "for", "untitled", "course"]]
            if len(words) >= 2:
                course_code = "".join(w[0].upper() for w in words[:4]) + "101"
            elif words:
                course_code = words[0][:4].upper() + "101"
            else:
                course_code = "CRS101"
            notes.append(f"Course code inferred as '{course_code}'.")

        # 2. Extract Units / Modules
        units, detected_unit_hours = self._extract_units(clean_text)
        if not units:
            raise ValueError(
                "Could not extract any units or modules from the syllabus. "
                "Please verify that the syllabus contains recognizable unit/module headings or topic sections."
            )

        if detected_unit_hours and not suggested_total_classes:
            suggested_total_classes = max(20, detected_unit_hours)

        notes.append(f"Successfully extracted {len(units)} units/modules with granular topics and prerequisite DAG.")

        # 3. Extract Course Outcomes
        outcomes = self._extract_outcomes(clean_text, units)
        if outcomes:
            notes.append(f"Successfully extracted {len(outcomes)} Course Outcomes (Bloom-aligned).")
        else:
            notes.append("Synthesized curriculum-aligned Course Outcomes.")

        confidence = 0.96 if len(units) >= 3 and len(outcomes) >= 2 else 0.88 if len(units) >= 2 else 0.75

        return ExtractedCurriculum(
            course_name=course_name,
            course_code=course_code,
            semester=semester,
            academic_year=academic_year,
            suggested_total_classes=suggested_total_classes,
            suggested_period_duration=suggested_period_duration,
            outcomes=outcomes,
            units=units,
            confidence_score=confidence,
            extraction_notes=notes
        )

    def _extract_outcomes(self, text: str, units: List[UnitDraft]) -> List[OutcomeDraft]:
        outcomes: List[OutcomeDraft] = []

        # Strategy A: Explicit CO markers (e.g. CO1:, Course Outcome 1:, CLO 1:, CO-1)
        co_matches = re.findall(
            r"(?:^|\n)\s*(?:CO|CLO|Course\s*Outcome|Course\s*Learning\s*Outcome|Outcome)\s*[\.\-_]?\s*(\d+)[\s:\-]+([^\n\r]+)",
            text,
            re.IGNORECASE
        )
        for code_num, desc_raw in co_matches:
            desc = desc_raw.strip()
            if not desc or len(desc) < 6:
                continue
            bloom = self._infer_bloom_level(desc)
            outcomes.append(OutcomeDraft(
                code=f"CO{code_num}",
                description=desc,
                bloom_level=bloom
            ))

        # Strategy B: Section block under Course Outcomes / Learning Objectives header
        if not outcomes:
            co_section_match = re.search(
                r"(?:^|\n)\s*(?:COURSE\s*OUTCOMES?|COURSE\s*LEARNING\s*OUTCOMES?|LEARNING\s*OUTCOMES?|COURSE\s*OBJECTIVES?|EXPECTED\s*OUTCOMES?)\s*[:\-]?\s*\n(.*?)(?=\n\s*(?:(?:#{1,3}\s*)?(?:UNIT|MODULE|CHAPTER|PART|SECTION)\b|\Z))",
                text,
                re.IGNORECASE | re.DOTALL
            )
            if co_section_match:
                section_text = co_section_match.group(1).strip()
                item_lines = [line.strip() for line in section_text.split("\n") if line.strip()]
                idx = 1
                for item_line in item_lines:
                    # Strip bullet marks or numbering: 1., (a), -, •
                    clean_item = re.sub(r"^(?:(?:CO|CLO)?\s*\d+[\.\:\)\-]|[\(\[]?[a-z\d]+[\)\]\.]|[•\*\-])\s*", "", item_line, flags=re.IGNORECASE).strip()
                    if len(clean_item) >= 8:
                        bloom = self._infer_bloom_level(clean_item)
                        outcomes.append(OutcomeDraft(
                            code=f"CO{idx}",
                            description=clean_item,
                            bloom_level=bloom
                        ))
                        idx += 1

        # Strategy C: Synthesize outcomes from extracted units if none detected
        if not outcomes and units:
            for u in units[:5]:
                topic_titles = [t.title for t in u.topics[:2]]
                topics_str = " and ".join(topic_titles) if topic_titles else u.title
                if u.unit_number == 1:
                    desc = f"Understand and explain the fundamental concepts and architecture of {u.title} ({topics_str})"
                    bloom: BloomLevel = "Understand"
                elif u.unit_number == 2:
                    desc = f"Apply core techniques and principles in {u.title} ({topics_str})"
                    bloom = "Apply"
                elif u.unit_number == 3:
                    desc = f"Analyze and evaluate methodologies related to {u.title}"
                    bloom = "Analyze"
                elif u.unit_number == 4:
                    desc = f"Design and implement solutions addressing {u.title}"
                    bloom = "Create"
                else:
                    desc = f"Assess and optimize systems incorporating concepts of {u.title}"
                    bloom = "Evaluate"

                outcomes.append(OutcomeDraft(
                    code=f"CO{u.unit_number}",
                    description=desc,
                    bloom_level=bloom
                ))

        return outcomes

    def _infer_bloom_level(self, text: str) -> BloomLevel:
        """Infers the Bloom's taxonomy cognitive level from text verbs."""
        text_lower = text.lower()
        for level, verbs in BLOOM_MAPPING.items():
            if any(re.search(rf"\b{re.escape(v)}\b", text_lower) for v in verbs):
                return level
        return "Understand"

    def _extract_units(self, text: str) -> Tuple[List[UnitDraft], Optional[int]]:
        # Truncate text before reference/bibliography/textbook/exam sections
        cutoff_pattern = r"(?:\n\s*(?:TEXT\s*BOOKS?|REFERENCES?|REFERENCE\s*BOOKS?|RECOMMENDED\s*READINGS?|SUGGESTED\s*READINGS?|EVALUATION\s*SCHEME|QUESTION\s*PAPER\s*PATTERN|WEB\s*REFERENCES?|EXAMINATION\s*PATTERN)\s*[:\-])"
        split_cutoff = re.split(cutoff_pattern, text, flags=re.IGNORECASE)
        core_text = split_cutoff[0] if split_cutoff else text

        units: List[UnitDraft] = []
        all_concepts_flat: List[str] = []
        total_unit_hours = 0

        # Strategy 1: Explicit Unit / Module / Chapter / Part / Section Headers
        unit_pattern = (
            r"(?:^|\n)\s*(?:#{1,3}\s*)?(?:UNIT|MODULE|CHAPTER|PART|SECTION)\s*[-:]?\s*"
            r"([0-9IVXLCDM]+|[A-E])\b[\s:\-]*(.*?)"
            r"(?=(?:\n\s*(?:#{1,3}\s*)?(?:UNIT|MODULE|CHAPTER|PART|SECTION)\s*[-:]?\s*(?:[0-9IVXLCDM]+|[A-E])\b)|\Z)"
        )
        matches = list(re.finditer(unit_pattern, core_text, re.IGNORECASE | re.DOTALL))

        if matches:
            for i, match in enumerate(matches, start=1):
                unit_raw = match.group(1).strip().upper()
                unit_body = match.group(2).strip()

                unit_num = i
                if unit_raw in ROMAN_MAP:
                    unit_num = ROMAN_MAP[unit_raw]
                elif unit_raw in LETTER_MAP:
                    unit_num = LETTER_MAP[unit_raw]
                else:
                    try:
                        unit_num = int(unit_raw)
                    except ValueError:
                        unit_num = i

                lines = [line.strip() for line in unit_body.split("\n") if line.strip()]
                if not lines:
                    continue

                unit_title, u_hours = self._clean_unit_title(lines[0], unit_num)
                if u_hours:
                    total_unit_hours += u_hours
                # If first line was just punctuation or empty, check second line
                topic_lines = lines[1:] if len(lines) > 1 else [lines[0]]
                if len(lines) > 1 and len(lines[0]) < 3:
                    unit_title, u_hours = self._clean_unit_title(lines[1], unit_num)
                    if u_hours:
                        total_unit_hours += u_hours
                    topic_lines = lines[2:] if len(lines) > 2 else [lines[1]]

                topics = self._parse_topics_from_lines(topic_lines, unit_num, unit_title, all_concepts_flat, u_hours)
                units.append(UnitDraft(
                    unit_number=unit_num,
                    title=unit_title,
                    description=f"Curriculum module covering {unit_title}",
                    topics=topics
                ))

            if units:
                return units, (total_unit_hours if total_unit_hours > 0 else None)

        # Strategy 2: Numbered major headings (e.g. '1. Relational Model ... 2. Normalization ...')
        numbered_pattern = (
            r"(?:^|\n)\s*([1-9])\.\s+([A-Za-z][^\n\r]+)\n(.*?)"
            r"(?=(?:\n\s*[1-9]\.\s+[A-Za-z])|\Z)"
        )
        num_matches = list(re.finditer(numbered_pattern, core_text, re.DOTALL))
        if len(num_matches) >= 2:
            for i, match in enumerate(num_matches, start=1):
                try:
                    unit_num = int(match.group(1))
                except ValueError:
                    unit_num = i
                unit_title, u_hours = self._clean_unit_title(match.group(2), unit_num)
                if u_hours:
                    total_unit_hours += u_hours
                body = match.group(3).strip()
                topic_lines = [line.strip() for line in body.split("\n") if line.strip()]
                topics = self._parse_topics_from_lines(topic_lines, unit_num, unit_title, all_concepts_flat, u_hours)
                units.append(UnitDraft(
                    unit_number=unit_num,
                    title=unit_title,
                    description=f"Curriculum module covering {unit_title}",
                    topics=topics
                ))
            if units:
                return units, (total_unit_hours if total_unit_hours > 0 else None)

        # Strategy 3: Markdown Headings (## or ###)
        md_heading_pattern = (
            r"(?:^|\n)#{2,3}\s+(?:(?:UNIT|MODULE|CHAPTER)?\s*[0-9IVXLCDM]*[:\-]?\s*)?([^\n\r]+)\n(.*?)"
            r"(?=(?:\n#{2,3}\s+)|\Z)"
        )
        md_matches = list(re.finditer(md_heading_pattern, core_text, re.DOTALL))
        if len(md_matches) >= 2:
            for i, match in enumerate(md_matches, start=1):
                unit_title, u_hours = self._clean_unit_title(match.group(1), i)
                if u_hours:
                    total_unit_hours += u_hours
                body = match.group(2).strip()
                topic_lines = [line.strip() for line in body.split("\n") if line.strip()]
                topics = self._parse_topics_from_lines(topic_lines, i, unit_title, all_concepts_flat, u_hours)
                units.append(UnitDraft(
                    unit_number=i,
                    title=unit_title,
                    description=f"Curriculum module covering {unit_title}",
                    topics=topics
                ))
            if units:
                return units, (total_unit_hours if total_unit_hours > 0 else None)

        # Strategy 4: Resilient topic clustering fallback
        # If no explicit units detected, chunk available lines into 3-4 logical units
        non_empty_lines = [line.strip() for line in core_text.split("\n") if line.strip() and len(line.strip()) >= 5]
        if len(non_empty_lines) >= 3:
            num_units = 3 if len(non_empty_lines) <= 9 else 4 if len(non_empty_lines) <= 16 else 5
            chunk_size = max(1, len(non_empty_lines) // num_units)
            for u_idx in range(1, num_units + 1):
                start = (u_idx - 1) * chunk_size
                end = len(non_empty_lines) if u_idx == num_units else u_idx * chunk_size
                chunk = non_empty_lines[start:end]
                if not chunk:
                    continue
                unit_title, u_hours = self._clean_unit_title(chunk[0], u_idx)
                topics = self._parse_topics_from_lines(chunk, u_idx, unit_title, all_concepts_flat, u_hours)
                units.append(UnitDraft(
                    unit_number=u_idx,
                    title=unit_title,
                    description=f"Curriculum module covering {unit_title}",
                    topics=topics
                ))

        return units, (total_unit_hours if total_unit_hours > 0 else None)

    def _clean_unit_title(self, raw_title: str, unit_num: int) -> Tuple[str, Optional[int]]:
        """Strips hours notations, chapter prefixes, and extracts unit hours if present."""
        hours = None
        h_match = re.search(r"[\(\[]\s*(\d+)\s*(?:Hours?|Hrs?|Periods?|Lectures?|L)\s*[\)\]]", raw_title, flags=re.IGNORECASE)
        if h_match:
            try:
                hours = int(h_match.group(1))
            except ValueError:
                hours = None

        t = re.sub(r"^(?:UNIT|MODULE|CHAPTER|PART|SECTION)?\s*[-:]?\s*(?:[0-9IVXLCDM]+|[A-E])\s*[:\.\-]\s*", "", raw_title, flags=re.IGNORECASE).strip()
        t = re.sub(r"\s*[\(\[]\s*\d+\s*(?:Hours?|Hrs?|Periods?|Lectures?|L)\s*[\)\]]", "", t, flags=re.IGNORECASE).strip()
        t = re.sub(r"^[:\-–—\.]\s*", "", t).strip()
        if not t or len(t) < 3:
            t = f"Unit {unit_num}"
        elif len(t) > 90:
            t = t[:90].strip()
        return t, hours

    def _parse_topics_from_lines(
        self,
        topic_lines: List[str],
        unit_num: int,
        unit_title: str,
        all_concepts_flat: List[str],
        unit_hours: Optional[int] = None
    ) -> List[TopicDraft]:
        topics: List[TopicDraft] = []

        for line_raw in topic_lines:
            line = re.sub(r"^[•\*\-\d+\.]\s*", "", line_raw).strip()
            # Remove hours notation like '(4 Hours)' or '(6L)'
            line = re.sub(r"\s*[\(\[]\s*\d+\s*(?:Hours?|Hrs?|Periods?|Lectures?|L)\s*[\)\]]", "", line, flags=re.IGNORECASE).strip()
            if not line or len(line) < 3:
                continue

            # Skip lines that look like textbook or reference citations
            if re.match(r"^(?:text\s*books?|references?|author|edition|isbn)\b", line, re.IGNORECASE):
                continue

            # Structure A: 'Topic Title: Concept 1, Concept 2, Concept 3'
            if ":" in line or " - " in line:
                parts = re.split(r"[:\-–—]", line, maxsplit=1)
                topic_title = parts[0].strip()
                details = parts[1].strip() if len(parts) > 1 else ""

                if len(topic_title) < 3:
                    topic_title = f"{unit_title} Section {len(topics) + 1}"

                concept_strings = [s.strip() for s in re.split(r"[,;•]\s*", details) if len(s.strip()) > 2]
                if not concept_strings:
                    concept_strings = [topic_title]
            else:
                # Structure B: 'Concept 1, Concept 2, Concept 3, Concept 4'
                items = [s.strip() for s in re.split(r"[,;•]\s*", line) if len(s.strip()) > 2]
                if not items:
                    continue
                if len(items) == 1:
                    topic_title = items[0]
                    concept_strings = [items[0]]
                else:
                    topic_title = items[0]
                    concept_strings = items

            # Build ConceptDraft items with accurate types and prerequisite DAG
            concepts: List[ConceptDraft] = []
            prev_concept: Optional[str] = None

            for idx, c_name in enumerate(concept_strings, start=1):
                c_name_clean = re.sub(r"^[0-9\.\)\-•]+\s*", "", c_name).strip()
                if not c_name_clean or len(c_name_clean) < 2:
                    continue

                c_type, diff, bloom = self._infer_concept_attributes(c_name_clean)
                importance = 5 if diff >= 4 else 4 if diff == 3 else 3

                # Directed Acyclic Graph (DAG) prerequisite chaining
                prereqs: List[str] = []
                if prev_concept and prev_concept != c_name_clean:
                    prereqs.append(prev_concept)
                elif all_concepts_flat and idx == 1:
                    # Link initial concept of topic to previous key concept in course
                    prereqs.append(all_concepts_flat[-1])

                concepts.append(ConceptDraft(
                    name=c_name_clean,
                    description=f"Detailed study and mastery of {c_name_clean}",
                    difficulty=diff,
                    importance=importance,
                    concept_type=c_type,
                    prerequisites=prereqs,
                    bloom_level=bloom
                ))
                all_concepts_flat.append(c_name_clean)
                prev_concept = c_name_clean

            if concepts:
                # Dynamic duration calculation: check topic line hours first, then unit hours, else concept difficulty
                t_hours_match = re.search(r"[\(\[]\s*(\d+)\s*(?:Hours?|Hrs?|Periods?|Lectures?|L)\s*[\)\]]", line_raw, re.IGNORECASE)
                if t_hours_match:
                    est_minutes = int(t_hours_match.group(1)) * 60
                elif unit_hours and len(topic_lines) > 0:
                    est_minutes = max(55, (unit_hours * 60) // max(1, len(topic_lines)))
                else:
                    est_minutes = max(55, min(180, len(concepts) * 25 + sum(c.difficulty for c in concepts) * 5))

                topics.append(TopicDraft(
                    title=topic_title,
                    description=f"Instructional topic covering {topic_title}",
                    estimated_minutes=est_minutes,
                    concepts=concepts
                ))

        # Fallback if no sub-topics found: create from unit title
        if not topics:
            concept_name = f"{unit_title} Core Principles"
            concepts = [
                ConceptDraft(
                    name=concept_name,
                    description=f"Core coverage of {unit_title}",
                    difficulty=3,
                    importance=4,
                    concept_type="conceptual",
                    prerequisites=[all_concepts_flat[-1]] if all_concepts_flat else []
                )
            ]
            all_concepts_flat.append(concept_name)
            fallback_minutes = (unit_hours * 60) if unit_hours else 110
            topics = [
                TopicDraft(
                    title=unit_title,
                    description=f"Curriculum topic for {unit_title}",
                    estimated_minutes=fallback_minutes,
                    concepts=concepts
                )
            ]

        return topics

    def _infer_concept_attributes(self, name: str) -> Tuple[ConceptType, int, BloomLevel]:
        """Infers (concept_type, difficulty 1-5, bloom_level) based on pedagogical terminology."""
        n_low = name.lower()

        # Problem solving / mathematical / algorithmic
        if any(w in n_low for w in ["algorithm", "complexity", "proof", "decomposition", "calculus", "solver", "heuristic", "optimization", "graph", "tree", "matrix"]):
            return ("problem_solving", 4, "Apply")

        # Analytical / theoretical / architectural
        if any(w in n_low for w in ["architecture", "normal form", "bcnf", "3nf", "concurrency", "serializability", "protocol", "deadlock", "tradeoff", "analysis"]):
            return ("analytical", 4, "Analyze")

        # Practical / hands-on / programming
        if any(w in n_low for w in ["sql", "dml", "ddl", "code", "implementation", "syntax", "library", "queries", "demo", "lab", "terminal"]):
            return ("practical", 3, "Apply")

        # Procedural / step-by-step
        if any(w in n_low for w in ["pipeline", "process", "recovery", "walkthrough", "procedure", "execution", "lifecycle"]):
            return ("procedural", 3, "Understand")

        # Conceptual / foundational
        if any(w in n_low for w in ["introduction", "overview", "definition", "concept", "characteristics", "fundamentals"]):
            return ("conceptual", 2, "Understand")

        # High difficulty advanced topics
        if any(w in n_low for w in ["advanced", "distributed", "fault-tolerant", "deep learning", "neural", "compiler", "kernel"]):
            return ("analytical", 5, "Evaluate")

        return ("conceptual", 3, "Understand")


nlp_provider = DeterministicNLPProvider()
