"""
CLI interface for QueueCTL
Handles all command-line commands using argparse
"""

import argparse
import json
import sys
from tabulate import tabulate

from .queue import Queue
from .worker import WorkerManager
from .config import get_config
from .storage import JobState
from .utils import format_datetime, truncate_string, validate_job_data


def cmd_enqueue(args):
    """Handle enqueue command"""
    try:
        # Parse job data from JSON string
        job_data = json.loads(args.job_json)
        
        # Validate job data
        is_valid, error = validate_job_data(job_data)
        if not is_valid:
            print(f"Error: {error}")
            return 1
        
        # Enqueue job
        queue = Queue()
        result = queue.enqueue(job_data)
        
        if result['success']:
            print(f"✓ {result['message']}")
            return 0
        else:
            print(f"✗ {result['message']}")
            return 1
    
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON - {str(e)}")
        return 1
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


def cmd_worker_start(args):
    """Handle worker start command"""
    try:
        count = args.count or 1
        
        if count < 1 or count > 100:
            print("Error: Worker count must be between 1 and 100")
            return 1
        
        manager = WorkerManager()
        result = manager.start_workers(count)
        
        if result['success']:
            print(f"✓ {result['message']}")
            print(f"Worker PIDs: {', '.join(map(str, result['pids']))}")
            return 0
        else:
            print(f"✗ {result['message']}")
            return 1
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


def cmd_worker_stop(args):
    """Handle worker stop command"""
    try:
        manager = WorkerManager()
        result = manager.stop_workers()
        
        print(f"✓ {result['message']}")
        return 0
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


def cmd_status(args):
    """Handle status command"""
    try:
        queue = Queue()
        stats = queue.get_stats()
        
        print("\n=== QueueCTL Status ===\n")
        
        # Job statistics
        print("Jobs:")
        job_stats = stats['jobs']
        job_table = [
            ["Pending", job_stats.get(JobState.PENDING, 0)],
            ["Processing", job_stats.get(JobState.PROCESSING, 0)],
            ["Completed", job_stats.get(JobState.COMPLETED, 0)],
            ["Failed", job_stats.get(JobState.FAILED, 0)],
            ["DLQ", job_stats.get(JobState.DLQ, 0)],
            ["Total", stats['total_jobs']]
        ]
        print(tabulate(job_table, headers=["State", "Count"], tablefmt="simple"))
        
        # Worker statistics
        print("\nWorkers:")
        worker_stats = stats['workers']
        worker_table = [
            ["Active", worker_stats['active']],
            ["Total", worker_stats['total']]
        ]
        print(tabulate(worker_table, headers=["Status", "Count"], tablefmt="simple"))
        print()
        
        return 0
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


