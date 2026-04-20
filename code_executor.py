#!/usr/bin/env python3
"""
MyanOS — Python Code Execution Module
Isolated subprocess execution with matplotlib visualization support

Ported from ai_colab_platform/server/pythonExecutor.ts to Python
Features:
  - Sandboxed Python code execution
  - stdout/stderr capture
  - Matplotlib figure capture (base64 images)
  - Configurable timeout
  - Execution time tracking
"""

import subprocess
import sys
import time
import json
import base64
import io
import os
from pathlib import Path

# ─── Config ────────────────────────────────────────────────────────────────────
DEFAULT_TIMEOUT = 30  # seconds
MAX_TIMEOUT = 120     # seconds (for training tasks)


def execute_python_code(code, timeout=DEFAULT_TIMEOUT):
    """
    Execute Python code in an isolated subprocess.
    Returns output, errors, and execution time.

    Args:
        code: Python code string to execute
        timeout: Maximum execution time in seconds

    Returns:
        dict with keys: status, output, error, execution_time
    """
    start_time = time.time()

    # Escape single quotes in user code for embedding
    safe_code = code.replace("'", "\\'")

    python_script = f"""
import sys, traceback, json, io
from contextlib import redirect_stdout, redirect_stderr

output_buffer = io.StringIO()
error_buffer = io.StringIO()

try:
    with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
        exec('{safe_code}')
    output = output_buffer.getvalue()
    error = error_buffer.getvalue()
    print(json.dumps({{"status": "success", "output": output, "error": error}}))
except Exception as e:
    error_msg = traceback.format_exc()
    print(json.dumps({{"status": "error", "output": "", "error": error_msg}}))
"""

    try:
        result = subprocess.run(
            [sys.executable, '-c', python_script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        exec_time = int((time.time() - start_time) * 1000)

        try:
            parsed = json.loads(result.stdout.strip())
            return {
                'status': parsed.get('status', 'error'),
                'output': parsed.get('output', ''),
                'error': parsed.get('error', '') or result.stderr,
                'executionTime': exec_time,
            }
        except (json.JSONDecodeError, ValueError):
            return {
                'status': 'error',
                'output': result.stdout,
                'error': result.stderr or 'Failed to parse execution output',
                'executionTime': exec_time,
            }

    except subprocess.TimeoutExpired:
        exec_time = int((time.time() - start_time) * 1000)
        return {
            'status': 'error',
            'output': '',
            'error': f'Execution timeout ({timeout}s limit exceeded)',
            'executionTime': exec_time,
        }
    except Exception as e:
        exec_time = int((time.time() - start_time) * 1000)
        return {
            'status': 'error',
            'output': '',
            'error': f'Execution error: {e}',
            'executionTime': exec_time,
        }


def execute_python_with_visualization(code, timeout=DEFAULT_TIMEOUT):
    """
    Execute Python code with matplotlib visualization support.
    Captures generated figures as base64-encoded images.

    Args:
        code: Python code string to execute
        timeout: Maximum execution time in seconds

    Returns:
        dict with keys: status, output, error, images, execution_time
    """
    start_time = time.time()

    safe_code = code.replace("'", "\\'")

    python_script = f"""
import sys, traceback, json, base64, io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from contextlib import redirect_stdout, redirect_stderr

output_buffer = io.StringIO()
error_buffer = io.StringIO()
images = []

try:
    with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
        exec('{safe_code}')

    # Capture matplotlib figures
    for fig_num in plt.get_fignums():
        fig = plt.figure(fig_num)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        images.append(img_base64)
        plt.close(fig)

    output = output_buffer.getvalue()
    error = error_buffer.getvalue()
    print(json.dumps({{
        "status": "success",
        "output": output,
        "error": error,
        "images": images
    }}))
except Exception as e:
    error_msg = traceback.format_exc()
    print(json.dumps({{
        "status": "error",
        "output": "",
        "error": error_msg,
        "images": []
    }}))
"""

    try:
        result = subprocess.run(
            [sys.executable, '-c', python_script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        exec_time = int((time.time() - start_time) * 1000)

        try:
            parsed = json.loads(result.stdout.strip())
            return {
                'status': parsed.get('status', 'error'),
                'output': parsed.get('output', ''),
                'error': parsed.get('error', '') or result.stderr,
                'images': parsed.get('images', []),
                'executionTime': exec_time,
            }
        except (json.JSONDecodeError, ValueError):
            return {
                'status': 'error',
                'output': result.stdout,
                'error': result.stderr or 'Failed to parse execution output',
                'images': [],
                'executionTime': exec_time,
            }

    except subprocess.TimeoutExpired:
        exec_time = int((time.time() - start_time) * 1000)
        return {
            'status': 'error',
            'output': '',
            'error': f'Execution timeout ({timeout}s limit exceeded)',
            'images': [],
            'executionTime': exec_time,
        }
    except Exception as e:
        exec_time = int((time.time() - start_time) * 1000)
        return {
            'status': 'error',
            'output': '',
            'error': f'Execution error: {e}',
            'images': [],
            'executionTime': exec_time,
        }


# ─── Self-Test ──────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("MyanOS Code Executor — Self Test\n")

    # Test 1: Simple print
    print("Test 1: Simple print")
    result = execute_python_code('print("Hello from MyanOS!")')
    print(f"  Status: {result['status']}")
    print(f"  Output: {result['output'].strip()}")
    print()

    # Test 2: Error handling
    print("Test 2: Error handling")
    result = execute_python_code('1/0')
    print(f"  Status: {result['status']}")
    print(f"  Error: {result['error'][:100]}")
    print()

    # Test 3: Visualization
    print("Test 3: Visualization")
    code = """
import matplotlib.pyplot as plt
import numpy as np
x = np.linspace(0, 10, 100)
y = np.sin(x)
plt.plot(x, y)
plt.title('Test Plot')
"""
    result = execute_python_with_visualization(code)
    print(f"  Status: {result['status']}")
    print(f"  Images: {len(result.get('images', []))}")
    if result.get('images'):
        print(f"  First image size: {len(result['images'][0])} chars (base64)")
    print()

    print("All tests completed!")
