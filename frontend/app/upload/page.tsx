"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { Upload, Check, ChevronDown, ChevronRight, X, AlertCircle } from "lucide-react";
import { syllabusAPI, coursesAPI } from "@/lib/api";
import type { ExtractedCurriculum, UnitDraft, TopicDraft, ConceptDraft, OutcomeDraft, Course } from "@/lib/types";

const SAMPLE_SYLLABUS = `Course: Operating Systems
Code: CS304

Course Outcomes
CO1: Explain the role of an operating system and its main services
CO2: Apply CPU scheduling algorithms to a given set of processes
CO3: Analyze deadlock conditions and choose a prevention strategy

UNIT 1: Processes and Threads
Processes: process states, process control block, context switching
Threads: user and kernel threads, multithreading models

UNIT 2: CPU Scheduling
Scheduling basics: CPU burst, turnaround time, waiting time
Scheduling algorithms: FCFS, shortest job first, round robin, priority scheduling

UNIT 3: Synchronization and Deadlocks
Synchronization: critical section problem, mutex locks, semaphores
Deadlocks: deadlock conditions, resource allocation graph, Banker's algorithm

UNIT 4: Memory Management
Paging: page tables, TLB, multilevel paging
Virtual memory: demand paging, page replacement algorithms, thrashing`;

