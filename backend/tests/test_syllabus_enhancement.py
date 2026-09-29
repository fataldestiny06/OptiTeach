import io
import pymupdf
from fastapi.testclient import TestClient
from app.main import app
from app.nlp.deterministic import nlp_provider
from app.schemas.schemas import ExtractedCurriculum

client = TestClient(app)


def test_extract_from_pdf_pymupdf():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 60), """Course: Distributed Database Systems
Code: CS402

Course Outcomes:
CO1: Explain distributed database architecture and data fragmentation
CO2: Apply distributed query optimization and semi-join techniques
CO3: Evaluate two-phase commit and distributed concurrency control

UNIT 1: Distributed Architectures and Fragmentation (8 Hours)
Architecture: client-server systems, peer-to-peer systems, multidatabase systems
Fragmentation: horizontal fragmentation, vertical fragmentation, mixed fragmentation

UNIT 2: Distributed Query Optimization (10 Hours)
Query processing: query decomposition, data localization, global query optimization
Join strategies: semi-join algorithm, bloom filters, distributed join ordering

UNIT 3: Distributed Transactions and Reliability (8 Hours)
Transactions: distributed transaction management, ACID properties in distributed systems
Commit protocols: two-phase commit protocol, three-phase commit, coordinator election
""")
    pdf_bytes = doc.tobytes()

    curriculum: ExtractedCurriculum = nlp_provider.extract_from_pdf(pdf_bytes)
    assert curriculum.course_code == "CS402"
    assert "Distributed Database" in curriculum.course_name
    assert len(curriculum.outcomes) == 3
    assert len(curriculum.units) == 3
    assert curriculum.confidence_score >= 0.85

    # Check units and topics
    assert curriculum.units[0].unit_number == 1
    assert "Distributed Architectures" in curriculum.units[0].title
    assert len(curriculum.units[0].topics) >= 2


def test_extract_from_text_bullet_points():
    text = """
    Course Title: Operating Systems Internals
    Subject Code: OS301
    
    Course Outcomes:
    1. Understand process abstraction and system calls
    2. Analyze scheduling metrics and thread concurrency
    
    UNIT 1: Process and Memory Management
    • Process Control Block and Process States
    • Context Switching and CPU Register Save
    • Paging, Page Tables, and Translation Lookaside Buffer
    
    UNIT 2: Concurrency Control
    • Critical Section Problem and Peterson Algorithm
    • Mutex Locks and Counting Semaphores
    • Deadlock Conditions and Banker Algorithm
    """
    res = nlp_provider.extract_from_text(text)
    assert res.course_code == "OS301"
    assert len(res.outcomes) >= 2
    assert len(res.units) == 2
    # Verify bullets were parsed into concepts
    total_concepts = sum(len(t.concepts) for u in res.units for t in u.topics)
    assert total_concepts >= 6


def test_extract_from_text_numbered_units():
    text = """
    Course: Software Architecture
    Code: CS501
    
    1. Architectural Styles and Patterns (8 Hours)
    Client-server pattern, layered architecture, event-driven architecture, microservices.
    
    2. Quality Attributes and Tactics (8 Hours)
    Availability tactics, modifiability tactics, performance analysis, security auditing.
    
    3. Architecture Documentation (6 Hours)
    Viewpoints, perspectives, C4 model, ADR documentation, component diagrams.
    """
    res = nlp_provider.extract_from_text(text)
    assert res.course_code == "CS501"
    assert len(res.units) == 3
    assert "Architectural Styles" in res.units[0].title
    assert "Quality Attributes" in res.units[1].title


def test_extract_from_text_comma_separated_topics():
    text = """
    Subject Name: Computer Networks
    Code: NET201
    
    UNIT I: Physical and Data Link Layer
    Transmission media, twisted pair, optical fiber, wireless channels, framing, flow control, CRC error checking.
    
    UNIT II: Network Layer and Routing
    IPv4 addressing, subnetting, CIDR, distance vector routing, link state routing, OSPF, BGP protocol.
    """
    res = nlp_provider.extract_from_text(text)
    assert res.course_code == "NET201"
    assert len(res.units) == 2
    assert sum(len(u.topics) for u in res.units) >= 2


def test_extract_from_text_markdown_headings():
    text = """# Artificial Intelligence (AI401)

## Unit 1: Problem Solving and Search
State space search: BFS, DFS, uniform cost search
Informed search: A* search, heuristic design, admissibility

## Unit 2: Knowledge Representation
Propositional logic: syntax, semantics, inference rules
First order logic: quantifiers, unification, resolution refutation
"""
    res = nlp_provider.extract_from_text(text)
    assert res.course_code == "AI401"
    assert len(res.units) == 2
    assert "Search" in res.units[0].title


def test_prerequisite_dag_invariants():
    text = """
    Course: Data Structures
    Code: CS201
    
    UNIT 1: Linear Data Structures
    Arrays and Pointers: dynamic arrays, memory layout, pointer arithmetic
    Linked Lists: singly linked lists, doubly linked lists, circular lists
    
    UNIT 2: Non-Linear Data Structures
    Binary Trees: tree traversal, binary search trees, balanced AVL trees
    Graph Structures: adjacency list, adjacency matrix, topological sort
    """
    res = nlp_provider.extract_from_text(text)
    concept_names = {c.name for u in res.units for t in u.topics for c in t.concepts}

    for u in res.units:
        for t in u.topics:
            for c in t.concepts:
                for p in c.prerequisites:
                    # Prerequisite must exist in the curriculum
                    assert p in concept_names
                    # No concept should have itself as a prerequisite
                    assert p != c.name


def test_api_upload_pdf_endpoint():
    # Login to obtain JWT
    login_resp = client.post("/api/auth/login", json={
        "email": "faculty@optiteach.edu",
        "password": "admin123"
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create dummy PDF
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), """Course: Cloud Computing
Code: CS405

Course Outcomes:
CO1: Understand cloud service and deployment models
CO2: Design fault-tolerant cloud microservices

UNIT 1: Cloud Architecture Fundamentals
Infrastructure: IaaS, PaaS, SaaS models, virtualization, hypervisors
Storage: object storage, block storage, distributed file systems

UNIT 2: Containerization and Orchestration
Containers: Docker engine, image layers, container networking
Orchestration: Kubernetes pods, deployments, services, ingress controllers
""")
    pdf_bytes = doc.tobytes()

    response = client.post(
        "/api/syllabus/upload",
        files={"file": ("cloud_syllabus.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers=headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["course_code"] == "CS405"
    assert len(data["units"]) == 2
    assert len(data["outcomes"]) == 2


def test_api_upload_txt_file_endpoint():
    login_resp = client.post("/api/auth/login", json={
        "email": "faculty@optiteach.edu",
        "password": "admin123"
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    txt_content = b"""Course: Mobile Computing
Code: CS408

UNIT 1: Cellular Networks
GSM: architecture, radio subsystem, call routing, handover

UNIT 2: Wireless LAN
WiFi: 802.11 standards, MAC layer, CSMA/CA, security
"""
    response = client.post(
        "/api/syllabus/upload",
        files={"file": ("mobile_syllabus.txt", io.BytesIO(txt_content), "text/plain")},
        headers=headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["course_code"] == "CS408"
    assert len(data["units"]) == 2
