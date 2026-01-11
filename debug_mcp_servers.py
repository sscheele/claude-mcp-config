#!/usr/bin/env python3
"""
Debug script to test all MCP servers configured in .cursor/mcp.json
"""

import json
import subprocess
import sys
import os
import signal
import time
from pathlib import Path
from typing import Dict, Any, Optional

def expand_path(path: str) -> str:
    """Expand ~ and relative paths"""
    return os.path.expanduser(os.path.expandvars(path))

def send_mcp_request(process: subprocess.Popen, method: str, params: Dict[str, Any]) -> Optional[Dict]:
    """Send a JSON-RPC request to the MCP server"""
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }
    
    try:
        request_str = json.dumps(request) + "\n"
        process.stdin.write(request_str.encode('utf-8'))
        process.stdin.flush()
        
        # Read response with timeout
        import select
        if sys.platform != 'win32':
            # Unix-like systems
            ready, _, _ = select.select([process.stdout], [], [], 5)
            if ready:
                line = process.stdout.readline()
                if line:
                    return json.loads(line.decode('utf-8'))
        else:
            # Windows - simpler approach
            line = process.stdout.readline()
            if line:
                return json.loads(line.decode('utf-8'))
    except Exception as e:
        print(f"    Error sending request: {e}")
    return None

def test_mcp_server(name: str, config: Dict[str, Any]) -> bool:
    """Test a single MCP server configuration"""
    print(f"\n{'='*60}")
    print(f"Testing MCP Server: {name}")
    print(f"{'='*60}")
    
    # Check configuration
    if config.get("type") != "stdio":
        print(f"  ⚠️  Warning: Server type '{config.get('type')}' not supported (only 'stdio' is tested)")
        return False
    
    command = config.get("command")
    args = config.get("args", [])
    env = config.get("env", {})
    
    if not command:
        print(f"  ❌ Error: No command specified")
        return False
    
    # Expand paths in args
    expanded_args = [expand_path(arg) if arg.startswith("~") or arg.startswith("./") else arg for arg in args]
    
    # Prepare environment
    full_env = os.environ.copy()
    full_env.update(env)
    
    # Check if command exists
    if command == "docker":
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"  ❌ Error: Docker command not found or not working")
            return False
    else:
        # Check if command is in PATH
        import shutil
        if not shutil.which(command):
            print(f"  ⚠️  Warning: Command '{command}' not found in PATH")
    
    print(f"  Command: {command}")
    print(f"  Args: {expanded_args}")
    if env:
        print(f"  Env vars: {env}")
    
    # Try to start the process
    print(f"\n  Starting process...")
    try:
        process = subprocess.Popen(
            [command] + expanded_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=full_env,
            cwd=Path(__file__).parent
        )
        
        # Give it a moment to start
        time.sleep(1)
        
        # Check if process is still running
        if process.poll() is not None:
            # Process exited immediately
            stdout, stderr = process.communicate(timeout=2)
            print(f"  ❌ Error: Process exited immediately with code {process.returncode}")
            if stdout:
                print(f"  stdout: {stdout.decode('utf-8', errors='replace')[:500]}")
            if stderr:
                print(f"  stderr: {stderr.decode('utf-8', errors='replace')[:500]}")
            return False
        
        print(f"  ✓ Process started successfully (PID: {process.pid})")
        
        # Try to send initialize request
        print(f"\n  Sending initialize request...")
        init_params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "mcp-debug-script",
                "version": "1.0.0"
            }
        }
        
        response = send_mcp_request(process, "initialize", init_params)
        
        if response:
            print(f"  ✓ Received response: {json.dumps(response, indent=2)[:200]}")
            
            # Send initialized notification
            try:
                notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                }
                process.stdin.write((json.dumps(notification) + "\n").encode('utf-8'))
                process.stdin.flush()
            except Exception as e:
                print(f"  ⚠️  Warning: Could not send initialized notification: {e}")
            
            # Try to list tools/resources
            print(f"\n  Testing list tools...")
            tools_response = send_mcp_request(process, "tools/list", {})
            if tools_response:
                print(f"  ✓ Tools response received")
            
            print(f"\n  Testing list resources...")
            resources_response = send_mcp_request(process, "resources/list", {})
            if resources_response:
                print(f"  ✓ Resources response received")
            
        else:
            print(f"  ⚠️  Warning: No response to initialize request")
            # Try to read stderr for any errors
            import select
            if sys.platform != 'win32':
                ready, _, _ = select.select([process.stderr], [], [], 1)
                if ready:
                    error_line = process.stderr.readline()
                    if error_line:
                        print(f"  stderr: {error_line.decode('utf-8', errors='replace')[:500]}")
        
        # Clean up
        print(f"\n  Cleaning up...")
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        except Exception as e:
            print(f"  ⚠️  Warning during cleanup: {e}")
        
        print(f"  ✓ Server test completed")
        return True
        
    except FileNotFoundError:
        print(f"  ❌ Error: Command '{command}' not found")
        return False
    except Exception as e:
        print(f"  ❌ Error: {type(e).__name__}: {e}")
        import traceback
        print(f"  Traceback:\n{traceback.format_exc()}")
        return False

def main():
    """Main function"""
    mcp_config_path = Path(__file__).parent / ".cursor" / "mcp.json"
    
    if not mcp_config_path.exists():
        print(f"Error: MCP config file not found at {mcp_config_path}")
        sys.exit(1)
    
    print(f"Reading MCP configuration from: {mcp_config_path}")
    
    try:
        with open(mcp_config_path, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading config file: {e}")
        sys.exit(1)
    
    servers = config.get("mcpServers", {})
    
    if not servers:
        print("No MCP servers configured")
        sys.exit(0)
    
    print(f"\nFound {len(servers)} MCP server(s) to test\n")
    
    results = {}
    for name, server_config in servers.items():
        results[name] = test_mcp_server(name, server_config)
    
    # Summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    for name, success in results.items():
        status = "✓ PASS" if success else "❌ FAIL"
        print(f"  {name}: {status}")
    
    # Exit with error if any failed
    if not all(results.values()):
        sys.exit(1)

if __name__ == "__main__":
    main()
