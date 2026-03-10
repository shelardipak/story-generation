import streamlit as st
import jiraUtils as jiraUtils
import methodUtil as utils
from mLogin import login_ui, logout_ui
from generated_resBody import *
from modified_resBody import *
from logging_config import get_logger
import time
import urllib3
import base64
from pathlib import Path
from htbuilder import HtmlElement, div, br, hr, a, p, img, styles
from htbuilder.units import percent, px
from branding import BRAND_BURGUNDY, BRAND_GREEN, find_brand_logo_b64
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = get_logger(__name__)

generated_body = None
data = None
response = None


def image(src_as_string, **style):
    return img(src=src_as_string, style=styles(**style))


def link(link, text, **style):
    return a(_href=link, _target="_blank", style=styles(**style))(text)


def update_session_state(key, value):
    st.session_state[key] = value


def render_brand_header():
    """Render a Flamingo brand header with the provided logo image and title."""
    # Load the preferred brand logo (fallback to legacy if needed)
    logo_b64 = find_brand_logo_b64()
    # Burgundy block background with green accent for the title
    gradient = BRAND_BURGUNDY
    img_html = (
        f'<img src="data:image/png;base64,{logo_b64}" alt="M&G Brand" '
        'style="width:78px;height:78px;object-fit:cover;border-radius:12px;'
        'border:2px solid rgba(255,255,255,0.85);box-shadow:0 4px 12px rgba(0,0,0,0.25);"/>'
        if logo_b64
        else ""
    )

    # Flamingo icon with no background (moved to the end, size matched to logo ~78x78)
    flamingo_html = (
        '<div style="width:78px;height:78px;display:flex;align-items:center;justify-content:center;font-size:64px;line-height:1;">🦩</div>'
    )

    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:18px;background:{gradient};padding:18px 22px;border-radius:22px;margin-bottom:18px;box-shadow:0 6px 22px -4px rgba(0,0,0,0.28);">
            <div style="display:flex;align-items:center;gap:14px;">{img_html}</div>
            <div style="flex:1;">
                <h1 style="color:#ffffff;margin:0 0 4px 0;font-size:30px;font-weight:720;letter-spacing:.5px;">
                    Flamingo – <span style="color:{BRAND_GREEN}">AI in SDLC</span>
                </h1>
                <p style="color:#fff;margin:0;font-size:15px;font-weight:500;letter-spacing:.3px;opacity:.95;">M&amp;G plc</p>
            </div>
            <div>{flamingo_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def update_test_case_tracking(story_key, test_key):
    """Update workflow tracking when test cases are created for a story"""
    try:
        if 'story_workflow_data' not in st.session_state:
            st.session_state.story_workflow_data = {}
        
        # Find the corresponding story in workflow data
        story_found = False
        for workflow_key, workflow_data in st.session_state.story_workflow_data.items():
            if workflow_data.get('jira_id') == story_key:
                # Update test case information
                # Maintain a list of all created test keys
                test_list = workflow_data.get('test_jira_ids')
                if not isinstance(test_list, list):
                    test_list = []
                if test_key and test_key not in test_list:
                    test_list.append(test_key)
                workflow_data['test_jira_ids'] = test_list
                # Keep last created key for backward compatibility
                workflow_data['test_jira_id'] = test_key
                story_found = True
                break
        
        # If story not found in workflow data, it might be a standalone test creation
        if not story_found:
            logger.info(f"Test case {test_key} created for story {story_key} (not tracked in current workflow)")
        
        # Force refresh the workflow table
        if 'workflow_table_cache' in st.session_state:
            del st.session_state.workflow_table_cache
        st.session_state.force_workflow_refresh = True
        
        logger.info(f"Updated test case tracking for story {story_key} with test {test_key}")
        
    except Exception as e:
        logger.error(f"Error updating test case tracking: {str(e)}")

def update_test_generation_tracking(story_key, test_count):
    """Update workflow tracking when test cases are first generated (but not yet created in JIRA)"""
    try:
        if 'story_workflow_data' not in st.session_state:
            st.session_state.story_workflow_data = {}
        
        # Find the corresponding story in workflow data
        story_found = False
        for workflow_key, workflow_data in st.session_state.story_workflow_data.items():
            if workflow_data.get('jira_id') == story_key:
                # Update test generation status
                workflow_data['test_case_count'] = test_count  # This field controls "Generated" status
                story_found = True
                break
        
        # If story not found in workflow data, it might be a standalone test generation
        if not story_found:
            logger.info(f"Test cases generated for story {story_key} (not tracked in current workflow)")
        
        # Force refresh the workflow table
        if 'workflow_table_cache' in st.session_state:
            del st.session_state.workflow_table_cache
        st.session_state.force_workflow_refresh = True
        
        logger.info(f"Updated test generation tracking for story {story_key} with {test_count} test cases")
        
    except Exception as e:
        logger.error(f"Error updating test generation tracking: {str(e)}")


def layout(*args):
    style = """
    <style>
      # MainMenu {visibility: hidden;}
      footer {visibility: hidden;}
     .stApp { bottom: 105px; }
    </style>
    """

    style_div = styles(
        position="fixed",
        left=0,
        bottom=0,
        margin=px(0, 0, 0, 0),
        width=percent(100),
        color="black",
        text_align="center",
        height="auto",
        opacity=1
    )

    style_hr = styles(
        display="block",
        margin=px(8, 8, "auto", "auto"),
        border_style="inset",
        border_width=px(2)
    )

    body = p()
    foot = div(
        style=style_div
    )(
        hr(
            style=style_hr
        ),
        body
    )

    st.markdown(style, unsafe_allow_html=True)

    for arg in args:
        if isinstance(arg, str):
            body(arg)

        elif isinstance(arg, HtmlElement):
            body(arg)

    st.markdown(str(foot), unsafe_allow_html=True)


def footer():
    myArgs = [
        "Disclaimer: Our app aids in generating test cases, but it's not infallible. Users must review and validate these suggestions before implementing them into Jira. ",
        br(),
        " The responsibility for the final decision and any consequences lies solely with the user. By using this application, you accept these terms and understand that due diligence is required.",
        br(),
        " Reference ",
        link("https://mandg.atlassian.net/wiki/spaces/QT/pages/327123291/How+to+use+the+app+-+JiraTestGenAI",
             "@HowToUse")
    ]
    layout(*myArgs)


def login_page():
    st.set_page_config(page_title="Flamingo | M&G plc - AI in SDLC",
                       page_icon=":flamingo:",
                       initial_sidebar_state="expanded")

    render_brand_header()

    st.markdown(f"""
        <div style="background-color: {BRAND_BURGUNDY}; height: 2px;"></div>
        """, unsafe_allow_html=True)

    if st.session_state.get("authenticated", False):
        username = st.session_state.get("username")
        st.button("Login")
        st.write("Welcome 👋 " + st.session_state.get("display_name",""))
        try:
            response_code, accountId = jiraUtils.get_user_details(username)
        except Exception as cred_ex:
            st.error(f"JIRA credential error: {cred_ex}")
            response_code, accountId = 0, None
        if response_code == 200 and username:
            st.session_state['logged_in'] = True
            st.session_state['username'] = username
            st.session_state['accountId'] = accountId
            # Auto-load projects once per session
            if 'available_projects' not in st.session_state:
                try:
                    with st.spinner("Fetching JIRA projects..."):
                        st.session_state.available_projects = jiraUtils.get_available_projects()
                    if not st.session_state.available_projects:
                        diag = jiraUtils.jira_credentials_status()
                        st.warning("No projects returned. Verify permissions & credentials.")
                        with st.expander("Diagnostics", expanded=False):
                            st.json(diag)
                except Exception as proj_ex:
                    st.error(f"Failed to load projects: {proj_ex}")
        else:
            st.write("Login failed. Please try again.")
            login_ui()
    else:
        login_ui()


def main():
    logger.info("Inside main()")
    print("Inside main()")
    global response
    global generated_body
    global data
    st.set_page_config(page_title="Flamingo | M&G plc - AI in SDLC",
                       page_icon=":flamingo:",
                       initial_sidebar_state="expanded")

    render_brand_header()

    # Only create the radio in the sidebar, not in the main area
    if st.session_state['logged_in']:
        with st.sidebar:
            if st.button("Logout"):
                logout_ui()
                return
            with st.chat_message("user"):
                st.write(f"Hello 👋  {st.session_state['display_name']}")
            st.markdown(
                f'<div style="color: white; background-color: {BRAND_BURGUNDY}; padding: 1px; border-radius: 5px; cursor: pointer; margin-bottom: 10px;" title="Double click to logout"></div>',
                unsafe_allow_html=True
            )
            # Place radio selection here, just below green line
            # Reordered per request: show Story Creation first, then Test Cases Generator
            options = ["Story Creation", "Test Cases Generator"]
            # Single source of truth: main_tab. Derive radio default from it; do not pre-set tab_radio separately.
            current = st.session_state.get('main_tab')

            # Navigation triggers (one-shot)
            nav_trigger = False
            if st.session_state.get('navigate_to_tests') or st.session_state.get('pending_nav_to_tests'):
                current = "Test Cases Generator"
                nav_trigger = True
            query_params = st.query_params
            if query_params.get('navigate_to_tests') == 'true':
                current = "Test Cases Generator"
                nav_trigger = True
                story_identifier = query_params.get('story_identifier')
                if story_identifier:
                    st.session_state.target_story_key = story_identifier
                    st.session_state.auto_fill_story = True
                    st.session_state.auto_run_tests = True

            # Clear one-shot flags once captured
            if nav_trigger:
                for flag in ['navigate_to_tests', 'pending_nav_to_tests']:
                    st.session_state.pop(flag, None)

            # Determine index without mutating radio value afterward
            if current not in options:
                current = options[0]
            default_index = options.index(current)
            selected = st.radio("Select an option:", options, index=default_index, key="tab_radio")
            if nav_trigger:
                st.caption("<span style='background:#e7f5ff;color:#1864ab;padding:2px 8px;border-radius:12px;font-size:11px;'>auto-switch</span>", unsafe_allow_html=True)
            # Update main_tab only if changed
            if selected != st.session_state.get('main_tab'):
                st.session_state['main_tab'] = selected

    st.markdown(f"""
        <div style="background-color: {BRAND_BURGUNDY}; height: 2px;"></div>
        """, unsafe_allow_html=True)

    # Only show main area content if a selection is made
    if st.session_state.get('main_tab') == "Test Cases Generator":
        # Check for query parameters to handle navigation from story creation
        query_params = st.query_params
        if query_params.get('navigate_to_tests') == 'true':
            story_identifier = query_params.get('story_identifier')
            if story_identifier:
                st.session_state.target_story_key = story_identifier
                st.session_state.auto_fill_story = True
                # Leave params for a later clear once run is triggered
        
        # Check if coming from story creation with auto-fill
        auto_fill_value = ""
        if st.session_state.get('auto_fill_story') and st.session_state.get('target_story_key'):
            auto_fill_value = st.session_state.target_story_key
            st.session_state.auto_fill_story = False  # Reset flag
            st.info(f"🔗 Auto-filled with story: {auto_fill_value}")
        
        # Only show the input UI if Test Cases Generator is selected
        story_key_placeholder = st.empty()
        story_key = story_key_placeholder.text_input(
            "Enter JIRA Story Id 👇", 
            value=auto_fill_value,
            help="Enter the JIRA story key (e.g., CT-12345) to generate test cases"
        )
        # If input is still empty but we have a target story key in session, use it
        if not story_key and st.session_state.get('target_story_key'):
            story_key = st.session_state['target_story_key']
        
        cols = st.columns(2)
        with cols[0]:
            submit_button = st.button("Submit")
        with cols[1]:
            clear_button = st.button("Clear")
        
        # Bulk Test Case Creation removed as part of Export All deprecation

        # Initialize session state
        if 'user_input_list' not in st.session_state:
            st.session_state.user_input_list = []

        if "submit" not in st.session_state:
            st.session_state["submit"] = False

        if 'checkbox' not in st.session_state:
            st.session_state.checkbox = False

        if 'final_submit_clicked' not in st.session_state:
            st.session_state.final_submit_clicked = False

        if clear_button:
            st.session_state.user_input_list = []
            st.session_state.final_submit = False
            st.session_state.clear_button = False
            st.cache_data.clear()

        # Submit button
        # If auto-run flag is set (coming from StoryCreation), simulate a submit once
        if st.session_state.get('auto_run_tests') and (auto_fill_value or st.session_state.get('target_story_key')):
            # Auto-trigger submit and mark story key in list once
            logger.info("[AutoRun] Auto-submitting test generation for %s", st.session_state.get('target_story_key'))
            st.session_state['auto_run_tests'] = False
            if not story_key and st.session_state.get('target_story_key'):
                story_key = st.session_state['target_story_key']
            submit_button = True
            st.session_state['auto_submitted_tests'] = True

        # (Auto creation removed) — user must manually submit

        # Auto-run path: if flagged and not already processed, force submit logic
        if (st.session_state.get('auto_submitted_tests') and not st.session_state.get('submit')) and (auto_fill_value or st.session_state.get('target_story_key')):
            logger.info("[AutoRun] Forcing submit branch without user interaction")
            submit_button = True
            st.session_state['auto_submitted_tests'] = False  # consume flag

        if submit_button:
            if st.session_state.get("authenticated", True):
                if not story_key and st.session_state.get('target_story_key'):
                    story_key = st.session_state['target_story_key']
                if story_key:
                    story_key_placeholder.text_input("### Enter JIRA Story Key", value=story_key, key='story_key')
                    st.session_state.user_input_list.append({'text': story_key, 'accepted': None})
                st.session_state.submit = True
                st.session_state.final_submit = False
                st.session_state.clear_button = False
                st.session_state.final_submit_clicked = False
                logger.info("[Submit] Story key accepted for test generation: %s (auto=%s)", story_key, st.session_state.get('auto_create_tests'))
                # Clear query params after kickoff to avoid re-triggering on rerun
                try:
                    st.query_params.clear()
                except Exception:
                    pass

        if st.session_state["submit"] and not st.session_state.final_submit and not st.session_state.final_submit_clicked:

            st.write("Story Key submitted:", story_key)
            try:
                jira_response, project_identity = jiraUtils.description_extraction(story_key)

                logger.info("OpenAI response extraction success: %s", data)
            except Exception as e:
                print(f"Error occurred during data extraction: {e}")
                logger.error(f"Error occurred during data extraction: {e}")
                st.markdown("<h6>Wrong Story Key Entered. Please enter the correct Story Key</h6>", unsafe_allow_html=True)
                st.stop()

            try:
                data = utils.TestGenerationInProgress(story_key)
            except Exception as gen_ex:
                diag = str(gen_ex)
                # Build dynamic diagnostics referencing unified GPT-4o endpoints
                attempted_chain = "TST1 → dev1"
                last_endpoint = st.session_state.get('testgen_endpoint_used')
                last_error = st.session_state.get('testgen_last_error')
                extra_diag = ""
                if last_endpoint or last_error:
                    extra_diag = (
                        f"<br/><strong>Last Endpoint:</strong> {last_endpoint or 'N/A'}"
                        f"<br/><strong>Last Error:</strong> {last_error or 'N/A'}"
                    )
                err_html = f"""
                <div style='border:1px solid #c00;padding:10px;border-radius:6px;background:#fff5f5;'>
                    <strong>❌ Test generation failed.</strong><br/>
                    Story: {story_key}<br/>
                    <details style='margin-top:6px;'>
                        <summary style='cursor:pointer;'>Diagnostics (click to expand)</summary>
                        <code style='white-space:pre-wrap;font-size:12px;'>{diag[:1600]}</code>{extra_diag}
                    </details>
                    <em>Automatic fallback attempted across {attempted_chain}. Verify API keys (INT_DASHBOARD_GENCORE_KEY_TST / _DEV1), deployment access, and network connectivity.</em>
                </div>
                """
                st.markdown(err_html, unsafe_allow_html=True)
                st.session_state.auto_create_tests = False
                st.stop()

            # CT metadata (if project is CT based on story key) editable with suggestions
            try:
                if project_identity == 'CT':
                    import jiraUtils as _ju
                    if 'ct_project_metadata' not in st.session_state:
                        ok, err, meta = _ju.get_ct_project_metadata('CT')
                        if ok and meta:
                            st.session_state.ct_project_metadata = meta
                        else:
                            st.session_state.ct_project_metadata_error = err or 'Unknown metadata error'
                    meta = st.session_state.get('ct_project_metadata') or {}
                    # Fetch full option list via createmeta
                    if 'ct_allowed_values' not in st.session_state:
                        ok_meta, err_meta, field_map = _ju.get_ct_field_allowed_values('CT', 'Story')
                        if ok_meta:
                            st.session_state.ct_allowed_values = field_map
                        else:
                            st.session_state.ct_allowed_values_error = err_meta
                    allowed_map = st.session_state.get('ct_allowed_values', {})
                    portfolios_full = allowed_map.get('customfield_10229') or []
                    # delivery_teams_full removed per requirement (no Delivery Teams needed)
                    delivery_teams_full = []
                    # Fallback to issue sampling if createmeta incomplete
                    if not portfolios_full:
                        okp, _, vals_issue = _ju.get_ct_portfolio_values('CT')
                        if okp and vals_issue:
                            portfolios_full = vals_issue
                    # Delivery teams enumeration removed
                    if meta.get('cust_Tech_Portfolio') and meta['cust_Tech_Portfolio'] not in portfolios_full:
                        portfolios_full.append(meta['cust_Tech_Portfolio'])
                    # Do not append delivery teams
                    portfolios_full = sorted(set(portfolios_full))
                    # delivery_teams_full sorting skipped
                    suggestions_components = sorted({m for m in [meta.get('components'), 'Backend', 'Frontend', 'API'] if m})
                    with st.expander('CT Project Fields (select / confirm)', expanded=True):
                        st.session_state.setdefault('ct_portfolio', meta.get('cust_Tech_Portfolio'))
                        # st.session_state.setdefault('ct_delivery_teams_multi', [])  # removed
                        st.session_state.setdefault('ct_components', meta.get('components'))
                        st.session_state.ct_portfolio = st.selectbox('Customer Tech Portfolio', [''] + portfolios_full, index=([''] + portfolios_full).index(st.session_state.ct_portfolio) if st.session_state.ct_portfolio in portfolios_full else 0)
                        # Delivery Teams multiselect removed per user request
                        st.session_state.ct_components = st.selectbox('Components', [''] + suggestions_components, index=([''] + suggestions_components).index(st.session_state.ct_components) if st.session_state.ct_components in suggestions_components else 0)
                    if st.session_state.get('ct_project_metadata_error') and not meta:
                        # Suppress noisy banner: log silently, continue with empty/default suggestions
                        logger.warning("CT metadata suggestions limited (suppressed): %s", st.session_state.ct_project_metadata_error)
            except Exception as _ct_ex:
                st.info(f"CT metadata UI setup failed: {_ct_ex}")

            generated_body = Generated_resBody_ai(data)
            print("Test cases parsed success: ")
            logger.info("Test cases parsed success: ")

            update_test_generation_tracking(story_key, len(generated_body.test_cases) if hasattr(generated_body, 'test_cases') else 0)
            # Manual path continues to render form for review & selective acceptance

            try:
                st.markdown("<h5>Test Cases generated:</h5>", unsafe_allow_html=True)

                with st.form(key='my_form'):
                    with st.sidebar:
                        st.markdown("## Test attributes")
                        if project_identity == 'CT':
                            st.write("Project Key:", jira_response.project_key)
                            st.write("Project Name:", jira_response.project_name)
                            st.write("Customer Tech Portfolio:", jira_response.cust_Tech_Portfolio)
                            st.write("Customer Tech Delivery Teams:", jira_response.CustTechDeliveryTeams)
                            st.write("Fix Version:", jira_response.fix_version)
                            st.write("Affects Version:", jira_response.affects_version)
                            st.write("Labels:", "IntDashboardAI")
                        else:
                            st.write("Project Key :", jira_response.project_key)
                            st.write("Project Name :", jira_response.project_name)
                            st.write("Delivery Teams :", jira_response.deliveryTeam)
                            st.write("Components :", jira_response.components)
                            st.write("Labels:", "IntDashboardAI")

                    for idx, test_case in enumerate(generated_body.test_cases):
                        st.write("Test case: ", idx + 1)

                        for key, value in {
                            f'Summary{idx + 1}': test_case.test_summary,
                            f'Description{idx + 1}': test_case.test_description
                        }.items():
                            st.session_state.setdefault(key, value)
                            st.text_area(key.split(str(idx + 1))[0], value=st.session_state[key], key=key,
                                         height=50 if 'Summary' in key else 150)

                        for detail_idx, detail in enumerate(test_case.test_details):
                            cols = st.columns(3)

                            for key, value in {
                                f'TestStep{idx + 1}_{detail_idx + 1}': detail.test_step,
                                f'TestPrerequisite{idx + 1}_{detail_idx + 1}': detail.test_prerequisite,
                                f'ExpectedResult{idx + 1}_{detail_idx + 1}': detail.expected_result
                            }.items():
                                st.session_state.setdefault(key, value)
                                cols[0 if 'Step' in key else 1 if 'Prerequisite' in key else 2].text_area(
                                    key.split(str(idx + 1))[0],
                                    value=st.session_state[key],
                                    key=key,
                                    height=50
                                )
                        # checkbox
                        st.session_state.setdefault(f'Accept{idx + 1}', False)
                        st.session_state[f'Accept{idx + 1}'] = st.checkbox(f'Accept Test Case {idx + 1}',
                                                                           value=st.session_state[f'Accept{idx + 1}'])
                        st.write("Accept Test Case", idx + 1, ":", st.session_state[f'Accept{idx + 1}'])

                    # Adding the final submit button
                    if st.form_submit_button('Final Submit'):
                        st.session_state.final_submit_clicked = True
                        print("Final Button hit---------------")
                        logger.info("Final Button hit---------------")
                        st.session_state.text_show = "Test case creation in progress..."
                        text_placeholder = st.empty()
                        text_placeholder.info(st.session_state.text_show)
                        st.session_state.final_submit = True
                        st.session_state["submit"] = False

                        # Loop for each test case to create test case and test steps in jira
                        for idx, test_case in enumerate(generated_body.test_cases):
                            if st.session_state[f'Accept{idx + 1}']:
                                testID, testKey = jiraUtils.post_test_creation(
                                    st.session_state[f'Summary{idx + 1}'],
                                    st.session_state[f'Description{idx + 1}'],
                                    st.session_state['accountId'],
                                    st.session_state['username']
                                )
                                jiraUtils.post_test_addition_to_story(story_key, testKey)
                                time.sleep(10)
                                for detail_idx, detail in enumerate(test_case.test_details):
                                    jiraUtils.post_test_step(
                                        testID,
                                        st.session_state[f'TestStep{idx + 1}_{detail_idx + 1}'],
                                        st.session_state[f'TestPrerequisite{idx + 1}_{detail_idx + 1}'],
                                        st.session_state[f'ExpectedResult{idx + 1}_{detail_idx + 1}']
                                    )
                                st.write("Test case number ", idx + 1, " created successfully in Jira")
                                
                                # Update workflow tracking for this story
                                update_test_case_tracking(story_key, testKey)

                        st.session_state.text_show = ""
                        text_placeholder.write(st.session_state.text_show)
                        
                        # Show success message and link back to Story Creation
                        st.success("✅ Test cases created successfully in JIRA!")
                        st.info("🔄 Go back to the **Story Creation** tab to see the updated workflow table with test case status.")

                        # Delete the session state for the test case details
                        for idx in range(len(st.session_state.keys())):
                            if idx < len(generated_body.test_cases):
                                for key in ['Summary', 'Description', 'Decision', 'Accept']:
                                    st.session_state.pop(f'{key}{idx + 1}', None)
                                for detail_idx in range(len(generated_body.test_cases[idx].test_details)):
                                    for key in ['TestStep', 'TestPrerequisite', 'ExpectedResult']:
                                        st.session_state.pop(f'{key}{idx + 1}_{detail_idx + 1}', None)

            except Exception as e:
                print(f"Error occurred during test case display: {e}")
                logger.error(f"Error occurred during test case display: {e}")
    elif st.session_state['main_tab'] == "Story Creation":
        from StoryCreation import render_story_creation
        render_story_creation()
    # If no selection, main area is blank


if __name__ == "__main__":
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state['logged_in']:
        main()
    else:
        login_page()
        footer()
