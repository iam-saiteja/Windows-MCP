from fastmcp import FastMCP, Context
import inspect
from functools import wraps
import asyncio

class ProxyMCP:
    def __init__(self, mcp):
        self._mcp = mcp

    def tool(self, *args, **kwargs):
        decorator = self._mcp.tool(*args, **kwargs)

        def wrapper(func):
            sig = inspect.signature(func)
            params = list(sig.parameters.values())

            wait_param = inspect.Parameter(
                "wait_for_previous",
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=bool | None
            )

            new_params = params + [wait_param]
            new_sig = sig.replace(parameters=new_params)

            @wraps(func)
            def new_func(*f_args, **f_kwargs):
                f_kwargs.pop("wait_for_previous", None)
                return func(*f_args, **f_kwargs)

            new_func.__signature__ = new_sig
            new_func.__annotations__["wait_for_previous"] = bool | None

            return decorator(new_func)
        return wrapper

    def __getattr__(self, name):
        return getattr(self._mcp, name)

mcp = FastMCP("test")
proxy = ProxyMCP(mcp)

@proxy.tool()
def my_tool(a: int, ctx: Context = None) -> str:
    """My tool desc."""
    return f"Got {a}"

print(mcp.list_tools())
async def run():
    print(await mcp.call_tool("my_tool", {"a": 5, "wait_for_previous": True}))

asyncio.run(run())
