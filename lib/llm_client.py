"""
LLM client for the Dataiku LLM Mesh.
Loads config from llm_config.json and provides a simple call interface.
"""
import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "llm_config.json")


def load_config():
    """Load LLM configuration from llm_config.json."""
    with open(_CONFIG_PATH, "r") as f:
        return json.load(f)


def get_llm():
    """Return a Dataiku LLM handle based on config."""
    import dataiku
    config = load_config()
    return dataiku.api_client().get_default_project().get_llm(config["llm_id"])


def call_llm(user_prompt, system_prompt=None):
    """
    Send a prompt to the configured Dataiku LLM Mesh model.
    Returns the response text string.
    """
    config = load_config()
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
    config = load_config()
    try:
        llm = get_llm()
        completion = llm.new_completion()
        completion.with_message(
            "Respond with exactly: LLM_MESH_OK", role="user"
        )
        resp = completion.execute()
        if resp.success and resp.text.strip():
            return True, f"Connected to '{config['llm_id']}' — response: {resp.text.strip()[:80]}"
        return False, f"LLM returned empty or unsuccessful response: {resp.text}"
    except ImportError:
        return False, "dataiku module not available — run this notebook inside Dataiku DSS."
    except Exception as e:
        return False, f"Connection failed: {e}"
