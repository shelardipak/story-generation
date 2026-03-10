import json
import requests
from jiraStoryResBody import *
from logging_config import get_logger
import base64
import urllib3
import jira_zepher_auth as jwt_auth
import os
import re
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()
logger = get_logger(__name__)
story_response = None
project_identity = None
accountId = None
email_id = None

def extract_main_description(text):
    """Extract the main description part from the story text, excluding acceptance criteria and technical notes."""
    # Remove sections like Acceptance Criteria and Technical Notes if present
    text = re.sub(r'(?:Acceptance Criteria|AC):\s*(?:.*\n?)*?(?=\n\n|\n(?=[A-Z][^:\n]*:)|$)', '', text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r'(?:Technical Notes?|Implementation|Tech Notes?|Technical Implementation Notes?):\s*(?:.*\n?)*?(?=\n\n|\n(?=[A-Z][^:\n]*:)|$)', '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    # Clean up extra newlines and return the result
    return re.sub(r'\n{3,}', '\n\n', text).strip()

def extract_acceptance_criteria_jira(text):
    """Extract acceptance criteria from story text."""
    # Look for acceptance criteria sections
    patterns = [
        r'(?:Acceptance Criteria|AC):\s*((?:.*\n?)*?)(?:\n\n|\n(?=[A-Z][^:\n]*:)|$)',
        r'(?:Given|When|Then).*?(?=\n\n|\n(?=[A-Z][^:\n]*:)|$)',
    ]
    
    criteria = None
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            criteria = match.group(1 if len(match.groups()) > 0 else 0).strip()
            break
    
    # If criteria found, format each line as a bullet point if not already
    if criteria:
        formatted_criteria = []
        for line in criteria.split('\n'):
            line = line.strip()
            if line:
                if not line.startswith('•') and not line.startswith('-') and not line.startswith('*'):
                    line = '• ' + line
                formatted_criteria.append(line)
        return '\n'.join(formatted_criteria)
    
    # Default criteria if none found
    return """• Given I am a user with appropriate permissions
• When I access the feature
• Then I should be able to perform the required action
• And the system should respond appropriately"""

def extract_technical_notes_jira(text):
    """Extract technical implementation notes from story text."""
    # Look for technical sections
    patterns = [
        r'(?:Technical Notes?|Implementation|Technical Implementation Notes?):\s*((?:.*\n?)*?)(?:\n\n|\n(?=[A-Z][^:\n]*:)|$)',
        r'(?:Implementation Details?|Technical Details?):\s*((?:.*\n?)*?)(?:\n\n|\n(?=[A-Z][^:\n]*:)|$)',
    ]
    
    notes = None
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            notes = match.group(1).strip()
            break
    
    # If notes found, format each line as a bullet point if not already
    if notes:
        formatted_notes = []
        for line in notes.split('\n'):
            line = line.strip()
            if line:
                if not line.startswith('•') and not line.startswith('-') and not line.startswith('*'):
                    line = '• ' + line
                formatted_notes.append(line)
        return '\n'.join(formatted_notes)
    
    # Default technical notes if none found
    return """• Implementation should follow established design patterns and best practices
• Security considerations must be addressed including input validation and authorization
• Testing strategy should include unit tests, integration tests, and user acceptance testing
• Consider scalability requirements for future growth
• Ensure backward compatibility with existing systems"""


def jira_authkey():
        """Return base64 basic auth key for JIRA, with fallback env names.

        Primary env var names (new convention):
            INT_DASHBOARD_JIRA_USERNAME, INT_DASHBOARD_JIRA_AUTH
        Fallback legacy names:
            JIRA_USERNAME, JIRA_AUTH

        Returns:
            str: base64 encoded auth key or raises ValueError if missing.
        """
        username = os.getenv("INT_DASHBOARD_JIRA_USERNAME") or os.getenv("JIRA_USERNAME")
        api_token = os.getenv("INT_DASHBOARD_JIRA_AUTH") or os.getenv("JIRA_AUTH")
        if not username or not api_token:
                logger.error("JIRA credentials missing (username/api token). Ensure env vars are set.")
                raise ValueError("Missing JIRA credentials (INT_DASHBOARD_JIRA_USERNAME/JIRA_USERNAME or INT_DASHBOARD_JIRA_AUTH/JIRA_AUTH)")
        os.environ['NO_PROXY'] = 'mandg.atlassian.net'
        raw_key = f"{username}:{api_token}"
        auth_key = base64.b64encode(raw_key.encode('utf-8')).decode('utf-8')
        return auth_key

def jira_credentials_status():
        """Diagnostic helper to report which env variables are present (without exposing secrets)."""
        vars_present = {
                'INT_DASHBOARD_JIRA_USERNAME': bool(os.getenv('INT_DASHBOARD_JIRA_USERNAME')),
                'INT_DASHBOARD_JIRA_AUTH': bool(os.getenv('INT_DASHBOARD_JIRA_AUTH')),
                'JIRA_USERNAME (fallback)': bool(os.getenv('JIRA_USERNAME')),
                'JIRA_AUTH (fallback)': bool(os.getenv('JIRA_AUTH')),
        }
        return vars_present

# ---------------------------------------------------------------------------
# JIRA Search Helper with Deprecated Endpoint Fallback
# ---------------------------------------------------------------------------
def _jira_search(jql: str, fields=None, max_results: int = 50, start_at: int = 0, timeout: int = 25):
    """Perform a JIRA JQL search using legacy GET pattern first, then fall back to /search/jql if deprecated.

    Args:
        jql (str): JQL query (unescaped).
        fields (list[str]|None): Field names to request.
        max_results (int): Max results.
        start_at (int): Pagination offset.
        timeout (int): Request timeout seconds.

    Returns:
        (success: bool, status_code: int, json_or_error: dict|str)
    """
    base = os.getenv("JIRA_BASE_URL", "")
    if not base:
        return False, 0, "Missing JIRA_BASE_URL"
    auth_key = jira_authkey()
    headers = {
        'Authorization': 'Basic ' + auth_key,
        'Content-Type': 'application/json'
    }

    # --- Attempt legacy GET style (may be removed resulting in 410) ---
    try:
        field_param = ''
        if fields:
            if isinstance(fields, (list, tuple)):
                field_param = '&fields=' + ','.join(fields)
            else:
                field_param = '&fields=' + str(fields)
        legacy_url = f"{base}search?jql={requests.utils.quote(jql)}&maxResults={max_results}&startAt={start_at}{field_param}"
        resp = requests.get(legacy_url, headers=headers, timeout=timeout, verify=False)
        if resp.status_code == 200:
            try:
                return True, resp.status_code, resp.json()
            except Exception as je:
                return False, resp.status_code, f"Invalid JSON from legacy search: {je}"
        # If 410 (Gone) or explicit deprecation text, fall through to new endpoint
        body_text = resp.text[:500]
        if resp.status_code == 410 or 'has been removed' in body_text:
            logger.info("Legacy JIRA search endpoint deprecated (status %s); switching to /search/jql", resp.status_code)
        else:
            # Non-success that isn't deprecation, return early
            return False, resp.status_code, f"Legacy search failed {resp.status_code}: {body_text}"
    except Exception as e:
        logger.warning("Legacy search exception: %s", e)

    # --- Fallback: /search/jql (POST) ---
    try:
        fallback_url = f"{base}search/jql"
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
        }
        if fields:
            payload["fields"] = list(fields) if isinstance(fields, (list, tuple)) else [fields]
        resp2 = requests.post(fallback_url, headers=headers, json=payload, timeout=timeout, verify=False)
        if resp2.status_code == 200:
            try:
                return True, resp2.status_code, resp2.json()
            except Exception as je:
                return False, resp2.status_code, f"Invalid JSON from new search endpoint: {je}"
        return False, resp2.status_code, f"/search/jql failed {resp2.status_code}: {resp2.text[:500]}"
    except Exception as e:
        return False, 0, f"Fallback search exception: {e}"


