import streamlit as st
from logging_config import get_logger
# Ensure v3 template forced immediately on import (before any render logic)
if 'force_v3_template' not in st.session_state:
    st.session_state.force_v3_template = True
st.session_state.use_adf_export = True
st.session_state.use_adf_template_v3 = True
st.session_state.use_adf_template_v2 = False
import os
import json
import requests
from requests.auth import HTTPBasicAuth
from PIL import Image
import io
import base64
import re
import logging
import time
import pandas as pd
from html import unescape

logger = get_logger(__name__)
try:
    # ADF builders (v1 legacy, v2, v3) – import explicitly so globals() check isn't brittle
    from adf_templates import (
        build_story_description_adf,
        build_story_description_adf_v2,
        build_story_description_adf_v3,
        validate_adf_size
    )
except Exception as _adf_import_ex:
    build_story_description_adf = None
    build_story_description_adf_v2 = None
    build_story_description_adf_v3 = None
    validate_adf_size = lambda _x: True
    try:
        logger.warning("ADF template import failed: %s", _adf_import_ex)
    except Exception:
        pass
try:
    # Use centralized prompt builder for consistency
    from story_prompt import get_story_generation_prompt
    from story_prompt import validate_story_quality  # quality checklist text
except Exception:
    get_story_generation_prompt = None  # Fallback handled later
    validate_story_quality = lambda _x: ""

# ---------------------------------------------------------------------------
# Quality Analysis Utilities (Optional refinement loop – not auto-applied)
# ---------------------------------------------------------------------------
def _analyze_story_quality(story: dict) -> dict:
    """Heuristically analyze a single generated story and identify missing aspects.

    Returns a dict with keys: issues (list[str]), suggestions (list[str]).
    Non-invasive: does not mutate input.
    """
    issues = []
    suggestions = []
    title = (story.get('title') or '').strip()
    desc = (story.get('description') or '')
    ac = (story.get('acceptance_criteria') or '')
    tech = (story.get('technical_notes') or story.get('technical_notes'.replace('_',''))) or ''

    if not title:
        issues.append("Missing title")
        suggestions.append("Add a concise, action-oriented title describing user outcome.")
    if 'As a' not in desc or 'I want' not in desc:
        issues.append("Description may lack standard user story phrasing (As a / I want / so that)")
        suggestions.append("Rewrite description to follow 'As a <role>, I want <capability> so that <value>'.")
    if not any(kw in ac.lower() for kw in ['given', 'when', 'then']):
        issues.append("Acceptance criteria missing Gherkin structure")
        suggestions.append("Add Given/When/Then structured criteria covering happy path, edge, and error cases.")
    if 'performance' not in ac.lower():
        suggestions.append("Consider adding performance NFR with p95 target if applicable.")
    if 'accessibility' not in ac.lower():
        suggestions.append("Include accessibility NFR (WCAG 2.1 AA, keyboard navigation, screen reader labels).")
    if ('security' not in ac.lower()) and ('penetration' not in ac.lower()):
        suggestions.append("Include security / penetration NFR (RBAC, input validation, no sensitive data exposure).")
    if not tech.strip():
        suggestions.append("Add technical notes (APIs, data model, integration points, constraints).")
    if len(desc.split()) > 300:
        suggestions.append("Description seems long; consider splitting into smaller vertical slice stories.")

    return {"issues": issues, "suggestions": suggestions}

