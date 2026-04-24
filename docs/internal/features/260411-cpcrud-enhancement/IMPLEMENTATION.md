# CPCRUD Enhancement Implementation Notes

## Usage

### CLI

```bash
# Process templates with NAT settings and rules
fpcr cpcrud ops/templates/example-with-nat.yaml ops/templates/example-with-rules.yaml

# Process without publishing
fpcr cpcrud --no-publish ops/templates/example-with-rules.yaml
```

### Python API

```python
from cpcrud import (
    apply_crud_templates,
    CheckPointObjectManager,
    CheckPointRuleManager,
    PositionHelper,
)
import yaml

# Validate a template
from cpcrud import validate_template_with_schema
with open("template.yaml") as f:
    template = yaml.safe_load(f)
errors = validate_template_with_schema(template)

# Use managers directly
# Initialize client: from fpcr import get_client; client = await get_client()
object_mgr = CheckPointObjectManager(client)
rule_mgr = CheckPointRuleManager(client)

# Add host with NAT
result = await object_mgr.execute(
    mgmt_name="mds-prod",
    domain="DMZ",
    operation="add",
    obj_type="host",
    data={
        "name": "server-01",
        "ip-address": "10.0.1.10",
        "nat-settings": {
            "method": "static",
            "ip-address": "203.0.113.10"
        }
    }
)

# Add access rule
result = await rule_mgr.add(
    rule_type="access-rule",
    data={
        "name": "Allow HTTPS",
        "source": ["Any"],
        "destination": ["web-servers"],
        "service": ["https"],
        "action": "Accept"
    },
    mgmt_name="mds-prod",
    domain="DMZ",
    layer="Network",
    position="top"
)
```

## NAT Settings Reference

### Static NAT

```yaml
nat-settings:
  method: static
  ip-address: "203.0.113.10"  # For network
  # OR
  ipv4-address: "203.0.113.10"  # For host/address-range
```

### Hide NAT

```yaml
nat-settings:
  method: hide
  gateway: "gw-object-name"  # Maps to install-on
```

## Rule Positioning Reference

```yaml
# Absolute position
position: 1

# Layer-level
position: "top"
position: "bottom"

# Section-relative
position:
  top: "Section Name"
position:
  bottom: "Section Name"
position:
  above: "Rule Name"
position:
  below: "Rule Name"
```

## Public API

### Exports

- `apply_crud_templates(template_files, no_publish=False)` - Process YAML templates
- `validate_template_with_schema(template)` - Validate against JSON schema
- `CheckPointObjectManager(client)` - Network object CRUD manager
- `CheckPointRuleManager(client)` - Firewall rule CRUD manager
- `PositionHelper` - Rule position validation utilities
- `DEFAULT_SCHEMA_PATH` - Path to JSON schema file

### Supported Object Types

- `host` - Host objects with optional NAT
- `network` - Network objects with optional NAT
- `address-range` - Address range objects with optional NAT
- `network-group` - Network groups

### Supported Rule Types

- `access-rule` - Access control rules (requires `layer`)
- `nat-rule` - NAT rules (requires `package`)
- `threat-prevention-rule` - Threat/IPS rules (requires `layer`, add only)
- `https-rule` - HTTPS inspection rules (requires `layer`, add only)
