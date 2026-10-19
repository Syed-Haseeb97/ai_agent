import unittest

import helpers  # noqa: F401
from background_agent import (Action, ActionKind, BackgroundTask, DefaultActionPolicy, PolicyVerdict,
                              TaskLimits)

TASK = BackgroundTask("g", TaskLimits())
P = DefaultActionPolicy()


def verdict(kind, **params):
    return P.evaluate(Action(kind, params), TASK).verdict


class PolicyTests(unittest.TestCase):
    def test_plain_reads_and_writes_allowed(self):
        self.assertIs(verdict(ActionKind.FS_READ, path="a"), PolicyVerdict.ALLOW)
        self.assertIs(verdict(ActionKind.FS_WRITE, path="a", content="x"), PolicyVerdict.ALLOW)

    def test_destructive_and_overwrite_need_confirmation(self):
        self.assertIs(verdict(ActionKind.FS_DELETE, path="a"), PolicyVerdict.CONFIRM)
        self.assertIs(verdict(ActionKind.FS_WRITE, path="a", overwrite=True), PolicyVerdict.CONFIRM)
        self.assertIs(verdict(ActionKind.FS_MOVE, src="a", dst="b", overwrite=True), PolicyVerdict.CONFIRM)

    def test_gui_denied_by_default(self):
        for k in (ActionKind.GUI_CLICK, ActionKind.GUI_TYPE, ActionKind.GUI_LAUNCH_APP):
            self.assertIs(verdict(k), PolicyVerdict.DENY)
        self.assertIs(DefaultActionPolicy(allow_gui=True).evaluate(Action(ActionKind.GUI_CLICK), TASK).verdict,
                      PolicyVerdict.ALLOW)

    def test_process_run_rules(self):
        self.assertIs(verdict(ActionKind.PROCESS_RUN, argv=["python", "-V"]), PolicyVerdict.ALLOW)
        self.assertIs(verdict(ActionKind.PROCESS_RUN, argv=["C:\\Python\\python.EXE", "-V"]), PolicyVerdict.ALLOW)
        self.assertIs(verdict(ActionKind.PROCESS_RUN, argv=["tool.exe"]), PolicyVerdict.CONFIRM)
        for gui_or_dangerous in ("notepad.exe", "chrome", "powershell", "shutdown", "taskkill.exe"):
            self.assertIs(verdict(ActionKind.PROCESS_RUN, argv=[gui_or_dangerous]), PolicyVerdict.DENY, gui_or_dangerous)
        self.assertIs(verdict(ActionKind.PROCESS_RUN, argv=[]), PolicyVerdict.DENY)
        self.assertIs(verdict(ActionKind.PROCESS_RUN, argv="python -V"), PolicyVerdict.DENY)

    def test_shell_rules(self):
        self.assertIs(verdict(ActionKind.PROCESS_SHELL, command="dir"), PolicyVerdict.CONFIRM)
        for bad in ("format C: /q", "del /s /q C:\\x", "shutdown /s", "reg delete HKLM\\x", "rm -rf /", ""):
            self.assertIs(verdict(ActionKind.PROCESS_SHELL, command=bad), PolicyVerdict.DENY, bad)

    def test_url_rules(self):
        self.assertIs(verdict(ActionKind.BROWSER_GOTO, url="https://example.com/x"), PolicyVerdict.ALLOW)
        self.assertIs(verdict(ActionKind.BROWSER_GOTO, url="file:///C:/Users/x"), PolicyVerdict.DENY)
        self.assertIs(verdict(ActionKind.BROWSER_GOTO, url="javascript:alert(1)"), PolicyVerdict.DENY)
        self.assertIs(verdict(ActionKind.BROWSER_GOTO, url="http://localhost:8080"), PolicyVerdict.CONFIRM)
        self.assertIs(verdict(ActionKind.BROWSER_GOTO, url="http://192.168.1.1/"), PolicyVerdict.CONFIRM)
        self.assertIs(verdict(ActionKind.BROWSER_GOTO, url="http://[::1]/"), PolicyVerdict.CONFIRM)


if __name__ == "__main__":
    unittest.main()
