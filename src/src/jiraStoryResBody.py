class JiraStory_ResBody:
    global nullvar
    nullvar = 'null'

    def __init__(self, response_body):
        self._description = None
        self._summary = None
        self._acceptance_criteria = None
        self._label = None
        self._components = None
        self._cust_Tech_Portfolio = None
        self._affects_version = None
        self._fix_version = None
        self._project_key = None
        self._project_name = None
        self._project_id = None
        self._CustTechDeliveryTeams = None
        self._story_key = None
        self._priority = None
        self._deliveryTeam = None
        self.response_body = response_body

        try:
            if response_body["fields"] is not None and 'description' in response_body["fields"] and \
                    response_body["fields"]["description"] is not None:
                self._description = response_body['fields']['description']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'summary' in response_body["fields"] and response_body["fields"][
                "summary"] is not None:
                self._summary = response_body['fields']['summary']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'customfield_10381' in response_body["fields"] and \
                    response_body["fields"]["customfield_10381"] is not None:
                self._acceptance_criteria = response_body['fields']['customfield_10381']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'labels' in response_body["fields"] and response_body["fields"][
                "labels"] is not None:
                self._label = response_body['fields']['labels']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'components' in response_body["fields"] and \
                    response_body["fields"]["components"] is not None:
                self._components = response_body['fields']['components'][0]['name']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'customfield_10246' in response_body["fields"] and \
                    response_body["fields"]["customfield_10381"] is not None:
                self._deliveryTeam = response_body['fields']['customfield_10246']['value']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'customfield_10229' in response_body["fields"]:
                self._cust_Tech_Portfolio = response_body["fields"]['customfield_10229']['value']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'versions' in response_body["fields"] and \
                    response_body["fields"]["versions"] is not None:
                self._affects_version = response_body["fields"]['versions'][0]['name']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'fixVersions' in response_body["fields"] and \
                    response_body["fields"]["fixVersions"] is not None:
                self._fix_version = response_body["fields"]['fixVersions'][0]['name']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'project' in response_body["fields"] and \
                    response_body["fields"]["project"]['key'] is not None:
                self._project_key = response_body["fields"]["project"]['key']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'project' in response_body["fields"] and \
                    response_body["fields"]["project"]['name'] is not None:
                self._project_name = response_body["fields"]["project"]['name']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'project' in response_body["fields"] and \
                    response_body["fields"]["project"]['id'] is not None:
                self._project_id = response_body["fields"]["project"]['id']
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'customfield_10236' in response_body["fields"] and \
                    response_body["fields"]["customfield_10236"][0]["value"] is not None:
                self._CustTechDeliveryTeams = response_body["fields"]["customfield_10236"][0]["value"]
        except Exception as e:
            pass

        try:
            if response_body["fields"] is not None and 'priority' in response_body["fields"] and \
                    response_body["fields"]["priority"]["name"] is not None:
                self._priority = response_body["fields"]['priority']['name']
        except Exception as e:
            pass

        try:
            if response_body["key"] is not None:
                self._story_key = response_body['key']
        except Exception as e:
            pass

    @property
    def description(self):
        return self._description if self._description is not None else None

    @description.setter
    def description(self, value):
        self._description = value if value is not None else None

    @property
    def deliveryTeam(self):
        return self._deliveryTeam if self._deliveryTeam is not None else None

    @deliveryTeam.setter
    def deliveryTeam(self, value):
        self._deliveryTeam = value if value is not None else None

    @property
    def summary(self):
        return self._summary if self._summary is not None else None

    @summary.setter
    def summary(self, value):
        self._summary = value if value is not None else None

    @property
    def acceptance_criteria(self):
        return self._acceptance_criteria if self._acceptance_criteria is not None else None

    @acceptance_criteria.setter
    def acceptance_criteria(self, value):
        self._acceptance_criteria = value if value is not None else None

    @property
    def label(self):
        return self._label if self._label is not None else None

    @label.setter
    def label(self, value):
        self._label = value if value is not None else None

    @property
    def components(self):
        return self._components if self._components is not None else None

    @components.setter
    def components(self, value):
        self._components = value if value is not None else None

    @property
    def cust_Tech_Portfolio(self):
        return self._cust_Tech_Portfolio if self._cust_Tech_Portfolio is not None else None

    @cust_Tech_Portfolio.setter
    def cust_Tech_Portfolio(self, value):
        self._cust_Tech_Portfolio = value if value is not None else None

    @property
    def affects_version(self):
        return self._affects_version if self._affects_version is not None else None

    @affects_version.setter
    def affects_version(self, value):
        self._affects_version = value if value is not None else None

    @property
    def fix_version(self):
        return self._fix_version if self._fix_version is not None else None

    @fix_version.setter
    def fix_version(self, value):
        self._fix_version = value if value is not None else None

    @property
    def project_key(self):
        return self._project_key if self._project_key is not None else None

    @project_key.setter
    def project_key(self, value):
        self._project_key = value if value is not None else None

    @property
    def project_name(self):
        return self._project_name if self._project_name is not None else None

    @project_name.setter
    def project_name(self, value):
        self._project_name = value if value is not None else None

    @property
    def project_id(self):
        return self._project_id if self._project_id is not None else None

    @project_id.setter
    def project_id(self, value):
        self._project_id = value if value is not None else None

    @property
    def CustTechDeliveryTeams(self):
        return self._CustTechDeliveryTeams if self._CustTechDeliveryTeams is not None else None

    @CustTechDeliveryTeams.setter
    def CustTechDeliveryTeams(self, value):
        self._CustTechDeliveryTeams = value if value is not None else None

    @property
    def priority(self):
        return self._priority if self._priority is not None else None

    @priority.setter
    def priority(self, value):
        self._priority = value if value is not None else None

    @property
    def story_key(self):
        return self._story_key if self._story_key is not None else None

    @story_key.setter
    def story_key(self, value):
        self._story_key = value if value is not None else None