def _format_quality_feedback(story_index: int, analysis: dict) -> str:
    if not analysis['issues'] and not analysis['suggestions']:
        return f"✅ Story {story_index} passes basic heuristic quality checks."
    lines = [f"### 🔍 Quality Review – Story {story_index}"]
    if analysis['issues']:
        lines.append("**Issues:**")
        for i in analysis['issues']:
            lines.append(f"- ❗ {i}")
    if analysis['suggestions']:
        lines.append("**Suggestions:**")
        for s in analysis['suggestions']:
            lines.append(f"- 💡 {s}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Default Project Handling
# ---------------------------------------------------------------------------
# Force the application to use 'CTR' as the default JIRA project unless user
# explicitly changes it. Central helper provided for consistent access.
try:
    if 'default_jira_project' not in st.session_state:
        st.session_state.default_jira_project = 'CTR'
except Exception:
    pass

def get_default_jira_project():
    """Return current default JIRA project (forced to 'CTR' if unset)."""
    try:
        return st.session_state.get('default_jira_project', 'CTR') or 'CTR'
    except Exception:
        return 'CTR'

# ---------------------------------------------------------------------------
# Logging setup (added after refactor where logger references remained)
# ---------------------------------------------------------------------------
try:
    from logging_config import get_logger  # already imported below but safe
    logger = get_logger(__name__)
except Exception:  # fallback basic logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("StoryCreation")

# Import local modules
from jiraUtils import (
    post_story_creation,
    create_feature_link,
    get_available_projects,
    get_user_details
)
# (get_logger already handled above for logger variable)

def search_epics_and_features(project_key: str):
    """Search for Epics and Features with fallback + pagination.

    Uses jiraUtils._jira_search helper that already handles legacy 410 fallback.
    Returns (success, list|error_message)
    """
    try:
        import jiraUtils
        from jiraUtils import _jira_search as _ju_search  # reuse existing search abstraction
    except Exception as imp_ex:
        return False, f"Import error: {imp_ex}"

    jql = f'project = "{project_key}" AND (issuetype = Epic OR issuetype = Feature) ORDER BY updated DESC'
    collected = []
    start_at = 0
    page_size = 50  # multiple pages to reach ~200
    max_total = 200
    try:
        while start_at < max_total:
            ok, status, data = _ju_search(jql, fields=["summary","issuetype"], max_results=page_size, start_at=start_at)
            if not ok:
                # If status 410 or 0, error already handled by helper; break with message
                return False, f"Search failed ({status}): {data}"
            issues = (data or {}).get('issues', [])
            if not issues:
                break
            for issue in issues:
                try:
                    collected.append({
                        'key': issue.get('key',''),
                        'summary': issue.get('fields',{}).get('summary',''),
                        'type': issue.get('fields',{}).get('issuetype',{}).get('name','')
                    })
                except Exception:
                    continue
            if len(issues) < page_size:
                break
            start_at += page_size
            if len(collected) >= max_total:
                break
        return True, collected
    except Exception as e:
        return False, f"Error searching epics/features: {e}"

## Removed: test_openai_connection helper and UI per request

def display_individual_story(story, story_index):
    """Display and edit individual story (story points removed)."""
    st.markdown(f"### 📝 Story {story_index + 1}: {story.get('title', 'Untitled')}")

    jira_project = story.get('jira_project', st.session_state.get('default_jira_project', 'Not Set'))
    feature_epic = story.get('feature_epic', st.session_state.get('default_feature_epic', 'Not Set'))
    st.markdown(
        f"""
        <div style="background-color: #f0f8ff; padding: 10px; border-radius: 5px; margin-bottom: 15px; font-size: 0.9em;">
        <strong>🎯 JIRA Configuration:</strong> Project: <code>{jira_project}</code> | Feature/Epic: <code>{feature_epic}</code>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Title + Priority + Labels (story points removed)
    info_col1, info_col2, info_col3 = st.columns([3, 1, 2])
    with info_col1:
        edited_title = st.text_input(
            "📝 Title:", value=story.get('title', ''), key=f"title_{story_index}", placeholder="Enter story title..."
        )
    with info_col2:
        priority_options = ["Low", "Medium", "High", "Critical"]
        current_priority = story.get('priority', 'Medium')
        try:
            priority_index = priority_options.index(current_priority)
        except ValueError:
            priority_index = 1
        edited_priority = st.selectbox(
            "⚡ Priority:", options=priority_options, index=priority_index, key=f"priority_{story_index}"
        )
    with info_col3:
        import re as _re_lbl

        def _parse_labels_inline(raw_text: str) -> list[str]:
            if not raw_text:
                return []
            parts = _re_lbl.split(r'[\s,]+', raw_text) if hasattr(_re_lbl, 'split') else []
            cleaned = []
            seen_lower = set()
            for p in parts:
                p = (p or '').strip()
                if not p:
                    continue
                safe = _re_lbl.sub(r'[^A-Za-z0-9_-]', '', p)[:255]
                low = safe.lower()
                if safe and low not in seen_lower:
                    seen_lower.add(low)
                    cleaned.append(safe)
            return cleaned

        labels_raw = st.text_input(
            "🏷️ Labels (comma/space)",
            value=','.join(story.get('labels', [])),
            key=f"labels_{story_index}",
            placeholder="marketing, phase1 performance_opt",
            help="Separate multiple labels by commas or spaces. Do not include spaces inside a single label; use hyphen_or_underscore if needed."
        )
        parsed_labels = _parse_labels_inline(labels_raw)
    
    # Epic field - full width
    edited_epic = st.text_input(
        "🎯 Epic (Optional):",
        value=story.get('epic', ''),
        key=f"epic_{story_index}",
        placeholder="e.g., CT-12345"
    )
    # Fallback labels input directly under epic for visibility (mirrors same state)
    with st.expander("Optional: Edit Labels", expanded=False):
        fallback_labels_raw = st.text_input(
            "Labels (duplicate field for convenience)",
            value=labels_raw,
            key=f"labels_fallback_{story_index}",
            help="Same as above. Reminder: individual labels cannot contain spaces; use hyphen_or_underscore."
        )
        if fallback_labels_raw != labels_raw:
            parsed_labels = _parse_labels_inline(fallback_labels_raw)
            labels_raw = fallback_labels_raw
    
    # Compact description editing with tabs for better organization
    desc_tab1, desc_tab2, desc_tab3 = st.tabs(["📄 Description", "✅ Acceptance Criteria", "🔧 Technical Notes"])
    
    with desc_tab1:
        main_description = st.text_area(
            "Story Description:",
            value=story.get('description', ''),
            height=120,
            key=f"description_{story_index}",
            placeholder="Describe the user story requirements...",
            help="Main story description with context and requirements"
        )
        # Debug preview: show exactly what will be sent in the ADF 'User Story' panel
        with st.expander("🔍 Preview: Exact 'User Story' panel content (verbatim)", expanded=False):
            st.markdown("This is the raw text that will appear under the User Story panel in Jira (no synthetic rewriting).")
            st.code(main_description or "(empty)", language="markdown")
    
    with desc_tab2:
        description_text = story.get('description', '')
        acceptance_criteria = extract_acceptance_criteria(description_text)
        
        edited_acceptance_criteria = st.text_area(
            "Acceptance Criteria:",
            value=acceptance_criteria,
            height=180,
            key=f"acceptance_{story_index}",
            placeholder=(
                "- Given [context]\n- When [action]\n- Then [outcome]\n\n"
                "### Non-Functional Requirements (NFRs) — Performance, Accessibility, Security/Penetration\n"
                "- Performance: p95 < 2s page load; API p95 < 500ms\n"
                "- Accessibility: WCAG 2.1 AA; keyboard navigation\n"
                "- Security/Penetration: Input validation; role-based access on endpoints\n"
            ),
            help="Clear, testable criteria. Include a labeled NFR subsection with concrete thresholds."
        )
    
    with desc_tab3:
        technical_notes = extract_technical_notes(description_text)
        
        edited_technical_notes = st.text_area(
            "Technical Implementation Notes:",
            value=technical_notes,
            height=120,
            key=f"technical_{story_index}",
            placeholder="Technical considerations, APIs, dependencies...",
            help="Technical details and implementation guidance"
        )
    
    # Create updated story object with current form values
    updated_story = {
        'title': edited_title,
        'priority': edited_priority,
        'epic': edited_epic,
        'description': main_description,
        'acceptance_criteria': edited_acceptance_criteria,
        'technical_notes': edited_technical_notes,
        'jira_project': story.get('jira_project', st.session_state.get('default_jira_project', 'CT')),
        'feature_epic': story.get('feature_epic', st.session_state.get('default_feature_epic', '')),
        'labels': parsed_labels,
    }
    
    # Compact action buttons
    st.markdown("---")
    action_col1, action_col2, action_col3 = st.columns([1, 1, 2])
    
    with action_col1:
        if st.button(f"💾 Save Changes", key=f"save_{story_index}", type="primary"):
            # Update in session state
            if 'generated_stories' in st.session_state and isinstance(st.session_state.generated_stories, list):
                if story_index < len(st.session_state.generated_stories):
                    st.session_state.generated_stories[story_index] = updated_story
                    st.success(f"✅ Story {story_index + 1} updated successfully!")
                    time.sleep(1)
                    st.rerun()
    
    with action_col2:
        if st.button(f"📤 Export to JIRA", key=f"export_{story_index}"):
            # Direct export using pre-configured settings instead of showing panel
            
            # Check authentication
            if 'accountId' not in st.session_state or 'username' not in st.session_state:
                st.error("⚠️ Please ensure you're logged in to export stories to JIRA.")
            else:
                # Get pre-configured settings from multiple sources
                # Priority: 1. Original story data, 2. Session state defaults, 3. Fallback values
                project_key = (story.get('jira_project') or 
                               st.session_state.get('selected_project_key') or 
                               st.session_state.get('default_jira_project') or 
                               'CTR')
                feature_key = (story.get('feature_epic') or 
                              st.session_state.get('default_feature_epic') or 
                              '')
                
                if not feature_key:
                    st.warning("⚠️ No Feature/Epic configured for this story. Please set it in the JIRA Configuration at the top.")
                else:
                    # Debug information
                    st.info(f"📋 Attempting to create story in project: {project_key}, Feature: {feature_key}")
                    
                    with st.spinner(f"Creating story {story_index + 1} in JIRA..."):
                        account_id = st.session_state.get('accountId')
                        email_id = st.session_state.get('username')
                        try:
                            # Use existing export helper if available
                            post_success, issue_key, msg = export_story_to_jira(
                                story_data=story,
                                project_key=project_key,
                                project_name=project_key,  # If a mapping to name exists, adjust accordingly
                                account_id=account_id,
                                email_id=email_id,
                                epic_key=feature_key,
                                feature_key=feature_key,
                                story_points=0,
                            )
                            if post_success:
                                st.success(f"✅ Created {issue_key} in JIRA")
                                # Persist record for top summary panel
                                st.session_state[f'created_story_{issue_key}'] = {
                                    'story_key': issue_key,
                                    'story_title': story.get('title', 'Untitled'),
                                    'project_key': project_key,
                                    'story_url': f"https://{os.getenv('JIRA_BASE_URL','').replace('https://','')}/browse/{issue_key}" if os.getenv('JIRA_BASE_URL') else None
                                }
                                # Update workflow status if tracking structure exists
                                workflow_key = f"story_{story_index+1}"
                                if 'story_workflow_data' in st.session_state and workflow_key in st.session_state.story_workflow_data:
                                    st.session_state.story_workflow_data[workflow_key]['jira_id'] = issue_key
                                    st.session_state.story_workflow_data[workflow_key]['workflow_status'] = 'Exported'
                                st.rerun()
                            else:
                                st.error(msg or "Failed to create story")
                        except Exception as e:
                            st.error(f"Error exporting: {e}")
    
    with action_col3:
        # Show original content in compact expander
        with st.expander("👁️ View Original Generated Content"):
            st.text_area(
                "Original:",
                value=story.get('description', ''),
                height=80,
                disabled=True,
                key=f"original_{story_index}"
            )

    # Optional quality refinement section (non-destructive)
    with st.expander("🧪 Quality Review / Refinement Aid", expanded=False):
        if st.button(f"Run Quality Checks (Story {story_index + 1})", key=f"qc_run_{story_index}"):
            analysis = _analyze_story_quality(story)
            feedback_md = _format_quality_feedback(story_index + 1, analysis)
            st.markdown(feedback_md)
            # Provide full checklist for manual copy/reference
            qc_text = validate_story_quality("") if callable(validate_story_quality) else ""
            if qc_text:
                with st.expander("Full Quality Checklist", expanded=False):
                    st.code(qc_text.strip(), language="markdown")
        else:
            st.caption("Click the button to analyze this story for structural/completeness gaps. No changes are auto-applied.")

    # Export panel no longer needed - direct export is used instead

def export_single_story_to_jira(story_data, story_number):
    """Export a single story to JIRA with configuration."""
    # Check authentication
    if 'accountId' not in st.session_state or 'username' not in st.session_state:
        st.error("⚠️ Please ensure you're logged in to export stories to JIRA.")
        return
    
    if not st.session_state.get('available_projects'):
        st.error("⚠️ No JIRA projects available. Please check your permissions.")
        return
    
    # Single story export configuration
    with st.expander(f"🚀 Export Story {story_number} to JIRA", expanded=True):
        # Project selection
        ct_projects = [p for p in st.session_state.available_projects if 'CT' in p['key']]
        other_projects = [p for p in st.session_state.available_projects if p not in ct_projects]
        sorted_projects = ct_projects + other_projects
        
        project_options = [f"{p['key']} - {p['name']}" for p in sorted_projects]
        selected_project = st.selectbox(
            "Target JIRA Project:",
            options=project_options,
            help="Project where this story will be created",
            key=f"single_project_{story_number}"
        )
        
        project_key = selected_project.split(' - ')[0]
        project_name = selected_project.split(' - ', 1)[1]
        # Persist selection
        st.session_state.selected_project_key = project_key
        st.session_state.selected_project_name = project_name
        if not st.session_state.get('default_jira_project'):
            st.session_state.default_jira_project = project_key
        
        # Configuration for this story
        col1, col2 = st.columns(2)
        
        with col1:
            epic_key = st.text_input(
                "Epic Key (Optional):",
                value=story_data.get('epic', ''),
                help="Link to existing epic",
                key=f"single_epic_{story_number}"
            )
        
        with col2:
            feature_key = st.text_input(
                "Feature Key (Required):",
                value="CT-184664",
                help="Feature to link this story to (mandatory field)",
                key=f"single_feature_{story_number}",
                placeholder="e.g., CT-184664"
            )
            
            # Validate feature key format
            if feature_key and not re.match(r'^[A-Z]+-\d+$', feature_key):
                st.warning("⚠️ Feature key should be in format like 'CT-184664'")
        
        # Export button - disabled if feature key is empty
        feature_key_valid = feature_key and feature_key.strip() and re.match(r'^[A-Z]+-\d+$', feature_key.strip())
        
        if not feature_key_valid:
            st.warning("🔗 Feature Key is required for JIRA export")
        
        export_disabled = not feature_key_valid
        
        if st.button(
            f"📤 Create Story {story_number} in JIRA",
            type="primary",
            key=f"create_single_{story_number}",
            disabled=export_disabled,
            help="Feature Key is required to export to JIRA",
        ):
            with st.spinner(f"Creating story {story_number} in JIRA..."):
                account_id = st.session_state.get('accountId', 'default_account_id')
                email_id = st.session_state.get('username', 'default@example.com')

                success, story_key, message = export_story_to_jira(
                    story_data=story_data,
                    project_key=project_key,
                    project_name=project_name,
                    account_id=account_id,
                    email_id=email_id,
                    epic_key=epic_key if epic_key.strip() else None,
                    feature_key=feature_key if feature_key.strip() else None,
                    story_points=0,
                )

            if success:
                jira_base_url = os.getenv("JIRA_BASE_URL", "https://mandg.atlassian.net")
                story_url = f"{jira_base_url.rstrip('/')}/browse/{story_key}"

                # Store the created story key in session state for test case creation
                session_key = f"created_story_{story_number}"
                st.session_state[session_key] = {
                    'story_key': story_key,
                    'jira_key': story_key,
                    'story_title': story_data['title'],
                    'project_key': project_key,
                    'story_url': story_url,
                }

                # Update workflow tracking data
                workflow_key = f"story_{story_number}"
                if 'story_workflow_data' not in st.session_state:
                    st.session_state.story_workflow_data = {}
                if workflow_key not in st.session_state.story_workflow_data:
                    st.session_state.story_workflow_data[workflow_key] = {}

                st.session_state.story_workflow_data[workflow_key].update({
                    'jira_id': story_key,
                    'workflow_status': 'Story Created',
                    'jira_url': story_url,
                    'project_key': project_key,
                })

                # Update workflow table cache
                update_workflow_cache()

                st.success("✅ Story created successfully!")
                st.info(f"**JIRA Story:** {story_key}")
                st.markdown(f"**[View Story in JIRA]({story_url})**")

                # Action buttons with better styling
                st.markdown("---")
                test_col, close_col = st.columns(2)
                with test_col:
                    if st.button(
                        "🧪 Create Test Cases",
                        key=f"create_tests_{story_number}",
                        type="secondary",
                        use_container_width=True,
                        help=f"Generate test cases for story {story_key}",
                    ):
                        # Navigate to test case creation with pre-filled story key
                        st.session_state.target_story_key = story_key
                        st.session_state.navigate_to_tests = True
                        st.session_state.auto_fill_story = True
                        st.session_state.auto_run_tests = True
                        # Also pass through query params for sidebar router
                        st.query_params.navigate_to_tests = 'true'
                        st.query_params.story_identifier = story_key
                        st.rerun()

                with close_col:
                    if st.button(
                        "✅ Close Panel",
                        key=f"close_panel_{story_number}",
                        type="primary",
                        use_container_width=True,
                        help="Close the export panel",
                    ):
                        # Close the export panel
                        st.session_state[f"export_panel_active_{story_number-1}"] = False
                        st.rerun()
            else:
                st.error(f"❌ Failed to create story: {message}")

def render_export_panel(story_data, story_number):
    """Render persistent export panel with wider layout and cancel option."""
    # Check authentication
    if 'accountId' not in st.session_state or 'username' not in st.session_state:
        st.error("⚠️ Please ensure you're logged in to export stories to JIRA.")
        return
    
    if not st.session_state.get('available_projects'):
        st.error("⚠️ No JIRA projects available. Please check your permissions.")
        return
    
    # Use a container with custom styling for wider layout
    st.markdown("---")
    st.markdown(f"### 🚀 Export Story {story_number} to JIRA")
    
    # Create a wider container
    with st.container():
        # Project selection with wider column
        project_col, button_col = st.columns([4, 1])
        
        with project_col:
            ct_projects = [p for p in st.session_state.available_projects if 'CT' in p['key']]
            other_projects = [p for p in st.session_state.available_projects if p not in ct_projects]
            sorted_projects = ct_projects + other_projects
            
            project_options = [f"{p['key']} - {p['name']}" for p in sorted_projects]
            
            # Pre-select project based on story configuration
            story_project = story_data.get('jira_project', 'CT')
            default_index = 0
            for i, option in enumerate(project_options):
                if option.startswith(story_project):
                    default_index = i
                    break
            
            selected_project = st.selectbox(
                "Target JIRA Project:",
                options=project_options,
                index=default_index,
                help=f"Project where this story will be created (pre-configured: {story_project})",
                key=f"panel_project_{story_number}"
            )
            
            project_key = selected_project.split(' - ')[0]
            project_name = selected_project.split(' - ', 1)[1]
            st.session_state.selected_project_key = project_key
            st.session_state.selected_project_name = project_name
            if not st.session_state.get('default_jira_project'):
                st.session_state.default_jira_project = project_key
        
        # Configuration fields (now 3 columns: epic, feature, labels)
        config_col1, config_col2, config_col3 = st.columns(3)
        
        with config_col1:
            epic_key = st.text_input(
                "Epic Key (Optional):",
                value=story_data.get('epic', ''),
                help="Link to existing epic",
                key=f"panel_epic_{story_number}"
            )
        
        with config_col2:
            # Use pre-configured feature/epic value
            default_feature = story_data.get('feature_epic', 'CT-184664')
            feature_key = st.text_input(
                "Feature Key (Required):",
                value=default_feature,
                help=f"Feature to link this story to (pre-configured: {default_feature})",
                key=f"panel_feature_{story_number}",
                placeholder="e.g., CT-184664"
            )
            
            # Validate feature key format
            if feature_key and not re.match(r'^[A-Z]+-\d+$', feature_key):
                st.warning("⚠️ Feature key should be in format like 'CT-184664'")

        with config_col3:
            raw_labels_input = st.text_input(
                "Additional Labels",
                value=st.session_state.get('custom_labels_raw', ''),
                key=f"panel_labels_{story_number}",
                help="Optional comma/space separated labels to add besides 'JiraStoryGenAI'"
            )
            import re as _re_lbl2
            parsed_labels = []
            for token in _re_lbl2.split(r'[\s,]+'):
                token = token.strip()
                if not token:
                    continue
                safe = _re_lbl2.sub(r'[^A-Za-z0-9_-]', '', token)[:255]
                if safe and safe.lower() not in [p.lower() for p in parsed_labels]:
                    parsed_labels.append(safe)
            st.session_state.custom_labels = parsed_labels
            st.session_state.custom_labels_raw = raw_labels_input
            if parsed_labels:
                st.caption(f"Labels: {', '.join(parsed_labels)}")
            else:
                st.caption("No additional labels")
        
        # Action buttons in a row
        st.markdown("---")
        action_col1, action_col2, action_col3, action_col4 = st.columns([2, 2, 2, 2])
        
        # Validate feature key
        feature_key_valid = feature_key and feature_key.strip() and re.match(r'^[A-Z]+-\d+$', feature_key.strip())
        
        if not feature_key_valid:
            st.warning("🔗 Feature Key is required for JIRA export")
        
        export_disabled = not feature_key_valid
        
        with action_col1:
            if st.button(f"📤 Create Story in JIRA", 
                        type="primary", 
                        key=f"panel_create_{story_number}",
                        disabled=export_disabled,
                        help="Feature Key is required to export to JIRA"):
                with st.spinner(f"Creating story {story_number} in JIRA..."):
                    account_id = st.session_state.get('accountId', 'default_account_id')
                    email_id = st.session_state.get('username', 'default@example.com')
                    
                    success, story_key, message = export_story_to_jira(
                        story_data=story_data,
                        project_key=project_key,
                        project_name=project_name,
                        account_id=account_id,
                        email_id=email_id,
                        epic_key=epic_key if epic_key.strip() else None,
                        feature_key=feature_key if feature_key.strip() else None,
                        story_points=0
                    )
                    
                    if success:
                        jira_base_url = os.getenv("JIRA_BASE_URL", "https://mandg.atlassian.net")
                        story_url = f"{jira_base_url.rstrip('/')}/browse/{story_key}"
                        
                        # Store the created story key in session state for test case creation
                        session_key = f"created_story_{story_number}"
                        st.session_state[session_key] = {
                            'story_key': story_key,
                            'jira_key': story_key,
                            'story_title': story_data['title'],
                            'project_key': project_key,
                            'story_url': story_url
                        }
                        
                        # Update workflow tracking data
                        workflow_key = f"story_{story_number}"
                        if 'story_workflow_data' not in st.session_state:
                            st.session_state.story_workflow_data = {}
                        if workflow_key not in st.session_state.story_workflow_data:
                            st.session_state.story_workflow_data[workflow_key] = {}
                        
                        st.session_state.story_workflow_data[workflow_key].update({
                            'jira_id': story_key,
                            'workflow_status': 'Story Created',
                            'jira_url': story_url,
                            'project_key': project_key
                        })
                        
                        # Force workflow table refresh for real-time updates
                        if 'workflow_table_cache' in st.session_state:
                            del st.session_state.workflow_table_cache
                        update_workflow_cache()
                        
                        st.success(f"✅ Story created successfully!")
                        st.info(f"**JIRA Story:** {story_key}")
                        st.markdown(f"**[View Story in JIRA]({story_url})**")
                        
                        # Immediate refresh to update the table with JIRA ID
                        st.rerun()
                        
                        # Action buttons with professional styling
                        st.markdown("---")
                        test_col, close_col = st.columns(2)
                        with test_col:
                            if st.button(
                                "🧪 Create Test Cases",
                                key=f"panel_create_tests_{story_number}",
                                type="secondary",
                                use_container_width=True,
                                help=f"Generate test cases for story {story_key}",
                            ):
                                # Navigate to test case creation with pre-filled story key
                                st.session_state.target_story_key = story_key
                                st.session_state.navigate_to_tests = True
                                st.session_state.auto_fill_story = True
                                st.session_state.auto_run_tests = True
                                st.query_params.navigate_to_tests = 'true'
                                st.query_params.story_identifier = story_key
                                st.rerun()

                        with close_col:
                            if st.button("✅ Close Panel", 
                                       key=f"close_export_panel_{story_number}",
                                       type="primary",
                                       use_container_width=True,
                                       help="Close the export panel"):
                                # Close the export panel
                                st.session_state[f"export_panel_active_{story_number-1}"] = False
                                st.rerun()
                    else:
                        st.error(f"❌ Failed to create story: {message}")
        
        with action_col2:
            if st.button("❌ Cancel", 
                        key=f"panel_cancel_{story_number}",
                        help="Close the export panel"):
                # Close the export panel
                st.session_state[f"export_panel_active_{story_number-1}"] = False
                st.rerun()

def extract_acceptance_criteria(description):
    """Extract acceptance criteria from description text."""
    if not description:
        return ""
    
    # Look for acceptance criteria patterns
    patterns = [
        r"(?i)acceptance criteria[:\s]*\n(.*?)(?=\n\n|\ntechnical|\nImplementation|\Z)",
        r"(?i)given.*when.*then.*",
        r"(?i)criteria[:\s]*\n(.*?)(?=\n\n|\ntechnical|\nImplementation|\Z)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description, re.DOTALL)
        if match:
            return match.group(1).strip() if match.groups() else match.group().strip()
    
    return ""

def extract_technical_notes(description):
    """Extract technical notes from description text."""
    if not description:
        return ""
    
    # Look for technical patterns
    patterns = [
        r"(?i)technical.*?notes?[:\s]*\n(.*?)(?=\n\n|\Z)",
        r"(?i)implementation[:\s]*\n(.*?)(?=\n\n|\Z)",
        r"(?i)technical considerations[:\s]*\n(.*?)(?=\n\n|\Z)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description, re.DOTALL)
        if match:
            return match.group(1).strip() if match.groups() else match.group().strip()
    
    return ""

def export_single_story_to_jira(story, story_number):
    """Export a single story to JIRA."""
    # Check authentication
    if 'accountId' not in st.session_state or 'username' not in st.session_state:
        st.warning("⚠️ Please ensure you're logged in to export stories to JIRA.")
        return
    
    if not st.session_state.get('available_projects'):
        st.warning("⚠️ No JIRA projects available. Please check your permissions.")
        return
    
    # Project selection in expander
    with st.expander(f"JIRA Configuration for Story {story_number}", expanded=True):
        # Project selection
        ct_projects = [p for p in st.session_state.available_projects if 'CT' in p['key']]
        other_projects = [p for p in st.session_state.available_projects if p not in ct_projects]
        sorted_projects = ct_projects + other_projects
        
        project_options = [f"{p['key']} - {p['name']}" for p in sorted_projects]
        selected_project = st.selectbox(
            "Select JIRA Project:",
            options=project_options,
            key=f"project_select_{story_number}"
        )
        
        project_key = selected_project.split(' - ')[0]
        project_name = selected_project.split(' - ', 1)[1]
        
        # Additional fields
        col1, col2 = st.columns(2)
        
        with col1:
            epic_key = st.text_input(
                "Epic Key (Optional):",
                value=story.get('epic', ''),
                key=f"epic_key_{story_number}"
            )
        
        with col2:
            feature_key = st.text_input(
                "Feature Key:",
                value="CT-184664",
                key=f"feature_key_{story_number}"
            )
        
        if st.button(f"Create Story {story_number}", key=f"create_{story_number}"):
            with st.spinner(f"Creating story {story_number} in JIRA..."):
                # Get current user details
                account_id = st.session_state.get('accountId', 'default_account_id')
                email_id = st.session_state.get('username', 'default@example.com')
                
                # Export to JIRA
                success, story_key, message = export_story_to_jira(
                    story_data=story,
                    project_key=project_key,
                    project_name=project_name,
                    account_id=account_id,
                    email_id=email_id,
                    epic_key=epic_key if epic_key.strip() else None,
                    feature_key=feature_key if feature_key.strip() else None,
                    story_points=0
                )
                
                if success:
                    st.success(f"✅ Story {story_number} created: {story_key}")
                    jira_base_url = os.getenv("JIRA_BASE_URL", "https://mandg.atlassian.net")
                    story_url = f"{jira_base_url.rstrip('/')}/browse/{story_key}"
                    st.markdown(f"🔗 [View Story in JIRA]({story_url})")
                else:
                    st.error(f"❌ Failed to create story {story_number}: {message}")

def render_view_export_panel(story_data, story_number):
    """Render persistent export panel for story viewing mode with wider layout and cancel option."""
    # Check authentication
    if 'accountId' not in st.session_state or 'username' not in st.session_state:
        st.error("⚠️ Please ensure you're logged in to export stories to JIRA.")
        return
    
    if not st.session_state.get('available_projects'):
        st.error("⚠️ No JIRA projects available. Please check your permissions.")
        return
    
    # Use a container with custom styling for wider layout
    st.markdown("---")
    st.markdown(f"### 🚀 Export Story {story_number} to JIRA")
    
    # Create a wider container
    with st.container():
        # Project selection with wider column
        project_col, button_col = st.columns([4, 1])
        
        with project_col:
            ct_projects = [p for p in st.session_state.available_projects if 'CT' in p['key']]
            other_projects = [p for p in st.session_state.available_projects if p not in ct_projects]
            sorted_projects = ct_projects + other_projects
            
            project_options = [f"{p['key']} - {p['name']}" for p in sorted_projects]
            selected_project = st.selectbox(
                "Target JIRA Project:",
                options=project_options,
                help="Project where this story will be created",
                key=f"view_panel_project_{story_number}"
            )
            
            project_key = selected_project.split(' - ')[0]
            project_name = selected_project.split(' - ', 1)[1]
            st.session_state.selected_project_key = project_key
            st.session_state.selected_project_name = project_name
            if not st.session_state.get('default_jira_project'):
                st.session_state.default_jira_project = project_key
        
        # Configuration fields in two columns for better width usage
        config_col1, config_col2 = st.columns(2)
        
        with config_col1:
            epic_key = st.text_input(
                "Epic Key (Optional):",
                value=story_data.get('epic', ''),
                help="Link to existing epic",
                key=f"view_panel_epic_{story_number}"
            )
        
        with config_col2:
            feature_key = st.text_input(
                "Feature Key (Required):",
                value="CT-184664",
                help="Feature to link this story to (mandatory field)",
                key=f"view_panel_feature_{story_number}",
                placeholder="e.g., CT-184664"
            )
        with config_col3:
            raw_labels_input = st.text_input(
                "Additional Labels (comma / space separated)",
                value=st.session_state.get('custom_labels_raw', ''),
                key=f"view_panel_labels_{story_number}",
                help="Optional labels to add to the Jira issue besides the default 'JiraStoryGenAI'. Use commas or spaces."
            )
            # Parse & sanitize immediately (letters, numbers, hyphen, underscore)
            import re as _re_lbl
            parsed = []
            for token in _re_lbl.split(raw_labels_input):
                for part in _re_lbl.split(r'[ ,]+', token):
                    label = part.strip()
                    if not label:
                        continue
                    safe = _re_lbl.sub(r'[^A-Za-z0-9_-]', '', label)[:255]
                    if safe and safe.lower() not in [p.lower() for p in parsed]:
                        parsed.append(safe)
            st.session_state.custom_labels = parsed
            st.session_state.custom_labels_raw = raw_labels_input
            if parsed:
                st.caption(f"Labels to apply: {', '.join(parsed)}")
            else:
                st.caption("No additional labels will be applied.")
            
            # Validate feature key format
            if feature_key and not re.match(r'^[A-Z]+-\d+$', feature_key):
                st.warning("⚠️ Feature key should be in format like 'CT-184664'")
        
        # Action buttons in a row
        st.markdown("---")
        action_col1, action_col2, action_col3, action_col4 = st.columns([2, 2, 2, 2])
        
        # Validate feature key
        feature_key_valid = feature_key and feature_key.strip() and re.match(r'^[A-Z]+-\d+$', feature_key.strip())
        
        if not feature_key_valid:
            st.warning("🔗 Feature Key is required for JIRA export")
        
        export_disabled = not feature_key_valid
        
        with action_col1:
            if st.button(f"📤 Create Story in JIRA", 
                        type="primary", 
                        key=f"view_panel_create_{story_number}",
                        disabled=export_disabled,
                        help="Feature Key is required to export to JIRA"):
                with st.spinner(f"Creating story {story_number} in JIRA..."):
                    account_id = st.session_state.get('accountId', 'default_account_id')
                    email_id = st.session_state.get('username', 'default@example.com')
                    
                    success, story_key, message = export_story_to_jira(
                        story_data=story_data,
                        project_key=project_key,
                        project_name=project_name,
                        account_id=account_id,
                        email_id=email_id,
                        epic_key=epic_key if epic_key.strip() else None,
                        feature_key=feature_key if feature_key.strip() else None,
                        story_points=0
                    )
                    
                    if success:
                        jira_base_url = os.getenv("JIRA_BASE_URL", "https://mandg.atlassian.net")
                        story_url = f"{jira_base_url.rstrip('/')}/browse/{story_key}"
                        
                        # Store the created story key in session state for test case creation
                        session_key = f"view_created_story_{story_number}"
                        st.session_state[session_key] = {
                            'story_key': story_key,
                            'jira_key': story_key,
                            'story_title': story_data['title'],
                            'project_key': project_key,
                            'story_url': story_url
                        }
                        
                        # Also store in the regular created_story session for consistency
                        regular_session_key = f"created_story_{story_number}"
                        st.session_state[regular_session_key] = {
                            'story_key': story_key,
                            'jira_key': story_key,
                            'story_title': story_data['title'],
                            'project_key': project_key,
                            'story_url': story_url
                        }
                        
                        # Update workflow tracking data
                        workflow_key = f"story_{story_number}"
                        if 'story_workflow_data' not in st.session_state:
                            st.session_state.story_workflow_data = {}
                        if workflow_key not in st.session_state.story_workflow_data:
                            st.session_state.story_workflow_data[workflow_key] = {}
                        
                        st.session_state.story_workflow_data[workflow_key].update({
                            'jira_id': story_key,
                            'workflow_status': 'Story Created',
                            'jira_url': story_url,
                            'project_key': project_key
                        })
                        
                        # Update workflow table cache
                        update_workflow_cache()
                        
                        st.success(f"✅ Story created successfully!")
                        st.info(f"**JIRA Story:** {story_key}")
                        st.markdown(f"**[View Story in JIRA]({story_url})**")
                        
                        # Professional action buttons
                        st.markdown("---")
                        test_col, close_col = st.columns(2)
                        with test_col:
                            if st.button(
                                "🧪 Create Test Cases",
                                key=f"view_panel_create_tests_{story_number}",
                                type="secondary",
                                use_container_width=True,
                                help=f"Generate test cases for story {story_key}",
                            ):
                                # Navigate to test case creation with pre-filled story key
                                st.session_state.target_story_key = story_key
                                st.session_state.navigate_to_tests = True
                                st.session_state.auto_fill_story = True
                                st.session_state.auto_run_tests = True
                                st.query_params.navigate_to_tests = 'true'
                                st.query_params.story_identifier = story_key
                                st.rerun()

                        with close_col:
                            if st.button("✅ Close Panel", 
                                       key=f"view_panel_close_{story_number}",
                                       type="primary",
                                       use_container_width=True,
                                       help="Close the export panel"):
                                # Close the export panel
                                st.session_state[f"view_export_panel_active_{story_number-1}"] = False
                                st.rerun()
                    else:
                        st.error(f"❌ Failed to create story: {message}")
        
        with action_col2:
            if st.button("❌ Cancel", 
                        key=f"view_panel_cancel_{story_number}",
                        help="Close the export panel"):
                # Close the export panel
                st.session_state[f"view_export_panel_active_{story_number-1}"] = False
                st.rerun()

def export_all_stories_to_jira(stories):
    """Deprecated: Bulk export has been removed from the UI."""
    st.info("Bulk export has been deprecated. Please export stories individually.")

def copy_all_stories_as_text(stories):
    """Generate formatted text for all stories."""
    all_stories_text = f"# Generated User Stories ({len(stories)} stories)\n\n"
    
    for i, story in enumerate(stories, 1):
        story_text = f"""## Story {i}: {story.get('title', 'Untitled')}

**Priority:** {story.get('priority', 'Medium')}
**Epic:** {story.get('epic', 'Not specified')}

**Description:**
{story.get('description', 'No description available')}

---

"""
        all_stories_text += story_text
    
    # Add summary at the end
    high_priority = len([s for s in stories if s.get('priority', '').lower() == 'high'])
    
    all_stories_text += f"""## Summary
- **Total Stories:** {len(stories)}
- **High Priority Stories:** {high_priority}
- **Generated on:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    st.markdown("### <span class='badge'>TEXT</span> All Stories", unsafe_allow_html=True)
    st.code(all_stories_text, language="markdown")
    st.success("✅ All stories formatted! Copy the text above to use elsewhere.")
    
    # Option to download as file
    st.download_button(
        label="💾 Download as Markdown File",
        data=all_stories_text,
        file_name=f"user_stories_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.md",
        mime="text/markdown",
        help="Download all stories as a markdown file"
    )

def _legacy_build_story_prompt(use_case_text: str, uploaded_images=None) -> str:
    """(Legacy fallback) Basic vertical slice prompt if central prompt module unavailable."""
    base = (
        "Generate SMALL, INDEPENDENT, DEPLOYABLE user stories (no Story Points).\n" \
        "Use acceptance criteria with Given/When/Then plus NFR subsection (Performance/Accessibility/Security).\n" \
        f"USE CASE:\n{use_case_text}\n"
    )
    if uploaded_images:
        base += f"Images attached: {len(uploaded_images)} (consider only materially relevant visual details).\n"
    return base


def generate_story_with_gencore(use_case_text, uploaded_images=None):
    """Generate stories (small vertical slices) using GenCore API with redundancy (TST1 -> dev1 -> Mock)."""

    # Prefer GPT-5 first, then fall back to GPT‑4o (TST1/dev/prod as available)
    endpoints = [
        
        {
            "name": "TST1",
            "url": "https://api-tst1.mandg.co.uk/enterprise/azureopenai/openai/deployments/gpt-4o/chat/completions",
            "api_key": os.getenv("INT_DASHBOARD_GENCORE_KEY_TST")
        },
        {
            "name": "dev1",  # label only per user preference
            "url": "https://api-dev1.mandg.co.uk/enterprise/azureopenai/openai/deployments/gpt-4o/chat/completions",
            "api_key": os.getenv("INT_DASHBOARD_GENCORE_KEY_DEV1")
        },
    ]

    api_version = "2024-10-21"

    # Build refined decomposition prompt via centralized prompt builder when available
    if get_story_generation_prompt:
        # Include user feedback if regenerating
        user_feedback = st.session_state.get('story_generation_feedback', None)
        # CRITICAL FIX: Pass slider parameters from session state to prompt builder
        prompt = get_story_generation_prompt(
            use_case_text,
            has_image=bool(uploaded_images),
            image_description=None,
            image_type=None,
            desired_story_count=st.session_state.get('desired_story_count'),
            target_ac_per_story=st.session_state.get('target_ac_per_story'),
            maximize_mode=st.session_state.get('maximize_mode', False),
            include_nfr_story=st.session_state.get('include_nfr_story', False),
            user_feedback=user_feedback
        )
    else:
        prompt = _legacy_build_story_prompt(use_case_text, uploaded_images)

    if uploaded_images:
        prompt += (
            f"\n\nAdditional Context from {len(uploaded_images)} uploaded image(s):"
            "\nThe uploaded images may include wireframes, flowcharts, UI mockups, or process diagrams."
            "\nIncorporate visual elements, workflows, and user interface considerations reflected in the images."
        )

    # Build multimodal payload: text + inline images (if any)
    user_content = None
    if uploaded_images:
        # Use Azure OpenAI multimodal format: a list of content parts
        content_parts = [{"type": "text", "text": prompt}]
        for img in uploaded_images:
            try:
                b64 = img.get("data")
                if b64:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}
                    })
            except Exception:
                # Best-effort; skip malformed image entries
                pass
        user_content = content_parts
        try:
            st.session_state["storygen_image_count"] = len(uploaded_images)
        except Exception:
            pass
    else:
        user_content = prompt

    payload = {
        "model": "CHAT_COMPLETION_MODEL",
        "messages": [
            {"role": "user", "content": user_content},
        ],
    }

    last_error_detail = None

    # Iterate endpoints in order; return immediately on success
    for idx, ep in enumerate(endpoints):
        name = ep["name"]
        api_key = ep.get("api_key")
        if not api_key:
            logger.warning("[StoryGen] Skipping %s (no API key)", name)
            continue
        url = f"{ep['url']}?api-version={api_version}"
        headers = {
            "x-Gencore-Correlation-ID": f"StoryGen{int(time.time())}",
            "api-key": api_key,
            "Content-Type": "application/json",
        }
        logger.info("[StoryGen] Trying endpoint %s", name)
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=40, verify=False)
        except requests.exceptions.Timeout as te:
            last_error_detail = f"Timeout contacting {name}: {te}"
            logger.error(last_error_detail)
            continue
        except requests.exceptions.ConnectionError as ce:
            last_error_detail = f"Connection error contacting {name}: {ce}"
            logger.error(last_error_detail)
            continue
        except Exception as e:
            last_error_detail = f"Unexpected exception contacting {name}: {e}"
            logger.error(last_error_detail)
            continue

        if resp.status_code != 200:
            category = (
                "AUTHENTICATION" if resp.status_code in (401, 403)
                else "SERVER" if resp.status_code in (500, 502, 503, 504)
                else "UNEXPECTED"
            )
            snippet = (resp.text or "")[:280]
            last_error_detail = f"{category} failure via {name} - status {resp.status_code} - {snippet}"
            logger.error("[StoryGen] %s", last_error_detail)
            continue

        try:
            data = resp.json()
        except Exception as je:
            last_error_detail = f"Invalid JSON from {name}: {je}"
            logger.error(last_error_detail)
            continue

        content = ""
        try:
            if data.get("choices"):
                content = data["choices"][0].get("message", {}).get("content", "")
        except Exception:
            content = ""

        if content:
            # Scrub any Story Points lines prior to returning
            try:
                import re as _re_scrub
                content = "\n".join([
                    ln for ln in content.splitlines()
                    if not _re_scrub.search(r"^\s*(\*\*|__)?Story\s+Points?(\*\*|__)?\s*:", ln, _re_scrub.IGNORECASE)
                ])
            except Exception:
                pass
            try:
                st.session_state["storygen_endpoint_used"] = name
                st.session_state.pop("storygen_last_error", None)
                st.session_state["storygen_mock"] = False
            except Exception:
                pass
            logger.info("[StoryGen] Success via %s (len=%d)", name, len(content))
            return True, content
        else:
            last_error_detail = f"No content returned from {name} despite 200 response"
            logger.error("[StoryGen] %s", last_error_detail)
            continue

    # All endpoints failed -> set diagnostics and return mock
    try:
        st.session_state["storygen_last_error"] = last_error_detail or "Unknown failure contacting all endpoints"
        st.session_state["storygen_mock"] = True
    except Exception:
        pass

    logger.warning("[StoryGen] All endpoints failed – using MOCK response")

    mock_response = """🚨 **MOCK RESPONSE - ALL ENDPOINTS UNAVAILABLE** 🚨\nThis is a mock response because all API endpoints (TST1 and dev1) are currently unavailable.\nThe application would normally generate actual stories here.\n\n## Story 1: User Authentication System\n**Title:** User Authentication System\n**Priority:** High\n**Description:** As a user, I want to securely log into the system using my credentials so that I can access my personalized dashboard and protected resources.\n\n**Acceptance Criteria:**\n- Given a registered user with valid credentials\n- When the user submits their username and password\n- Then the system authenticates the user and grants access to the dashboard\n- And the session remains active for a specified duration\n- And invalid credentials display appropriate error messages\n\n**Non-Functional Requirements (NFRs) — Performance, Accessibility, Security/Penetration:**\n- Performance: p95 login request completes in < 500ms; rate limiting blocks > 5 attempts/min/IP; CPU < 70% under 200 RPM\n- Accessibility: Meets WCAG 2.1 AA; all auth inputs have labels; full keyboard navigation including submit\n- Security/Penetration: Passwords hashed (bcrypt); no sensitive info in error messages; CSRF protection on forms\n\n**Technical Implementation Notes:**\n- Implement secure password hashing (bcrypt/scrypt)\n- Add multi-factor authentication support\n- Include session management with JWT tokens\n- Add rate limiting for login attempts\n- Implement account lockout after failed attempts\n\n## Story 2: User Dashboard\n**Title:** Personalized User Dashboard\n**Priority:** Medium\n**Description:** As an authenticated user, I want to view a personalized dashboard that shows relevant information and quick actions so that I can efficiently navigate the system.\n\n**Acceptance Criteria:**\n- Given an authenticated user\n- When they access the dashboard\n- Then they see personalized widgets and recent activity\n- And they can customize the layout and content\n\n**Non-Functional Requirements (NFRs) — Performance, Accessibility, Security/Penetration:**\n- Performance: p95 initial render < 2s on average hardware; data refresh p95 < 1s; LCP < 2.5s\n- Accessibility: WCAG 2.1 AA; color contrast >= 4.5:1; focus indicators for interactive elements\n- Security/Penetration: Only authorized widgets accessible; no secrets in client; role-based access enforced\n\n**Technical Implementation Notes:**\n- Create responsive dashboard layout\n- Implement drag-and-drop widget customization\n- Add real-time data updates\n- Optimize database queries for performance\n- Include accessibility features (WCAG compliance)\n\n---\n⚠️ **Note:** This is a mock response. In production, stories would be generated by the AI API based on your specific use case."""

    # Remove any Story Points lines from mock (to align with UI requirement to hide estimation)
    import re as _re_sp
    mock_response = "\n".join([
        ln for ln in mock_response.splitlines()
        if not _re_sp.search(r"^\s*(\*\*|__)?Story\s+Points?(\*\*|__)?\s*:\s*", ln, _re_sp.IGNORECASE)
    ])

    return True, mock_response

