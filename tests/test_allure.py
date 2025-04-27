# -*- coding: utf-8 -*-
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

            httpdbg_steps = []
            for step in result["steps"]:
                if step["name"] == "httpdbg":
                    httpdbg_steps = step["steps"]
            assert len(httpdbg_steps) == 4

            step = httpdbg_steps[0]
            assert step["name"] == "200 GET /get?setupsession (from fixture_session)"
            step = httpdbg_steps[1]
            assert step["name"] == "200 GET /get?setupfunction (from fixture_function)"
            step = httpdbg_steps[2]
            assert step["name"] == "200 GET /get"
            step = httpdbg_steps[3]
            assert (
                step["name"] == "200 GET /get?teardownfunction (from fixture_function)"
            )

        else:

            httpdbg_steps = []
            for step in result["steps"]:
                if step["name"] == "httpdbg":
                    httpdbg_steps = step["steps"]
            assert len(httpdbg_steps) == 4

            step = httpdbg_steps[0]
            assert step["name"] == "200 GET /get?setupfunction (from fixture_function)"
            step = httpdbg_steps[1]
            assert step["name"] == "200 POST /post"
            step = httpdbg_steps[2]
            assert (
                step["name"] == "200 GET /get?teardownfunction (from fixture_function)"
            )
            step = httpdbg_steps[3]
            assert step["name"] == "200 GET /get?teardownsession (from fixture_session)"


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

        httpdbg_steps = []
        for step in result.get("steps", []):
            if step["name"] == "httpdbg":
                httpdbg_steps = step["steps"]

        if result["name"] == "test_pass":
            assert len(httpdbg_steps) == 0
        else:
            assert result["name"] == "test_fail"
            assert len(httpdbg_steps) == 1


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


def test_mode_allure_with_headers(pytester, tmp_path):

    pytester.makepyfile(
        """
        import requests

        def test_pass(httpbin):
            requests.get(httpbin.url + "/get")
        """
    )

    result = pytester.runpytest("--httpdbg-allure", f"--alluredir={tmp_path}")

    result.assert_outcomes(passed=1)

    result_files = list(tmp_path.glob("*result.json"))

    assert len(result_files) == 1

    headers_filename_request, headers_filename_response = get_attachments_req_resp(
        result_files[0], "headers"
    )

    with open(tmp_path / headers_filename_request) as f:
        assert "GET /get HTTP/1.1" in f.read()

    with open(tmp_path / headers_filename_response) as f:
        assert "HTTP/1.1 200 OK" in f.read()


def test_mode_allure_without_headers(pytester, tmp_path):

    pytester.makepyfile(
        """
        import requests

        def test_pass(httpbin):
            requests.get(httpbin.url + "/get")
        """
    )

    result = pytester.runpytest(
        "--httpdbg-allure", f"--alluredir={tmp_path}", "--httpdbg-no-headers"
    )

    result.assert_outcomes(passed=1)

    result_files = list(tmp_path.glob("*result.json"))

    assert len(result_files) == 1

    headers_filename_request, headers_filename_response = get_attachments_req_resp(
        result_files[0], "headers"
    )

    assert headers_filename_request is None
    assert headers_filename_response is None