def description_extraction(story_key):
    global story_response
    global project_identity
    print("Inside jira test description extraction - before call")
    logger.info("Inside jira test description extraction - before call")
    # Classify project by key prefix (CT, CTR, etc.)
    try:
        identity = story_key.split('-', 1)[0].strip().upper()
    except Exception:
        identity = 'INV'
    if identity == 'CT':
        project_identity = 'CT'
    elif identity == 'CTR':
        project_identity = 'CTR'
    else:
        project_identity = 'INV'
    print("Project identity: ", project_identity)
    logger.info("Project identity: %s", project_identity)
    url = os.getenv("JIRA_BASE_URL") + "issue" + f'/{story_key}'
    auth_key = jira_authkey()
    headers = {
        'Authorization': 'Basic ' + auth_key,
        'Content-Type': 'application/json'
    }
    response = requests.get(url, headers=headers, verify=False)

    response_code = response.status_code
    response_body = response.json()
    print('DescriptionExtraction URL : ', url)
    logger.info("DescriptionExtraction URL : %s", url)
    print('DescriptionExtraction headers : ', headers)
    logger.info("DescriptionExtraction headers : %s", headers)
    print("DescriptionExtraction Response code: ", response.status_code)
    logger.info("DescriptionExtraction Response code: %s", response.status_code)

    assert response_code == 200
    print("JIRA DescriptionExtraction get call success")
    logger.info("JIRA DescriptionExtraction get call success")
    try:
        story_response = JiraStory_ResBody(response_body)
        print("JIRA get response assign success")
        logger.info("JIRA get response assign success")
    except Exception as e:
        print(f"Error occurred during story_response assign: {e}")
        logger.error("Error occurred during story_response assign: %s", e)

    return story_response, project_identity


# This method will bring user details from JIRA
def get_user_details(e_id):
    global accountId
    global email_id
    print("Inside jira user details extraction - before call")
    logger.info("Inside jira user details extraction - before call")
    email_id = e_id
    url = format(os.getenv("JIRA_BASE_URL")) + "user/search?query=" + email_id
    auth_key = jira_authkey()
    headers = {
        'Authorization': 'Basic ' + auth_key,
        'Content-Type': 'application/json'
    }
    response = requests.get(url, headers=headers, verify=False)
    response_code = response.status_code

    if response_code == 200:
        try:
            response_body = response.json()
            if response_body and len(response_body) > 0:
                accountId = response_body[0]['accountId']
            else:
                print("Warning: Empty response or no user data found")
                logger.warning("Empty response or no user data found: %s", response_body)
                accountId = "default_account_id"  # Provide a default value
        except json.JSONDecodeError as e:
            print(f"Invalid JSON response: {e}")
            logger.error("Invalid JSON response: %s", e)
            accountId = "default_account_id"  # Provide a default value
        except (IndexError, KeyError) as e:
            print(f"Error extracting accountId: {e}, Response: {response_body}")
            logger.error("Error extracting accountId: %s, Response: %s", e, response_body)
            accountId = "default_account_id"  # Provide a default value
    else:
        print(f"Error: received status code {response_code}")
        logger.error("Error: received status code %s", response_code)
        print(response.text)
        accountId = "default_account_id"  # Provide a default value

    print("Jira Account ID extracted success - after call")
    logger.info("Jira Account ID extracted success - after call")

    return response_code, accountId