# ---------------------------------------------------------------------------
# Confluence Integration (Context Injection for Story Generation)
# ---------------------------------------------------------------------------
def _derive_confluence_base():
    """Derive the Confluence base URL from JIRA_BASE_URL if a dedicated one isn't set.
    If JIRA_BASE_URL ends with /, trim. Append /wiki if not present.
    """
    jira_base = os.getenv("JIRA_BASE_URL", "").rstrip('/')
    if not jira_base:
        return None
    # If already contains '/wiki', assume it's correct
    if jira_base.endswith('/wiki'):
        return jira_base
    return jira_base + '/wiki'

def fetch_confluence_page_content(page_url: str):
    """Fetch Confluence page content (storage format) and return plain text.

    Strategy:
      1. Parse page ID from the provided URL.
      2. Derive candidate base URLs in priority order:
         - Explicit /wiki root from the pasted URL (segment up to /wiki)
         - Root without /wiki (some tenants expose Confluence w/o /wiki)
         - Derived from JIRA_BASE_URL + /wiki (fallback)
      3. Attempt each candidate until a 200 is obtained.

    Returns: (success: bool, title, text, error)
    """
    if not page_url or not page_url.strip():
        return False, None, None, "Empty URL"

    page_url = page_url.strip()
    try:
        import jiraUtils as _ju
        auth_key = _ju.jira_authkey()
    except Exception:
        return False, None, None, "Cannot construct JIRA/Confluence auth key (ensure JIRA creds loaded)"

    import re
    # Page ID extraction patterns
    page_id = None
    for pat in [r"/pages/(\d+)", r"/(\d{6,})($|/)"]:
        m = re.search(pat, page_url)
        if m:
            page_id = m.group(1)
            break
    if not page_id:
        return False, None, None, "Could not parse page ID from URL"

    candidates = []
    # If /wiki present, capture base up to /wiki
    if '/wiki/' in page_url:
        candidates.append(page_url.split('/wiki/')[0].rstrip('/') + '/wiki')
    # Root domain (strip path after host)
    try:
        from urllib.parse import urlparse
        parsed = urlparse(page_url)
        root = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
        if root:
            candidates.append(root.rstrip('/'))
    except Exception:
        pass
    # Fallback to derived from JIRA base
    derived = _derive_confluence_base()
    if derived:
        candidates.append(derived)
    # De-duplicate preserving order
    seen = set()
    ordered_candidates = []
    for c in candidates:
        if c not in seen:
            ordered_candidates.append(c)
            seen.add(c)

    headers = {
        'Authorization': 'Basic ' + auth_key,
        'Accept': 'application/json'
    }
    last_error = None
    for base in ordered_candidates:
        api_url = f"{base}/rest/api/content/{page_id}?expand=body.storage,version,title"
        try:
            resp = requests.get(api_url, headers=headers, timeout=20, verify=False)
        except Exception as e:
            last_error = f"Request error via {base}: {e}"
            continue
        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception as je:
                last_error = f"Invalid JSON via {base}: {je}"
                continue
            title = data.get('title') or ''
            storage_html = data.get('body', {}).get('storage', {}).get('value', '')
            if not storage_html:
                last_error = f"Empty storage content via {base}"
                continue
            # Strip HTML
            text = re.sub(r'<script.*?</script>', ' ', storage_html, flags=re.I|re.S)
            text = re.sub(r'<style.*?</style>', ' ', text, flags=re.I|re.S)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = unescape(text)
            text = re.sub(r'\s+', ' ', text).strip()
            MAX_LEN = 6000
            if len(text) > MAX_LEN:
                text = text[:MAX_LEN] + '…'
            return True, title, text, None
        else:
            # 404 could mean wrong base variant; record error
            snippet = resp.text[:160].replace('\n', ' ')
            last_error = f"HTTP {resp.status_code} via {base}: {snippet}"
            continue
    return False, None, None, last_error or "All attempts failed"