import os
import re
import json
import requests
import base64
import logging
from logging_config import get_logger

logger = get_logger(__name__)

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
    username = os.getenv("INT_DASHBOARD_JIRA_USERNAME")
    api_token = os.getenv("INT_DASHBOARD_JIRA_AUTH")
    os.environ['NO_PROXY'] = 'mandg.atlassian.net'
    raw_key = f"{username}:{api_token}"
    auth_key = base64.b64encode(raw_key.encode('utf-8')).decode('utf-8')
    return auth_key

def create_formatted_description_adf(description):
    """
    Create a properly formatted JIRA description in ADF format with sections
    """
    # Extract sections from the description
    main_description = extract_main_description(description)
    acceptance_criteria = extract_acceptance_criteria_jira(description)
    technical_notes = extract_technical_notes_jira(description)
    
    # Create formatted ADF content with sections
    content_blocks = []
    
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
    
    # Acceptance Criteria section with bold heading
    content_blocks.append({
        "type": "paragraph",
        "content": [
            {
                "text": "Acceptance Criteria:",
                "type": "text",
                "marks": [{"type": "strong"}]
            }
        ]
    })
    
    # Acceptance criteria content as bullet points
    if acceptance_criteria:
        for line in acceptance_criteria.split('\n'):
            line = line.strip()
            if line:
                # Add bullet point if not already there
                if not line.startswith('•') and not line.startswith('-') and not line.startswith('*'):
                    line = '• ' + line
                    
                content_blocks.append({
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "text": line.lstrip('• -* '),
                                            "type": "text"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                })
    
    # Add spacing
    content_blocks.append({
        "type": "paragraph",
        "content": [{"text": "", "type": "text"}]
    })
    
    # Technical Notes section with bold heading
    content_blocks.append({
        "type": "paragraph",
        "content": [
            {
                "text": "Technical Implementation Notes:",
                "type": "text",
                "marks": [{"type": "strong"}]
            }
        ]
    })
    
    # Technical notes content as bullet points
    if technical_notes:
        for line in technical_notes.split('\n'):
            line = line.strip()
            if line:
                # Add bullet point if not already there
                if not line.startswith('•') and not line.startswith('-') and not line.startswith('*'):
                    line = '• ' + line
                    
                content_blocks.append({
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "text": line.lstrip('• -* '),
                                            "type": "text"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                })
    
    description_adf = {
        "version": 1,
        "type": "doc",
        "content": content_blocks
    }
    
    return description_adf

