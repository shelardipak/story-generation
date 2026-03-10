import regex as re
import requests
import jiraUtils as jiraUtils
from logging_config import get_logger
import prompt as init_prompt
from jsonpath_ng import jsonpath, parse
import json
import streamlit as st
import urllib3
import os
from dotenv import load_dotenv
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

logger = get_logger(__name__)


def getTextJson(data, finalText=""):
    """(Legacy helper) Recursively extract visible text (skips struck-through)."""
    if isinstance(data, dict):
        if "marks" in data and any(mark.get("type") == "strike" for mark in data.get("marks", [])):
            return finalText
        for k, v in data.items():
            finalText = getTextJson(v, finalText)
        return finalText
    if isinstance(data, list):
        for item in data:
            finalText = getTextJson(item, finalText)
    elif isinstance(data, str):
        finalText += f" {data}"
    return finalText


def openAiRes(prompt: str):
    """Call unified GPT-4o endpoints (TST1 -> dev1) for test generation.

    Mirrors story generation configuration:
    - Endpoints: gpt-4o on TST1 then dev1
    - API version: 2024-10-21
    - Fallback with detailed diagnostics

    Returns: (success: bool, content_or_error: str)
    Side effects: writes st.session_state['testgen_endpoint_used'] and
                  st.session_state['testgen_last_error'].
    """
    api_version = "2024-10-21"

    endpoints = [
        {
            "name": "TST1",
            "url": "https://api-tst1.mandg.co.uk/enterprise/azureopenai/openai/deployments/gpt-4o/chat/completions",
            "api_key": os.getenv("INT_DASHBOARD_GENCORE_KEY_TST")
        },
        {
            "name": "dev1",
            "url": "https://api-dev1.mandg.co.uk/enterprise/azureopenai/openai/deployments/gpt-4o/chat/completions",
            "api_key": os.getenv("INT_DASHBOARD_GENCORE_KEY_DEV1")
        },
    ]

    body = {"model": "CHAT_COMPLETION_MODEL", "messages": [{"role": "user", "content": prompt}]}
    attempts = []
    last_error = None

    for ep in endpoints:
        name = ep['name']
        ep_key = ep.get('api_key')
        if not ep_key:
            msg = f"{name}: skipped (no key)"
            attempts.append(msg)
            logger.warning("[TestGenAI] %s", msg)
            continue

        url = f"{ep['url']}?api-version={api_version}"
        masked = ep_key[:4] + "…" + ep_key[-4:] if ep_key and len(ep_key) > 12 else "(short)"
        headers = {
            'x-Gencore-Correlation-ID': 'TestGen' + str(int(time.time())),
            'api-key': ep_key,
            'Content-Type': 'application/json'
        }
        logger.info("[TestGenAI] Trying %s (key %s)", name, masked)
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=60, verify=False)
        except requests.exceptions.Timeout as te:
            msg = f"{name}: TIMEOUT {te}"
            attempts.append(msg)
            last_error = msg
            logger.error(msg)
            continue
        except requests.exceptions.ConnectionError as ce:
            msg = f"{name}: CONNECTION {ce}"
            attempts.append(msg)
            last_error = msg
            logger.error(msg)
            continue
        except Exception as e:
            msg = f"{name}: EXCEPTION {e}"
            attempts.append(msg)
            last_error = msg
            logger.error(msg)
            continue

        if resp.status_code != 200:
            cat = (
                "AUTH" if resp.status_code in (401, 403) else
                "RATE_LIMIT" if resp.status_code == 429 else
                "SERVER" if resp.status_code in (500, 502, 503, 504) else
                "OTHER"
            )
            snippet = (resp.text or '')[:240]
            msg = f"{name}: {cat} {resp.status_code} {snippet}"
            attempts.append(msg)
            last_error = msg
            logger.error("[TestGenAI] %s", msg)
            continue

        try:
            data = resp.json()
        except Exception as je:
            msg = f"{name}: INVALID_JSON {je}"
            attempts.append(msg)
            last_error = msg
            logger.error(msg)
            continue

        # Azure OpenAI style error object even with 200 is unlikely but guard anyway;  non-200 handled above.
        # Also proactively detect safety/content filter blocks that sometimes return structured errors.
        try:
            if isinstance(data, dict) and 'error' in data:
                err = data.get('error') or {}
                code = str(err.get('code', '')).lower()
                message = str(err.get('message', ''))
                combined = f"{code} {message}".lower()
                if any(k in combined for k in ["content_filter", "content-filter", "filtered", "block", "blocked", "safety"]):
                    msg = f"{name}: BLOCKED {err.get('code','')} {message[:160]}".strip()
                    attempts.append(msg)
                    last_error = msg
                    logger.warning("[TestGenAI] %s", msg)
                    continue
                else:
                    # Treat other error objects as generic failures
                    msg = f"{name}: ERROR {err.get('code','')} {message[:160]}".strip()
                    attempts.append(msg)
                    last_error = msg
                    logger.error("[TestGenAI] %s", msg)
                    continue
        except Exception:
            pass

        content = ""
        try:
            if data.get('choices'):
                content = data['choices'][0].get('message', {}).get('content', '')
        except Exception:
            content = ""

        # If no content but a finish_reason or moderation result indicates blocking, surface that explicitly.
        if not content:
            try:
                # OpenAI style: choices[0].finish_reason == 'content_filter'
                fr = data.get('choices', [{}])[0].get('finish_reason') if isinstance(data.get('choices'), list) else None
                if fr and 'content_filter' in str(fr).lower():
                    msg = f"{name}: BLOCKED content_filter finish_reason"
                    attempts.append(msg)
                    last_error = msg
                    logger.warning("[TestGenAI] %s", msg)
                    continue
                # Azure safety result path (future-proof): look for 'blocked' fields
                safety = data.get('prompt_filter_results') or data.get('content_filter_results')
                if safety:
                    safety_text = json.dumps(safety)[:160]
                    if any(term in safety_text.lower() for term in ["blocked", "filtered"]):
                        msg = f"{name}: BLOCKED safety_results {safety_text}"
                        attempts.append(msg)
                        last_error = msg
                        logger.warning("[TestGenAI] %s", msg)
                        continue
            except Exception:
                pass

        if content:
            logger.info("[TestGenAI] Success via %s (len=%d)", name, len(content))
            try:
                st.session_state['testgen_endpoint_used'] = name
                st.session_state.pop('testgen_last_error', None)
            except Exception:
                pass
            return True, content
        else:
            msg = f"{name}: EMPTY_CONTENT"
            attempts.append(msg)
            last_error = msg
            logger.error("[TestGenAI] %s", msg)
            continue

    diagnostic = "All endpoints failed -> " + "; ".join(attempts)
    try:
        st.session_state['testgen_last_error'] = last_error or diagnostic
    except Exception:
        pass
    return False, diagnostic