def get_available_projects():
    """
    Get list of available JIRA projects for story creation
    
    Returns:
        list: List of dictionaries with project details [{'key': 'CT', 'name': 'Project Name', 'id': '12345'}]
    """
    try:
        print("Inside JIRA projects extraction - before call")
        logger.info("Inside JIRA projects extraction - before call")
        
        url = os.getenv("JIRA_BASE_URL") + "project"
        auth_key = jira_authkey()
        headers = {
            'Authorization': 'Basic ' + auth_key,
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=headers, verify=False)
        response_code = response.status_code
        
        print("getProjects Response code: ", response.status_code)
        logger.info("getProjects Response code: %s", response.status_code)
        
        if response_code == 200:
            response_body = response.json()
            projects = []
            
            for project in response_body:
                projects.append({
                    'key': project['key'],
                    'name': project['name'],
                    'id': project['id']
                })
            
            print(f"Projects extracted successfully: {len(projects)} projects found")
            logger.info(f"Projects extracted successfully: {len(projects)} projects found")
            
            return projects
        else:
            print(f"Error: received status code {response_code}")
            logger.error(f"Error: received status code {response_code}")
            return []
            
    except Exception as e:
        print(f"Error in projects extraction: {str(e)}")
        logger.error(f"Error in projects extraction: {str(e)}")
        return []


def get_ct_project_metadata(project_key: str = "CT"):
    """Fetch a single representative issue from the CT project to extract common custom field values.

    Strategy:
      - Use JQL to fetch the most recently updated issue in the project (maxResults=1) including needed fields.
      - Return a dict of extracted metadata (portfolio, delivery teams, components, delivery team field).
      - Cache not implemented here; caller can cache in st.session_state.
    """
    try:
        jql = f"project={project_key} ORDER BY updated DESC"
        field_list = [
            "customfield_10229",
            "customfield_10236",
            "customfield_10246",
            "components",
        ]
        ok, status, data = _jira_search(jql, fields=field_list, max_results=1)
        if not ok:
            return False, data, None
        issues = (data or {}).get('issues') or []
        if not issues:
            return False, "No issues found in project for metadata sampling", None
        f = issues[0].get('fields', {})
        meta = {
            'cust_Tech_Portfolio': (f.get('customfield_10229') or {}).get('value') if isinstance(f.get('customfield_10229'), dict) else None,
            'CustTechDeliveryTeams': (f.get('customfield_10236') or [{}])[0].get('value') if isinstance(f.get('customfield_10236'), list) and f.get('customfield_10236') else None,
            'deliveryTeam': (f.get('customfield_10246') or {}).get('value') if isinstance(f.get('customfield_10246'), dict) else None,
            'components': (f.get('components') or [{}])[0].get('name') if isinstance(f.get('components'), list) and f.get('components') else None,
        }
        return True, None, meta
    except Exception as e:
        logger.error("Error fetching CT metadata: %s", e)
        return False, str(e), None


def get_ct_portfolio_values(project_key: str = "CT", max_issues: int = 200):
    """Return distinct Customer Tech Portfolio values (customfield_10229) using paged JQL search.

    Uses unified _jira_search helper with automatic fallback to new /search/jql endpoint.
    Returns: (success: bool, error: str|None, values: list[str])
    """
    try:
        collected = set()
        fetched = 0
        batch = 100
        jql = f"project={project_key} AND customfield_10229 is not EMPTY ORDER BY updated DESC"
        while fetched < max_issues:
            ok, status, data = _jira_search(jql, fields=["customfield_10229"], max_results=batch, start_at=fetched)
            if not ok:
                return False, data, sorted(collected)
            issues = (data or {}).get('issues') or []
            if not issues:
                break
            for issue in issues:
                f = issue.get('fields', {})
                v = f.get('customfield_10229')
                if isinstance(v, dict):
                    val = v.get('value')
                    if val:
                        collected.add(val)
            fetched += len(issues)
            if len(issues) < batch:
                break
        return True, None, sorted(collected)
    except Exception as e:
        logger.error("Error fetching CT portfolio values: %s", e)
        return False, str(e), []


def get_ct_delivery_teams_values(project_key: str = "CT", max_issues: int = 200):
    """Return distinct Customer Tech Delivery Teams values (customfield_10236 multi-select)."""
    try:
        collected = set()
        fetched = 0
        batch = 100
        jql = f"project={project_key} AND customfield_10236 is not EMPTY ORDER BY updated DESC"
        while fetched < max_issues:
            ok, status, data = _jira_search(jql, fields=["customfield_10236"], max_results=batch, start_at=fetched)
            if not ok:
                return False, data, sorted(collected)
            issues = (data or {}).get('issues') or []
            if not issues:
                break
            for issue in issues:
                f = issue.get('fields', {})
                arr = f.get('customfield_10236')
                if isinstance(arr, list):
                    for entry in arr:
                        if isinstance(entry, dict):
                            val = entry.get('value')
                            if val:
                                collected.add(val)
            fetched += len(issues)
            if len(issues) < batch:
                break
        return True, None, sorted(collected)
    except Exception as e:
        logger.error("Error fetching CT delivery teams values: %s", e)
        return False, str(e), []


