"""
Story Prompt Module modifed for bais

This module contains the prompts and templates used for generating JIRA user stories
using OpenAI. It follows INVEST principles (Independent, Negotiable, Valuable, 
Estimable, Small, Testable) to create high-quality user stories.

Supports image attachments including Miro diagrams, wireframes, mockups, and process flows.
"""

def get_story_generation_prompt(use_case_text, has_image=False, image_description=None, image_type=None,
                                desired_story_count: int = None, target_ac_per_story: int = None,
                                maximize_mode: bool = False, include_nfr_story: bool = False, 
                                user_feedback: str = None) -> str:
    """Return an improved prompt emphasizing FUNCTIONAL uniqueness for each story's acceptance criteria.

    Differences vs previous version:
      * Removes accidental embedded Python code inside the prompt.
      * Instructs model to generate criteria tied to THAT story's specific actor, actions, domain objects.
      * Requires each story's AC set to be UNIQUE (no copied lines across stories).
      * Encourages scenario naming and varied Given contexts per story.
      * NFR lines only when contextually relevant, avoiding identical boilerplate across stories.
      * Incorporates user feedback from previous generation to improve subsequent iterations.
    
    Args:
        user_feedback: Optional feedback from user about previous story generation to improve quality
    """
    # User feedback enrichment - DEFINE FIRST before using
    feedback_context = ""
    if user_feedback and user_feedback.strip():
        feedback_context = f"""
**CRITICAL: User Feedback from Previous Generation:**
{user_feedback.strip()}

**INSTRUCTIONS:** Carefully address ALL points mentioned in the user feedback above. 
This feedback indicates issues with the previous generation that MUST be corrected in this iteration.
Pay special attention to:
- Specific stories or acceptance criteria that were inaccurate
- Missing scenarios or edge cases
- Terminology or domain-specific language corrections
- Scope adjustments (too broad/narrow)
- Priority or decomposition improvements
"""

    image_context = ""
    if has_image:
        image_type_guidance = get_image_type_guidance(image_type)
        if image_description:
            image_context = f"""
**Visual Context:**
- Type: {image_type or 'diagram/mockup'}
- Content Summary: {image_description}
- Guidance: {image_type_guidance}

Incorporate concrete UI components, flows, data entities, and integration points visible in the image into story decomposition and AC wording.
"""
        else:
            image_context = f"""
**Visual Context:** A {image_type or 'provided'} asset exists. {image_type_guidance}
Use it to drive domain‑specific nouns and interaction verbs in titles and AC.
"""
    
    # Prepend feedback context if available (highest priority)
    if feedback_context:
        image_context = feedback_context + "\n" + image_context

    if desired_story_count and desired_story_count >= 2:
        count_clause = f"exactly {desired_story_count}"
        range_hint = f"Return exactly {desired_story_count} well‑scoped stories."
    else:
        count_clause = "AS MANY persona-based stories as needed (NO artificial minimum or maximum)"
        range_hint = "Create one story per distinct persona/user role. NO LIMITS on story count. Decompose by user personas/actors rather than arbitrary story limits."

    ac_target_clause = (f"Aim for ~{target_ac_per_story} criteria if meaningful." if target_ac_per_story else "Provide 8–15 FUNCTIONAL criteria per story.")
    maximize_clause = ("Push toward upper bound of distinct slices when ambiguity permits." if maximize_mode else "")

    # NFR mode wording
    if include_nfr_story:
        nfr_mode_clause = (
            "Do NOT include a 'Non-Functional Requirements' subsection in any individual functional story. "
            "Instead, collect all NFRs (Security, Performance, Accessibility, Capacity, Failover, Monitoring, Deployment, Backup, Disaster Recovery, Data Integrity, Privacy, etc.) "
            "and place them ONLY in a single final consolidated quality story."
        )
        consolidated_block = """
FINAL CONSOLIDATED NON-FUNCTIONAL STORY (mandatory):
After all functional stories, add one last story:
## Story <next number>: Non-Functional Requirements (Consolidated)
Description: This story captures all cross-cutting quality and operational requirements derived from the functional stories above. Requirements are short, story-specific, and use plain business language (avoid overly technical jargon unless essential).

Acceptance Criteria (treat each as a Given/When/Then bullet for parser compatibility):
For EACH functional story above, identify its relevant non-functional needs and list them here under their category. Cover these categories only if impacted:
- Performance (response times, throughput, latency targets specific to operations mentioned in functional stories)
- Capacity Management (concurrent users, data volumes, peak load handling for described workflows)
- Failover Testing / Resilience (behavior on component failure, retry logic, graceful degradation referenced in functional ACs)
- Component or System Failure (specific services/dependencies identified in stories; recovery expectations)
- IT Service Management (incident response, change control for deployments impacting the stories)
- Compatibility (browsers, devices, platforms if UI stories exist; API version constraints if integration stories exist)
- Monitoring & Alerts (observable metrics & thresholds tied to operations in stories; alerting for anomalies/failures mentioned)
- Deployment Mechanisms (zero-downtime requirements, rollback strategy for features in stories)
- Backup & Restoration (RPO/RTO for data modified by stories; restore testing scope)
- Batches & Schedules (if batch processing appears in stories, list schedule constraints and monitoring)
- Availability (uptime SLA for services used by stories; maintenance window constraints)
- Security (HTTPS/TLS for data in transit mentioned in stories, authorization checks, audit logging for protected actions, input sanitization, OWASP concerns, PII handling, GDPR compliance where applicable)
- Disaster Recovery (failover sites, recovery procedures for critical operations in stories)
- Print & Fulfilment Capability (if print/output generation mentioned in stories)
- Accessibility (WCAG 2.1 AA if UI stories; keyboard navigation, screen reader compatibility, focus management, color contrast for specific UI elements mentioned)
- Data Integrity (transaction consistency, rollback/compensation for workflows in stories; validation/audit trails)
- Observability (logging, tracing for troubleshooting features in stories)

Format each NFR line starting with 'Given' for parser compatibility, e.g.:
- Given authentication workflow executes When credentials are submitted Then the process completes in <2 seconds (Performance for Story 1).
- Given user input fields on login screen When accessed via keyboard Then all fields are navigable and labeled for screen readers (Accessibility for Story 1).
- Given credential transmission When user logs in Then HTTPS is enforced (Security for Story 1).

Use the exact story numbers and feature names from functional stories above; avoid generic placeholders. If a category has no relevant items, skip it entirely.
"""
    else:
        nfr_mode_clause = "Exclude Non-Functional Requirements entirely; produce ONLY functional stories and their functional acceptance criteria."
        consolidated_block = ""

    prompt = f"""
Generate {count_clause} SMALL (1–2 sprint-day) vertical slice JIRA user stories from the use case below.
{range_hint} {maximize_clause}

**CRITICAL: DOMAIN ACCURACY**
- Include ONLY features, systems, and domains explicitly mentioned or clearly implied in the use case input.
- Do NOT default to any specific domain (e.g., Cash Warning, FCA compliance, etc.) unless explicitly present in the input.
- Examples provided below are for FORMAT ILLUSTRATION ONLY - do not copy their domain content.
- Generate stories based solely on the actual use case provided, not on example patterns.

**CRITICAL: PERSONA-BASED STORY CREATION**
- Create separate stories for EACH distinct user persona/role (e.g., Admin, Manager, End User, Guest, System, API Consumer)
- Each persona should have their own story capturing their specific needs and workflows
- NO artificial limits on the number of stories - generate as many as there are distinct personas
- If multiple personas interact with the same feature, create separate stories for each persona's perspective

**MANDATORY: SYSTEM COVERAGE**
- Cover ALL impacted systems explicitly (e.g., AX batch jobs, CX Wealth Portal, MyPru, Salesforce, DA Portal, middleware, document storage)
- Create separate stories for different products/product lines when logic differs
- Include operational access requirements (Salesforce profiles, middleware permissions, system access)
- Specify document storage requirements and locations if applicable

**MANDATORY: EDGE CASES & DEPENDENCIES**
Must include acceptance criteria for:
- Weekend/holiday handling and scheduling
- Feature flag checks and configuration switches
- Exclusions (e.g., DFM relationships, specific account types, restricted products)
- Dependencies: templates, fund lists, configuration flags, reference data
- Communication templates: FCA-compliant email and letter templates (with placeholders)
- Data synchronization across systems
- Batch job timing and dependencies

FORMAT:
Each story starts with: ## Story N: <Action-Oriented Title>

Story decomposition heuristics (apply to find more slices):
* Distinct user roles / personas
* Impacted systems (separate story per system if complex)
* Different products or product lines with varying logic
* Workflow stages (ingest, validate, notify, audit, report, admin config)
* CRUD or lifecycle operations (create, view, update, search/filter, delete/retire)
* Alternate channels / devices / formats
* Error / exception handling surfaces
* Security / permissions variants (different roles, denied attempts)
* Performance / scaling enablers (caching, batching, async handling) only if user-facing value
If a candidate slice cannot be independently valuable or demoable, merge it back.

**STORY DESCRIPTION FORMAT:**
As a <specific role> I want <capability> so that <business value>. 

Follow with 2–4 sentences of context (rules, data, UX intent, impacted systems).

**CRITICAL OUTPUT STRUCTURE:**
- **Description field**: Contains ONLY the user story and context (NO acceptance criteria here)
- **Acceptance Criteria field**: Contains ALL the AC 1, AC 2, AC 3... with Given/When/Then format

**Each AC must be SPECIFIC, CONCRETE, and ACTIONABLE - NO generic placeholders**

Format each acceptance criterion exactly like this example:
```
AC 1 - [Specific action/requirement with concrete details]

GIVEN [specific precondition with actual dates, values, system states]

WHEN [specific trigger event with actual parameters]

THEN [specific expected outcome with actual system names, email addresses, values]
```

**Example of CORRECT format (FORMAT ONLY - use your actual use case domain):**
AC 1 - Automate monthly data reconciliation batch on first business day
GIVEN today's date is the last day of the current month
WHEN the date changes to the first day of the next month
THEN the automated reconciliation batch must be executed at 02:00 AM

AC 2 - Send batch completion notification emails to operations team
GIVEN the monthly reconciliation batch is in progress
WHEN the batch execution is completed successfully
THEN the success email must be sent to operations-team@company.com with subject "Reconciliation Complete - [Month] [Year]"

**WRONG - Do NOT write generic criteria like this:**
❌ Given <specific precondition> When <action> Then <outcome>
❌ Given user has valid credentials When user logs in Then user sees dashboard
❌ Given external system unavailable When operation invoked Then graceful fallback

**RIGHT - Write concrete, business-specific criteria (adapt to YOUR use case domain):**
✅ GIVEN user account USR789456 has subscription status set to 'expired'
✅ WHEN the daily account review batch runs on 15th March 2026 at 03:00 AM
✅ THEN email notification must be sent to account-renewals@company.com with subject "Renewal Required - Account USR789456"

**Mandatory Coverage Areas (create specific ACs for each - ONLY if relevant to your use case):**

1. **Batch/Scheduled Processing (if applicable):**
   - GIVEN todays date is [specific date before trigger]
   - WHEN the date changes to [exact trigger date/time]
   - THEN the [specific batch name] must be executed at [exact scheduled time]

2. **Success Notifications:**
   - GIVEN [specific process/batch] run is in progress
   - WHEN the [process] execution is completed
   - THEN success email must be initiated to [actual email address] with [specific subject line]

3. **Failure Notifications:**
   - GIVEN [specific process/batch] run is in progress
   - WHEN the [process] execution fails because of [specific failure reason]
   - THEN failure email must be initiated to [actual email address] with [error details in body]

4. **Weekend/Holiday Handling:**
   - GIVEN scheduled execution date falls on Saturday/Sunday/[specific holiday]
   - WHEN the scheduled time arrives
   - THEN processing must be deferred to next business day [specific time]

5. **Feature Flag/Configuration:**
   - GIVEN feature flag [actual flag name] is set to [specific value]
   - WHEN [specific action] is triggered
   - THEN [specific behavior] must occur as per flag configuration

6. **Exclusions/Filtering (if applicable to use case):**
   - GIVEN account has [specific exclusion criteria, e.g., inactive status flag = true]
   - WHEN [specific process] evaluates the account
   - THEN account must be excluded from processing with audit log entry "[specific log message]"

7. **Data Validation (if data processing is part of use case):**
   - GIVEN customer record is missing [specific required field, e.g., email address]
   - WHEN validation is performed
   - THEN record must be rejected with error code [actual error code] and logged in error table [actual table name]

8. **System Integration:**
   - GIVEN data is received from [specific source system, e.g., Salesforce]
   - WHEN data synchronization to [specific target system, e.g., AX batch] occurs
   - THEN all [specific fields list] must be mapped correctly and validated against [specific business rules]

9. **Document Storage:**
   - GIVEN [specific document type, e.g., FCA warning letter] is generated
   - WHEN document creation is complete
   - THEN document must be stored in [actual storage location path] with naming convention [specific pattern] and retention period [actual duration]

10. **Template/Communication:**
    - GIVEN customer qualifies for [specific communication type]
    - WHEN communication is triggered
    - THEN [actual template name, e.g., "FCA_Cash_Warning_Q1_2025.docx"] must be used with placeholders populated from [specific data source]

11. **Product-Specific Logic:**
    - GIVEN customer holds [specific product name, e.g., ISA account]
    - WHEN [specific calculation/process] is performed
    - THEN [product-specific rule] must be applied: [exact calculation formula or business logic]

12. **Operational Access:**
    - GIVEN operations user requires access to [specific system/function]
    - WHEN user logs into [specific system, e.g., Salesforce]
    - THEN user must have [specific profile/permission set name] assigned to perform [specific actions list]

**Quality Rules:**
* Use ACTUAL system names from the use case (only mention systems explicitly stated or clearly implied)
* Use ACTUAL email addresses, file paths, table names, field names from the requirements
* Use ACTUAL dates, times, numeric thresholds, timeout values specified in the use case
* Use ACTUAL template names, batch job names, configuration flag names mentioned in requirements
* Use ACTUAL error codes, status codes, audit log messages defined in the use case
* Each AC must be independently testable with clear pass/fail criteria
* Minimum 8-12 ACs per story covering all scenarios relevant to THIS use case
* DO NOT use placeholders like <system>, <value>, <outcome> - be concrete
* DO NOT invent domain-specific content not present in the input

**CRITICAL OUTPUT FORMAT:**
Use this EXACT structure for each story:

## Story N: [Title]

**Description:**
As a [specific role], I want [capability] so that [business value].

[2-4 sentences of context about rules, data, UX intent, impacted systems]

**Acceptance Criteria:**
AC 1 - [Specific action/requirement with concrete details]
GIVEN [specific precondition with actual dates, values, system states]
WHEN [specific trigger event with actual parameters]
THEN [specific expected outcome with actual system names, email addresses, values]

AC 2 - [Specific action/requirement]
GIVEN [specific precondition]
WHEN [specific trigger]
THEN [specific outcome]

[Continue with AC 3, AC 4, etc...]

**Example (FORMAT REFERENCE ONLY - DO NOT copy domain content, use YOUR actual use case):**
## Story 1: Automate Monthly Inventory Reconciliation Process

**Description:**
As an Inventory Manager, I want the monthly inventory reconciliation process to run automatically on the first business day of each month so that I can identify discrepancies early and maintain accurate stock levels for operational planning.

**Acceptance Criteria:**
AC 1 - Schedule automated inventory reconciliation batch for first business day of month
GIVEN today's date is the last day of the current month
WHEN the date changes to the first day of the new month
THEN the inventory reconciliation batch must be executed at 02:00 AM

AC 2 - Send reconciliation completion notification to inventory management team
GIVEN the monthly inventory reconciliation batch is in progress
WHEN the batch execution is completed successfully
THEN the success email must be sent to inventory-ops@company.com with subject "Reconciliation Complete - [Month] [Year]"

AC 3 - Handle weekend and holiday scheduling for reconciliation batch
GIVEN the scheduled execution date falls on Saturday/Sunday/public holiday
WHEN the scheduled time arrives
THEN processing must be deferred to the next business day at 02:00 AM

Quality guardrails:
* Functional scenario bullets are lexically distinct (no duplicates across stories).
* Scenarios collectively cover: success (happy), alternate path, validation error (negative), permission/security denial, system/dependency failure, downstream external interaction & latency; add concurrency / data consistency / end-of-workflow transitions if domain warrants.
* {nfr_mode_clause}
* NFR bullets (if consolidated story requested) are concise, plain language, tailored (no boilerplate).
* No Story Points anywhere.

**FINAL REMINDER - CRITICAL:**
* Base ALL stories on the actual use case provided below - NOT on the examples shown above
* Do NOT include Cash Warning (CW), FCA compliance, or any other domain UNLESS explicitly mentioned in the use case
* Examples are for FORMAT guidance only - use the actual domain, systems, and requirements from the input

Use Case Input:
{use_case_text}
{image_context}
{consolidated_block}
"""
    return prompt

