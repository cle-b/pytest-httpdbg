# -*- coding: utf-8 -*-
import glob
import os
import time
import traceback
from typing import Optional

import pytest

from httpdbg import httprecord

httpdbg_record_filename = pytest.StashKey[str]()


def safe_test_name_for_filename(nodeid):
    safe_nodeid = "".join([c if c.isalnum() else "_" for c in nodeid])
    return f"{safe_nodeid}_{int(time.time()*1000)}.httpdbg.md"


def content_type_md(content_type):
    ct = ""
    if "json" in content_type.lower():
        ct = "json"
    elif "html" in content_type.lower():
        ct = "html"
    elif "xml" in content_type.lower():
        ct = "xml"
    return ct


def record_to_md(record, initiators):
    return f"""## {record.url}

### initiator

{initiators[record.initiator_id].label}

```
{initiators[record.initiator_id].short_stack}
```

### request

```http
{record.request.rawheaders.decode("utf-8")}
```

```{content_type_md(record.request.get_header("Content-Type"))}
{record.request.preview.get("parsed", record.request.preview.get("text", ""))}
```

### response

```http
{record.response.rawheaders.decode("utf-8")}
```

```{content_type_md(record.response.get_header("Content-Type"))}
{record.response.preview.get("parsed", record.response.preview.get("text", ""))}
```

"""


def pytest_addoption(parser):

    reporting_group = parser.getgroup("reporting")

    # mode custom
    reporting_group.addoption(
        "--httpdbg", action="store_true", help="record HTTP(S) requests"
    )

    reporting_group.addoption(
        "--httpdbg-dir", type=str, default="", help="save httpdbg traces in a directory"
    )

    reporting_group.addoption(
        "--httpdbg-no-clean",
        action="store_true",
        default=False,
        help="do not clean the httpdbg directory",
    )

    # mode allure
    reporting_group.addoption(
        "--httpdbg-allure",
        action="store_true",
        help="save HTTP(S) traces into the allure report",
    )

    reporting_group.addoption(
        "--httpdbg-no-headers",
        action="store_true",
        default=False,
        help="save the HTTP headers",
    )

    reporting_group.addoption(
        "--httpdbg-no-binary",
        action="store_true",
        default=False,
        help="do not save the HTTP payload if it's a binary content",
    )

    reporting_group.addoption(
        "--httpdbg-only-on-failure",
        action="store_true",
        default=False,
        help="save the HTTP requests only if the test failed",
    )

    reporting_group.addoption(
        "--httpdbg-initiator",
        action="append",
        help="add a new initiator (package) for httpdbg",
    )


def pytest_configure(config):

    if config.option.httpdbg is True and config.option.httpdbg_allure is True:
        pytest.exit(
            "Error: --httpdbg and --httpdbg-allure are mutually exclusive. Please specify only one."
        )

    # clean logs directory
    httpdbg_dir = config.option.httpdbg_dir
    if httpdbg_dir and not config.option.httpdbg_no_clean:
        if os.path.isdir(httpdbg_dir):
            for logfile in glob.glob(os.path.join(httpdbg_dir, "*.httpdbg.md")):
                os.remove(logfile)
            try:
                os.rmdir(httpdbg_dir)
            except OSError:
                pass  # the directory is not empty, we don't remove it


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: Optional[pytest.Item]):
    if item.config.option.httpdbg:
        with httprecord(initiators=item.config.option.httpdbg_initiator) as records:
            # the record of the http requests has been enable using a pytest command line argument
            # -> first, we stash the path to the log file
            httpdbg_dir = item.config.option.httpdbg_dir
            if httpdbg_dir:
                os.makedirs(httpdbg_dir, exist_ok=True)

                filename = os.path.join(
                    httpdbg_dir, safe_test_name_for_filename(item.nodeid)
                )
                item.stash[httpdbg_record_filename] = filename

            yield

            # the record of the http requests has been enable using a pytest command line argument
            # -> we create a human readable file that contains all the HTTP requests recorded
            if httpdbg_record_filename in item.stash:
                with open(
                    item.stash[httpdbg_record_filename], "w", encoding="utf-8"
                ) as f:
                    f.write(f"# {item.nodeid}\n\n")
                    for record in records:
                        f.write(f"{record_to_md(record, records.initiators)}\n")
    else:
        yield


