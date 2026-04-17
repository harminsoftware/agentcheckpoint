import time
import random
from agentcheckpoint import checkpoint

def run_mock_agent(task_query: str, fail_on_step=False):
    print(f"Starting agent run for task: {task_query}")
    
    # Context manager handles instantiation
    with checkpoint(framework="generic", model="mock-model-xl") as cp:
        
        # Step 1: Initial Prompt
        print("[Step 1] Receiving prompt...")
        cp.step(
            messages=[{"role": "user", "content": task_query}],
            variables={"status": "initializing", "confidence": 0.0}
        )
        time.sleep(1)

        # Step 2: Planning & Tool Call
        print("[Step 2] Planning and calling tool...")
        cp.step(
            messages=[
                {"role": "user", "content": task_query},
                {"role": "assistant", "content": "I need to search for this information."}
            ],
            tool_calls=[{"tool_name": "web_search", "tool_input": {"query": task_query}, "status": "running"}],
            variables={"status": "searching", "confidence": 0.4}
        )
        time.sleep(1)

        # Simulate a crash if requested
        if fail_on_step:
            print("[CRASH] Encountered simulated API timeout!")
            raise TimeoutError("API timed out waiting for web_search response.")

        # Step 3: Tool Execution Complete
        print("[Step 3] Tool finished executing...")
        cp.step(
            messages=[
                {"role": "user", "content": task_query},
                {"role": "assistant", "content": "I need to search for this information."},
                {"role": "tool", "content": "Search results: 1. Found relevant data... 2. Found more data..."}
            ],
            tool_calls=[{"tool_name": "web_search", "tool_input": {"query": task_query}, "tool_output": "Search results: 1. Found relevant data...", "status": "completed"}],
            variables={"status": "synthesizing", "confidence": 0.85, "raw_results_count": 2}
        )
        time.sleep(1)

        # Step 4: Final Output
        print("[Step 4] Delivering final answer...")
        cp.step(
            messages=[
                {"role": "user", "content": task_query},
                {"role": "assistant", "content": "I need to search for this information."},
                {"role": "tool", "content": "Search results: 1. Found relevant data... 2. Found more data..."},
                {"role": "assistant", "content": f"Based on my search, here is the answer for '{task_query}'. The data shows... "}
            ],
            variables={"status": "done", "confidence": 0.98, "raw_results_count": 2}
        )
        print("Run completed successfully!")

if __name__ == "__main__":
    # Generate one successful run
    try:
        run_mock_agent("How to build a distributed cache in Python?")
    except Exception as e:
        pass
    
    # Generate one failing run to show the error state in dashboard
    try:
        run_mock_agent("What is the capital of France?", fail_on_step=True)
    except Exception as e:
        print(f"Caught expected error: {e}")