def parse_multiple_stories(raw_text: str):
    """Parse raw model output into a list of story dictionaries with robust heading detection.

    Handles variants produced by LLMs where multiple stories are concatenated:
      - '## Story 1: Title'
      - '### Story 2 Title'
      - '### User Story 3: Title'
      - 'Story 4: Title' (no markdown hashes)
      - 'User Story 5 - Title'

    If a preamble appears before the first detected story heading it becomes Story 1
    (unless the first heading already numbers Story 1). Acceptance Criteria and
    Technical Notes extraction reuses existing helper functions. Any NFR duplication
    inside acceptance criteria is normalized by ensure_nfr_subsection_in_ac.
    """
    if not raw_text:
        return []

    text = raw_text.strip()

    # Unified regex: optional markdown hashes, optional 'User', required 'Story', number, optional separator, optional title
    header_pattern = re.compile(
        r"^(?P<hashes>#{1,6}\s*)?(?P<prefix>User\s+)?Story\s+(?P<num>\d+)\s*[:\-–]?\s*(?P<title>[^\n#]*)$",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = list(header_pattern.finditer(text))

    if not matches:
        # No story headers detected -> treat the entire block as a single story
        return [{
            'title': 'User Story',
            'description': text,
            'acceptance_criteria': extract_acceptance_criteria(text),
            'technical_notes': extract_technical_notes(text),
            'priority': 'Medium',
            'epic': ''
        }]

    stories = []

    # If there is leading content before first heading and the first heading number > 1, treat that as Story 1.
    first_match = matches[0]
    leading_block = text[:first_match.start()].strip()
    first_num = int(first_match.group('num'))
    if leading_block:
        inferred_title = leading_block.split('\n', 1)[0].strip()
        if len(inferred_title) > 120:
            inferred_title = 'Preceding Context'
        # Only add as Story 1 if numbering does not already start at 1
        if first_num != 1:
            stories.append({
                'title': inferred_title or 'Story 1',
                'description': leading_block,
                'acceptance_criteria': extract_acceptance_criteria(leading_block),
                'technical_notes': extract_technical_notes(leading_block),
                'priority': 'Medium',
                'epic': ''
            })

    # Iterate through detected headings building story blocks
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        num = match.group('num')
        raw_title = (match.group('title') or '').strip()
        # Clean excessive trailing punctuation/dots
        raw_title = re.sub(r'[.]{3,}$', '', raw_title).strip()
        if not raw_title:
            # Try first non-empty line of block as title fallback
            first_line = block.split('\n', 1)[0].strip()
            # Avoid using typical section headers as title
            if re.match(r'(?i)Acceptance Criteria|Technical (Implementation )?Notes', first_line):
                first_line = f"Story {num}"
            raw_title = first_line[:140]

        # Extract priority & epic heuristically
        priority_match = re.search(r"Priority:\s*(High|Medium|Low|Critical|Highest)", block, re.IGNORECASE)
        epic_match = re.search(r"Epic:\s*([A-Za-z0-9\- ]+)", block, re.IGNORECASE)

        # Separate description from acceptance criteria
        # Description: user story + context ONLY
        # Acceptance Criteria: AC 1, AC 2, AC 3... with Given/When/Then
        if re.search(r"(?i)Acceptance Criteria", block):
            parts = re.split(r"(?i)(?:^|\n)(?:#+\s*)?Acceptance Criteria(?:\s*\([^)]*\))?\s*:?(?:\n|$)", block, maxsplit=1)
            raw_description = parts[0].strip()
        else:
            raw_description = block

        # Extract acceptance criteria properly (ACs with Given/When/Then format)
        ac_text = extract_acceptance_criteria(block)
        story = {
            'title': raw_title or f"Story {num}",
            'description': raw_description,
            'acceptance_criteria': ac_text,
            'technical_notes': extract_technical_notes(block),
            'priority': (priority_match.group(1).capitalize() if priority_match else 'Medium'),
            'epic': epic_match.group(1).strip() if epic_match else ''
        }
        stories.append(story)

    # Final sanity: ensure titles unique; append counter if duplicates
    seen_titles = {}
    for s in stories:
        base = s['title']
        if base not in seen_titles:
            seen_titles[base] = 1
        else:
            seen_titles[base] += 1
            s['title'] = f"{base} ({seen_titles[base]})"

    return stories

# ---------------------------------------------------------------------------
# Sanitization Helpers
# ---------------------------------------------------------------------------
_SP_LINE_REGEX = re.compile(r"^\s*(\*\*|__)?Story\s+Points?(\*\*|__)?\s*:\s*.*$", re.IGNORECASE)

def strip_story_points_lines(text: str) -> str:
    """Remove any lines that declare Story Points from a block of text."""
    if not text:
        return text
    cleaned = [ln for ln in text.splitlines() if not _SP_LINE_REGEX.match(ln.strip())]
    return "\n".join(cleaned).strip()

def render_workflow_control_table(stories):
    """Render a compact workflow/status table for generated stories.

    Columns:
      #, Title, Priority, Points, JIRA Key (if exported), Status, Actions
    Uses st.session_state.story_workflow_data if present to enrich rows.
    """
    if not stories:
        return
    
    # Initialize story_workflow_data if not exists
    if 'story_workflow_data' not in st.session_state:
        st.session_state.story_workflow_data = {}
    
    # Build row data
    import os, re
    raw_base = os.getenv('JIRA_BASE_URL', 'https://mandg.atlassian.net/rest/api/2/')
    # Remove any /rest/api/<version> or /rest/api/latest fragment
    browse_base_root = re.sub(r"/rest/api/(?:latest|\d+(?:\.\d+)*)/?$", "", raw_base.rstrip('/'))
    if not browse_base_root:
        browse_base_root = 'https://mandg.atlassian.net'
    browse_base = browse_base_root + '/browse/'

    rows = []
    workflow = st.session_state.story_workflow_data  # Now safe to access directly since we initialized above
    # Initialize per-story confirmation state container if missing
    if 'test_gen_confirm' not in st.session_state:
        st.session_state.test_gen_confirm = {}

    for idx, story in enumerate(stories, start=1):
        key = f"story_{idx}"
        wf = workflow.get(key, {})
        jira_key = wf.get('jira_id', '')
        if jira_key:
            jira_display = f"<a href='{browse_base}{jira_key}' target='_blank'>{jira_key}</a>"
        else:
            jira_display = 'None'

        # Build test case links if available
        test_keys = []
        if isinstance(wf.get('test_jira_ids'), list):
            test_keys = wf.get('test_jira_ids')
        elif wf.get('test_jira_id'):
            # Back-compat single value
            test_keys = [wf.get('test_jira_id')]
        test_links_html = ''
        if test_keys:
            link_tags = [f"<a href='{browse_base}{tk}' target='_blank'>{tk}</a>" for tk in test_keys]
            test_links_html = ', '.join(link_tags)
        else:
            test_links_html = 'None'
        rows.append({
            '#': idx,
            'Title': story.get('title', '')[:40] + ('…' if len(story.get('title',''))>40 else ''),
            'JIRA': jira_display,
            'Tests Gen': wf.get('test_case_count', 0),
            'JIRA Tests': test_links_html,
            'Status': wf.get('workflow_status', 'Generated')
        })

    df = pd.DataFrame(rows)
    # Use unsafe_allow_html via to_html to preserve links
    st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)

    # Export All button
    st.markdown("")
    col_export_all, col_spacer = st.columns([2, 8])
    with col_export_all:
        # Count how many stories are not yet exported
        not_exported_count = sum(1 for s in stories if not workflow.get(f"story_{stories.index(s)+1}", {}).get('jira_id'))
        if not_exported_count > 0:
            if st.button(f"📤 Export All ({not_exported_count} remaining)", key="export_all_btn", use_container_width=True):
                if 'accountId' not in st.session_state:
                    st.warning("⚠️ Login required to export stories")
                else:
                    # Get default configuration from session state
                    project = st.session_state.get('default_jira_project') or 'CT'
                    feature_key = st.session_state.get('default_feature_epic')
                    
                    if not feature_key:
                        st.warning("⚠️ Feature Key is required. Please set it in JIRA Configuration at the top.")
                    else:
                        with st.spinner(f"Exporting {not_exported_count} stories to JIRA..."):
                            success_count = 0
                            failed_stories = []
                            
                            # Initialize story_workflow_data if not exists
                            if 'story_workflow_data' not in st.session_state:
                                st.session_state.story_workflow_data = {}
                            
                            for idx, story in enumerate(stories, start=1):
                                key = f"story_{idx}"
                                wf = workflow.get(key, {})
                                
                                # Skip if already exported
                                if wf.get('jira_id'):
                                    continue
                                
                                # Use story-specific config if available, otherwise use defaults
                                story_project = story.get('jira_project') or project
                                story_feature = story.get('feature_epic') or feature_key
                                
                                ok, issue_key, msg = export_story_to_jira(
                                    story, story_project, story_project,
                                    st.session_state.get('accountId'),
                                    st.session_state.get('username'),
                                    epic_key=story_feature,
                                    feature_key=story_feature,
                                    story_points=0
                                )
                                
                                if ok:
                                    if key not in st.session_state.story_workflow_data:
                                        st.session_state.story_workflow_data[key] = {}
                                    st.session_state.story_workflow_data[key]['jira_id'] = issue_key
                                    st.session_state.story_workflow_data[key]['workflow_status'] = 'Exported'
                                    success_count += 1
                                else:
                                    failed_stories.append(f"Story {idx}: {msg}")
                            
                            if success_count > 0:
                                st.success(f"✅ Successfully exported {success_count} stor{'y' if success_count==1 else 'ies'} to JIRA!")
                            if failed_stories:
                                st.error(f"❌ Failed to export {len(failed_stories)} stor{'y' if len(failed_stories)==1 else 'ies'}:")
                                for err in failed_stories[:5]:  # Show max 5 errors
                                    st.caption(err)
                            
                            try: st.rerun()
                            except Exception: pass
        else:
            st.caption("✅ All stories exported")
    st.markdown("---")

    # Track which story is currently awaiting confirmation (single global panel)
    if 'active_test_confirm_story' not in st.session_state:
        st.session_state.active_test_confirm_story = None

    for idx, story in enumerate(stories, start=1):
        key = f"story_{idx}"
        wf = workflow.get(key, {})
        cols = st.columns([4,1,1,1])
        with cols[0]:
            st.write(f"**Story {idx}:** {story.get('title','')[:70]}")
        with cols[1]:
            if st.button("📤 Export", key=f"wf_export_{idx}"):
                if 'accountId' not in st.session_state:
                    st.warning("Login required")
                else:
                    project = story.get('jira_project') or st.session_state.get('default_jira_project') or 'CT'
                    feature_key = story.get('feature_epic') or st.session_state.get('default_feature_epic')
                    ok, issue_key, msg = export_story_to_jira(
                        story, project, project,
                        st.session_state.get('accountId'),
                        st.session_state.get('username'),
                        epic_key=feature_key,
                        feature_key=feature_key,
                        story_points=0
                    )
                    if ok:
                        # Initialize story_workflow_data if not exists
                        if 'story_workflow_data' not in st.session_state:
                            st.session_state.story_workflow_data = {}
                        if key not in st.session_state.story_workflow_data:
                            st.session_state.story_workflow_data[key] = {}
                        st.session_state.story_workflow_data[key]['jira_id'] = issue_key
                        st.session_state.story_workflow_data[key]['workflow_status'] = 'Exported'
                        st.success(issue_key)
                        try: st.rerun()
                        except Exception: pass
                    else:
                        st.error(msg)
        with cols[2]:
            jira_available = bool(wf.get('jira_id'))
            tests_created = bool(wf.get('test_jira_ids')) or bool(wf.get('test_jira_id'))
            tests_generated = int(wf.get('test_case_count', 0) or 0) > 0
            base_disabled = (not jira_available) or tests_created or tests_generated

            if not jira_available:
                help_text = "Export story to JIRA before generating tests"
            elif tests_created:
                created_count = len(wf.get('test_jira_ids') or ([wf.get('test_jira_id')] if wf.get('test_jira_id') else []))
                help_text = f"Tests already created in JIRA ({created_count})"
            elif tests_generated:
                help_text = f"Tests already generated ({wf.get('test_case_count', 0)})"
            else:
                help_text = "Enable and confirm to generate test cases during refinement"

            if tests_created or tests_generated:
                st.caption("✅ Tests ready")
            else:
                # Show enable button only if no other story is awaiting confirmation
                awaiting = st.session_state.active_test_confirm_story
                if awaiting is None:
                    if st.button("🔒 Enable Tests", key=f"wf_tests_enable_{idx}", disabled=base_disabled, help=help_text):
                        if not base_disabled:
                            st.session_state.active_test_confirm_story = key
                            st.session_state.active_test_confirm_idx = idx
                            try: st.rerun()
                            except Exception: pass
                elif awaiting == key:
                    st.caption("⏳ Awaiting confirmation below…")
                else:
                    st.caption("(Another story pending confirmation)")
        with cols[3]:
            if st.button("🗑", key=f"wf_del_{idx}"):
                current = st.session_state.get('generated_stories', [])
                if idx-1 < len(current):
                    del current[idx-1]
                    st.session_state.generated_stories = current if current else None
                    # If deleted story was pending confirmation, clear panel
                    if st.session_state.get('active_test_confirm_story') == key:
                        st.session_state.active_test_confirm_story = None
                        st.session_state.active_test_confirm_idx = None
                    try: st.rerun()
                    except Exception: pass

    # Modal dialog for test generation confirmation
    active_key = st.session_state.get('active_test_confirm_story')
    if active_key:
        active_idx = st.session_state.get('active_test_confirm_idx')
        wf = workflow.get(active_key, {})
        
        @st.dialog(f"Confirm Test Generation for Story {active_idx}")
        def confirm_test_generation():
            st.info(
                "Proceed only when the story is refined, acceptance criteria (incl. NFRs) are agreed, and the story is exported to JIRA."
            )
            proceed_col, cancel_col = st.columns([1,1])
            with proceed_col:
                proceed = st.button("✅ Generate Tests Now", key="confirm_tests_proceed", use_container_width=True)
            with cancel_col:
                cancel = st.button("❌ Cancel", key="confirm_tests_cancel", use_container_width=True)
            
            if cancel:
                st.session_state.active_test_confirm_story = None
                st.session_state.active_test_confirm_idx = None
                st.rerun()
            
            if proceed:
                target_story_key = st.session_state.story_workflow_data.get(active_key, {}).get('jira_id')
                if target_story_key:
                    st.session_state.target_story_key = target_story_key
                    st.session_state.auto_fill_story = True
                    # Manual review flow: user must explicitly submit & accept test cases
                st.session_state.pending_nav_to_tests = True
                st.session_state.active_test_confirm_story = None
                st.session_state.active_test_confirm_idx = None
                st.rerun()
        
        confirm_test_generation()

def display_multiple_stories(stories):
    """Render per-story tabs for editing (title, acceptance criteria, technical notes)."""
    if not stories:
        return
    
    # Get generation version for unique widget keys (prevents stale data after regeneration)
    gen_version = st.session_state.get('story_generation_version', 0)
    
    tabs = st.tabs([f"Story {i+1}" for i in range(len(stories))])
    for i, (tab, story) in enumerate(zip(tabs, stories)):
        with tab:
            # (Test generation panel removed; navigation now handled via main view)
            # Editable fields with generation-versioned keys
            new_title = st.text_input("Title", value=story.get('title',''), key=f"title_v{gen_version}_{i}")
            new_priority = st.selectbox(
                "Priority", ["Low","Medium","High","Critical"],
                index=["Low","Medium","High","Critical"].index(
                    story.get('priority','Medium').capitalize() if story.get('priority') else 'Medium'
                ), key=f"priority_v{gen_version}_{i}"
            )
            
            # Extract AC from description if present, then remove it from description
            full_description = story.get('description', '')
            extracted_ac = extract_acceptance_criteria(full_description)
            clean_description = remove_acceptance_criteria_from_description(full_description) if extracted_ac else full_description
            
            new_description = st.text_area(
                "Description (User story + Context only)", 
                height=160, 
                value=clean_description, 
                key=f"desc_v{gen_version}_{i}",
                help="Description should contain: As a... I want... So that... and 2-4 context sentences. AC section removed automatically."
            )
            
            # Editable AC field with extracted content
            new_ac = st.text_area(
                "Acceptance Criteria (AC 1, AC 2, AC 3... with Given/When/Then)", 
                height=200,
                value=extracted_ac if extracted_ac else story.get('acceptance_criteria', ''),
                key=f"ac_v{gen_version}_{i}",
                help="AC 1, AC 2, AC 3... format with GIVEN/WHEN/THEN. Edit as needed."
            )
            
            new_notes = st.text_area(
                "Technical Notes", height=120,
                value=story.get('technical_notes', extract_technical_notes(story.get('description',''))),
                key=f"notes_v{gen_version}_{i}"
            )
            
            # Auto-save: Detect changes and save automatically
            changes_detected = (
                new_title.strip() != story.get('title', '').strip() or
                new_priority != story.get('priority', 'Medium') or
                new_description.strip() != clean_description.strip() or
                new_ac.strip() != story.get('acceptance_criteria', '').strip() or
                new_notes.strip() != story.get('technical_notes', '').strip()
            )
            
            if changes_detected:
                # Auto-save changes with clean description (no AC section) and edited AC
                story.update({
                    'title': new_title.strip() or story.get('title','Untitled'),
                    'priority': new_priority,
                    'description': new_description,
                    'acceptance_criteria': new_ac,  # Use edited AC value
                    'technical_notes': new_notes
                })
                st.caption("✅ Auto-saved")
            colA, colB = st.columns(2)
            with colA:
                if st.button("Save", key=f"save_story_v{gen_version}_{i}"):
                    # Save with edited AC value
                    story.update({
                        'title': new_title.strip() or story.get('title','Untitled'),
                        'priority': new_priority,
                        'description': new_description,
                        'acceptance_criteria': new_ac,  # Use edited AC
                        'technical_notes': new_notes
                    })
                    st.success("Saved")
                    try: st.rerun()
                    except Exception: pass
            with colB:
                if st.button("Export to JIRA", key=f"export_story_v{gen_version}_{i}"):
                    if 'accountId' not in st.session_state:
                        st.warning("Login required")
                    else:
                        project = story.get('jira_project') or st.session_state.get('default_jira_project') or 'CT'
                        feature_key = story.get('feature_epic') or st.session_state.get('default_feature_epic')
                        ok, issue_key, msg = export_story_to_jira(
                            story, project, project,
                            st.session_state.get('accountId'),
                            st.session_state.get('username'),
                            epic_key=feature_key,
                            feature_key=feature_key,
                            story_points=0
                        )
                        if ok:
                            key = f"story_{i+1}"
                            if 'story_workflow_data' not in st.session_state:
                                st.session_state.story_workflow_data = {}
                            if key not in st.session_state.story_workflow_data:
                                st.session_state.story_workflow_data[key] = {}
                            st.session_state.story_workflow_data[key]['jira_id'] = issue_key
                            st.session_state.story_workflow_data[key]['workflow_status'] = 'Exported'
                            st.success(issue_key)
                            try: st.rerun()
                            except Exception: pass



__STORY_CREATION_BUILD__ = "2025-09-03-01"  # Incremented to enforce new prompt (NFR subsection)
if 'logger' in globals():
    try:
        logger.debug(f"Loading StoryCreation module build {__STORY_CREATION_BUILD__}")
    except Exception:
        pass

def test_jira_connection():
    """Test JIRA connection."""
    try:
        jira_url = os.getenv("JIRA_BASE_URL")
        jira_username = os.getenv("INT_DASHBOARD_JIRA_USERNAME")
        jira_api_token = os.getenv("INT_DASHBOARD_JIRA_AUTH")
        
        if not all([jira_url, jira_username, jira_api_token]):
            return False, "JIRA credentials not configured"
        
        # Test connection by getting projects
        auth = HTTPBasicAuth(jira_username, jira_api_token)
        response = requests.get(f"{jira_url}/rest/api/3/myself", auth=auth, timeout=10)
        
        if response.status_code == 200:
            return True, "✅ JIRA connection successful"
        else:
            return False, f"JIRA connection failed: {response.status_code}"
            
    except Exception as e:
        return False, f"Connection test failed: {str(e)}"