def get_ct_delivery_team_values(project_key: str = "CT", max_issues: int = 200):
    """Return distinct Delivery Team values (customfield_10246 single value)."""
    try:
        collected = set()
        fetched = 0
        batch = 100
        jql = f"project={project_key} AND customfield_10246 is not EMPTY ORDER BY updated DESC"
        while fetched < max_issues:
            ok, status, data = _jira_search(jql, fields=["customfield_10246"], max_results=batch, start_at=fetched)
            if not ok:
                return False, data, sorted(collected)
            issues = (data or {}).get('issues') or []
            if not issues:
                break
            for issue in issues:
                f = issue.get('fields', {})
                v = f.get('customfield_10246')
                if isinstance(v, dict):
                    val = v.get('value')
                    if val:
                        collected.add(val)
            fetched += len(issues)
            if len(issues) < batch:
                break
        return True, None, sorted(collected)
    except Exception as e:
        logger.error("Error fetching CT delivery team values: %s", e)
        return False, str(e), []


def get_ct_field_allowed_values(project_key: str = "CT", issue_type_name: str = "Story"):
    """Return full allowed option lists for CT custom fields via Create Meta.

    This fetches the create meta for the specified project & issue type and extracts
    the complete option list (not just values already used in issues) for:
      - customfield_10229 (Customer Tech Portfolio)
      - customfield_10236 (Customer Tech Delivery Teams – multi-select)

    Returns: (success: bool, error: str|None, data: dict[str, list[str]])
        data example: { 'customfield_10229': ['CEO','COO',...], 'customfield_10236': ['Team A','Team B'] }
    """
    try:
        auth_key = jira_authkey()
        base = os.getenv("JIRA_BASE_URL", "")
        if not base:
            return False, "Missing JIRA_BASE_URL", {}
        # Endpoint: /rest/api/3/issue/createmeta
        # base already includes /rest/api/3/ per existing usage patterns (issue, search, etc.)
        url = (
            f"{base}issue/createmeta?projectKeys={project_key}"
            f"&issuetypeNames={requests.utils.quote(issue_type_name)}&expand=projects.issuetypes.fields"
        )
        headers = {
            'Authorization': 'Basic ' + auth_key,
            'Content-Type': 'application/json'
        }
        resp = requests.get(url, headers=headers, timeout=30, verify=False)
        if resp.status_code != 200:
            snippet = resp.text[:200].replace('\n', ' ')
            return False, f"createmeta failed {resp.status_code}: {snippet}", {}
        try:
            meta = resp.json()
        except Exception as je:
            return False, f"Invalid JSON from createmeta: {je}", {}
        projects = meta.get('projects') or []
        if not projects:
            return False, "No projects in createmeta response", {}
        issue_types = projects[0].get('issuetypes') or []
        target_type = None
        for it in issue_types:
            if it.get('name') == issue_type_name:
                target_type = it
                break
        if not target_type:
            return False, f"Issue type '{issue_type_name}' not found in createmeta", {}
        fields = target_type.get('fields') or {}
        results = {}
        for fid in ["customfield_10229", "customfield_10236"]:
            fmeta = fields.get(fid)
            allowed = []
            if isinstance(fmeta, dict):
                av = fmeta.get('allowedValues') or []
                for entry in av:
                    if isinstance(entry, dict):
                        val = entry.get('value')
                        if val:
                            allowed.append(val)
            if allowed:
                results[fid] = sorted(set(allowed))
        return True, None, results
    except Exception as e:
        logger.error("Error fetching CT field allowed values: %s", e)
        return False, str(e), {}


