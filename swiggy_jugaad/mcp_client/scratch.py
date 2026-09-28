# scratch.py
from swiggy_jugaad.mcp_client import instamart_session, run

async def go():
    async with instamart_session() as s:
        result = await s.call_tool("get_orders", {})
        print("isError:", result.isError)
        print("blocks:", len(result.content))
        for i, block in enumerate(result.content):
            print(f"--- block {i} ({type(block).__name__}) ---")
            print(getattr(block, "text", "<no text>"))

run(lambda: go())
