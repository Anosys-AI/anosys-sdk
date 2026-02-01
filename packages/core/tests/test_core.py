"""
Tests for anosys-sdk-core package.
"""


def test_context_imports():
    """Test that context module can be imported."""
    from anosys_sdk_core.context import (
        set_user_context,
        get_user_context,
        clear_user_context,
        extract_session_id,
        extract_token,
    )
    assert callable(set_user_context)
    assert callable(get_user_context)
    assert callable(clear_user_context)
    assert callable(extract_session_id)
    assert callable(extract_token)


def test_decorators_imports():
    """Test that decorators module can be imported."""
    from anosys_sdk_core.decorators import (
        setup_api,
        anosys_logger,
        anosys_raw_logger,
    )
    assert callable(setup_api)
    assert callable(anosys_logger)
    assert callable(anosys_raw_logger)


def test_models_imports():
    """Test that models module can be imported."""
    from anosys_sdk_core.models import BASE_KEY_MAPPING, DEFAULT_STARTING_INDICES
    assert isinstance(BASE_KEY_MAPPING, dict)
    assert isinstance(DEFAULT_STARTING_INDICES, dict)


def test_redaction_imports():
    """Test that redaction module can be imported."""
    from anosys_sdk_core.redaction import redact_string, redact_dict
    assert callable(redact_string)
    assert callable(redact_dict)


def test_user_context_flow():
    """Test basic user context operations."""
    from anosys_sdk_core.context import (
        set_user_context,
        get_user_context,
        clear_user_context,
        extract_session_id,
    )
    
    # Initially should be None
    clear_user_context()
    assert get_user_context() is None
    
    # Set context
    ctx = {"session_id": "test-session-123", "token": "test-token"}
    set_user_context(ctx)
    
    # Get context
    result = get_user_context()
    assert result == ctx
    
    # Extract session ID
    session_id = extract_session_id()
    assert session_id == "test-session-123"
    
    # Clear context
    clear_user_context()
    assert get_user_context() is None