# This will be a post call to create test cases for story key entered by user
def post_test_creation(summary, description, account_id, email_id):
    global project_identity

    print("Project identity inside test creation: ", project_identity)
    logger.info("Project identity inside test creation: %s", project_identity)
    url = os.getenv("JIRA_BASE_URL") + "issue"

    Description_ADF = {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "text": description,
                        "type": "text"
                    }
                ]
            }
        ]
    }
    # Enforce standardized label for all created tests
    STANDARD_TEST_LABELS = ["JiraTestgenAI"]
    if project_identity == 'INV':
        payload = {
            "fields": {
                "project": {
                    "key": story_response.project_key,
                    "name": story_response.project_name
                },
                "summary": summary,
                "description": Description_ADF,
                "issuetype": {"name": "Test"},
                "customfield_10391": {"value": "Functional"},
                "customfield_10428": {
                    "value": "P1 (Must be executed)",
                    "id": "12651"},
                "components": [{"name": story_response.components}],
                "labels": STANDARD_TEST_LABELS
            }
        }
    elif project_identity == 'CTR':
        # Minimal payload for CTR: just submit the test case with inputs
        payload = {
            "fields": {
                "project": {
                    "key": story_response.project_key,
                    "name": story_response.project_name
                },
                "summary": summary,
                "description": Description_ADF,
                "issuetype": {"name": "Test"},
                "labels": STANDARD_TEST_LABELS
            }
        }
    else:
        # Build base fields
        fields = {
            "project": {
                "key": story_response.project_key,
                "name": story_response.project_name
            },
            "summary": summary,
            "description": Description_ADF,
            "issuetype": {"name": "Test"},
            "priority": {"name": "Trivial"},
            "labels": STANDARD_TEST_LABELS,
            "assignee": {"accountId": account_id},  # Jira Cloud v3: accountId only
        }

        # Optional fields only if values are present
        try:
            if getattr(story_response, 'fix_version', None):
                fields["fixVersions"] = [{"name": story_response.fix_version}]
            if getattr(story_response, 'affects_version', None):
                fields["versions"] = [{"name": story_response.affects_version}]
            if getattr(story_response, 'cust_Tech_Portfolio', None):
                fields["customfield_10229"] = {"value": story_response.cust_Tech_Portfolio}
            if getattr(story_response, 'CustTechDeliveryTeams', None):
                fields["customfield_10236"] = [{"value": story_response.CustTechDeliveryTeams}]
        except Exception:
            pass

        payload = {"fields": fields}

    auth_key = jira_authkey()
    headers = {
        'Authorization': 'Basic ' + auth_key,
        'Content-Type': 'application/json'
    }
    print('Inside jira test creation - before call')
    logger.info("Inside jira test creation - before call")
    print('postTestCreation URL : ', url)
    logger.info("postTestCreation URL : %s", url)
    print('postTestCreation headers : ', headers)
    logger.info("postTestCreation headers : %s", headers)
    print("postTestCreation payLoad : ", payload)
    logger.info("postTestCreation payLoad : %s", payload)

    response = requests.post(url, json=payload, headers=headers, verify=False)
    # print(f"Error: received status code {response_code}")
    print("postTestCreation response.text: ", response.text)
    logger.info("postTestCreation response.text: %s", response.text)

    print("postTestCreation Response code: ", response.status_code)
    logger.info("postTestCreation Response code: %s", response.status_code)
    response_code = response.status_code
    if response_code != 201:
        # Raise a descriptive error including server response
        try:
            err_text = response.text
        except Exception:
            err_text = ""
        raise Exception(f"JIRA Test creation failed ({response_code}): {err_text[:500]}")
    print("Test ID creation success ", response_code)
    logger.info("Test ID creation success %s", response_code)
    response_body = response.json()
    # getting test case id
    test_key_value = response_body['key']
    test_id = response_body['id']
    print("Test key created: ", test_key_value)
    logger.info("Test key created: %s", test_key_value)
    print("Test id created: ", test_id)
    logger.info("Test id created: %s", test_id)
    return test_id, test_key_value


# This will be a post call to add test steps for each test cases created
def post_test_step(Test_id, TestStep, TestPrerequisite, ExpectedResult):
    print("Inside jira test step addition - before call" + story_response.project_id)
    logger.info("Inside jira test step addition - before call %s", story_response.project_id)
    zepherAuth = jwt_auth.jwt_token(Test_id, story_response.project_id)
    url = os.getenv("ZEPHYR_BASE_URL") + "teststep/" + Test_id + "?projectId=" + story_response.project_id
    payload = {
        "step": TestStep,
        "data": TestPrerequisite,
        "result": ExpectedResult
    }
    headers = {
        'Authorization': 'JWT ' + zepherAuth,
        'Content-Type': 'application/json',
        'zapiAccessKey': os.getenv("INT_DASHBOARD_JIRA_ACCESS_KEY")
    }

    print('postTestStep URL : ', url)
    logger.info("postTestStep URL : %s", url)
    print('postTestStep headers : ', headers)
    logger.info("postTestStep headers : %s", headers)
    print("postTestStep payLoad : ", payload)
    logger.info("postTestStep payLoad : %s", payload)

    response = requests.post(url, json=payload, headers=headers, verify=False)

    print("postTestStep Response code: ", response.status_code)
    logger.info("postTestStep Response code: %s", response.status_code)
    assert response.status_code == 200
    print('Test step added success - after call: ', response.json())
    logger.info("Test step added success - after call: %s", response.json())


