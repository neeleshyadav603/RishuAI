"""Lexyta LMS (lms.lexyta.com): mark a class meeting's attendance in one go.

Works on the meeting's attendance page open in Rishu's browser. The user says
who is absent / late / excused ("roll 5 aur 12 absent, baaki present"); the
tool finds each student by college roll number (or its last digits) or name,
sets every status on every page, and only locks the attendance when asked.
Page structure: docs/lms/lexyta.md (no student data in the repo).
"""

from __future__ import annotations

import re
import time
from typing import Any

from ..browser import Browser, BrowserError, CdpError
from ..permissions import Risk
from .registry import ToolResult

STATUSES = ("Present", "Late", "Absent", "Excused")

ROWS = r"""() => {
  const rows = [];
  for (const li of document.querySelectorAll('li')) {
    const control = li.querySelector('[testid="attendance-mark"], lexyta-segmented-control');
    const user = li.querySelector('lms-user-column');
    if (!control || !user) continue;
    // Text of the leaf elements (name, roll number, e-mail), whatever the layout.
    const lines = Array.from(user.querySelectorAll('*')).filter((e) => e.children.length === 0)
      .map((e) => R.squash(e.textContent)).filter(Boolean);
    const email = lines.find((l) => l.includes('@')) || '';
    const roll = lines.find((l) => /\d/.test(l) && !l.includes('@')) || '';
    const name = lines.find((l) => l !== email && l !== roll) || '';
    const selected = Array.from(control.querySelectorAll('[role=tab]')).find((t) => t.getAttribute('aria-selected') === 'true');
    rows.push({ name, roll, current: selected ? R.squash(selected.innerText) : '' });
  }
  const pager = (R.squash(document.body.innerText).match(/\d+\s*-\s*\d+ of \d+ items/) || [''])[0];
  const next = Array.from(document.querySelectorAll('button, a')).find((b) => R.squash(b.innerText).toLowerCase() === 'next');
  const nextOk = !!next && !next.disabled && next.getAttribute('aria-disabled') !== 'true' && R.visible(next);
  return { rows, pager, nextOk, url: location.href };
}"""

SET = r"""(roll, name, status) => {
  for (const li of document.querySelectorAll('li')) {
    const control = li.querySelector('[testid="attendance-mark"], lexyta-segmented-control');
    const user = li.querySelector('lms-user-column');
    if (!control || !user) continue;
    const text = R.squash(user.innerText);
    if ((roll && !text.includes(roll)) || (!roll && !text.includes(name))) continue;
    const tab = Array.from(control.querySelectorAll('[role=tab]')).find((t) => R.squash(t.innerText).toLowerCase() === status.toLowerCase());
    if (!tab) return { ok: false, reason: 'no ' + status + ' button' };
    if (tab.getAttribute('aria-selected') !== 'true') tab.click();
    return { ok: true };
  }
  return { ok: false, reason: 'row not on this page' };
}"""

PAGE = r"""(label) => {
  const b = Array.from(document.querySelectorAll('button, a')).find((x) => R.squash(x.innerText).toLowerCase() === label.toLowerCase());
  if (!b || b.disabled) return false;
  b.click();
  return true;
}"""

LOCK = r"""() => {
  const b = document.querySelector('[lexytatestid="attendance-lock"]');
  if (!b || b.disabled) return { ok: false };
  b.click();
  return { ok: true };
}"""

DIALOG = r"""() => {
  const d = Array.from(document.querySelectorAll('[role=dialog], [role=alertdialog]')).find(R.visible);
  return d ? R.squash(d.innerText).slice(0, 300) : '';
}"""


def _trailing_number(roll: str) -> int | None:
    match = re.search(r"(\d+)\D*$", roll)
    return int(match.group(1)[-3:]) if match else None


