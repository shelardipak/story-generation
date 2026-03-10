import json
import jwt
import time
import hashlib
from logging_config import get_logger
import os
from dotenv import load_dotenv

load_dotenv()

# Get the logger for this module
logger = get_logger(__name__)


def is_json(data):
    try:
        json.loads(data)
    except ValueError:
        return False
    return True


def jwt_token(testId, projectId):
    # ACCOUNT ID
    ACCOUNT_ID = os.getenv("INT_DASHBOARD_JIRA_ACCOUNT_ID")

    # ACCESS KEY from navigation >> Tests >> API Keys
    ACCESS_KEY = os.getenv("INT_DASHBOARD_JIRA_ACCESS_KEY")

    # ACCESS KEY from navigation >> Tests >> API Keys
    SECRET_KEY = os.getenv("INT_DASHBOARD_JIRA_SECRET")

    # JWT EXPIRE how long token been to be active? 3600 == 1 hour
    JWT_EXPIRE = 3600

    # BASE URL for Zephyr for Jira Cloud
    BASE_URL = os.getenv("ZEPHYR_BASE_URL")

    # RELATIVE PATH for token generation and make request to api 
    RELATIVE_PATH = '/public/rest/api/1.0/teststep/' + testId

    # CANONICAL PATH (Http Method & Relative Path & Query String)
    TOTAL_PATH = 'POST&' + RELATIVE_PATH + '&' + 'projectId=' + projectId
    print(TOTAL_PATH)

    # TOKEN HEADER: to generate jwt token
    payload_token = {
        'sub': ACCOUNT_ID,
        'qsh': hashlib.sha256(TOTAL_PATH.encode('utf-8')).hexdigest(),
        'iss': ACCESS_KEY,
        'exp': int(time.time()) + JWT_EXPIRE,
        'iat': int(time.time())
    }

    # GENERATE TOKEN
    print("Before jira zepher token generation")
    logger.info("Before jira zepher token generation")
    print("payload_token of jira zepher: ", payload_token)
    logger.info("payload_token of jira zepher: %s", payload_token)
    token = jwt.encode(payload_token, SECRET_KEY, algorithm='HS256').strip()
    print(token)
    return token