def get_image_type_guidance(image_type):
    """
    Provide specific guidance based on the type of image attachment.
    
    Args:
        image_type (str): Type of image (miro, wireframe, mockup, etc.)
    
    Returns:
        str: Specific guidance for analyzing that image type
    """
    guidance_map = {
        "miro": """
        For Miro boards, pay attention to:
        - Process flows and user journeys mapped out
        - Brainstorming clusters and idea groupings
        - Workflow diagrams and decision points
        - System architecture or component relationships
        - User story mapping and epic breakdowns
        """,
        "wireframe": """
        For wireframes, focus on:
        - Page layouts and component placement
        - Navigation patterns and user flows
        - Input fields, buttons, and interactive elements
        - Information hierarchy and content organization
        - Responsive design considerations
        """,
        "mockup": """
        For mockups, analyze:
        - Visual design and styling requirements
        - Exact UI components and their behaviors
        - Content types and data requirements
        - Interactive states (hover, active, disabled)
        - Brand guidelines and design system elements
        """,
        "process_flow": """
        For process flows, examine:
        - Sequential steps and decision points
        - Different user paths and scenarios
        - System interactions and data exchanges
        - Error handling and exception flows
        - Integration points with external systems
        """,
        "architecture": """
        For architecture diagrams, consider:
        - System components and their responsibilities
        - Data flow between services
        - Integration patterns and APIs
        - Security boundaries and access controls
        - Scalability and performance considerations
        """
    }
    
    return guidance_map.get(image_type, """
    For the provided visual content, analyze:
    - Key components and their relationships
    - User interactions and workflows
    - Data structures and information flow
    - Technical requirements and constraints
    - Any implementation details shown
    """)

