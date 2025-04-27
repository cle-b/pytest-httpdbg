# pytest-httpdbg

A pytest plugin for recording HTTP(S) requests and saving them in your test report.

## installation 

```
pip install pytest-httpdbg
```

## Allure report

If you use the [allure-pytest](https://pypi.org/project/allure-pytest/) plugin to generate an [Allure](https://allurereport.org/docs/pytest/) report, you can use [pytest-httpdbg](https://pypi.org/project/pytest-httpdbg/) to include HTTP request traces in your test report without any code modifications.

All you need to do is add the `--httpdbg-allure` option to your pytest command line:

```
pytest ../httpdbg-docs/examples/ --alluredir=./allure-results --httpdbg-allure
``` 

If an HTTP request is made by the test (or within a fixture, during the setup or teardown phase), the request will be saved in the Allure report under a step called `httpdbg`.

![](https://github.com/cle-b/pytest-httpdbg/blob/main/pytest-httpdbg-allure-0.8.0.png?raw=true)


## Custom test report

You can add HTTP traces to any test report of your choice. To do this, you can use the HTTP traces saved by the plugin in Markdown format.

When a test finishes (including the teardown step), a log file in Markdown format is generated. The path to this log file is stored in the test item when the test starts (before the setup step), even if the file does not yet exist.

### pytest-html

You can copy the following code in your top-level `conftest.py` to include the logs into your `pytest-html` report.

```python
import os

import pytest

from pytest_httpdbg import httpdbg_record_filename


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    pytest_html = item.config.pluginmanager.getplugin("html")
    outcome = yield
    report = outcome.get_result()
    extras = getattr(report, "extras", [])

    if call.when == "call":
        if httpdbg_record_filename in item.stash:
            extras.append(
                pytest_html.extras.url(
                    os.path.basename(item.stash[httpdbg_record_filename]),
                    name="HTTPDBG",
                )
            )
            report.extras = extras
```

This example works if you use the same directory for the html test report file and the httpdbg logs. 
 
 `pytest demo/ --httpdbg --httpdbg-dir report  --html=report/report.html`

If this is not the case, you must adapt it to your configuration.

![](https://github.com/cle-b/pytest-httpdbg/blob/main/ui.png?raw=true)

## pytest command line options

```
reporting:

  --httpdbg                                 record HTTP(S) requests
  --httpdbg-dir=HTTPDBG_DIR                 save httpdbg traces in a directory
  --httpdbg-no-clean                        do not clean the httpdbg directory

  --httpdbg-allure                          save HTTP(S) traces into the allure report
  --httpdbg-no-headers                      save the HTTP headers
  --httpdbg-no-binary                       do not save the HTTP payload if it's a binary content
  --httpdbg-only-on-failure                 save the HTTP requests only if the test failed

  --httpdbg-initiator=HTTPDBG_INITIATOR     add a new initiator (package) for httpdbg

```

## httpdbg

This plugin is based on the [httpdbg](https://pypi.org/project/httpdbg/) Python tool. You can use it to trace all HTTP requests in your tests and view them in a more detailed user interface using the `pyhttpdbg` command.

```
pyhttpdbg -m pytest -v examples/
```

![](https://github.com/cle-b/pytest-httpdbg/blob/main/httpdbg-pytest-1.2.1.png?raw=true)

## documentation

https://httpdbg.readthedocs.io/en/latest/pytest/
