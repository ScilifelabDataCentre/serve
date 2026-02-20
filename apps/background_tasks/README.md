# Background Task Framework

A comprehensive framework for running validation and external API tasks before app deployment.

Background tasks are triggered during deployment via `apps.helpers.create_instance_from_form()` which enqueues
`apps.tasks.run_background_tasks` (Celery). The orchestrator runs registered tasks, blocks deployment if any
**critical** task fails, and otherwise proceeds to deployment.

## Feature flags (django-waffle)

- **`background_tasks` (switch)**: Enables the background-task orchestrator (instead of direct deployment).
- **`background_tasks_nonblocking_deploy` (switch)**:
  - **OFF (default)**: failed *critical* background tasks block deployment (current behavior).
  - **ON**: deployment proceeds even if critical background tasks fail (tasks are still recorded as failed).

## Overview

The background task framework provides:

- **Extensible Task System**: Easy-to-add new tasks using decorators
- **Sequential & Parallel Execution**: Control task execution order
- **Automatic Retry**: Configurable retry logic with exponential backoff
- **Manual Retry**: UI for manually retrying failed tasks
- **Task Monitoring**: Views for per-app and admin-wide task status
- **Critical vs Optional Tasks**: Block deployment on critical failures

## Architecture

```
Form Submission
    ↓
create_instance_from_form()
    ↓
transaction.on_commit(run_background_tasks.delay(instance.serialize(), app_slug))
    ↓
run_background_tasks() [Celery Task; creates BackgroundTask rows]
    ↓
Execute tasks by execution_order (parallel within same order)
    ↓
check_tasks_and_deploy() [Celery Task]
    ↓
deploy_resource() [if all critical tasks pass]
```

## Quick Start

### 1. Creating a New Task

Create your task class by extending `BaseBackgroundTask`:

```python
from apps.background_tasks.base import BaseBackgroundTask
from apps.background_tasks.registry import TASK_REGISTRY

@TASK_REGISTRY.register(
    name='my_validation_task',
    is_critical=True,          # Blocks deployment if fails
    execution_order=1,         # Lower numbers run first
    app_types=['customapp']    # Or None for all app types
)
class MyValidationTask(BaseBackgroundTask):
    max_retries = 3
    task_type = "validation"  # Options: validation, external_api, post_deploy
    timeout_seconds = 60

    def execute(self, app_instance, **kwargs):
        """
        Your task logic here.
        Raise an exception if task should fail.
        Return a dict with result data.
        """
        # Validation logic
        if not some_condition:
            raise ValueError("Validation failed!")

        return {
            "success": True,
            "some_data": "value"
        }
```

#### Where configuration lives

- **Registration metadata** (what name/order/criticality/app-types this task has) is passed to the decorator and is
  **written onto the class** by the registry:
  - `task_name`, `execution_order`, `is_critical`, `app_types`
- **Execution behavior** (retry policy, type, timeout) remains on the class:
  - `max_retries`, `task_type`, `timeout_seconds`, plus optional overrides like `should_retry()` / `get_retry_delay()`

### 2. Task Registration

Tasks are registered when their module is imported. This repo uses a single explicit
entrypoint to ensure deterministic startup registration:

```python
# apps/background_tasks/load.py
_TASK_MODULES = (
    "apps.background_tasks.tasks.validation",
    # "apps.background_tasks.tasks.my_tasks",
)
```

That entrypoint is called from `apps/apps.py`:

```python
class AppsConfig(AppConfig):
    def ready(self):
        from apps.background_tasks.load import register_tasks

        register_tasks()
```

### 3. Task Configuration

#### Execution Order

Tasks with lower `execution_order` run first. Tasks with the same order run in parallel:

```python
@TASK_REGISTRY.register(name='task1', execution_order=0)  # Runs first
@TASK_REGISTRY.register(name='task2', execution_order=0)  # Runs in parallel with task1
@TASK_REGISTRY.register(name='task3', execution_order=1)  # Runs after task1 & task2
```

#### Critical vs Optional

- **Critical tasks (`is_critical=True`)**: Deployment is blocked if they fail
- **Optional tasks (`is_critical=False`)**: Deployment continues even if they fail

```python
@TASK_REGISTRY.register(name='docker_validation', is_critical=True)
@TASK_REGISTRY.register(name='invenio_record', is_critical=False)
```