def export_story_to_jira(story_data, project_key, project_name, account_id, email_id, 
                        epic_key=None, feature_key=None, story_points=0, 
                        cust_tech_portfolio=None, cust_tech_delivery_teams=None):
    """Export story to JIRA.

    Enhancement: If ADF builder is available and user enabled rich export toggle
    (session_state['use_adf_export'] == True), build ADF JSON for description.
    Fallback to plain markdown text otherwise.
    """
    try:
        logger.info(f"Exporting story to JIRA project {project_key}")
        # Ensure front-end raw description (use case input) is mapped if model-generated description is empty or generic
        raw_input_desc = st.session_state.get('raw_description_input') or st.session_state.get('raw_use_case_text') or st.session_state.get('use_case_text')
        existing_desc = story_data.get('description')
        if raw_input_desc:
            generic_pattern = re.compile(r"^As a\s+\w+.*I want\s+a capability\s+so that\s+I achieve value\.?$", re.IGNORECASE)
            if (not existing_desc) or len(existing_desc.strip()) < 60 or generic_pattern.match(existing_desc.strip()):
                story_data['description'] = raw_input_desc.strip()
                logger.debug("Description overridden with raw input (length=%d)", len(raw_input_desc))
            else:
                logger.debug("Preserving existing story description (length=%d)", len(existing_desc))
        else:
            logger.debug("No raw input description found in session_state; using story_data['description'] as-is")
        
        # Get acceptance criteria and format in Option B style (AC1: Title, : GIVEN, : WHEN, : THEN)
        raw_ac_source = story_data.get('acceptance_criteria') or extract_acceptance_criteria(story_data.get('description',''))
        raw_ac_source = sanitize_ac_text(raw_ac_source)
        
        # Remove NFR section completely
        nfr_pattern = r'(?i)(?:\n\s*###?\s*Non-Functional Requirements[\s\S]*?)(?=\n\s*AC\s*\d+|\Z)'
        raw_ac_source = re.sub(nfr_pattern, '', raw_ac_source)
        
        # Format AC in Option B style: keep titles, prefix GIVEN/WHEN/THEN with indented ":"
        def format_ac_option_b(ac_text: str) -> list:
            """Format AC in Option B style as a list where each item groups AC title with its GIVEN/WHEN/THEN.
            Returns a list of strings, each containing:
            AC1: Title
               :GIVEN ...
               :WHEN ...
               :THEN ...
            """
            if not ac_text:
                return []
            
            # Parse each AC block (AC 1 - Title ... or AC1: ... or similar)
            ac_blocks = []
            current_block = []
            current_ac_num = None
            current_title = None
            
            for line in ac_text.splitlines():
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                
                # Check if this is an AC header line (AC 1 -, AC1:, AC 1:, etc.)
                ac_header_match = re.match(r'(?i)^AC\s*(\d+)\s*[-:]\s*(.*)$', line_stripped)
                if ac_header_match:
                    # Save previous block if exists
                    if current_block:
                        ac_blocks.append((current_ac_num, current_title, current_block))
                    
                    # Start new block
                    current_ac_num = ac_header_match.group(1)
                    current_title = ac_header_match.group(2).strip()
                    current_block = []
                    continue
                
                # Check if line is GIVEN/WHEN/THEN/AND
                if re.match(r'(?i)^(GIVEN|WHEN|THEN|AND)\b', line_stripped):
                    current_block.append(line_stripped)
                elif current_block:  # Continuation line after GIVEN/WHEN/THEN
                    current_block.append(line_stripped)
            
            # Save last block
            if current_block:
                ac_blocks.append((current_ac_num, current_title, current_block))
            
            # Format blocks - each AC block as a single string with embedded newlines
            formatted_blocks = []
            for ac_num, title, content_lines in ac_blocks:
                # Start with AC title
                block_lines = [f"AC{ac_num}: {title}"]
                
                # Add each GIVEN/WHEN/THEN line with 3 spaces and colon (no space after colon)
                for content_line in content_lines:
                    block_lines.append(f"   :{content_line}")
                
                # Join this AC block into a single string
                formatted_blocks.append("\n".join(block_lines))
            
            return formatted_blocks
        
        ac_lines = format_ac_option_b(raw_ac_source)
        
        tech_text = story_data.get('technical_notes') or extract_technical_notes(story_data.get('description',''))
        base_desc = strip_story_points_lines((story_data.get('description') or '').strip())

        # Plain combined markdown (fallback) – preserve raw description exactly as entered, then append AC & Technical Notes sections if not already present
        # Preserve the EXACT raw description text as entered by the user (no trimming other than converting None->'').
        raw_description_original = story_data.get('description') or ''
        logger.debug(
            "Raw description length=%d preview='%s'",
            len(raw_description_original),
            raw_description_original[:120].replace('\n',' ') + ('…' if len(raw_description_original)>120 else '')
        )
        has_existing_ac_heading = re.search(r'(?im)^##\s*Acceptance Criteria', raw_description_original)
        ac_section = "" if has_existing_ac_heading else ("\n\n## Acceptance Criteria\n" + strip_story_points_lines('\n\n'.join(ac_lines)) if ac_lines else "")
        tech_section = ("\n\n## Technical Notes\n" + strip_story_points_lines(tech_text) if tech_text else "")
        # Even when ADF used, Jira may display plain text preview in some contexts; ensure full raw description present
        combined_description = (raw_description_original + ac_section + tech_section).strip()

        # Choose ADF template version precedence: v3 > v2 > legacy
        use_adf_v3 = bool(st.session_state.get('use_adf_template_v3'))
        use_adf_v2 = bool(st.session_state.get('use_adf_template_v2')) and not use_adf_v3
        use_adf = bool(st.session_state.get('use_adf_export')) and (
            callable(build_story_description_adf)
            or ('build_story_description_adf_v2' in globals())
            or ('build_story_description_adf_v3' in globals())
        )
        adf_doc = None
        if use_adf:
            # Disable heuristic decomposition of role/problem/motivation to prevent hallucinated synthetic sentence.
            # We treat the entire raw_description_original as authoritative user input.
            user_role = story_data.get('user_role') or ''
            primary_problem = story_data.get('primary_problem') or ''
            motivation = story_data.get('motivation') or ''
            # Use acceptance criteria as-is without preprocessing (preserve original AC titles)
            # ac_lines already returned from format_ac_option_b as a list of grouped AC blocks
            data_map_common = {
                'story_title': story_data.get('title') or 'User Story',
                'user_role': user_role,
                'primary_problem': primary_problem,
                'motivation': motivation,
                # Business value should not invent content if not explicitly supplied; leave blank unless provided.
                'business_value': story_data.get('business_value',''),
                'scope_statement': 'Defined by initial context of story text.',
                'acceptance_criteria': ac_lines,  # legacy consumers
                'acceptance_functional': ac_lines,  # preserve original AC format
                'acceptance_nfr': [],  # not separated anymore
                'nfrs': [],
                'created_by': 'JiraTestgenAI',
                'generated_timestamp': pd.Timestamp.utcnow().isoformat(),
                'version': os.getenv('VERSION','1.0'),
                'description_lines': raw_description_original.split('\n'),
            }
            chosen_builder = None
            if use_adf_v3 and build_story_description_adf_v3:
                data_map_v3 = {
                    **data_map_common,
                    'requirements': story_data.get('requirements') or story_data.get('technical_notes','').split('\n')[:3],  # minimal safe requirement extraction
                    # Provide raw description verbatim to ADF builder.
                    'additional_info': raw_description_original,
                    'additional_info_raw': raw_description_original,
                    'meta': {
                        'ac_summary': f"Total AC: {len(ac_lines)}"
                    }
                }
                try:
                    adf_doc = build_story_description_adf_v3(data_map_v3)
                    chosen_builder = 'v3'
                    if not validate_adf_size(adf_doc):
                        logger.warning("ADF v3 document exceeds size threshold – falling back to plain description")
                        adf_doc = None
                except Exception as adf_ex:
                    logger.error(f"Failed building ADF v3: {adf_ex}; falling back to plain text")
                    adf_doc = None
            elif use_adf_v2 and build_story_description_adf_v2:
                # Additional mapping for template v2
                data_map_v2 = {
                    **data_map_common,
                    'requirements': story_data.get('requirements') or story_data.get('technical_notes','').split('\n')[:3],
                    'additional_info': story_data.get('description'),
                }
                try:
                    adf_doc = build_story_description_adf_v2(data_map_v2)
                    chosen_builder = 'v2'
                    if not validate_adf_size(adf_doc):
                        logger.warning("ADF v2 document exceeds size threshold – falling back to plain description")
                        adf_doc = None
                except Exception as adf_ex:
                    logger.error(f"Failed building ADF v2: {adf_ex}; falling back to plain text")
                    adf_doc = None
            else:
                # Legacy builder path retains extended fields
                legacy_map = {
                    **data_map_common,
                    'out_of_scope': [],
                    'assumptions': [],
                    'preconditions': [],
                    'postconditions': 'Story success state achieved; data persisted; audit logged.',
                    'gherkin': '',
                    'edge_cases': [],
                    'dependencies': [],
                    'test_summary': 'Tests to be generated via JiraTestgenAI.',
                    'links': [],
                    'revision_history': []
                }
                try:
                    if build_story_description_adf:
                        # Inject raw description paragraphs directly at top of legacy map by overwriting fields used for synthesis
                        legacy_map['business_value'] = ''  # avoid reuse of motivation
                        # Provide raw description as first paragraphs by pre-pending to description fields if builder uses them
                        adf_doc = build_story_description_adf(legacy_map)
                        chosen_builder = 'legacy'
                    if not validate_adf_size(adf_doc):
                        logger.warning("ADF document exceeds size threshold – falling back to plain description")
                        adf_doc = None
                except Exception as adf_ex:
                    logger.error(f"Failed building ADF: {adf_ex}; falling back to plain text")
                    adf_doc = None

            try:
                logger.info("ADF builder chosen: %s", chosen_builder or 'none (plain text)')
            except Exception:
                pass

        ct_portfolio = st.session_state.get('ct_portfolio') if project_key == 'CT' else None

        # Merge per-story labels into global custom_labels (transient for this export only)
        try:
            per_story_labels = story_data.get('labels') or []
            global_labels = st.session_state.get('global_labels', []) or []
            per_story_labels = per_story_labels + [g for g in global_labels if g not in per_story_labels]
            if per_story_labels:
                existing = set([l for l in st.session_state.get('custom_labels', [])])
                for l in per_story_labels:
                    if l not in existing:
                        existing.add(l)
                st.session_state.custom_labels = list(existing)
        except Exception:
            pass

        # Build description with main story content only (remove AC section if present)
        description_text = story_data.get('description', '')
        
        # Get acceptance criteria from story_data (user edited in Streamlit)
        ac_for_jira = story_data.get('acceptance_criteria', '')
        
        # Clean AC: remove generic placeholder content
        if ac_for_jira:
            generic_patterns = [
                r'Given I am a user with appropriate permissions',
                r'When I access the feature',
                r'Given a user with privileges',
                r'When they initiate a standard operation',
                r'\[performance\]',
                r'\[accessibility\]',
                r'\[security\]',
                r'\[audit\]',
                r'### Non-Functional Requirements',
                r'Performance: p95',
                r'Accessibility: Meets WCAG',
                r'Security/Penetration:'
            ]
            # Check if AC contains generic content
            has_generic = any(re.search(pat, ac_for_jira, re.IGNORECASE) for pat in generic_patterns)
            if has_generic:
                # Filter out generic lines, keep only AC N lines with GIVEN/WHEN/THEN
                lines = ac_for_jira.split('\n')
                clean_lines = []
                for line in lines:
                    # Keep lines that are AC N or GIVEN/WHEN/THEN, skip generic ones
                    if re.match(r'(?i)^AC\s*\d+', line.strip()) or re.match(r'(?i)^(GIVEN|WHEN|THEN|AND)\b', line.strip()):
                        # Check if this line itself doesn't contain generic markers
                        if not any(re.search(gp, line, re.IGNORECASE) for gp in [r'\[performance\]', r'\[accessibility\]', r'\[security\]', r'\[audit\]']):
                            clean_lines.append(line)
                ac_for_jira = '\n'.join(clean_lines).strip()
        
        # Ensure description doesn't have AC section
        if extract_acceptance_criteria(description_text):
            description_text = remove_acceptance_criteria_from_description(description_text)
        
        complete_description = description_text or base_desc
        # Clean up generic content from AC
        if ac_for_jira:
            generic_patterns = [
                r'Given I am a user with appropriate permissions',
                r'When I access the feature',
                r'Given a user with privileges',
                r'When they initiate a standard operation',
                r'\[performance\]',
                r'\[accessibility\]',
                r'\[security\]',
                r'\[audit\]',
                r'### Non-Functional Requirements'
            ]
            is_generic = any(re.search(pat, ac_for_jira, re.IGNORECASE) for pat in generic_patterns)
            if is_generic:
                ac_for_jira = ""  # Clear generic AC
        
        # Add technical notes to description if present and not generic
        tech_for_jira = story_data.get('technical_notes') or extract_technical_notes(story_data.get('description',''))
        if tech_for_jira and tech_for_jira.strip():
            # Skip if it's generic placeholder content
            generic_tech_patterns = [
                r'Consider scalability requirements',
                r'Ensure backward compatibility',
                r'Follow team coding standards'
            ]
            is_generic_tech = any(re.search(pat, tech_for_jira, re.IGNORECASE) for pat in generic_tech_patterns)
            if not is_generic_tech:
                complete_description += "\n\n## Technical Notes\n\n" + tech_for_jira.strip()
        
        # Use ADF doc if available, otherwise use complete_description
        final_description = adf_doc if adf_doc else complete_description
        
        story_id, issue_key = post_story_creation(
            summary=story_data['title'],
            description=final_description,
            project_key=project_key,
            project_name=project_name,
            account_id=account_id,
            email_id=email_id,
            epic_key=epic_key,
            feature_key=feature_key,
            story_points=0,
            cust_tech_portfolio=ct_portfolio or cust_tech_portfolio,
            cust_tech_delivery_teams=None,
            acceptance_criteria_text=ac_for_jira.strip() if ac_for_jira else None
        )

        if story_id and issue_key:
            logger.info(f"Story created successfully: {issue_key} (ADF={'yes' if adf_doc else 'no'})")
            return True, issue_key, f"Story created successfully: {issue_key}"
        else:
            base_error_msg = "Failed to create story in JIRA"
            detailed_msg = ""
            try:
                from pathlib import Path
                log_path = Path("c:/Users/P3000767/Documents/Tesgen app/qa-jira-test-case-generator-app/src/logs/app.log")
                recent_logs = []
                if log_path.exists():
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as log_file:
                        recent_logs = log_file.readlines()[-120:]
                jira_response_lines = [l for l in recent_logs if 'postStoryCreation response.text:' in l]
                last_response_line = jira_response_lines[-1] if jira_response_lines else ''
                extracted_api_json = None
                if last_response_line:
                    json_start = last_response_line.find('{')
                    if json_start != -1:
                        potential_json = last_response_line[json_start:].strip()
                        import json as _json
                        try:
                            extracted_api_json = _json.loads(potential_json)
                        except Exception:
                            pass
                if extracted_api_json and isinstance(extracted_api_json, dict):
                    errs = extracted_api_json.get('errorMessages') or []
                    if errs:
                        detailed_msg = '; '.join(errs)
                else:
                    permission_errors = [line for line in recent_logs if 'You do not have permission' in line]
                    epic_type_errors = [line for line in recent_logs if 'must be of type' in line and 'Epic' in line]
                    if permission_errors:
                        detailed_msg = permission_errors[-1].split(' - ', 1)[-1].strip()
                    elif epic_type_errors:
                        detailed_msg = epic_type_errors[-1].split(' - ', 1)[-1].strip()
                guidance = []
                if detailed_msg:
                    if 'must be of type' in detailed_msg and 'Epic' in detailed_msg:
                        guidance.append("The key entered in the Feature/Epic field is not an Epic. Please supply a valid Epic key (issue type Epic).")
                    if 'permission' in detailed_msg.lower():
                        guidance.append("You may lack Create Issue permissions for the selected project. Try a different project or contact a JIRA administrator.")
                else:
                    guidance.append("Check that: (1) JIRA credentials are valid, (2) you have Create Issue permissions, (3) the Epic/Feature key is correct.")
                combined_guidance = ' '.join(guidance)
                error_msg = f"{base_error_msg}. {detailed_msg if detailed_msg else ''} {combined_guidance}".strip()
            except Exception as parse_ex:
                error_msg = f"Failed to create story in JIRA (no additional detail available) - parsing error: {parse_ex}"
            logger.error(error_msg)
            return False, None, error_msg
    except Exception as e:
        logger.exception("Unexpected exception during export_story_to_jira")
        return False, None, f"Exception during export: {str(e)}"

def remove_acceptance_criteria_from_description(text):
    """Remove the Acceptance Criteria section from description text.
    
    Returns the description with AC section removed (only user story + context remains).
    """
    if not text:
        return text
    
    # Remove everything from "Acceptance Criteria:" onwards (including Technical Notes if present)
    patterns = [
        r"(?is)\n\s*\*\*Acceptance Criteria:\*\*.*$",  # **Acceptance Criteria:** and everything after
        r"(?is)\n\s*##\s*Acceptance Criteria.*$",  # ## Acceptance Criteria and everything after
        r"(?is)\n\s*Acceptance Criteria:.*$",  # Acceptance Criteria: and everything after
    ]
    
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned)
    
    return cleaned.strip()

def extract_acceptance_criteria(text):
    """Extract acceptance criteria from story text.
    
    Extracts everything after 'Acceptance Criteria:' heading until Technical Notes or end of text.
    This includes all AC 1, AC 2, AC 3... with GIVEN/WHEN/THEN blocks.
    """
    if not text:
        return ""

    # Pattern to find "Acceptance Criteria:" (with optional markdown ** or ##) and capture everything after it
    # Stop at Technical Notes section or end of text
    patterns = [
        r"(?is)\*\*Acceptance Criteria:\*\*\s*\n(.+?)(?=\n\s*(?:##|\*\*)\s*Technical|$)",  # **Acceptance Criteria:**
        r"(?is)##\s*Acceptance Criteria\s*\n(.+?)(?=\n\s*##\s*Technical|$)",  # ## Acceptance Criteria
        r"(?is)Acceptance Criteria:\s*\n(.+?)(?=\n\s*(?:##|\*\*)\s*Technical|$)",  # Acceptance Criteria:
    ]
    
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            block = m.group(1).strip()
            if block:
                return block

    # No acceptance criteria found
    return ""

    # Filter lines: keep bullets, numbered items, and Given/When/Then style lines
    # Remove any markdown fenced code blocks or language specifiers (``` or ```markdown)
    sanitized = []
    fence_open = False
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith('```'):  # toggle fence
            fence_open = not fence_open
            continue
        if fence_open:
            # Skip content inside fenced code blocks for AC purposes
            continue
        # Remove accidental 'markdown' labels that sometimes appear from model output
        if line.strip().lower() in {'markdown','```markdown'}:
            continue
        sanitized.append(line)
    lines = sanitized
    kept = []
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            continue
        if re.match(r"[-*•]\s+", stripped):
            kept.append(stripped)
        elif re.match(r"\d+\.\s+", stripped):
            kept.append(stripped)
        elif re.match(r"(?i)(Given|When|Then|And)\b", stripped):
            kept.append(stripped if stripped.startswith('-') else f"- {stripped}")
        elif len(stripped) < 120 and ('should' in stripped.lower() or 'must' in stripped.lower()):
            # Heuristic acceptance statement
            kept.append(f"- {stripped}")
    # If filtering removed everything, fall back to original block
    if not kept:
        kept = lines
    return "\n".join(kept).strip()