def get_system_message():
    """
    Get the system message that defines the AI's role and expertise.
    
    Returns:
        str: System message for OpenAI
    """
    return """You are a Senior Product Owner and Business Analyst with 10+ years of experience in:

**Core Expertise:**
- Agile methodologies (Scrum, Kanban) and user story writing
- JIRA administration, workflow design, and project management
- Requirements gathering, analysis, and stakeholder management
- User experience design and customer journey mapping
- Software development lifecycle and technical architecture
- Acceptance criteria definition using Gherkin (BDD) syntax

**Specialized Skills:**
- Breaking down complex business requirements into implementable stories
- Writing clear, testable acceptance criteria with comprehensive coverage
- Estimating story complexity using Planning Poker and relative sizing
- Identifying technical dependencies and integration requirements
- Ensuring stories deliver measurable business value
- Visual analysis of wireframes, mockups, Miro boards, and process diagrams

**Industry Experience:**
- Enterprise software development and SaaS platforms
- E-commerce and customer-facing applications
- API design and microservices architecture
- Mobile applications and responsive web design
- Data analytics and reporting systems
- Financial services, healthcare, retail, and other regulated industries

**Quality Standards:**
You create detailed, actionable user stories that development teams can implement efficiently while ensuring:
- Stories follow INVEST principles rigorously
- Acceptance criteria are comprehensive and testable
- Technical considerations are thorough but not over-constraining
- Visual materials are properly analyzed and referenced
- Business value is clearly articulated and measurable
- Stories are appropriately sized for sprint execution

**Critical Principles:**
- Generate stories based ONLY on the actual use case provided - do not invent features or domain content
- Include domain-specific features (e.g., Cash Warning, compliance workflows) ONLY when explicitly mentioned in the input
- Examples shown are for format illustration only - adapt content to the actual requirements
- Be precise, complete, and free of hallucinations - if unclear, request clarification

Your stories enable successful sprint planning, development, testing, and stakeholder demos."""