export default function UploadPage() {
  const [curriculum, setCurriculum] = useState<ExtractedCurriculum | null>(null);
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmedCourse, setConfirmedCourse] = useState<{ id: string; title: string; code: string } | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [rawText, setRawText] = useState("");
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [expandedUnits, setExpandedUnits] = useState<Set<number>>(new Set());
  const fileRef = useRef<HTMLInputElement>(null);

  // Target Course mode: "new" or "existing"
  const [targetMode, setTargetMode] = useState<"new" | "existing">("new");
  const [targetCourseId, setTargetCourseId] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Editable course parameters
  const [courseTitle, setCourseTitle] = useState("");
  const [courseCode, setCourseCode] = useState("");
  const [semester, setSemester] = useState(() => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1; // 1-based
    return month >= 6 && month <= 11 ? `Fall ${year}` : `Spring ${year}`;
  });
  const [academicYear, setAcademicYear] = useState(() => {
    const now = new Date();
    const y = now.getFullYear();
    const m = now.getMonth() + 1;
    // Academic year starts in June; if we're Jan–May we're still in the prev year's cycle
    const start = m >= 6 ? y : y - 1;
    return `${start}-${start + 1}`;
  });
  const [totalClasses, setTotalClasses] = useState(40);
  const [periodDuration, setPeriodDuration] = useState(55);

  useEffect(() => {
    const urlParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
    const cid = urlParams?.get("courseId");

    coursesAPI.list().then((c) => {
      setCourses(c);
      if (cid && c.some((item) => item.id === cid)) {
        setTargetMode("existing");
        setTargetCourseId(cid);
        const match = c.find((item) => item.id === cid);
        if (match) {
          setCourseTitle(match.title);
          setCourseCode(match.code);
          setSemester(match.semester);
          setTotalClasses(match.total_classes);
          setPeriodDuration(match.period_duration);
        }
      } else if (c.length > 0) {
        setTargetCourseId(c[0].id);
      }
    }).catch(() => {});
  }, []);

  const handleUpload = async (file?: File, text?: string) => {
    setLoading(true);
    setConfirmedCourse(null);
    setErrorMessage(null);
    setUploadedFileName(file ? file.name : null);
    try {
      const result = await syllabusAPI.upload(file, !file ? text || undefined : undefined);
      setCurriculum(result);
      if (result.course_name && result.course_name !== "Untitled Course") {
        setCourseTitle(result.course_name);
      }
      if (result.course_code) {
        setCourseCode(result.course_code);
      }
      // Auto-populate from NLP-extracted document metadata when available
      if (result.semester) setSemester(result.semester);
      if (result.academic_year) setAcademicYear(result.academic_year);
      if (result.suggested_total_classes) setTotalClasses(result.suggested_total_classes);
      if (result.suggested_period_duration) setPeriodDuration(result.suggested_period_duration);
      setExpandedUnits(new Set(result.units.map((_, i) => i)));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "The syllabus could not be read.";
      setErrorMessage(msg);
    }
    setLoading(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const handleConfirm = async () => {
    if (!curriculum) return;
    setConfirming(true);
    try {
      let activeCourseId = targetCourseId;

      if (targetMode === "new") {
        // Create brand new course for this subject
        const newCourse = await coursesAPI.create({
          code: courseCode.trim() || curriculum.course_code,
          title: courseTitle.trim() || curriculum.course_name,
          semester: semester.trim(),
          total_classes: totalClasses,
          period_duration: periodDuration,
          academic_year: academicYear,
          section_name: "Section A",
        });
        activeCourseId = newCourse.id;
        // Refresh course list
        const updatedCourses = await coursesAPI.list();
        setCourses(updatedCourses);
      }

      if (activeCourseId) {
        await coursesAPI.confirmCurriculum(activeCourseId, {
          course_name: courseTitle.trim() || curriculum.course_name,
          course_code: courseCode.trim() || curriculum.course_code,
          units: curriculum.units,
          outcomes: curriculum.outcomes,
        });

        setConfirmedCourse({
          id: activeCourseId,
          title: courseTitle.trim() || curriculum.course_name,
          code: courseCode.trim() || curriculum.course_code,
        });
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Saving failed");
    }
    setConfirming(false);
  };

  const toggleUnit = (idx: number) => {
    setExpandedUnits((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const updateOutcome = (idx: number, desc: string) => {
    if (!curriculum) return;
    const nextOutcomes = [...curriculum.outcomes];
    nextOutcomes[idx] = { ...nextOutcomes[idx], description: desc };
    setCurriculum({ ...curriculum, outcomes: nextOutcomes });
  };

  const topicCount = curriculum ? curriculum.units.reduce((s, u) => s + u.topics.length, 0) : 0;
  const conceptCount = curriculum
    ? curriculum.units.reduce((s, u) => s + u.topics.reduce((s2, t) => s2 + t.concepts.length, 0), 0)
    : 0;
  const reset = () => {
    setCurriculum(null);
    setConfirmedCourse(null);
    setUploadedFileName(null);
  };

  return (
    <div className="animate-fade-in">
      <header className="page-header">
        <div>
          <h1>Import syllabus</h1>
          <p>
            Give OptiTeach your syllabus as a file or pasted text. It reads the units, topics and course
            outcomes, and you check them here before anything is saved.
          </p>
        </div>
      </header>

      {errorMessage && (
        <div
          role="alert"
          style={{
            padding: "14px 18px",
            marginBottom: 24,
            background: "var(--redpen-wash)",
            borderLeft: "4px solid var(--redpen)",
            borderRadius: "var(--radius-md)",
            display: "flex",
            alignItems: "flex-start",
            gap: 12,
          }}
        >
          <AlertCircle size={20} style={{ color: "var(--redpen)", flexShrink: 0, marginTop: 2 }} />
          <div style={{ flex: 1 }}>
            <strong>{curriculum ? "The course couldn't be saved." : "The syllabus couldn't be read."}</strong>
            <p style={{ marginTop: 4 }}>{errorMessage}</p>
            {!curriculum && (
              <p style={{ color: "var(--pencil)", marginTop: 6 }}>
                Each unit needs its own heading line, such as <code>UNIT 1: Relational Model</code> or{" "}
                <code>Module 2: Normalization</code>, with its topics listed underneath.
              </p>
            )}
          </div>
          <button type="button" className="btn btn-ghost" aria-label="Dismiss" onClick={() => setErrorMessage(null)}>
            <X size={16} />
          </button>
        </div>
      )}

      {!curriculum ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 24 }}>
          <div
            className={`drop-zone ${dragOver ? "drag-over" : ""}`}
            role="button"
            tabIndex={0}
            style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", minHeight: 280 }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                fileRef.current?.click();
              }
            }}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleUpload(f);
                e.target.value = "";
              }}
            />
            <Upload size={36} style={{ color: "var(--ink)", margin: "0 auto 14px" }} />
            <h2 style={{ fontSize: "1.05rem", marginBottom: 6 }}>
              {loading
                ? `Reading ${uploadedFileName ? `"${uploadedFileName}"` : "the syllabus"}…`
                : "Drop a syllabus file here, or click to choose one"}
            </h2>
            <p style={{ color: "var(--pencil)" }}>PDF (.pdf), plain text (.txt) or Markdown (.md)</p>
          </div>

          <div className="card" style={{ padding: 24, display: "flex", flexDirection: "column" }}>
            <label htmlFor="syllabus-text" style={{ fontWeight: 700, marginBottom: 10 }}>
              Or paste the syllabus text
            </label>
            <textarea
              id="syllabus-text"
              className="input"
              style={{ flex: 1, minHeight: 200, resize: "vertical", fontFamily: "var(--font-mono)", fontSize: "0.88rem" }}
              placeholder={`Course: Database Management Systems
Code: CS302

UNIT 1: Relational Model
Keys: super key, candidate key, foreign key
Relational algebra: selection, projection, join

UNIT 2: Normalization
Functional dependencies: closure, minimal cover
Normal forms: 1NF, 2NF, 3NF, BCNF`}
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => handleUpload(undefined, rawText)}
                disabled={loading || !rawText.trim()}
                style={{ flex: 1 }}
              >
                {loading ? <><div className="spinner" /> Reading…</> : "Read this syllabus"}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setRawText(SAMPLE_SYLLABUS);
                  handleUpload(undefined, SAMPLE_SYLLABUS);
                }}
                disabled={loading}
                title="Fills in a short Operating Systems syllabus and reads it"
              >
                Try the sample syllabus
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="animate-fade-in-up">
          {confirmedCourse && (
            <div
              role="status"
              style={{
                padding: "16px 20px",
                marginBottom: 24,
                background: "var(--tick-wash)",
                borderLeft: "4px solid var(--tick)",
                borderRadius: "var(--radius-md)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 16,
              }}
            >
              <div>
                <strong style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Check size={18} style={{ color: "var(--tick)" }} /> Saved to {confirmedCourse.code}
                </strong>
                <p style={{ color: "var(--pencil)", marginTop: 4 }}>
                  {confirmedCourse.title} curriculum confirmed! The semester time plan (MILP optimization), curriculum knowledge graph, and class sessions have been automatically generated.
                </p>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Link href={`/courses/${confirmedCourse.id}`} className="btn btn-primary">Open course</Link>
                <Link href={`/optimization?courseId=${confirmedCourse.id}`} className="btn btn-secondary">View time plan</Link>
                <Link href={`/curriculum?courseId=${confirmedCourse.id}`} className="btn btn-secondary">Curriculum graph</Link>
                <Link href={`/calendar?courseId=${confirmedCourse.id}`} className="btn btn-secondary">Class calendar</Link>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    reset();
                    setRawText("");
                  }}
                >
                  Import another
                </button>
              </div>
            </div>
          )}

          <section className="card" style={{ padding: 22, marginBottom: 24 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap", marginBottom: 16 }}>
              <div>
                <h2 style={{ fontSize: "1.2rem" }}>Check what was found</h2>
                <p style={{ color: "var(--pencil)", marginTop: 4 }}>
                  {curriculum.units.length} units, {topicCount} topics and {conceptCount} concepts
                  {curriculum.outcomes.length > 0 ? `, plus ${curriculum.outcomes.length} course outcomes` : ""}.
                  {curriculum.confidence_score < 0.6 && " Some headings were unclear, so look through the units carefully."}
                </p>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button type="button" className="btn btn-ghost" onClick={reset}>
                  {confirmedCourse ? "Close" : "Start over"}
                </button>
                {!confirmedCourse && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={handleConfirm}
                    disabled={confirming || (targetMode === "existing" && !targetCourseId)}
                  >
                    {confirming
                      ? <><div className="spinner" /> Saving…</>
                      : <><Check size={16} /> {targetMode === "new" ? "Create course and save" : "Save to course"}</>}
                  </button>
                )}
              </div>
            </div>

            <fieldset style={{ border: "none", padding: 0, margin: "0 0 18px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
              <legend style={{ fontWeight: 700, marginBottom: 8 }}>Where should it go?</legend>
              <label style={{ display: "flex", gap: 10, alignItems: "flex-start", cursor: "pointer" }}>
                <input type="radio" name="targetMode" checked={targetMode === "new"} onChange={() => setTargetMode("new")} style={{ marginTop: 4 }} />
                <span>
                  <strong>A new course</strong>
                  <span style={{ display: "block", color: "var(--pencil)" }}>Creates the course with the details below.</span>
                </span>
              </label>
              <label style={{ display: "flex", gap: 10, alignItems: "flex-start", cursor: courses.length ? "pointer" : "not-allowed", opacity: courses.length ? 1 : 0.5 }}>
                <input
                  type="radio"
                  name="targetMode"
                  checked={targetMode === "existing"}
                  onChange={() => setTargetMode("existing")}
                  disabled={courses.length === 0}
                  style={{ marginTop: 4 }}
                />
                <span style={{ flex: 1 }}>
                  <strong>A course I already have</strong>
                  <span style={{ display: "block", color: "var(--pencil)" }}>Replaces that course&apos;s units and outcomes.</span>
                  {targetMode === "existing" && (
                    <select
                      className="input-select"
                      aria-label="Course to replace"
                      value={targetCourseId}
                      onChange={(e) => setTargetCourseId(e.target.value)}
                      style={{ marginTop: 8, width: "100%" }}
                    >
                      {courses.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.code}: {c.title} ({c.semester})
                        </option>
                      ))}
                    </select>
                  )}
                </span>
              </label>
            </fieldset>

            {targetMode === "new" && (
              <div className="form-grid">
                <label className="field" style={{ gridColumn: "span 2" }}>
                  Title
                  <input className="input" value={courseTitle} onChange={(e) => setCourseTitle(e.target.value)} placeholder="Database Management Systems" />
                </label>
                <label className="field">
                  Code
                  <input className="input" value={courseCode} onChange={(e) => setCourseCode(e.target.value.toUpperCase())} placeholder="CS302" />
                </label>
                <label className="field">
                  Semester
                  <input className="input" value={semester} onChange={(e) => setSemester(e.target.value)} placeholder="Fall 2026" />
                </label>
                <label className="field" style={{ gridColumn: "span 2" }}>
                  Periods in the semester
                  <input className="input" type="number" min={1} value={totalClasses} onChange={(e) => setTotalClasses(Number(e.target.value))} />
                </label>
                <label className="field" style={{ gridColumn: "span 2" }}>
                  Minutes per period
                  <input className="input" type="number" min={1} value={periodDuration} onChange={(e) => setPeriodDuration(Number(e.target.value))} />
                </label>
              </div>
            )}
          </section>

          {curriculum.outcomes.length > 0 && (
            <section className="card" style={{ padding: 20, marginBottom: 20 }}>
              <h2 style={{ fontSize: "1.05rem" }}>Course outcomes</h2>
              <p style={{ color: "var(--pencil)", margin: "4px 0 14px" }}>
                Edit the wording if needed. The level on the right says what students should be able to do, from remember up to create.
              </p>
              <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                {curriculum.outcomes.map((o: OutcomeDraft, i: number) => (
                  <li key={i} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <strong style={{ minWidth: 44 }}>{o.code}</strong>
                    <input
                      className="input"
                      aria-label={`${o.code} description`}
                      value={o.description}
                      onChange={(e) => updateOutcome(i, e.target.value)}
                      style={{ flex: 1 }}
                    />
                    <span className="badge badge-neutral" style={{ minWidth: 90, justifyContent: "center" }}>{o.bloom_level}</span>
                  </li>
                ))}
              </ol>
            </section>
          )}

          <section>
            <h2 style={{ fontSize: "1.05rem", marginBottom: 12 }}>Units and topics</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {curriculum.units.map((unit: UnitDraft, uIdx: number) => {
                const open = expandedUnits.has(uIdx);
                return (
                  <div key={uIdx} className="card" style={{ overflow: "hidden" }}>
                    <button
                      type="button"
                      aria-expanded={open}
                      onClick={() => toggleUnit(uIdx)}
                      style={{
                        all: "unset",
                        boxSizing: "border-box",
                        width: "100%",
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        padding: "14px 20px",
                        cursor: "pointer",
                        borderBottom: open ? "1px solid var(--border-default)" : "none",
                      }}
                    >
                      {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      <strong>Unit {unit.unit_number}: {unit.title}</strong>
                      <span style={{ marginLeft: "auto", color: "var(--pencil)" }}>{unit.topics.length} topics</span>
                    </button>
                    {open && (
                      <div style={{ padding: "4px 20px 16px" }}>
                        {unit.topics.map((topic: TopicDraft, tIdx: number) => (
                          <div key={tIdx} style={{ marginTop: 12 }}>
                            <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                              <span style={{ fontWeight: 600 }}>{topic.title}</span>
                              <span style={{ color: "var(--pencil)", fontSize: "0.88rem" }}>about {topic.estimated_minutes} min</span>
                            </div>
                            {topic.concepts.length > 0 && (
                              <ul style={{ margin: "6px 0 0", paddingLeft: 20, display: "flex", flexDirection: "column", gap: 4 }}>
                                {topic.concepts.map((concept: ConceptDraft, cIdx: number) => (
                                  <li key={cIdx} style={{ fontSize: "0.92rem" }}>
                                    {concept.name}
                                    <span style={{ color: "var(--pencil)" }}>
                                      {" "}(difficulty {concept.difficulty} of 5
                                      {concept.prerequisites.length > 0 ? `; needs ${concept.prerequisites.join(", ")}` : ""})
                                    </span>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
