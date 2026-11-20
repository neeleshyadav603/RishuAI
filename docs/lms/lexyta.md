# Lexyta LMS (lms.lexyta.com) — page structure

From pages the owner saved on 20 Nov 2026 (structure only; no student data is
kept in this repo). Lexyta is an Angular app; elements carry stable
`lexytatestid` / `testid` attributes, which the attendance skill prefers over
CSS classes.

## URLs

- Sign in: `/signin?returnUrl=…` (Email, Password, "Sign in", also "Sign in with QR code").
  Rishu never types the password: the user signs in once in Rishu's browser window.
- Home `/`, courses `/my-courses`, course modules `/my-courses/{courseId}/modules`
- Classes `/classes`, one class `/classes/{classId}` with tabs:
  `overview`, `students`, `meetings`, `assignments`, `reports`, `announcements`, `staff`
- Meetings: `/classes/{classId}/meetings` — table Title / Start Time / End Time /
  Duration / Provider / Status ("Scheduled", "Ended"); "Add Meeting" button;
  only finished meetings count for attendance.
- Attendance: `/classes/{classId}/meetings/{meetingId}/attendance`
- Gradebook (seen as a link on the home page): `/classes/{classId}/assignments/{assignmentId}/gradebook`
  — pages not yet received (see `docs/NEEDS_USER.md`).

## Attendance page

- Header: "Meeting attendance", "Class Meeting · {date}".
- Search: `input[lexytatestid=search-input]` + button `lexytatestid=search-submit`.
- Summary `lexyta-bar-graph[testid=attendance-summary]`: "Roll call", "N of M still to mark",
  counts for Present / Late / Absent / Excused / Not marked.
- Bulk buttons: "Import CSV" (with an options toggle), "Mark remaining as absent",
  "Mark remaining as present", "Submit & lock attendance" (`lexytatestid=attendance-lock`).
- Table `lexyta-table[paginate]`, 20 rows per page, paginator buttons "1 2 3 4" and
  "Next", text "1-20 of M items".
- Row (`li`): `lms-user-column` with the name, the college roll number and the e-mail;
  `lexyta-segmented-control[testid=attendance-mark]` → `div[role=tablist][aria-label="Attendance status"]`
  with four `button[role=tab]` labelled "Present", "Late", "Absent", "Excused"
  (`aria-selected` shows the current one); the status text
  `span[lexytatestid=attendance-status][data-status=PRESENT|ABSENT|…]`; a clear
  button `lexytatestid=attendance-clear`.
- Select-all checkbox `aria-label="Select all students on this page"`, row checkbox
  `aria-label="Select student"`.

## Rows Rishu reads

- Home: `a[lexytatestid=teaching-class-row]` per class the user teaches (links to `/classes/{id}`),
  gradebook links `/classes/{id}/assignments/{id}/gradebook`.
- Meetings list: `li` rows (pointer cursor, no role) containing `div[lexytatestid=professor-meeting-row]`
  with title, start time, end, duration, provider and a status badge; a row menu button (ellipsis);
  menu `lexyta-menu-select[testid=meetings-attendance-lock-menu]` above the list.
- Attendance row: `li` > `lms-user-column` (leaf spans: name, college roll number, e-mail) +
  `lexyta-segmented-control[testid=attendance-mark]` > `[role=tablist]` > four `button[role=tab]`.
  `lexyta_mark_attendance` reads the leaf spans, so the layout (flex column or inline) does not matter.