def get_story_refinement_prompt(existing_story, refinement_notes, feedback_source=None):
    """
    Generate a prompt for refining an existing story based on feedback.
    
    Args:
        existing_story (str): The current story content
        refinement_notes (str): Feedback or refinement requirements
        feedback_source (str): Source of feedback (developer, tester, stakeholder, etc.)
    
    Returns:
        str: Prompt for story refinement
    """
    source_context = f" from {feedback_source}" if feedback_source else ""
    
    return f"""
Please refine the following JIRA user story based on feedback{source_context}:

**Current Story:**
{existing_story}

**Refinement Requirements:**
{refinement_notes}

**Refinement Instructions:**
1. **Maintain INVEST Principles:** Ensure the story remains Independent, Negotiable, Valuable, Estimable, Small, and Testable
2. **Update Acceptance Criteria:** Make them more specific, testable, and comprehensive based on feedback
3. **Adjust Scope:** If scope has changed significantly, split into smaller vertical slices where needed (never reintroduce Story Points)
4. **Enhance Technical Notes:** Add any missing implementation considerations or clarify existing ones
5. **Validate Sprint Sizing:** Ensure the story remains completable within one sprint
6. **Clarify Ambiguities:** Address any unclear requirements or edge cases identified
7. **Update Attachments/Labels:** Refresh references to visual materials and update relevant tags
8. **Strengthen Value Proposition:** Ensure business value remains clear and measurable

**Quality Checks:**
- Can this story be developed and tested independently?
- Are the acceptance criteria unambiguous and testable?
- Is the business value clear to all stakeholders?
- Can the development team estimate effort confidently?
- Will this fit within a sprint without blocking other work?

**Refined Story Output:**
[Provide the complete refined story using the standard format, with clear indicators of what changed and why]

**Summary of Changes:**
[Brief explanation of key modifications made and rationale]
"""

