# FPCR Create & Verify Flow Diagrams

**Date:** 2026-04-12

**Related:** [260412-fpcr-flow-design.md](./260412-fpcr-flow-design.md)

---

## 1. Overall Architecture

```mermaid
graph TB
    subgraph Frontend
        FE[RITM Editor UI]
    end

    subgraph API Layer
        R1[POST /ritm/{id}/match-objects]
        R2[POST /ritm/{id}/create-rules]
        R3[POST /ritm/{id}/generate-evidence]
        R4[GET /ritm/{id}/export-pdf]
    end

    subgraph Services
        IL[InitialsLoader]
        OM[ObjectMatcher]
        PV[PolicyVerifier]
        RC[RuleCreator]
        EG[EvidenceGenerator]
    end

    subgraph External
        CPAIOPS[CPAIOPS Client]
        CSV[FWTeam_admins.csv]
        Cache[Cache Service]
        cpsearch[cpsearch]
    end

    FE --> R1
    FE --> R2
    FE --> R3
    FE --> R4

    R1 --> OM
    R2 --> RC
    R3 --> EG

    OM --> cpsearch
    OM --> CPAIOPS
    RC --> PV
    RC --> CPAIOPS
    PV --> CPAIOPS

    EG --> Cache
    IL --> CSV

    style Frontend fill:#e1f5fe
    style API Layer fill:#fff3e0
    style Services fill:#f3e5f5
    style External fill:#e8f5e9
```

---

## 2. Object Matching Flow

```mermaid
flowchart TD
    Start([Engineer enters IPs/services]) --> Classify[Classify input type]
    Classify --> Search[Search existing objects via cpsearch]

    Search --> Found{Objects found?}

    Found -->|Yes| Score[Score objects]
    Score --> Convention{Matches naming<br/>convention?}
    Convention -->|Yes| Prefer[Prefer convention match]
    Convention -->|No| Usage[Prefer by usage count]
    Prefer --> SelectBest[Select best match]
    Usage --> SelectBest

    Found -->|No| Create{Auto-create<br/>enabled?}
    Create -->|Yes| Generate[Generate name following<br/>convention]
    Create -->|No| Error[Return error]

    Generate --> CreateObj[Create object via CPAIOPS]
    CreateObj --> MarkCreated[Mark as created=True]

    SelectBest --> MarkExisting[Mark as created=False]
    MarkCreated --> Result[Return MatchResult]
    MarkExisting --> Result

    Result --> Next{More inputs?}
    Next -->|Yes| Classify
    Next -->|No| End([Return all results])

    style Start fill:#c8e6c9
    style End fill:#c8e6c9
    style Error fill:#ffcdd2
    style CreateObj fill:#fff9c4
    style SelectBest fill:#b2dfdb
```

---

## 3. Rule Creation Flow

```mermaid
flowchart TD
    Start([Engineer clicks Create & Verify]) --> GroupRules[Group rules by package]

    GroupRules --> PackageLoop{For each package}

    PackageLoop --> CreateRules[Create rules via CPAIOPS]
    CreateRules --> StorePending[Store in DB<br/>status=pending]
    StorePending --> Verify[Verify policy via CPAIOPS]

    Verify --> Verified{Verification<br/>success?}

    Verified -->|Yes| Disable[Disable created rules]
    Disable --> UpdateSuccess[Mark as verified]
    UpdateSuccess --> KeepRules[Keep rules in package]

    Verified -->|No| GetErrors[Get error messages]
    GetErrors --> Rollback[Delete created rules via CPAIOPS]
    Rollback --> UpdateFailed[Mark as failed]
    UpdateFailed --> StoreErrors[Store errors in DB]

    KeepRules --> NextPackage
    StoreErrors --> NextPackage

    NextPackage{More packages?}
    NextPackage -->|Yes| PackageLoop
    NextPackage -->|No| Aggregate[Aggregate results]

    Aggregate --> CalcStats[Calculate totals<br/>created/kept/deleted]
    CalcStats --> Return[Return CreationResult]
    Return --> End([Display results to engineer])

    style Start fill:#c8e6c9
    style End fill:#c8e6c9
    style Rollback fill:#ffcdd2
    style KeepRules fill:#c8e6c9
    style Disable fill:#fff9c4
```

