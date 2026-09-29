"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Upload } from "lucide-react";
import { coursesAPI } from "@/lib/api";
import type { Course } from "@/lib/types";

const ROLE_NOTE: Record<string, string> = { co_teacher: "Shared with you (co-teacher)", viewer: "Shared with you (view only)" };

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<Course | null>(null);

  useEffect(() => {
    coursesAPI.list().then(setCourses).catch(() => setCourses([]));
  }, []);

  if (courses === null) return <div className="skeleton" style={{ height: 240 }} />;

  return (
    <div className="animate-fade-in">
      <header className="page-header">
        <div>
          <h1>Courses</h1>
          <p>Your courses, and any a colleague has shared with you.</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
          <Plus size={16} /> New course
        </button>
      </header>

      {courses.length === 0 ? (
        <div style={{ maxWidth: 520 }}>
          <p style={{ marginBottom: 16 }}>You don&apos;t have any courses yet. Create one, then import its syllabus to lay out the topics.</p>
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}><Plus size={16} /> New course</button>
        </div>
      ) : (
        <ul className="course-list">
          {courses.map((c) => (
            <li key={c.id}>
              <Link href={`/courses/${c.id}`} className="course-row">
                <span className="course-row__code">{c.code}</span>
                <span className="course-row__main">
                  <strong>{c.title}</strong>
                  <span>
                    {c.semester}, {c.total_classes} periods of {c.period_duration} min
                    {ROLE_NOTE[c.my_role] ? `. ${ROLE_NOTE[c.my_role]}` : ""}
                  </span>
                </span>
                <span className="course-row__status">
                  {c.units_count === 0
                    ? <span className="badge badge-warning">Needs a syllabus</span>
                    : <span style={{ color: "var(--pencil)" }}>{c.topics_count} topics, {c.concepts_count} concepts</span>}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {creating && (
        <NewCourseDialog
          onClose={() => setCreating(false)}
          onCreated={(c) => { setCourses((prev) => [...(prev || []), c]); setCreating(false); setCreated(c); }}
        />
      )}

      {created && (
        <div className="modal-overlay" onClick={() => setCreated(null)}>
          <div className="modal-content" role="dialog" aria-modal="true" aria-labelledby="created-title" style={{ maxWidth: 480 }} onClick={(e) => e.stopPropagation()}>
            <h2 id="created-title" style={{ fontSize: "1.3rem" }}>{created.code} is ready.</h2>
            <p style={{ color: "var(--pencil)", margin: "8px 0 20px" }}>
              Import its syllabus next: OptiTeach reads the units, topics and course outcomes, and you check them before anything is saved.
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Link href={`/upload?courseId=${created.id}`} className="btn btn-primary"><Upload size={16} /> Import syllabus</Link>
              <Link href={`/courses/${created.id}`} className="btn btn-secondary">Open the course</Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function NewCourseDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (c: Course) => void }) {
  const [form, setForm] = useState(() => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const defaultSemester = month >= 6 && month <= 11 ? `Fall ${year}` : `Spring ${year}`;
    const startYear = month >= 6 ? year : year - 1;
    const defaultAcademicYear = `${startYear}-${startYear + 1}`;
    return {
      code: "", title: "", semester: defaultSemester, academic_year: defaultAcademicYear,
      total_classes: 40, period_duration: 55, section_name: "Section A", student_count: 60,
    };
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (field: keyof typeof form, numeric = false) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [field]: numeric ? Number(e.target.value) : e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onCreated(await coursesAPI.create(form));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the course");
    }
    setBusy(false);
  };

  const total = form.total_classes * form.period_duration;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" role="dialog" aria-modal="true" aria-labelledby="new-course-title" style={{ maxWidth: 560, width: "100%" }} onClick={(e) => e.stopPropagation()}>
        <h2 id="new-course-title" style={{ fontSize: "1.3rem" }}>New course</h2>
        <form onSubmit={submit} className="form-grid" style={{ marginTop: 12 }}>
          <label className="field">Code<input className="input" required placeholder="CS302" value={form.code} onChange={set("code")} /></label>
          <label className="field" style={{ gridColumn: "span 3" }}>Title<input className="input" required placeholder="Database Management Systems" value={form.title} onChange={set("title")} /></label>
          <label className="field" style={{ gridColumn: "span 2" }}>Semester<input className="input" required placeholder="Fall 2026" value={form.semester} onChange={set("semester")} /></label>
          <label className="field" style={{ gridColumn: "span 2" }}>Academic year<input className="input" value={form.academic_year} onChange={set("academic_year")} /></label>
          <label className="field" style={{ gridColumn: "span 2" }}>Periods in the semester<input className="input" type="number" min={1} value={form.total_classes} onChange={set("total_classes", true)} /></label>
          <label className="field" style={{ gridColumn: "span 2" }}>Minutes per period<input className="input" type="number" min={1} value={form.period_duration} onChange={set("period_duration", true)} /></label>
          <label className="field" style={{ gridColumn: "span 2" }}>Section<input className="input" value={form.section_name} onChange={set("section_name")} /></label>
          <label className="field" style={{ gridColumn: "span 2" }}>Students<input className="input" type="number" min={1} value={form.student_count} onChange={set("student_count", true)} /></label>
          <p style={{ gridColumn: "1 / -1", color: "var(--pencil)" }}>
            That&apos;s {total.toLocaleString()} minutes of teaching to plan.
          </p>
          {error && <p role="alert" style={{ gridColumn: "1 / -1", color: "var(--redpen)", fontWeight: 600 }}>{error}</p>}
          <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={busy}>{busy ? "Creating…" : "Create course"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
