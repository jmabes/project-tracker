# 0002 — Carrying import rows from preview to confirm

- Status: Accepted
- Date: 2026-10-01

## Context

Spreadsheet import has two requests:

1. The upload request parses the file and shows a preview of every row.
2. The confirm request saves the valid rows.

Nothing may be written before confirm, and `CLAUDE.md` says uploaded files must
never be kept after the import finishes. So the second request needs the rows from
the first one without the server holding on to the file.

Options considered:

1. **Keep the uploaded file** (in a temp directory or the instance folder) and parse
   it again on confirm. This breaks the "never store uploads" rule. It also needs
   cleanup for previews that are never confirmed.
2. **Server-side pending-import store**: write the parsed rows to a database table
   or file, keyed by a token in the session. This doesn't keep the file itself, but
   it brings back stored state, a cleanup job and a schema change, all for a
   single-user app.
3. **Flask's session cookie.** The default session is a signed cookie, and browsers
   cap a cookie at about 4 KB. That only fits a few dozen rows.
4. **Hidden form field on the preview page**: the preview's confirm form carries the
   valid rows' cleaned values as JSON, and confirm validates them again.

## Decision

Use option 4.

- `importer.preview.encode_rows` writes the valid rows as JSON. Each entry holds
  the row number and its cleaned values, with dates as `YYYY-MM-DD` text. Invalid
  and skipped rows are left out because they wouldn't be imported anyway.
- The confirm form is protected by the app-wide `CSRFProtect`, like every other
  POST.
- `importer.preview.decode_rows` checks only the JSON's shape. The values then go
  through `build_preview` again, which means `validate_project` plus the
  existing-name and in-file duplicate checks. Values edited in the browser, or a
  project added after the preview, therefore can't get past validation.
- If any row no longer passes, nothing is saved and the page shows a fresh preview
  with a notice. The user confirms only what they can see.
- The uploaded file lives only for the upload request. The parser reads it into
  memory and the view closes it. Werkzeug spools uploads over 500 KB to an
  anonymous temporary file, which closing frees. A test checks that it was closed
  and that the temp directory is left empty.

### Size limits

- The confirm form is posted as `application/x-www-form-urlencoded`. In Werkzeug
  3.1.9, `MAX_FORM_MEMORY_SIZE` (default 500 kB) applies only to `multipart/form-data`
  fields, so the hidden field is limited only by `MAX_CONTENT_LENGTH` (2 MB).
- A row with every field filled in is about 215 bytes of JSON, or about 330 bytes once
  the browser URL-encodes it. That leaves room for roughly 6,000 rows, far more than a
  personal project list.

## Consequences

- The server keeps no state between the two requests. That means no cleanup job, no
  new table and no migration. Abandoning a preview leaves nothing behind.
- Confirm validates every row twice: once in `build_preview` and again in
  `services.create_projects`. Both are cheap at this scale.
- Reloading the preview page or confirming twice is safe. The second confirm finds
  every name already taken and saves nothing.
- If imports ever need to be much larger than 2 MB, this choice should be revisited,
  together with the upload limit.

## Links

- Flask config (`MAX_CONTENT_LENGTH`, `MAX_FORM_MEMORY_SIZE`):
  https://flask.palletsprojects.com/en/stable/config/
- Flask file uploads (where uploads are stored):
  https://flask.palletsprojects.com/en/stable/patterns/fileuploads/
- Werkzeug request data limits:
  https://werkzeug.palletsprojects.com/en/stable/request_data/
- Werkzeug `Request.max_form_memory_size` and `_get_file_stream`:
  https://werkzeug.palletsprojects.com/en/stable/wrappers/
