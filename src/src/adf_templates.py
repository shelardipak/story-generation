"""ADF (Atlassian Document Format) template builder utilities for Jira story creation.

This module converts generated story data structures into ADF JSON ready for the Jira REST API.

Public entry points:
    build_story_description_adf(data: dict) -> dict
        Returns ADF doc for story description rich formatting.
    build_minimal_story_adf(data: dict) -> dict
        Returns a smaller doc (no edge cases / dependencies panels) for lighter issues.

Data contract (expected keys in input data dict):
    story_title: str
    user_role: str
    primary_problem: str
    motivation: str
    business_value: str
    scope_statement: str
    out_of_scope: list[str]
    assumptions: list[str]
    preconditions: list[str]
    postconditions: str
    acceptance_criteria: list[str]   # individual bullets
    gherkin: str                     # multiline Gherkin scenarios (optional)
    edge_cases: list[str]
    nfrs: list[str]
    dependencies: list[str]
    test_summary: str
    links: list[str]
    created_by: str
    generated_timestamp: str
    version: str
    revision_history: list[str]

Graceful degradation: If any list key is missing, it will be treated as empty. Strings missing become ''.

Usage in export flow:
    1. Prepare data mapping in StoryCreation.export_story_to_jira before calling post_story_creation.
    2. Call build_story_description_adf(data) to get ADF JSON.
    3. Pass this ADF JSON instead of plain description if Jira API supports rich text (body is 'description').

Note: Jira Cloud REST API v3 for issue create accepts ADF JSON in the description field when specifying
      the field as an object with 'content' & 'version'. Some helper wrappers may already handle plain text.
      If post_story_creation currently only sends a string, integration will require a small change there.
"""
from __future__ import annotations
from typing import List, Dict, Any
import re

# ---------------------------------------------------------------------------
# Helper constructors
# ---------------------------------------------------------------------------

def _text(text: str) -> Dict[str, Any]:
    return {"type": "text", "text": text or ""}

def _paragraph(text: str) -> Dict[str, Any]:
    return {"type": "paragraph", "content": [_text(text)] if text else []}

def _heading(level: int, text: str) -> Dict[str, Any]:
    return {"type": "heading", "attrs": {"level": level}, "content": [_text(text)]}

def _bullet_list(items: List[str]) -> Dict[str, Any]:
    return {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [ _paragraph(item) ]}
            for item in items if (item or "").strip()
        ]
    }

def _ordered_list(items: List[str]) -> Dict[str, Any]:
    return {
        "type": "orderedList",
        "content": [
            {"type": "listItem", "content": [ _paragraph(item) ]}
            for item in items if (item or "").strip()
        ]
    }

def _panel(panel_type: str, text: str) -> Dict[str, Any]:
    return {
        "type": "panel",
        "attrs": {"panelType": panel_type},
        "content": [_paragraph(text)]
    }

def _code_block(language: str, text: str) -> Dict[str, Any]:
    return {
        "type": "codeBlock",
        "attrs": {"language": language},
        "content": [{"type": "text", "text": text or ""}]
    }

def _rule() -> Dict[str, Any]:
    return {"type": "rule"}

# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _base_doc() -> Dict[str, Any]:
    return {"type": "doc", "version": 1, "content": []}

