# -*- coding: utf-8 -*-
import glob
import os
import pickle
import time
from typing import Optional
import uuid

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
    parser.addoption("--httpdbg", action="store_true", help="record HTTP(S) requests")
    parser.addoption(
        "--httpdbg-dir", type=str, default="", help="save httpdbg traces in a directory"
    )
    parser.addoption(
        "--httpdbg-no-clean",
        action="store_true",
        default=False,
        help="do not clean the httpdbg directory",
    )
    parser.addoption(
        "--httpdbg-initiator",
        action="append",
        help="add a new initiator (package) for httpdbg",
    )


def pytest_configure(config):
    # add a flag to indicates to HTTPDBG to not set specific initiator
    if config.option.httpdbg:
        os.environ["HTTPDBG_PYTEST_PLUGIN"] = "1"

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
    if item.config.option.httpdbg or (
        ("HTTPDBG_SUBPROCESS_DIR" in os.environ)
        and ("PYTEST_XDIST_WORKER" in os.environ)
    ):
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

            # pytest is executed using pyhttpdbg
            # -> we serialize the HTTPRecords object to share it with the main pyhttpdbg process
            if "HTTPDBG_SUBPROCESS_DIR" in os.environ:
                if "PYTEST_XDIST_WORKER" in os.environ:
                    if len(records.requests) > 0:
                        fname = f"{os.environ['HTTPDBG_SUBPROCESS_DIR']}/{uuid.uuid1()}"
                        with open(f"{fname}.httpdbgrecords.tmp", "wb") as f:
                            pickle.dump(records, f)
                        os.rename(
                            f"{fname}.httpdbgrecords.tmp", f"{fname}.httpdbgrecords"
                        )

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
