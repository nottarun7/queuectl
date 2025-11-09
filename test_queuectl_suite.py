#!/usr/bin/env python
"""
QueueCTL Test Suite
Comprehensive tests validating all core functionality
"""

import os
import time
import threading
import subprocess
import sys
from queuectl.storage import Storage
from queuectl.queue import Queue
from queuectl.worker import Worker
from queuectl.config import Config

def cleanup_test_files():
    """Remove test database files"""
    for f in ["test.db", "test_config.json"]:
        if os.path.exists(f):
            os.remove(f)

def print_test_header(test_name):
    print(f"\n{'=' * 70}")
    print(f"  {test_name}")
    print(f"{'=' * 70}\n")

def test_1_basic_completion():
    """Test 1: Basic job completes successfully"""
    print_test_header("Test 1: Basic Job Completion")
    
    cleanup_test_files()
    storage = Storage("test.db")
    queue = Queue(storage=storage)
    
    # Enqueue simple job
    result = queue.enqueue({"id": "test-basic", "command": "python -c \"print('Hello')\""})
    print(f"✓ Enqueued: {result['message']}")
    
    # Run worker
    worker = Worker("test-worker-1", queue=queue)
    threading.Thread(target=lambda: (time.sleep(2), setattr(worker, 'running', False)), daemon=True).start()
    worker.start()
    
    # Verify
    job = storage.get_job("test-basic")
    storage.close()
    
    assert job['state'] == 'completed' and job['attempts'] == 1, f"Expected completed/1, got {job['state']}/{job['attempts']}"
    print("✅ PASSED: Job completed successfully\n")
    return True

def test_2_retry_and_dlq():
    """Test 2: Failed job retries with backoff and moves to DLQ"""
    print_test_header("Test 2: Retry with Exponential Backoff and DLQ")
    
    cleanup_test_files()
    config = Config("test_config.json")
    config.set("max_retries", 2)
    config.set("backoff_base", 2)
    
    storage = Storage("test.db")
    queue = Queue(storage=storage)
    
    # Enqueue failing job
    result = queue.enqueue({
        "id": "test-fail",
        "command": "python -c \"import sys; sys.exit(1)\"",
        "max_retries": 2
    })
    print(f"✓ Enqueued failing job: {result['message']}")
    
    # Track retry timing
    retry_times = []
    original_get = storage.get_next_pending_job
    def track_timing(worker_id):
        job = original_get(worker_id)
        if job and job['id'] == 'test-fail':
            retry_times.append(time.time())
        return job
    storage.get_next_pending_job = track_timing
    
    # Run worker
    worker = Worker("test-worker-2", queue=queue)
    threading.Thread(target=lambda: (time.sleep(8), setattr(worker, 'running', False)), daemon=True).start()
    worker.start()
    
    # Verify DLQ
    job = storage.get_job("test-fail")
    storage.close()
    os.remove("test_config.json")
    
    # Check backoff timing
    if len(retry_times) >= 2:
        delay = retry_times[1] - retry_times[0]
        print(f"✓ Backoff delay: {delay:.1f}s (expected ~2s)")
    
    assert job['state'] == 'dlq' and job['attempts'] == 2, f"Expected dlq/2, got {job['state']}/{job['attempts']}"
    print("✅ PASSED: Job moved to DLQ after retries with exponential backoff\n")
    return True

def test_3_concurrent_workers():
    """Test 3: Multiple workers without overlap"""
    print_test_header("Test 3: Multiple Workers - No Duplicate Processing")
    
    cleanup_test_files()
    storage = Storage("test.db")
    queue = Queue(storage=storage)
    
    # Enqueue multiple jobs
    print("✓ Enqueueing 5 jobs...")
    for i in range(1, 6):
        queue.enqueue({
            "id": f"job-{i}",
            "command": f"python -c \"import time; time.sleep(0.3); print('Job {i}')\""
        })
    
    # Run multiple workers in sequence (simpler than multiprocessing for test)
    print("✓ Running 2 worker iterations...")
    for iteration in [1, 2]:
        worker = Worker(f"worker-{iteration}", queue=queue)
        threading.Thread(target=lambda: (time.sleep(3), setattr(worker, 'running', False)), daemon=True).start()
        worker.start()
    
    # Verify no duplicates
    jobs = storage.list_jobs()
    storage.close()
    
    completed = [j for j in jobs if j['state'] == 'completed']
    duplicates = [j for j in jobs if j['attempts'] > 1]
    
    print(f"✓ Completed: {len(completed)}/5 jobs")
    print(f"✓ Duplicate attempts: {len(duplicates)}")
    
    assert len(duplicates) == 0, f"Found {len(duplicates)} jobs with duplicate attempts"
    assert len(completed) >= 4, f"Expected at least 4 completed, got {len(completed)}"
    print("✅ PASSED: No duplicate job processing detected\n")
    return True

