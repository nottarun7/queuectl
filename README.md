# QueueCTL - Background Job Queue System

A CLI-based background job queue system built with Python, featuring automatic retries with exponential backoff, Dead Letter Queue (DLQ) management, and persistent storage using SQLite.

[![Watch the demo](./video.mp4)](./video.mp4)


## Features

**CLI-Based Interface** - Easy-to-use command-line interface  
**Background Job Processing** - Multiple worker processes execute jobs concurrently  
**Automatic Retries** - Configurable retry logic with exponential backoff  
**Dead Letter Queue** - Failed jobs moved to DLQ after max retries  
**Persistent Storage** - SQLite-based persistence survives restarts  
**Graceful Shutdown** - Workers handle shutdown signals properly  
**Configurable Settings** - Adjust retry policies, timeouts, and more  
**Job State Tracking** - Monitor job status (pending, processing, completed, failed, dlq)  
**Worker Management** - Start/stop multiple workers dynamically

## Architecture

```
queuectl/
├── __init__.py           # Package initialization
├── cli.py                # CLI command handling (argparse)
├── queue.py              # Core job queue logic
├── worker.py             # Worker process management
├── storage.py            # SQLite persistence layer
├── config.py             # Configuration management
└── utils.py              # Helper functions
```

### Component Overview

- **Storage Layer** (`storage.py`): Handles SQLite database operations for jobs and workers
- **Queue Manager** (`queue.py`): Manages job lifecycle, state transitions, and DLQ
- **Worker Manager** (`worker.py`): Spawns and manages worker processes using multiprocessing
- **Configuration** (`config.py`): Centralized configuration with file-based persistence
- **CLI** (`cli.py`): User-facing command-line interface
- **Utilities** (`utils.py`): Command execution, logging, and helper functions

## Installation

### Requirements

- Python 3.7+
- pip

### Setup

1. **Clone or download the project:**
   ```bash
   cd c:\Projects\FLAM
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install QueueCTL:**
   ```bash
   pip install -e .
   ```

   This installs `queuectl` as a command-line tool.

## Usage

### Quick Start

```bash
# 1. Enqueue a job
queuectl enqueue '{"id":"job1","command":"echo Hello World"}'

# 2. Start workers
queuectl worker start --count 3

# 3. Check status
queuectl status

# 4. Stop workers
queuectl worker stop
```

### Command Reference

#### **Enqueue a Job**

Add a new job to the queue:

```bash
queuectl enqueue '{"id":"unique-job-id","command":"your-shell-command"}'
```

Example:
```bash
queuectl enqueue '{"id":"job1","command":"echo Processing data"}'
queuectl enqueue '{"id":"job2","command":"python script.py"}'
queuectl enqueue '{"id":"job3","command":"curl https://api.example.com"}'
```

#### **Worker Management**

Start worker processes:
```bash
queuectl worker start --count 3
```

Stop all workers:
```bash
queuectl worker stop
```

#### **Check Status**

View queue and worker statistics:
```bash
queuectl status
```

Output:
```
=== QueueCTL Status ===

Jobs:
State        Count
-----------  -------
Pending            5
Processing         2
Completed         10
Failed             1
DLQ                0
Total             18

Workers:
Status    Count
--------  -------
Active          3
Total           3
```

#### **List Jobs**

List all jobs:
```bash
queuectl list
```

Filter by state:
```bash
queuectl list --state pending
queuectl list --state completed
queuectl list --state failed
queuectl list --state processing
queuectl list --state dlq
```

Limit results:
```bash
queuectl list --state completed --limit 50
```

#### **Dead Letter Queue (DLQ)**

List jobs in DLQ:
```bash
queuectl dlq list
```

Retry a failed job:
```bash
queuectl dlq retry job1
```

#### **Configuration Management**

View all configuration:
```bash
queuectl config get
```

Get specific setting:
```bash
queuectl config get max-retries
```

Update configuration:
```bash
queuectl config set max-retries 5
queuectl config set backoff-base 3
queuectl config set job-timeout 600
```

Reset to defaults:
```bash
queuectl config reset max-retries
queuectl config reset  # Reset all
```

### Configuration Options

| Key | Default | Description |
|-----|---------|-------------|
| `max_retries` | 3 | Maximum retry attempts before moving to DLQ |
| `backoff_base` | 2 | Base for exponential backoff (delay = base^attempts) |
| `backoff_max_delay` | 3600 | Maximum backoff delay in seconds (1 hour) |
| `worker_poll_interval` | 1 | Worker polling interval in seconds |
| `worker_heartbeat_interval` | 5 | Worker heartbeat update interval |
| `job_timeout` | 300 | Job execution timeout in seconds (5 minutes) |
| `db_path` | queuectl.db | Path to SQLite database |
| `log_level` | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Job Lifecycle

```
                    ┌─────────┐
                    │ PENDING │
                    └────┬────┘
                         │
                    ┌────▼────────┐
                    │ PROCESSING  │
                    └────┬────────┘
                         │
              ┌──────────┴───────────┐
              │                      │
         ┌────▼────┐          ┌─────▼─────┐
         │COMPLETED│          │  FAILED   │
         └─────────┘          └─────┬─────┘
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                    ┌────▼────┐         ┌─────▼─────┐
                    │  RETRY  │         │    DLQ    │
                    └────┬────┘         └───────────┘
                         │
                    ┌────▼────┐
                    │ PENDING │
                    └─────────┘
