---
name: notes-manager
description: A custom skill for managing notes and journal entries in the workspace.
---

# Notes Manager Skill

## Description
A custom skill for managing notes and journal entries in the workspace.

## Commands/Triggers
- "Take a note about [topic]"
- "Save this note: [content]"
- "Show me my notes"
- "Find notes about [topic]"
- "Create daily journal entry"

## Implementation
Uses file management tools to:
- Create and edit note files
- Organize notes in directories
- Search through notes
- Maintain a notes index

## File Structure
```
notes/
  ├── daily/
  │   ├── 2024-01-01.md
  │   └── 2024-01-02.md
  ├── topics/
  │   ├── programming.md
  │   └── ideas.md
  └── index.md
```

## Examples

### Taking a note
```
User: Take a note about meeting with team
Assistant: I'll create a note about your team meeting.
```

### Daily journal
```
User: Create today's journal entry
Assistant: I'll create a daily journal entry for today.
```

### Finding notes
```
User: Find my notes about Python
Assistant: Let me search for your Python-related notes.
```

## Procedures

### Creating a new note
1. Determine note type (daily, topic, general)
2. Create appropriate directory if needed
3. Write note content to file
4. Update notes index

### Searching notes
1. List note files in relevant directories
2. Search file contents for keywords
3. Return matching notes with context

## Best Practices
1. Use consistent naming conventions
2. Add dates to daily notes
3. Organize notes by topic or project
4. Regularly review and clean up old notes
5. Backup important notes