def get_epic_breakdown_prompt(epic_description, visual_materials=None):
    """
    Generate a prompt for breaking down an epic into user stories.
    
    Args:
        epic_description (str): Description of the epic or large feature
        visual_materials (str): Description of any visual materials provided
    
    Returns:
        str: Prompt for epic breakdown
    """
    visual_context = f"\n\n**Visual Materials:** {visual_materials}" if visual_materials else ""
    
    return f"""
Break down the following epic into a set of independent, valuable user stories:

**Epic Description:** {epic_description}{visual_context}

**Epic Breakdown Requirements:**

1. **Story Independence:** Each story must be developable and deployable separately
2. **Value Delivery:** Stories should be ordered to deliver value incrementally
3. **Sprint Sizing:** All stories must fit within 1-2 week sprints
4. **Technical Cohesion:** Consider shared technical components and dependencies
5. **User Journey Alignment:** Respect natural user workflow and experience

**Required Output:**

## Epic: [Epic Title]

**Epic Goal:** [High-level business objective and success criteria]

**Epic Acceptance Criteria:**
- [Overall epic completion criteria]
- [Key performance indicators or success metrics]

**Story Breakdown:**

### Story 1: [Foundational/Core Story]
[Complete story format with highest priority]

### Story 2: [Next Most Valuable Story]
[Complete story format]

### Story 3: [Additional Story]
[Complete story format]

[Continue as needed...]

**Implementation Sequence:**
1. **Sprint 1:** [Story X] - [Rationale for priority]
2. **Sprint 2:** [Story Y] - [Rationale for sequencing]
3. **Sprint 3:** [Story Z] - [Dependencies and reasoning]

**Cross-Story Considerations:**
- **Shared Components:** [Common UI elements, APIs, or data models]
- **Dependencies:** [Technical or business dependencies between stories]
- **Risks:** [Potential blockers or integration challenges]

**Definition of Done for Epic:**
- [All stories completed and integrated]
- [Documentation updated]

Generate 3-6 well-structured stories that collectively deliver the epic's value while maintaining independence and sprint-appropriate sizing.
"""