# Allure mode: HTTP requests are recorded throughout the entire session and
# saved in the Allure report at the test level.
def pytest_sessionstart(session):
    if session.config.option.httpdbg_allure:
        session.httpdbg_recorder = httprecord(
            initiators=session.config.option.httpdbg_initiator
        )
        session.httpdbg_records = session.httpdbg_recorder.__enter__()


def pytest_sessionfinish(session, exitstatus):
    if session.config.option.httpdbg_allure:
        session.httpdbg_recorder.__exit__(None, None, None)


def get_allure_attachment_type_from_content_type(content_type: str):
    try:
        import allure

        for attachment_type in allure.attachment_type:
            if attachment_type.mime_type == content_type:
                return attachment_type
    except ImportError:
        pass
    return None


def req_resp_steps(label, req, save_headers, save_binary_payload):
    try:
        import allure

        # we generate the payload first because we do not want to add a step
        # if there is no headers and no payload to save
        content = req.preview
        payload = None
        if content.get("text"):
            payload = content.get("text")
        elif save_binary_payload:
            payload = req.content

        if save_headers or payload:
            with allure.step(label):
                if save_headers:
                    allure.attach(
                        req.rawheaders.decode("utf-8"),
                        name="headers",
                        attachment_type=allure.attachment_type.TEXT,
                    )
                if payload:
                    attachment_type = get_allure_attachment_type_from_content_type(
                        content.get("content_type")
                    )
                    allure.attach(
                        payload, name="payload", attachment_type=attachment_type
                    )
    except ImportError:
        pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):

    outcome = yield
    report = outcome.get_result()

    if item.config.option.httpdbg_allure:
        # we keep the information about the status of the test for all phases
        item.passed = getattr(item, "passed", True) and report.passed

        if report.when == "teardown":
            if (not item.config.option.httpdbg_only_on_failure) or (not item.passed):
                try:
                    import allure

                    with allure.step("httpdbg"):

                        records = item.session.httpdbg_records

                        for record in records:

                            label = ""

                            if record.response.status_code:
                                label += f"{record.response.status_code} "

                            if record.request.method:
                                label += f"{record.request.method} "

                            if record.request.uri:
                                url = record.request.uri
                            else:
                                url = record.url
                            if len(url) > 200:
                                url = url[:100] + "..." + url[-97:]
                            ex = (
                                (str(type(record.exception)) + " ")
                                if record.exception is not None
                                else ""
                            )
                            label += f"{ex}{url}"

                            if record.tag:
                                label += f" (from {record.tag})"

                            with allure.step(label):
                                details = record.url
                                details += f"\n\nstatus: {record.response.status_code} {record.response.message}"
                                details += f"\n\nstart: {record.tbegin.isoformat()}"
                                details += f"\nend:   {record.last_update.isoformat()}"

                                if record.initiator_id in records.initiators:
                                    details += f"\n\n{records.initiators[record.initiator_id].short_stack}"

                                if record.exception is not None:
                                    details += (
                                        f"\n\nException:   {type(record.exception)}\n"
                                    )
                                    details += "".join(
                                        traceback.format_exception(
                                            type(record.exception),
                                            record.exception,
                                            record.exception.__traceback__,
                                        )
                                    )

                                allure.attach(
                                    details,
                                    name="details",
                                    attachment_type=allure.attachment_type.TEXT,
                                )

                                req_resp_steps(
                                    "request",
                                    record.request,
                                    not item.config.option.httpdbg_no_headers,
                                    not item.config.option.httpdbg_no_binary,
                                )
                                req_resp_steps(
                                    "response",
                                    record.response,
                                    not item.config.option.httpdbg_no_headers,
                                    not item.config.option.httpdbg_no_binary,
                                )
                except ImportError:
                    pass

            item.session.httpdbg_records.reset()
