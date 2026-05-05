# Graphify Integration for AI Assistants

This document configures graphify to work seamlessly with AI assistants (Claude Code, GitHub Copilot, etc.) so they always have access to project context when planning, brainstorming, or analyzing.

---

## 🤖 For Claude Code

### Native Integration (Recommended)

Run this command once to enable native graphify integration in Claude Code:

```bash
graphify claude install
```

This adds a `## graphify` section to `CLAUDE.md` that instructs Claude to:

- Check the graph before answering codebase questions
- Rebuild the graph after code changes
- Use graph context for better answers

### Manual Integration

Already configured in `CLAUDE.md` - see the "## 📊 Knowledge Graph Commands" section.

---

## 🤖 For GitHub Copilot

Copilot doesn't have native graphify support, but we can provide context through documentation.

### Export Graph for Copilot

Export the graph as markdown/wiki that Copilot can read:

```bash
/graphify-labeled . --wiki --obsidian
```

This creates:

- `graphify-out/wiki/` - Markdown documentation
- `graphify-out/obsidian/` - Obsidian vault with all nodes

### Add Context to .copilot-instructions.md

Create `.copilot-instructions.md` at your project root:

```markdown
# Context Sources for Copilot

When planning or analyzing code, also consult:

## Knowledge Graph
- See `graphify-out/wiki/index.md` for community overview
- Each community has detailed documentation in `graphify-out/wiki/community_*.md`
- Top 10 hub nodes: Domain, CacheOrchestrationService, CPAIOPSClient, CPObject, etc.

## Project Documentation
- `docs/CONTEXT.md` - Navigation map
- `docs/internal/` - Feature documentation
- `CLAUDE.md` - AI working model

## Quick Reference
- 76 communities detected in codebase
- Top communities by size: Rulebase Processing, Client API Layer, Caching Layer, Domain Management
```

---

## 🔄 Auto-Update Strategy

### For Development Workflows

1. **Before planning features**: Check graph for existing patterns
2. **After making changes**: Rebuild graph to update context
3. **For cross-session continuity**: Graph persists in `graphify-out/graph.json`

### Git Hook Integration

Install automatic graph rebuild on commits:

```bash
graphify hook install
```

After every `git commit`, the hook:

- Detects changed code files
- Re-runs AST extraction (fast, no LLM needed)
- Updates `graph.json` and `GRAPH_REPORT.md`

---

## 📋 Quick Reference for AI Assistants

### Key Commands

| Command | Purpose |
|---------|---------|
| `/graphify-labeled` | Build graph with meaningful labels |
| `/graphify . --wiki` | Build wiki for agent consumption |
| `/graphify . --obsidian` | Build Obsidian vault |
| `/graphify query "question"` | Query the graph |
| `/graphify path "A" "B"` | Find shortest path between concepts |
| `graphify hook install` | Auto-rebuild on commits |

### Graph Statistics

- **Nodes**: 2,303
- **Edges**: 6,189
- **Communities**: 76
- **Top Communities**: Rulebase Processing, Client API Layer, Caching Layer, Domain Management

### Key Hub Nodes

1. **Domain** (131 edges) - Central domain model
2. **CacheOrchestrationService** (127 edges) - Cache orchestration
3. **CPAIOPSClient** (125 edges) - Main API client
4. **CPObject** (121 edges) - Check Point object model

---

## 🎯 Usage Scenarios

### Scenario 1: Planning a New Feature

```
1. Check graph: /graphify-labeled
2. Query relevant communities: /graphify query "How does CPCRUD work?"
3. Check connections: /graphify path "CPCRUD" "Domain"
4. Plan with full context
```

### Scenario 2: Debugging

```
1. Query affected components: /graphify query "cache invalidation"
2. Find dependencies: /graphify path "CacheService" "Database"
3. Understand flow with graph structure
```

### Scenario 3: Code Review

```
1. Rebuild graph after changes: python graphify-relabel.py
2. Check new connections in GRAPH_REPORT.md
3. Verify surprising connections are intentional
```

---

## 🔧 Configuration Files

| File | Purpose |
|------|---------|
| `.graphifyignore` | What to exclude from graph |
| `graphify-out/graph.json` | Persistent graph storage |
| `graphify-out/community_labels.json` | Community name mappings |
| `graphify-out/wiki/` | Agent-consumable documentation |
| `graphify-out/obsidian/` | Obsidian vault for visual exploration |