# This will be a post call to create JIRA user story
def post_story_creation(summary, description, project_key, project_name, account_id, email_id, epic_key=None, feature_key=None, story_points=None, priority="Medium", cust_tech_portfolio=None, cust_tech_delivery_teams=None, acceptance_criteria_text=None):
    """
    Create a new JIRA user story
    
    Args:
        summary (str): Story title/summary
        description (str): Story description (user story + context + technical notes)
        project_key (str): JIRA project key (e.g., 'CT', 'INV')
        project_name (str): JIRA project name
        account_id (str): Assignee account ID
        email_id (str): Assignee email
        epic_key (str, optional): Epic key to link the story to
        feature_key (str, optional): Feature key for "Is part of feature" link
        story_points (int, optional): Story points estimation
        priority (str): Priority level (Highest, High, Medium, Low, Lowest)
        cust_tech_portfolio (str, optional): Customer Tech Portfolio (required for CT projects)
        cust_tech_delivery_teams (str, optional): Customer Tech Delivery Teams (required for CT projects)
        acceptance_criteria_text (str, optional): Acceptance criteria to set in customfield_10381 after creation
    
    Returns:
        tuple: (story_id, story_key) if successful, (None, None) if failed
    """
    try:
        print("Inside JIRA story creation - before call")
        logger.info("Inside JIRA story creation - before call")
        
        url = os.getenv("JIRA_BASE_URL") + "issue"
        
        # Convert description to ADF format with proper sections
        if isinstance(description, str):
            # Extract sections from the description
            main_description = extract_main_description(description)
            acceptance_criteria = extract_acceptance_criteria_jira(description)
            technical_notes = extract_technical_notes_jira(description)
            
            # Create formatted ADF content with sections
            content_blocks = []
            
            # Title as heading
            content_blocks.append({
                "type": "heading",
                "attrs": {"level": 1},
                "content": [
                    {
                        "text": summary,
                        "type": "text"
                    }
                ]
            })
            
            # Add Priority
            content_blocks.append({
                "type": "paragraph",
                "content": [
                    {
                        "text": "Priority: ",
                        "type": "text",
                        "marks": [{"type": "strong"}]
                    },
                    {
                        "text": priority,
                        "type": "text"
                    }
                ]
            })
            
            # Add spacing
            content_blocks.append({
                "type": "paragraph",
                "content": [{"text": "", "type": "text"}]
            })
            
            # Main description paragraph
            if main_description:
                content_blocks.append({
                    "type": "paragraph",
                    "content": [
                        {
                            "text": main_description,
                            "type": "text"
                        }
                    ]
                })
            
            # Add spacing
            content_blocks.append({
                "type": "paragraph",
                "content": [{"text": "", "type": "text"}]
            })
            
            # Technical Notes section with heading (AC goes to separate field)
            if technical_notes:
                content_blocks.append({
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [
                        {
                            "text": "Technical Notes",
                            "type": "text"
                        }
                    ]
                })
                
                # Technical notes content
                for line in technical_notes.split('\n'):
                    line = line.strip()
                    if line:
                        content_blocks.append({
                            "type": "paragraph",
                            "content": [{"text": line, "type": "text"}]
                        })
            
            description_adf = {
                "version": 1,
                "type": "doc",
                "content": content_blocks
            }
        else:
            description_adf = description

        # Build initial payload (attempt with Epic Link if provided)
        # Merge default label with any user-specified custom labels stored in session
        merged_labels = ["JiraStoryGenAI"]
        try:
            import streamlit as _st_lbl
            custom_labels = getattr(_st_lbl.session_state, 'custom_labels', []) or []
            for lbl in custom_labels:
                if isinstance(lbl, str) and lbl and lbl not in merged_labels:
                    merged_labels.append(lbl)
        except Exception:
            pass

        base_fields = {
            "project": {"key": project_key, "name": project_name},
            "summary": summary,
            "description": description_adf,
            "issuetype": {"name": "Story"},
            "priority": {"name": priority},
            "labels": merged_labels
        }

        if account_id and account_id != "default_account_id":
            base_fields["assignee"] = {"accountId": account_id, "emailAddress": email_id}

        # Intentionally DO NOT send epic/feature linkage on create to avoid screen configuration errors.
        # We'll link epic (parent) and feature after successful creation via update calls / issue links.

        # Project-specific customizations (Delivery Teams intentionally omitted per latest requirement)
        if project_key == 'CT':
            portfolio_value = cust_tech_portfolio if cust_tech_portfolio else "CEO"
            base_fields["customfield_10229"] = {"value": portfolio_value}
            # NOTE: User requested to omit Delivery Teams; if later required, restore:
            # if cust_tech_delivery_teams: ... (previous implementation)
        
        payload = {"fields": base_fields}
        
        # Note: Issue links cannot be created during issue creation
        # For CT projects, we'll attempt immediate post-creation linking
        # Skip story points for now as the field ID varies by project and screen configuration
        # This can be added manually in JIRA or configured separately
        
        # Attempt creation (with epic link if present). If it fails due to epic field not on screen, retry without and update later.

        auth_key = jira_authkey()
        headers = {
            'Authorization': 'Basic ' + auth_key,
            'Content-Type': 'application/json'
        }
        
        print('postStoryCreation URL : ', url)
        logger.info("postStoryCreation URL : %s", url)
        print('postStoryCreation headers : ', headers)
        logger.info("postStoryCreation headers : %s", headers)
        print("postStoryCreation payLoad : ", payload)
        logger.info("postStoryCreation payLoad : %s", payload)

        # Primary create attempt (no epic / feature linkage yet)
        response = requests.post(url, json=payload, headers=headers, verify=False)

        print("postStoryCreation response.text: ", response.text)
        logger.info("postStoryCreation response.text: %s", response.text)
        print("postStoryCreation Response code: ", response.status_code)
        logger.info("postStoryCreation Response code: %s", response.status_code)

        response_code = response.status_code
        
        # Helper closure to perform post-creation linking (epic & feature)
        def _post_creation_linking(story_key_created: str):
            # Epic linking (update after creation)
            if epic_key:
                update_url = os.getenv("JIRA_BASE_URL") + f"issue/{story_key_created}"
                epic_update_variants = [
                    {"fields": {"customfield_10014": epic_key}},  # Classic company-managed epic link
                    {"fields": {"parent": {"key": epic_key}}}      # Team-managed parent linkage
                ]
                for variant in epic_update_variants:
                    try:
                        r_upd = requests.put(update_url, json=variant, headers=headers, verify=False)
                        if r_upd.status_code == 204:
                            logger.info(f"Epic linkage succeeded using field(s): {list(variant['fields'].keys())}")
                            break
                        else:
                            logger.warning(f"Epic linkage attempt failed ({r_upd.status_code}): {r_upd.text[:300]}")
                    except Exception as e_upd:
                        logger.warning(f"Epic linkage exception: {e_upd}")
            # Feature linking via issue link types
            if feature_key:
                try:
                    dynamic_create_feature_link(story_key_created, feature_key)
                except Exception as e_link:
                    logger.warning(f"Feature linkage failed: {e_link}")

        if response_code == 201:
            print("Story creation success ", response_code)
            logger.info("Story creation success %s", response_code)
            response_body = response.json()
            
            # Getting story key and ID
            story_key = response_body['key']
            story_id = response_body['id']
            
            print("Story key created: ", story_key)
            logger.info("Story key created: %s", story_key)
            print("Story id created: ", story_id)
            logger.info("Story id created: %s", story_id)
            
            _post_creation_linking(story_key)
            
            # Update acceptance criteria field (customfield_10381) if provided
            if acceptance_criteria_text and acceptance_criteria_text.strip():
                try:
                    update_url = os.getenv("JIRA_BASE_URL") + f"issue/{story_key}"
                    update_payload = {
                        "fields": {
                            "customfield_10381": acceptance_criteria_text.strip()
                        }
                    }
                    update_response = requests.put(update_url, json=update_payload, headers=headers, verify=False)
                    if update_response.status_code in [200, 204]:
                        logger.info(f"Successfully updated acceptance criteria for {story_key}")
                        print(f"✓ Acceptance criteria updated for {story_key}")
                    else:
                        logger.warning(f"Failed to update acceptance criteria for {story_key}: {update_response.status_code} - {update_response.text}")
                        print(f"⚠ Could not update acceptance criteria field for {story_key}")
                except Exception as ac_ex:
                    logger.warning(f"Exception updating acceptance criteria for {story_key}: {ac_ex}")

            # Optional post-create ADF panel reinforcement: if description was dict and contains panels we skip.
            try:
                if isinstance(description, dict):
                    # Already ADF. Optionally validate presence of panels.
                    pass
                else:
                    # If legacy markdown used, we can push a minimal diagnostic panel update (disabled by default).
                    if os.getenv('ENABLE_POST_CREATE_ADF_UPDATE','false').lower() == 'true':
                        update_simple_panel_adf(story_key)
            except Exception as _adf_upd_ex:
                logger.warning(f"Post-create ADF update skipped: {_adf_upd_ex}")
            
            return story_id, story_key
        else:
            error_message = f"Story creation failed with status code: {response_code}"
            if response.text:
                try:
                    error_details = response.json()
                    if 'errors' in error_details:
                        error_message += f" - Errors: {error_details['errors']}"
                    if 'errorMessages' in error_details:
                        error_message += f" - Messages: {error_details['errorMessages']}"
                except:
                    error_message += f" - Response: {response.text[:500]}"
            
            print(error_message)
            logger.error(error_message)
            return None, None
            
    except Exception as e:
        error_message = f"Error in story creation: {str(e)}"
        print(error_message)
        logger.error(error_message)
        return None, None

