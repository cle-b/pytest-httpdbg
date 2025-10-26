import json

import pytest


confest_py = """
        import pytest
        import requests
        from pytest_httpdbg import httpdbg_record_filename

        @pytest.fixture(scope="session")
        def fixture_session(httpbin):
            requests.get(httpbin.url + "/get?setupsession")
            yield
            requests.get(httpbin.url + "/get?teardownsession")


        @pytest.fixture()
        def fixture_function(httpbin, fixture_session):
            requests.get(httpbin.url + "/get?setupfunction")
            yield
            requests.get(httpbin.url + "/get?teardownfunction")
    """


def test_mode_mutual_exclusion(pytester):
    pytester.makeconftest(confest_py)

    pytester.makepyfile(
        """
        import requests

        def test_get(httpbin, fixture_session, fixture_function):
            requests.get(httpbin.url + "/get")
        """
    )

    result = pytester.runpytest("--httpdbg", "--httpdbg-allure")

    result.stderr.fnmatch_lines(
        [
            "*mutually exclusive. Please specify only one*",
        ]
    )

    assert result.ret == pytest.ExitCode.INTERNAL_ERROR


def test_mode_allure(pytester, tmp_path):
    pytester.makeconftest(confest_py)

    pytester.makepyfile(
        """
        import requests

        def test_get(httpbin, fixture_session, fixture_function):
            requests.get(httpbin.url + "/get")

        def test_post(httpbin, fixture_session, fixture_function):
            requests.post(httpbin.url + "/post", json={"a":"b"})
        """
    )

    result = pytester.runpytest("--httpdbg-allure", f"--alluredir={tmp_path}")

    result.assert_outcomes(passed=2)

    result_files = list(tmp_path.glob("*result.json"))

    assert len(result_files) == 2

    for result_file in result_files:

        with open(result_file) as f:
            result = json.load(f)

        if result["name"] == "test_get":
            for step in result["steps"]:
                if step["name"] == "httpdbg":
                    attachments = step["attachments"]
                    assert len(attachments) == 1
                    assert attachments[0]["name"] == "http traces"
                    assert attachments[0]["type"] == "text/html"
                    with open(tmp_path / attachments[0]["source"]) as f:
                        htmlcontent = f.read()
                    assert "test_get" in htmlcontent
                    assert "/get?setupsession" in htmlcontent
                    assert "/get?setupfunction" in htmlcontent
                    assert "/get?teardownfunction" in htmlcontent


def test_mode_allure_only_on_failure(pytester, tmp_path):
    pytester.makeconftest(confest_py)

    pytester.makepyfile(
        """
        import requests

        def test_pass(httpbin):
            requests.get(httpbin.url + "/get")

        def test_fail(httpbin):
            requests.post(httpbin.url + "/post", json={"a":"b"})
            assert False
        """
    )

    result = pytester.runpytest(
        "--httpdbg-allure", f"--alluredir={tmp_path}", "--httpdbg-only-on-failure"
    )

    result.assert_outcomes(passed=1, failed=1)

    result_files = list(tmp_path.glob("*result.json"))

    assert len(result_files) == 2

    for result_file in result_files:

        with open(result_file) as f:
            result = json.load(f)

        if result["name"] == "test_pass":
            assert "steps" not in result

        if result["name"] == "test_fail":
            for step in result["steps"]:
                if step["name"] == "httpdbg":
                    attachments = step.get("attachments", [])
                    assert len(attachments) == 1


def get_attachments_req_resp(result_file, name):
    with open(result_file) as f:
        result = json.load(f)

    httpdbg_steps = []
    for step in result.get("steps", []):
        if step["name"] == "httpdbg":
            httpdbg_steps = step["steps"]
    assert len(httpdbg_steps) == 1

    filename_request = None
    filename_response = None
    for step in httpdbg_steps[0]["steps"]:
        if step["name"] == "request":
            for attachment in step["attachments"]:
                if attachment["name"] == name:
                    filename_request = attachment["source"]
        if step["name"] == "response":
            for attachment in step["attachments"]:
                if attachment["name"] == name:
                    filename_response = attachment["source"]

    return filename_request, filename_response
