"""Connect readable tool definitions to application-owned data and role checks."""
from contextvars import ContextVar
from functools import wraps

_company = ContextVar("tool_company")


def current_company():
    """Return the company service bound to this tool call, never a model argument."""
    return _company.get()


def bind_company_tools(definitions, company, require):
    """Bind each tool to an employee's access check without changing its input schema."""
    def bind(definition):
        @wraps(definition.func)
        def invoke(*args, **kwargs):
            require(definition.name)
            token = _company.set(company)
            try:
                return definition.func(*args, **kwargs)
            finally:
                _company.reset(token)

        return definition.model_copy(update={"func": invoke, "handle_tool_error": True})

    return [bind(definition) for definition in definitions]
