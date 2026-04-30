"""Tests for launchd plist template validation."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


@pytest.fixture
def template_path() -> Path:
    """Return path to launchd template file."""
    return Path(__file__).parent.parent.parent / "install" / "services" / "com.traderbot.agent.plist"


@pytest.fixture
def template_content(template_path: Path) -> str:
    """Read template file content."""
    return template_path.read_text()


@pytest.fixture
def template_xml(template_content: str) -> ET.Element:
    """Parse template as XML."""
    return ET.fromstring(template_content)


def test_template_file_exists(template_path: Path) -> None:
    """Template file exists and is readable."""
    assert template_path.exists(), f"Template file not found: {template_path}"
    assert template_path.is_file(), f"Template path is not a file: {template_path}"


def test_template_is_valid_xml(template_content: str) -> None:
    """Template is valid XML."""
    try:
        ET.fromstring(template_content)
    except ET.ParseError as e:
        pytest.fail(f"Template is not valid XML: {e}")


def test_template_is_plist(template_xml: ET.Element) -> None:
    """Template is a valid plist document."""
    assert template_xml.tag == "plist", f"Root element should be 'plist', got '{template_xml.tag}'"
    assert template_xml.get("version") == "1.0", "Plist version should be 1.0"


def test_template_has_dict_root(template_xml: ET.Element) -> None:
    """Template has a dict as the root container."""
    dict_elem = template_xml.find("dict")
    assert dict_elem is not None, "Template should have a <dict> element"


def test_template_has_label_key(template_xml: ET.Element) -> None:
    """Template has Label key."""
    dict_elem = template_xml.find("dict")
    assert dict_elem is not None, "Template should have a <dict> element"
    keys = [elem.text for elem in dict_elem.findall("key")]
    assert "Label" in keys, "Template should have 'Label' key"


def test_template_label_has_agent_id_placeholder(template_content: str) -> None:
    """Template Label contains AGENT_ID placeholder."""
    assert "AGENT_ID" in template_content, "Template should contain AGENT_ID placeholder"
    assert "com.traderbot.agent.AGENT_ID" in template_content, "Label should use AGENT_ID placeholder"


def test_template_has_program_arguments(template_xml: ET.Element) -> None:
    """Template has ProgramArguments key."""
    dict_elem = template_xml.find("dict")
    assert dict_elem is not None, "Template should have a <dict> element"
    keys = [elem.text for elem in dict_elem.findall("key")]
    assert "ProgramArguments" in keys, "Template should have 'ProgramArguments' key"


def test_template_program_arguments_structure(template_xml: ET.Element) -> None:
    """Template ProgramArguments is an array with correct command."""
    dict_elem = template_xml.find("dict")
    assert dict_elem is not None, "Template should have a <dict> element"
    
    # Find ProgramArguments key and its following array
    found_key = False
    for elem in dict_elem:
        if elem.tag == "key" and elem.text == "ProgramArguments":
            found_key = True
        elif found_key and elem.tag == "array":
            strings = [s.text for s in elem.findall("string")]
            assert "traderbot" in strings[0], f"First arg should be traderbot binary path, got: {strings[0]}"
            assert "scan" in strings, "Should include 'scan' command"
            assert "--continuous" in strings, "Should include '--continuous' flag"
            return
    
    pytest.fail("ProgramArguments array not found or invalid")


def test_template_has_environment_variables(template_xml: ET.Element) -> None:
    """Template has EnvironmentVariables key."""
    dict_elem = template_xml.find("dict")
    assert dict_elem is not None, "Template should have a <dict> element"
    keys = [elem.text for elem in dict_elem.findall("key")]
    assert "EnvironmentVariables" in keys, "Template should have 'EnvironmentVariables' key"


def test_template_has_token_placeholder(template_content: str) -> None:
    """Template contains TOKEN_PLACEHOLDER."""
    assert "TOKEN_PLACEHOLDER" in template_content, "Template should contain TOKEN_PLACEHOLDER"
    assert "TRADERBOT_PROFILE_TOKEN" in template_content, "Template should define TRADERBOT_PROFILE_TOKEN"


def test_template_has_working_directory(template_xml: ET.Element) -> None:
    """Template has WorkingDirectory key."""
    dict_elem = template_xml.find("dict")
    assert dict_elem is not None, "Template should have a <dict> element"
    keys = [elem.text for elem in dict_elem.findall("key")]
    assert "WorkingDirectory" in keys, "Template should have 'WorkingDirectory' key"


def test_template_has_username_placeholder(template_content: str) -> None:
    """Template contains USERNAME placeholder."""
    assert "USERNAME" in template_content, "Template should contain USERNAME placeholder"
    # Should appear in WorkingDirectory and log paths
    assert template_content.count("USERNAME") >= 3, "USERNAME should appear at least 3 times (WorkingDirectory + 2 log paths)"


def test_template_has_run_at_load(template_xml: ET.Element) -> None:
    """Template has RunAtLoad set to true."""
    dict_elem = template_xml.find("dict")
    assert dict_elem is not None, "Template should have a <dict> element"
    
    # Find RunAtLoad key and its following value
    found_key = False
    for elem in dict_elem:
        if elem.tag == "key" and elem.text == "RunAtLoad":
            found_key = True
        elif found_key and elem.tag == "true":
            return  # Found RunAtLoad=true
    
    pytest.fail("RunAtLoad not set to true")


def test_template_has_keep_alive(template_xml: ET.Element) -> None:
    """Template has KeepAlive key."""
    dict_elem = template_xml.find("dict")
    assert dict_elem is not None, "Template should have a <dict> element"
    keys = [elem.text for elem in dict_elem.findall("key")]
    assert "KeepAlive" in keys, "Template should have 'KeepAlive' key"


def test_template_keep_alive_successful_exit_false(template_xml: ET.Element) -> None:
    """Template KeepAlive has SuccessfulExit=false."""
    dict_elem = template_xml.find("dict")
    assert dict_elem is not None, "Template should have a <dict> element"
    
    # Find KeepAlive key and its following dict
    found_key = False
    for elem in dict_elem:
        if elem.tag == "key" and elem.text == "KeepAlive":
            found_key = True
        elif found_key and elem.tag == "dict":
            # Check for SuccessfulExit key with false value
            keep_alive_dict = elem
            found_successful_exit = False
            for sub_elem in keep_alive_dict:
                if sub_elem.tag == "key" and sub_elem.text == "SuccessfulExit":
                    found_successful_exit = True
                elif found_successful_exit and sub_elem.tag == "false":
                    return  # Found SuccessfulExit=false
            pytest.fail("KeepAlive dict should have SuccessfulExit=false")
    
    pytest.fail("KeepAlive dict not found")


def test_template_has_standard_out_path(template_xml: ET.Element) -> None:
    """Template has StandardOutPath key."""
    dict_elem = template_xml.find("dict")
    assert dict_elem is not None, "Template should have a <dict> element"
    keys = [elem.text for elem in dict_elem.findall("key")]
    assert "StandardOutPath" in keys, "Template should have 'StandardOutPath' key"


def test_template_has_standard_error_path(template_xml: ET.Element) -> None:
    """Template has StandardErrorPath key."""
    dict_elem = template_xml.find("dict")
    assert dict_elem is not None, "Template should have a <dict> element"
    keys = [elem.text for elem in dict_elem.findall("key")]
    assert "StandardErrorPath" in keys, "Template should have 'StandardErrorPath' key"


def test_template_log_paths_use_placeholders(template_content: str) -> None:
    """Template log paths use USERNAME and AGENT_ID placeholders."""
    assert "/Users/USERNAME/Library/Logs/traderbot-AGENT_ID.log" in template_content, \
        "StandardOutPath should use USERNAME and AGENT_ID placeholders"
    assert "/Users/USERNAME/Library/Logs/traderbot-AGENT_ID-error.log" in template_content, \
        "StandardErrorPath should use USERNAME and AGENT_ID placeholders"


def test_template_has_comments(template_content: str) -> None:
    """Template includes XML comments for documentation."""
    assert "<!--" in template_content, "Template should include XML comments"
    assert "installer" in template_content.lower(), "Template should reference installer in comments"


def test_template_all_placeholders_documented(template_content: str) -> None:
    """All placeholders are documented in comments."""
    # Check that each placeholder has a comment explaining it
    assert "AGENT_ID" in template_content
    assert "TOKEN_PLACEHOLDER" in template_content
    assert "USERNAME" in template_content
    
    # Verify comments mention these placeholders
    lines = template_content.split("\n")
    comment_lines = [line for line in lines if "<!--" in line or "-->" in line]
    comment_text = " ".join(comment_lines)
    
    assert "AGENT_ID" in comment_text, "AGENT_ID should be documented in comments"
    assert "TOKEN_PLACEHOLDER" in comment_text, "TOKEN_PLACEHOLDER should be documented in comments"
    assert "USERNAME" in comment_text, "USERNAME should be documented in comments"

# Made with Bob
