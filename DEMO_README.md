# QueueCTL Feature Demonstration Guide

This guide provides step-by-step instructions to demonstrate all core features of QueueCTL, covering the 5 required test scenarios.

---

## **Prerequisites**

Ensure QueueCTL is installed:
```cmd
pip install -e .
```

Clean any previous test data:
```cmd
del queuectl.db queuectl.config.json workers.pid 2>nul
```

**Windows Note:** This guide uses JSON files + `enqueue_job.py` helper to avoid CMD/PowerShell quoting issues.

---

## **Scenario 1: Basic Job Completes Successfully**

**Objective:** Demonstrate that a simple job executes and completes successfully.

### Steps:

**1.1** Create a job file `job1.json`:
```json
{
  "id": "hello-world",
  "command": "echo Hello from QueueCTL"
}
```

**1.2** Enqueue the job:
```cmd
python enqueue_job.py job1.json
```

**Expected Output:**
```
✓ Job hello-world enqueued successfully
```

**1.3** Start a worker in the background:
```cmd
python -m queuectl worker start --count 1
```

**Expected Output:**
```
Started 1 worker process(es)
Worker PIDs: [12345]
```

**1.4** Check job status:
```cmd
python -m queuectl status
```

**Expected Output:**
```
=== QueueCTL Status ===

Jobs:
State         Count
----------  -------
Pending           0
Processing        0
Completed         1
...
```

**1.5** View job details:
```cmd
python -m queuectl list
```

**Expected Output:**
```
id            state       attempts  command                      created_at
------------  --------  ----------  ---------------------------  -------------------
hello-world   completed          1  echo Hello from QueueCTL     2025-11-09 16:00:00
```

**1.6** Stop the worker:
```cmd
python -m queuectl worker stop
```

**Expected Output:**
```
Stopping 1 worker(s): [12345]
All workers stopped successfully
```

✅ **Result:** Job completed successfully with 1 attempt.

---

## **Scenario 2: Failed Job Retries with Backoff and Moves to DLQ**

**Objective:** Demonstrate exponential backoff retry mechanism and Dead Letter Queue.

### Steps:

**2.1** Configure retry settings:
```cmd
python -m queuectl config set max_retries 3
python -m queuectl config set backoff_base 2
```

**Expected Output:**
```
Configuration updated: max_retries = 3
Configuration updated: backoff_base = 2
```

**2.2** Create a failing job file `job2.json`:
```json
{
  "id": "will-fail",
  "command": "exit 1",
  "max_retries": 3
}
```

**2.3** Enqueue the failing job:
```cmd
python enqueue_job.py job2.json
```

**2.4** Start a worker and observe retry behavior:
```cmd
python -m queuectl worker run
```

**Expected Console Output (watch the timing):**
```
INFO - Worker worker-xxxxx processing job will-fail (attempt 1/3): exit 1
WARNING - Job will-fail failed (attempt 1/3): Exit code 1
INFO - Job will-fail will retry in 2s (attempt 1/3)
[~2 second delay - WATCH THE CLOCK]
INFO - Worker worker-xxxxx processing job will-fail (attempt 2/3): exit 1
WARNING - Job will-fail failed (attempt 2/3): Exit code 1
INFO - Job will-fail will retry in 4s (attempt 2/3)
[~4 second delay - EXPONENTIAL BACKOFF!]
INFO - Worker worker-xxxxx processing job will-fail (attempt 3/3): exit 1
WARNING - Job will-fail failed (attempt 3/3): Exit code 1
INFO - Job will-fail moved to DLQ after 3 attempts
```

**2.5** Stop worker with `Ctrl+C`, then check DLQ:
```cmd
python -m queuectl dlq list
```

**Expected Output:**
```
id         state    attempts  error_message               created_at
---------  -------  --------  --------------------------  -------------------
will-fail  dlq             3  Exit code 1: ...            2025-11-09 16:05:00
```

**2.6** Retry the job from DLQ:
```cmd
python -m queuectl dlq retry will-fail
```

**Expected Output:**
```
Job will-fail moved from DLQ back to pending queue
```

✅ **Result:** Job retried with exponential backoff (2s, 4s delays) and moved to DLQ after max retries.

---

## **Scenario 3: Multiple Workers Process Jobs Without Overlap**

**Objective:** Demonstrate atomic job locking prevents duplicate processing.