def update_story_description_adf(issue_key: str, adf_doc: dict) -> bool:
    """PUT an updated ADF description for an existing issue.

    Returns True if update succeeded, False otherwise.
    """
    try:
        auth_key = jira_authkey()
        headers = {'Authorization': 'Basic ' + auth_key, 'Content-Type': 'application/json'}
        url = os.getenv('JIRA_BASE_URL') + f'issue/{issue_key}'
        payload = {"fields": {"description": adf_doc}}
        resp = requests.put(url, json=payload, headers=headers, verify=False)
        if resp.status_code == 204:
            logger.info(f"ADF description updated for {issue_key}")
            return True
        else:
            logger.warning(f"ADF update failed ({resp.status_code}): {resp.text[:300]}")
            return False
    except Exception as ex:
        logger.error(f"ADF update exception: {ex}")
        return False

def build_minimal_panel_adf(title: str, sections: dict) -> dict:
    """Build a minimal panel-based ADF doc for diagnostics.

    sections: mapping heading -> list[str] bullets.
    """
    doc = {"type": "doc", "version": 1, "content": []}
    # Title
    doc["content"].append({"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": title}]})
    for heading, items in sections.items():
        panel_type = 'info'
        if heading.lower().startswith('acceptance'): panel_type = 'success'
        panel_node = {
            "type": "panel",
            "attrs": {"panelType": panel_type},
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": heading, "marks": [{"type": "strong"}]}]},
                {"type": "bulletList", "content": [
                    {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": itm}]}]} for itm in items
                ]} if items else {"type": "paragraph", "content": []}
            ]
        }
        doc["content"].append(panel_node)
    return doc

def update_simple_panel_adf(issue_key: str):
    """Convenience: build and apply a minimal panel ADF to existing issue for testing panel rendering."""
    test_doc = build_minimal_panel_adf(
        "User Story Template",
        {
            "User Story": ["As a user", "I want X", "So that Y"],
            "Requirements": ["Requirement 1", "Requirement 2"],
            "Non-Functional Requirements": ["Performance p95 < 2s", "Security OWASP mitigated"],
            "Additional Information": ["Scope: initial"],
            "Acceptance Criteria": ["Given condition", "When action", "Then outcome"]
        }
    )
    update_story_description_adf(issue_key, test_doc)

