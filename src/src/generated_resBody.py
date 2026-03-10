
class TestDetail:

    def __init__(self, test_detail):
        self._test_detail = test_detail

    @property
    def test_step_number(self):
        try:
            return self._test_detail["Test Step number"]
        except KeyError:
            return None
        
    @test_step_number.setter
    def test_step_number(self, value):
        self._detail["Test Step number"] = value

    @property
    def test_step(self):
        try:
            return self._test_detail["Test Step"]
        except KeyError:
            return None
        
    @test_step.setter
    def test_step(self, value):
        self._detail["Test Step"] = value

    @property
    def test_prerequisite(self):
        try:
            return self._test_detail["Test prerequisite"]
        except KeyError:
            return None
        
    @test_prerequisite.setter
    def test_prerequisite(self, value):
        self._detail["Test prerequisite"] = value

    @property
    def expected_result(self):
        try:
            return self._test_detail["Expected Result"]
        except KeyError:
            return None
        
    @expected_result.setter
    def expected_result(self, value):
        self._detail["Expected Result"] = value


class TestCase:
    def __init__(self, test_case):
        self._test_case = test_case

    @property
    def test_summary(self):
        try:
            return self._test_case["Test Summary"]
        except KeyError:
            return None
        
    @test_summary.setter
    def test_summary(self, value):
        self._case["Test Summary"] = value

    @property
    def test_description(self):
        try:
            return self._test_case["Test Description"]
        except KeyError:
            return None
        
    @test_description.setter
    def test_description(self, value):
        self._case["Test Description"] = value

    @property
    def test_details(self):
        try:
            return [TestDetail(detail) for detail in self._test_case["Test Details"]]
        except KeyError:
            return None
        
    @test_details.setter
    def test_details(self, value):
        self._case["Test Details"] = [detail.detail for detail in value]


class Generated_resBody_ai:
    def __init__(self, response_body):
        self._response_body = response_body
        self._test_cases = [TestCase(case) for case in response_body.get("Test Cases", [])]
     
    @property
    def test_cases(self):
        if self._test_cases is not None:
            return [TestCase(test_case) for test_case in self._test_cases]
        else:
            return []
        
    @test_cases.setter
    def test_cases(self, value):
         self._test_cases = [TestCase(case) for case in value]