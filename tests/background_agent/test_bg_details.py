import unittest

import helpers  # noqa: F401
from background_agent import Action, ActionKind, ConfirmationRequest
from background_agent.actions import sanitize_for_display


class ActionDetailsTests(unittest.TestCase):
    def test_shell_and_run_show_the_full_command(self):
        self.assertEqual(Action(ActionKind.PROCESS_SHELL, {"command": "dir C:\\Users /s"}).details(), "dir C:\\Users /s")
        self.assertEqual(Action(ActionKind.PROCESS_RUN, {"argv": ["python", "-c", "print('a b')"]}).details(),
                         subprocess_quote(["python", "-c", "print('a b')"]))
        self.assertIn("[in sub]", Action(ActionKind.PROCESS_SHELL, {"command": "x", "cwd": "sub"}).details())

    def test_file_actions(self):
        self.assertEqual(Action(ActionKind.FS_DELETE, {"path": "a", "recursive": True}).details(), "a (recursive)")
        self.assertEqual(Action(ActionKind.FS_MOVE, {"src": "a", "dst": "b", "overwrite": True}).details(), "a -> b (will overwrite)")

    def test_write_details_show_size_never_content(self):
        d = Action(ActionKind.FS_WRITE, {"path": "p.txt", "content": "TOP-SECRET", "overwrite": True}).details()
        self.assertEqual(d, "p.txt (10 bytes) (will overwrite)")
        self.assertNotIn("TOP-SECRET", d)

    def test_url(self):
        self.assertEqual(Action(ActionKind.BROWSER_GOTO, {"url": "http://localhost:9/x?a=1"}).details(), "http://localhost:9/x?a=1")

    def test_spoofing_characters_are_made_visible(self):
        nasty = "ls\n\rok \u202e txt.exe \u2066 \x1b[2J \x00"
        out = Action(ActionKind.PROCESS_SHELL, {"command": nasty}).details()
        for ch in ("\n", "\r", "\u202e", "\u2066", "\x1b", "\x00"):
            self.assertNotIn(ch, out)
        self.assertIn("\\u202e", out)
        self.assertIn("\\u000a", out)

    def test_length_is_capped(self):
        out = Action(ActionKind.PROCESS_SHELL, {"command": "x" * 5000}).details(max_chars=100)
        self.assertEqual(len(out), 100)
        self.assertTrue(out.endswith("\u2026"))
        self.assertEqual(len(sanitize_for_display("y" * 10, 100)), 10)

    def test_malformed_params_do_not_crash(self):
        for params in ({}, {"argv": "python"}, {"argv": [1, 2]}, {"path": None}):
            for kind in (ActionKind.PROCESS_RUN, ActionKind.FS_DELETE, ActionKind.FS_WRITE):
                Action(kind, params).details()

    def test_confirmation_request_details_is_optional_and_backward_compatible(self):
        r = ConfirmationRequest("t", ActionKind.FS_DELETE, "s", "r")
        self.assertEqual(r.details, "")


def subprocess_quote(argv):
    import subprocess
    return subprocess.list2cmdline(argv)


if __name__ == "__main__":
    unittest.main()