def create_feature_link(story_key, feature_key):
    """
    Create an 'Is part of feature' link between a story and feature
    
    Args:
        story_key (str): The story key (e.g., 'CT-12345')
        feature_key (str): The feature key (e.g., 'CT-184664')
    """
    try:
        url = os.getenv("JIRA_BASE_URL") + "issueLink"
        
        # Try different link type names that might work for "Is part of feature"
        payload = {
            "type": {
                "name": "Is part of feature"  # Try exact name first
            },
            "inwardIssue": {
                "key": feature_key
            },
            "outwardIssue": {
                "key": story_key
            }
        }
        
        auth_key = jira_authkey()
        headers = {
            'Authorization': 'Basic ' + auth_key,
            'Content-Type': 'application/json'
        }
        
        print(f'Creating feature link between {story_key} and {feature_key}')
        logger.info(f"Creating feature link between {story_key} and {feature_key}")
        
        response = requests.post(url, json=payload, headers=headers, verify=False)
        
        if response.status_code == 201:
            print("Feature link created successfully")
            logger.info("Feature link created successfully")
        else:
            print(f"Feature link creation failed: {response.status_code} - {response.text}")
            logger.error(f"Feature link creation failed: {response.status_code} - {response.text}")
            
            # Try alternative link type names
            alternative_types = ["Feature", "Parent-Child", "Relates"]
            for alt_type in alternative_types:
                print(f"Trying alternative link type: {alt_type}")
                payload["type"]["name"] = alt_type
                response = requests.post(url, json=payload, headers=headers, verify=False)
                if response.status_code == 201:
                    print(f"Feature link created successfully with type: {alt_type}")
                    logger.info(f"Feature link created successfully with type: {alt_type}")
                    return
                else:
                    print(f"Alternative type {alt_type} failed: {response.status_code}")
            
            # If all alternatives fail, raise the original error
            raise Exception(f"All link types failed. Last response: {response.text}")
            
    except Exception as e:
        print(f"Error creating feature link: {str(e)}")
        logger.error(f"Error creating feature link: {str(e)}")
        raise e

def dynamic_create_feature_link(story_key: str, feature_key: str):
    """Attempt to create a feature link by dynamically discovering an appropriate issue link type.

    Strategy:
      1. Fetch all link types.
      2. Prefer types whose name or inward/outward description contains 'feature'.
      3. Fall back to existing heuristic alternatives.
    """
    try:
        auth_key = jira_authkey()
        headers = {'Authorization': 'Basic ' + auth_key, 'Content-Type': 'application/json'}
        base_url = os.getenv("JIRA_BASE_URL")
        types_resp = requests.get(base_url + 'issueLinkType', headers=headers, verify=False)
        chosen_types = []
        if types_resp.status_code == 200:
            data = types_resp.json()
            for t in data.get('issueLinkTypes', []):
                name = (t.get('name') or '').lower()
                inward = (t.get('inward') or '').lower()
                outward = (t.get('outward') or '').lower()
                if 'feature' in name or 'feature' in inward or 'feature' in outward:
                    chosen_types.append(t.get('name'))
        # Append legacy fallbacks
        for fallback in ["Is part of feature", "Feature", "Parent-Child", "Relates"]:
            if fallback not in chosen_types:
                chosen_types.append(fallback)
        tried = []
        for link_type in chosen_types:
            payload = {
                "type": {"name": link_type},
                "inwardIssue": {"key": feature_key},
                "outwardIssue": {"key": story_key}
            }
            resp = requests.post(base_url + 'issueLink', json=payload, headers=headers, verify=False)
            tried.append((link_type, resp.status_code))
            if resp.status_code == 201:
                print(f"Dynamic feature link success with type '{link_type}'")
                logger.info(f"Dynamic feature link success with type '{link_type}'")
                return
        raise Exception(f"All dynamic feature link attempts failed: {tried}")
    except Exception as e:
        logger.warning(f"dynamic_create_feature_link error: {e}")
        raise

# This will be an api call to add test cases to story key entered by user
def post_test_addition_to_story(storyKey, TestKey):
    url = os.getenv("JIRA_BASE_URL") + "issueLink"
    payload = {
        "type": {
            "name": "Tests"
        },
        "outwardIssue": {
            "key": storyKey
        },
        "inwardIssue": {
            "key": TestKey
        }
    }
    auth_key = jira_authkey()
    headers = {
        'Authorization': 'Basic ' + auth_key,
        'Content-Type': 'application/json'
    }
    print('postTestAdditionToStory URL : ', url)
    logger.info("postTestAdditionToStory URL : %s", url)
    print('postTestAdditionToStory headers : ', headers)
    logger.info("postTestAdditionToStory headers : %s", headers)
    print("postTestAdditionToStory payLoad : ", payload)
    logger.info("postTestAdditionToStory payLoad : %s", payload)
    print('Inside postTestAdditionToStory-before call')
    logger.info("Inside postTestAdditionToStory-before call")

    response = requests.post(url, json=payload, headers=headers, verify=False)
    response_code = response.status_code

    print("postTestAdditionToStory Response code: ", response.status_code)
    logger.info("postTestAdditionToStory Response code: %s", response.status_code)
    assert response_code == 201


if __name__ == "__main__":
    # storyId='INV-83955'
    # # testKey= 'INV-84848'
    # # testID = '5233914'
    # description_extraction(storyId)
    # # DescriptionText= mUtil.getTextJson(story_response._description)
    # # AcceptanceText=mUtil.getTextJson(story_response._acceptance_criteria)
    # # print("FinalText : ",DescriptionText,AcceptanceText)
    # testID, testKey = post_test_creation('Summary', 'Description', accountId, email_id)
    # post_test_step(testID, 'TestStep', 'TestPrerequisite', 'ExpectedResult')
    # post_test_addition_to_story(storyId, testKey)
    print("Inside jira main")
    logger.info("Inside jira main")