def create_jira_issue_main_story(summary, description, project_key, project_name, account_id, email_id, 
                              epic_key=None, feature_key=None, story_points=None, priority="Medium", 
                              cust_tech_portfolio=None, cust_tech_delivery_teams=None):
    """
    Create a new JIRA user story with properly formatted description
    
    Args:
        summary (str): Story title/summary
        description (str): Story description text
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
    
    Returns:
        tuple: (True, story_key, success_message) if successful, (False, None, error_message) if failed
    """
    try:
        logger.info("Creating JIRA story with formatted description")
        
        url = os.getenv("JIRA_BASE_URL") + "issue"
        
        # Format description with proper sections
        description_adf = create_formatted_description_adf(description)
        
        # Base payload for story creation
        payload = {
            "fields": {
                "project": {
                    "key": project_key,
                    "name": project_name
                },
                "summary": summary,
                "description": description_adf,
                "issuetype": {"name": "Story"},
                "priority": {"name": priority},
                "labels": ["JiraStoryGenAI"]
            }
        }
        
        # Only add assignee if we have a valid account ID (not default)
        if account_id and account_id != "default_account_id":
            payload["fields"]["assignee"] = {
                "accountId": account_id,
                "emailAddress": email_id
            }
        
        # Add epic link if provided
        if epic_key:
            payload["fields"]["customfield_10014"] = epic_key  # Epic Link field
        
        # Project-specific customizations
        if project_key == 'CT':
            # Add CT-specific required custom fields
            portfolio_value = cust_tech_portfolio if cust_tech_portfolio else "CEO"  # Default to CEO as specified
            payload["fields"]["customfield_10229"] = {"value": portfolio_value}  # Cust Tech Portfolio
            
        elif project_key == 'INV':
            # Add INV-specific custom fields if needed
            pass

        auth_key = jira_authkey()
        headers = {
            'Authorization': 'Basic ' + auth_key,
            'Content-Type': 'application/json'
        }
        
        logger.info(f"Creating JIRA story with summary: {summary}")
        
        response = requests.post(url, json=payload, headers=headers, verify=False)
        
        logger.info(f"JIRA API response status: {response.status_code}")
        
        if response.status_code == 201:
            response_body = response.json()
            story_key = response_body['key']
            
            logger.info(f"Story created successfully: {story_key}")
            
            # Try to create feature link if provided
            if feature_key:
                try:
                    logger.info(f"Creating feature link: {story_key} -> {feature_key}")
                    create_feature_link(story_key, feature_key)
                    logger.info(f"Feature link created: {story_key} -> {feature_key}")
                except Exception as link_error:
                    logger.warning(f"Feature link failed: {str(link_error)}")
            
            return True, story_key, f"Successfully created story {story_key}"
        else:
            error_message = f"Failed to create story: Status {response.status_code}"
            if response.text:
                try:
                    error_details = response.json()
                    if 'errors' in error_details:
                        error_message += f" - {error_details['errors']}"
                except:
                    error_message += f" - {response.text[:200]}"
            
            logger.error(error_message)
            return False, None, error_message
            
    except Exception as e:
        error_message = f"Error creating story: {str(e)}"
        logger.error(error_message)
        return False, None, error_message

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
                "name": "Relates"  # Default to "Relates" which usually works
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
        
        logger.info(f"Creating feature link between {story_key} and {feature_key}")
        
        response = requests.post(url, json=payload, headers=headers, verify=False)
        
        if response.status_code == 201:
            logger.info("Feature link created successfully")
            return True
        else:
            logger.error(f"Feature link creation failed: {response.status_code}")
            
            # Try alternative link type names
            alternative_types = ["Is part of feature", "Feature", "Parent-Child"]
            for alt_type in alternative_types:
                logger.info(f"Trying alternative link type: {alt_type}")
                payload["type"]["name"] = alt_type
                response = requests.post(url, json=payload, headers=headers, verify=False)
                if response.status_code == 201:
                    logger.info(f"Feature link created with type: {alt_type}")
                    return True
            
            raise Exception(f"All link types failed. Status: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Error creating feature link: {str(e)}")
        raise e