def sanitize_ac_text(ac_text: str) -> str:
    """Remove fenced code blocks and stray markdown labels from acceptance criteria string."""
    if not ac_text:
        return ac_text
    out_lines = []
    fence = False
    for ln in ac_text.split('\n'):
        if ln.strip().startswith('```'):
            fence = not fence
            continue
        if fence:
            continue
        if ln.strip().lower() in {'markdown','```markdown'}:
            continue
        out_lines.append(ln)
    return '\n'.join(out_lines)

def extract_technical_notes(text):
    """Extract technical implementation notes from story text."""
    # Look for technical sections
    patterns = [
        r'(?:Technical Notes?|Implementation|Tech Notes?):\s*((?:.*\n?)*?)(?:\n\n|\n(?=[A-Z][^:\n]*:)|$)',
        r'(?:Implementation Details?|Technical Details?):\s*((?:.*\n?)*?)(?:\n\n|\n(?=[A-Z][^:\n]*:)|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip()
    
    # Default notes if extraction fails
    return """• Consider scalability requirements for future growth
• Ensure backward compatibility with existing systems
• Follow team coding standards and conventions"""

def ensure_nfr_subsection_in_ac(ac_text: str) -> str:
    """Ensure Acceptance Criteria includes a visible NFR subsection with concrete bullets.

    If the NFR subsection is missing, append a template with Performance, Accessibility,
    and Security/Penetration bullets. Returns updated acceptance criteria text.
    """
    base = (ac_text or "").strip()
    if not base:
        base = "- Given [context]\n- When [action]\n- Then [outcome]"
    # Check if NFR subsection already present
    if re.search(r"(?i)Non-Functional Requirements\s*\(NFRs?\)|\bNFRs?\b", base):
        return base
    # Append a clearly labeled NFR block
    nfr_block = (
        "\n\n### Non-Functional Requirements (NFRs) — Performance, Accessibility, Security/Penetration\n"
        "- Performance: p95 < 2s page load; API p95 < 500ms; CPU < 70% under expected load\n"
        "- Accessibility: Meets WCAG 2.1 AA; keyboard-only navigation; ARIA labels present\n"
        "- Security/Penetration: Input validation; authorization enforced on all endpoints; no secrets in client\n"
    )
    return base + nfr_block

def diversify_acceptance_criteria(ac_text: str, story_title: str, description: str, user_role: str, primary_problem: str) -> str:
    """Diversify acceptance criteria by injecting story-specific context, de-duplicating, and balancing functional vs NFR lines.

    Steps:
      1. Split into raw lines; remove empty and heading markers.
      2. Identify functional (Given/When/Then) vs non-functional (performance/security/etc.) lines.
      3. Generate contextual NFR variants referencing key domain nouns from title/problem.
      4. Merge & deduplicate (case-insensitive) preserving original order priority.
      5. Enforce ratio: aim for >=60% functional if available; otherwise generate synthetic functional scaffolds.
      6. Truncate overly long lines and remove trailing punctuation duplicates.
    """
    if not ac_text:
        ac_text = "- Given valid context\n- When primary action occurs\n- Then expected result is achieved"
    lines = [ln.strip() for ln in ac_text.split('\n') if ln.strip() and not ln.strip().startswith('###')]
    # Extract domain tokens from title/problem (simple heuristic: nouns by splitting and filtering)
    domain_tokens = []
    for source in (story_title, primary_problem):
        if source:
            parts = re.split(r'[^A-Za-z0-9]+', source)
            for p in parts:
                if len(p) > 3 and p.lower() not in {'user','story','feature','system','data'}:
                    domain_tokens.append(p.lower())
    domain_tokens = list(dict.fromkeys(domain_tokens))[:5]
    domain_fragment = ', '.join(domain_tokens) if domain_tokens else ''

    functional = [l for l in lines if re.match(r'(?i)^(given|when|then|and)\b', l)]
    nfr_patterns = r'(?i)(performance|latency|p95|p99|accessibility|wcag|security|owasp|authorization|privacy|pii|reliability|failover|observability|logging|audit|scalability|throughput)'
    non_functional = [l for l in lines if re.search(nfr_patterns, l)]

    # Contextual NFR variants (only add if we have domain tokens)
    contextual_nfrs = []
    if domain_tokens:
        contextual_nfrs.extend([
            f"Performance ({domain_fragment}): p95 < 500ms for critical operations",
            f"Security ({domain_fragment}): all inputs validated; authorization enforced for protected resources",
            f"Observability ({domain_fragment}): structured logs include correlation IDs for traceability",
            f"Reliability ({domain_fragment}): graceful degradation if dependent service unavailable",
            f"Accessibility ({domain_fragment}): keyboard-only navigation and ARIA roles validated",
        ])
    # If missing functional breadth, synthesize a few generic Given/When/Then lines referencing domain
    if len(functional) < 6:
        synth_base = domain_tokens[0] if domain_tokens else 'feature'
        scaffold = [
            f"Given a user with privileges to access {synth_base}",
            f"When they initiate a standard operation on {synth_base}",
            f"Then the system persists changes and confirms success",
            f"When invalid data is submitted for {synth_base}",
            f"Then validation messages are displayed without partial commits",
        ]
        functional.extend([l for l in scaffold if l not in functional])

    # Deduplicate preserving first occurrence (case-insensitive)
    def dedupe(seq):
        seen = set()
        out = []
        for item in seq:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out

    merged = dedupe(functional + non_functional + contextual_nfrs)

    # Trim overly long lines
    cleaned = []
    for l in merged:
        if len(l) > 220:
            l = l[:217].rstrip() + '…'
        # Ensure bullet prefix
        if not l.startswith('- '):
            l = '- ' + l
        cleaned.append(l)

    # Cap / ensure minimum
    if len(cleaned) < 10:
        cleaned.extend(['- Error paths handled without exposing stack traces', '- Metrics emitted: latency, errors, throughput'])
    if len(cleaned) > 30:
        cleaned = cleaned[:30]

    # Return diversified bullets without AC numbering; scenario formatting will handle numbered headers
    return '\n'.join(cleaned)

def scenario_format_acceptance_criteria(ac_text: str) -> str:
    """Format acceptance criteria into distinct scenarios numbered AC 1, AC 2, ...

    Scenario structure:
      AC <n> - <SCENARIO NAME>
      Given ...
      When ...
      Then ...
      1) additional outcome
      2) additional outcome

    Rules:
      * Each 'Given' starts a new scenario.
      * First 'When' and first 'Then' kept; subsequent When/Then/And lines become numbered outcomes.
      * Lines like '- AC1:' or 'AC1 -' from previous formatting are ignored.
      * If no Given found, synthesize one from the first functional line.
      * Preserve trailing NFR block (### Non-Functional Requirements ...).
    """
    if not ac_text:
        return "AC 1 - SCENARIO\nGiven a valid context\nWhen an action occurs\nThen the expected outcome is produced"
    # Separate NFR block (keep at end)
    nfr_match = re.search(r"(\n\s*###\s*Non-Functional Requirements[\s\S]*)", ac_text, flags=re.IGNORECASE)
    nfr_block = nfr_match.group(1).strip('\n') if nfr_match else ''
    functional_part = ac_text.replace(nfr_block, '') if nfr_block else ac_text
    # Normalize lines; drop bullet prefix and prior AC headers
    raw_lines = []
    for ln in functional_part.splitlines():
        if not ln.strip():
            continue
        stripped = re.sub(r'^[-*•]\s*', '', ln).strip()
        if re.match(r'(?i)^AC\s*\d+\b', stripped) or re.match(r'(?i)^AC\d+\b', stripped):
            # Skip old AC header lines
            continue
        raw_lines.append(stripped)

    scenarios = []
    current = {'given': None, 'when': None, 'then': None, 'extras': []}

    def flush():
        if current['given'] or current['when'] or current['then'] or current['extras']:
            scenarios.append({k: v for k, v in current.items()})
        current['given'] = current['when'] = current['then'] = None
        current['extras'] = []

    for ln in raw_lines:
        if re.match(r'(?i)^given\b', ln):
            flush(); current['given'] = ln; continue
        if current['given'] and not current['when'] and re.match(r'(?i)^when\b', ln):
            current['when'] = ln; continue
        if current['given'] and current['when'] and not current['then'] and re.match(r'(?i)^then\b', ln):
            current['then'] = ln; continue
        # Additional lines become numbered outcomes
        if re.match(r'(?i)^(when|then|and)\b', ln):
            extra = re.sub(r'(?i)^(when|then|and)\b\s*', '', ln).strip()
            current['extras'].append(extra)
        else:
            # If scenario not started yet, treat as Given
            if not current['given']:
                flush(); current['given'] = f"Given {ln}" if not ln.lower().startswith('given') else ln
            else:
                current['extras'].append(ln)
    flush()

    if not scenarios:
        scenarios = [{'given': 'Given context established', 'when': 'When action is performed', 'then': 'Then expected result is produced', 'extras': []}]

    out_lines = []
    for i, sc in enumerate(scenarios, start=1):
        given_line = sc['given'] or 'Given context established'
        # Derive scenario name from Given phrase (take first 3 meaningful tokens)
        name_tokens = []
        after_given = re.sub(r'(?i)^given\b', '', given_line).strip()
        for token in re.split(r'[^A-Za-z0-9]+', after_given):
            if token and token.lower() not in {'a','an','the','and','with','user','valid','context','is','are','to','of'}:
                name_tokens.append(token.capitalize())
            if len(name_tokens) >= 3:
                break
        scenario_name = ' '.join(name_tokens) or 'Scenario'
        out_lines.append(f"AC {i} - {scenario_name.upper()}")
        out_lines.append(given_line)
        out_lines.append(sc['when'] or 'When action is performed')
        out_lines.append(sc['then'] or 'Then expected result is produced')
        for idx_ex, extra in enumerate(sc['extras'], start=1):
            if extra:
                out_lines.append(f"{idx_ex}) {extra}")
        out_lines.append('')  # blank line between scenarios

    formatted = '\n'.join(out_lines).rstrip()
    if nfr_block:
        formatted += '\n\n' + nfr_block
    return formatted

def display_created_tickets():
    """Display all created JIRA tickets in a persistent area."""
    # Collect all created stories from session state
    created_stories = []
    
    # Check for created stories from both regular and view panels
    for key in st.session_state.keys():
        if key.startswith('created_story_') or key.startswith('view_created_story_'):
            story_info = st.session_state[key]
            if isinstance(story_info, dict) and 'story_key' in story_info:
                created_stories.append(story_info)
    
    if created_stories:
        st.markdown("---")
        header_col, clear_col = st.columns([3, 1])
        with header_col:
            st.markdown("### <span class='badge'>JIRA</span> Created Stories", unsafe_allow_html=True)
        with clear_col:
            if st.button("🗑️ Clear All", 
                        key="clear_created_stories",
                        type="secondary",
                        help="Clear all created story records"):
                # Remove all created story entries from session state
                for key in list(st.session_state.keys()):
                    if key.startswith('created_story_') or key.startswith('view_created_story_'):
                        del st.session_state[key]
                st.rerun()
        
        # Create a container for the created stories
        with st.container():
            for i, story in enumerate(created_stories):
                col1, col2, col3 = st.columns([2, 2, 1])
                
                with col1:
                    st.markdown(f"**{story['story_key']}**")
                    st.caption(f"📋 {story['story_title']}")
                
                with col2:
                    if 'story_url' in story:
                        st.markdown(f"🔗 [View in JIRA]({story['story_url']})")
                    st.caption(f"📁 Project: {story.get('project_key', 'N/A')}")
                
                with col3:
                    # Create a more professional button layout
                    button_container = st.container()
                    with button_container:
                        if st.button("🧪 Create Test Cases", 
                                   key=f"persistent_create_tests_{story['story_key']}",
                                   type="primary",
                                   use_container_width=True,
                                   help=f"Generate test cases for {story['story_key']}"):
                            # Navigate to test case creation
                            st.session_state.target_story_key = story['story_key']
                            st.session_state.navigate_to_tests = True
                            st.session_state.auto_fill_story = True
                            st.query_params.navigate_to_tests = 'true'
                            st.query_params.story_identifier = story['story_key']
                            st.session_state.auto_run_tests = True
                            st.info("🔄 Please click 'Test Cases Generator' tab above to proceed")
                            st.rerun()
                
                if i < len(created_stories) - 1:  # Add separator except for last item
                    st.markdown("---")
        
        st.markdown("---")

def render_story_creation():
    """Render the story creation interface (clean, re-indented version)."""
    st.markdown(
        "<h1 style='margin-bottom:4px;'><span class='badge'>USER STORY</span> Generator</h1>",
        unsafe_allow_html=True,
    )
    st.markdown("Transform your use cases into comprehensive user stories with AI assistance.")

    # Environment / endpoint badges
    endpoint = st.session_state.get('storygen_endpoint_used')
    mock_used = st.session_state.get('storygen_mock')
    last_error = st.session_state.get('storygen_last_error') if mock_used else None
    badge_parts = []
    if endpoint:
        badge_parts.append(f"<span style='background:#0b7285;color:#fff;padding:4px 8px;border-radius:12px;font-size:12px;margin-right:6px;'>Endpoint: {endpoint}</span>")
    if mock_used:
        badge_parts.append("<span style='background:#ffa94d;color:#222;padding:4px 8px;border-radius:12px;font-size:12px;margin-right:6px;'>MOCK MODE</span>")
    if last_error:
        badge_parts.append(f"<span style='background:#ffc9c9;color:#c92a2a;padding:4px 8px;border-radius:12px;font-size:12px;'>Last Error: {last_error[:90]}{'…' if len(last_error)>90 else ''}</span>")
    if badge_parts:
        st.markdown("<div style='margin:4px 0 12px 0;'>" + "".join(badge_parts) + "</div>", unsafe_allow_html=True)

    # Created tickets panel
    display_created_tickets()

    # Lazy-load JIRA projects
    if (
        'accountId' in st.session_state
        and 'username' in st.session_state
        and 'available_projects' not in st.session_state
    ):
        try:
            with st.spinner("Loading JIRA projects..."):
                st.session_state.available_projects = get_available_projects()
        except Exception as e:
            st.error(f"❌ Error loading JIRA projects: {e}")
            st.session_state.available_projects = []

    stories = st.session_state.get('generated_stories')

    # =============================
    # EXISTING STORIES VIEW
    # =============================
    if stories:
        story_count = len(stories)
        # Correct pluralisation (avoid 'Storyies')
        plural = "Story" if story_count == 1 else "Stories"
        st.success(
            f"{story_count} {plural} generated – ready for review and export"
        )

        # =============================
        # ADJUST STORY COUNT & REGENERATE
        # =============================
        st.markdown("---")
        st.markdown("### 🔄 Adjust Story Count & Regenerate")
        st.markdown(
            """
            <div style='background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%); padding: 15px; border-radius: 10px; margin-bottom: 15px; color: white;'>
                <h4 style='color: white; margin-top: 0;'>📊 Dynamic Story Adjustment</h4>
                <p style='margin-bottom: 0; font-size: 14px;'>
                    <strong>Reduce stories:</strong> Consolidate functionalities into fewer, broader stories<br/>
                    <strong>Increase stories:</strong> Split functionalities into more granular, focused stories
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Create columns for slider and button
        slider_col, button_col = st.columns([3, 1])
        
        with slider_col:
            # Initialize regenerate slider value with current story count
            if 'regenerate_story_count' not in st.session_state:
                st.session_state.regenerate_story_count = story_count
            
            new_story_count = st.slider(
                "Adjust Number of Stories to generate",
                min_value=1,
                max_value=15,
                value=st.session_state.regenerate_story_count,
                key="regenerate_slider",
                help="Slide to adjust the number of stories."
            )
            st.session_state.regenerate_story_count = new_story_count
            
            # Visual feedback on change
            if new_story_count < story_count:
                st.caption(f"⬇️ **Consolidating** from {story_count} to {new_story_count} stories (broader scope per story)")
            elif new_story_count > story_count:
                st.caption(f"⬆️ **Splitting** from {story_count} to {new_story_count} stories (more granular stories)")
            else:
                st.caption(f"✅ Current: {story_count} stories")
        
        with button_col:
            st.markdown("<br/>", unsafe_allow_html=True)  # Align button with slider
            regenerate_clicked = st.button(
                "🔄 Regenerate",
                type="primary",
                help="Generate new stories with the adjusted count",
                use_container_width=True
            )
        
        # Handle regeneration
        if regenerate_clicked:
            # Check if we have the original use case text
            use_case_text = st.session_state.get('raw_use_case_text', '')
            if not use_case_text:
                st.error("⚠️ Cannot regenerate: Original use case text not found. Please generate new stories from the input form.")
            else:
                # Update desired count in session state
                st.session_state['desired_story_count'] = new_story_count
                st.session_state['story_count_slider'] = new_story_count
                
                # Get uploaded images if they exist (stored in session)
                uploaded_images_data = st.session_state.get('uploaded_images_data', [])
                
                # Build content with adjustment context
                adjustment_context = ""
                if new_story_count < story_count:
                    adjustment_context = f"\n\nIMPORTANT: Consolidate the functionalities into exactly {new_story_count} stories (currently {story_count}). Merge related features and broaden story scope while maintaining all core functionalities."
                elif new_story_count > story_count:
                    adjustment_context = f"\n\nIMPORTANT: Split the functionalities into exactly {new_story_count} stories (currently {story_count}). Create more granular, focused stories while covering all functionalities."
                
                content = use_case_text + adjustment_context
                
                with st.spinner(f"🤖 Regenerating {new_story_count} stories..."):
                    success, result = generate_story_with_gencore(content, uploaded_images_data if uploaded_images_data else None)
                
                if success:
                    # Parse and update stories
                    new_stories = parse_multiple_stories(result)
                    
                    if len(new_stories) > 0:
                        # Get old story count before updating
                        old_story_count = len(st.session_state.get('generated_stories', []))
                        
                        st.session_state['generated_stories'] = new_stories
                        
                        # Clear and rebuild workflow data for new story count
                        st.session_state.story_workflow_data = {}
                        
                        # Get default JIRA configuration
                        default_project = st.session_state.get('default_jira_project') or 'CT'
                        default_feature = st.session_state.get('default_feature_epic')
                        
                        # Initialize workflow data for each new story
                        for i, s in enumerate(new_stories):
                            key = f"story_{i+1}"
                            s['jira_project'] = default_project
                            s['feature_epic'] = default_feature
                            st.session_state.story_workflow_data[key] = {
                                'jira_id': None,
                                'test_case_count': 0,
                                'test_jira_id': None,
                                'test_jira_ids': None,
                                'workflow_status': 'Generated',
                                'story_title': s.get('title', 'Untitled'),
                                'priority': s.get('priority', 'Medium'),
                                'story_points': '0',
                                'jira_project': default_project,
                                'feature_epic': default_feature,
                            }
                        
                        # Increment generation counter to invalidate old widget keys
                        # This ensures cached widget values from old stories don't interfere
                        if 'story_generation_version' not in st.session_state:
                            st.session_state.story_generation_version = 0
                        st.session_state.story_generation_version += 1
                        
                        st.success(f"✅ Successfully regenerated {len(new_stories)} stories!")
                        st.rerun()
                    else:
                        st.error("No stories were generated. Please try again.")
                else:
                    st.error(f"Regeneration failed: {result}")

        st.markdown("---")

        col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
        with col_stats1:
            st.metric("Total Stories", story_count)
        with col_stats2:
            st.metric(
                "High Priority",
                len([s for s in stories if s.get('priority', '').lower() == 'high']),
            )
        with col_stats3:
            st.metric(
                "Total Points",
                0,
            )
        with col_stats4:
            st.metric(
                "With Epic",
                len([s for s in stories if s.get('epic', '').strip()]),
            )

        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Generate New Stories"):
                # Clear feedback when starting completely fresh
                st.session_state.pop('story_generation_feedback', None)
                st.session_state.generated_stories = None
                st.rerun()
        with c2:
            st.caption("Export individually from the workflow table or tabs below")
        with c3:
            if st.button("Copy All Stories as Text"):
                copy_all_stories_as_text(stories)

        st.markdown("---")
        
        if len(stories) >= 1:
            st.markdown("### Workflow Control Center")
            with st.container():
                render_workflow_control_table(stories)

        st.markdown("### Review & Edit Individual Stories")
        st.caption(
            "Use the tabs below to edit content, acceptance criteria and technical notes."
        )
        st.markdown("")
        # Enforce NFR subsection for any stories that may have been cached without it
        try:
            for s in stories:
                s['acceptance_criteria'] = ensure_nfr_subsection_in_ac(
                    s.get('acceptance_criteria') or extract_acceptance_criteria(s.get('description',''))
                )
        except Exception:
            pass
        display_multiple_stories(stories)
        
        # ========== FEEDBACK LOOP SECTION - BELOW JIRA EXPORT ==========
        st.markdown("---")
        st.markdown("### 💬 Provide Feedback & Regenerate Stories")
        st.markdown("""
        <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; margin-bottom: 20px; color: white;'>
            <h4 style='color: white; margin-top: 0;'>🔄 Iterative Improvement</h4>
            <p style='margin-bottom: 0;'>Not satisfied with the generated stories? Provide specific feedback below and regenerate to get improved results. Your feedback will automatically enrich the prompt to address quality issues.</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Display previous feedback if exists
        previous_feedback = st.session_state.get('story_generation_feedback', '')
        if previous_feedback:
            st.success(f"✅ **Active Feedback Being Used:** {previous_feedback}")
        
        # Feedback input
        feedback_text = st.text_area(
            "What would you like to improve? (Be specific for best results)",
            placeholder="Examples:\n- Story 2 acceptance criteria are too generic, need more specific validation scenarios\n- Missing edge cases for error handling in Story 3\n- Technical notes should include database schema changes\n- Priorities seem incorrect for business value\n- Stories are too broad, need better vertical slicing\n- Need more persona-specific stories for different user roles",
            height=180,
            key="feedback_input",
            help="Be specific about what's wrong and what you expect. The more detailed your feedback, the better the regenerated stories."
        )
        
        col_fb1, col_fb2, col_fb3 = st.columns([3, 2, 1])
        with col_fb1:
            if st.button("🔄 Apply Feedback & Auto-Regenerate", type="primary", disabled=not feedback_text.strip(), use_container_width=True):
                if feedback_text.strip():
                    st.session_state['story_generation_feedback'] = feedback_text.strip()
                    st.session_state['regenerate_mode'] = True
                    st.session_state['auto_regenerate'] = True
                    st.session_state.generated_stories = None
                    st.rerun()
        with col_fb2:
            if st.button("🗑️ Clear Feedback & Start Fresh", use_container_width=True):
                st.session_state.pop('story_generation_feedback', None)
                st.session_state.generated_stories = None
                st.success("Feedback cleared. Generate new stories without feedback context.")
                st.rerun()
        with col_fb3:
            st.metric("Feedback", "✅ Active" if previous_feedback else "⭕ None")
        
        return

    # =============================
    # GENERATION FORM (NO STORIES)
    # =============================
    
    # Auto-regenerate trigger: If auto_regenerate flag is set, show form and auto-submit
    auto_regen_mode = st.session_state.get('auto_regenerate', False)
    
    # Show feedback indicator if regenerating
    if st.session_state.get('story_generation_feedback'):
        if auto_regen_mode:
            st.markdown("""
            <div style='background: #28a745; padding: 15px; border-radius: 8px; margin-bottom: 20px; color: white;'>
                <h4 style='color: white; margin: 0;'>⚡ Auto-Regenerating with Your Feedback...</h4>
                <p style='margin: 5px 0 0 0;'>Story generation will start automatically in a moment. Please wait.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("🔄 **Regenerating with Feedback:** Your previous feedback is being used to improve story quality.")
        with st.expander("View Active Feedback"):
            st.write(st.session_state['story_generation_feedback'])
    
    st.markdown("### JIRA Configuration")
    st.caption("Configure JIRA settings first – applied to all generated stories.")
    c_proj, c_feat = st.columns(2)
    with c_proj:
        if st.session_state.get('available_projects'):
            projects = st.session_state.available_projects
            ct = [p for p in projects if 'CT' in p['key']]
            others = [p for p in projects if p not in ct]
            ordered = ct + others
            opts = [f"{p['key']} - {p['name']}" for p in ordered]
            default_key = st.session_state.get('default_jira_project', 'CT')
            default_index = next(
                (i for i, p in enumerate(ordered) if p['key'] == default_key), 0
            )
            selection = st.selectbox(
                "JIRA Project:", opts, index=default_index, help="Target project"
            )
            jira_project = selection.split(' - ')[0]
        else:
            jira_project = st.text_input(
                "JIRA Project Key:",
                value=st.session_state.get('default_jira_project', 'CT'),
                placeholder="e.g., CT, PROJ, DEV",
            )
            st.info("Login to load project dropdown")
    with c_feat:
        feature_epic_input = st.text_input(
            "Feature Key (manual entry)",
            value=st.session_state.get('default_feature_epic', ''),
            placeholder="e.g., CT-12345",
            help="Enter the Feature issue key directly. Autocomplete removed per request. (Epics not referenced here)"
        )
        if feature_epic_input and feature_epic_input.strip():
            st.session_state.default_feature_epic = feature_epic_input.strip().upper()
        feature_epic = st.session_state.get('default_feature_epic', '')

    # Global labels input (applies to all newly generated stories and used as default)
    import re as _re_glbl

    def _parse_labels(raw_text: str) -> list[str]:
        """Parse a raw labels string into a list of sanitized, de-duplicated labels.

        Rules:
        - Split on commas or any whitespace.
        - Allow only A-Za-z0-9_-
        - Trim to 255 chars (Jira label len safety)
        - Case-insensitive de-duplication preserving first occurrence's casing
        """
        if not raw_text:
            return []
        parts = _re_glbl.split(r'[\s,]+', raw_text) if hasattr(_re_glbl, 'split') else []  # fallback guard
        cleaned = []
        seen_lower = set()
        for p in parts:
            p = (p or '').strip()
            if not p:
                continue
            safe = _re_glbl.sub(r'[^A-Za-z0-9_-]', '', p)[:255]
            low = safe.lower()
            if safe and low not in seen_lower:
                seen_lower.add(low)
                cleaned.append(safe)
        return cleaned

    global_labels_raw = st.text_input(
        "Global Labels (optional, comma/space separated)",
        value=st.session_state.get('global_labels_raw', ''),
        help="Enter multiple labels separated by comma or spaces. Each individual label must not contain spaces (use hyphen_or_underscore). These labels will be pre-applied to every generated story."
    )
    parsed_global = _parse_labels(global_labels_raw)
    st.session_state.global_labels = parsed_global
    st.session_state.global_labels_raw = global_labels_raw
    if parsed_global:
        st.caption(f"Global labels active: {', '.join(parsed_global)}")
    else:
        st.caption("No global labels set.")

    # Persist preferences (normalized indentation)
    if jira_project:
        st.session_state.default_jira_project = jira_project
    if feature_epic:
        st.session_state.default_feature_epic = feature_epic

    # CT project: provide suggested values but allow user to choose / override
    try:
        if jira_project and jira_project.upper() == 'CT':
            import jiraUtils as _ju
            if 'ct_project_metadata' not in st.session_state:
                ok, err, meta = _ju.get_ct_project_metadata('CT')
                if ok and meta:
                    st.session_state.ct_project_metadata = meta
                else:
                    st.session_state.ct_project_metadata_error = err or 'Unknown error fetching CT metadata'
            meta = st.session_state.get('ct_project_metadata') or {}
            # Fetch full allowed option lists (createmeta) – more reliable than sampling issues
            if 'ct_allowed_values' not in st.session_state:
                ok_meta, err_meta, field_map = _ju.get_ct_field_allowed_values('CT', 'Story')
                if ok_meta:
                    st.session_state.ct_allowed_values = field_map
                else:
                    st.session_state.ct_allowed_values_error = err_meta
            allowed_map = st.session_state.get('ct_allowed_values', {})
            portfolios_full = allowed_map.get('customfield_10229') or []
            delivery_teams_full = allowed_map.get('customfield_10236') or []
            # Fallback enrichment with observed metadata & previous heuristic lists
            if not portfolios_full:
                okp, _, vals_issue = _ju.get_ct_portfolio_values('CT')
                if okp and vals_issue:
                    portfolios_full = vals_issue
            # Delivery teams enumeration retained internally but UI removed per requirement
            delivery_teams_full = []
            # Add any sampled current issue values to ensure they're present
            if meta.get('cust_Tech_Portfolio') and meta['cust_Tech_Portfolio'] not in portfolios_full:
                portfolios_full.append(meta['cust_Tech_Portfolio'])
            # Delivery team values no longer appended (UI removed)
            portfolios_full = sorted(set(portfolios_full))
            # Omit sorting for removed delivery teams list
            # Fetch full components list for project (cache per project to reduce calls)
            try:
                if 'project_components_cache' not in st.session_state:
                    st.session_state.project_components_cache = {}
                comp_cache = st.session_state.project_components_cache.get(jira_project)
                need_comp_refresh = True
                if comp_cache and (time.time() - comp_cache.get('fetched_at',0) < 600):  # 10 min TTL
                    need_comp_refresh = False
                if need_comp_refresh:
                    import jiraUtils as _ju_comp
                    base_url = os.getenv('JIRA_BASE_URL','')
                    full_components = []
                    if base_url:
                        try:
                            auth_key = _ju_comp.jira_authkey()
                            headers = { 'Authorization': 'Basic ' + auth_key, 'Content-Type': 'application/json' }
                            resp = requests.get(f"{base_url}project/{jira_project}/components", headers=headers, timeout=20, verify=False)
                            if resp.status_code == 200:
                                data = resp.json()
                                if isinstance(data, list):
                                    for c in data:
                                        nm = c.get('name')
                                        if nm:
                                            full_components.append(nm)
                            else:
                                logger.warning('Components fetch failed %s %s', resp.status_code, resp.text[:120])
                        except Exception as comp_ex:
                            logger.warning('Components fetch exception: %s', comp_ex)
                    # Fallback to any meta component + heuristics if API empty
                    if not full_components and meta.get('components'):
                        full_components = [meta.get('components')]
                    if not full_components:
                        full_components = ['Backend','Frontend','API']
                    st.session_state.project_components_cache[jira_project] = {
                        'fetched_at': time.time(),
                        'components': sorted(set(full_components))
                    }
                suggestions_components = st.session_state.project_components_cache[jira_project]['components']
            except Exception as comp_outer_ex:
                logger.warning('Components resolution outer exception: %s', comp_outer_ex)
                suggestions_components = sorted({m for m in [meta.get('components'), 'Backend', 'Frontend', 'API'] if m})
            with st.expander('CT Project Fields (select / confirm)', expanded=True):
                st.session_state.setdefault('ct_portfolio', meta.get('cust_Tech_Portfolio'))
                # st.session_state.setdefault('ct_delivery_teams_multi', [])  # removed
                st.session_state.setdefault('ct_components', meta.get('components'))
                st.session_state.ct_portfolio = st.selectbox(
                    'Customer Tech Portfolio', [''] + portfolios_full,
                    index=([''] + portfolios_full).index(st.session_state.ct_portfolio) if st.session_state.ct_portfolio in portfolios_full else 0,
                    help='Full option list sourced from JIRA create metadata')
                # Delivery Teams multiselect removed per user request
                st.session_state.ct_components = st.selectbox(
                    'Components', [''] + suggestions_components,
                    index=([''] + suggestions_components).index(st.session_state.ct_components) if st.session_state.ct_components in suggestions_components else 0
                )
                if st.button('Refresh Components', key='refresh_components_btn'):
                    st.session_state.project_components_cache.pop(jira_project, None)
                    st.experimental_rerun()
            if st.session_state.get('ct_project_metadata_error') and not meta:
                # Suppress noisy banner; keep silent log only
                try:
                    logger.warning("CT metadata suggestions limited (suppressed StoryCreation): %s", st.session_state.ct_project_metadata_error)
                except Exception:
                    pass
    except Exception as _ct_ex:
        st.info(f"CT metadata UI setup failed: {_ct_ex}")

    # Connection test UI removed

    st.markdown("### Describe Your Use Case")
    # Pre-fill with preserved use case text if regenerating with feedback
    default_use_case = st.session_state.get('raw_use_case_text', '')
    use_case_text = st.text_area(
        "Enter your use case or requirement:",
        value=default_use_case,
        height=150,
        placeholder=(
            "As a project manager, I need a dashboard that shows real-time status so I can identify bottlenecks."
        ),
    )
    # Persist raw user-entered description for export mapping
    if use_case_text:
        st.session_state['raw_use_case_text'] = use_case_text

    # Story count selection slider (user-configurable, max 15 stories)
    st.markdown("### 📊 Story Generation Settings")
    st.markdown("Select the number of stories you would like to generate:")
    
    # Initialize slider value in session state if not present
    if 'story_count_slider' not in st.session_state:
        st.session_state.story_count_slider = 5  # Default to 5 stories
    
    # Slider for story count (1-15)
    desired_story_count = st.slider(
        "Number of Stories to Generate",
        min_value=1,
        max_value=15,
        value=st.session_state.story_count_slider,
        help="Select how many user stories you want to generate (recommended: 3-8 stories for focused scope)",
        key="story_count_input"
    )
    
    # Update session state
    st.session_state.story_count_slider = desired_story_count
    
    # Display selected value with visual feedback
    if desired_story_count <= 3:
        st.caption(f"✅ **{desired_story_count} stor{'y' if desired_story_count == 1 else 'ies'}** - Focused scope (recommended for detailed work)")
    elif desired_story_count <= 8:
        st.caption(f"✅ **{desired_story_count} stories** - Balanced scope (recommended)")
    else:
        st.caption(f"⚠️ **{desired_story_count} stories** - Large scope (may require more refinement)")
    
    max_ac_per_story = 30    # slightly higher guidance threshold for AC richness
    maximize_mode = False    # Use specific count, not maximize mode
    st.session_state['desired_story_count'] = desired_story_count
    st.session_state['target_ac_per_story'] = max_ac_per_story
    st.session_state['maximize_mode'] = maximize_mode
    # Default enable ADF export & template v2 unless explicitly disabled earlier
    # Hard-force defaults: always enable ADF export and v3 template unless user explicitly chooses otherwise
    st.session_state.use_adf_export = True
    if 'force_v3_template' not in st.session_state:
        st.session_state.force_v3_template = True
    if st.session_state.get('force_v3_template'):
        st.session_state.use_adf_template_v3 = True
        st.session_state.use_adf_template_v2 = False

    # Template selection UI (radio) – Legacy / v2 / v3
    # Keep radio for visibility but lock selection to v3 when force flag active
    if st.session_state.get('force_v3_template'):
        st.caption("ADF Template Version: v3 (locked by system configuration)")
    else:
        templ_choice = st.radio(
            'ADF Template Version',
            options=['Legacy','v2','v3'],
            index=(2 if st.session_state.get('use_adf_template_v3') else (1 if st.session_state.get('use_adf_template_v2') else 0)),
            help='Choose formatting style for JIRA description: panels & lists vary by version.'
        )
        if templ_choice == 'Legacy':
            st.session_state.use_adf_template_v3 = False
            st.session_state.use_adf_template_v2 = False
        elif templ_choice == 'v2':
            st.session_state.use_adf_template_v3 = False
            st.session_state.use_adf_template_v2 = True
        else:  # v3
            st.session_state.use_adf_template_v3 = True
            st.session_state.use_adf_template_v2 = False
        st.caption(f"Current ADF template: {templ_choice}")

        # Cache / session reset utility
        with st.expander("Advanced: Reset StoryGen Session"):
            st.markdown("Use this to clear generated stories and re-apply forced v3 template settings if the description mapping seems stale.")
            if st.button("Clear StoryGen Cache & Reinitialize v3", type="secondary"):
                purge_keys = [k for k in st.session_state.keys() if k.startswith('generated_') or k.startswith('created_story_') or k in {
                    'generated_stories','story_workflow_data','workflow_table_cache','workflow_table_initialized','force_workflow_refresh'
                }]
                for pk in purge_keys:
                    st.session_state.pop(pk, None)
                # Re-assert v3 flags
                st.session_state.force_v3_template = True
                st.session_state.use_adf_export = True
                st.session_state.use_adf_template_v3 = True
                st.session_state.use_adf_template_v2 = False
                st.success("Session cache cleared. v3 template locked and export enabled.")

    # Confluence Page URL (Optional)
    st.markdown("### Confluence Page (Optional)")
    conf_col1, conf_col2 = st.columns([3,1])
    with conf_col1:
        confluence_url = st.text_input(
            "Confluence Page URL:",
            value=st.session_state.get('confluence_page_url', ''),
            placeholder="https://your-domain.atlassian.net/wiki/spaces/SPACE/pages/123456789/Page+Title",
            help="Provide a Confluence page to enrich story generation context"
        )
    with conf_col2:
        if st.button("Fetch Page", help="Retrieve page content and cache for generation"):
            if not confluence_url.strip():
                st.warning("Enter a URL first")
            else:
                with st.spinner("Fetching Confluence page..."):
                    ok, title, text, err = fetch_confluence_page_content(confluence_url.strip())
                if ok:
                    st.session_state['confluence_page_url'] = confluence_url.strip()
                    st.session_state['confluence_page_title'] = title
                    st.session_state['confluence_page_context'] = text
                    st.success(f"Fetched page: {title or 'Untitled'} (chars: {len(text)})")
                    st.caption(text[:240] + ('…' if len(text) > 240 else ''))
                else:
                    st.error(f"Failed: {err}")
    if st.session_state.get('confluence_page_context') and not st.session_state.get('confluence_page_url_shown'):
        st.info(f"Confluence context ready: {st.session_state.get('confluence_page_title','(no title)')}")
        st.session_state['confluence_page_url_shown'] = True

    # Moved Supporting Images heading to sit directly above uploader (was previously above Confluence section)
    st.markdown("### Supporting Images (Optional)")
    uploaded_files = st.file_uploader(
        "Upload wireframes, flowcharts, or process diagrams:",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    uploaded_images = []
    if uploaded_files:
        st.success(f"{len(uploaded_files)} image(s) uploaded")
        for f in uploaded_files:
            try:
                img = Image.open(f)
                st.image(img, caption=f"📋 {f.name}", use_column_width=True)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                uploaded_images.append({
                    'name': f.name,
                    'data': base64.b64encode(buf.getvalue()).decode(),
                })
            except Exception as e:
                st.error(f"Error processing {f.name}: {e}")
        
        # Store uploaded images in session state for regeneration feature
        st.session_state['uploaded_images_data'] = uploaded_images

    with st.expander("Tips for Better Results"):
        st.markdown(
            """
            **Multiple Stories:** Mention multiple roles, workflows, scenarios.
            **Images:** Wireframes / process diagrams enrich context.
            **Format:** "As a [user], I need [function] so that [benefit]".
            **JIRA:** Project & Feature/Epic applied to all generated stories.
            """
        )

    # Consolidated NFR story option
    include_nfr_story = st.checkbox(
        "Generate consolidated Non-Functional Quality story (single)",
        value=st.session_state.get('include_nfr_story', False),
        help="If selected, individual stories will exclude NFR sections and one final story will list cross-cutting NFR acceptance criteria."
    )
    st.session_state.include_nfr_story = include_nfr_story

    has_use_case = bool(use_case_text.strip())
    has_images = bool(uploaded_images)
    has_confluence = bool(st.session_state.get('confluence_page_context'))
    has_feature = bool(feature_epic and feature_epic.strip())
    disabled = not (has_feature and (has_use_case or has_images or has_confluence))
    if not has_feature:
        st.warning("Select a Feature/Epic before generating stories (mandatory).")
    
    # Check for auto-regeneration trigger
    auto_regen_trigger = st.session_state.get('auto_regenerate', False)
    
    # Show helpful message when in feedback regeneration mode
    button_label = "🔄 Generate Stories with Feedback" if st.session_state.get('story_generation_feedback') else "Generate Stories"
    
    if auto_regen_trigger and not disabled:
        st.warning("⚡ Auto-generating with feedback... Please wait.")
    elif st.session_state.get('story_generation_feedback') and not auto_regen_trigger:
        st.info("👇 Click the button below to generate improved stories using your feedback")

    # Manual button click or auto-trigger
    generate_clicked = st.button(button_label, type="primary", disabled=disabled)
    
    # IMPORTANT: Auto-trigger takes precedence
    should_generate = generate_clicked or (auto_regen_trigger and not disabled)
    
    # Process auto-regeneration or manual click
    if should_generate:
        # Clear auto_regenerate flag to prevent infinite loop
        if auto_regen_trigger:
            st.session_state.pop('auto_regenerate', None)
        if not has_feature:
            st.error("Feature/Epic selection is required.")
            st.stop()
        # Clear prior session data (but preserve feedback if in regeneration mode)
        preserve_feedback = st.session_state.get('story_generation_feedback')
        for key in [
            'generated_stories', 'story_workflow_data', 'workflow_table_cache',
            'workflow_table_initialized', 'force_workflow_refresh'
        ]:
            st.session_state.pop(key, None)
        for key in [k for k in st.session_state.keys() if k.startswith('created_story_')]:
            st.session_state.pop(key, None)
        # Restore feedback if it was present
        if preserve_feedback:
            st.session_state['story_generation_feedback'] = preserve_feedback

        # Build base content
        if has_use_case and has_images:
            processing_info = f"🤖 Generating from text + {len(uploaded_images)} image(s)..."
            base_content = use_case_text
        elif has_use_case:
            processing_info = "🤖 Generating from use case text..."
            base_content = use_case_text
        elif has_images:
            processing_info = f"🤖 Generating from {len(uploaded_images)} image(s)..."
            base_content = (
                "Please analyze the uploaded image(s) and generate comprehensive user stories based on the visual content."
            )
        else:
            # Only Confluence context
            processing_info = "🤖 Generating from Confluence page context..."
            base_content = "Context sourced from Confluence page only."

        # Append Confluence context if present
        if has_confluence:
            conf_title = st.session_state.get('confluence_page_title') or 'Confluence Page'
            conf_text = st.session_state.get('confluence_page_context', '')
            base_content += f"\n\n### Additional Confluence Context (Title: {conf_title})\n{conf_text}"

        content = base_content
        # Inject desired count hint directly before sending to model (central prompt builder handles parameter)
        if get_story_generation_prompt:
            st.session_state['desired_story_count'] = desired_story_count
            st.session_state['target_ac_per_story'] = max_ac_per_story
            st.session_state['maximize_mode'] = maximize_mode
        
        # Show generation parameters for transparency (debug info)
        with st.expander("⚙️ Generation Parameters (for verification)", expanded=False):
            st.json({
                "desired_story_count": desired_story_count,
                "target_ac_per_story": max_ac_per_story,
                "maximize_mode": maximize_mode,
                "include_nfr_story": st.session_state.get('include_nfr_story', False),
                "has_use_case_text": bool(use_case_text.strip()),
                "has_images": len(uploaded_images) if uploaded_images else 0,
                "has_confluence_context": bool(st.session_state.get('confluence_page_context')),
                "has_feedback": bool(st.session_state.get('story_generation_feedback'))
            })
        
        with st.spinner(processing_info):
            success, result = generate_story_with_gencore(content, uploaded_images)
        if not success:
            # Show enhanced diagnostics
            endpoint_used = st.session_state.get('storygen_endpoint_used')
            err_detail = st.session_state.get('storygen_last_error')
            diag_html = "<div style='border:1px solid #cc0000;padding:10px;border-radius:6px;background:#fff5f5;'>" \
                        "<strong>❌ Story generation failed.</strong><br/>" \
                        f"Last attempted endpoint: {endpoint_used or 'TST1 → PROD'}<br/>" \
                        f"Details: {err_detail or result}" \
                        "<br/>If this persists share this block with the app admin." \
                        "</div>"
            st.markdown(diag_html, unsafe_allow_html=True)
            return
        stories = parse_multiple_stories(result)
        # Retry logic: if we got significantly fewer stories than the slider requested, retry
        # CRITICAL FIX: Respect user's slider selection in retry logic
        success2 = False
        result2 = None
        target_count = st.session_state.get('desired_story_count', 5)
        # Only retry if we got less than 50% of requested count (or less than 2 stories when 3+ were requested)
        if target_count and len(stories) < max(2, target_count // 2):
            retry_hint = (
                result + f"\n\n<!-- CRITICAL: You generated {len(stories)} stories but the requirement is EXACTLY {target_count} stories. Please generate {target_count} distinct stories, each with '## Story N:' header. This is mandatory. -->"
            )
            with st.spinner(f"Retrying to reach target of {target_count} stories (currently have {len(stories)})..."):
                success2, result2 = generate_story_with_gencore(retry_hint, uploaded_images)
            if success2:
                retry_stories = parse_multiple_stories(result2)
                if len(retry_stories) > len(stories):
                    stories = retry_stories
                    if len(stories) == target_count:
                        st.success(f"✅ Retry successful: Generated exactly {len(stories)} stories as requested.")
                    else:
                        st.info(f"Retry produced {len(stories)} stories (target was {target_count}).")
                else:
                    st.warning(f"Retry did not yield more stories. Generated {len(stories)} of {target_count} requested.")

        # Extract & consolidate NFR lines if checkbox selected
        if st.session_state.get('include_nfr_story'):
            # 1. Extract any NFR subsections from individual stories (model may leak them)
            extracted_nfrs = []
            for idx, s in enumerate(stories):
                ac_text = s.get('acceptance_criteria') or ''
                # Detect '### Non-Functional Requirements' block
                if re.search(r'(?i)^###?\s*Non[- ]Functional\s+Requirements', ac_text, re.MULTILINE):
                    # Split on that header
                    parts = re.split(r'(?i)(^###?\s*Non[- ]Functional\s+Requirements.*?)$', ac_text, maxsplit=1, flags=re.MULTILINE)
                    if len(parts) >= 3:
                        before_nfr = parts[0].strip()
                        # Remainder after header
                        nfr_section = parts[2].strip()
                        # Extract bullet lines from NFR section (stop at next heading or end)
                        nfr_lines_raw = []
                        for line in nfr_section.split('\n'):
                            line_stripped = line.strip()
                            if line_stripped.startswith('#'):
                                break  # Another heading; stop
                            if line_stripped and (line_stripped.startswith('-') or line_stripped.startswith('•') or ':' in line_stripped):
                                # Strip leading bullet
                                clean_line = re.sub(r'^[-•]\s*', '', line_stripped).strip()
                                if clean_line:
                                    extracted_nfrs.append(f"(Story {idx+1}) {clean_line}")
                                    nfr_lines_raw.append(clean_line)
                        # Remove NFR section from original story AC
                        s['acceptance_criteria'] = before_nfr
            # 2. Check if consolidated NFR story already exists
            nfr_story_idx = None
            for idx, s in enumerate(stories):
                if re.search(r'(?i)(non[- ]functional|quality envelope)', s.get('title','')):
                    nfr_story_idx = idx
                    break
            # 3. If consolidated story exists, append extracted items; else create one
            if nfr_story_idx is not None:
                existing_ac = stories[nfr_story_idx].get('acceptance_criteria') or ''
                if extracted_nfrs:
                    stories[nfr_story_idx]['acceptance_criteria'] = existing_ac + '\n' + '\n'.join(extracted_nfrs)
            else:
                # No consolidated story; create one using extracted items
                if extracted_nfrs:
                    nfr_story = {
                        'title': 'Non-Functional Requirements (Consolidated)',
                        'description': 'Cross-cutting quality and operational requirements derived from the functional stories above.',
                        'acceptance_criteria': '\n'.join(extracted_nfrs),
                        'technical_notes': '',
                        'priority': 'Medium',
                        'epic': feature_epic or ''
                    }
                    stories.append(nfr_story)

        # Acceptance Criteria enrichment pipeline (heuristic + optional second pass + tagging)
        if maximize_mode and stories:
            # Initialize toggles if not present (non-UI defaults)
            st.session_state.setdefault('ac_auto_expand_enabled', True)
            st.session_state.setdefault('ac_second_pass_enabled', True)
            st.session_state.setdefault('ac_category_tagging_enabled', True)

            needs_second_pass = []
            for idx, s in enumerate(stories):
                ac_text = s.get('acceptance_criteria') or ''
                raw_lines = [ln for ln in ac_text.split('\n') if ln.strip() and not ln.strip().lower().startswith('###')]
                functional = [ln for ln in raw_lines if re.search(r'(?i)\b(given|when|then)\b', ln)]
                nfrs = [ln for ln in raw_lines if ln.lower().startswith('nfr:') or re.search(r'(?i)(performance|accessibility|security|reliability|observability)', ln)]
                approx_tokens = sum(len(ln) for ln in raw_lines) // 4  # character-based approximation
                low_functional = len(functional) < 8
                low_nfr = len(nfrs) < 2
                low_total = len(raw_lines) < 12
                low_tokens = approx_tokens < 180
                if low_functional or low_nfr or low_total or low_tokens:
                    needs_second_pass.append(idx)

            if needs_second_pass and st.session_state.get('ac_auto_expand_enabled'):
                if st.session_state.get('ac_second_pass_enabled'):
                    enriched_count = 0
                    for idx in needs_second_pass:
                        s = stories[idx]
                        ac_text = s.get('acceptance_criteria') or ''
                        enrichment_prompt = (
                            "Improve and expand the following acceptance criteria for a JIRA user story. "
                            "Provide a comprehensive bullet list (15-25 items if meaningful) covering: happy path, alternative flows, "
                            "invalid inputs, boundary values, authorization failures, concurrency/conflicts, resilience/timeouts, audit/logging, "
                            "data integrity (including rollback/compensation), localization (if relevant), performance (p95/p99 thresholds), "
                            "accessibility (WCAG 2.1 AA keyboard & screen reader), security (sanitization, authorization, OWASP concerns), privacy (PII), monitoring/metrics.\n\n"
                            "Return ONLY the improved acceptance criteria bullets in Markdown (no extra narrative).\n\n"
                            "Existing criteria:\n" + ac_text
                        )
                        with st.spinner(f"Expanding acceptance criteria for Story {idx+1}..."):
                            ok_enrich, enrich_out = generate_story_with_gencore(enrichment_prompt, None)
                        if ok_enrich and enrich_out:
                            cleaned = re.sub(r'^#+.*$', '', enrich_out, flags=re.MULTILINE).strip()
                            diversified = diversify_acceptance_criteria(
                                cleaned,
                                s.get('title',''),
                                s.get('description',''),
                                re.search(r'As a\s+([^,]+?)\s*,?\s*I want', s.get('description','')) and re.search(r'As a\s+([^,]+?)\s*,?\s*I want', s.get('description','')).group(1) or 'user',
                                re.search(r'I want\s+(.*?)\s+so that', s.get('description','')) and re.search(r'I want\s+(.*?)\s+so that', s.get('description','')).group(1) or 'capability'
                            )
                            s['acceptance_criteria'] = ensure_nfr_subsection_in_ac(diversified)
                            enriched_count += 1
                    if enriched_count:
                        st.info(f"Acceptance criteria auto-expanded for {enriched_count} stor{'y' if enriched_count==1 else 'ies'}.")
                else:
                    # Guidance only
                    for idx in needs_second_pass:
                        s = stories[idx]
                        ac_text = s.get('acceptance_criteria') or ''
                        guidance = (
                            ac_text.rstrip() + "\n\n(Expand further: add alternative paths, invalid inputs, boundary values, authorization denials, concurrency, resilience/timeouts, audit/logging, data integrity, localization, performance p95/p99, accessibility WCAG, security OWASP, privacy/PII, monitoring/metrics.)"
                        )
                        s['acceptance_criteria'] = guidance
                    st.info("Acceptance criteria guidance appended (second-pass expansion disabled).")

            # Category tagging
            if stories and st.session_state.get('ac_category_tagging_enabled'):
                tag_map = {
                    'concurrency': r'(?i)concurr|simultaneous|parallel',
                    'security': r'(?i)security|authorization|authenticat|owasp|csrf|xss|injection',
                    'performance': r'(?i)p95|p99|latency|response time|throughput',
                    'accessibility': r'(?i)wcag|screen reader|aria|keyboard',
                    'resilience': r'(?i)timeout|retry|failure|degrade',
                    'audit': r'(?i)audit|logging|log entry|trace',
                    'data_integrity': r'(?i)rollback|transaction|integrity|consisten',
                    'privacy': r'(?i)pii|personal data|gdpr',
                }
                for s in stories:
                    ac_text = s.get('acceptance_criteria') or ''
                    # Diversify existing criteria before tagging
                    ac_text = diversify_acceptance_criteria(
                        ac_text,
                        s.get('title',''),
                        s.get('description',''),
                        re.search(r'As a\s+([^,]+?)\s*,?\s*I want', s.get('description','')) and re.search(r'As a\s+([^,]+?)\s*,?\s*I want', s.get('description','')).group(1) or 'user',
                        re.search(r'I want\s+(.*?)\s+so that', s.get('description','')) and re.search(r'I want\s+(.*?)\s+so that', s.get('description','')).group(1) or 'capability'
                    )
                    ac_text = ensure_nfr_subsection_in_ac(ac_text)
                    lines = ac_text.split('\n')
                    tagged_lines = []
                    for ln in lines:
                        categories_hit = [tag for tag, pattern in tag_map.items() if re.search(pattern, ln)]
                        if categories_hit:
                            tag_label = ' [' + ', '.join(sorted(set(categories_hit))) + ']'
                            if tag_label not in ln:
                                ln = ln + tag_label
                        tagged_lines.append(ln)
                    s['acceptance_criteria'] = '\n'.join(tagged_lines)
        if not stories:
            st.error("❌ Failed to parse generated stories")
            return

        # Post-scrub any lingering Story Points lines in descriptions using helper
        for s in stories:
            s['description'] = strip_story_points_lines(s.get('description') or '')

        st.session_state.generated_stories = stories
        
        # Initialize generation version for unique widget keys
        if 'story_generation_version' not in st.session_state:
            st.session_state.story_generation_version = 0
        else:
            st.session_state.story_generation_version += 1
        
        if 'story_workflow_data' not in st.session_state:
            st.session_state.story_workflow_data = {}
        for i, s in enumerate(stories):
            key = f"story_{i+1}"
            if key not in st.session_state.story_workflow_data:
                s['jira_project'] = jira_project
                s['feature_epic'] = feature_epic
                st.session_state.story_workflow_data[key] = {
                    'jira_id': None,
                    'test_case_count': 0,
                    'test_jira_id': None,
                    'workflow_status': 'Generated',
                    'story_title': s.get('title', 'Untitled'),
                    'priority': s.get('priority', 'Medium'),
                    'story_points': '0',
                    'jira_project': jira_project,
                    'feature_epic': feature_epic,
                }
        plural2 = "story" if len(stories) == 1 else "stories"
        # Show success message with slider validation
        target_count = st.session_state.get('desired_story_count', 5)
        if len(stories) == target_count:
            st.success(
                f"✅ Generated exactly {len(stories)} {plural2} successfully (matched your slider selection) — review below."
            )
        elif len(stories) < target_count:
            st.warning(
                f"⚠️ Generated {len(stories)} {plural2} (you requested {target_count}). The AI may have consolidated some stories. Review and regenerate if needed."
            )
        else:
            st.info(
                f"ℹ️ Generated {len(stories)} {plural2} (you requested {target_count}). The AI found additional valuable story slices."
            )
        try:
            st.rerun()
        except Exception:
            try:
                st.experimental_rerun()
            except Exception:
                pass

    with st.expander("💡 Help & Tips", expanded=False):
        st.markdown(
            """
            **Better Input:** Provide context, constraints, roles, and success criteria.
            **Images:** Architecture + wireframes → richer technical & UI stories.
            **After Generation:** Edit each story; then export individually to JIRA.
            """
        )

"""StoryCreation module.

Provides `render_story_creation()` for use by `webwork.py`. Avoid executing Streamlit UI code
at import time to keep imports lightweight and prevent circular dependency / runtime side effects.
"""

if __name__ == "__main__":
    # Allow running this file directly for quick local debug.
    try:
        render_story_creation()
    except Exception as _run_ex:
        try:
            logger.error(f"StoryCreation standalone run failed: {_run_ex}")
        except Exception:
            pass