def get_acceptance_criteria_templates():
    """
    Get templates for different types of acceptance criteria.
    
    Returns:
        dict: Dictionary of acceptance criteria templates
    """
    return {
        "user_interface": """
        **UI/UX Acceptance Criteria:**
        • **Given** I am on the [page/screen name]
          **When** I [perform action] on [specific UI element]
          **Then** I should see [expected visual feedback and state change]
        
        • **Given** I am using a [mobile/tablet/desktop] device
          **When** I [interact with the interface]
          **Then** the layout should [responsive behavior]
        
        • **Given** I have [accessibility needs or assistive technology]
          **When** I navigate the interface
          **Then** I should be able to [complete task with appropriate support]
        """,
        
        "api_endpoint": """
        **API Acceptance Criteria:**
        • **Given** I send a [HTTP method] request to [endpoint] with [valid parameters]
          **When** the request is processed
          **Then** I should receive a [status code] response with [expected data structure]
        
        • **Given** I send a request with [invalid/missing parameters]
          **When** the API validates the input
          **Then** I should receive a [error status code] with [descriptive error message]
        
        • **Given** the [external dependency] is unavailable
          **When** I make the API call
          **Then** I should receive [appropriate error response and timeout handling]
        """,
        
        "data_processing": """
        **Data Processing Acceptance Criteria:**
        • **Given** I have [specific data set or input]
          **When** the system processes the data
          **Then** the output should [meet validation rules and format requirements]
        
        • **Given** the input data contains [edge case or boundary condition]
          **When** processing occurs
          **Then** the system should [handle gracefully with appropriate response]
        
        • **Given** processing takes longer than [time threshold]
          **When** the operation is in progress
          **Then** the user should see [progress indicator and status updates]
        """,
        
        "integration": """
        **Integration Acceptance Criteria:**
        • **Given** [external system] is available and responding
          **When** data synchronization occurs
          **Then** [specific data elements] should be [accurately transferred/updated]
        
        • **Given** [external system] returns an error
          **When** integration attempts to connect
          **Then** the system should [retry logic and error handling]
        
        • **Given** data conflicts exist between systems
          **When** synchronization detects conflicts
          **Then** [conflict resolution strategy] should be applied
        """
    }