---

## 4. Evidence Generation Flow

```mermaid
flowchart TD
    Start([Engineer clicks Generate Evidence]) --> GetChanges[Get show-changes<br/>from API session]

    GetChanges --> ParseChanges[Parse changes by<br/>domain > package > section]
    ParseChanges --> LoadResults[Load verification<br/>results from DB]

    LoadResults --> RenderHTML[Render HTML template]
    RenderHTML --> StyleHTML[Apply Smart Console<br/>CSS styling]

    LoadResults --> GenYAML[Generate CPCRUD<br/>YAML format]
    GenYAML --> ValidateYAML[Validate against<br/>checkpoint_ops_schema.json]

    StyleHTML --> Combine[Combine artifacts]
    ValidateYAML --> Combine
    GetChanges --> Combine

    Combine --> StoreDB[Store in RITM record]
    StoreDB --> Return[Return HTML, YAML, Changes]
    Return --> Display[Display in browser]

    Display --> ExportPDF{Export PDF?}
    ExportPDF -->|Yes| RenderPDF[Render PDF via WeasyPrint]
    RenderPDF --> Download[Download PDF file]
    Download --> End([Complete])

    ExportPDF -->|No| End

    style Start fill:#c8e6c9
    style End fill:#c8e6c9
    style ValidateYAML fill:#b2dfdb
    style RenderPDF fill:#fff9c4
```

---

## 5. Full Engineer 1 Workflow

```mermaid
stateDiagram-v2
    [*] --> CreatingRITM: Engineer starts
    CreatingRITM --> EnteringInputs: RITM created
    EnteringInputs --> MatchingObjects: IPs/services entered
    MatchingObjects --> DefiningRules: Objects matched/created
    DefiningRules --> CreatingRules: Rules defined
    CreatingRules --> GeneratingEvidence: Rules created & verified
    GeneratingEvidence --> ReviewingEvidence: Evidence generated
    ReviewingEvidence --> ReadyForApproval: Engineer satisfied
    ReviewingEvidence --> DefiningRules: Needs changes

    ReadyForApproval --> [*]: Submitted for approval

    note right of MatchingObjects
        Objects auto-created
        if not found
        following naming
        conventions
    end note

    note right of CreatingRules
        Verify per package
        Rollback failed packages
        Keep verified rules
    end note

    note right of GeneratingEvidence
        HTML evidence card
        YAML export
        PDF download
    end note
```

---

## 6. Peer Review Workflow (Engineer 2)

```mermaid
stateDiagram-v2
    [*] --> ViewingQueue: Peer selects approval queue
    ViewingQueue --> LockingRITM: Selects RITM
    LockingRITM --> ViewingEvidence: Lock acquired
    ViewingEvidence --> Approving: Evidence reviewed
    ViewingEvidence --> Rejecting: Feedback needed
    ViewingEvidence --> Canceling: Cancel review

    Approving --> EnablingRules: Approve clicked
    EnablingRules --> Verifying: Re-verify policy
    Verifying --> Publishing: Verification success
    Publishing --> Approved: Rules published
    Approved --> [*]: Complete

    Rejecting --> Returning: Enter feedback
    Returning --> WorkInProgress: RITM returned
    WorkInProgress --> [*]: Creator notified

    Canceling --> [*]: Lock released

    note right of Approving
        Enable disabled rules
        Re-verify policy
        Publish with session name
    end note

    note right of Rejecting
        Provide feedback
        Return to creator
        Keep objects/groups
    end note
```

---

## 7. Database State Transitions

