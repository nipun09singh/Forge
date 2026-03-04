import asyncio
import sys
sys.path.insert(0, '.')

from main import build_agency

async def test_real_task():
    agency, event_log = build_agency()
    print(f"Agency: {agency.name}")
    print(f"Teams: {list(agency.teams.keys())}")
    print(f"")
    print("=" * 50)
    print("SENDING REAL TASK...")
    print("=" * 50)
    
    result = await agency.execute("Create a simple patient appointment reminder. Write a Python script called reminder.py in the data directory that takes a patient name and appointment date and prints a reminder message.")
    
    print(f"")
    print(f"Success: {result.success}")
    print(f"Output (first 500 chars):")
    print(result.output[:500] if result.output else "(empty)")
    
    # Check if any files were created
    import os
    data_dir = "./data"
    if os.path.exists(data_dir):
        files = os.listdir(data_dir)
        print(f"")
        print(f"Files in ./data/: {files}")
        if "reminder.py" in files:
            print(f"")
            print("🎉 reminder.py WAS CREATED! Content:")
            print(open(os.path.join(data_dir, "reminder.py")).read())
    
    # Show costs
    costs = event_log.cost_tracker.get_summary()
    print(f"")
    print(f"Cost:  | Tokens: {costs['total_tokens']}")

asyncio.run(test_real_task())