def get_story_templates_by_type():
    """
    Get story templates for common development patterns.
    
    Returns:
        dict: Dictionary of story templates
    """
    return {
        "crud_operation": """
**Title:** As a [user role], I want to [create/read/update/delete] [entity] so that [business value]

**Description:**
As a [specific user role], I want to [specific CRUD operation] [specific entity/data] so that [clear business benefit and user goal].

[Context about when and why this operation is needed, business rules that apply, and any workflow considerations]

**Acceptance Criteria:**
• **Given** I am a [user role] with [appropriate permissions]
  **When** I [perform the CRUD operation] on [entity]
  **Then** I should [see confirmation and updated state]

• **Given** I attempt to [operation] [entity] without [required permission/data]
  **When** I submit the request
  **Then** I should see [appropriate error message and guidance]

• **Given** the [entity] has [business rule constraints]
  **When** I [attempt operation that violates rules]
  **Then** the system should [prevent action and explain why]

**Technical Notes:**
- API endpoints: [GET/POST/PUT/DELETE endpoints]
- Database changes: [table updates, new fields, indexes]
- Validation rules: [client-side and server-side validation]
- Performance: [expected response times for operations]

**Attachments:** [Reference to data model diagrams or UI mockups]
**Labels:** backend, API, database, [entity-type]
**Sizing:** (Team to estimate; DO NOT include numeric points)
**Priority:** [Based on user workflow dependencies]
**Epic:** [Data Management / User Management / Content Management]
""",
        
        "user_registration": """
**Title:** As a new user, I want to create an account so that I can access personalized features

**Description:**
As a new user visiting the platform, I want to create a user account with my basic information so that I can access personalized features, save my preferences, and receive relevant communications.

**Acceptance Criteria:**
• **Given** I am on the registration page
  **When** I enter valid email, password, and required information
  **Then** I should receive a confirmation email and be redirected to email verification instructions

• **Given** I enter an email that's already registered
  **When** I attempt to create an account
  **Then** I should see a message suggesting login or password reset

• **Given** my password doesn't meet security requirements
  **When** I submit the registration form
  **Then** I should see specific guidance on password requirements

• **Given** I click the verification link in my email
  **When** the system validates the token
  **Then** my account should be activated and I should be logged in

**Technical Notes:**
- Password hashing and security standards
- Email verification workflow and token expiration
- Database schema for user accounts
- Rate limiting for registration attempts
- GDPR compliance for data collection

**Attachments:** Registration flow wireframes
**Labels:** frontend, backend, security, user-management
**Sizing:** (Team to estimate)
**Priority:** High
**Epic:** User Onboarding
""",
        
        "search_functionality": """
**Title:** As a user, I want to search [content type] so that I can quickly find relevant information

**Description:**
As a user looking for specific information, I want to search through [content type] using keywords and filters so that I can quickly locate relevant content without browsing through everything manually.

**Acceptance Criteria:**
• **Given** I enter search terms in the search box
  **When** I submit the search
  **Then** I should see relevant results ranked by relevance with highlighted keywords

• **Given** my search returns many results
  **When** I apply filters [by category, date, type, etc.]
  **Then** the results should update to show only items matching the filters

• **Given** my search returns no results
  **When** I see the empty state
  **Then** I should see suggestions for alternative searches or broader terms

• **Given** I search for [common misspellings or synonyms]
  **When** the search processes my query
  **Then** I should see results for the intended terms with "Did you mean..." suggestions

**Technical Notes:**
- Search index implementation and updating strategy
- Performance requirements for search response time
- Faceted search and filtering capabilities
- Search analytics and query logging
- Mobile-responsive search interface

**Attachments:** Search interface mockups and user flow diagrams
**Labels:** frontend, backend, search, performance
**Sizing:** (Team to estimate)
**Priority:** Medium
**Epic:** Content Discovery
"""
    }