```mermaid
stateDiagram-v2
    [*] --> Draft: RITM created
    Draft --> Draft: Policies saved (auto-save)
    Draft --> PartialCreation: Rules creation started

    PartialCreation --> Draft: Creation failed
    PartialCreation --> PartialSuccess: Some packages failed
    PartialCreation --> AllSuccess: All packages verified

    PartialSuccess --> Draft: Creator edits
    PartialSuccess --> ReadyForEvidence: Evidence generated

    AllSuccess --> ReadyForEvidence: Evidence generated
    ReadyForEvidence --> Ready: Evidence approved by creator

    Ready --> Locked: Peer locks for review
    Locked --> Ready: Lock released/timeout
    Locked --> Approved: Peer approves
    Locked --> Rejected: Peer rejects

    Approved --> Completed: Published to Check Point
    Rejected --> Draft: Creator edits

    Completed --> [*]

    note right of PartialSuccess
        Rules in failed packages:
        - Deleted (rolled back)
        Rules in verified packages:
        - Kept (disabled)
    end note

    note right of Approved
        Rules enabled
        Policy published
        Ready for installation
    end note
```

---

## 8. Error Handling Flow

```mermaid
flowchart TD
    Start([Error during operation]) --> ClassifyError{Error type?}

    ClassifyError -->|Object creation| ObjectError[Log error, mark as failed]
    ClassifyError -->|Rule creation| RuleError[Rollback rules in package]
    ClassifyError -->|Verification| VerifyError[Rollback rules in package]
    ClassifyError -->|Evidence| EvidenceError[Return partial evidence]

    ObjectError --> StoreError[Store in ritm_verification]
    RuleError --> StoreError
    VerifyError --> StoreError

    StoreError --> FormatError[Format error message]
    FormatError --> AddToResponse[Add to CreationResult]

    EvidenceError --> AddToResponse

    AddToResponse --> HasFailures{Has failures?}
    HasFailures -->|Yes| MarkFailed[Mark RITM as partial]
    HasFailures -->|No| MarkSuccess[Mark RITM as success]

    MarkFailed --> IncludeErrors[Include errors in<br/>session description]
    MarkSuccess --> Return

    IncludeErrors --> Return[Return result to frontend]
    Return --> End([Display to engineer])

    style Start fill:#ffcdd2
    style Rollback fill:#ffcdd2
    style End fill:#fff3e0
```

---

## 9. Component Interaction Sequence

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as FastAPI
    participant OM as ObjectMatcher
    participant RC as RuleCreator
    participant EG as EvidenceGenerator
    participant CP as CPAIOPS
    participant DB as Database

    FE->>API: POST /ritm/{id}/match-objects
    API->>OM: match_and_create_objects()
    OM->>CP: Query existing objects
    CP-->>OM: Found objects
    OM->>OM: Score & select best
    alt Not found
        OM->>CP: Create new object
        CP-->>OM: Object UID
    end
    OM-->>API: MatchResult[]
    API-->>FE: Matched/created objects

    FE->>API: POST /ritm/{id}/create-rules
    API->>RC: create_rules_with_rollback()
    RC->>DB: Store pending rules
    RC->>CP: Create rules
    CP-->>RC: Rule UIDs
    RC->>CP: verify-policy()
    CP-->>RC: Verification result
    alt Failed
        RC->>CP: Delete rules (rollback)
    end
    RC->>DB: Update verification status
    RC-->>API: CreationResult
    API-->>FE: Results with errors

    FE->>API: POST /ritm/{id}/generate-evidence
    API->>EG: generate_evidence()
    EG->>DB: Load verification results
    EG->>CP: show-changes
    CP-->>EG: Changes response
    EG->>EG: Render HTML template
    EG->>EG: Generate YAML
    EG->>DB: Store evidence
    EG-->>API: Evidence data
    API-->>FE: HTML + YAML + changes
```

---

## 10. Deployment Context

```mermaid
graph LR
    subgraph User Browser
        UI[RITM WebUI]
    end

    subgraph FastAPI Server
        API[API Endpoints]
        Services[Service Layer]
        Templates[Jinja2 Templates]
    end

    subgraph Data Layer
        DB[(SQLite Database)]
        CSV[FWTeam_admins.csv]
        Schema[checkpoint_ops_schema.json]
    end

    subgraph External Services
        CP[Check Point Management]
    end

    UI <--> API
    API <--> Services
    Services <--> Templates
    Services <--> DB
    Services <--> CSV
    Services <--> Schema
    Services <--> CP

    style UI fill:#e3f2fd
    style API fill:#fff3e0
    style Services fill:#f3e5f5
    style DB fill:#e8f5e9
    style CP fill:#ffebee
```