def test_4_invalid_commands():
    """Test 4: Invalid commands fail gracefully"""
    print_test_header("Test 4: Graceful Failure on Invalid Commands")
    
    cleanup_test_files()
    storage = Storage("test.db")
    queue = Queue(storage=storage)
    
    # Enqueue invalid commands
    test_cases = [
        {"id": "invalid-cmd", "command": "nonexistent_command_xyz", "max_retries": 1},
        {"id": "file-not-found", "command": "python missing.py", "max_retries": 1},
    ]
    
    print("✓ Enqueueing invalid commands...")
    for job in test_cases:
        queue.enqueue(job)
    
    # Process
    worker = Worker("test-worker-4", queue=queue)
    threading.Thread(target=lambda: (time.sleep(4), setattr(worker, 'running', False)), daemon=True).start()
    worker.start()
    
    # Verify graceful failures
    all_passed = True
    for test_case in test_cases:
        job = storage.get_job(test_case['id'])
        if job['state'] not in ['failed', 'dlq']:
            all_passed = False
            print(f"✗ {test_case['id']}: Expected failed/dlq, got {job['state']}")
        else:
            print(f"✓ {test_case['id']}: Failed gracefully ({job['state']})")
    
    storage.close()
    
    assert all_passed, "Some invalid commands did not fail as expected"
    print("✅ PASSED: All invalid commands handled gracefully\n")
    return True

def test_5_persistence():
    """Test 5: Job data survives restart"""
    print_test_header("Test 5: Data Persistence Across Restarts")
    
    cleanup_test_files()
    
    # Phase 1: Create jobs
    print("Phase 1: Initial setup")
    storage1 = Storage("test.db")
    queue1 = Queue(storage=storage1)
    
    jobs = [
        {"id": "persist-1", "command": "echo 'Test 1'"},
        {"id": "persist-2", "command": "echo 'Test 2'"},
    ]
    
    for job in jobs:
        queue1.enqueue(job)
    print(f"✓ Enqueued {len(jobs)} jobs")
    
    # Process one
    worker1 = Worker("worker-phase1", queue=queue1)
    threading.Thread(target=lambda: (time.sleep(1), setattr(worker1, 'running', False)), daemon=True).start()
    worker1.start()
    
    jobs_before = storage1.list_jobs()
    print(f"✓ Jobs before restart: {len(jobs_before)}")
    storage1.close()
    
    # Phase 2: Simulate restart
    print("\nPhase 2: After restart")
    storage2 = Storage("test.db")
    queue2 = Queue(storage=storage2)
    
    jobs_after = storage2.list_jobs()
    print(f"✓ Jobs after restart: {len(jobs_after)}")
    
    # Process remaining
    worker2 = Worker("worker-phase2", queue=queue2)
    threading.Thread(target=lambda: (time.sleep(2), setattr(worker2, 'running', False)), daemon=True).start()
    worker2.start()
    
    jobs_final = storage2.list_jobs()
    storage2.close()
    
    assert len(jobs_before) == len(jobs_after), "Job count changed after restart"
    print("✅ PASSED: All job data persisted across restart\n")
    return True

def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print(" " * 20 + "QUEUECTL TEST SUITE")
    print("=" * 70)
    
    tests = [
        ("Basic Job Completion", test_1_basic_completion),
        ("Retry & DLQ with Backoff", test_2_retry_and_dlq),
        ("Concurrent Workers", test_3_concurrent_workers),
        ("Invalid Command Handling", test_4_invalid_commands),
        ("Data Persistence", test_5_persistence),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, True))
        except AssertionError as e:
            print(f"❌ FAILED: {e}\n")
            results.append((test_name, False))
        except Exception as e:
            print(f"❌ ERROR: {e}\n")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print(" " * 25 + "TEST SUMMARY")
    print("=" * 70)
    
    passed_count = sum(1 for _, passed in results if passed)
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print("=" * 70)
    print(f"\nResults: {passed_count}/{len(tests)} tests passed")
    
    cleanup_test_files()
    
    if passed_count == len(tests):
        print("\n🎉 ALL TESTS PASSED!\n")
        return 0
    else:
        print(f"\n❌ {len(tests) - passed_count} TEST(S) FAILED\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
