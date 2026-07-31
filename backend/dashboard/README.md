# Dashboard

A read-only UI over `backend/audit/`'s `scan_audit_log` table - the visual piece the
audit-logging work always described itself as "backing." No writes happen here;
`backend/audit/audit_logger.py` remains the only writer.

## Where this sits

```
Browser                              backend/dashboard/
┌──────────────┐  GET /dashboard/    ┌────────────────────────────┐
│  Sign in,    │────────────────────▶│ static/index.html + app.js │
│  view trail  │  Authorization:     │   -> GET /dashboard/api/*   │
└──────────────┘  Bearer <token>     │      (queries.py reads      │
                                      │       audit_log.db)         │
                                      └────────────────────────────┘
```

- Login uses the **same** `backend/auth/` accounts as device management -
  `POST /auth/login`, same bearer token. No separate dashboard login system.
- **Admin role required for the entire dashboard** (`Depends(require_role("admin"))`
  on both endpoints) - since `scan_audit_log` always includes the raw prompt (see
  `backend/audit/README.md`), there's no reduced-visibility view for `viewer`
  accounts today. A `viewer` can still authenticate elsewhere (e.g. `backend/auth/`'s
  own endpoints) but gets `403 Forbidden` from anything under `/dashboard/`.
- Mounted as its own sub-app at `/dashboard` in `app.py`, alongside `/auth` and
  `/devices`, with the same restrictive (non-wildcard) CORS policy - see
  `app.py`'s comment on why a single `CORSMiddleware` can't express different
  policies for different route groups.

## Module layout

| Path | Responsibility |
|---|---|
| `queries.py` | Read-only SQL over `audit_log.db` - `get_stats()`, `get_events()`. Never writes. |
| `routes.py` | Two JSON endpoints, both behind `require_role("admin")`: `GET /api/stats`, `GET /api/events` |
| `static/index.html` | Login screen + dashboard shell |
| `static/style.css` | Palette lifted directly from `browser-extension/popup/popup.css` and `content/modal.js` - see "Styling" below |
| `static/app.js` | Vanilla JS - login flow, fetch + render, filters, pagination. No build step, no framework, same approach as `browser-extension/`. |

## Styling: matches the extension, not a generic dashboard

Every color in `style.css` was pulled from the existing browser extension rather
than picked fresh:

- Background gradient, text/muted/accent colors, border, glass-panel blur: copied
  from `browser-extension/popup/popup.css`'s `:root` custom properties.
- Status colors (green/amber/red): copied from `browser-extension/content/modal.js`'s
  `.status-safe`/`.status-sanitize`/`.status-block` styles.

**One addition**: the extension only has 3 client-facing statuses (`SAFE`/
`SANITIZE`/`BLOCK`, since `WARN` and `MASK` both collapse to `SANITIZE` there - see
`backend/policy/README.md`). The dashboard shows the full 4-value `decision`
(`ALLOW`/`WARN`/`MASK`/`BLOCK`) since that distinction matters for an audit view, so
it needed a 4th status step between amber and red. Added **orange** (`#fb923c`
family) for `MASK`, following the same lightness/opacity pattern as the existing
three rather than picking an arbitrary new hue.

### Why the bar charts are single-color, not multi-color

The layer-breakdown and LLM-provider charts give each category its own row with a
direct text label - per the dataviz skill's color-formula guidance, coloring each
bar differently would "spend the identity channel" on something the label already
shows. So every bar in those two charts shares one accent hue (`--accent`, the
extension's existing sky blue); only the decisions-over-time chart uses multiple
colors, because there each color is a status (`ALLOW`/`WARN`/`MASK`/`BLOCK`)
genuinely shown side by side in the same stacked column.

**Not run in this environment**: the dataviz skill's automated palette validator
(`validate_palette.js`) needs Node, which wasn't available here. The status colors
are direct reuses of already-shipped extension colors (so already implicitly
vetted by being in production), and the one new color (orange) follows the same
lightness/opacity formula as its neighbors - but this wasn't run through the
validator's CVD-separation checks. Worth doing if Node becomes available.

## API

Both endpoints require `Authorization: Bearer <token>` from an `admin`-role
account (same tokens `/auth/login` issues; a `viewer` token gets `403`):

- `GET /dashboard/api/stats?days=7` - summary counts, decision/layer/provider
  breakdowns, and a daily decision trend for the last N days (1-90).
- `GET /dashboard/api/events?limit=&offset=&decision=&platform=&search=` - paginated
  event rows. `search` matches `masked_prompt`/`raw_prompt`/`username`/`reason`
  (substring, case-insensitive). Every event includes both `maskedPrompt` and
  `rawPrompt` - access control happens once, at the route level (admin-only),
  not by selectively withholding fields per role.

## "Layer" bucketing

`queries.py`'s `_LAYER_BY_DECISION_PATH` maps the pre-classifier's fine-grained
`decision_path` (e.g. `semantic_confirmed_public`, `true_ambiguity`) onto the
coarser buckets the original dashboard proposal called "which layer is
responsible": `Presidio`, `Pre-Classifier (Lexical)`, `Pre-Classifier (Semantic)`,
`ECI (LLM)`, or `Unknown` (rows written before the `decision_path` column existed).

## Local development

```
uvicorn app:app --reload --port 8081
```
then open `http://localhost:8081/dashboard/` and sign in with a dashboard account
(`python scripts/create_admin.py` if you don't have one yet).
