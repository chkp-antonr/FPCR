"""Business logic for CPCRUD template processing.

This module provides the core business logic for processing YAML templates,
validating them against JSON schemas, and routing operations to the appropriate
managers (ObjectManager or RuleManager).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator, validate
from ruamel.yaml import YAML

from cpcrud.config import DEFAULT_SCHEMA_PATH
from cpcrud.object_manager import CheckPointObjectManager
from cpcrud.rule_manager import CheckPointRuleManager

logger = __import__("logging").getLogger(__name__)
yaml = YAML(typ="safe")


@lru_cache(maxsize=1)
def _load_cpcrud_schema_validator() -> Draft7Validator:
    """Load and cache the JSON schema validator.

    Uses lru_cache to ensure the schema is only loaded once per session.

    Returns:
        Draft7Validator: The cached JSON schema validator.

    Raises:
        FileNotFoundError: If the schema file cannot be found.
        json.JSONDecodeError: If the schema file is not valid JSON.
    """
    schema_path = Path(DEFAULT_SCHEMA_PATH)
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path) as f:
        schema = json.load(f)

    return Draft7Validator(schema)


def validate_template_with_schema(template: dict[str, Any]) -> list[str]:
    """Validate a template against the CPCRUD JSON schema.

    Args:
        template: The loaded YAML template as a dictionary.

    Returns:
        A list of error messages. Empty list if validation passes.
    """
    errors = []
    try:
        validator = _load_cpcrud_schema_validator()
        validate(instance=template, schema=validator.schema)
    except FileNotFoundError as e:
        errors.append(f"Schema file not found: {e}")
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON in schema file: {e}")
    except Exception:
        # Collect all validation errors
        validator = _load_cpcrud_schema_validator()
        for error in validator.iter_errors(template):
            path = ".".join(str(p) for p in error.path) if error.path else "root"
            errors.append(f"Validation error at '{path}': {error.message}")

    return errors


async def apply_crud_templates(
    client: Any,
    template_files: list[str],
    no_publish: bool = False,
) -> dict[str, Any]:
    """Process YAML templates and apply CRUD operations.

    This is the main entry point for template processing. It:
    1. Loads YAML templates
    2. Validates them against the JSON schema
    3. Routes operations to ObjectManager or RuleManager based on type
    4. Aggregates results from all operations

    Args:
        client: CPAIOPSClient instance for API communication.
        template_files: List of YAML template file paths to process.
        no_publish: If True, skip publishing changes after processing.

    Returns:
        A dictionary with aggregated results containing:
        - 'success': List of successful operations
        - 'errors': List of failed operations
        - 'warnings': List of warnings
    """
    # Initialize managers
    object_manager = CheckPointObjectManager(client)
    rule_manager = CheckPointRuleManager(client)

    # Aggregate results
    aggregated_results: dict[str, Any] = {
        "success": [],
        "errors": [],
        "warnings": [],
    }

    for file_path in template_files:
        logger.info(f"Processing template: {file_path}")

        # Load YAML template
        try:
            with open(file_path) as f:
                template = yaml.load(f)
        except Exception as e:
            error_msg = f"Failed to load YAML file '{file_path}': {e}"
            logger.error(error_msg)
            aggregated_results["errors"].append(
                {"file": file_path, "error": error_msg, "error_type": "YAMLParseError"}
            )
            continue

        # Validate against schema
        validation_errors = validate_template_with_schema(template)
        if validation_errors:
            error_msg = f"Schema validation failed for '{file_path}'"
            logger.error(f"{error_msg}: {validation_errors}")
            aggregated_results["errors"].append(
                {
                    "file": file_path,
                    "error": error_msg,
                    "validation_errors": validation_errors,
                    "error_type": "SchemaValidationError",
                }
            )
            continue

        # Process each management server
        for mgmt_server in template.get("management_servers", []):
            mgmt_name = mgmt_server.get("mgmt_name")
            if not mgmt_name:
                try:
                    server_names = client.get_mgmt_names()
                    if server_names:
                        mgmt_name = server_names[0]
                        logger.info(f"Using default management server: {mgmt_name}")
                    else:
                        error_msg = "No mgmt_name specified and no management servers found"
                        logger.error(error_msg)
                        aggregated_results["errors"].append(
                            {
                                "file": file_path,
                                "error": error_msg,
                                "error_type": "NoManagementServer",
                            }
                        )
                        continue
                except Exception as e:
                    error_msg = f"Failed to retrieve management servers: {e}"
                    logger.error(error_msg)
                    aggregated_results["errors"].append(
                        {
                            "file": file_path,
                            "error": error_msg,
                            "error_type": "ManagementServerLookupError",
                        }
                    )
                    continue

            # Process each domain
            for domain_config in mgmt_server.get("domains", []):
                domain_name = domain_config.get("name", "")
                api_domain = domain_name if domain_name else "SMC User"

                # Pre-process: ensure groups exist for objects
                for op in domain_config.get("operations", []):
                    if op.get("operation") in ["add", "update"] and op.get("type") in [
                        "host",
                        "network",
                        "address-range",
                    ]:
                        groups = op.get("data", {}).get("groups", [])
                        for g in groups:
                            result = await object_manager.execute(
                                mgmt_name, domain_name, "show", "network-group", key={"name": g}
                            )
                            if not result["success"]:
                                logger.info(f"Creating missing group: {g}")
                                await object_manager.execute(
                                    mgmt_name, domain_name, "add", "network-group", data={"name": g}
                                )

                try:
                    # Process operations
                    for op in domain_config.get("operations", []):
                        operation = op.get("operation")
                        obj_type = op.get("type")

                        # Route to appropriate manager based on type
                        if obj_type in CheckPointObjectManager.SUPPORTED_OBJECT_TYPES:
                            # Object operation
                            result = await object_manager.execute(
                                mgmt_name=mgmt_name,
                                domain=domain_name,
                                operation=operation,
                                obj_type=obj_type,
                                data=op.get("data"),
                                key=op.get("key"),
                            )
                        elif obj_type in CheckPointRuleManager.SUPPORTED_RULE_TYPES:
                            # Rule operation
                            if operation == "add":
                                result = await rule_manager.add(
                                    mgmt_name=mgmt_name,
                                    domain=domain_name,
                                    rule_type=obj_type,
                                    data=op.get("data", {}),
                                )
                            elif operation == "update":
                                result = await rule_manager.update(
                                    mgmt_name=mgmt_name,
                                    domain=domain_name,
                                    rule_type=obj_type,
                                    data=op.get("data", {}),
                                    key=op.get("key", {}),
                                )
                            elif operation == "delete":
                                result = await rule_manager.delete(
                                    mgmt_name=mgmt_name,
                                    domain=domain_name,
                                    rule_type=obj_type,
                                    key=op.get("key", {}),
                                )
                            elif operation == "show":
                                result = await rule_manager.show(
                                    mgmt_name=mgmt_name,
                                    domain=domain_name,
                                    rule_type=obj_type,
                                    key=op.get("key", {}),
                                )
                            else:
                                result = {
                                    "errors": [
                                        {
                                            "operation": operation,
                                            "rule_type": obj_type,
                                            "error": f"Unsupported operation: {operation}",
                                            "error_type": "UnsupportedOperation",
                                        }
                                    ]
                                }
                        else:
                            # Unknown type
                            error_msg = f"Unsupported type: {obj_type}"
                            logger.error(error_msg)
                            aggregated_results["errors"].append(
                                {
                                    "file": file_path,
                                    "mgmt_name": mgmt_name,
                                    "domain": domain_name,
                                    "operation": operation,
                                    "type": obj_type,
                                    "error": error_msg,
                                    "error_type": "UnsupportedType",
                                }
                            )
                            continue

                        # Aggregate results
                        if result.get("success"):
                            aggregated_results["success"].extend(
                                [
                                    {
                                        "file": file_path,
                                        "mgmt_name": mgmt_name,
                                        "domain": domain_name,
                                        **success_item,
                                    }
                                    for success_item in result["success"]
                                ]
                            )
                        if result.get("errors"):
                            aggregated_results["errors"].extend(
                                [
                                    {
                                        "file": file_path,
                                        "mgmt_name": mgmt_name,
                                        "domain": domain_name,
                                        **error_item,
                                    }
                                    for error_item in result["errors"]
                                ]
                            )
                        if result.get("warnings"):
                            aggregated_results["warnings"].extend(
                                [
                                    {
                                        "file": file_path,
                                        "mgmt_name": mgmt_name,
                                        "domain": domain_name,
                                        **warning_item,
                                    }
                                    for warning_item in result["warnings"]
                                ]
                            )

                    # Publish changes
                    if not no_publish:
                        logger.info(f"Publishing changes for {mgmt_name}/{api_domain}")
                        await client.api_call(
                            mgmt_name=mgmt_name, domain=api_domain, command="publish"
                        )

                except Exception as e:
                    error_msg = f"Error processing domain '{domain_name}' on '{mgmt_name}': {e}"
                    logger.error(error_msg)
                    aggregated_results["errors"].append(
                        {
                            "file": file_path,
                            "mgmt_name": mgmt_name,
                            "domain": domain_name,
                            "error": error_msg,
                            "error_type": "DomainProcessingError",
                        }
                    )

    return aggregated_results