def build_story_description_adf(data: Dict[str, Any]) -> Dict[str, Any]:
    """Build full ADF document for a story description using rich structure."""
    d = _base_doc()
    c = d["content"]

    # Normalize list fields
    def norm_list(key: str) -> List[str]:
        v = data.get(key)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            # Support single string with newline separated bullets
            parts = [p.strip('-• ').strip() for p in v.split('\n') if p.strip()]
            return parts
        return []

    # Add sections
    c.append(_heading(1, data.get('story_title', 'User Story')))
    c.append(_heading(2, 'User Story'))
    c.append(_paragraph(
        f"As a {data.get('user_role','user')}, I want {data.get('primary_problem','a capability')} so that {data.get('motivation','I achieve value')}."
    ))
    c.append(_heading(2, 'Business Value'))
    c.append(_paragraph(data.get('business_value','')))
    c.append(_heading(2, 'Scope'))
    c.append(_paragraph(data.get('scope_statement','')))
    out_of_scope = norm_list('out_of_scope')
    if out_of_scope:
        c.append(_heading(3, 'Out of Scope'))
        c.append(_bullet_list(out_of_scope))
    assumptions = norm_list('assumptions')
    if assumptions:
        c.append(_heading(2, 'Assumptions'))
        c.append(_bullet_list(assumptions))
    preconditions = norm_list('preconditions')
    if preconditions:
        c.append(_heading(2, 'Preconditions'))
        c.append(_bullet_list(preconditions))
    postconditions = data.get('postconditions')
    if postconditions:
        c.append(_heading(2, 'Postconditions / Success State'))
        c.append(_paragraph(postconditions))
    ac_list = norm_list('acceptance_criteria')
    if ac_list:
        c.append(_heading(2, 'Acceptance Criteria'))
        c.append(_bullet_list(ac_list))
    gherkin = data.get('gherkin')
    if gherkin:
        c.append(_heading(2, 'Gherkin Scenarios'))
        c.append(_code_block('gherkin', gherkin))
    edge_cases = norm_list('edge_cases')
    if edge_cases:
        c.append(_heading(2, 'Edge Cases'))
        c.append(_bullet_list(edge_cases))
    # NFRs removed - only appear in consolidated NFR story
    dependencies = norm_list('dependencies')
    if dependencies:
        c.append(_heading(2, 'Dependencies'))
        c.append(_bullet_list(dependencies))
    test_summary = data.get('test_summary')
    if test_summary:
        c.append(_heading(2, 'Test Coverage Summary'))
        c.append(_paragraph(test_summary))
    links = norm_list('links')
    if links:
        c.append(_heading(2, 'Links'))
        c.append(_paragraph(' | '.join(links)))

    # Footer & revision history
    c.append(_rule())
    footer = f"Generated by {data.get('created_by','JiraTestgenAI')} on {data.get('generated_timestamp','')} (Version {data.get('version','')})"
    c.append(_paragraph(footer))
    revisions = norm_list('revision_history')
    if revisions:
        c.append(_heading(3, 'Revision History'))
        c.append(_bullet_list(revisions))
    return d

