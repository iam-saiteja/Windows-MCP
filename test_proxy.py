import inspect
from functools import wraps

def add_param(func):
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    wait_param = inspect.Parameter(
        "wait_for_previous",
        inspect.Parameter.KEYWORD_ONLY,
        default=None,
        annotation=bool | None
    )

    new_params = params + [wait_param]
    # sort to ensure no non-default follows default?
    # KEYWORD_ONLY can follow anything.
    new_sig = sig.replace(parameters=new_params)

    @wraps(func)
    def wrapper(*args, **kwargs):
        kwargs.pop("wait_for_previous", None)
        return func(*args, **kwargs)

    wrapper.__signature__ = new_sig
    wrapper.__annotations__["wait_for_previous"] = bool | None
    return wrapper

@add_param
def my_func(a: int, b: str = "hi"):
    pass

print(inspect.signature(my_func))
print(my_func.__annotations__)