def match_student(token: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows meant by "5", "12", "22CSE005" or "Aryan"."""
    token = token.strip()
    if not token:
        return []
    low = token.lower()
    if token.isdigit() and len(token) <= 3:
        wanted = int(token)
        return [r for r in rows if _trailing_number(r["roll"]) == wanted]
    exact = [r for r in rows if r["roll"].lower() == low]
    if exact:
        return exact
    if any(ch.isdigit() for ch in token):
        return [r for r in rows if r["roll"].lower().endswith(low)]
    same = [r for r in rows if " ".join(r["name"].lower().split()) == " ".join(low.split())]
    if len(same) == 1:
        return same
    words = low.split()
    return [r for r in rows if all(w in r["name"].lower() for w in words)]


class LexytaAttendance:
    def __init__(self, browser: Browser, sleep: Any = time.sleep):
        self.browser = browser
        self._sleep = sleep

    def _rows(self) -> dict[str, Any]:
        return self.browser.run(ROWS) or {"rows": [], "pager": "", "nextOk": False}

    def _go_first_page(self) -> None:
        for _ in range(20):
            page = self._rows()
            if not page.get("pager") or page["pager"].replace(" ", "").startswith("1-"):
                return
            if not self.browser.run(PAGE, "1") and not self.browser.run(PAGE, "Previous"):
                return
            self._wait_change(page.get("pager", ""))

    def _wait_change(self, pager: str) -> None:
        for _ in range(30):
            self._sleep(0.2)
            now = self._rows()
            if now.get("pager") != pager and now.get("rows"):
                return

    def _pages(self):
        """Yield each page's rows, moving with the "Next" button."""
        self._go_first_page()
        for _ in range(30):
            page = self._rows()
            yield page
            if not page.get("nextOk"):
                return
            self.browser.run(PAGE, "Next")
            self._wait_change(page.get("pager", ""))

    def mark(
        self,
        absent: list[str] | None = None,
        late: list[str] | None = None,
        excused: list[str] | None = None,
        everyone_else: str = "present",
        lock: bool = False,
    ) -> ToolResult:
        try:
            url = self.browser.run("() => location.href", timeout=5) or ""
        except (BrowserError, CdpError) as exc:
            return ToolResult(False, f"Rishu's browser is not open: {exc}")
        if "lexyta" not in url or "/attendance" not in url:
            return ToolResult(
                False,
                "Open the meeting's attendance page in Rishu's browser first: Lexyta → the class → "
                "Meetings → the meeting → Attendance (browser_open https://lms.lexyta.com, then click through), "
                "then call this again.",
            )
        try:
            everyone: list[dict[str, Any]] = []
            for page in self._pages():
                everyone.extend(page.get("rows", []))
        except (BrowserError, CdpError) as exc:
            return ToolResult(False, f"Could not read the attendance list: {exc}")
        if not everyone:
            return ToolResult(False, "No students were found on this attendance page.")

        wanted: dict[str, tuple[str, dict[str, Any]]] = {}
        problems: list[str] = []
        for status, tokens in (("Absent", absent), ("Late", late), ("Excused", excused)):
            for token in tokens or []:
                found = match_student(str(token), everyone)
                if len(found) == 1:
                    wanted[found[0]["roll"] or found[0]["name"]] = (status, found[0])
                elif not found:
                    problems.append(f'no student matches "{token}"')
                else:
                    who = ", ".join(f"{r['name']} ({r['roll']})" for r in found[:4])
                    problems.append(f'"{token}" matches more than one student: {who}')
        if problems:
            return ToolResult(
                False,
                "Nothing was changed. Please check: "
                + "; ".join(problems)
                + ". Ask the user and call again.",
                untrusted=True,
                source=url,
            )

        rest = {"present": "Present", "absent": "Absent", "none": ""}.get(
            everyone_else.lower(), "Present"
        )
        changed, failed = 0, []
        try:
            for page in self._pages():
                for row in page.get("rows", []):
                    key = row["roll"] or row["name"]
                    status = wanted[key][0] if key in wanted else rest
                    if not status or row.get("current", "").lower() == status.lower():
                        continue
                    done = self.browser.run(SET, row["roll"], row["name"], status) or {}
                    if done.get("ok"):
                        changed += 1
                    else:
                        failed.append(f"{row['name']}: {done.get('reason', 'failed')}")
                self._sleep(0.3)
            # Check what the page shows now.
            final: dict[str, str] = {}
            for page in self._pages():
                for row in page.get("rows", []):
                    final[row["roll"] or row["name"]] = row.get("current", "")
        except (BrowserError, CdpError) as exc:
            return ToolResult(
                False, f"Stopped while marking: {exc}. Some statuses may already be set."
            )

        wrong = [
            f"{info['name']} should be {status}"
            for key, (status, info) in wanted.items()
            if final.get(key, "").lower() != status.lower()
        ]
        counts: dict[str, int] = {}
        for value in final.values():
            counts[value or "Not marked"] = counts.get(value or "Not marked", 0) + 1
        summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        marked = (
            "; ".join(
                f"{info['name']} ({info['roll']}) → {status}" for status, info in wanted.values()
            )
            or "nobody named"
        )
        text = f"Attendance set for {len(final)} students ({summary}). Named: {marked}. Changed {changed} statuses."
        if failed or wrong:
            text += " Problems: " + "; ".join(failed + wrong)
        if lock:
            if failed or wrong:
                text += " Not locked because of the problems above."
            else:
                clicked = (self.browser.run(LOCK) or {}).get("ok")
                self._sleep(1.0)
                dialog = self.browser.run(DIALOG) if clicked else ""
                if not clicked:
                    text += " The 'Submit & lock attendance' button was not available."
                elif dialog:
                    text += f" Clicked 'Submit & lock attendance'; a confirmation box is open: \"{dialog}\". Ask the user to confirm it in the browser."
                else:
                    text += " Submitted and locked."
        else:
            text += " Not locked yet (the user can say 'lock kar do')."
        return ToolResult(not (failed or wrong), text, untrusted=True, source=url)


def _preview(args: dict[str, Any]) -> str:
    def names(key: str) -> str:
        items = args.get(key) or []
        return ", ".join(str(i) for i in items) if items else "—"

    rest = str(args.get("everyone_else", "present")).lower()
    rest_text = {
        "present": "everyone else PRESENT",
        "absent": "everyone else ABSENT",
        "none": "others unchanged",
    }.get(rest, "everyone else PRESENT")
    lock = (
        " Then SUBMIT & LOCK the attendance (cannot be undone)."
        if args.get("lock")
        else " Do not lock yet."
    )
    return (
        f"On the open Lexyta attendance page: ABSENT: {names('absent')}; LATE: {names('late')}; "
        f"EXCUSED: {names('excused')}; {rest_text}.{lock}"
    )


def register(registry: Any, browser: Browser) -> LexytaAttendance:
    from . import Tool, _obj

    tool = LexytaAttendance(browser)
    roll_list = {
        "type": "array",
        "items": {"type": "string"},
        "description": 'College roll numbers, their last digits ("5", "12") or names',
    }
    registry.register(
        Tool(
            name="lexyta_mark_attendance",
            description=(
                "Lexyta LMS: mark a class meeting's attendance in one go on the attendance page open in "
                "Rishu's browser. Give who is absent / late / excused; everyone else becomes present "
                "(or absent / unchanged). lock=true also clicks 'Submit & lock attendance' — only when the "
                "user asks to lock or submit."
            ),
            parameters=_obj(
                {
                    "absent": roll_list,
                    "late": roll_list,
                    "excused": roll_list,
                    "everyone_else": {"type": "string", "enum": ["present", "absent", "none"]},
                    "lock": {"type": "boolean"},
                }
            ),
            risk=Risk.R2,
            handler=tool.mark,
            untrusted_output=True,
            preview_fn=_preview,
            skill="lexyta_attendance",
        )
    )
    return tool