def build_story_description_adf_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """Build ADF document following the agreed template structure:

    Sections:
      User Story Template
        - User Story (As a / I want / So that)
        - Requirements (numbered list if provided)
        - Non-Functional Requirements (panel list)
        - Additional Information (free text if present)
        - Acceptance Criteria (bullets, preserving Given/When/Then formatting)

    Input mapping expectations (data dict keys):
      story_title, user_role, primary_problem, motivation
      requirements (list[str] or newline separated string)
      nfrs (list[str])
      additional_info (str)
      acceptance_criteria (list[str] or newline separated string)
    Falls back to existing keys if specialized ones missing (e.g. use assumptions/out_of_scope merged into additional_info).
    """
    d = _base_doc()
    c = d['content']

    def norm_list(value) -> List[str]:
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        if isinstance(value, str):
            return [p.strip('-• ').strip() for p in value.split('\n') if p.strip()]
        return []

    # Helper to create a panel with a heading and arbitrary children nodes
    def _panel_section(panel_type: str, heading_text: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Use a bold paragraph for heading to mitigate Jira theme rendering inconsistencies with heading inside panels.
        heading_para = {
            "type": "paragraph",
            "content": [{"type": "text", "text": heading_text, "marks": [{"type": "strong"}]}]
        }
        return {
            "type": "panel",
            "attrs": {"panelType": panel_type},
            "content": [heading_para, *children]
        }

    # Title heading outside panels
    c.append(_heading(1, data.get('story_title', 'User Story')))

    # User Story panel
    user_story_para = _paragraph(
        f"As a {data.get('user_role','user')}, I want {data.get('primary_problem','a capability')} so that {data.get('motivation','I achieve value')}"
    )
    c.append(_panel_section('info', 'User Story', [user_story_para]))

    # Requirements panel (ordered list if clearly numbered or we can always use ordered list)
    requirements = norm_list(data.get('requirements'))
    if not requirements:
        requirements = norm_list(data.get('preconditions'))[:3] or norm_list(data.get('assumptions'))[:3]
    req_node = _ordered_list(requirements) if requirements else _paragraph('')
    c.append(_panel_section('success', 'Requirements', [req_node]))

    # Non-Functional Requirements panel removed - only in consolidated NFR story

    # Additional Information panel
    add_info = data.get('additional_info')
    if not add_info:
        scope = data.get('scope_statement','')
        out_of_scope = norm_list(data.get('out_of_scope'))
        assumptions = norm_list(data.get('assumptions'))
        parts = []
        if scope: parts.append(f"Scope: {scope}")
        if assumptions: parts.append("Assumptions: " + '; '.join(assumptions))
        if out_of_scope: parts.append("Out of Scope: " + '; '.join(out_of_scope))
        add_info = '\n'.join(parts)
    add_info_node = _paragraph(add_info or '')
    c.append(_panel_section('note', 'Additional Information', [add_info_node]))

    # Acceptance Criteria panel – preserve each criterion as list item; strip leading markdown syntax
    ac_list_raw = data.get('acceptance_criteria')
    ac_list = [re.sub(r'^[-*•]\s*', '', x).strip() for x in norm_list(ac_list_raw)]
    ac_node = _bullet_list(ac_list) if ac_list else _paragraph('')
    c.append(_panel_section('success', 'Acceptance Criteria', [ac_node]))

    # Footer
    c.append(_rule())
    footer = f"Generated by {data.get('created_by','JiraTestgenAI')} on {data.get('generated_timestamp','')} (Template v2)"
    c.append(_paragraph(footer))
    return d

def build_minimal_story_adf(data: Dict[str, Any]) -> Dict[str, Any]:
    """Smaller variant excluding edge cases & some sections to reduce size."""
    keys_to_exclude = {'edge_cases','dependencies','links','revision_history'}
    filtered = {k:v for k,v in data.items() if k not in keys_to_exclude}
    return build_story_description_adf(filtered)

# ---------------------------------------------------------------------------
# Simple validation utilities
# ---------------------------------------------------------------------------

def validate_adf_size(adf: Dict[str, Any], max_bytes: int = 32000) -> bool:
    import json
    raw = json.dumps(adf, ensure_ascii=False)
    return len(raw.encode('utf-8')) <= max_bytes

def summarize_adf(adf: Dict[str, Any]) -> Dict[str, Any]:
    """Return quick stats helpful for debugging before sending to Jira."""
    stats = {
        'node_count': 0,
        'heading_count': 0,
        'list_items': 0,
        'code_blocks': 0,
        'panels': 0,
        'approx_length': 0,
    }
    import json
    raw = json.dumps(adf, ensure_ascii=False)
    stats['approx_length'] = len(raw)

    def walk(node):
        if isinstance(node, dict):
            stats['node_count'] += 1
            t = node.get('type')
            if t == 'heading': stats['heading_count'] += 1
            if t == 'listItem': stats['list_items'] += 1
            if t == 'codeBlock': stats['code_blocks'] += 1
            if t == 'panel': stats['panels'] += 1
            for k in ('content',):
                if k in node and isinstance(node[k], list):
                    for child in node[k]:
                        walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(adf)
    return stats

__all__ = [
    'build_story_description_adf',
    'build_story_description_adf_v2',
    'build_minimal_story_adf',
    'validate_adf_size',
    'summarize_adf',
    'build_story_description_adf_v3'
]

# ---------------------------------------------------------------------------
# Panel layout builder (HTML parity) – v3
# ---------------------------------------------------------------------------

def build_story_description_adf_v3(data: Dict[str, Any]) -> Dict[str, Any]:
    """Build ADF document aligned to presented HTML layout for visual parity.

    Panels:
      - User Story (context paragraph + optional role badge)
      - Requirements (ordered list)
      - Non-Functional Requirements (bullet list)
      - Additional Information (notes paragraph)
      - Acceptance Criteria (bullet list preserving original lines)

    Differences vs v2:
      * Stable ordering tuned for readability in Jira
      * Each panel gets a bold heading paragraph plus optional meta footer line
      * Acceptance Criteria keeps Gherkin-esque lines with hyphen stripping only
      * Optional metadata (metrics, counters) can be passed via data['meta'] dict
    """
    d = _base_doc()
    c = d['content']

    def norm_list(value) -> List[str]:
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        if isinstance(value, str):
            return [p.strip() for p in value.split('\n') if p.strip()]
        return []

    def panel(panel_type: str, title: str, body_nodes: List[Dict[str, Any]], meta: str | None = None):
        # Use a heading level 3 inside panel for larger font while retaining colored panel style.
        heading_node = {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": title}]}
        content_nodes = [heading_node, *body_nodes]
        if meta:
            meta_para = {"type": "paragraph", "content": [{"type": "text", "text": meta, "marks": [{"type": "em"}]}]}
            content_nodes.append(meta_para)
        return {"type": "panel", "attrs": {"panelType": panel_type}, "content": content_nodes}

    # Title outside panels
    c.append(_heading(1, data.get('story_title', 'User Story')))

    # User Story panel – use raw description text paragraphs if provided
    raw_description = data.get('additional_info_raw') or data.get('additional_info') or ''
    # Remove inline Acceptance Criteria heading/content from raw description so AC only appears in dedicated panels
    if raw_description:
        try:
            # Remove markdown heading formats (### Functional Acceptance Criteria) and everything after until next section or end
            raw_description = re.sub(r'(?:^|\n)#{1,6}\s*Functional\s+Acceptance\s+Criteria.*?(?=\n#{1,6}\s+|\Z)', '', raw_description, flags=re.IGNORECASE | re.DOTALL)
            # Pattern: lines starting with **Acceptance Criteria:** or Acceptance Criteria: until a blank line
            raw_description = re.sub(r'(?:^|\n)\*?\*?Acceptance Criteria:?\*?\*?.*?(?=\n\s*\n|$)', '', raw_description, flags=re.IGNORECASE | re.DOTALL)
            raw_description = re.sub(r'(?:^|\n)\*?\*?Non-Functional Requirements:?\*?\*?.*?(?=\n\s*\n|$)', '', raw_description, flags=re.IGNORECASE | re.DOTALL)
            # Remove any trailing bullet points that might be AC leftovers (lines starting with - Given/When/Then)
            raw_description = re.sub(r'(?:\n\s*-\s*Given.*?(?=\n(?![\s-])|$))+', '', raw_description, flags=re.IGNORECASE | re.DOTALL)
            # Strip any remaining ** or *** markup patterns while keeping their inner text
            raw_description = re.sub(r'\*{2,3}([^*]+?)\*{2,3}', r'\1', raw_description)
            # Clean up multiple blank lines
            raw_description = re.sub(r'\n\s*\n\s*\n+', '\n\n', raw_description)
        except Exception:
            pass
    # Treat both single and double newlines as potential paragraph breaks to mirror Streamlit display
    raw_desc_parts = []
    if raw_description:
        # Split on blank line first; then further split remaining large blocks on single newline where lines are short
        primary_blocks = [blk for blk in re.split(r'\n\s*\n', raw_description) if blk.strip()]
        for blk in primary_blocks:
            # If the block contains multiple short lines, keep them as separate paragraphs to preserve formatting
            lines = [l for l in blk.split('\n') if l.strip()]
            if len(lines) > 1 and all(len(l) < 160 for l in lines):
                raw_desc_parts.extend(lines)
            else:
                raw_desc_parts.append(blk.strip())
    def _strip_marks(s: str) -> str:
        """Remove all markdown asterisk emphasis markers (bold/italic) robustly.

        Strategy:
          1. Iteratively remove ***wrapped***, **wrapped**, *wrapped* patterns.
          2. Remove residual unmatched asterisks not used for bullet lists.
        """
        if not s:
            return s
        prev = None
        while prev != s:
            prev = s
            s = re.sub(r'\*{3}([^*]+?)\*{3}', r'\1', s)
            s = re.sub(r'\*{2}([^*]+?)\*{2}', r'\1', s)
            s = re.sub(r'\*{1}([^*]+?)\*{1}', r'\1', s)
        # Remove leftover asterisk runs that are adjacent to word chars (avoid stripping multiplication signs by requiring no digits around)
        s = re.sub(r'(?<!\d)\*+(?!\d)', '', s)
        return s.strip()

    if not raw_desc_parts:
        # No synthesis; present placeholder so user notices missing description
        raw_desc_nodes = [_paragraph("(No description provided)")] 
    else:
        raw_desc_nodes = [_paragraph(_strip_marks(part)) for part in raw_desc_parts]
    
    if not raw_desc_parts:
        # No synthesis; present placeholder so user notices missing description
        raw_desc_nodes = [_paragraph("(No description provided)")] 
    else:
        raw_desc_nodes = [_paragraph(_strip_marks(part)) for part in raw_desc_parts]
    
    role_badge = data.get('user_role')
    if role_badge:
        raw_desc_nodes.append(_paragraph(""))
        raw_desc_nodes.append(_paragraph(f"Role: {role_badge}"))
    c.append(panel('info', 'User Story', raw_desc_nodes))

    # Functional Acceptance Criteria as separate panel (below User Story)
    func_list = [_strip_marks(x) for x in norm_list(data.get('acceptance_functional'))]
    if func_list:
        processed_func_nodes = []
        for x in func_list:
            cleaned = re.sub(r'^[-*•]\s*','', x).strip()
            if '\n' in cleaned:
                parts = [_strip_marks(p) for p in cleaned.split('\n') if p.strip()]
                para_nodes = [{"type": "paragraph", "content": [{"type": "text", "text": part}]} for part in parts]
                processed_func_nodes.append({"type": "listItem", "content": para_nodes})
            else:
                processed_func_nodes.append({"type": "listItem", "content": [_paragraph(cleaned)]})
        c.append(panel('success', 'Functional Acceptance Criteria', [{"type": "bulletList", "content": processed_func_nodes}]))
    
    # Requirements panel
    requirements = norm_list(data.get('requirements'))
    req_node = _ordered_list(requirements) if requirements else _paragraph('')
    c.append(panel('success', 'Requirements', [req_node], meta=f"Total: {len(requirements)}" if requirements else None))

    # (Removed early NFR panel; will unify later with acceptance_nfr entries)

    # Additional Information panel (skip if identical to raw description to prevent duplication)
    add_info = data.get('additional_info') or ''
    raw_desc_compare = (data.get('additional_info_raw') or '').strip()
    if add_info.strip() and add_info.strip() != raw_desc_compare:
        add_info_lines = [p.strip() for p in re.split(r'\n\s*\n', add_info or '') if p.strip()]
        add_info_nodes = [_paragraph(p) for p in add_info_lines] or [_paragraph(add_info or '')]
        c.append(panel('note', 'Additional Information', add_info_nodes))

    # Prepare NFR list (unified single NFR panel shown later)
    acceptance_nfr_raw = [_strip_marks(x) for x in norm_list(data.get('acceptance_nfr'))]
    base_nfr_raw = [_strip_marks(x) for x in norm_list(data.get('nfrs'))]
    # Merge & deduplicate preserving order: acceptance_nfr first (story-specific), then base_nfr
    seen_nfr = set()
    unified_nfr = []
    for src in (acceptance_nfr_raw, base_nfr_raw):
        for item in src:
            key = item.lower()
            if key and key not in seen_nfr:
                seen_nfr.add(key)
                unified_nfr.append(item)
    
    # NFR panel removed - only appears in consolidated NFR story, not individual stories

    # Footer rule and attribution
    c.append(_rule())
    footer = f"Generated by {data.get('created_by','JiraTestgenAI')} on {data.get('generated_timestamp','')} (Template v3)"
    c.append(_paragraph(footer))
    return d
