## ADDED Requirements

### Requirement: Phased Product Blueprint

The NEXT product planning document MUST distinguish long-term direction from bounded, independently useful delivery phases and MUST include a separately identifiable first-phase scope after the overall design.

#### Scenario: A developer reads the blueprint

- **WHEN** a developer prepares a first-phase implementation proposal
- **THEN** the document identifies first-phase user outcomes, included and excluded capabilities, dependencies, and verifiable acceptance scenarios
- **AND** later-phase capabilities are not implicitly prerequisites for first-phase acceptance
- **AND** future runtime functionality is not presented as already implemented

### Requirement: Explicit Collaboration And Evidence Boundaries

The blueprint MUST document product ownership, frontend design and primary implementation ownership, backend design review responsibility, and the distinction between observed, inferred, stale, and unknown information.

#### Scenario: Work is delegated to another developer

- **WHEN** a developer proposes a backend work package
- **THEN** the blueprint provides product requirements and review criteria without prescribing a fixed task count or unapproved database and API designs
- **AND** Codex remains responsible for frontend design consistency and review of cross-module network behavior

### Requirement: Draft And Approval Status

Planning artifacts MUST remain explicitly marked as drafts until the user confirms their scope, and the document MUST describe user confirmation before stage closeout begins.

#### Scenario: The document draft is produced

- **WHEN** the blueprint is written and document checks pass
- **THEN** first-phase scope confirmation and change closeout remain pending user approval
- **AND** documentation completion does not mark the planned frontend or backend features as delivered

### Requirement: Discoverable Two-Way Handoff

The blueprint MUST link to a first-phase collaboration entry identifying frontend and backend responsibilities, the backend intake request, and a place for implementation feedback and design review outcomes without duplicating the product scope or implementation task lists.

#### Scenario: A backend developer joins the work

- **WHEN** a developer opens the collaboration entry linked from the blueprint
- **THEN** they can find the first-phase requirements, baseline verification request, pending review items, and the next responsible role
- **AND** they can record a proposal and evidence for Codex review without asking the user to relay technical details
- **AND** no response or approval is assumed before it is recorded

#### Scenario: Work resumes in another session or after documentation archive

- **WHEN** a collaborator resumes the work from the blueprint
- **THEN** its handoff entry identifies the current collaboration location or an explicitly pending-start archived reference
- **AND** active feedback is not silently lost during archive or maintained in two competing records
- **AND** cross-workspace availability and notification requirements are explicit rather than assumed to happen automatically
