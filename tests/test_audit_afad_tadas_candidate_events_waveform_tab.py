from pathlib import Path
import zipfile

from scripts import audit_afad_tadas_candidate_events_waveform_tab as mod


class FakeDownload:
    suggested_filename = "20240223121432_1658.zip"

    def save_as(self, path: str) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("dummy.HNE", "STREAM: HNE\n")


class FakeDownloadInfo:
    value = FakeDownload()


class FakeExpectDownload:
    def __enter__(self):
        return FakeDownloadInfo()

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeTab:
    def __init__(self, page):
        self.page = page

    def count(self):
        return 1

    def click(self):
        self.page.tab_clicked = True


class FakeButton:
    def __init__(self, page):
        self.page = page

    def count(self):
        return 1

    def wait_for(self, state, timeout):
        assert state == "visible"
        assert self.page.tab_clicked

    def is_disabled(self):
        return False

    def click(self):
        assert self.page.tab_clicked
        self.page.button_clicked = True


class FakePage:
    def __init__(self):
        self.tab_clicked = False
        self.button_clicked = False
        self.visited = None

    def goto(self, url, wait_until):
        self.visited = (url, wait_until)

    def wait_for_timeout(self, value):
        pass

    def locator(self, selector):
        assert selector == mod.WAVEFORM_TAB_SELECTOR
        return FakeTab(self)

    def get_by_role(self, role, name, exact):
        assert role == "button"
        assert name == mod.RAW_BUTTON_NAME
        assert exact is True
        return FakeButton(self)

    def expect_download(self, timeout):
        return FakeExpectDownload()


def test_verified_download_opens_waveform_tab_before_raw_button(tmp_path: Path):
    page = FakePage()
    target = tmp_path / "raw.zip"
    url, suggested = mod.download_raw_zip(page, "2136302", target, 30000)

    assert page.visited == (
        "https://tadas.afad.gov.tr/waveform-detail/2136302",
        "domcontentloaded",
    )
    assert page.tab_clicked is True
    assert page.button_clicked is True
    assert suggested == "20240223121432_1658.zip"
    assert url.endswith("/2136302")
    assert zipfile.is_zipfile(target)