def test_mode_allure_payload(pytester, tmp_path):

    pytester.makepyfile(
        """
        import requests

        def test_get(httpbin):
            requests.get(httpbin.url + "/get")

        def test_post(httpbin):
            requests.post(httpbin.url + "/post", data="hello")

        def test_binary(httpbin):
            requests.get(httpbin.url + "/bytes/56")

        """
    )

    result = pytester.runpytest("--httpdbg-allure", f"--alluredir={tmp_path}")

    result.assert_outcomes(passed=3)

    result_files = list(tmp_path.glob("*result.json"))

    assert len(result_files) == 3

    for result_file in result_files:

        with open(result_file) as f:
            test_name = json.load(f)["name"]

        if test_name == "test_get":
            get_payload_request, get_payload_response = get_attachments_req_resp(
                result_file, "payload"
            )

        if test_name == "test_post":
            post_payload_request, post_payload_response = get_attachments_req_resp(
                result_file, "payload"
            )

        if test_name == "test_binary":
            binary_payload_request, binary_payload_response = get_attachments_req_resp(
                result_file, "payload"
            )

    assert get_payload_request is None
    with open(tmp_path / get_payload_response) as f:
        payload = f.read()
        assert "User-Agent" in payload
        assert "/get" in payload

    with open(tmp_path / post_payload_request) as f:
        payload = f.read()
        assert "hello" in payload
    with open(tmp_path / post_payload_response) as f:
        payload = f.read()
        assert "User-Agent" in payload
        assert "/post" in payload

    assert binary_payload_request is None
    with open(tmp_path / binary_payload_response, "rb") as f:
        assert len(f.read()) == 56


def test_mode_allure_payload_no_binary(pytester, tmp_path):

    pytester.makepyfile(
        """
        import requests

        def test_get(httpbin):
            requests.get(httpbin.url + "/get")

        def test_post(httpbin):
            requests.post(httpbin.url + "/post", data="hello")

        def test_binary(httpbin):
            requests.get(httpbin.url + "/bytes/56")
        """
    )

    result = pytester.runpytest(
        "--httpdbg-allure", f"--alluredir={tmp_path}", "--httpdbg-no-binary"
    )

    result.assert_outcomes(passed=3)

    result_files = list(tmp_path.glob("*result.json"))

    assert len(result_files) == 3

    for result_file in result_files:

        with open(result_file) as f:
            test_name = json.load(f)["name"]

        if test_name == "test_get":
            get_payload_request, get_payload_response = get_attachments_req_resp(
                result_file, "payload"
            )

        if test_name == "test_post":
            post_payload_request, post_payload_response = get_attachments_req_resp(
                result_file, "payload"
            )

        if test_name == "test_binary":
            binary_payload_request, binary_payload_response = get_attachments_req_resp(
                result_file, "payload"
            )

    assert get_payload_request is None
    assert get_payload_response is not None

    assert post_payload_request is not None
    assert post_payload_response is not None

    assert binary_payload_request is None
    assert binary_payload_request is None


def test_mode_allure_details(pytester, tmp_path):

    pytester.makepyfile(
        """
        import requests

        def test_get(httpbin):
            requests.get("http://127.0.0.1" + ":8345" + "/get")
        """
    )

    result = pytester.runpytest("--httpdbg-allure", f"--alluredir={tmp_path}")

    result.assert_outcomes(failed=1)

    result_files = list(tmp_path.glob("*result.json"))

    assert len(result_files) == 1

    with open(result_files[0]) as f:
        result = json.load(f)

    filename_payload = None
    for step in result.get("steps", []):
        if step["name"] == "httpdbg":
            for attachment in step["steps"][0]["attachments"]:
                if attachment["name"] == "details":
                    filename_payload = attachment["source"]

    with open(tmp_path / filename_payload) as f:
        payload = f.read()
        assert "http://127.0.0.1:8345/get" in payload
        assert 'requests.get("http://127.0.0.1" + ":8345" + "/get")' in payload


def test_mode_allure_no_step_if_empty(pytester, tmp_path):

    pytester.makepyfile(
        """
        import requests

        def test_binary(httpbin):
            requests.get(httpbin.url + "/bytes/56")
    """
    )

    result = pytester.runpytest(
        "--httpdbg-allure",
        f"--alluredir={tmp_path}",
        "--httpdbg-no-headers",
        "--httpdbg-no-binary",
    )

    result.assert_outcomes(passed=1)

    result_files = list(tmp_path.glob("*result.json"))

    assert len(result_files) == 1

    sub_steps = "should be None"

    with open(result_files[0]) as f:
        result = json.load(f)

        for step in result.get("steps", []):
            if step["name"] == "httpdbg":
                sub_steps = step["steps"][0].get("steps")

    assert sub_steps is None