def validate_story_quality(story_content):
    """
    Provide a checklist for validating story quality.
    
    Args:
        story_content (str): The story content to validate
    
    Returns:
        str: Quality validation checklist
    """
    return """
**Story Quality Validation Checklist:**

**INVEST Principles:**
☐ **Independent:** Can be developed without dependencies on other incomplete stories
☐ **Negotiable:** Has room for discussion and alternative implementation approaches
☐ **Valuable:** Delivers clear business value that stakeholders can understand and measure
☐ **Estimable:** Development team can confidently estimate effort and complexity
☐ **Small:** Can be completed within one sprint (1-2 weeks)
☐ **Testable:** Has specific, verifiable acceptance criteria with clear pass/fail conditions

**Content Quality:**
☐ **Clear Title:** Describes what the user accomplishes, not how
☐ **Specific User Role:** Uses precise persona, not generic "user"
☐ **Business Value:** "So that" clause explains real benefit to user or business
☐ **Comprehensive Criteria:** Covers happy path, edge cases, and error scenarios
☐ **Technical Depth:** Includes implementation considerations without over-constraining
☐ **Visual References:** Properly references any attached diagrams or mockups

**Completeness:**
☐ **All Required Fields:** Title, description, acceptance criteria, technical notes, labels (no story points)
☐ **Attachment References:** Clear connections to visual materials when provided
☐ **Dependencies Identified:** Lists any prerequisites or related stories
☐ **Quality Criteria:** Includes performance, security, and accessibility requirements where relevant

**Team Readiness:**
☐ **Development Ready:** Has enough detail for implementation planning
☐ **Testing Ready:** QA can write test cases from acceptance criteria
☐ **Demo Ready:** Stakeholders can see and validate completed functionality
☐ **Documentation Ready:** Technical writers can create user documentation

**Sprint Planning:**
☐ **Atomic Value:** Delivers something users can experience at sprint end
☐ **Risk Assessed:** Major technical unknowns have been identified
☐ **Resource Appropriate:** Matches team capacity and skills
☐ **Definition of Done:** Clear completion criteria aligned with team standards
"""
