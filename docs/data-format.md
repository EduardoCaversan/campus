# Explicit evidence import

`campus import evidence.json` accepts a JSON array. Each observation includes:

```json
[
  {
    "subject": "local:course:AB123:2026-2",
    "kind": "course",
    "field": "name",
    "value": "Example Algorithms",
    "source": "manual",
    "external_ref": "local:teaching-plan",
    "confidence": 1,
    "excerpt": "Synthetic documentation example; replace with the real evidence."
  }
]
```

These are documentation examples only; normal execution never seeds sample academic facts. `observed_at` is an ISO timestamp with timezone, defaults to now, and cannot be in the future. References and excerpts should identify actual evidence. Imports express user-supplied assertions; they are not independent source verification.

## Entity fields

Each field is a separate assertion, allowing contradictory sources and historical values to coexist.

| Kind | Fields used by engines |
| --- | --- |
| `course` | `name`, `code`, `semester`, `section`, `professor`, `grade`, `absences`, `total_units`, `held_units`, `minimum_attendance`, `grading`, `passing_grade`, `grade_scale` |
| `assignment` | `name`, `course` (course subject), `description`, `due_at`, `opens_at`, `submission_state`, `attachments` (URL list), `repository` (explicit local path) |
| `curriculum` | `code`, `name`, `completed` (boolean), `prerequisites` (code list), `workload`, optional `offerings` (term-of-year list), `offerings_confirmed`, `schedule` |
| `mail` | `sender`, `subject`, `date`, `body_excerpt` or `snippet` |
| `document` | `text` |

Attendance fields must share a unit, e.g. class periods; `minimum_attendance` is a fraction between 0 and 1. No default 75% policy is inferred. Workload hours are not automatically converted into class periods.

`grading` is a complete component array: `[{"name":"Exam 1","weight":0.4,"grade":5},{"name":"Exam 2","weight":0.6,"grade":null}]`. Weights must be positive and sum to 1. A null grade is unknown, not zero. The stored passing grade and scale must be explicit before a course calculation is performed.

For curriculum, `completed: false` and `prerequisites: []` must be explicit; a missing prerequisite list is unknown, not proof there are no prerequisites. Current enrollment is not completed. Schedule entries use `{ "day": 1, "start": "10:00", "end": "12:00" }`, with zero-padded 24-hour times. Offerings like `[1]` mean first term of the year and remain estimated unless confirmed evidence says otherwise. The planner's relative terms are not an institutional promise of future availability.

## Course mappings

Identifiers retain provider scope, for example `moodle:course:42`. Automatic correlations require exact code, semester and section; name matches produce suggestions. `campus map-course ALIAS CANONICAL` explicitly joins two known entities. Mapping does not erase conflicting fields or their original evidence.

## State and freshness

Provider health is separate from the freshness and completeness of each fact. Authentication can be healthy while extraction is partial. `last_seen` advances when an identical source assertion is observed again. Evidence keeps its original version timestamp. Old imports do not overwrite newer source assertions. Conflicts remain visible and stale facts never silently become fresh because a health check succeeded.
