# Workflow Validation Probe

A minimal CLI tool that validates a JSON task list and prints a summary.

## Usage

```bash
python src/workflow_probe.py samples/passed.json
```

## Output

```json
{
  "total": 3,
  "counts": {
    "pending": 0,
    "running": 0,
    "passed": 3,
    "failed": 0
  },
  "failed_task_ids": [],
  "ready": true
}
```

## Task Format

Each task in the `tasks` array must have:
- `id`: non-empty string
- `title`: non-empty string
- `status`: one of `pending`, `running`, `passed`, `failed`
