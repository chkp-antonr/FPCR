# graphify-relabel

Regenerate graph.html with meaningful community labels instead of generic "Community 1", "Community 2", etc.

## Usage

### After running `/graphify`

Simply run one of these commands:

**Windows (double-click):**

```
graphify-relabel.bat
```

**Windows (PowerShell):**

```powershell
.\graphify-relabel.ps1
```

**Cross-platform (Python):**

```bash
python graphify-relabel.py
```

### What it does

1. Loads `graphify-out/graph.json`
2. Extracts communities from the graph
3. Analyzes content of each community
4. Generates meaningful labels like:
   - Rulebase Processing
   - Client API Layer
   - Caching Layer
   - Domain Management
   - WebUI Components
   - Test Suite
   - Example Code
   - Documentation
   - etc.
5. Regenerates `graphify-out/graph.html` with these labels

### Output

- `graphify-out/graph.html` - Updated with meaningful community labels
- `graphify-out/community_labels.json` - Saved labels for reference

### Example

Before:

```
Community 0 - 256 nodes
Community 1 - 180 nodes
Community 2 - 95 nodes
```

After:

```
Rulebase Processing - 256 nodes
Client API Layer - 180 nodes
Caching Layer - 95 nodes
```

## Troubleshooting

**Error: "graphify-out/graph.json not found"**

- Run `/graphify` first to create the graph

**Error: "No module named 'graphify'"**

- Install graphify: `pip install graphifyy`

## Integration with graphify

This script is designed to be run immediately after `/graphify` completes. It's a post-processing step that enhances the visualization without needing to rebuild the entire graph.
