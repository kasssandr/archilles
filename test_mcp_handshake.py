#!/usr/bin/env python3
"""
Test script to verify MCP server responds to initialization handshake.
This simulates what Claude Desktop should send to the server.
"""
import json
import subprocess
import sys
import os

# Set up environment like Claude Desktop would
env = os.environ.copy()
env['CALIBRE_LIBRARY_PATH'] = 'D:\\Calibre-Bibliothek'
env['RAG_DB_PATH'] = 'C:\\Users\\tomra\\archilles\\archilles_rag_db'

print("Starting MCP server subprocess...")
proc = subprocess.Popen(
    [sys.executable, 'mcp_server.py'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=env,
    text=True,
    bufsize=1
)

# Send MCP initialization request
init_request = {
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'initialize',
    'params': {
        'protocolVersion': '2024-11-05',
        'capabilities': {},
        'clientInfo': {
            'name': 'test-client',
            'version': '1.0.0'
        }
    }
}

print(f"\nSending initialization request:")
print(json.dumps(init_request, indent=2))

try:
    # Send request
    proc.stdin.write(json.dumps(init_request) + '\n')
    proc.stdin.flush()

    print("\nWaiting for response (timeout 10s)...")

    # Read response with timeout
    import select
    if sys.platform == 'win32':
        # Windows doesn't support select on pipes, just read with timeout
        import time
        start = time.time()
        response_line = None
        while time.time() - start < 10:
            if proc.poll() is not None:
                print("ERROR: Server process exited!")
                stderr = proc.stderr.read()
                print(f"STDERR:\n{stderr}")
                break
            # Try to read without blocking
            try:
                response_line = proc.stdout.readline()
                if response_line:
                    break
            except:
                pass
            time.sleep(0.1)
    else:
        # Unix: use select
        import select
        ready = select.select([proc.stdout], [], [], 10)
        if ready[0]:
            response_line = proc.stdout.readline()
        else:
            response_line = None

    if response_line:
        print(f"Received response:")
        response = json.loads(response_line.strip())
        print(json.dumps(response, indent=2))

        # Send initialized notification
        notification = {
            'jsonrpc': '2.0',
            'method': 'notifications/initialized'
        }
        print(f"\nSending initialized notification:")
        print(json.dumps(notification, indent=2))
        proc.stdin.write(json.dumps(notification) + '\n')
        proc.stdin.flush()

        print("\nSERVER HANDSHAKE SUCCESSFUL!")
        print("The server is working correctly. The issue is likely in Claude Desktop config.")

    else:
        print("ERROR: No response received within timeout")
        print("\nChecking if process is still running...")
        if proc.poll() is None:
            print("Server is still running but not responding")
            stderr = proc.stderr.read()
            print(f"STDERR:\n{stderr}")
        else:
            print("Server process has exited")
            stderr = proc.stderr.read()
            print(f"STDERR:\n{stderr}")

finally:
    proc.terminate()
    proc.wait(timeout=5)
    print("\nServer terminated")
