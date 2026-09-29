from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from typing import Optional
from app.nlp.deterministic import nlp_provider
from app.schemas.schemas import ExtractedCurriculum
from app.models.entities import User
from app.services.artifact_service import artifact_service
from app.auth.security import get_current_user, limit_uploads
from app.api.courses import read_syllabus_upload

router = APIRouter(prefix="/syllabus", tags=["Syllabus Extraction"], dependencies=[Depends(get_current_user), Depends(limit_uploads)])

@router.post("/upload", response_model=ExtractedCurriculum)
async def upload_syllabus(
    file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
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
            raise HTTPException(
                status_code=400,
                detail="No syllabus content provided. Please upload a PDF file or paste syllabus text to extract."
            )
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve)) from ve
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Syllabus extraction failed: {str(e)}") from e

    # Raw extraction draft in MongoDB (expires via TTL unless confirmed into a course)
    artifact_service.record_extraction(curriculum, course_id=None, extracted_by=current_user.id)

    return curriculum