def cmd_list(args):
    """Handle list command"""
    try:
        state = args.state
        limit = args.limit or 100
        
        # Validate state
        valid_states = [JobState.PENDING, JobState.PROCESSING, JobState.COMPLETED, 
                       JobState.FAILED, JobState.DLQ]
        if state and state not in valid_states:
            print(f"Error: Invalid state. Must be one of: {', '.join(valid_states)}")
            return 1
        
        queue = Queue()
        jobs = queue.list_jobs(state=state, limit=limit)
        
        if not jobs:
            print(f"No jobs found{' in state: ' + state if state else ''}")
            return 0
        
        # Format job list
        table_data = []
        for job in jobs:
            table_data.append([
                truncate_string(job['id'], 20),
                truncate_string(job['command'], 40),
                job['state'],
                job['attempts'],
                job['max_retries'],
                format_datetime(job['created_at']),
                truncate_string(job.get('error_message', '') or '', 30)
            ])
        
        headers = ["Job ID", "Command", "State", "Attempts", "Max Retries", "Created", "Error"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\nTotal: {len(jobs)} job(s)")
        
        return 0
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


def cmd_dlq_list(args):
    """Handle DLQ list command"""
    try:
        limit = args.limit or 100
        
        queue = Queue()
        jobs = queue.get_dlq_jobs(limit=limit)
        
        if not jobs:
            print("No jobs in Dead Letter Queue")
            return 0
        
        # Format job list
        table_data = []
        for job in jobs:
            table_data.append([
                truncate_string(job['id'], 20),
                truncate_string(job['command'], 40),
                job['attempts'],
                format_datetime(job['updated_at']),
                truncate_string(job.get('error_message', '') or '', 40)
            ])
        
        headers = ["Job ID", "Command", "Attempts", "Last Updated", "Error"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\nTotal: {len(jobs)} job(s) in DLQ")
        
        return 0
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


def cmd_dlq_retry(args):
    """Handle DLQ retry command"""
    try:
        job_id = args.job_id
        
        queue = Queue()
        result = queue.retry_job(job_id)
        
        if result['success']:
            print(f"✓ {result['message']}")
            return 0
        else:
            print(f"✗ {result['message']}")
            return 1
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


def cmd_config_get(args):
    """Handle config get command"""
    try:
        config = get_config()
        
        if args.key:
            value = config.get(args.key)
            if value is not None:
                print(f"{args.key}: {value}")
                return 0
            else:
                print(f"Error: Configuration key '{args.key}' not found")
                return 1
        else:
            # Show all configuration
            all_config = config.get_all()
            table_data = [[k, v] for k, v in sorted(all_config.items())]
            print(tabulate(table_data, headers=["Key", "Value"], tablefmt="simple"))
            return 0
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


def cmd_config_set(args):
    """Handle config set command"""
    try:
        config = get_config()
        
        # Try to parse value as int if possible
        value = args.value
        try:
            value = int(value)
        except (ValueError, TypeError):
            pass
        
        success = config.set(args.key, value)
        
        if success:
            print(f"✓ Configuration updated: {args.key} = {value}")
            return 0
        else:
            print(f"✗ Failed to update configuration")
            return 1
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


def cmd_config_reset(args):
    """Handle config reset command"""
    try:
        config = get_config()
        
        if args.key:
            success = config.reset(args.key)
            if success:
                print(f"✓ Configuration key '{args.key}' reset to default")
                return 0
            else:
                print(f"✗ Failed to reset key '{args.key}'")
                return 1
        else:
            success = config.reset()
            if success:
                print("✓ All configuration reset to defaults")
                return 0
            else:
                print("✗ Failed to reset configuration")
                return 1
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        prog='queuectl',
        description='QueueCTL - A CLI-based background job queue system'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Enqueue command
    parser_enqueue = subparsers.add_parser('enqueue', help='Add a new job to the queue')
    parser_enqueue.add_argument('job_json', help='Job data as JSON string')
    parser_enqueue.set_defaults(func=cmd_enqueue)
    
    # Worker commands
    parser_worker = subparsers.add_parser('worker', help='Manage workers')
    worker_subparsers = parser_worker.add_subparsers(dest='worker_command')
    
    parser_worker_start = worker_subparsers.add_parser('start', help='Start workers')
    parser_worker_start.add_argument('--count', type=int, default=1, 
                                    help='Number of workers to start (default: 1)')
    parser_worker_start.set_defaults(func=cmd_worker_start)
    
    parser_worker_run = worker_subparsers.add_parser('run', help='Run a single worker in the foreground')
    parser_worker_run.add_argument('--id', dest='worker_id', help='Optional worker id')
    parser_worker_run.add_argument('--exit-when-idle', action='store_true',
                                   help='Exit automatically when the queue is idle')
    parser_worker_run.add_argument('--max-idle', type=int, default=10,
                                   help='Seconds of idle time before exiting when --exit-when-idle is set (default: 10)')
    parser_worker_run.set_defaults(func=cmd_worker_run)
    parser_worker_stop = worker_subparsers.add_parser('stop', help='Stop all workers')
    parser_worker_stop.set_defaults(func=cmd_worker_stop)
    
    # Status command
    parser_status = subparsers.add_parser('status', help='Show queue and worker status')
    parser_status.set_defaults(func=cmd_status)
    
    # List command
    parser_list = subparsers.add_parser('list', help='List jobs')
    parser_list.add_argument('--state', choices=[JobState.PENDING, JobState.PROCESSING, 
                            JobState.COMPLETED, JobState.FAILED, JobState.DLQ],
                            help='Filter by job state')
    parser_list.add_argument('--limit', type=int, default=100, 
                            help='Maximum number of jobs to show (default: 100)')
    parser_list.set_defaults(func=cmd_list)
    
    # DLQ commands
    parser_dlq = subparsers.add_parser('dlq', help='Manage Dead Letter Queue')
    dlq_subparsers = parser_dlq.add_subparsers(dest='dlq_command')
    
    parser_dlq_list = dlq_subparsers.add_parser('list', help='List jobs in DLQ')
    parser_dlq_list.add_argument('--limit', type=int, default=100,
                                help='Maximum number of jobs to show (default: 100)')
    parser_dlq_list.set_defaults(func=cmd_dlq_list)
    
    parser_dlq_retry = dlq_subparsers.add_parser('retry', help='Retry a job from DLQ')
    parser_dlq_retry.add_argument('job_id', help='Job ID to retry')
    parser_dlq_retry.set_defaults(func=cmd_dlq_retry)
    
    # Config commands
    parser_config = subparsers.add_parser('config', help='Manage configuration')
    config_subparsers = parser_config.add_subparsers(dest='config_command')
    
    parser_config_get = config_subparsers.add_parser('get', help='Get configuration value')
    parser_config_get.add_argument('key', nargs='?', help='Configuration key (optional)')
    parser_config_get.set_defaults(func=cmd_config_get)
    
    parser_config_set = config_subparsers.add_parser('set', help='Set configuration value')
    parser_config_set.add_argument('key', help='Configuration key')
    parser_config_set.add_argument('value', help='Configuration value')
    parser_config_set.set_defaults(func=cmd_config_set)
    
    parser_config_reset = config_subparsers.add_parser('reset', help='Reset configuration')
    parser_config_reset.add_argument('key', nargs='?', help='Configuration key to reset (optional)')
    parser_config_reset.set_defaults(func=cmd_config_reset)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute command
    if hasattr(args, 'func'):
        return args.func(args)
    else:
        parser.print_help()
        return 1


def cmd_worker_run(args):
    """Run a single worker in the foreground (blocking)"""
    try:
        worker_id = args.worker_id if hasattr(args, 'worker_id') and args.worker_id else f"worker-foreground-{int(__import__('time').time())}"
        manager = WorkerManager()
        # Run worker in current process; allow exiting when idle if requested
        exit_on_idle = getattr(args, 'exit_when_idle', False)
        max_idle = getattr(args, 'max_idle', 10)
        manager._run_worker(worker_id, exit_on_idle=exit_on_idle, max_idle_seconds=max_idle)
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