#### App Type Filtering

Restrict tasks to specific app types:

```python
@TASK_REGISTRY.register(
    name='docker_validation',
    app_types=['customapp', 'gradio', 'streamlit']
)
```

Or apply to all apps:

```python
@TASK_REGISTRY.register(
    name='subdomain_check',
    app_types=None  # Runs for all app types
)
```

## Task Lifecycle

### 1. Automatic Retry

Tasks automatically retry on failure using exponential backoff:

```python
class MyTask(BaseBackgroundTask):
    max_retries = 3  # Try up to 3 times

    def should_retry(self, error, retry_count):
        # Custom retry logic
        if isinstance(error, ValidationError):
            return False  # Don't retry validation errors
        return retry_count < self.max_retries

    def get_retry_delay(self, retry_count):
        # Custom backoff (capped at 5 minutes): 15s, 75s, 300s...
        return min(15 * (5**retry_count), 300)
```

#### Idempotency / duplicate delivery

`execute_single_background_task` has an idempotency guard: if a task row is already `running`/`success`/`failed`, it
returns early instead of re-running the same row.

### 2. Task Hooks

Override these methods for custom behavior:

```python
class MyTask(BaseBackgroundTask):
    def on_success(self, app_instance, result):
        """Called when task succeeds"""
        logger.info(f"Task completed: {result}")

    def on_failure(self, app_instance, error):
        """Called when task fails"""
        # Custom error handling
        send_alert_to_slack(error)

    def validate_inputs(self, app_instance, **kwargs):
        """Called before execution"""
        if not app_instance.image:
            raise ValidationError("Image is required")
```

## Monitoring Tasks

### User View (Per-App)

View tasks for a specific app:

```
/projects/<project>/apps/tasks/<app_slug>/<app_id>
```

Features:
- Real-time status updates (polls every 3 seconds)
- Task details with error messages
- Manual retry button for failed tasks
- Summary statistics

### Admin View (All Tasks)

View all tasks across all apps (superuser only):

```
/projects/<project>/apps/admin/background-tasks
```

Features:
- Filter by status, app type, critical flag
- Pagination
- Detailed task information
- Search by task name or app

### API Endpoint

Get task status programmatically:

```
GET /projects/<project>/apps/tasks/<app_slug>/<app_id>/status

Response:
{
    "tasks": [
        {
            "id": 1,
            "task_name": "validate_docker_image",
            "status": "success",
            "is_critical": true,
            "duration_seconds": 5.23,
            ...
        }
    ],
    "summary": {
        "total": 3,
        "pending": 0,
        "running": 0,
        "success": 3,
        "failed": 0,
        "retrying": 0
    }
}
```

## Example Tasks

### Docker Image Validation

Located in `apps/background_tasks/tasks/validation.py`:

```python
@TASK_REGISTRY.register(
    name='validate_docker_image',
    is_critical=True,
    execution_order=1,
    app_types=['customapp', 'jupyter', 'rstudio']
)
class DockerImageValidator(BaseBackgroundTask):
    """Validates Docker image architecture"""

    def execute(self, app_instance, **kwargs):
        from apps.validators.container_images import get_image_architectures

        image = app_instance.image
        architectures = get_image_architectures(...)

        if 'amd64' not in [arch.arch for arch in architectures]:
            raise ValueError(f"Image {image} missing amd64 architecture")

        return {"architectures": architectures}
```

### External API tasks

There is no `apps/background_tasks/tasks/external_api.py` module in this repo. To add an external API task, create a
module under `apps/background_tasks/tasks/`, register the task with `@TASK_REGISTRY.register(...)`, and import the
module by adding it to `_TASK_MODULES` in `apps/background_tasks/load.py` so it is registered on startup.

## Database Model

Tasks are tracked in the `BackgroundTask` model:

```python
BackgroundTask
├── app_instance (ForeignKey)
├── task_name (str)
├── task_type (validation/external_api/post_deploy)
├── status (pending/running/success/failed/retrying)
├── is_critical (bool)
├── execution_order (int)
├── result_data (JSON)
├── error_message (text)
├── retry_count (int)
├── max_retries (int)
├── created_at (datetime)
├── started_at (datetime)
├── completed_at (datetime)
└── celery_task_id (str)
```

## Testing

