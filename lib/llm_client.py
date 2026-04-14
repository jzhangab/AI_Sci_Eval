"""
LLM client for the Dataiku LLM Mesh.
Call configure() from the notebook before using any other functions.
"""

_config = {}


def configure(llm_id, temperature=0.1, max_tokens=4096, system_prompt=""):
    """Set LLM configuration. Must be called before any LLM operations."""
    _config.update({
        "llm_id": llm_id,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_prompt": system_prompt,
    })


def get_config():
    """Return the current config dict. Raises if configure() hasn't been called."""
    if not _config:
        raise RuntimeError("LLM not configured. Call llm_client.configure() first.")
    return _config


def get_llm():
    """Return a Dataiku LLM handle based on config."""
    import dataiku
    return dataiku.api_client().get_default_project().get_llm(get_config()["llm_id"])


def call_llm(user_prompt, system_prompt=None):
    """
    Send a prompt to the configured Dataiku LLM Mesh model.
    Returns the response text string.
    """
    config = get_config()
    llm = get_llm()
    completion = llm.new_completion()

    sys_prompt = system_prompt or config.get("system_prompt", "")
    if sys_prompt:
        completion.with_message(sys_prompt, role="system")

    completion.with_message(user_prompt, role="user")

    resp = completion.execute()
    if not resp.success:
        raise RuntimeError(f"LLM call failed: {resp.text}")
    return resp.text


def test_connection():
    """
    Quick connectivity test — sends a trivial prompt and returns status.
    Returns (success: bool, message: str).
    """
    config = get_config()
    try:
        llm = get_llm()
        completion = llm.new_completion()
        completion.with_message("Respond with exactly: LLM_MESH_OK", role="user")
        resp = completion.execute()
        if resp.success and resp.text.strip():
            return True, f"Connected to '{config['llm_id']}' — response: {resp.text.strip()[:80]}"
        return False, f"LLM returned empty or unsuccessful response: {resp.text}"
    except ImportError:
        return False, "dataiku module not available — run this notebook inside Dataiku DSS."
    except Exception as e:
        return False, f"Connection failed: {e}"
