def get_prompt_text():
    return '''
Create manual test cases for the below user story description. The test cases should cover all possible scenarios including positive, negative, boundary value, and equivalent tests. They should also consider potential side effects and impacts on other parts of the system.Each test case should be structured as a JSON object, following the format below:
{"Test Cases":[{"Test Summary": "A brief summary of the test case...",
"Test Description": "GIVEN some initial context, \n WHEN an event occurs, \n THEN ensure some outcomes.",
"Test Details": [{"Test Step number": 1,
"Test Step": "A description of the step...",
"Test prerequisite": "Any prerequisites for the step...",
"Expected Result": "The expected outcome of the step..."
}// Additional test steps as necessary...]}// Additional test cases as necessary...]}
Please ensure that the output is a valid JSON object. The 'Test Step number' should be an integer. Start your response with the JSON object containing the test cases only.
Story Description: '''