### Unit Tests

Test your tasks:

```python
from apps.background_tasks.registry import TASK_REGISTRY
from apps.models import BaseAppInstance

def test_my_task():
    task_class = TASK_REGISTRY.get_task_class('my_validation_task')
    task = task_class()

    app_instance = BaseAppInstance.objects.get(pk=1)
    result = task.execute(app_instance)

    assert result['success'] is True
```

### Integration Tests

Test the full workflow:

```python
def test_background_task_workflow():
    from apps.tasks import run_background_tasks

    instance = create_test_app_instance()
    result = run_background_tasks(instance.serialize(), 'customapp')

    tasks = BackgroundTask.objects.filter(app_instance=instance)
    assert tasks.filter(status='success').count() == tasks.count()
```

## Troubleshooting

### Task Not Running

1. Check if task is registered:
   ```python
   from apps.background_tasks.registry import TASK_REGISTRY
   print(list(TASK_REGISTRY.get_all_tasks().keys()))
   ```

2. Verify app type filter:
   ```python
   tasks = TASK_REGISTRY.get_tasks_for_app('customapp')
   print([t.task_name for t in tasks])
   ```

3. Check Celery worker logs:
   ```bash
   docker logs <celery-worker-container>
   ```

### Task Failing Repeatedly

1. View error in admin or task view
2. Check task-specific logs
3. Adjust retry logic or fix underlying issue
4. Manually retry from UI

### Deployment Blocked

1. Check which critical tasks failed
2. View error messages in task detail view
3. Fix issue and manually retry task
4. Or edit app to fix validation issues

### Error Details

On failures, the task row stores:

- `error_message`: a human-readable string for quick display
- `result_data["error"]`: structured details (exception type/module/message/traceback and stage)

## Best Practices

1. **Keep tasks focused**: One task per validation/operation
2. **Use appropriate criticality**: Don't block deployment unnecessarily
3. **Set reasonable timeouts**: Avoid hanging tasks
4. **Log liberally**: Makes debugging easier
5. **Test thoroughly**: Unit test task logic
6. **Handle errors gracefully**: Use custom `on_failure()` handlers
7. **Document task purpose**: Clear docstrings help maintainability

## Advanced Usage

### Custom Task Base Class

Create specialized base classes:

```python
class ValidationTaskBase(BaseBackgroundTask):
    task_type = "validation"
    max_retries = 2

    def on_failure(self, app_instance, error):
        # Common validation failure handling
        notify_validation_team(error)
```

### Dynamic Task Registration

Register tasks conditionally:

```python
if settings.FEATURE_FLAG_ENABLED:
    @TASK_REGISTRY.register(name='new_feature_validation')
    class NewFeatureValidator(BaseBackgroundTask):
        ...
```

### Task Chaining

Create dependencies between tasks using execution_order:

```python
@TASK_REGISTRY.register(name='step1', execution_order=0)
@TASK_REGISTRY.register(name='step2', execution_order=1)
@TASK_REGISTRY.register(name='step3', execution_order=2)
```

## Migration Guide

### From Direct Deployment

Old code:
```python
if do_deploy:
    deploy_resource.delay(instance.serialize())
```

New code (automatically integrated):
```python
if do_deploy:
    run_background_tasks.delay(instance.serialize(), app_slug)
    # Orchestrator handles deployment after tasks
```

### Adding First Task

1. Create task class in `apps/background_tasks/tasks/`
2. Register with `@TASK_REGISTRY.register()`
3. Add the module to `_TASK_MODULES` in `apps/background_tasks/load.py`
4. Create and run migration if needed
5. Tasks automatically run on next app creation

## Performance Considerations

- **Parallel Execution**: Tasks with same order run simultaneously
- **Async by Default**: All tasks run via Celery (non-blocking)
- **Timeout Protection**: Tasks have configurable timeouts
- **Resource Limits**: Consider task concurrency in production

## Security

- **Permission Checks**: Views enforce project-level permissions
- **Input Validation**: Use `validate_inputs()` method
- **Safe Serialization**: App instances serialized before passing to Celery
- **CSRF Protection**: All POST requests protected

## Support

For issues or questions:
- Check logs: Django logs and Celery worker logs
- Review task status in admin view
- Check error messages in task detail view
- Contact: serve@scilifelab.se