def _build_test_generation_prompt(story_key: str, story_description: str) -> str:
    return (
        "You are a senior QA engineer. Given the JIRA story below, produce JSON with the key 'Test Cases' "
        "as a list of test case objects. Each test case object MUST contain keys: 'Test Summary', 'Test Description', "
        "and 'Test Details' (a list of step objects). Each step object must have keys 'Test Step number', 'Test Step', "
        "'Test prerequisite', 'Expected Result'. Keep language concise. Return ONLY JSON.\n\n"
        f"Story Key: {story_key}\n--- STORY DESCRIPTION START ---\n{story_description}\n--- STORY DESCRIPTION END ---"
    )


def _parse_ai_test_json(raw: str) -> dict:
    if not raw:
        raise ValueError("Empty AI response")
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    # Heuristic: find first '{' and last '}'
    if not cleaned.startswith('{'):
        first = cleaned.find('{')
        last = cleaned.rfind('}')
        if first != -1 and last != -1 and last > first:
            cleaned = cleaned[first:last+1]
    data = json.loads(cleaned)
    if 'Test Cases' not in data:
        raise ValueError("Missing 'Test Cases' key in AI response")
    return data


@st.cache_data(show_spinner="🤖 Generating test cases…")
def TestGenerationInProgress(story_key: str):  # noqa: N802 (legacy name)
    """Generate structured test cases for a given JIRA story key.

    1. Pull story description from JIRA (jiraUtils.description_extraction)
    2. Build strict JSON instruction prompt
    3. Call single endpoint (gpt4o-tst1)
    4. Parse and return dict
    """
    try:
        jira_response, _project_identity = jiraUtils.description_extraction(story_key)
    except Exception as e:
        logger.error("Failed to extract story description: %s", e)
        raise
    # jira_response likely has description inside; fallback to str()
    story_desc = getattr(jira_response, 'description', None) or getattr(jira_response, 'story_description', None) or str(jira_response)
    prompt = _build_test_generation_prompt(story_key, story_desc)
    ok, content = openAiRes(prompt)
    if not ok:
        logger.error("AI test generation failed: %s", content)
        raise ValueError(content)
    try:
        parsed = _parse_ai_test_json(content)
    except Exception as e:
        logger.error("Failed parsing AI JSON: %s | Raw: %.400s", e, content)
        raise
    return parsed


def display_test_case(test_case, idx):
    st.write("Test case: ", idx + 1)

    test_summary = st.text_area("Test Summary", value=test_case.test_summary, key=f'Summary{idx + 1}', height=50)
    test_Description = st.text_area("Test Description", value=test_case.test_description, key=f'Description{idx + 1}',
                                    height=150)

    for detail_idx, detail in enumerate(test_case.test_details):
        cols = st.columns(3)
        cols[0].text_input("Test Step", value=detail.test_step, key=f'TestStep{idx + 1}_{detail_idx + 1}')
        cols[1].text_input("Test prerequisite", value=detail.test_prerequisite,
                           key=f'TestPrerequisite{idx + 1}_{detail_idx + 1}')
        cols[2].text_input("Expected Result", value=detail.expected_result,
                           key=f'ExpectedResult{idx + 1}_{detail_idx + 1}')
    # Allow user to accept or reject the test case
    if f'Decision{idx + 1}' not in st.session_state:
        st.session_state[f'Decision{idx + 1}'] = "Accept"  # Default value

    # decision = st.selectbox("Accept or Reject this test case?", ["Accept", "Reject"], key=f'Decision{idx+1}')
    decision = st.selectbox("Accept or Reject this test case?", ["Accept", "Reject"],
                            key=f'Decision{idx + 1}_{detail_idx + 1}')