### Steps:

**3.1** Create 5 job files (`job3a.json` through `job3e.json`):

**job3a.json:**
```json
{"id": "job-1", "command": "echo Job 1 && timeout /t 1 /nobreak >nul"}
```

**job3b.json:**
```json
{"id": "job-2", "command": "echo Job 2 && timeout /t 1 /nobreak >nul"}
```

**job3c.json:**
```json
{"id": "job-3", "command": "echo Job 3 && timeout /t 1 /nobreak >nul"}
```

**job3d.json:**
```json
{"id": "job-4", "command": "echo Job 4 && timeout /t 1 /nobreak >nul"}
```

**job3e.json:**
```json
{"id": "job-5", "command": "echo Job 5 && timeout /t 1 /nobreak >nul"}
```

**3.2** Enqueue all jobs:
```cmd
python enqueue_job.py job3a.json
python enqueue_job.py job3b.json
python enqueue_job.py job3c.json
python enqueue_job.py job3d.json
python enqueue_job.py job3e.json
```

**3.3** Start 3 workers simultaneously:
```cmd
python -m queuectl worker start --count 3
```

**Expected Output:**
```
Started 3 worker process(es)
Worker PIDs: [12345, 12346, 12347]
```

**3.4** Monitor status in real-time:
```cmd
python -m queuectl status
```

**Observe:** Jobs being processed concurrently.

**3.5** Wait 10 seconds for completion, then list all jobs:
```cmd
python -m queuectl list
```

**Expected Output:**
```
id      state       attempts  worker_id      command
------  --------  ----------  -------------  -------------------
job-1   completed          1  worker-12345   echo Job 1 && ...
job-2   completed          1  worker-12346   echo Job 2 && ...
job-3   completed          1  worker-12347   echo Job 3 && ...
job-4   completed          1  worker-12345   echo Job 4 && ...
job-5   completed          1  worker-12346   echo Job 5 && ...
```

**3.6** Verify no duplicate processing:
```cmd
python -m queuectl list
```

**Check:** All jobs have `attempts = 1` (no job processed more than once).

**3.7** Stop workers:
```cmd
python -m queuectl worker stop
```

✅ **Result:** Multiple workers processed jobs concurrently without any duplicate processing.

---

## **Scenario 4: Invalid Commands Fail Gracefully**

**Objective:** Demonstrate robust error handling for invalid commands.

### Steps:

**4.1** Create invalid command job files:

**job4a.json:**
```json
{"id": "bad-cmd", "command": "nonexistent_command_xyz", "max_retries": 1}
```

**job4b.json:**
```json
{"id": "missing-file", "command": "python missing_script.py", "max_retries": 1}
```

**job4c.json:**
```json
{"id": "syntax-error", "command": "python -c \"invalid syntax here\"", "max_retries": 1}
```

**4.2** Enqueue the jobs:
```cmd
python enqueue_job.py job4a.json
python enqueue_job.py job4b.json
python enqueue_job.py job4c.json
```

**4.3** Start a worker:
```cmd
python -m queuectl worker run
```

**Expected Console Output:**
```
WARNING - Job bad-cmd failed (attempt 1/1): Exit code 1: 'nonexistent_command_xyz' is not recognized...
INFO - Job bad-cmd moved to DLQ after 1 attempts

WARNING - Job missing-file failed (attempt 1/1): Exit code 1: python: can't open file...
INFO - Job missing-file moved to DLQ after 1 attempts

WARNING - Job syntax-error failed (attempt 1/1): Exit code 1: SyntaxError: invalid syntax
INFO - Job syntax-error moved to DLQ after 1 attempts
```

**4.4** Stop worker with `Ctrl+C`, then check DLQ:
```cmd
python -m queuectl dlq list
```

**Expected Output:**
```
id            state    attempts  error_message
------------  -------  --------  --------------------------------------------------
bad-cmd       dlq             1  Exit code 1: 'nonexistent_command_xyz' is not...
missing-file  dlq             1  Exit code 1: python: can't open file 'missing_s...
syntax-error  dlq             1  Exit code 1: SyntaxError: invalid syntax
```

✅ **Result:** All invalid commands failed gracefully with detailed error messages captured.

---

## **Scenario 5: Job Data Survives Restart**

**Objective:** Demonstrate SQLite persistence across worker restarts.

### Steps:

