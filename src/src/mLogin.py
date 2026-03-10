import os
import requests
import streamlit as st
from logging_config import get_logger
from msal import ConfidentialClientApplication
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

logger = get_logger(__name__)


def initialize_app():
    client_id = os.getenv("INT_DASHBOARD_CLIENT_ID")
    tenant_id = os.getenv("INT_DASHBOARD_TENANT_ID")
    client_secret = os.getenv("INT_DASHBOARD_CLIENT_SECRET")
    authority_url = f"https://login.microsoftonline.com/{tenant_id}"
    return ConfidentialClientApplication(client_id, authority=authority_url, client_credential=client_secret)


def acquire_access_token(app, code, scopes, redirect_uri):
    return app.acquire_token_by_authorization_code(code, scopes=scopes, redirect_uri=redirect_uri)


def fetch_user_data(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    graph_api_endpoint = "https://graph.microsoft.com/v1.0/me"
    response = requests.get(graph_api_endpoint, headers=headers)
    logger.info("MS fetch_user_data success: %s", response.status_code)
    return response.json()


def authentication_process(app):
    scopes = ["User.Read"]
    redirect_uri = os.getenv("REDIRECT_URI")
    auth_url = app.get_authorization_request_url(scopes, redirect_uri=redirect_uri)
    if not st.query_params.get("code"):
        st.link_button('Authorize App', url=auth_url)

    elif "access_token" in st.session_state:
        # Use the stored access token if it exists
        user_data = fetch_user_data(st.session_state["access_token"])
        logger.info("MS authentication_process success - Using the stored access token ")
        return user_data
    else:
        st.session_state["auth_code"] = st.query_params.get("code")
        token_result = acquire_access_token(app, st.session_state.auth_code, scopes, redirect_uri)
        # print("Token result: ", token_result)
        if "access_token" in token_result:
            # Store the access token in the session state
            st.session_state["access_token"] = token_result["access_token"]
            user_data = fetch_user_data(token_result["access_token"])
            print("MS authentication_process success - inside else ")
            logger.info("MS authentication_process success - inside else ")
            return user_data
        else:
            st.error("You have been logged out. Please login again")
            logger.error("You have been logged out. Please login again")
            st.link_button('Authorize App', url=auth_url)


def login_ui():
    app = initialize_app()
    user_data = authentication_process(app)
    if user_data:
        st.write("Welcome, ", user_data.get("displayName"))
        st.session_state["authenticated"] = True
        st.session_state["display_name"] = user_data.get("displayName")
        st.session_state["username"] = user_data.get("userPrincipalName")
        st.rerun()


def logout(app):
    accounts = app.get_accounts()
    print("Accounts retrieved: ", accounts)
    logger.info("Accounts retrieved: %s", accounts)
    if accounts:
        print("Accounts: ", accounts)
        logger.info("Accounts: %s", accounts)
        app.remove_account(accounts[0])
        st.write("Logged out successfully")
        # Clear the session state
        st.query_params.clear()
        st.session_state.clear()
    else:
        st.write("No account is currently logged in")
        st.session_state.clear()
        st.session_state.clear()


def logout_ui():
    app = initialize_app()
    logout(app)
