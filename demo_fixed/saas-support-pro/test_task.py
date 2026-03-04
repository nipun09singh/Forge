import asyncio, sys, os
sys.path.insert(0, '.')
os.makedirs('./data', exist_ok=True)

from main import build_agency

async def test():
    agency, event_log = build_agency()
    print(f"Agency: {agency.name} ({len(agency.teams)} teams)")
    print("Sending task: Create reminder.py...")
    print("")
    
    result = await agency.execute(
        "Write a Python script called reminder.py that prints 'Hello Patient! Your appointment is tomorrow at 10am'. Save it to the data directory using your read_write_file tool."
    )
    
    print(f"Success: {result.success}")
    print(f"Output: {result.output[:500]}")
    
    # Check if file was created
    if os.path.exists("./data/reminder.py"):
        print("")
        print("FILE CREATED! Content:")
        print(open("./data/reminder.py").read())
    else:
        print("")
        print("Files in data/:", os.listdir("./data"))
    
    costs = event_log.cost_tracker.get_summary()
    print(f"\nCost: ${costs['total_cost_usd']:.4f} | Tokens: {costs['total_tokens']}")

asyncio.run(test())
