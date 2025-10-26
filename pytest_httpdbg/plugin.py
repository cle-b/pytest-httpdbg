import glob
import os
import time
from typing import Optional

import pytest

from httpdbg import httprecord
from httpdbg.export import generate_html

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
        with httprecord(
            initiators=item.config.option.httpdbg_initiator, multiprocess=False
        ) as records:
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
            initiators=session.config.option.httpdbg_initiator,
            multiprocess=False,
        )
        session.httpdbg_records = session.httpdbg_recorder.__enter__()


def pytest_sessionfinish(session, exitstatus):
    if session.config.option.httpdbg_allure:
        session.httpdbg_recorder.__exit__(None, None, None)


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

                        allure.attach(
                            generate_html(
                                item.session.httpdbg_records, for_export=True
                            ),
                            name="http traces",
                            attachment_type=allure.attachment_type.HTML,
                        )
                except ImportError:
                    pass

            item.session.httpdbg_records.reset()