```

1. **PENDING**: Job is in queue, waiting to be picked up
2. **PROCESSING**: Worker is executing the job
3. **COMPLETED**: Job finished successfully (exit code 0)
4. **FAILED**: Job failed and will retry with exponential backoff
5. **DLQ**: Job exhausted all retries and moved to Dead Letter Queue

## Retry Logic

QueueCTL implements exponential backoff for failed jobs:

```
Retry Delay = backoff_base ^ attempt_number
```

Example with default settings (base=2):
- Attempt 1 fails → retry in 2 seconds
- Attempt 2 fails → retry in 4 seconds
- Attempt 3 fails → move to DLQ

Maximum delay is capped by `backoff_max_delay` (default: 3600 seconds).

## Examples

### Example 1: Process Data Files

```bash
# Enqueue multiple data processing jobs
queuectl enqueue '{"id":"process-file-1","command":"python process.py data1.csv"}'
queuectl enqueue '{"id":"process-file-2","command":"python process.py data2.csv"}'
queuectl enqueue '{"id":"process-file-3","command":"python process.py data3.csv"}'

# Start 2 workers to process in parallel
queuectl worker start --count 2

# Check progress
queuectl status
```

### Example 2: API Calls with Retry

```bash
# Configure for more retries with longer backoff
queuectl config set max-retries 5
queuectl config set backoff-base 3

# Enqueue API calls (will retry on failure)
queuectl enqueue '{"id":"api-call-1","command":"curl -X POST https://api.example.com/webhook"}'

# Start worker
queuectl worker start
```

### Example 3: Scheduled Tasks

```bash
# Enqueue backup job
queuectl enqueue '{"id":"daily-backup","command":"python backup.py --full"}'

# Enqueue report generation
queuectl enqueue '{"id":"report-gen","command":"python generate_report.py"}'

# Start worker to process
queuectl worker start
```

## Running Tests

Run the test suite:

```bash
python test_queuectl.py
```

Run the demo script:

```bash
python demo.py
```

The demo script demonstrates:
- Enqueueing jobs
- Starting workers
- Job processing
- Retry logic
- DLQ handling
- Configuration management

## Troubleshooting

### Workers Not Starting

Check if workers are already running:
```bash
queuectl status
```

Stop existing workers:
```bash
queuectl worker stop
```

### Jobs Stuck in Processing

If workers crashed, jobs may be stuck. Stop workers to release them:
```bash
queuectl worker stop
```

Jobs will move back to PENDING state.

### Database Lock Issues

Only one CLI command can write to the database at a time. If you experience locks:
- Ensure workers are stopped before running migrations
- Don't run multiple CLI commands simultaneously

### View Logs

Workers log to console. To see worker output, run workers in foreground:
```bash
python -m queuectl.worker worker-1
```

## Project Structure

```
c:\Projects\FLAM\
├── queuectl/              # Main package
│   ├── __init__.py
│   ├── cli.py             # CLI interface
│   ├── queue.py           # Queue manager
│   ├── worker.py          # Worker processes
│   ├── storage.py         # SQLite storage
│   ├── config.py          # Configuration
│   └── utils.py           # Utilities
├── demo.py                # Demo script
├── test_queuectl.py       # Test suite
├── requirements.txt       # Dependencies
├── setup.py               # Installation script
├── README.md              # This file
└── .gitignore            # Git ignore rules
```

## Advanced Features

### Custom Max Retries Per Job

You can set max retries for individual jobs:

```bash
queuectl enqueue '{"id":"job1","command":"python script.py","max_retries":5}'
```

### Job Metadata

Store additional metadata with jobs:

```bash
queuectl enqueue '{"id":"job1","command":"echo test","priority":"high","owner":"admin"}'
```

### Graceful Shutdown

Workers respond to SIGTERM and SIGINT signals:
- Current job completes
- Worker deregisters
- In-progress jobs return to PENDING

## Limitations

- Jobs must be shell commands (no Python function execution)
- Windows support for process management uses different signals
- No job priority or scheduling (FIFO order)
- No distributed workers (single-machine only)

## Future Enhancements

Potential improvements:
- Job priority queues
- Scheduled/delayed job execution
- Job dependencies and workflows
- REST API interface
- Distributed worker support
- Job result storage
- Web dashboard
- Prometheus metrics

## License

This project is created for the QueueCTL Backend Developer Internship Assignment.

## Author

Built as part of the QueueCTL Backend Developer Internship Assignment.

---

**Need Help?**

Run any command with `-h` or `--help`:
```bash
queuectl --help
queuectl worker --help
queuectl config --help
```
