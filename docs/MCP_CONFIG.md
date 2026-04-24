# MCP Configuration for Graphify

This configures the Model Context Protocol (MCP) server for graphify integration with AI agents and assistants.

---

## 🤖 What is MCP?

MCP (Model Context Protocol) allows AI assistants to query external tools and data sources in real-time. With graphify MCP, your AI assistant can:
- Query the knowledge graph dynamically
- Get node neighbors and connections
- Find shortest paths between concepts
- Retrieve god nodes and community structure
- Access graph statistics

---

## ⚙️ Configuration

### For Claude Desktop

Run the setup script from the `graphify/` directory:

```bash
cd graphify
python setup-mcp.py
```

Or manually add to `C:\Users\<username>\AppData\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fpcr-graph": {
      "command": "python",
      "args": [
        "-m",
        "graphify.serve",
        "D:\\Files\\GSe_new\\2026\\Labs\\Dev\\FPCR\\graphify-out\\graph.json"
      ],
      "description": "FPCR knowledge graph - query nodes, edges, communities, and paths"
    }
  }
}
```

> **Note:** The setup script (`graphify/setup-mcp.py`) automatically detects the correct path when run from the `graphify/` directory.

### For Claude Code (claude-code)

Claude Code uses a different config location. Check the settings for MCP server configuration.

---

## 🔧 Available MCP Tools

When MCP is configured, these tools are available to the AI assistant:

| Tool | Description |
|------|-------------|
| `query_graph` | Query the graph with a natural language question |
| `get_node` | Get detailed information about a specific node |
| `get_neighbors` | Get all neighbors of a node |
| `get_community` | Get all nodes in a community |
| `god_nodes` | Get the most connected nodes (hubs) |
| `graph_stats` | Get graph statistics (nodes, edges, communities) |
| `shortest_path` | Find shortest path between two nodes |

---

## 💡 Usage Examples

### For Brainstorming

```
When brainstorming features:
1. Call graph_stats to understand project scale
2. Call god_nodes to identify central components
3. Call query_graph for "how does [feature] relate to [component]?"
4. Use connections to identify dependencies
```

### For Planning

```
When creating implementation plans:
1. Call get_node for key components to understand context
2. Call shortest_path to identify dependencies
3. Call get_community to see related components
4. Use GRAPH_REPORT.md "Surprising Connections" for validation
```

### For Debugging

```
When investigating issues:
1. Call query_graph with error message or component name
2. Call get_neighbors to see what's connected
3. Call shortest_path between potentially related components
4. Check confidence scores (EXTRACTED vs INFERRED edges)
```

---

## 🚀 Starting the MCP Server

### Manual Start

```bash
python -m graphify.serve graphify-out/graph.json
```

### As Background Service

```bash
# Windows
Start-Process -NoNewWindow python -ArgumentList "-m","graphify.serve","graphify-out/graph.json"

# Linux/Mac
python -m graphify.serve graphify-out/graph.json &
```

### Verify MCP Server is Running

```bash
# Test MCP server
curl http://localhost:8000/health  # or configured port
```

---

## 📊 Example Queries

### Find Related Components
```json
{
  "tool": "query_graph",
  "arguments": {
    "query": "What components are connected to CacheOrchestrationService?"
  }
}
```

### Get Node Details
```json
{
  "tool": "get_node",
  "arguments": {
    "node_id": "cpcrud"
  }
}
```

### Find Path
```json
{
  "tool": "shortest_path",
  "arguments": {
    "source": "RITM",
    "target": "Domain"
  }
}
```

### Get Community
```json
{
  "tool": "get_community",
  "arguments": {
    "community_id": 0
  }
}
```

---

## 🔍 Troubleshooting

### MCP Server Not Found

**Error**: "MCP server 'fpcr-graph' not found"

**Solution**:
1. Check graphify is installed: `pip show graphifyy`
2. Check graph.json exists: `ls graphify-out/graph.json`
3. Restart Claude Desktop/Code

### Port Already in Use

**Error**: "Port 8000 already in use"

**Solution**:
```bash
# Find process using port
netstat -ano | findstr :8000  # Windows
lsof -i :8000  # Linux/Mac

# Kill process or use different port
```

### Graph Not Found

**Error**: "graph.json not found"

**Solution**:
1. Build graph first: `/graphify-labeled`
2. Check path in MCP config
3. Use absolute path in MCP config

---

## 📚 Further Reading

- [MCP Specification](https://modelcontextprotocol.io/)
- [Graphify Documentation](https://github.com/safishamsi/graphify)
- [Claude Code MCP Integration](https://code.anthropic.com)