**5.1** Create job files:

**job5a.json:**
```json
{"id": "persist-1", "command": "echo Starting Job 1 && timeout /t 3 /nobreak >nul && echo Done Job 1"}
```

**job5b.json:**
```json
{"id": "persist-2", "command": "echo Job 2"}
```

**job5c.json:**
```json
{"id": "persist-3", "command": "echo Job 3"}
```

**5.2** Enqueue the jobs:
```cmd
python enqueue_job.py job5a.json
python enqueue_job.py job5b.json
python enqueue_job.py job5c.json
```

**5.3** Start worker and let it process one job:
```cmd
python -m queuectl worker start --count 1
```

**5.4** Wait 5 seconds, then check status:
```cmd
python -m queuectl status
```

**Expected Output:**
```
=== QueueCTL Status ===

Jobs:
State         Count
----------  -------
Pending           2
Processing        0
Completed         1
...
```

**5.5** Simulate crash/restart - forcefully stop worker:
```cmd
python -m queuectl worker stop
```

**5.6** Verify data persisted - check status again:
```cmd
python -m queuectl status
```

**Expected Output (same counts):**
```
=== QueueCTL Status ===

Jobs:
State         Count
----------  -------
Pending           2
Processing        0
Completed         1
...
```

**5.7** List all jobs to confirm data integrity:
```cmd
python -m queuectl list
```

**Expected Output:**
```
id          state       attempts  command
----------  --------  ----------  -----------------------------------
persist-1   completed          1  echo Starting Job 1 && timeout...
persist-2   pending            0  echo Job 2
persist-3   pending            0  echo Job 3
```

**5.8** Restart worker to process remaining jobs:
```cmd
python -m queuectl worker start --count 1
```

**5.9** Wait 5 seconds and verify all jobs completed:
```cmd
python -m queuectl list
```

**Expected Output:**
```
id          state       attempts  command
----------  --------  ----------  -----------------------------------
persist-1   completed          1  echo Starting Job 1 && timeout...
persist-2   completed          1  echo Job 2
persist-3   completed          1  echo Job 3
```

**5.10** Stop worker:
```cmd
python -m queuectl worker stop
```

✅ **Result:** All job data persisted across worker restart. No data loss occurred.

---

## **Quick Demo Script (All Scenarios)**

For a fully automated demonstration, run:

```cmd
python demo_complete.py
```

This script demonstrates all 5 scenarios automatically with clear console output.

---

## **Alternative: Run Automated Test Suite**

To validate all scenarios programmatically:

```cmd
python test_queuectl_suite.py
```

**Expected Output:**
```
======================================================================
                    QUEUECTL TEST SUITE
======================================================================

✅ PASSED: Basic Job Completion
✅ PASSED: Retry & DLQ with Backoff
✅ PASSED: Concurrent Workers
✅ PASSED: Invalid Command Handling
✅ PASSED: Data Persistence

Results: 5/5 tests passed

🎉 ALL TESTS PASSED!
```

---

## **Configuration Options**

View current configuration:
```cmd
python -m queuectl config get max_retries
python -m queuectl config get backoff_base
python -m queuectl config get job_timeout
```

Modify settings:
```cmd
python -m queuectl config set max_retries 5
python -m queuectl config set backoff_base 3
python -m queuectl config set backoff_max_delay 300
python -m queuectl config set job_timeout 600
```

---

## **Troubleshooting**

**Workers not processing jobs:**
- Check worker status: `python -m queuectl worker stop` (shows if any running)
- Verify database: Check if `queuectl.db` exists
- Check logs: Workers output to console when run with `worker run`

**Jobs stuck in processing state:**
- Stop all workers: `python -m queuectl worker stop`
- Restart workers: `python -m queuectl worker start --count 1`

**Clean slate:**
```cmd
del queuectl.db queuectl.config.json workers.pid 2>nul
```

---

## **Summary**

This guide demonstrated all 5 core features:

1. ✅ **Basic Completion** - Simple jobs execute successfully
2. ✅ **Retry & DLQ** - Exponential backoff with 2^n delay formula
3. ✅ **Concurrency** - Atomic locking prevents duplicate processing
4. ✅ **Error Handling** - Invalid commands captured with detailed errors
5. ✅ **Persistence** - SQLite ensures zero data loss across restarts

**QueueCTL is production-ready for background job processing!**
